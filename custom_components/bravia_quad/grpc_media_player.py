"""gRPC media player for Bravia Quad (TCP parity in gRPC transport mode)."""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from typing import TYPE_CHECKING, Any

from homeassistant.components.media_player import (
    MediaPlayerDeviceClass,
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerState,
    MediaType,
)
from homeassistant.util import dt as dt_util

from .const import (
    DOMAIN,
    INPUT_OPTIONS,
    MAX_VOLUME,
    MUTE_OFF,
    MUTE_ON,
    POWER_OFF,
    POWER_ON,
    SOUND_EFFECT_OPTIONS,
)
from .grpc_entity_registry import entity_spec_for_path
from .grpc_value_normalize import (
    denormalize_for_exec,
    grpc_exec_unavailable_reason,
    normalize_grpc_value,
    normalize_input_source,
)
from .helpers import (
    BraviaGrpcPathMixin,
    VolumeTransitionMixin,
    get_device_info,
)

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry

    from .bravia_grpc_client import BraviaGrpcClientAsync
    from .grpc.client import NotifyStateUpdate
    from .grpc_mapping import GrpcTcpMapping

_LOGGER = logging.getLogger(__name__)

_PATH_POWER = "power"
_PATH_MUTE = "mute"
_PATH_VOLUME = "volume"
_PATH_INPUT = "playback_control.function"
_PATH_TITLE = "playback_control.title"
_PATH_ARTIST = "playback_control.artist"
_PATH_ALBUM = "playback_control.album"
_PATH_DURATION = "playback_control.duration"
_PATH_POSITION = "playback_control.position"
_PATH_JACKET = "playback_control.jacket_url"
_PATH_PLAYBACK_STATE = "playback_control.playback_state"
_PATH_PLAYBACK_COMMAND = "playback_control.playback_command"
_PATH_COMMAND_AVAILABILITY = "playback_control.playback_command.availability"
_PATH_COMMAND_UNAVAILABLE = "playback_control.playback_command.unavailable_reason"
_PATH_SPOTIFY_PLAYLIST = "playback_control.spotify_playlist_name"
_PATH_SERVICE_NAME = "playback_control.service_name"
_PATH_SOUND_EFFECT = "sound_setting.sound_effect"
_PATH_AVAILABLE_VALUES = "playback_control.function.available_values"
_PATH_FUNCTION_AVAILABILITY = "playback_control.function.availability"
_PATH_FUNCTION_UNAVAILABLE = "playback_control.function.unavailable_reason"
_PATH_SPOTIFY_STATUS = "playback_control.spotify.status"

# Read-only playback metadata (extra_state_attributes).
_PATH_AUDIO_FORMAT = "playback_control.audio_format"
_PATH_AUDIO_CHANNEL = "playback_control.audio_channel"
_PATH_SAMPLING_RATE = "playback_control.sampling_rate"
_PATH_IS_360RA = "playback_control.is_360ra"
_PATH_UPMIXER = "playback_control.upmixer"
_PATH_VIRTUALIZER = "playback_control.virtualizer"
_PATH_BT_CODEC = "playback_control.bt_codec"
_PATH_BT_DEVICE_NAME = "playback_control.bt_device_name"
_PATH_BT_SIGNAL_STRENGTH = "playback_control.bt_signal_strength"
_PATH_HDMI_ERROR = "playback_control.hdmi_error"
_PATH_NO_AUDIO = "playback_control.no_audio"

# Confirmed on live HT-A9M2 (Spotify and AirPlay, fw 001.454).
_PLAYBACK_EXEC: dict[str, tuple[str, str, str]] = {
    "play": (_PATH_PLAYBACK_COMMAND, "string_value", "play"),
    "pause": (_PATH_PLAYBACK_COMMAND, "string_value", "pause"),
    "next_track": (_PATH_PLAYBACK_COMMAND, "string_value", "next"),
}

