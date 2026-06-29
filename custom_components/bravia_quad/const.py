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

# Input options (API values used as translation keys)
INPUT_OPTIONS: list[str] = ["tv", "hdmi1", "spotify", "bluetooth", "airplay2"]

# Bass level options for non-subwoofer mode (API value -> int)
BASS_LEVEL_OPTIONS: dict[str, int] = {"min": 0, "mid": 1, "max": 2}

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

# Audio Return Channel options (API values used as translation keys)
AUDIO_RETURN_CHANNEL_OPTIONS: list[str] = ["off", "arc", "earc"]

# AV Sync limits (milliseconds)
MAX_AV_SYNC = 300
MIN_AV_SYNC = 0

# Model ID to friendly name fallback (used when HTTP/zeroconf unavailable)
MODEL_ID_TO_NAME: dict[str, str] = {
    "HT-A9M2": "BRAVIA Theatre Quad",
}
