"""Client for communicating with Bravia Quad device."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from typing import TYPE_CHECKING, Any

from .const import (
    AAV_OFF,
    AUTO_STANDBY_OFF,
    CMD_ID_INITIAL,
    CMD_ID_MAX,
    DEFAULT_PORT,
    FEATURE_AAV,
    FEATURE_AUTO_STANDBY,
    FEATURE_BASS_LEVEL,
    FEATURE_DEVICE_NAME,
    FEATURE_DRC,
    FEATURE_FIRMWARE_VERSION,
    FEATURE_HDMI_CEC,
    FEATURE_INPUT,
    FEATURE_MAC_ADDRESS,
    FEATURE_MANUFACTURER,
    FEATURE_MODEL_TYPE,
    FEATURE_MUTE,
    FEATURE_NIGHT_MODE,
    FEATURE_POWER,
    FEATURE_REAR_LEVEL,
    FEATURE_SERIAL_NUMBER,
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
    MUTE_OFF,
    NIGHT_MODE_OFF,
    POWER_OFF,
    POWER_ON,
    RECONNECT_INITIAL_DELAY,
    RECONNECT_MAX_DELAY,
    SOUND_FIELD_OFF,
    TCP_TIMEOUT,
    VOICE_ENHANCER_OFF,
)

if TYPE_CHECKING:
    from collections.abc import Callable

_LOGGER = logging.getLogger(__name__)

# Default values
DEFAULT_BASS_LEVEL = 1  # MID
DEFAULT_DRC = "auto"


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
        self._drc = DEFAULT_DRC
        self._aav = AAV_OFF
        self._mute = MUTE_OFF
        self._volume_step_interval = 0
        self._command_id_counter = CMD_ID_INITIAL
        self._command_lock = asyncio.Lock()
        self._pending_responses: dict[int, asyncio.Future] = {}
        self._listener_task: asyncio.Task | None = None
        self._background_tasks: set[asyncio.Task] = set()
        self._availability_callbacks: set[Callable[[bool], None]] = set()
        self._serial_number: str | None = None
        self._firmware_version: str | None = None
        self._model_type: str | None = None
        self._manufacturer: str | None = None

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
            _LOGGER.debug("Connected to Bravia Quad at %s:%s", self.host, self.port)
        except OSError as err:
            self._connected = False
            _LOGGER.debug("Failed to connect to Bravia Quad at %s: %s", self.host, err)
            raise ConnectionError(str(err)) from err

    async def async_disconnect(self) -> None:
        """Disconnect from the Bravia Quad device."""
        self._listening = False
        if self._listener_task:
            self._listener_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._listener_task
            self._listener_task = None
        await self._async_close_connection()

        # Cancel any background tasks
        for task in self._background_tasks:
            task.cancel()
        if self._background_tasks:
            await asyncio.gather(*self._background_tasks, return_exceptions=True)
        self._background_tasks.clear()

        _LOGGER.info("Disconnected from Bravia Quad")

    async def _async_close_connection(self) -> None:
        """Close the socket connection and fail pending commands."""
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

    async def _async_mark_disconnected(self) -> None:
        """Mark connection as lost, clean up, and notify entities."""
        was_connected = self._connected
        await self._async_close_connection()
        if was_connected:
            _LOGGER.warning("Connection to Bravia Quad lost")
            self._notify_availability(available=False)

    async def async_test_connection(self) -> bool:
        """Test connection by sending a power status request."""
        if not self._connected:
            await self.async_connect()

        try:
            value = await self._async_get_feature(FEATURE_POWER)
            if value is not None:
                self._power_state = value
                return True
        except (OSError, ConnectionError):
            _LOGGER.exception("Test connection failed")
        return False

    async def async_send_command(
        self, command: dict[str, Any]
    ) -> dict[str, Any] | None:
        """Send a command and wait for response."""
        if not self._connected or not self._writer or not self._reader:
            msg = "Not connected to device"
            raise ConnectionError(msg)

        if not self._listener_task or self._listener_task.done():
            await self.async_listen_for_notifications()

        command_id: int | None = None

        async with self._command_lock:
            try:
                # Assign a unique command id
                command = dict(command)
                command_id = self._get_next_command_id()
                command["id"] = command_id

                loop = asyncio.get_running_loop()
                response_future: asyncio.Future[dict[str, Any]] = loop.create_future()
                self._pending_responses[command_id] = response_future

                command_json = json.dumps(command) + "\n"
                _LOGGER.debug("Sending command: %s", command_json.strip())
                self._writer.write(command_json.encode())
                await self._writer.drain()
            except OSError as err:
                if command_id is not None:
                    self._pending_responses.pop(command_id, None)
                _LOGGER.exception("Error sending command")
                raise ConnectionError(str(err)) from err

            # Wait for response while holding the lock so the next command
            # is not sent until this one completes
            try:
                response = await asyncio.wait_for(response_future, timeout=TCP_TIMEOUT)
            except TimeoutError:
                _LOGGER.warning("Timeout waiting for response to command: %s", command)
                return None
            else:
                return response
            finally:
                if command_id is not None:
                    self._pending_responses.pop(command_id, None)

    async def _async_set_feature(self, feature: str, value: str) -> bool:
        """Set a feature value. Returns True on ACK."""
        command = {"id": 0, "type": "set", "feature": feature, "value": value}
        response = await self.async_send_command(command)
        return bool(response and response.get("value") == "ACK")

    async def _async_get_feature(self, feature: str) -> str | None:
        """Get a feature value fresh from the device."""
        command = {"id": 0, "type": "get", "feature": feature}
        response = await self.async_send_command(command)
        if response and response.get("type") == "result":
            value = response.get("value")
            if value and value not in ("NAK", "ERR"):
                return str(value)
        return None

    async def async_set_power(self, state: str) -> bool:
        """Set power state (on/off)."""
        if await self._async_set_feature(FEATURE_POWER, state):
            self._power_state = state
            return True
        return False

    async def async_set_volume(self, volume: int) -> bool:
        """Set volume (0-100)."""
        if volume < MIN_VOLUME or volume > MAX_VOLUME:
            msg = f"Volume must be between {MIN_VOLUME} and {MAX_VOLUME}"
            raise ValueError(msg)

        if await self._async_set_feature(FEATURE_VOLUME, str(volume)):
            self._volume = volume
            return True
        return False

    async def async_get_power(self) -> str:
        """Get current power state."""
        value = await self._async_get_feature(FEATURE_POWER)
        if value is not None:
            self._power_state = value
        return self._power_state

    async def async_get_volume(self) -> int:
        """Get current volume."""
        value = await self._async_get_feature(FEATURE_VOLUME)
        if value is not None:
            try:
                volume = int(value)
                if MIN_VOLUME <= volume <= MAX_VOLUME:
                    self._volume = volume
            except (ValueError, TypeError):
                pass
        return self._volume

    async def async_set_input(self, input_value: str) -> bool:
        """Set input source."""
        if await self._async_set_feature(FEATURE_INPUT, input_value):
            self._input = input_value
            return True
        return False

    async def async_get_input(self) -> str:
        """Get current input source."""
        value = await self._async_get_feature(FEATURE_INPUT)
        if value is not None:
            self._input = value
        return self._input

    async def async_set_voice_enhancer(self, state: str) -> bool:
        """Set voice enhancer state."""
        if await self._async_set_feature(FEATURE_VOICE_ENHANCER, state):
            self._voice_enhancer = state
            return True
        return False

    async def async_get_voice_enhancer(self) -> str:
        """Get current voice enhancer state."""
        value = await self._async_get_feature(FEATURE_VOICE_ENHANCER)
        if value is not None:
            self._voice_enhancer = value
        return self._voice_enhancer

    async def async_set_sound_field(self, state: str) -> bool:
        """Set sound field state."""
        if await self._async_set_feature(FEATURE_SOUND_FIELD, state):
            self._sound_field = state
            return True
        return False

    async def async_get_sound_field(self) -> str:
        """Get current sound field state."""
        value = await self._async_get_feature(FEATURE_SOUND_FIELD)
        if value is not None:
            self._sound_field = value
        return self._sound_field

    async def async_set_night_mode(self, state: str) -> bool:
        """Set night mode state."""
        if await self._async_set_feature(FEATURE_NIGHT_MODE, state):
            self._night_mode = state
            return True
        return False

    async def async_get_night_mode(self) -> str:
        """Get current night mode state."""
        value = await self._async_get_feature(FEATURE_NIGHT_MODE)
        if value is not None:
            self._night_mode = value
        return self._night_mode

    async def async_set_hdmi_cec(self, state: str) -> bool:
        """Set HDMI CEC state."""
        if await self._async_set_feature(FEATURE_HDMI_CEC, state):
            self._hdmi_cec = state
            return True
        return False

    async def async_get_hdmi_cec(self) -> str:
        """Get current HDMI CEC state."""
        value = await self._async_get_feature(FEATURE_HDMI_CEC)
        if value is not None:
            self._hdmi_cec = value
        return self._hdmi_cec

    async def async_set_auto_standby(self, state: str) -> bool:
        """Set auto standby state."""
        if await self._async_set_feature(FEATURE_AUTO_STANDBY, state):
            self._auto_standby = state
            return True
        return False

    async def async_get_auto_standby(self) -> str:
        """Get current auto standby state."""
        value = await self._async_get_feature(FEATURE_AUTO_STANDBY)
        if value is not None:
            self._auto_standby = value
        return self._auto_standby

    async def async_set_drc(self, state: str) -> bool:
        """Set DRC state."""
        if await self._async_set_feature(FEATURE_DRC, state):
            self._drc = state
            return True
        return False

    async def async_get_drc(self) -> str:
        """Get current DRC state."""
        value = await self._async_get_feature(FEATURE_DRC)
        if value is not None:
            self._drc = value
        return self._drc

    async def async_set_aav(self, state: str) -> bool:
        """Set AAV state."""
        if await self._async_set_feature(FEATURE_AAV, state):
            self._aav = state
            return True
        return False

    async def async_get_aav(self) -> str:
        """Get current AAV state."""
        value = await self._async_get_feature(FEATURE_AAV)
        if value is not None:
            self._aav = value
        return self._aav

    async def async_set_mute(self, state: str) -> bool:
        """Set mute state."""
        if await self._async_set_feature(FEATURE_MUTE, state):
            self._mute = state
            return True
        return False

    async def async_get_mute(self) -> str:
        """Get current mute state."""
        value = await self._async_get_feature(FEATURE_MUTE)
        if value is not None:
            self._mute = value
        return self._mute

    async def async_get_serial_number(self) -> str | None:
        """Get the device serial number."""
        value = await self._async_get_feature(FEATURE_SERIAL_NUMBER)
        if value is not None:
            self._serial_number = value
        return self._serial_number

    async def async_get_mac_address(self) -> str | None:
        """Get the device MAC address."""
        return await self._async_get_feature(FEATURE_MAC_ADDRESS)

    async def async_get_firmware_version(self) -> str | None:
        """Get the device firmware version."""
        value = await self._async_get_feature(FEATURE_FIRMWARE_VERSION)
        if value is not None:
            self._firmware_version = value
        return self._firmware_version

    async def async_get_model_type(self) -> str | None:
        """Get the device model type (e.g., HT-A9M2)."""
        value = await self._async_get_feature(FEATURE_MODEL_TYPE)
        if value is not None:
            self._model_type = value
        return self._model_type

    async def async_get_manufacturer(self) -> str | None:
        """Get the device manufacturer."""
        value = await self._async_get_feature(FEATURE_MANUFACTURER)
        if value is not None:
            self._manufacturer = value
        return self._manufacturer

    async def async_get_device_name(self) -> str | None:
        """Get the user-set device name."""
        return await self._async_get_feature(FEATURE_DEVICE_NAME)

    async def async_set_rear_level(self, level: int) -> bool:
        """Set rear level (-10 to 10)."""
        if level < MIN_REAR_LEVEL or level > MAX_REAR_LEVEL:
            msg = f"Rear level must be between {MIN_REAR_LEVEL} and {MAX_REAR_LEVEL}"
            raise ValueError(msg)

        if await self._async_set_feature(FEATURE_REAR_LEVEL, str(level)):
            self._rear_level = level
            return True
        return False

    async def async_get_rear_level(self) -> int:
        """Get current rear level."""
        value = await self._async_get_feature(FEATURE_REAR_LEVEL)
        if value is not None:
            try:
                rear_level = int(value)
                if MIN_REAR_LEVEL <= rear_level <= MAX_REAR_LEVEL:
                    self._rear_level = rear_level
            except (ValueError, TypeError):
                pass
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

        if await self._async_set_feature(FEATURE_BASS_LEVEL, str(level)):
            self._bass_level = level
            return True
        return False

    async def async_get_bass_level(self) -> int:
        """Get current bass level."""
        value = await self._async_get_feature(FEATURE_BASS_LEVEL)
        if value is not None:
            try:
                bass_level = int(value)
                if MIN_BASS_LEVEL <= bass_level <= MAX_BASS_LEVEL:
                    self._bass_level = bass_level
            except (ValueError, TypeError):
                pass
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
        if await self._async_set_feature(FEATURE_BASS_LEVEL, str(test_value)):
            # Successfully set to -1, subwoofer is connected
            self._bass_level = test_value
            _LOGGER.info(
                "Subwoofer detected: device accepted bass level %d", test_value
            )
            # Revert to original value. Note: there's a brief window where
            # user bass level changes could be overwritten, but this is
            # acceptable given detection is rare and the window is very short.
            await self._async_set_feature(FEATURE_BASS_LEVEL, str(current_level))
            self._bass_level = current_level
            return True

        # Device rejected -1, no subwoofer connected
        _LOGGER.info("No subwoofer detected: device rejected bass level %d", test_value)
        return False

    def register_availability_callback(self, callback: Callable[[bool], None]) -> None:
        """Register a callback for connection state changes."""
        self._availability_callbacks.add(callback)

    def unregister_availability_callback(
        self, callback: Callable[[bool], None]
    ) -> None:
        """Unregister a connection state change callback."""
        self._availability_callbacks.discard(callback)

    def _notify_availability(self, *, available: bool) -> None:
        """Notify all registered availability callbacks."""
        for callback in tuple(self._availability_callbacks):
            try:
                callback(available)
            except Exception:
                _LOGGER.exception("Error in availability callback")

    def register_notification_callback(self, feature: str, callback: Callable) -> None:
        """Register a callback for notifications."""
        if feature not in self._notification_callbacks:
            self._notification_callbacks[feature] = []
        self._notification_callbacks[feature].append(callback)

    def unregister_notification_callback(
        self, feature: str, callback: Callable
    ) -> None:
        """Unregister a callback for notifications."""
        if feature in self._notification_callbacks:
            with contextlib.suppress(ValueError):
                self._notification_callbacks[feature].remove(callback)

    async def async_listen_for_notifications(self) -> None:
        """Start the connection manager that keeps the listener alive."""
        if self._listener_task and not self._listener_task.done():
            return

        if not self._connected:
            await self.async_connect()

        self._listener_task = asyncio.create_task(self._connection_manager())

    async def _connection_manager(self) -> None:
        """Manage the notification loop lifecycle with auto-reconnect.

        Starts the read loop, waits for it to exit (on disconnect),
        reconnects, then starts a fresh loop. State fetch and
        availability notification happen after the new loop is
        already reading, so command responses are processed.
        """
        try:
            while True:
                await self._notification_loop()

                delay = RECONNECT_INITIAL_DELAY
                while True:
                    _LOGGER.debug("Reconnecting in %ds", delay)
                    await asyncio.sleep(delay)

                    try:
                        await self.async_connect()
                    except (OSError, ConnectionError):
                        delay = min(delay * 2, RECONNECT_MAX_DELAY)
                        continue

                    _LOGGER.info("Reconnected to device")
                    break

                self._notify_availability(available=True)
                task = asyncio.create_task(self.async_fetch_all_states())
                self._background_tasks.add(task)
                task.add_done_callback(self._background_tasks.discard)
        except asyncio.CancelledError:
            _LOGGER.info("Connection manager cancelled")
            raise

    async def _notification_loop(self) -> None:
        """Read and dispatch messages from the device.

        Exits on any connection error so the connection manager
        can reconnect.
        """
        _LOGGER.info("Starting notification listener")
        buffer = ""

        try:
            while self._connected and self._reader:
                try:
                    data = await asyncio.wait_for(self._reader.read(8192), timeout=1.0)

                    if not data:
                        _LOGGER.warning("Connection closed by device (EOF)")
                        break

                    buffer += data.decode("utf-8", errors="replace")
                    buffer = buffer.strip()
                    if buffer:
                        messages, buffer = self._decode_json_stream(buffer)
                        for message in messages:
                            await self._process_incoming_message(message)
                except TimeoutError:
                    continue
                except OSError:
                    _LOGGER.warning("Connection error in notification listener")
                    break
        except asyncio.CancelledError:
            raise

        await self._async_mark_disconnected()

    async def _reconnect_loop(self) -> None:
        """Attempt to reconnect with exponential backoff."""
        delay = RECONNECT_INITIAL_DELAY

        while True:
            _LOGGER.debug("Reconnecting in %ds", delay)
            await asyncio.sleep(delay)

            try:
                await self.async_connect()
            except (OSError, ConnectionError):
                delay = min(delay * 2, RECONNECT_MAX_DELAY)
                continue

            _LOGGER.info("Reconnected to device")
            self._notify_availability(available=True)
            task = asyncio.create_task(self.async_fetch_all_states())
            self._background_tasks.add(task)
            task.add_done_callback(self._background_tasks.discard)
            return

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

    @property
    def drc(self) -> str:
        """Return current Dynamic Range Compressor state."""
        return self._drc

    @property
    def aav(self) -> str:
        """Return current Advanced Auto Volume state."""
        return self._aav

    @property
    def mute(self) -> str:
        """Return current mute state."""
        return self._mute

    @property
    def serial_number(self) -> str | None:
        """Return the device serial number."""
        return self._serial_number

    @property
    def firmware_version(self) -> str | None:
        """Return the device firmware version."""
        return self._firmware_version

    @property
    def model_type(self) -> str | None:
        """Return the device model type."""
        return self._model_type

    @property
    def manufacturer(self) -> str | None:
        """Return the device manufacturer."""
        return self._manufacturer

    @property
    def volume_step_interval(self) -> int:
        """Return the volume step interval in ms."""
        return self._volume_step_interval

    @volume_step_interval.setter
    def volume_step_interval(self, value: int) -> None:
        """Set the volume step interval in ms."""
        self._volume_step_interval = value

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
            self.async_get_drc,
            self.async_get_aav,
            self.async_get_mute,
            self.async_get_serial_number,
            self.async_get_firmware_version,
            self.async_get_model_type,
            self.async_get_manufacturer,
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
            "Auto Standby: %s, DRC: %s, AAV: %s, Mute: %s, "
            "Serial: %s, FW: %s, Model Type: %s, Manufacturer: %s",
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
            self._drc,
            self._aav,
            self._mute,
            self._serial_number,
            self._firmware_version,
            self._model_type,
            self._manufacturer,
        )

    def _get_next_command_id(self) -> int:
        """Return a unique command id."""
        self._command_id_counter += 1
        if self._command_id_counter > CMD_ID_MAX:
            self._command_id_counter = CMD_ID_INITIAL
        return self._command_id_counter

    def _decode_json_stream(self, data: str) -> tuple[list[dict[str, Any]], str]:
        """Decode JSON objects from a buffer, returning unparsed remainder.

        The device sends concatenated JSON objects with no delimiter.
        A single TCP read may split an object mid-byte. This method
        parses all complete objects and returns any trailing fragment
        so the caller can prepend it to the next read.
        """
        messages: list[dict[str, Any]] = []
        if not data:
            return messages, ""

        decoder = json.JSONDecoder()
        idx = 0
        length = len(data)

        while idx < length:
            while idx < length and data[idx].isspace():
                idx += 1

            if idx >= length:
                break

            try:
                message, end = decoder.raw_decode(data, idx)
                messages.append(message)
                idx = end
            except json.JSONDecodeError:
                return messages, data[idx:]

        return messages, ""

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

        # Dispatch callbacks for notifications and non-ACK results
        if msg_type == "notify" or (
            msg_type == "result"
            and value is not None
            and not (isinstance(value, str) and value.upper() == "ACK")
        ):
            await self._dispatch_notification_callbacks(feature, value)

        # Workaround for Bravia Quad failing to send input change notification on wake
        if msg_type == "notify" and feature == FEATURE_POWER and value == POWER_ON:
            _LOGGER.debug("Power on notification received, refreshing input state")
            task = asyncio.create_task(self.async_get_input())
            self._background_tasks.add(task)
            task.add_done_callback(self._background_tasks.discard)

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
            FEATURE_DRC: self._update_drc_state,
            FEATURE_AAV: self._update_aav_state,
            FEATURE_MUTE: self._update_mute_state,
            FEATURE_SERIAL_NUMBER: self._update_serial_number_state,
            FEATURE_FIRMWARE_VERSION: self._update_firmware_version_state,
            FEATURE_MODEL_TYPE: self._update_model_type_state,
            FEATURE_MANUFACTURER: self._update_manufacturer_state,
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

    def _update_drc_state(self, value: Any) -> None:
        """Update Dynamic Range Compressor state from value."""
        self._drc = str(value)

    def _update_aav_state(self, value: Any) -> None:
        """Update Advanced Auto Volume state from value."""
        self._aav = str(value)

    def _update_mute_state(self, value: Any) -> None:
        """Update mute state from value."""
        self._mute = str(value)

    def _update_serial_number_state(self, value: Any) -> None:
        """Update serial number from value."""
        self._serial_number = str(value)

    def _update_firmware_version_state(self, value: Any) -> None:
        """Update firmware version from value."""
        self._firmware_version = str(value)

    def _update_model_type_state(self, value: Any) -> None:
        """Update model type from value."""
        self._model_type = str(value)

    def _update_manufacturer_state(self, value: Any) -> None:
        """Update manufacturer from value."""
        self._manufacturer = str(value)

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
