"""Entity metadata for gRPC mapped entities (TCP parity unique IDs and labels)."""

from __future__ import annotations

from dataclasses import dataclass

from .const import (
    FEATURE_AAV,
    FEATURE_AUDIO_RETURN_CHANNEL,
    FEATURE_AUTO_STANDBY,
    FEATURE_AUTO_UPDATE,
    FEATURE_AV_SYNC,
    FEATURE_BASS_LEVEL,
    FEATURE_BT_CONNECTION_QUALITY,
    FEATURE_DEVICE_NAME,
    FEATURE_DRC,
    FEATURE_DUAL_MONO,
    FEATURE_EXTERNAL_CONTROL,
    FEATURE_HDMI_CEC,
    FEATURE_HDMI_STANDBY_LINK,
    FEATURE_IMAX_MODE,
    FEATURE_INPUT,
    FEATURE_IP_ADDRESS,
    FEATURE_MAC_ADDRESS,
    FEATURE_NET_BT_STANDBY,
    FEATURE_NIGHT_MODE,
    FEATURE_POWER,
    FEATURE_REAR_LEVEL,
    FEATURE_SERIAL_NUMBER,
    FEATURE_SOUND_FIELD,
    FEATURE_TIMEZONE,
    FEATURE_TV_AV_SYNC,
    FEATURE_VOICE_ENHANCER,
    FEATURE_VOICE_ZOOM,
    FEATURE_VOICE_ZOOM_LEVEL,
    FEATURE_VOLUME,
)
from .grpc_mapping import GrpcTcpMapping, mapping_for_grpc_path

# (translation_key, unique_id_suffix) aligned with TCP entities
_BY_TCP_FEATURE: dict[str, tuple[str, str]] = {
    FEATURE_POWER: ("power", "power"),
    FEATURE_VOLUME: ("volume", "volume"),
    FEATURE_AAV: ("auto_volume", "advanced_auto_volume"),
    FEATURE_REAR_LEVEL: ("rear_level", "rear_level"),
    FEATURE_BASS_LEVEL: ("bass_level", "bass_level_slider"),
    FEATURE_VOICE_ZOOM_LEVEL: ("voice_zoom_level", "voice_zoom_level"),
    FEATURE_INPUT: ("input", "input"),
    FEATURE_VOICE_ENHANCER: ("voice_enhancer", "voice_enhancer"),
    FEATURE_SOUND_FIELD: ("sound_field", "sound_field"),
    FEATURE_NIGHT_MODE: ("night_mode", "night_mode"),
    FEATURE_HDMI_CEC: ("hdmi_cec", "hdmi_cec"),
    FEATURE_AUTO_STANDBY: ("auto_standby", "auto_standby"),
    FEATURE_AUTO_UPDATE: ("auto_update", "auto_update"),
    FEATURE_NET_BT_STANDBY: ("net_bt_standby", "net_bt_standby"),
    FEATURE_VOICE_ZOOM: ("voice_zoom", "voice_zoom"),
    FEATURE_EXTERNAL_CONTROL: ("external_control", "external_control"),
    FEATURE_DRC: ("drc", "drc"),
    FEATURE_DUAL_MONO: ("dual_mono", "dual_mono"),
    FEATURE_IMAX_MODE: ("imax_mode", "imax_mode"),
    FEATURE_BT_CONNECTION_QUALITY: ("bt_connection_quality", "bt_connection_quality"),
    FEATURE_HDMI_STANDBY_LINK: ("hdmi_standby_link", "hdmi_standby_link"),
    FEATURE_AUDIO_RETURN_CHANNEL: ("audio_return_channel", "audio_return_channel"),
    FEATURE_AV_SYNC: ("av_sync", "av_sync"),
    FEATURE_TV_AV_SYNC: ("tv_av_sync", "tv_av_sync"),
    FEATURE_DEVICE_NAME: ("device_name", "device_name"),
    FEATURE_TIMEZONE: ("timezone", "timezone"),
    FEATURE_IP_ADDRESS: ("ip_address", "ip_address"),
    FEATURE_MAC_ADDRESS: ("mac_wired", "mac_wired"),
    FEATURE_SERIAL_NUMBER: ("device_name", "serial_number"),
}

_BY_GRPC_PATH: dict[str, tuple[str, str]] = {
    "system_setting.cec_power_off_sync": (
        "cec_power_off_sync",
        "cec_power_off_sync",
    ),
    "system_setting.dimmer": ("display_brightness", "display_brightness"),
    "sound_setting.dsee_ultimate": ("dsee_ultimate", "dsee_ultimate"),
    "sound_setting.dts_dialog_control": ("dts_dialog_control", "dts_dialog_control"),
    "speaker_sound_setting.360ssm_height": ("ssm_360_height", "ssm_360_height"),
    "speaker_sound_setting.center_speaker_mode": (
        "center_speaker_mode",
        "center_speaker_mode",
    ),
    "sound_optimization.raee.is_measured": ("raee_measured", "raee_measured"),
    "sound_setting.volume.bass": ("bass_level", "bass_level_select"),
    "sound_setting.volume.subwoofer": ("subwoofer_level", "subwoofer_level"),
    "battery.life.rl": ("battery_life_rl", "battery_life_rl"),
    "battery.life.rr": ("battery_life_rr", "battery_life_rr"),
    "sound_setting.mix_stage": ("mix_stage", "mix_stage"),
    "sound_setting.stereo_playback": ("stereo_playback", "stereo_playback"),
    "speaker_sound_setting.sw_phase": ("sw_phase", "sw_phase"),
}

# Match TCP entity_registry_enabled_default=False where applicable
_DISABLED_BY_DEFAULT_SUFFIXES: frozenset[str] = frozenset(
    {
        "power",
        "input",
        "volume",
        "voice_zoom",
        "external_control",
        "timezone",
        "dual_mono",
        "volume_step_interval",
        "voice_zoom_level",
        "dts_dialog_control",
        "center_speaker_mode",
        "raee_measured",
        "battery_life_rl",
        "battery_life_rr",
        "mix_stage",
        "stereo_playback",
        "sw_phase",
    }
)


@dataclass(frozen=True, slots=True)
class EntitySpec:
    """Metadata to build a gRPC mapped HA entity."""

    grpc_path: str
    translation_key: str
    unique_id_suffix: str
    mapping: GrpcTcpMapping
    enabled_default: bool


def entity_spec_for_mapping(mapping: GrpcTcpMapping) -> EntitySpec:
    """Build EntitySpec from a GrpcTcpMapping row."""
    if mapping.tcp_feature and mapping.tcp_feature in _BY_TCP_FEATURE:
        translation_key, suffix = _BY_TCP_FEATURE[mapping.tcp_feature]
    elif mapping.grpc_path in _BY_GRPC_PATH:
        translation_key, suffix = _BY_GRPC_PATH[mapping.grpc_path]
    else:
        suffix = mapping.grpc_path.rsplit(".", maxsplit=1)[-1]
        translation_key = suffix

    return EntitySpec(
        grpc_path=mapping.grpc_path,
        translation_key=translation_key,
        unique_id_suffix=suffix,
        mapping=mapping,
        enabled_default=mapping.verified
        and suffix not in _DISABLED_BY_DEFAULT_SUFFIXES,
    )


def entity_spec_for_path(path: str) -> EntitySpec | None:
    """Return EntitySpec for a gRPC path."""
    mapping = mapping_for_grpc_path(path)
    if mapping is None:
        return None
    return entity_spec_for_mapping(mapping)