_NOW_PLAYING_PATHS: frozenset[str] = frozenset(
    {
        _PATH_TITLE,
        _PATH_ARTIST,
        _PATH_ALBUM,
        _PATH_DURATION,
        _PATH_POSITION,
        _PATH_JACKET,
        _PATH_PLAYBACK_STATE,
        _PATH_SPOTIFY_PLAYLIST,
        _PATH_SERVICE_NAME,
    }
)

_METADATA_PATH_TO_KEY: dict[str, str] = {
    _PATH_AUDIO_FORMAT: "audio_format",
    _PATH_AUDIO_CHANNEL: "audio_channel",
    _PATH_SAMPLING_RATE: "sampling_rate",
    _PATH_IS_360RA: "is_360ra",
    _PATH_UPMIXER: "upmixer",
    _PATH_VIRTUALIZER: "virtualizer",
    _PATH_BT_CODEC: "bt_codec",
    _PATH_BT_DEVICE_NAME: "bt_device_name",
    _PATH_BT_SIGNAL_STRENGTH: "bt_signal_strength",
    _PATH_HDMI_ERROR: "hdmi_error",
    _PATH_NO_AUDIO: "no_audio",
    _PATH_SPOTIFY_STATUS: "spotify_status",
    _PATH_FUNCTION_UNAVAILABLE: "source_unavailable_reason",
}

_METADATA_PATHS: frozenset[str] = frozenset(_METADATA_PATH_TO_KEY)

_HDMI_INPUT_METADATA: frozenset[str] = frozenset(
    {
        "audio_format",
        "audio_channel",
        "sampling_rate",
        "hdmi_error",
        "no_audio",
        "is_360ra",
        "upmixer",
        "virtualizer",
        "source_unavailable_reason",
    }
)

_SOURCE_METADATA_KEYS: dict[str, frozenset[str]] = {
    "tv": _HDMI_INPUT_METADATA,
    "hdmi1": _HDMI_INPUT_METADATA,
    "bluetooth": frozenset(
        {
            "bt_codec",
            "bt_device_name",
            "bt_signal_strength",
            "is_360ra",
            "upmixer",
            "virtualizer",
            "source_unavailable_reason",
        }
    ),
    "spotify": frozenset(
        {
            "spotify_status",
            "is_360ra",
            "upmixer",
            "virtualizer",
            "source_unavailable_reason",
        }
    ),
    "airplay2": frozenset(
        {
            "is_360ra",
            "upmixer",
            "virtualizer",
            "source_unavailable_reason",
        }
    ),
}

_COMMAND_NOTIFY_PATHS: frozenset[str] = frozenset(
    {_PATH_COMMAND_AVAILABILITY, _PATH_COMMAND_UNAVAILABLE}
)

_SOURCE_NOTIFY_PATHS: frozenset[str] = frozenset(
    {
        _PATH_AVAILABLE_VALUES,
        _PATH_FUNCTION_AVAILABILITY,
        _PATH_FUNCTION_UNAVAILABLE,
    }
)

_BASE_SUPPORTED_FEATURES = (
    MediaPlayerEntityFeature.TURN_ON
    | MediaPlayerEntityFeature.TURN_OFF
    | MediaPlayerEntityFeature.VOLUME_SET
    | MediaPlayerEntityFeature.VOLUME_STEP
    | MediaPlayerEntityFeature.VOLUME_MUTE
    | MediaPlayerEntityFeature.SELECT_SOURCE
    | MediaPlayerEntityFeature.SELECT_SOUND_MODE
)

_TRANSPORT_FEATURE_BY_ACTION: dict[str, MediaPlayerEntityFeature] = {
    "play": MediaPlayerEntityFeature.PLAY,
    "pause": MediaPlayerEntityFeature.PAUSE,
    "next_track": MediaPlayerEntityFeature.NEXT_TRACK,
}

