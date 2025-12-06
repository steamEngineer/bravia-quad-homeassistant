"""Client for communicating with Bravia Quad device."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from typing import TYPE_CHECKING, Any

from .const import (
    AUTO_STANDBY_OFF,
    CMD_ID_AUDIO,
    CMD_ID_AUTO_STANDBY,
    CMD_ID_HDMI_CEC,
    CMD_ID_INITIAL,
    CMD_ID_INPUT,
    CMD_ID_MAX,
    CMD_ID_POWER,
    CMD_ID_VOLUME,
    DEFAULT_PORT,
    FEATURE_AUTO_STANDBY,
    FEATURE_BASS_LEVEL,
    FEATURE_HDMI_CEC,
    FEATURE_INPUT,
    FEATURE_NIGHT_MODE,
    FEATURE_POWER,
    FEATURE_REAR_LEVEL,
    FEATURE_SOUND_FIELD,
    FEATURE_VOICE_ENHANCER,
    FEATURE_VOLUME,
    HDMI_CEC_OFF,
    MAX_BASS_LEVEL,
    MAX_BASS_LEVEL_NO_SUB,
    MAX_REAR_LEVEL,
    MAX_VOLUME,
    MIN_BASS_LEVEL,
    MIN_BASS_LEVEL_NO_SUB,
    MIN_REAR_LEVEL,
    MIN_VOLUME,
    NIGHT_MODE_OFF,
    POWER_OFF,
    SOUND_FIELD_OFF,
    TCP_TIMEOUT,
    VOICE_ENHANCER_OFF,
)

if TYPE_CHECKING:
    from collections.abc import Callable

_LOGGER = logging.getLogger(__name__)

# Default bass level (MID)
DEFAULT_BASS_LEVEL = 1


class BraviaQuadClient:
    """Client for Bravia Quad TCP communication."""

    def __init__(self, host: str, name: str) -> None:
        """Initialize the Bravia Quad client."""
        self.host = host
        self.port = DEFAULT_PORT
        self.name = name
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._connected = False
        self._listening = False
        self._notification_callbacks: dict[str, list[Callable]] = {}
        self._power_state = POWER_OFF
        self._volume = 0
        self._input = "tv"  # Default input
        self._rear_level = 0
        self._bass_level = DEFAULT_BASS_LEVEL
        self._voice_enhancer = VOICE_ENHANCER_OFF
        self._sound_field = SOUND_FIELD_OFF
        self._night_mode = NIGHT_MODE_OFF
        self._hdmi_cec = HDMI_CEC_OFF
        self._auto_standby = AUTO_STANDBY_OFF
        self._command_id_counter = CMD_ID_INITIAL
        self._command_lock = asyncio.Lock()
        self._pending_responses: dict[int, asyncio.Future] = {}
        self._listener_task: asyncio.Task | None = None

    async def async_connect(self) -> None:
        """Connect to the Bravia Quad device."""
        if self._connected:
            return

        try:
            self._reader, self._writer = await asyncio.wait_for(
                asyncio.open_connection(self.host, self.port),
                timeout=TCP_TIMEOUT,
            )
            # Give the connection a moment to stabilize
            await asyncio.sleep(0.1)
            self._connected = True
            _LOGGER.info("Connected to Bravia Quad at %s:%s", self.host, self.port)
        except OSError as err:
            self._connected = False
            _LOGGER.exception("Failed to connect to Bravia Quad")
            raise ConnectionError(str(err)) from err

    async def async_disconnect(self) -> None:
        """Disconnect from the Bravia Quad device."""
        self._listening = False
        if self._listener_task:
            self._listener_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._listener_task
            self._listener_task = None
        if self._writer:
            self._writer.close()
            with contextlib.suppress(OSError):
                await self._writer.wait_closed()
        self._reader = None
        self._writer = None
        self._connected = False

        # Fail any pending command futures
        for future in self._pending_responses.values():
            if not future.done():
                future.set_exception(ConnectionError("Disconnected"))
        self._pending_responses.clear()

        _LOGGER.info("Disconnected from Bravia Quad")

    async def async_test_connection(self) -> bool:
        """Test connection by sending a power status request."""
        if not self._connected:
            await self.async_connect()

        try:
            command = {
                "id": CMD_ID_POWER,
                "type": "get",
                "feature": FEATURE_POWER,
            }
            response = await self.async_send_command(command)

            if (
                response
                and response.get("type") == "result"
                and response.get("feature") == FEATURE_POWER
            ):
                self._power_state = response.get("value", POWER_OFF)
                return True
        except (OSError, ConnectionError):
            _LOGGER.exception("Test connection failed")
        return False

    async def async_send_command(
        self, command: dict[str, Any]
    ) -> dict[str, Any] | None:
        """Send a command and wait for response."""
        if not self._connected:
            await self.async_connect()

        if not self._writer or not self._reader:
            msg = "Not connected to device"
            raise ConnectionError(msg)

        if not self._listener_task or self._listener_task.done():
            await self.async_listen_for_notifications()

        response_future: asyncio.Future | None = None
        command_id: int | None = None

        async with self._command_lock:
            try:
                # Always assign a unique command id
                command = dict(command)
                command_id = self._get_next_command_id()
                command["id"] = command_id

                loop = asyncio.get_running_loop()
                response_future = loop.create_future()
                self._pending_responses[command_id] = response_future

                command_json = json.dumps(command) + "\n"
                _LOGGER.debug("Sending command: %s", command_json.strip())
                self._writer.write(command_json.encode())
                await self._writer.drain()
            except OSError as err:
                if command_id is not None and command_id in self._pending_responses:
                    self._pending_responses.pop(command_id, None)
                _LOGGER.exception("Error sending command")
                raise ConnectionError(str(err)) from err

        try:
            response = await asyncio.wait_for(response_future, timeout=TCP_TIMEOUT)
        except TimeoutError:
            if response_future and not response_future.done():
                response_future.cancel()
            _LOGGER.warning("Timeout waiting for response to command: %s", command)
            return None
        else:
            return response
        finally:
            if command_id is not None:
                self._pending_responses.pop(command_id, None)

    async def async_set_power(self, state: str) -> bool:
        """Set power state (on/off)."""
        command = {
            "id": CMD_ID_POWER,
            "type": "set",
            "feature": FEATURE_POWER,
            "value": state,
        }
        response = await self.async_send_command(command)

        if (
            response
            and response.get("type") == "result"
            and response.get("value") == "ACK"
        ):
            self._power_state = state
            return True
        return False

    async def async_set_volume(self, volume: int) -> bool:
        """Set volume (0-100)."""
        if volume < MIN_VOLUME or volume > MAX_VOLUME:
            msg = f"Volume must be between {MIN_VOLUME} and {MAX_VOLUME}"
            raise ValueError(msg)

        command = {
            "id": CMD_ID_VOLUME,
            "type": "set",
            "feature": FEATURE_VOLUME,
            "value": volume,
        }
        response = await self.async_send_command(command)

        if (
            response
            and response.get("type") == "result"
            and response.get("value") == "ACK"
        ):
            self._volume = volume
            return True
        return False

    async def async_get_power(self) -> str:
        """Get current power state."""
        command = {
            "id": CMD_ID_POWER,
            "type": "get",
            "feature": FEATURE_POWER,
        }
        response = await self.async_send_command(command)

        if (
            response
            and response.get("type") == "result"
            and response.get("feature") == FEATURE_POWER
        ):
            self._power_state = response.get("value", POWER_OFF)
            return self._power_state
        return self._power_state

    async def async_get_volume(self) -> int:
        """Get current volume."""
        command = {
            "id": CMD_ID_VOLUME,
            "type": "get",
            "feature": FEATURE_VOLUME,
        }
        response = await self.async_send_command(command)

        if (
            response
            and response.get("type") == "result"
            and response.get("feature") == FEATURE_VOLUME
        ):
            try:
                volume = int(response.get("value", 0))
                if MIN_VOLUME <= volume <= MAX_VOLUME:
                    self._volume = volume
                    return self._volume
            except (ValueError, TypeError):
                pass  # Invalid response value, return cached state
        return self._volume

    async def async_set_input(self, input_value: str) -> bool:
        """Set input (tv, hdmi1, spotify)."""
        command = {
            "id": CMD_ID_INPUT,
            "type": "set",
            "feature": FEATURE_INPUT,
            "value": input_value,
        }
        response = await self.async_send_command(command)

        if (
            response
            and response.get("type") == "result"
            and response.get("value") == "ACK"
        ):
            self._input = input_value
            return True
        return False

    async def async_get_input(self) -> str:
        """Get current input."""
        command = {
            "id": CMD_ID_INPUT,
            "type": "get",
            "feature": FEATURE_INPUT,
        }
        response = await self.async_send_command(command)

        if (
            response
            and response.get("type") == "result"
            and response.get("feature") == FEATURE_INPUT
        ):
            self._input = response.get("value", "tv")
            return self._input
        return self._input

    async def async_set_voice_enhancer(self, state: str) -> bool:
        """Set voice enhancer state (upon/upoff)."""
        command = {
            "id": CMD_ID_AUDIO,
            "type": "set",
            "feature": FEATURE_VOICE_ENHANCER,
            "value": state,
        }
        response = await self.async_send_command(command)

        if (
            response
            and response.get("type") == "result"
            and response.get("value") == "ACK"
        ):
            self._voice_enhancer = state
            return True
        return False

    async def async_get_voice_enhancer(self) -> str:
        """Get current voice enhancer state."""
        command = {
            "id": CMD_ID_AUDIO,
            "type": "get",
            "feature": FEATURE_VOICE_ENHANCER,
        }
        response = await self.async_send_command(command)

        if (
            response
            and response.get("type") == "result"
            and response.get("feature") == FEATURE_VOICE_ENHANCER
        ):
            self._voice_enhancer = response.get("value", VOICE_ENHANCER_OFF)
            return self._voice_enhancer
        return self._voice_enhancer

    async def async_set_sound_field(self, state: str) -> bool:
        """Set sound field state (on/off)."""
        command = {
            "id": CMD_ID_AUDIO,
            "type": "set",
            "feature": FEATURE_SOUND_FIELD,
            "value": state,
        }
        response = await self.async_send_command(command)

        if (
            response
            and response.get("type") == "result"
            and response.get("value") == "ACK"
        ):
            self._sound_field = state
            return True
        return False

    async def async_get_sound_field(self) -> str:
        """Get current sound field state."""
        command = {
            "id": CMD_ID_AUDIO,
            "type": "get",
            "feature": FEATURE_SOUND_FIELD,
        }
        response = await self.async_send_command(command)

        if (
            response
            and response.get("type") == "result"
            and response.get("feature") == FEATURE_SOUND_FIELD
        ):
            self._sound_field = response.get("value", SOUND_FIELD_OFF)
            return self._sound_field
        return self._sound_field

    async def async_set_night_mode(self, state: str) -> bool:
        """Set night mode state (on/off)."""
        command = {
            "id": CMD_ID_AUDIO,
            "type": "set",
            "feature": FEATURE_NIGHT_MODE,
            "value": state,
        }
        response = await self.async_send_command(command)

        if (
            response
            and response.get("type") == "result"
            and response.get("value") == "ACK"
        ):
            self._night_mode = state
            return True
        return False

    async def async_get_night_mode(self) -> str:
        """Get current night mode state."""
        command = {
            "id": CMD_ID_AUDIO,
            "type": "get",
            "feature": FEATURE_NIGHT_MODE,
        }
        response = await self.async_send_command(command)

        if (
            response
            and response.get("type") == "result"
            and response.get("feature") == FEATURE_NIGHT_MODE
        ):
            self._night_mode = response.get("value", NIGHT_MODE_OFF)
            return self._night_mode
        return self._night_mode

    async def async_set_hdmi_cec(self, state: str) -> bool:
        """Enable or disable HDMI CEC."""
        command = {
            "id": CMD_ID_HDMI_CEC,
            "type": "set",
            "feature": FEATURE_HDMI_CEC,
            "value": state,
        }
        response = await self.async_send_command(command)

        if (
            response
            and response.get("type") == "result"
            and response.get("value") == "ACK"
        ):
            self._hdmi_cec = state
            return True
        return False

    async def async_get_hdmi_cec(self) -> str:
        """Get current HDMI CEC state."""
        command = {
            "id": CMD_ID_HDMI_CEC,
            "type": "get",
            "feature": FEATURE_HDMI_CEC,
        }
        response = await self.async_send_command(command)

        if (
            response
            and response.get("type") == "result"
            and response.get("feature") == FEATURE_HDMI_CEC
        ):
            self._hdmi_cec = response.get("value", HDMI_CEC_OFF)
            return self._hdmi_cec
        return self._hdmi_cec

    async def async_set_auto_standby(self, state: str) -> bool:
        """Enable or disable auto standby."""
        command = {
            "id": CMD_ID_AUTO_STANDBY,
            "type": "set",
            "feature": FEATURE_AUTO_STANDBY,
            "value": state,
        }
        response = await self.async_send_command(command)

        if (
            response
            and response.get("type") == "result"
            and response.get("value") == "ACK"
        ):
            self._auto_standby = state
            return True
        return False

    async def async_get_auto_standby(self) -> str:
        """Get current auto standby state."""
        command = {
            "id": CMD_ID_AUTO_STANDBY,
            "type": "get",
            "feature": FEATURE_AUTO_STANDBY,
        }
        response = await self.async_send_command(command)

        if (
            response
            and response.get("type") == "result"
            and response.get("feature") == FEATURE_AUTO_STANDBY
        ):
            self._auto_standby = response.get("value", AUTO_STANDBY_OFF)
            return self._auto_standby
        return self._auto_standby

    async def async_set_rear_level(self, level: int) -> bool:
        """Set rear level (-10 to 10)."""
        if level < MIN_REAR_LEVEL or level > MAX_REAR_LEVEL:
            msg = f"Rear level must be between {MIN_REAR_LEVEL} and {MAX_REAR_LEVEL}"
            raise ValueError(msg)

        command = {
            "id": CMD_ID_VOLUME,
            "type": "set",
            "feature": FEATURE_REAR_LEVEL,
            "value": level,
        }
        response = await self.async_send_command(command)

        if (
            response
            and response.get("type") == "result"
            and response.get("value") == "ACK"
        ):
            self._rear_level = level
            return True
        return False

    async def async_get_rear_level(self) -> int:
        """Get current rear level."""
        command = {
            "id": CMD_ID_VOLUME,
            "type": "get",
            "feature": FEATURE_REAR_LEVEL,
        }
        response = await self.async_send_command(command)

        if (
            response
            and response.get("type") == "result"
            and response.get("feature") == FEATURE_REAR_LEVEL
        ):
            try:
                rear_level = int(response.get("value", 0))
                if MIN_REAR_LEVEL <= rear_level <= MAX_REAR_LEVEL:
                    self._rear_level = rear_level
                    return self._rear_level
            except (ValueError, TypeError):
                pass  # Invalid response value, return cached state
        return self._rear_level

    async def async_set_bass_level(self, level: int) -> bool:
        """
        Set bass level.

        With subwoofer: -10 to 10 (slider)
        Without subwoofer: 0 (MIN), 1 (MID), 2 (MAX) (select)
        """
        if level < MIN_BASS_LEVEL or level > MAX_BASS_LEVEL:
            msg = f"Bass level must be between {MIN_BASS_LEVEL} and {MAX_BASS_LEVEL}"
            raise ValueError(msg)

        command = {
            "id": CMD_ID_VOLUME,
            "type": "set",
            "feature": FEATURE_BASS_LEVEL,
            "value": level,
        }
        response = await self.async_send_command(command)

        if (
            response
            and response.get("type") == "result"
            and response.get("value") == "ACK"
        ):
            self._bass_level = level
            return True
        return False

    async def async_get_bass_level(self) -> int:
        """Get current bass level."""
        command = {
            "id": CMD_ID_VOLUME,
            "type": "get",
            "feature": FEATURE_BASS_LEVEL,
        }
        response = await self.async_send_command(command)

        if (
            response
            and response.get("type") == "result"
            and response.get("feature") == FEATURE_BASS_LEVEL
        ):
            try:
                bass_level = int(response.get("value", DEFAULT_BASS_LEVEL))
                if MIN_BASS_LEVEL <= bass_level <= MAX_BASS_LEVEL:
                    self._bass_level = bass_level
                    return self._bass_level
            except (ValueError, TypeError):
                pass  # Invalid response value, return cached state
        return self._bass_level

    async def async_detect_subwoofer(self) -> bool:
        """
        Detect if subwoofer is connected by testing bass level range.

        Returns True if subwoofer is detected (supports -10 to 10 range).
        Returns False if no subwoofer (only supports 0-2 select mode).
        """
        # Get current bass level
        current_level = await self.async_get_bass_level()

        # If already outside 0-2 range, definitely has subwoofer
        if (
            current_level < MIN_BASS_LEVEL_NO_SUB
            or current_level > MAX_BASS_LEVEL_NO_SUB
        ):
            _LOGGER.info(
                "Subwoofer detected: bass level %d is outside 0-2 range",
                current_level,
            )
            return True

        # Try setting to -1 (invalid without subwoofer)
        test_value = -1
        command = {
            "id": CMD_ID_VOLUME,
            "type": "set",
            "feature": FEATURE_BASS_LEVEL,
            "value": test_value,
        }
        response = await self.async_send_command(command)

        if (
            response
            and response.get("type") == "result"
            and response.get("value") == "ACK"
        ):
            # Successfully set to -1, subwoofer is connected
            _LOGGER.info(
                "Subwoofer detected: device accepted bass level %d", test_value
            )
            # Revert to original value. Note: there's a brief window where user
            # bass level changes could be overwritten, but this is acceptable
            # given detection is rare and the window is very short.
            revert_command = {
                "id": CMD_ID_VOLUME,
                "type": "set",
                "feature": FEATURE_BASS_LEVEL,
                "value": current_level,
            }
            await self.async_send_command(revert_command)
            self._bass_level = current_level
            return True

        # Device rejected -1, no subwoofer connected
        _LOGGER.info("No subwoofer detected: device rejected bass level %d", test_value)
        return False

    def register_notification_callback(self, feature: str, callback: Callable) -> None:
        """Register a callback for notifications."""
        if feature not in self._notification_callbacks:
            self._notification_callbacks[feature] = []
        self._notification_callbacks[feature].append(callback)

    async def async_listen_for_notifications(self) -> None:
        """Ensure the notification listener is running."""
        if self._listener_task and not self._listener_task.done():
            return

        if not self._connected:
            await self.async_connect()

        self._listener_task = asyncio.create_task(self._notification_loop())

    async def _notification_loop(self) -> None:
        """Listen for real-time notifications from the device."""
        self._listening = True
        _LOGGER.info("Starting notification listener")

        try:
            while self._listening and self._connected:
                try:
                    if not self._reader:
                        break

                    data = await asyncio.wait_for(self._reader.read(1024), timeout=1.0)

                    if not data:
                        await asyncio.sleep(0.1)
                        continue

                    response_str = data.decode("utf-8", errors="replace").strip()
                    if not response_str:
                        continue

                    messages = self._decode_json_stream(response_str)
                    if not messages:
                        continue

                    for message in messages:
                        await self._process_incoming_message(message)
                except TimeoutError:
                    continue
                except asyncio.CancelledError:
                    raise
                except OSError:
                    _LOGGER.exception("Error in notification listener")
                    await asyncio.sleep(1.0)
        except asyncio.CancelledError:
            _LOGGER.info("Notification listener cancelled")
            raise
        finally:
            self._listening = False
            _LOGGER.info("Notification listener stopped")

    @property
    def is_connected(self) -> bool:
        """Return connection status."""
        return self._connected

    @property
    def power_state(self) -> str:
        """Return current power state."""
        return self._power_state

    @property
    def volume(self) -> int:
        """Return current volume."""
        return self._volume

    @property
    def input(self) -> str:
        """Return current input."""
        return self._input

    @property
    def voice_enhancer(self) -> str:
        """Return current voice enhancer state."""
        return self._voice_enhancer

    @property
    def sound_field(self) -> str:
        """Return current sound field state."""
        return self._sound_field

    @property
    def night_mode(self) -> str:
        """Return current night mode state."""
        return self._night_mode

    @property
    def hdmi_cec(self) -> str:
        """Return current HDMI CEC state."""
        return self._hdmi_cec

    @property
    def auto_standby(self) -> str:
        """Return current auto standby state."""
        return self._auto_standby

    @property
    def rear_level(self) -> int:
        """Return current rear level."""
        return self._rear_level

    @property
    def bass_level(self) -> int:
        """Return current bass level."""
        return self._bass_level

    async def async_fetch_all_states(self) -> None:
        """Fetch all current states from the device."""
        _LOGGER.debug("Fetching all device states")

        fetchers = [
            self.async_get_power,
            self.async_get_volume,
            self.async_get_input,
            self.async_get_rear_level,
            self.async_get_bass_level,
            self.async_get_voice_enhancer,
            self.async_get_sound_field,
            self.async_get_night_mode,
            self.async_get_hdmi_cec,
            self.async_get_auto_standby,
        ]

        for fetch in fetchers:
            try:
                await fetch()
            except (OSError, ConnectionError):  # pragma: no cover - log and continue
                _LOGGER.warning("Failed to fetch state via %s", fetch.__name__)

        _LOGGER.debug(
            "State fetch complete - Power: %s, Volume: %d, Input: %s, "
            "Rear Level: %d, Bass Level: %d, Voice Enhancer: %s, "
            "Sound Field: %s, Night Mode: %s, HDMI CEC: %s, "
            "Auto Standby: %s",
            self._power_state,
            self._volume,
            self._input,
            self._rear_level,
            self._bass_level,
            self._voice_enhancer,
            self._sound_field,
            self._night_mode,
            self._hdmi_cec,
            self._auto_standby,
        )

    def _get_next_command_id(self) -> int:
        """Return a unique command id."""
        self._command_id_counter += 1
        if self._command_id_counter > CMD_ID_MAX:
            self._command_id_counter = CMD_ID_INITIAL
        return self._command_id_counter

    def _decode_json_stream(self, data: str) -> list[dict[str, Any]]:
        """Decode one or more JSON objects from a buffer string."""
        messages: list[dict[str, Any]] = []
        if not data:
            return messages

        decoder = json.JSONDecoder()
        idx = 0
        length = len(data)

        while idx < length:
            # Skip whitespace between JSON objects
            while idx < length and data[idx].isspace():
                idx += 1

            if idx >= length:
                break

            try:
                message, end = decoder.raw_decode(data, idx)
                messages.append(message)
                idx = end
            except json.JSONDecodeError as err:
                _LOGGER.warning(
                    "Failed to decode JSON chunk: %s (remaining=%s)",
                    err,
                    data[idx:],
                )
                break

        return messages

    async def _process_incoming_message(self, message: dict[str, Any]) -> None:
        """Process a single incoming message from the device."""
        if not message:
            return

        msg_type = message.get("type")
        feature = message.get("feature")
        value = message.get("value")

        _LOGGER.debug(
            "Processing message type=%s feature=%s value=%s",
            msg_type,
            feature,
            value,
        )

        if msg_type == "result":
            self._resolve_pending_response(message)

        self._update_internal_state(feature, value)

        if msg_type == "notify":
            await self._dispatch_notification_callbacks(feature, value)

    def _update_internal_state(self, feature: str | None, value: Any) -> None:
        """Update cached state based on feature and value."""
        if not feature:
            return

        if isinstance(value, str) and value.upper() == "ACK":
            return

        feature_handlers: dict[str, Callable[[Any], None]] = {
            FEATURE_POWER: self._update_power_state,
            FEATURE_VOLUME: self._update_volume_state,
            FEATURE_INPUT: self._update_input_state,
            FEATURE_REAR_LEVEL: self._update_rear_level_state,
            FEATURE_BASS_LEVEL: self._update_bass_level_state,
            FEATURE_VOICE_ENHANCER: self._update_voice_enhancer_state,
            FEATURE_SOUND_FIELD: self._update_sound_field_state,
            FEATURE_NIGHT_MODE: self._update_night_mode_state,
            FEATURE_HDMI_CEC: self._update_hdmi_cec_state,
            FEATURE_AUTO_STANDBY: self._update_auto_standby_state,
        }

        handler = feature_handlers.get(feature)
        if handler:
            try:
                handler(value)
            except (ValueError, TypeError):
                _LOGGER.debug("Invalid value %s for feature %s", value, feature)

    def _update_power_state(self, value: Any) -> None:
        """Update power state from value."""
        self._power_state = str(value)

    def _update_volume_state(self, value: Any) -> None:
        """Update volume state from value."""
        self._volume = int(value)

    def _update_input_state(self, value: Any) -> None:
        """Update input state from value."""
        self._input = str(value)

    def _update_rear_level_state(self, value: Any) -> None:
        """Update rear level state from value."""
        rear_level = int(value)
        if MIN_REAR_LEVEL <= rear_level <= MAX_REAR_LEVEL:
            self._rear_level = rear_level

    def _update_bass_level_state(self, value: Any) -> None:
        """Update bass level state from value."""
        bass_level = int(value)
        if MIN_BASS_LEVEL <= bass_level <= MAX_BASS_LEVEL:
            self._bass_level = bass_level

    def _update_voice_enhancer_state(self, value: Any) -> None:
        """Update voice enhancer state from value."""
        self._voice_enhancer = str(value)

    def _update_sound_field_state(self, value: Any) -> None:
        """Update sound field state from value."""
        self._sound_field = str(value)

    def _update_night_mode_state(self, value: Any) -> None:
        """Update night mode state from value."""
        self._night_mode = str(value)

    def _update_hdmi_cec_state(self, value: Any) -> None:
        """Update HDMI CEC state from value."""
        self._hdmi_cec = str(value)

    def _update_auto_standby_state(self, value: Any) -> None:
        """Update auto standby state from value."""
        self._auto_standby = str(value)

    async def _dispatch_notification_callbacks(
        self, feature: str | None, value: Any
    ) -> None:
        """Invoke registered callbacks for a feature."""
        if not feature:
            return

        callbacks = self._notification_callbacks.get(feature)
        if not callbacks:
            return

        for callback in callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(value)
                else:
                    callback(value)
            except (TypeError, ValueError, AttributeError):
                _LOGGER.exception("Error in notification callback")

    def _resolve_pending_response(self, message: dict[str, Any]) -> None:
        """Resolve the future waiting for a command response."""
        command_id = message.get("id")
        if command_id is None:
            return

        future = self._pending_responses.get(command_id)
        if future and not future.done():
            future.set_result(message)
