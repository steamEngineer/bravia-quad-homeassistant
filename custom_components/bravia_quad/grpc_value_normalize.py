"""Normalize gRPC field values to/from TCP/HA conventions."""

from __future__ import annotations

import json
from functools import lru_cache
from typing import TYPE_CHECKING, Any, Literal

from .const import (
    AAV_OFF,
    AAV_ON,
    AUTO_STANDBY_OFF,
    AUTO_STANDBY_ON,
    AUTO_UPDATE_OFF,
    AUTO_UPDATE_ON,
    BASS_LEVEL_OPTIONS,
    BT_CONNECTION_QUALITY_OPTIONS,
    CEC_POWER_OFF_SYNC_OPTIONS,
    CENTER_SPEAKER_MODE_OPTIONS,
    DIMMER_OPTIONS,
    DRC_OPTIONS,
    DUAL_MONO_OPTIONS,
    EXTERNAL_CONTROL_OFF,
    EXTERNAL_CONTROL_ON,
    FEATURE_AUDIO_RETURN_CHANNEL,
    FEATURE_BT_CONNECTION_QUALITY,
    FEATURE_DRC,
    FEATURE_DUAL_MONO,
    FEATURE_IMAX_MODE,
    FEATURE_INPUT,
    FEATURE_VOICE_ENHANCER,
    FEATURE_VOLUME,
    HDMI_CEC_OFF,
    HDMI_CEC_ON,
    HDMI_STANDBY_LINK_OPTIONS,
    IMAX_MODE_OPTIONS,
    INPUT_OPTIONS,
    MUTE_OFF,
    MUTE_ON,
    NET_BT_STANDBY_OFF,
    NET_BT_STANDBY_ON,
    NIGHT_MODE_OFF,
    NIGHT_MODE_ON,
    POWER_OFF,
    POWER_ON,
    SOUND_EFFECT_DEVICE_TO_HA,
    SOUND_EFFECT_HA_TO_DEVICE,
    SOUND_EFFECT_OPTIONS,
    SOUND_FIELD_OFF,
    SOUND_FIELD_ON,
    SSM360_HEIGHT_OPTIONS,
    STEREO_PLAYBACK_OPTIONS,
    SW_PHASE_OPTIONS,
    VOICE_ENHANCER_OFF,
    VOICE_ENHANCER_ON,
    VOICE_ZOOM_OFF,
    VOICE_ZOOM_ON,
)
from .grpc_mapping import GRPC_TCP_MAPPINGS

if TYPE_CHECKING:
    from collections.abc import Mapping

    from .grpc.get_capabilities_response import CapabilityMeta
    from .grpc_mapping import GrpcTcpMapping

ExecValueKind = Literal["bool_value", "int_value", "string_value"]
ExecPayload = bool | int | str | None


@lru_cache(maxsize=1)
def _fallback_omit_zero_int_paths() -> frozenset[str]:
    """Return mapped number paths plus volume for proto3 omit-zero defaults."""
    paths = {
        mapping.grpc_path
        for mapping in GRPC_TCP_MAPPINGS
        if mapping.ha_platform == "number" or mapping.grpc_path == "volume"
    }
    paths.update(
        {
            "sound_setting.volume.rear",
            "sound_setting.volume.subwoofer",
            "sound_setting.av_sync.hdmi_0",
            "sound_setting.av_sync.arc",
            "sound_setting.voice_zoom",
            "volume",
        }
    )
    return frozenset(paths)


def path_is_omit_zero_int(
    path: str,
    capability_index: Mapping[str, CapabilityMeta] | None,
) -> bool:
    """Return whether an omitted value for *path* should normalize to 0."""
    if capability_index is not None:
        meta = capability_index.get(path)
        if meta is not None:
            return meta.type == "int"
    return path in _fallback_omit_zero_int_paths()


# Back-compat alias for call sites written during omit-zero work.
_path_is_omit_zero_int = path_is_omit_zero_int