_CORE_PATHS: frozenset[str] = frozenset(
    {_PATH_POWER, _PATH_MUTE, _PATH_VOLUME, _PATH_INPUT, _PATH_SOUND_EFFECT}
)

# Inputs that may carry streaming now-playing metadata from the device.
_STREAMING_SOURCES: frozenset[str] = frozenset({"spotify", "bluetooth", "airplay2"})

# AirPlay is detect-only — activated by casting, not ExecCommand source switch.
_DETECT_ONLY_SOURCES: frozenset[str] = frozenset({"airplay2"})

# Backfill on setup — bulk GetStates often omits *.availability (notify-only delta).
_PLAYBACK_BACKFILL_PATHS: tuple[str, ...] = (
    _PATH_COMMAND_AVAILABILITY,
    _PATH_COMMAND_UNAVAILABLE,
    _PATH_PLAYBACK_STATE,
)

_ACTION_DEVICE_TOKENS: dict[str, str] = {
    "next_track": "next",
    "previous_track": "previous",
}

_POSITION_WRITE_INTERVAL = 5.0

# HA MediaPlayerEntity exposes several media_* reads via @cached_property.
_CACHED_MEDIA_PROPS: tuple[str, ...] = (
    "media_title",
    "media_artist",
    "media_album_name",
    "media_content_type",
    "media_duration",
    "media_position",
    "media_position_updated_at",
    "media_image_url",
    "media_image_remotely_accessible",
    "media_playlist",
    "app_name",
    "entity_picture",
    "sound_mode",
    "sound_mode_list",
    "extra_state_attributes",
)


def _coerce_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _parse_seconds(value: Any) -> int | None:
    try:
        seconds = int(value)
    except (TypeError, ValueError):
        return None
    if seconds < 0:
        return None
    return seconds


def _parse_available_values(raw: Any) -> list[str] | None:
    """Parse device-reported source list; None means keep current list."""
    text = _coerce_str(raw)
    if not text:
        return None
    if text.startswith("["):
        try:
            parsed = json.loads(text)
            if isinstance(parsed, list):
                return [str(item).strip() for item in parsed if str(item).strip()]
        except (json.JSONDecodeError, TypeError, ValueError):
            pass
    separator = "," if "," in text else None
    if separator:
        parts = [part.strip() for part in text.split(separator)]
    else:
        parts = re.split(r"\s+", text)
    values = [part for part in parts if part]
    normalized = []
    for value in values or []:
        mapped = normalize_input_source(value)
        if mapped and mapped not in normalized:
            normalized.append(mapped)
    return normalized or None


def _filter_source_list(sources: list[str], *, current: str | None) -> list[str]:
    """Omit detect-only sources unless they are the active input."""
    return [
        source
        for source in sources
        if source not in _DETECT_ONLY_SOURCES or source == current
    ]


def _source_selection_blocked(reason: str | None) -> bool:
    if not reason:
        return False
    return reason.lower() not in ("none", "")


def _coerce_availability_flag(availability: Any) -> bool | None:
    """Return True/False when availability is a bool-like scalar, else None."""
    if availability is None:
        return None
    if isinstance(availability, bool):
        return availability
    if isinstance(availability, int):
        return availability != 0
    text = _coerce_str(availability)
    if text is None:
        return None
    lower = text.lower()
    if lower in ("true", "1", "yes", "on"):
        return True
    if lower in ("false", "0", "no", "off"):
        return False
    return None


def _availability_allows_action(availability: Any, action: str) -> bool:
    """Match HA transport action against device availability metadata."""
    flag = _coerce_availability_flag(availability)
    if flag is not None:
        return flag
    text = _coerce_str(availability)
    if text is None:
        return False
    tokens = re.split(r"[\s,]+", text.lower())
    device_token = _ACTION_DEVICE_TOKENS.get(action, action)
    return device_token in tokens


