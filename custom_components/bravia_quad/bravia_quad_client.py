"""HA TCP adapter over sony-cisip2 (sticky cache and quirks stay in Theatre)."""

from __future__ import annotations

import asyncio
import contextlib
import inspect
import logging
from collections.abc import Awaitable, Callable, Coroutine
from typing import Any

from sony_cisip2 import SonyCISIP2

from .const import (
    AAV_OFF,
    AUTO_STANDBY_OFF,
    AUTO_UPDATE_OFF,
    DEFAULT_PORT,
    FEATURE_360SSM,
    FEATURE_AAV,
    FEATURE_AUDIO_RETURN_CHANNEL,
    FEATURE_AUTO_STANDBY,
    FEATURE_AUTO_UPDATE,
    FEATURE_AV_SYNC,
    FEATURE_BASS_LEVEL,
    FEATURE_BT_CONNECTION_QUALITY,
    FEATURE_DESTINATION,
    FEATURE_DEVICE_NAME,
    FEATURE_DHCP,
    FEATURE_DRC,
    FEATURE_DUAL_MONO,
    FEATURE_EXTERNAL_CONTROL,
    FEATURE_FIRMWARE_VERSION,
    FEATURE_HDMI_CEC,
    FEATURE_HDMI_PASSTHROUGH,
    FEATURE_HDMI_STANDBY_LINK,
    FEATURE_IMAX_MODE,
    FEATURE_INPUT,
    FEATURE_IP_ADDRESS,
    FEATURE_LANGUAGE,
    FEATURE_MAC_ADDRESS,
    FEATURE_MANUFACTURER,
    FEATURE_MODEL_TYPE,
    FEATURE_MUTE,
    FEATURE_NET_BT_STANDBY,
    FEATURE_NETWORK_MODE,
    FEATURE_NIGHT_MODE,
    FEATURE_POWER,
    FEATURE_REAR_LEVEL,
    FEATURE_SERIAL_NUMBER,
    FEATURE_SOUND_FIELD,
    FEATURE_TEMPERATURE,
    FEATURE_TIMEZONE,
    FEATURE_TV_AV_SYNC,
    FEATURE_VOICE_ENHANCER,
    FEATURE_VOICE_ZOOM,
    FEATURE_VOICE_ZOOM_LEVEL,
    FEATURE_VOLUME,
    HDMI_CEC_OFF,
    IMAX_MODE_AUTO,
    MAX_AV_SYNC,
    MAX_BASS_LEVEL,
    MAX_BASS_LEVEL_NO_SUB,
    MAX_REAR_LEVEL,
    MAX_VOLUME,
    MIN_AV_SYNC,
    MIN_BASS_LEVEL,
    MIN_BASS_LEVEL_NO_SUB,
    MIN_REAR_LEVEL,
    MIN_VOLUME,
    MUTE_OFF,
    NIGHT_MODE_OFF,
    POWER_OFF,
    POWER_ON,
    SOUND_FIELD_OFF,
    TCP_TIMEOUT,
    VOICE_ENHANCER_OFF,
    VOICE_ZOOM_OFF,
)

_LOGGER = logging.getLogger(__name__)

DEFAULT_BASS_LEVEL = 1  # MID
DEFAULT_DRC = "auto"

HaNotifyCallback = Callable[[Any], Awaitable[None] | None]
HaAvailabilityCallback = Callable[[bool], None]


class _HaSonyCISIP2(SonyCISIP2):
    """
    SonyCISIP2 with an HA connection-lost hook.

    ponytail: library has on_reconnect but no on_connection_lost; override
    _mark_disconnected until upstream adds a first-class hook.
    """

    def __init__(
        self,
        host: str,
        port: int = DEFAULT_PORT,
        timeout: float = TCP_TIMEOUT,
        on_reconnect: Callable[[], Coroutine[Any, Any, None]] | None = None,
        on_connection_lost: Callable[[], None] | None = None,
    ) -> None:
        """Initialize with optional HA connection-lost callback."""
        super().__init__(host, port=port, timeout=timeout, on_reconnect=on_reconnect)
        self._on_connection_lost = on_connection_lost

    async def _mark_disconnected(self) -> None:
        """Mark connection lost, then notify HA availability."""
        was_connected = self._connected
        await super()._mark_disconnected()
        if was_connected and self._on_connection_lost is not None:
            self._on_connection_lost()


