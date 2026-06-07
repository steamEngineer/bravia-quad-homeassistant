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
FEATURE_MAC_ADDRESS = "network.macaddress"
FEATURE_SERIAL_NUMBER = "system.serialnumber"
FEATURE_FIRMWARE_VERSION = "system.version"
FEATURE_MODEL_TYPE = "system.modeltype"
FEATURE_MANUFACTURER = "system.manufacturer"
FEATURE_DEVICE_NAME = "system.devicename"

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

# Input options (API values used as translation keys)
INPUT_OPTIONS: list[str] = ["tv", "hdmi1", "spotify", "bluetooth", "airplay2"]

# Bass level options for non-subwoofer mode (API value -> int)
BASS_LEVEL_OPTIONS: dict[str, int] = {"min": 0, "mid": 1, "max": 2}

# DRC options (API values used as translation keys)
DRC_OPTIONS: list[str] = ["auto", "on", "off"]

# Model ID to friendly name fallback (used when HTTP/zeroconf unavailable)
MODEL_ID_TO_NAME: dict[str, str] = {
    "HT-A9M2": "BRAVIA Theatre Quad",
}
