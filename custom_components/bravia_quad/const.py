"""Constants for the Bravia Quad integration."""

from __future__ import annotations

DOMAIN = "bravia_quad"

# Configuration keys
CONF_HAS_SUBWOOFER = "has_subwoofer"
CONF_MANUFACTURER = "manufacturer"
CONF_MODEL = "model"
CONF_MODEL_ID = "model_id"
CONF_SERIAL = "serial_number"
CONF_VOLUME_STEP_INTERVAL = "volume_step_interval"
CONF_TRANSPORT = "transport"
CONF_USE_GRPC = "use_grpc"  # legacy options key; migrated to CONF_TRANSPORT
CONF_GRPC_KEYS = "grpc_keys"
CONF_GRPC_OAUTH_REDIRECT = "grpc_oauth_redirect"
CONF_GRPC_DEVICE_ID = "grpc_device_id"
CONF_GRPC_DEBUG = "grpc_debug"
CONF_GRPC_SEEDS_POLL = "grpc_seeds_poll"
# Persisted gRPC ``*.unavailable_reason`` map (reload survives GetStates ``none``).
CONF_FEATURE_UNAVAILABLE_REASONS = "feature_unavailable_reasons"

TRANSPORT_TCP = "tcp"
TRANSPORT_GRPC = "grpc"

# gRPC (BRAVIA Connect control plane)
DEFAULT_GRPC_PORT = 55051

# Default values
DEFAULT_MODEL = "Bravia Theatre"
DEFAULT_NAME = "Bravia Theatre"
DEFAULT_VOLUME_STEP_INTERVAL = 0  # ms

# Default port for Bravia Theatre TCP communication
DEFAULT_PORT = 33336

# Timeout for TCP operations
TCP_TIMEOUT = 10

# Reconnection delays (seconds)
RECONNECT_INITIAL_DELAY = 5
RECONNECT_MAX_DELAY = 60


# Device limits
MAX_VOLUME = 100
MIN_VOLUME = 0
MAX_VOLUME_STEP_INTERVAL = 10000  # 10s
MAX_REAR_LEVEL = 10
MIN_REAR_LEVEL = -10
MAX_BASS_LEVEL = 10
MIN_BASS_LEVEL = -10

# Bass level limits for non-subwoofer mode (select: MIN/MID/MAX)
MAX_BASS_LEVEL_NO_SUB = 2
MIN_BASS_LEVEL_NO_SUB = 0

# Command ID limits (to prevent overflow)
CMD_ID_INITIAL = 10
CMD_ID_MAX = 1_000_000

# Features
FEATURE_POWER = "main.power"
FEATURE_VOLUME = "main.volumestep"
FEATURE_INPUT = "main.input"
FEATURE_REAR_LEVEL = "main.rearvolumestep"
FEATURE_BASS_LEVEL = "main.bassstep"
FEATURE_VOICE_ENHANCER = "audio.voiceenhancer"
FEATURE_SOUND_FIELD = "audio.soundfield"
FEATURE_NIGHT_MODE = "audio.nightmode"
FEATURE_HDMI_CEC = "hdmi.cec"
FEATURE_AUTO_STANDBY = "system.autostandby"
FEATURE_DRC = "audio.drangecomp"
FEATURE_AAV = "audio.aav"
FEATURE_MUTE = "main.mute"
FEATURE_HDMI_PASSTHROUGH = "hdmi.passthrough"
FEATURE_DUAL_MONO = "audio.dualmono"
FEATURE_AUTO_UPDATE = "system.autoupdate"
FEATURE_IMAX_MODE = "audio.imaxmode"
FEATURE_AV_SYNC = "audio.avsync"
FEATURE_TV_AV_SYNC = "tv.avsync"
FEATURE_BT_CONNECTION_QUALITY = "bluetooth.connectionquality"

FEATURE_SERIAL_NUMBER = "system.serialnumber"
FEATURE_EXTERNAL_CONTROL = "system.externalcontrol"
FEATURE_HDMI_STANDBY_LINK = "hdmi.standbylink"
FEATURE_NET_BT_STANDBY = "system.netbtstandby"
FEATURE_VOICE_ZOOM = "audio.voicezoom3"
FEATURE_VOICE_ZOOM_LEVEL = "audio.voicezoom3step"
FEATURE_AUDIO_RETURN_CHANNEL = "hdmi.audioreturnchannel"
FEATURE_MAC_ADDRESS = "network.macaddress"
FEATURE_TIMEZONE = "system.timezone"
FEATURE_TEMPERATURE = "system.temperature"
FEATURE_360SSM = "audio.360ssm"
FEATURE_FIRMWARE_VERSION = "system.version"
FEATURE_MODEL_TYPE = "system.modeltype"
FEATURE_MANUFACTURER = "system.manufacturer"
FEATURE_DEVICE_NAME = "system.devicename"
FEATURE_NETWORK_MODE = "network.mode"
FEATURE_IP_ADDRESS = "network.ipaddress"
FEATURE_DESTINATION = "system.destination"
FEATURE_LANGUAGE = "system.language"
FEATURE_DHCP = "network.dhcp"

# Power states
POWER_ON = "on"
POWER_OFF = "off"

# Voice Enhancer states
VOICE_ENHANCER_ON = "upon"
VOICE_ENHANCER_OFF = "upoff"

# Sound Field states
SOUND_FIELD_ON = "on"
SOUND_FIELD_OFF = "off"

# Night Mode states
NIGHT_MODE_ON = "on"
NIGHT_MODE_OFF = "off"