class BraviaQuadClient:
    """HA façade over SonyCISIP2: sticky cache, availability, typed helpers."""

    def __init__(self, host: str, name: str) -> None:
        """Initialize the Bravia Quad client adapter."""
        self.host = host
        self.port = DEFAULT_PORT
        self.name = name
        self._connected = False
        self._notify_wrap_registered = False
        self._notification_callbacks: dict[str, list[HaNotifyCallback]] = {}
        self._availability_callbacks: set[HaAvailabilityCallback] = set()
        self._background_tasks: set[asyncio.Task[Any]] = set()

        self._power_state = POWER_OFF
        self._volume = 0
        self._input = "tv"
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
        self._serial_number: str | None = None
        self._firmware_version: str | None = None
        self._model_type: str | None = None
        self._manufacturer: str | None = None
        self._auto_update = AUTO_UPDATE_OFF
        self._imax_mode = IMAX_MODE_AUTO
        self._voice_zoom = VOICE_ZOOM_OFF

        self._lib = _HaSonyCISIP2(
            host,
            port=DEFAULT_PORT,
            timeout=float(TCP_TIMEOUT),
            on_reconnect=self._async_on_lib_reconnect,
            on_connection_lost=self._on_lib_connection_lost,
        )

    def _on_lib_connection_lost(self) -> None:
        """Handle library drop: sync flag + entity unavailable."""
        if not self._connected:
            return
        self._connected = False
        _LOGGER.warning("Connection to Bravia Quad lost")
        self._notify_availability(available=False)

    async def _async_on_lib_reconnect(self) -> None:
        """Handle library reconnect: available + fire-and-forget state fetch."""
        self._connected = True
        self._notify_availability(available=True)
        task = asyncio.create_task(self.async_fetch_all_states())
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)

    def _ensure_notify_wrap(self) -> None:
        """Register the sticky/notify bridge on the library once."""
        if self._notify_wrap_registered:
            return
        self._lib.register_notification_callback(None, self._on_lib_notify)
        self._notify_wrap_registered = True

    async def _on_lib_notify(self, feature: str | None, value: Any) -> None:
        """Update sticky cache and fan out to HA entity callbacks."""
        self._update_internal_state(feature, value)
        await self._dispatch_notification_callbacks(feature, value)
        # Device quirk: power-on notify often omits a matching input notify.
        if feature == FEATURE_POWER and value == POWER_ON:
            _LOGGER.debug("Power on notification received, refreshing input state")
            task = asyncio.create_task(self.async_get_input())
            self._background_tasks.add(task)
            task.add_done_callback(self._background_tasks.discard)

    async def async_connect(self) -> None:
        """Connect to the Bravia Quad device."""
        if self._connected:
            return

        try:
            await self._lib.connect()
        except (OSError, ConnectionError, TimeoutError) as err:
            self._connected = False
            _LOGGER.debug("Failed to connect to Bravia Quad at %s: %s", self.host, err)
            raise ConnectionError(str(err)) from err

        self._connected = True
        self._ensure_notify_wrap()
        _LOGGER.debug("Connected to Bravia Quad at %s:%s", self.host, self.port)

    async def async_disconnect(self) -> None:
        """Disconnect from the Bravia Quad device."""
        for task in self._background_tasks:
            task.cancel()
        if self._background_tasks:
            await asyncio.gather(*self._background_tasks, return_exceptions=True)
        self._background_tasks.clear()

        await self._lib.disconnect()
        self._connected = False
        _LOGGER.info("Disconnected from Bravia Quad")

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
        """Send a get/set command via the library (BT pairing button façade)."""
        if not self._connected:
            msg = "Not connected to device"
            raise ConnectionError(msg)

        msg_type = command.get("type")
        feature = command.get("feature")
        if not isinstance(feature, str) or not feature:
            return None

        if msg_type == "set":
            result = await self._lib.set_feature(feature, command.get("value"))
            if result is None:
                return None
            return {"type": "result", "feature": feature, "value": result}

        if msg_type == "get":
            value = await self._lib.get_feature(feature)
            if value is None:
                return None
            return {"type": "result", "feature": feature, "value": value}

        return None

    async def _async_set_feature(self, feature: str, value: str) -> bool:
        """Set a feature value. Returns True on ACK."""
        result = await self._lib.set_feature(feature, value)
        return result == "ACK"

    async def _async_get_feature(self, feature: str) -> str | None:
        """Get a feature value fresh from the device."""
        value = await self._lib.get_feature(feature)
        if value is None:
            return None
        return str(value)

    async def async_get_tcp_feature(self, feature: str) -> str | None:
        """Get a TCP control-plane feature (used by gRPC hybrid seeding)."""
        return await self._async_get_feature(feature)

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

    async def async_set_hdmi_passthrough(self, value: str) -> bool:
        """Set the HDMI passthrough mode."""
        return await self._async_set_feature(FEATURE_HDMI_PASSTHROUGH, value)

    async def async_get_hdmi_passthrough(self) -> str | None:
        """Get the HDMI passthrough mode."""
        return await self._async_get_feature(FEATURE_HDMI_PASSTHROUGH)

    async def async_set_dual_mono(self, value: str) -> bool:
        """Set the dual mono mode."""
        return await self._async_set_feature(FEATURE_DUAL_MONO, value)

    async def async_get_dual_mono(self) -> str | None:
        """Get the dual mono mode."""
        return await self._async_get_feature(FEATURE_DUAL_MONO)

    async def async_set_auto_update(self, value: str) -> bool:
        """Set the auto update state."""
        if await self._async_set_feature(FEATURE_AUTO_UPDATE, value):
            self._auto_update = value
            return True
        return False

    async def async_get_auto_update(self) -> str:
        """Get the auto update state."""
        value = await self._async_get_feature(FEATURE_AUTO_UPDATE)
        if value is not None:
            self._auto_update = value
        return self._auto_update

    async def async_set_imax_mode(self, value: str) -> bool:
        """Set the IMAX mode."""
        if await self._async_set_feature(FEATURE_IMAX_MODE, value):
            self._imax_mode = value
            return True
        return False

    async def async_get_imax_mode(self) -> str:
        """Get the IMAX mode."""
        value = await self._async_get_feature(FEATURE_IMAX_MODE)
        if value is not None:
            self._imax_mode = value
        return self._imax_mode

    async def async_set_av_sync(self, value: int) -> bool:
        """Set AV sync delay in milliseconds."""
        value = max(MIN_AV_SYNC, min(MAX_AV_SYNC, value))
        return await self._async_set_feature(FEATURE_AV_SYNC, str(value))

    async def async_get_av_sync(self) -> int | None:
        """Get AV sync delay."""
        raw = await self._async_get_feature(FEATURE_AV_SYNC)
        if raw is not None:
            try:
                return int(raw)
            except (ValueError, TypeError):
                pass
        return None

    async def async_set_tv_av_sync(self, value: int) -> bool:
        """Set TV AV sync delay in milliseconds."""
        value = max(MIN_AV_SYNC, min(MAX_AV_SYNC, value))
        return await self._async_set_feature(FEATURE_TV_AV_SYNC, str(value))

    async def async_get_tv_av_sync(self) -> int | None:
        """Get TV AV sync delay."""
        raw = await self._async_get_feature(FEATURE_TV_AV_SYNC)
        if raw is not None:
            try:
                return int(raw)
            except (ValueError, TypeError):
                pass
        return None

    async def async_set_bt_connection_quality(self, value: str) -> bool:
        """Set the Bluetooth connection quality."""
        return await self._async_set_feature(FEATURE_BT_CONNECTION_QUALITY, value)

    async def async_get_bt_connection_quality(self) -> str | None:
        """Get the Bluetooth connection quality."""
        return await self._async_get_feature(FEATURE_BT_CONNECTION_QUALITY)

    async def async_set_external_control(self, value: str) -> bool:
        """Set the external control state."""
        return await self._async_set_feature(FEATURE_EXTERNAL_CONTROL, value)

    async def async_get_external_control(self) -> str | None:
        """Get the external control state."""
        return await self._async_get_feature(FEATURE_EXTERNAL_CONTROL)

    async def async_set_hdmi_standby_link(self, value: str) -> bool:
        """Set the HDMI standby link mode."""
        return await self._async_set_feature(FEATURE_HDMI_STANDBY_LINK, value)

    async def async_get_hdmi_standby_link(self) -> str | None:
        """Get the HDMI standby link mode."""
        return await self._async_get_feature(FEATURE_HDMI_STANDBY_LINK)

    async def async_set_net_bt_standby(self, value: str) -> bool:
        """Set the network/BT standby state."""
        return await self._async_set_feature(FEATURE_NET_BT_STANDBY, value)

    async def async_get_net_bt_standby(self) -> str | None:
        """Get the network/BT standby state."""
        return await self._async_get_feature(FEATURE_NET_BT_STANDBY)

    async def async_set_voice_zoom(self, value: str) -> bool:
        """Set the voice zoom state."""
        if await self._async_set_feature(FEATURE_VOICE_ZOOM, value):
            self._voice_zoom = value
            return True
        return False

    async def async_get_voice_zoom(self) -> str:
        """Get the voice zoom state."""
        value = await self._async_get_feature(FEATURE_VOICE_ZOOM)
        if value is not None:
            self._voice_zoom = value
        return self._voice_zoom

    async def async_set_audio_return_channel(self, value: str) -> bool:
        """Set the audio return channel mode."""
        return await self._async_set_feature(FEATURE_AUDIO_RETURN_CHANNEL, value)

    async def async_get_audio_return_channel(self) -> str | None:
        """Get the audio return channel mode."""
        return await self._async_get_feature(FEATURE_AUDIO_RETURN_CHANNEL)

    async def async_get_voice_zoom_level(self) -> int | None:
        """Get the voice zoom level."""
        raw = await self._async_get_feature(FEATURE_VOICE_ZOOM_LEVEL)
        if raw is not None:
            try:
                return int(raw)
            except (ValueError, TypeError):
                pass
        return None

    async def async_get_timezone(self) -> str | None:
        """Get the device timezone."""
        return await self._async_get_feature(FEATURE_TIMEZONE)

    async def async_get_temperature(self) -> str | None:
        """Get the device temperature."""
        return await self._async_get_feature(FEATURE_TEMPERATURE)

    async def async_get_360ssm(self) -> str | None:
        """Get the 360SSM status."""
        return await self._async_get_feature(FEATURE_360SSM)

    async def async_get_network_mode(self) -> str | None:
        """Get the network mode."""
        return await self._async_get_feature(FEATURE_NETWORK_MODE)

    async def async_get_ip_address(self) -> str | None:
        """Get the device IP address."""
        return await self._async_get_feature(FEATURE_IP_ADDRESS)

    async def async_get_destination(self) -> str | None:
        """Get the device destination."""
        return await self._async_get_feature(FEATURE_DESTINATION)

    async def async_get_language(self) -> str | None:
        """Get the device language."""
        return await self._async_get_feature(FEATURE_LANGUAGE)

    async def async_get_dhcp(self) -> str | None:
        """Get the DHCP status."""
        return await self._async_get_feature(FEATURE_DHCP)

    async def async_detect_subwoofer(self) -> bool:
        """
        Detect if subwoofer is connected by testing bass level range.

        Returns True if subwoofer is detected (supports -10 to 10 range).
        Returns False if no subwoofer (only supports 0-2 select mode).
        """
        current_level = await self.async_get_bass_level()

        if (
            current_level < MIN_BASS_LEVEL_NO_SUB
            or current_level > MAX_BASS_LEVEL_NO_SUB
        ):
            _LOGGER.info(
                "Subwoofer detected: bass level %d is outside 0-2 range",
                current_level,
            )
            return True

        test_value = -1
        if await self._async_set_feature(FEATURE_BASS_LEVEL, str(test_value)):
            self._bass_level = test_value
            _LOGGER.info(
                "Subwoofer detected: device accepted bass level %d", test_value
            )
            await self._async_set_feature(FEATURE_BASS_LEVEL, str(current_level))
            self._bass_level = current_level
            return True

        _LOGGER.info("No subwoofer detected: device rejected bass level %d", test_value)
        return False

    def register_availability_callback(self, callback: HaAvailabilityCallback) -> None:
        """Register a callback for connection state changes."""
        self._availability_callbacks.add(callback)

    def unregister_availability_callback(
        self, callback: HaAvailabilityCallback
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

    def register_notification_callback(
        self, feature: str, callback: HaNotifyCallback
    ) -> None:
        """Register a callback for notifications."""
        if feature not in self._notification_callbacks:
            self._notification_callbacks[feature] = []
        self._notification_callbacks[feature].append(callback)

    def unregister_notification_callback(
        self, feature: str, callback: HaNotifyCallback
    ) -> None:
        """Unregister a callback for notifications."""
        if feature in self._notification_callbacks:
            with contextlib.suppress(ValueError):
                self._notification_callbacks[feature].remove(callback)

    async def async_listen_for_notifications(self) -> None:
        """Ensure connected; library starts its connection manager on connect."""
        if not self._connected:
            await self.async_connect()

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
    def auto_update(self) -> str:
        """Return the auto update state."""
        return self._auto_update

    @property
    def imax_mode(self) -> str:
        """Return the IMAX mode."""
        return self._imax_mode

    @property
    def voice_zoom(self) -> str:
        """Return the voice zoom state."""
        return self._voice_zoom

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
            self.async_get_auto_update,
            self.async_get_imax_mode,
            self.async_get_voice_zoom,
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
            "Serial: %s, FW: %s, Model Type: %s, Manufacturer: %s, "
            "Auto Update: %s, IMAX Mode: %s, Voice Zoom: %s",
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
            self._auto_update,
            self._imax_mode,
            self._voice_zoom,
        )

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
            FEATURE_AUTO_UPDATE: self._update_auto_update_state,
            FEATURE_IMAX_MODE: self._update_imax_mode_state,
            FEATURE_VOICE_ZOOM: self._update_voice_zoom_state,
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

    def _update_auto_update_state(self, value: Any) -> None:
        """Update auto update from value."""
        self._auto_update = str(value)

    def _update_imax_mode_state(self, value: Any) -> None:
        """Update IMAX mode from value."""
        self._imax_mode = str(value)

    def _update_voice_zoom_state(self, value: Any) -> None:
        """Update voice zoom from value."""
        self._voice_zoom = str(value)

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
                if inspect.iscoroutinefunction(callback):
                    await callback(value)
                else:
                    callback(value)
            except (TypeError, ValueError, AttributeError):
                _LOGGER.exception("Error in notification callback")