_ON_OFF_BY_FEATURE: dict[str, tuple[str, str]] = {
    "main.power": (POWER_ON, POWER_OFF),
    "main.mute": (MUTE_ON, MUTE_OFF),
    "audio.soundfield": (SOUND_FIELD_ON, SOUND_FIELD_OFF),
    "audio.nightmode": (NIGHT_MODE_ON, NIGHT_MODE_OFF),
    "hdmi.cec": (HDMI_CEC_ON, HDMI_CEC_OFF),
    "system.autostandby": (AUTO_STANDBY_ON, AUTO_STANDBY_OFF),
    "audio.aav": (AAV_ON, AAV_OFF),
    "system.autoupdate": (AUTO_UPDATE_ON, AUTO_UPDATE_OFF),
    "system.externalcontrol": (EXTERNAL_CONTROL_ON, EXTERNAL_CONTROL_OFF),
    "system.netbtstandby": (NET_BT_STANDBY_ON, NET_BT_STANDBY_OFF),
    "audio.voicezoom3": (VOICE_ZOOM_ON, VOICE_ZOOM_OFF),
}

# gRPC notify strings → TCP select values
_GRPC_BT_TO_TCP: dict[str, str] = {
    "sound_quality": "prioritysound",
    "stable_connection": "priorityconnection",
}
_TCP_BT_TO_GRPC: dict[str, str] = {v: k for k, v in _GRPC_BT_TO_TCP.items()}

_BASS_TCP_TO_GRPC: dict[int, str] = {v: k for k, v in BASS_LEVEL_OPTIONS.items()}

_GRPC_ONLY_BOOL_PATHS: frozenset[str] = frozenset(
    {
        "sound_setting.dsee_ultimate",
        "sound_setting.dts_dialog_control",
        "sound_setting.mix_stage",
    }
)


def format_raee_value(value: Any) -> str | None:
    """Format RAEE measured sensor value for HA display."""
    if value is None:
        return None
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.startswith("{"):
            try:
                return json.dumps(json.loads(stripped), sort_keys=True)
            except json.JSONDecodeError:
                return stripped
        return stripped
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _bool_to_on_off(value: bool, *, on: str, off: str) -> str:
    return on if value else off


def coerce_bool(value: Any) -> bool | None:
    """Coerce gRPC/TCP bool representations to Python bool."""
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value != 0
    if isinstance(value, str):
        return value.lower() in ("on", "true", "1", "yes", "upon")
    return None


def normalize_input_source(value: Any) -> str | None:
    """Map gRPC input values to HA/TCP source ids."""
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if text == "airplay":
        return "airplay2"
    if text == "hdmi":
        return "hdmi1"
    return text


def denormalize_input_source(ha_value: str) -> str:
    """Map HA/TCP source ids to gRPC playback_control.function values."""
    if ha_value == "airplay2":
        return "airplay"
    if ha_value == "hdmi1":
        return "hdmi"
    return ha_value