class BraviaGrpcMediaPlayer(
    BraviaGrpcPathMixin, VolumeTransitionMixin, MediaPlayerEntity
):
    """Bravia Quad media player driven by gRPC notify + ExecCommand."""

    _attr_device_class = MediaPlayerDeviceClass.SPEAKER
    _attr_has_entity_name = True
    _attr_name = None
    _attr_should_poll = False
    _attr_translation_key = "bravia_quad"
    # Spotify / streaming jacket URLs are on the public internet (i.scdn.co, etc.).
    _attr_media_image_remotely_accessible = True

    def __init__(self, grpc_client: BraviaGrpcClientAsync, entry: ConfigEntry) -> None:
        self._grpc_client = grpc_client
        self._entry = entry
        self._grpc_path = _PATH_POWER
        self._attr_unique_id = f"{DOMAIN}_{entry.unique_id}_media_player"
        self._attr_device_info = get_device_info(entry)
        self._attr_source_list = _filter_source_list(list(INPUT_OPTIONS), current=None)
        self._attr_sound_mode_list = list(SOUND_EFFECT_OPTIONS)
        self._playback_metadata: dict[str, str] = {}
        self._last_position_write = 0.0
        self._position_write_task: asyncio.Task[None] | None = None
        self._init_volume_transition()
        self._seed_from_cache()

    @property
    def volume_step_interval(self) -> int:
        return self._grpc_client.volume_step_interval

    async def _async_volume_step(self, volume: int) -> bool:
        return await self._async_exec_path(_PATH_VOLUME, volume)

    @property
    def supported_features(self) -> MediaPlayerEntityFeature:
        """Return base features plus transport controls on streaming sources."""
        features = _BASE_SUPPORTED_FEATURES
        if _source_selection_blocked(
            self._playback_metadata.get("source_unavailable_reason")
        ):
            features &= ~MediaPlayerEntityFeature.SELECT_SOURCE
        if not self._transport_controls_available():
            return features
        for action, flag in _TRANSPORT_FEATURE_BY_ACTION.items():
            if action in _PLAYBACK_EXEC and self._playback_action_allowed(action):
                features |= flag
        return features

    @property
    def extra_state_attributes(self) -> dict[str, str]:
        """Return source-context playback metadata."""
        source = self._attr_source or "tv"
        allowed = _SOURCE_METADATA_KEYS.get(source, frozenset())
        return {
            key: value
            for key, value in self._playback_metadata.items()
            if key in allowed and value
        }

    def _transport_controls_available(self) -> bool:
        if not self._power_is_on():
            return False
        return self._attr_source in _STREAMING_SOURCES

    def _playback_action_allowed(self, action: str) -> bool:
        """Gate transport actions when device publishes command availability."""
        if grpc_exec_unavailable_reason(
            self._grpc_client.notify_state, _PATH_PLAYBACK_COMMAND
        ):
            return False
        availability = self._grpc_client.notify_state.get(_PATH_COMMAND_AVAILABILITY)
        if availability is None:
            # AirPlay publishes explicit availability; Spotify often leaves it null.
            return self._attr_source != "airplay2"
        return _availability_allows_action(availability, action)

    def _mapping(self, path: str) -> GrpcTcpMapping:
        spec = entity_spec_for_path(path)
        assert spec is not None
        return spec.mapping

    def _power_is_on(self) -> bool:
        power = normalize_grpc_value(
            self._mapping(_PATH_POWER),
            self._grpc_client.notify_state.get(_PATH_POWER),
        )
        return power == POWER_ON

    def _update_media_player_state(self) -> None:
        """Sync HA playback state from power + device playback_state notify."""
        if not self._power_is_on():
            self._attr_state = MediaPlayerState.OFF
            return
        playback = _coerce_str(self._grpc_client.notify_state.get(_PATH_PLAYBACK_STATE))
        playback_key = playback.lower() if playback else ""
        if playback_key in ("play", "playing"):
            self._attr_state = MediaPlayerState.PLAYING
        elif playback_key in ("pause", "paused"):
            self._attr_state = MediaPlayerState.PAUSED
        elif self._attr_media_title:
            self._attr_state = MediaPlayerState.PLAYING
        else:
            self._attr_state = MediaPlayerState.ON

    def _update_source_list_from_cache(self) -> None:
        parsed = _parse_available_values(
            self._grpc_client.notify_state.get(_PATH_AVAILABLE_VALUES)
        )
        if parsed:
            self._attr_source_list = _filter_source_list(
                parsed, current=self._attr_source
            )

    def _has_playback_signal(self) -> bool:
        state = self._grpc_client.notify_state
        if _coerce_str(state.get(_PATH_TITLE)):
            return True
        if _coerce_str(state.get(_PATH_PLAYBACK_STATE)):
            return True
        if _coerce_str(state.get(_PATH_SERVICE_NAME)):
            return True
        return _parse_seconds(state.get(_PATH_POSITION)) is not None

    def _seed_from_cache(self) -> None:
        state = self._grpc_client.notify_state
        vol = state.get(_PATH_VOLUME)
        try:
            volume = int(vol) if vol is not None else 0
            self._attr_volume_level = volume / MAX_VOLUME
        except (TypeError, ValueError):
            self._attr_volume_level = 0.0
        mute = normalize_grpc_value(self._mapping(_PATH_MUTE), state.get(_PATH_MUTE))
        if mute is not None:
            self._attr_is_volume_muted = mute == MUTE_ON
        src = normalize_grpc_value(self._mapping(_PATH_INPUT), state.get(_PATH_INPUT))
        self._attr_source = str(src) if src else "tv"
        self._update_source_list_from_cache()
        if not self._attr_source_list:
            self._attr_source_list = _filter_source_list(
                list(INPUT_OPTIONS), current=self._attr_source
            )
        if self._attr_source not in self._attr_source_list:
            self._attr_source_list = [*self._attr_source_list, self._attr_source]
        sound_effect = _coerce_str(state.get(_PATH_SOUND_EFFECT))
        if sound_effect and sound_effect in self._attr_sound_mode_list:
            self._attr_sound_mode = sound_effect
        self._seed_metadata_from_cache()
        self._seed_playback_from_cache()
        self._update_media_player_state()

    def _seed_metadata_from_cache(self) -> None:
        for path in _METADATA_PATHS:
            value = self._grpc_client.notify_state.get(path)
            if value is not None:
                self._apply_metadata_update(path, value)

    def _seed_playback_from_cache(self) -> None:
        if self._attr_source not in _STREAMING_SOURCES:
            return
        if not self._has_playback_signal():
            return
        for path in _NOW_PLAYING_PATHS:
            value = self._grpc_client.notify_state.get(path)
            if value is not None:
                self._apply_playback_update(path, value)

    def _clear_playback_metadata(self) -> None:
        self._attr_media_title = None
        self._attr_media_artist = None
        self._attr_media_album_name = None
        self._attr_media_content_type = None
        self._attr_media_duration = None
        self._attr_media_position = None
        self._attr_media_position_updated_at = None
        self._attr_media_image_url = None
        self._attr_media_playlist = None
        self._attr_app_name = None

    def _clear_source_context_metadata(self) -> None:
        keys_to_clear = set().union(*_SOURCE_METADATA_KEYS.values()) - {
            "source_unavailable_reason"
        }
        for key in keys_to_clear:
            self._playback_metadata.pop(key, None)

    def _invalidate_media_cached_properties(self) -> None:
        for name in _CACHED_MEDIA_PROPS:
            self.__dict__.pop(name, None)

    def _apply_metadata_update(self, path: str, value: Any) -> bool:
        key = _METADATA_PATH_TO_KEY.get(path)
        if key is None:
            return False
        text = _coerce_str(value)
        if text is None:
            self._playback_metadata.pop(key, None)
        else:
            self._playback_metadata[key] = text
        return True

    def _apply_playback_update(self, path: str, value: Any) -> bool:  # noqa: PLR0911
        """Update playback attrs from notify; True means write HA state immediately."""
        if path == _PATH_TITLE:
            title = _coerce_str(value)
            if not title:
                self._clear_playback_metadata()
                return True
            self._attr_media_title = title
            self._attr_media_content_type = MediaType.MUSIC
            return True
        if path == _PATH_ARTIST:
            self._attr_media_artist = _coerce_str(value)
            return True
        if path == _PATH_ALBUM:
            self._attr_media_album_name = _coerce_str(value)
            return True
        if path == _PATH_DURATION:
            self._attr_media_duration = _parse_seconds(value)
            return True
        if path == _PATH_POSITION:
            position = _parse_seconds(value)
            if position is None:
                return False
            self._attr_media_position = position
            self._attr_media_position_updated_at = dt_util.utcnow()
            return False
        if path == _PATH_JACKET:
            self._attr_media_image_url = _coerce_str(value)
            return True
        if path == _PATH_PLAYBACK_STATE:
            return True
        if path == _PATH_SPOTIFY_PLAYLIST:
            self._attr_media_playlist = _coerce_str(value)
            return True
        if path == _PATH_SERVICE_NAME:
            self._attr_app_name = _coerce_str(value)
            return True
        return False

    def _schedule_playback_state_write(self, *, immediate: bool) -> None:
        if not getattr(self, "hass", None):
            return
        self._invalidate_media_cached_properties()
        if immediate:
            if self._position_write_task:
                self._position_write_task.cancel()
                self._position_write_task = None
            self._last_position_write = time.monotonic()
            self.async_write_ha_state()
            return
        elapsed = time.monotonic() - self._last_position_write
        if elapsed >= _POSITION_WRITE_INTERVAL:
            self._last_position_write = time.monotonic()
            self.async_write_ha_state()
            return
        if self._position_write_task and not self._position_write_task.done():
            return
        delay = _POSITION_WRITE_INTERVAL - elapsed
        self._position_write_task = self.hass.async_create_task(
            self._delayed_playback_write(delay)
        )

    async def _delayed_playback_write(self, delay: float) -> None:
        try:
            await asyncio.sleep(delay)
            self._last_position_write = time.monotonic()
            self._invalidate_media_cached_properties()
            self.async_write_ha_state()
        except asyncio.CancelledError:
            pass
        finally:
            self._position_write_task = None

    def _grpc_state_callback(self, update: NotifyStateUpdate) -> None:
        path = update.path
        if path in _COMMAND_NOTIFY_PATHS:
            self.hass.async_create_task(self._on_command_availability_update())
            return
        if path in _SOURCE_NOTIFY_PATHS:
            self.hass.async_create_task(self._on_source_notify(path, update.value))
            return
        if path in _METADATA_PATHS:
            self.hass.async_create_task(self._on_metadata_update(path, update.value))
            return
        if path in _NOW_PLAYING_PATHS:
            self.hass.async_create_task(self._on_playback_update(path, update.value))
            return
        if path not in _CORE_PATHS:
            return
        self.hass.async_create_task(self._on_path_update(path, update.value))

    async def _on_command_availability_update(self) -> None:
        if self._attr_source in _STREAMING_SOURCES:
            await self._backfill_playback_paths()
        self.async_write_ha_state()

    async def _backfill_playback_paths(self) -> None:
        await self._grpc_client.async_fetch_field_paths(list(_PLAYBACK_BACKFILL_PATHS))

    async def _on_source_notify(self, path: str, value: Any) -> None:
        if path == _PATH_AVAILABLE_VALUES:
            parsed = _parse_available_values(value)
            if parsed:
                self._attr_source_list = _filter_source_list(
                    parsed, current=self._attr_source
                )
        elif path in (_PATH_FUNCTION_AVAILABILITY, _PATH_FUNCTION_UNAVAILABLE):
            self._apply_metadata_update(path, value)
        self.async_write_ha_state()

    async def _on_metadata_update(self, path: str, value: Any) -> None:
        self._apply_metadata_update(path, value)
        self.async_write_ha_state()

    async def _on_playback_update(self, path: str, value: Any) -> None:
        if self._attr_source not in _STREAMING_SOURCES:
            return
        immediate = self._apply_playback_update(path, value)
        self._update_media_player_state()
        self._schedule_playback_state_write(immediate=immediate)

    async def _handle_source_transition(self, previous: str | None, new: str) -> None:
        """Apply source-change side effects shared by notify and user selection."""
        self._attr_source = new
        if new not in self._attr_source_list:
            self._attr_source_list = [*self._attr_source_list, new]
        if previous in _STREAMING_SOURCES and new not in _STREAMING_SOURCES:
            self._clear_playback_metadata()
            self._clear_source_context_metadata()
            self._update_media_player_state()
        elif previous not in _STREAMING_SOURCES and new in _STREAMING_SOURCES:
            self._clear_source_context_metadata()
            await self._backfill_playback_paths()
            self._seed_playback_from_cache()
        elif previous != new:
            self._clear_source_context_metadata()
            self._seed_metadata_from_cache()

    async def _on_path_update(self, path: str, value: Any) -> None:
        if path == _PATH_VOLUME and self.should_suppress_volume_notification():
            return
        mapping = self._mapping(path)
        normalized = normalize_grpc_value(mapping, value)
        if path == _PATH_POWER:
            self._update_media_player_state()
        elif path == _PATH_MUTE:
            if normalized is None:
                return
            self._attr_is_volume_muted = normalized == MUTE_ON
        elif path == _PATH_VOLUME:
            try:
                volume = int(normalized)
                if 0 <= volume <= MAX_VOLUME:
                    self._attr_volume_level = volume / MAX_VOLUME
            except (TypeError, ValueError):
                return
        elif path == _PATH_SOUND_EFFECT:
            mode = _coerce_str(value)
            if mode and mode in self._attr_sound_mode_list:
                self._attr_sound_mode = mode
        elif path == _PATH_INPUT:
            previous = self._attr_source
            option = str(normalized) if normalized is not None else None
            if option is None:
                return
            await self._handle_source_transition(previous, option)
        self.async_write_ha_state()

    async def _on_grpc_state(self, value: Any) -> None:
        """Unused — multi-path callbacks via _grpc_state_callback override."""

    async def _async_exec_path(self, path: str, ha_value: Any) -> bool:
        mapping = self._mapping(path)
        kind, payload = denormalize_for_exec(mapping, ha_value)
        return await self._grpc_client.async_exec_command(path, **{kind: payload})

    async def _async_exec_playback(self, action: str) -> bool:
        if not self._transport_controls_available():
            return False
        if not self._playback_action_allowed(action):
            return False
        spec = _PLAYBACK_EXEC.get(action)
        if spec is None:
            return False
        path, value_kind, payload = spec
        before_state = self._grpc_client.notify_state.get(_PATH_PLAYBACK_STATE)
        before_title = self._grpc_client.notify_state.get(_PATH_TITLE)
        ok = await self._grpc_client.async_exec_command(path, **{value_kind: payload})
        if ok:
            await self._await_playback_confirm(
                action,
                before_state=before_state,
                before_title=before_title,
            )
        return ok

    async def _await_playback_confirm(
        self,
        action: str,
        *,
        before_state: Any,
        before_title: Any,
        timeout: float = 2.0,
    ) -> None:
        """Refresh HA state after transport exec once notify confirms (or timeout)."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if action == "next_track":
                if self._grpc_client.notify_state.get(_PATH_TITLE) != before_title:
                    break
            elif action == "pause":
                state = _coerce_str(
                    self._grpc_client.notify_state.get(_PATH_PLAYBACK_STATE)
                )
                if state and state.lower() in ("pause", "paused"):
                    break
            elif action == "play":
                state = _coerce_str(
                    self._grpc_client.notify_state.get(_PATH_PLAYBACK_STATE)
                )
                if state and state.lower() in ("play", "playing"):
                    break
            else:
                break
            await asyncio.sleep(0.1)
        self._update_media_player_state()
        self._invalidate_media_cached_properties()
        if getattr(self, "hass", None):
            self.async_write_ha_state()

    async def async_media_play(self) -> None:
        await self._async_exec_playback("play")

    async def async_media_pause(self) -> None:
        await self._async_exec_playback("pause")

    async def async_media_next_track(self) -> None:
        await self._async_exec_playback("next_track")

    async def async_select_sound_mode(self, sound_mode: str) -> None:
        if sound_mode not in self._attr_sound_mode_list:
            return
        if await self._grpc_client.async_exec_command(
            _PATH_SOUND_EFFECT, string_value=sound_mode
        ):
            self._attr_sound_mode = sound_mode
            self.async_write_ha_state()

    async def async_turn_on(self) -> None:
        if await self._async_exec_path(_PATH_POWER, POWER_ON):
            self._update_media_player_state()
            self.async_write_ha_state()

    async def async_turn_off(self) -> None:
        if await self._async_exec_path(_PATH_POWER, POWER_OFF):
            self._update_media_player_state()
            self.async_write_ha_state()

    async def async_set_volume_level(self, volume: float) -> None:
        clamped = min(max(volume, 0.0), 1.0)
        target = round(clamped * MAX_VOLUME)
        previous = self._attr_volume_level
        current = round((previous or 0) * MAX_VOLUME)
        self._attr_volume_level = target / MAX_VOLUME
        self.async_write_ha_state()
        if not await self._async_set_volume_with_transition(current, target):
            self._attr_volume_level = previous
            self.async_write_ha_state()

    async def async_volume_up(self) -> None:
        current = round((self._attr_volume_level or 0) * MAX_VOLUME)
        target = min(current + 1, MAX_VOLUME)
        if await self._async_exec_path(_PATH_VOLUME, target):
            self._attr_volume_level = target / MAX_VOLUME
            self.async_write_ha_state()

    async def async_volume_down(self) -> None:
        current = round((self._attr_volume_level or 0) * MAX_VOLUME)
        target = max(current - 1, 0)
        if await self._async_exec_path(_PATH_VOLUME, target):
            self._attr_volume_level = target / MAX_VOLUME
            self.async_write_ha_state()

    async def async_select_source(self, source: str) -> None:
        if source in _DETECT_ONLY_SOURCES and self._attr_source != source:
            return
        if source not in self._attr_source_list:
            return
        if await self._async_exec_path(_PATH_INPUT, source):
            await self._handle_source_transition(self._attr_source, source)
            self.async_write_ha_state()

    async def async_mute_volume(self, mute: bool) -> None:  # noqa: FBT001
        state = MUTE_ON if mute else MUTE_OFF
        if await self._async_exec_path(_PATH_MUTE, state):
            self._attr_is_volume_muted = mute
            self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self._grpc_client.add_state_callback(self._grpc_state_callback)
        await self._grpc_client.async_fetch_field_paths(list(_PLAYBACK_BACKFILL_PATHS))
        self._seed_from_cache()
        self._invalidate_media_cached_properties()
        self.async_write_ha_state()

    async def async_will_remove_from_hass(self) -> None:
        self._grpc_client.remove_state_callback(self._grpc_state_callback)
        self._cancel_volume_transition()
        if self._position_write_task:
            self._position_write_task.cancel()
        await super().async_will_remove_from_hass()
