"""HA-facing notify helpers (not Connect wire protocol)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class NotifyStateUpdate:
    """Single field delta from StartNotifyStates."""

    path: str
    value: Any


def load_keys_from_file(file_path: str) -> dict[str, str]:
    """
    Load authentication keys from a JSON file.

    Args:
        file_path: Path to JSON file containing keys

    Returns:
        Dictionary with keys: device_id, key_id, session_key, hmac_key, expires_in

    Raises:
        FileNotFoundError: If file doesn't exist
        ValueError: If file format is invalid

    """
    path = Path(file_path)
    if not path.exists():
        msg = f"Keys file not found: {file_path}"
        raise FileNotFoundError(msg)

    with path.open(encoding="utf-8") as f:
        data = json.load(f)

    # Validate required fields
    required_fields = ["session_key", "hmac_key"]
    missing_fields = [field for field in required_fields if field not in data]
    if missing_fields:
        msg = f"Missing required fields in keys file: {', '.join(missing_fields)}"
        raise ValueError(msg)

    return {
        "device_id": data.get("device_id"),
        "key_id": data.get("key_id"),
        "session_key": data["session_key"],
        "hmac_key": data["hmac_key"],
        "auth_data": data.get(
            "auth_data"
        ),  # Optional auth_data field for ConfirmSignin
        "expires_in": data.get("expires_in", 86400),
    }