def normalize_grpc_value(
    mapping: GrpcTcpMapping,
    raw_value: Any,
    *,
    capability_index: Mapping[str, CapabilityMeta] | None = None,
) -> Any | None:
    """Convert a gRPC field value to TCP notification conventions."""
    grpc_path = mapping.grpc_path
    if raw_value is None:
        # Proto3 omits zero ints; path may be present with no value field.
        if _path_is_omit_zero_int(grpc_path, capability_index):
            return 0
        return None

    # Safety net: unsigned int64 that skipped notify/GetStates signed decode.
    if isinstance(raw_value, int) and raw_value >= 1 << 63:
        raw_value = raw_value - (1 << 64)

    tcp_feature = mapping.tcp_feature

    if grpc_path.endswith((".availability", ".unavailable_reason")):
        return None

    if grpc_path == "sound_setting.volume.subwoofer":
        try:
            return int(raw_value)
        except (TypeError, ValueError):
            return raw_value

    if grpc_path in _GRPC_ONLY_BOOL_PATHS:
        if isinstance(raw_value, bool):
            return raw_value
        coerced = coerce_bool(raw_value)
        return coerced if coerced is not None else raw_value

    if grpc_path == "speaker_sound_setting.360ssm_height":
        text = str(raw_value)
        return text or None

    if grpc_path == "speaker_sound_setting.center_speaker_mode":
        text = str(raw_value)
        return text or None

    if grpc_path in (
        "system_setting.cec_power_off_sync",
        "system_setting.dimmer",
    ):
        return str(raw_value)

    if grpc_path == "sound_optimization.raee.is_measured":
        return format_raee_value(raw_value)

    if grpc_path == "sound_setting.sound_effect":
        text = str(raw_value)
        return SOUND_EFFECT_DEVICE_TO_HA.get(text, text) or None

    if tcp_feature is None:
        return None

    if tcp_feature == FEATURE_VOICE_ENHANCER:
        if isinstance(raw_value, bool):
            return VOICE_ENHANCER_ON if raw_value else VOICE_ENHANCER_OFF
        text = str(raw_value).lower()
        if text in ("on", "true", "1", "upon"):
            return VOICE_ENHANCER_ON
        if text in ("off", "false", "0", "upoff"):
            return VOICE_ENHANCER_OFF
        return str(raw_value)

    if tcp_feature in _ON_OFF_BY_FEATURE:
        on, off = _ON_OFF_BY_FEATURE[tcp_feature]
        if isinstance(raw_value, bool):
            return _bool_to_on_off(raw_value, on=on, off=off)
        text = str(raw_value).lower()
        if text in ("on", "true", "1"):
            return on
        if text in ("off", "false", "0"):
            return off
        return str(raw_value)

    if grpc_path == "playback_control.function":
        normalized = normalize_input_source(raw_value)
        return normalized if normalized is not None else str(raw_value)

    if grpc_path == "sound_setting.volume.bass":
        if isinstance(raw_value, str) and raw_value in BASS_LEVEL_OPTIONS:
            return BASS_LEVEL_OPTIONS[raw_value]
        if isinstance(raw_value, int):
            return raw_value
        return raw_value

    if grpc_path in ("sound_setting.imax_enhanced", "sound_setting.drc"):
        if isinstance(raw_value, bool):
            return "on" if raw_value else "off"
        return str(raw_value)

    if grpc_path == "system_setting.earc":
        if isinstance(raw_value, bool):
            return raw_value
        text = str(raw_value).lower()
        if text in ("false", "0", "off"):
            return False
        if text in ("true", "1", "on", "arc", "earc"):
            return True
        coerced = coerce_bool(raw_value)
        return coerced if coerced is not None else raw_value

    if tcp_feature == FEATURE_BT_CONNECTION_QUALITY:
        text = str(raw_value).lower()
        return _GRPC_BT_TO_TCP.get(text, str(raw_value))

    if isinstance(raw_value, bool):
        return _bool_to_on_off(raw_value, on="on", off="off")

    return raw_value


def exec_base_path(command_path: str) -> str:
    """Parent path for ExecCommand availability metadata (e.g. ``*.on_off`` → parent)."""
    if command_path.endswith(".on_off"):
        return command_path.rsplit(".", maxsplit=1)[0]
    return command_path


def grpc_exec_unavailable_reason(
    notify_state: dict[str, Any], command_path: str
) -> str | None:
    """Return device unavailable_reason when ExecCommand should be blocked."""
    base = exec_base_path(command_path)
    reason = notify_state.get(f"{base}.unavailable_reason")
    if reason is not None and str(reason).lower() not in ("", "none"):
        return str(reason)
    availability = notify_state.get(f"{base}.availability")
    if availability is False:
        if reason is None:
            return "unavailable"
        if str(reason).lower() in ("", "none"):
            return None
        return str(reason)
    return None


