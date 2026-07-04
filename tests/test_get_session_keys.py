"""Unit tests for Sony Seeds OAuth helpers."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "grpc"))

from get_session_keys import (  # noqa: E402
    build_credentials_bundle,
    extract_ssh_app_redirect_from_har,
    parse_authorization_code,
)

SSH_APP = "ssh-app://signin?code=abc123&state=state456"


def test_parse_authorization_code_from_ssh_app() -> None:
    assert parse_authorization_code(SSH_APP) == "abc123"
    assert parse_authorization_code("raw-code") == "raw-code"


def test_extract_ssh_app_redirect_from_har(tmp_path: Path) -> None:
    har = {
        "log": {
            "entries": [
                {
                    "request": {"url": "https://example.com/"},
                    "response": {"headers": [{"name": "Location", "value": SSH_APP}]},
                }
            ]
        }
    }
    path = tmp_path / "capture.har"
    path.write_text(json.dumps(har), encoding="utf-8")
    assert extract_ssh_app_redirect_from_har(path) == SSH_APP


def test_extract_ssh_app_redirect_from_har_missing(tmp_path: Path) -> None:
    har = {"log": {"entries": []}}
    path = tmp_path / "empty.har"
    path.write_text(json.dumps(har), encoding="utf-8")
    with pytest.raises(ValueError, match="No ssh-app://"):
        extract_ssh_app_redirect_from_har(path)


def test_build_credentials_bundle_preserves_refresh_token() -> None:
    session_keys = {
        "device_id": "dev",
        "key_id": "kid",
        "session_key": "sk",
        "hmac_key": "hk",
        "expires_in": 86400,
    }
    token_response = {"access_token": "at-new", "expires_in": 3600}
    previous = {"refresh_token": "rt-old"}
    bundle = build_credentials_bundle(session_keys, token_response, previous=previous)
    assert bundle["access_token"] == "at-new"
    assert bundle["refresh_token"] == "rt-old"
    assert bundle["session_key"] == "sk"
    assert "session_keys_expires_at" in bundle
    assert "access_token_expires_at" in bundle
