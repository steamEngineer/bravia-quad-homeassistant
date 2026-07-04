"""Tests for GetStatesWithAuth HMAC signing helpers."""

from __future__ import annotations

import binascii
import hashlib
import hmac as hmac_mod
from pathlib import Path

import pytest

from custom_components.bravia_quad.grpc.get_states_auth import (
    build_get_states_signing_preimage,
    build_mutex_signing_preimage,
    extract_signing_preimage,
    sign_get_states_auth_token,
    sign_get_states_request_body,
)
from custom_components.bravia_quad.grpc.get_states_request import (
    build_get_states_with_auth_request,
    build_small_get_states_with_auth_request,
    load_field_paths,
)

HMAC_KEY = "d6e0edbb98b3442a1fb244dd05e69cb156c0b0ae68808844297f5c642368eb6a"
SESSION_RANDOM = bytes.fromhex("7af2777ca8bdfbe7")
SESSION_ID = "f5ad6fb5-0142-4ff4-aad4-8fc1c05fa8c9"

# Frida blutter capture 2026-07-02 (getstates-20260702-225446.log)
CAPTURE_HMAC_KEY = "a27ad33a7a06d183b5c412d4f1d08a36e8f17765877982df79ee066a60eb97ff"
CAPTURE_SESSION_RANDOM = bytes.fromhex("e072a043c7f7c5ef")
CAPTURE_SESSION_ID = "1531cdf4-aad1-4a09-a17a-c6a9c46e84cf"
CAPTURE_MUTEX_PREIMAGE = bytes.fromhex(
    "0a1a0a18636c69656e745f636f6e74726f6c2e6d757465782e616e79"
    "12300a08e072a043c7f7c5ef1a2431353331636466342d616164312d346130392d613137612d"
    "633661396334366538346366"
)
CAPTURE_MUTEX_AUTH = bytes.fromhex(
    "cce33185bbf2b9e61fc05a7f06fae9cdf2444df2c76428802b642bfb64ac8aee"
)
CAPTURE_FULL_AUTH = bytes.fromhex(
    "35ec7b54756af2d7d283d6b3028f1bd17b535fb7b7a4fcd75ee1ae4765687964"
)
CAPTURE_DIR = Path(__file__).resolve().parents[1] / ".cache/frida"


def test_sign_get_states_auth_token_deterministic() -> None:
    preimage = b"test-preimage-bytes"
    a = sign_get_states_auth_token(HMAC_KEY, preimage)
    b = sign_get_states_auth_token(HMAC_KEY, preimage)
    assert a == b
    assert len(a) == 32


def test_mutex_preimage_matches_frida_capture() -> None:
    preimage = build_mutex_signing_preimage(
        "client_control.mutex.any",
        session_random=CAPTURE_SESSION_RANDOM,
        session_id=CAPTURE_SESSION_ID,
    )
    assert preimage == CAPTURE_MUTEX_PREIMAGE
    assert len(preimage) == 78
    digest = sign_get_states_auth_token(CAPTURE_HMAC_KEY, preimage)
    assert digest == CAPTURE_MUTEX_AUTH


def test_sign_get_states_request_body_mutex_wire() -> None:
    wire = build_small_get_states_with_auth_request(
        "client_control.mutex.any",
        session_random=CAPTURE_SESSION_RANDOM,
        session_id=CAPTURE_SESSION_ID,
        auth_token=CAPTURE_MUTEX_AUTH,
    )
    assert extract_signing_preimage(wire) == CAPTURE_MUTEX_PREIMAGE
    assert sign_get_states_request_body(CAPTURE_HMAC_KEY, wire) == CAPTURE_MUTEX_AUTH


def test_build_get_states_signing_preimage() -> None:
    path_bytes = b"\x0a\x05power"
    nested = b"\x0a" + bytes([len(path_bytes)]) + path_bytes
    preimage = build_get_states_signing_preimage(
        nested,
        session_random=SESSION_RANDOM,
        session_id=SESSION_ID,
    )
    assert SESSION_RANDOM in preimage
    assert SESSION_ID.encode() in preimage


def test_full_get_states_wire_matches_frida_capture() -> None:
    capture_path = CAPTURE_DIR / "getstates_tx_seq47.bin"
    if not capture_path.is_file() or capture_path.stat().st_size != 6558:
        pytest.skip("177-path Frida GetStates capture not available")
    app_wire = capture_path.read_bytes()
    paths = load_field_paths()
    assert len(paths) == 177
    token = sign_get_states_auth_token(
        CAPTURE_HMAC_KEY,
        extract_signing_preimage(app_wire),
    )
    assert token == CAPTURE_FULL_AUTH
    ours = build_get_states_with_auth_request(
        paths,
        session_random=CAPTURE_SESSION_RANDOM,
        session_id=CAPTURE_SESSION_ID,
        auth_token=token,
    )
    assert len(ours) == len(app_wire)
    assert ours == app_wire


def test_sign_matches_hmac_sha256() -> None:
    data = b"hello"
    expected = hmac_mod.new(binascii.unhexlify(HMAC_KEY), data, hashlib.sha256).digest()
    assert sign_get_states_auth_token(HMAC_KEY, data) == expected
