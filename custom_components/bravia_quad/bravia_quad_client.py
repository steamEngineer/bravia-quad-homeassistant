"""Client for communicating with Bravia Quad device."""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Callable

from .const import (
    DEFAULT_PORT,
    TCP_TIMEOUT,
    CMD_ID_POWER,
    CMD_ID_VOLUME,
    CMD_ID_INPUT,
    CMD_ID_AUDIO,
    FEATURE_POWER,
    FEATURE_VOLUME,
    FEATURE_INPUT,
    FEATURE_REAR_LEVEL,
    FEATURE_BASS_LEVEL,
    FEATURE_VOICE_ENHANCER,
    FEATURE_SOUND_FIELD,
    FEATURE_NIGHT_MODE,
    POWER_ON,
    POWER_OFF,
    VOICE_ENHANCER_ON,
    VOICE_ENHANCER_OFF,
    SOUND_FIELD_ON,
    SOUND_FIELD_OFF,
    NIGHT_MODE_ON,
    NIGHT_MODE_OFF,
)

_LOGGER = logging.getLogger(__name__)


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
        self._bass_level = 1  # Default to MID
        self._voice_enhancer = VOICE_ENHANCER_OFF
        self._sound_field = SOUND_FIELD_OFF
        self._night_mode = NIGHT_MODE_OFF
        self._command_id_counter = 10  # Start from 10 to avoid conflicts
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
        except Exception as err:
            self._connected = False
            _LOGGER.error("Failed to connect to Bravia Quad: %s", err)
            raise

    async def async_disconnect(self) -> None:
        """Disconnect from the Bravia Quad device."""
        self._listening = False
        if self._listener_task:
            self._listener_task.cancel()
            try:
                await self._listener_task
            except asyncio.CancelledError:
                pass
            self._listener_task = None
        if self._writer:
            self._writer.close()
            try:
                await self._writer.wait_closed()
            except Exception:
                pass
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
            
            if response and response.get("type") == "result":
                if response.get("feature") == FEATURE_POWER:
                    self._power_state = response.get("value", POWER_OFF)
                    return True
            return False
        except Exception as err:
            _LOGGER.error("Test connection failed: %s", err)
            return False

    async def async_send_command(
        self, command: dict[str, Any], timeout: float = TCP_TIMEOUT
    ) -> dict[str, Any] | None:
        """Send a command and wait for response."""
        if not self._connected:
            await self.async_connect()

        if not self._writer or not self._reader:
            raise ConnectionError("Not connected to device")

        if not self._listener_task or self._listener_task.done():
            await self.async_listen_for_notifications()

        response_future: asyncio.Future | None = None

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
            except Exception as err:
                if command_id in self._pending_responses:
                    self._pending_responses.pop(command_id, None)
                _LOGGER.error("Error sending command: %s", err)
                return None

        try:
            response = await asyncio.wait_for(
                response_future, timeout=timeout
            )
            return response
        except asyncio.TimeoutError:
            if response_future and not response_future.done():
                response_future.cancel()
            _LOGGER.error("Timeout waiting for response to command: %s", command)
            return None
        finally:
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
        
        if response and response.get("type") == "result":
            if response.get("value") == "ACK":
                self._power_state = state
                return True
        return False

    async def async_set_volume(self, volume: int) -> bool:
        """Set volume (0-100)."""
        if volume < 0 or volume > 100:
            raise ValueError("Volume must be between 0 and 100")
        
        command = {
            "id": CMD_ID_VOLUME,
            "type": "set",
            "feature": FEATURE_VOLUME,
            "value": volume,
        }
        response = await self.async_send_command(command)
        
        if response and response.get("type") == "result":
            if response.get("value") == "ACK":
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
        
        if response and response.get("type") == "result":
            if response.get("feature") == FEATURE_POWER:
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
        
        if response and response.get("type") == "result":
            if response.get("feature") == FEATURE_VOLUME:
                try:
                    volume = int(response.get("value", 0))
                    if 0 <= volume <= 100:
                        self._volume = volume
                        return self._volume
                except (ValueError, TypeError):
                    pass
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
        
        if response and response.get("type") == "result":
            if response.get("value") == "ACK":
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
        
        if response and response.get("type") == "result":
            if response.get("feature") == FEATURE_INPUT:
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
        
        if response and response.get("type") == "result":
            if response.get("value") == "ACK":
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
        
        if response and response.get("type") == "result":
            if response.get("feature") == FEATURE_VOICE_ENHANCER:
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
        
        if response and response.get("type") == "result":
            if response.get("value") == "ACK":
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
        
        if response and response.get("type") == "result":
            if response.get("feature") == FEATURE_SOUND_FIELD:
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
        
        if response and response.get("type") == "result":
            if response.get("value") == "ACK":
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
        
        if response and response.get("type") == "result":
            if response.get("feature") == FEATURE_NIGHT_MODE:
                self._night_mode = response.get("value", NIGHT_MODE_OFF)
                return self._night_mode
        return self._night_mode

    async def async_set_rear_level(self, level: int) -> bool:
        """Set rear level (0-10)."""
        if level < 0 or level > 10:
            raise ValueError("Rear level must be between 0 and 10")
        
        command = {
            "id": CMD_ID_VOLUME,
            "type": "set",
            "feature": FEATURE_REAR_LEVEL,
            "value": level,
        }
        response = await self.async_send_command(command)
        
        if response and response.get("type") == "result":
            if response.get("value") == "ACK":
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
        
        if response and response.get("type") == "result":
            if response.get("feature") == FEATURE_REAR_LEVEL:
                try:
                    rear_level = int(response.get("value", 0))
                    if 0 <= rear_level <= 10:
                        self._rear_level = rear_level
                        return self._rear_level
                except (ValueError, TypeError):
                    pass
        return self._rear_level

    async def async_set_bass_level(self, level: int) -> bool:
        """Set bass level (0-2)."""
        if level < 0 or level > 2:
            raise ValueError("Bass level must be between 0 and 2")
        
        command = {
            "id": CMD_ID_VOLUME,
            "type": "set",
            "feature": FEATURE_BASS_LEVEL,
            "value": level,
        }
        response = await self.async_send_command(command)
        
        if response and response.get("type") == "result":
            if response.get("value") == "ACK":
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
        
        if response and response.get("type") == "result":
            if response.get("feature") == FEATURE_BASS_LEVEL:
                try:
                    bass_level = int(response.get("value", 1))
                    if 0 <= bass_level <= 2:
                        self._bass_level = bass_level
                        return self._bass_level
                except (ValueError, TypeError):
                    pass
        return self._bass_level

    def register_notification_callback(
        self, feature: str, callback: Callable
    ) -> None:
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

                    data = await asyncio.wait_for(
                        self._reader.read(1024), timeout=1.0
                    )

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
                except asyncio.TimeoutError:
                    continue
                except asyncio.CancelledError:
                    raise
                except Exception as err:
                    _LOGGER.error("Error in notification listener: %s", err)
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
        ]

        for fetch in fetchers:
            try:
                await fetch()
            except Exception as err:  # pragma: no cover - log and continue
                _LOGGER.warning("Failed to fetch state via %s: %s", fetch.__name__, err)

        _LOGGER.debug(
            "State fetch complete - Power: %s, Volume: %d, Input: %s, "
            "Rear Level: %d, Bass Level: %d, Voice Enhancer: %s, "
            "Sound Field: %s, Night Mode: %s",
            self._power_state,
            self._volume,
            self._input,
            self._rear_level,
            self._bass_level,
            self._voice_enhancer,
            self._sound_field,
            self._night_mode,
        )

    def _get_next_command_id(self) -> int:
        """Return a unique command id."""
        self._command_id_counter += 1
        if self._command_id_counter > 1_000_000:
            self._command_id_counter = 10
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

        try:
            if feature == FEATURE_POWER:
                self._power_state = value
            elif feature == FEATURE_VOLUME:
                self._volume = int(value)
            elif feature == FEATURE_INPUT:
                self._input = value
            elif feature == FEATURE_REAR_LEVEL:
                rear_level = int(value)
                if 0 <= rear_level <= 10:
                    self._rear_level = rear_level
            elif feature == FEATURE_BASS_LEVEL:
                bass_level = int(value)
                if 0 <= bass_level <= 2:
                    self._bass_level = bass_level
            elif feature == FEATURE_VOICE_ENHANCER:
                self._voice_enhancer = value
            elif feature == FEATURE_SOUND_FIELD:
                self._sound_field = value
            elif feature == FEATURE_NIGHT_MODE:
                self._night_mode = value
        except (ValueError, TypeError):
            _LOGGER.debug("Invalid value %s for feature %s", value, feature)

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
            except Exception as err:
                _LOGGER.error("Error in notification callback: %s", err)

    def _resolve_pending_response(self, message: dict[str, Any]) -> None:
        """Resolve the future waiting for a command response."""
        command_id = message.get("id")
        if command_id is None:
            return

        future = self._pending_responses.get(command_id)
        if future and not future.done():
            future.set_result(message)