# HDMI CEC states
HDMI_CEC_ON = "on"
HDMI_CEC_OFF = "off"

# Auto Standby states
AUTO_STANDBY_ON = "on"
AUTO_STANDBY_OFF = "off"

# Advanced Auto Volume states
AAV_ON = "on"
AAV_OFF = "off"

# Mute states
MUTE_ON = "on"
MUTE_OFF = "off"

# Auto Update states
AUTO_UPDATE_ON = "on"
AUTO_UPDATE_OFF = "off"

# IMAX Mode states
IMAX_MODE_AUTO = "auto"
IMAX_MODE_ON = "on"
IMAX_MODE_OFF = "off"

# IMAX Mode options (API values used as translation keys)
IMAX_MODE_OPTIONS: list[str] = ["auto", "on", "off"]

# External Control states
EXTERNAL_CONTROL_ON = "on"
EXTERNAL_CONTROL_OFF = "off"

# HDMI Standby Link states
HDMI_STANDBY_LINK_ON = "on"
HDMI_STANDBY_LINK_OFF = "off"

# Network/BT Standby states
NET_BT_STANDBY_ON = "on"
NET_BT_STANDBY_OFF = "off"

# Voice Zoom states
VOICE_ZOOM_ON = "on"
VOICE_ZOOM_OFF = "off"
MIN_VOICE_ZOOM_LEVEL = 0
MAX_VOICE_ZOOM_LEVEL = 2

# DTS Dialog Control (GetCapabilities fallback: min 0, max 6, span 1)
MIN_DTS_DIALOG_CONTROL = 0
MAX_DTS_DIALOG_CONTROL = 6

# Input options (API values used as translation keys)
INPUT_OPTIONS: list[str] = ["tv", "hdmi1", "spotify", "bluetooth", "airplay2"]

# Bass level options for non-subwoofer mode (API value -> int)
BASS_LEVEL_OPTIONS: dict[str, int] = {"min": 0, "mid": 1, "max": 2}
BASS_LEVEL_VALUES_TO_OPTIONS: dict[int, str] = {
    v: k for k, v in BASS_LEVEL_OPTIONS.items()
}

# DRC options (API values used as translation keys)
DRC_OPTIONS: list[str] = ["auto", "on", "off"]

# HDMI Passthrough options (API values used as translation keys)
HDMI_PASSTHROUGH_OPTIONS: list[str] = ["auto", "on", "off"]

# Dual Mono options (API values used as translation keys)
DUAL_MONO_OPTIONS: list[str] = ["main", "sub", "main_sub"]

# Bluetooth Connection Quality options (API values used as translation keys)
BT_CONNECTION_QUALITY_OPTIONS: list[str] = ["prioritysound", "priorityconnection"]

# HDMI Standby Link options (API values used as translation keys)
HDMI_STANDBY_LINK_OPTIONS: list[str] = ["auto", "on", "off"]

# CEC power-off sync options (API values used as translation keys)
CEC_POWER_OFF_SYNC_OPTIONS: list[str] = ["auto", "on", "off"]

# Display brightness options (API translation keys; live HT-A9M2 2026-07-08)
DIMMER_OPTIONS: list[str] = ["bright", "dark", "off"]

# HDMI Signal Format options (API values used as translation keys)
HDMI_SIGNAL_FORMAT_OPTIONS: list[str] = [
    "standard",
    "enhanced",
    "enhanced_4k120_8k",
]

# Audio Return Channel options (API values used as translation keys)
AUDIO_RETURN_CHANNEL_OPTIONS: list[str] = ["off", "arc", "earc"]

# gRPC sound effect modes (BRAVIA Connect UI "Sound Field" selection)
SOUND_EFFECT_DEVICE_TO_HA: dict[str, str] = {
    "Dolby Speaker Virtualizer": "dolby_speaker_virtualizer",
    "Neural:X": "neural_x",
    "360SSM": "ssm_360",
}
SOUND_EFFECT_HA_TO_DEVICE: dict[str, str] = {
    ha: device for device, ha in SOUND_EFFECT_DEVICE_TO_HA.items()
}
SOUND_EFFECT_OPTIONS: list[str] = list(SOUND_EFFECT_HA_TO_DEVICE.keys())

# gRPC 360SSM height (speaker_sound_setting.360ssm_height)
SSM360_HEIGHT_OPTIONS: list[str] = ["high", "mid", "low"]

# Capability-gated (e.g. HT-A8): stereo playback / subwoofer phase
# Dual-sub phase device enums use commas; HA translation keys must be [a-z0-9-_]+.
STEREO_PLAYBACK_OPTIONS: list[str] = ["up_mix", "multi_stereo"]
SW_PHASE_DEVICE_TO_HA: dict[str, str] = {
    "0": "0",
    "180": "180",
    "0,0": "0_0",
    "180,180": "180_180",
    "0,180": "0_180",
    "180,0": "180_0",
}
SW_PHASE_HA_TO_DEVICE: dict[str, str] = {
    ha: device for device, ha in SW_PHASE_DEVICE_TO_HA.items()
}
SW_PHASE_OPTIONS: list[str] = list(SW_PHASE_HA_TO_DEVICE.keys())

# AV Sync limits (milliseconds)
MAX_AV_SYNC = 300
MIN_AV_SYNC = 0
AV_SYNC_STEP = 25

# Model ID to friendly name fallback (used when HTTP/zeroconf unavailable)
MODEL_ID_TO_NAME: dict[str, str] = {
    "HT-A9M2": "BRAVIA Theatre Quad",
}
