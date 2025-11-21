"""Constants for the Bravia Quad integration."""
from __future__ import annotations

DOMAIN = "bravia_quad"

# Default port for Bravia Quad TCP communication
DEFAULT_PORT = 33336

# Timeout for TCP operations
TCP_TIMEOUT = 10

# Command IDs
CMD_ID_POWER = 3
CMD_ID_VOLUME = 2
CMD_ID_INPUT = 2

# Features
FEATURE_POWER = "main.power"
FEATURE_VOLUME = "main.volumestep"
FEATURE_INPUT = "main.input"

# Power states
POWER_ON = "on"
POWER_OFF = "off"

# Input options mapping (display name -> value)
INPUT_OPTIONS = {
    "TV (eARC)": "tv",
    "HDMI In": "hdmi1",
    "Spotify": "spotify",
}

# Reverse mapping (value -> display name)
INPUT_VALUES_TO_OPTIONS = {v: k for k, v in INPUT_OPTIONS.items()}

