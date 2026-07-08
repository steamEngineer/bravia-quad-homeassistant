"""gRPC ↔ TCP ↔ HA entity path mapping."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

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
    FEATURE_FIRMWARE_VERSION,
    FEATURE_HDMI_CEC,
    FEATURE_HDMI_STANDBY_LINK,
    FEATURE_IMAX_MODE,
    FEATURE_INPUT,
    FEATURE_IP_ADDRESS,
    FEATURE_MAC_ADDRESS,
    FEATURE_MUTE,
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

# Paths formerly hand-crafted — now served by grpc_mapped_entities
HANDCRAFTED_GRPC_PATHS: frozenset[str] = frozenset()

# Media-player paths — not duplicated as standalone switch/number/select entities
MEDIA_PLAYER_GRPC_PATHS: frozenset[str] = frozenset(
    {
        "power",
        "mute",
        "volume",
        "playback_control.function",
        "sound_setting.sound_effect",
    }
)

# App-setting paths: writable via ExecCommand; not readable via GetStates or
# StartNotifyStates on fw 001.454 (live investigation 2026-07-03). Initial HA
# state comes from restore; seeded via grpc_tcp_seed during gRPC backfill when
# a tcp_feature mapping exists (notify-only paths and GetStates gaps).
NOTIFY_ONLY_GRPC_PATHS: tuple[str, ...] = (
    "sound_setting.drc",
    "sound_setting.auto_volume",
    "sound_setting.dsee_ultimate",
    "speaker_sound_setting.360ssm_height",
    "system_setting.earc",
    "system_setting.hdmi_standby_through",
    "system_setting.auto_standby",
    "system_setting.auto_update",
    "system_setting.external_control",
    "system_setting.dimmer",
)

NOTIFY_ONLY_GRPC_PATHS_SET: frozenset[str] = frozenset(NOTIFY_ONLY_GRPC_PATHS)

# Hand-crafted exec-only paths with no TCP read fallback.
_HANDCRAFTED_NO_READ_GRPC_PATHS: frozenset[str] = frozenset(
    {
        "sound_setting.dts_dialog_control",
        "speaker_sound_setting.center_speaker_mode",
    }
)


def grpc_path_needs_ha_restore(path: str) -> bool:
    """Return True when entity state must be restored from HA on reload."""
    return path in NOTIFY_ONLY_GRPC_PATHS_SET or path in _HANDCRAFTED_NO_READ_GRPC_PATHS


@dataclass(frozen=True, slots=True)
class GrpcTcpMapping:
    """Maps gRPC command/state paths to TCP features and HA platforms."""

    grpc_path: str
    tcp_feature: str | None
    ha_platform: str
    writable: bool
    app_setting_id: str | None = None
    notes: str | None = None
    verified: bool = True


GRPC_TCP_MAPPINGS: tuple[GrpcTcpMapping, ...] = (
    GrpcTcpMapping("power", FEATURE_POWER, "media_player", writable=True),
    GrpcTcpMapping("mute", FEATURE_MUTE, "media_player", writable=True),
    GrpcTcpMapping("volume", FEATURE_VOLUME, "media_player", writable=True),
    GrpcTcpMapping(
        "sound_setting.volume.rear",
        FEATURE_REAR_LEVEL,
        "number",
        writable=True,
    ),
    GrpcTcpMapping(
        "sound_setting.volume.bass",
        FEATURE_BASS_LEVEL,
        "select",
        writable=True,
        notes="Bass level min/mid/max (BraviaGrpcBassLevelSelect)",
    ),
    GrpcTcpMapping(
        "sound_setting.volume.subwoofer",
        None,
        "number",
        writable=True,
        notes="Subwoofer level -10 to 10; created when has_subwoofer (gRPC-only path)",
    ),
    GrpcTcpMapping(
        "sound_setting.av_sync.hdmi_0",
        FEATURE_AV_SYNC,
        "number",
        writable=True,
        app_setting_id="sound_setting.av_sync",
    ),
    GrpcTcpMapping(
        "sound_setting.av_sync.arc",
        FEATURE_TV_AV_SYNC,
        "number",
        writable=True,
        app_setting_id="sound_setting.av_sync.current_function",
    ),
    GrpcTcpMapping(
        "sound_setting.imax_enhanced",
        FEATURE_IMAX_MODE,
        "select",
        writable=True,
    ),
    GrpcTcpMapping(
        "sound_setting.voice_mode",
        FEATURE_VOICE_ENHANCER,
        "switch",
        writable=True,
    ),
    GrpcTcpMapping(
        "sound_setting.voice_zoom.on_off",
        FEATURE_VOICE_ZOOM,
        "switch",
        writable=True,
    ),
    GrpcTcpMapping(
        "sound_setting.voice_zoom",
        FEATURE_VOICE_ZOOM_LEVEL,
        "number",
        writable=True,
    ),
    GrpcTcpMapping(
        "sound_setting.sound_field",
        FEATURE_SOUND_FIELD,
        "switch",
        writable=True,
    ),
    GrpcTcpMapping(
        "sound_setting.night_mode",
        FEATURE_NIGHT_MODE,
        "switch",
        writable=True,
    ),
    GrpcTcpMapping(
        "sound_setting.dual_mono",
        FEATURE_DUAL_MONO,
        "select",
        writable=True,
    ),
    GrpcTcpMapping(
        "sound_setting.drc",
        FEATURE_DRC,
        "select",
        writable=True,
        notes="Dynamic Range Compressor; not dts_dialog_control",
    ),
    GrpcTcpMapping(
        "system_setting.cec",
        FEATURE_HDMI_CEC,
        "switch",
        writable=True,
        app_setting_id="system_setting.cec",
    ),
    GrpcTcpMapping(
        "system_setting.nw_bt_standby",
        FEATURE_NET_BT_STANDBY,
        "switch",
        writable=True,
        app_setting_id="system_setting.nw_bt_standby",
    ),
    GrpcTcpMapping(
        "system_setting.friendly_name",
        FEATURE_DEVICE_NAME,
        "sensor",
        writable=False,
        app_setting_id="system_setting.friendly_name",
    ),
    GrpcTcpMapping(
        "system_setting.serial_number",
        FEATURE_SERIAL_NUMBER,
        "sensor",
        writable=False,
    ),
    GrpcTcpMapping(
        "system_setting.time_zone",
        FEATURE_TIMEZONE,
        "sensor",
        writable=False,
    ),
    GrpcTcpMapping(
        "system_setting.wifi_mac_address_wired",
        FEATURE_MAC_ADDRESS,
        "sensor",
        writable=False,
        notes="Wired MAC; wireless available via HTTP sensor",
    ),
    GrpcTcpMapping(
        "system_setting.ipv4_address",
        FEATURE_IP_ADDRESS,
        "sensor",
        writable=False,
    ),
    GrpcTcpMapping(
        "fw_update.version.main",
        FEATURE_FIRMWARE_VERSION,
        "update",
        writable=False,
    ),
    GrpcTcpMapping(
        "bluetooth_setting.connection_quality",
        FEATURE_BT_CONNECTION_QUALITY,
        "select",
        writable=True,
        app_setting_id="bluetooth_setting.connection_quality",
    ),
    GrpcTcpMapping(
        "playback_control.function",
        FEATURE_INPUT,
        "media_player",
        writable=True,
        notes="Input selection via playback function",
    ),
    GrpcTcpMapping(
        "sound_setting.sound_effect",
        None,
        "select",
        writable=True,
        notes="UI Sound Field modes; not sound_setting.sound_field bool",
    ),
    GrpcTcpMapping(
        "sound_setting.dsee_ultimate",
        None,
        "switch",
        writable=True,
        app_setting_id="sound_setting.dsee_ultimate",
    ),
    GrpcTcpMapping(
        "speaker_sound_setting.360ssm_height",
        None,
        "select",
        writable=True,
        app_setting_id="speaker_sound_setting.360ssm_height",
    ),
    GrpcTcpMapping(
        "sound_optimization.raee.is_measured",
        None,
        "sensor",
        writable=False,
        notes="Room calibration state",
    ),
    GrpcTcpMapping(
        "system_setting.auto_standby",
        FEATURE_AUTO_STANDBY,
        "switch",
        writable=True,
        app_setting_id="system_setting.auto_standby",
        verified=False,
    ),
    GrpcTcpMapping(
        "system_setting.auto_update",
        FEATURE_AUTO_UPDATE,
        "switch",
        writable=True,
        app_setting_id="system_setting.auto_update",
        verified=False,
    ),
    GrpcTcpMapping(
        "system_setting.external_control",
        FEATURE_EXTERNAL_CONTROL,
        "switch",
        writable=True,
        app_setting_id="system_setting.external_control",
        verified=False,
    ),
    GrpcTcpMapping(
        "system_setting.earc",
        FEATURE_AUDIO_RETURN_CHANNEL,
        "select",
        writable=True,
        app_setting_id="system_setting.earc",
        verified=False,
        notes="Proto bool; tri-state parity unverified — live spike required",
    ),
    GrpcTcpMapping(
        "system_setting.hdmi_standby_through",
        FEATURE_HDMI_STANDBY_LINK,
        "select",
        writable=True,
        app_setting_id="system_setting.hdmi_standby_through",
        verified=False,
    ),
    GrpcTcpMapping(
        "system_setting.cec_power_off_sync",
        None,
        "select",
        writable=True,
    ),
    GrpcTcpMapping(
        "sound_setting.auto_volume",
        FEATURE_AAV,
        "switch",
        writable=True,
        notes="Auto Volume (AAV); replaces legacy tv_audio mapping",
    ),
    GrpcTcpMapping(
        "speaker_sound_setting.center_speaker_mode",
        None,
        "select",
        writable=True,
        app_setting_id="speaker_sound_setting.center_speaker_mode",
    ),
    GrpcTcpMapping(
        "sound_setting.dts_dialog_control",
        None,
        "switch",
        writable=True,
        notes="DTS Dialog Control; separate from DRC",
    ),
    GrpcTcpMapping(
        "system_setting.dimmer",
        None,
        "select",
        writable=True,
    ),
)

GRPC_PATH_INDEX: dict[str, GrpcTcpMapping] = {
    mapping.grpc_path: mapping for mapping in GRPC_TCP_MAPPINGS
}


def mapping_for_grpc_path(path: str) -> GrpcTcpMapping | None:
    """Return mapping row for a gRPC field path."""
    return GRPC_PATH_INDEX.get(path)


def mappings_with_tcp_feature() -> tuple[GrpcTcpMapping, ...]:
    """Return mappings that bridge into the TCP notification plane."""
    return tuple(m for m in GRPC_TCP_MAPPINGS if m.tcp_feature is not None)


def notify_only_mappings_with_tcp() -> tuple[GrpcTcpMapping, ...]:
    """Notify-only gRPC paths that have a TCP get feature for seeding."""
    notify_only = set(NOTIFY_ONLY_GRPC_PATHS)
    return tuple(
        mapping
        for mapping in GRPC_TCP_MAPPINGS
        if mapping.grpc_path in notify_only and mapping.tcp_feature is not None
    )


def mappings_for_tcp_seed(notify_state: dict[str, Any]) -> tuple[GrpcTcpMapping, ...]:
    """Entity paths still unset in *notify_state* that can be read over TCP."""
    critical = entity_critical_grpc_paths()
    return tuple(
        mapping
        for mapping in GRPC_TCP_MAPPINGS
        if mapping.tcp_feature is not None
        and mapping.grpc_path in critical
        and notify_state.get(mapping.grpc_path) is None
    )


def mappings_for_platform(
    platform: str, *, writable: bool | None = None
) -> tuple[GrpcTcpMapping, ...]:
    """Return mappings for a HA platform, excluding handcrafted duplicates."""
    result: list[GrpcTcpMapping] = []
    for mapping in GRPC_TCP_MAPPINGS:
        if mapping.ha_platform != platform:
            continue
        if mapping.grpc_path in HANDCRAFTED_GRPC_PATHS:
            continue
        if platform in ("switch", "number", "select") and mapping.grpc_path in (
            MEDIA_PLAYER_GRPC_PATHS
        ):
            continue
        if writable is not None and mapping.writable != writable:
            continue
        result.append(mapping)
    return tuple(result)


_ENTITY_PATH_SUFFIX_SKIP: tuple[str, ...] = (
    ".availability",
    ".unavailable_reason",
)


def entity_critical_grpc_paths() -> frozenset[str]:
    """GRPC field paths that back HA entities (excludes availability metadata)."""
    paths: set[str] = set(MEDIA_PLAYER_GRPC_PATHS) | set(HANDCRAFTED_GRPC_PATHS)
    for mapping in GRPC_TCP_MAPPINGS:
        grpc_path = mapping.grpc_path
        if any(grpc_path.endswith(suffix) for suffix in _ENTITY_PATH_SUFFIX_SKIP):
            continue
        paths.add(grpc_path)
    return frozenset(paths)


def missing_entity_paths(notify_state: dict[str, Any]) -> frozenset[str]:
    """Entity paths with no usable value in *notify_state* (missing or ``None``)."""
    return frozenset(
        path for path in entity_critical_grpc_paths() if notify_state.get(path) is None
    )


PARITY_GATE_COMMANDS: tuple[tuple[str, str, int | None], ...] = (
    ("power", FEATURE_POWER, 1),
    ("mute", FEATURE_MUTE, 0),
    ("volume", FEATURE_VOLUME, 50),
    ("sound_setting.av_sync.hdmi_0", FEATURE_AV_SYNC, 0),
    ("sound_setting.imax_enhanced", FEATURE_IMAX_MODE, None),
    ("playback_control.function", FEATURE_INPUT, None),
    ("sound_setting.drc", FEATURE_DRC, None),
    ("sound_setting.auto_volume", FEATURE_AAV, 1),
)