def denormalize_for_exec(
    mapping: GrpcTcpMapping, ha_value: Any
) -> tuple[ExecValueKind, ExecPayload]:
    """Convert HA/TCP value to ExecCommand kwargs (int_value, bool_value, string_value)."""
    grpc_path = mapping.grpc_path
    tcp_feature = mapping.tcp_feature

    if grpc_path in _GRPC_ONLY_BOOL_PATHS:
        if isinstance(ha_value, bool):
            return ("bool_value", ha_value)
        coerced = coerce_bool(ha_value)
        if coerced is not None:
            return ("bool_value", coerced)
        return ("bool_value", bool(ha_value))

    if tcp_feature in _ON_OFF_BY_FEATURE:
        on, off = _ON_OFF_BY_FEATURE[tcp_feature]
        if isinstance(ha_value, bool):
            return ("bool_value", ha_value)
        text = str(ha_value).lower()
        if text in (on.lower(), "on", "true", "1", "upon"):
            return ("bool_value", True)
        if text in (off.lower(), "off", "false", "0", "upoff"):
            return ("bool_value", False)
        return ("bool_value", text in ("on", "true", "1"))

    if tcp_feature == FEATURE_VOICE_ENHANCER:
        return ("bool_value", str(ha_value).lower() in ("upon", "on", "true", "1"))

    if grpc_path == "playback_control.function":
        return ("string_value", denormalize_input_source(str(ha_value)))

    if grpc_path == "volume" or tcp_feature == FEATURE_VOLUME:
        return ("int_value", int(ha_value))

    if grpc_path == "sound_setting.volume.bass":
        if isinstance(ha_value, int):
            grpc_bass = _BASS_TCP_TO_GRPC.get(ha_value)
            if grpc_bass:
                return ("string_value", grpc_bass)
        return ("string_value", str(ha_value))

    if tcp_feature == FEATURE_IMAX_MODE:
        return ("string_value", str(ha_value))

    if tcp_feature == FEATURE_DRC:
        return ("string_value", str(ha_value))

    if tcp_feature == FEATURE_DUAL_MONO:
        return ("string_value", str(ha_value))

    if tcp_feature == FEATURE_BT_CONNECTION_QUALITY:
        text = str(ha_value).lower()
        return ("string_value", _TCP_BT_TO_GRPC.get(text, text))

    if grpc_path == "sound_setting.sound_effect":
        return (
            "string_value",
            SOUND_EFFECT_HA_TO_DEVICE.get(str(ha_value), str(ha_value)),
        )

    if (
        grpc_path == "system_setting.earc"
        or tcp_feature == FEATURE_AUDIO_RETURN_CHANNEL
    ):
        text = str(ha_value).lower()
        if text in ("off", "false", "0"):
            return ("bool_value", False)
        if text in ("arc", "earc", "on", "true", "1"):
            return ("bool_value", True)
        coerced = coerce_bool(ha_value)
        if coerced is not None:
            return ("bool_value", coerced)
        return ("bool_value", bool(ha_value))

    if mapping.ha_platform == "number":
        return ("int_value", int(ha_value))

    if isinstance(ha_value, bool):
        return ("bool_value", ha_value)

    return ("string_value", str(ha_value))


def ha_options_for_mapping(mapping: GrpcTcpMapping) -> list[str] | None:
    """Return HA option list for select mappings."""
    tcp_feature = mapping.tcp_feature
    if tcp_feature == FEATURE_DRC:
        return list(DRC_OPTIONS)
    if tcp_feature == FEATURE_DUAL_MONO:
        return list(DUAL_MONO_OPTIONS)
    if tcp_feature == FEATURE_IMAX_MODE:
        return list(IMAX_MODE_OPTIONS)
    if tcp_feature == FEATURE_BT_CONNECTION_QUALITY:
        return list(BT_CONNECTION_QUALITY_OPTIONS)
    if tcp_feature == FEATURE_INPUT or mapping.grpc_path == "playback_control.function":
        return list(INPUT_OPTIONS)
    if mapping.grpc_path == "system_setting.hdmi_standby_through":
        return list(HDMI_STANDBY_LINK_OPTIONS)
    if mapping.grpc_path == "system_setting.cec_power_off_sync":
        return list(CEC_POWER_OFF_SYNC_OPTIONS)
    if mapping.grpc_path == "speaker_sound_setting.360ssm_height":
        return list(SSM360_HEIGHT_OPTIONS)
    if mapping.grpc_path == "speaker_sound_setting.center_speaker_mode":
        return list(CENTER_SPEAKER_MODE_OPTIONS)
    if mapping.grpc_path == "sound_setting.sound_effect":
        return list(SOUND_EFFECT_OPTIONS)
    if mapping.grpc_path == "system_setting.dimmer":
        return list(DIMMER_OPTIONS)
    if mapping.grpc_path == "sound_setting.stereo_playback":
        return list(STEREO_PLAYBACK_OPTIONS)
    if mapping.grpc_path == "speaker_sound_setting.sw_phase":
        return list(SW_PHASE_OPTIONS)
    return None
