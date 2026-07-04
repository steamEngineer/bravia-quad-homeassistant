"""Tests for GetStatesWithAuth wire encoding."""

import binascii
from pathlib import Path

import pytest

from custom_components.bravia_quad.grpc.get_states_request import (
    build_get_states_with_auth_request,
    build_small_get_states_with_auth_request,
    encode_varint,
    load_field_paths,
)

CAPTURE_PATH = (
    Path(__file__).resolve().parents[1] / ".cache/frida/getstates_tx_seq47.bin"
)
CAPTURE_BULK_LEN = 6558
CAPTURE_SESSION_RANDOM = bytes.fromhex("e072a043c7f7c5ef")
CAPTURE_SESSION_ID = "1531cdf4-aad1-4a09-a17a-c6a9c46e84cf"
CAPTURE_AUTH_TOKEN = bytes.fromhex(
    "35ec7b54756af2d7d283d6b3028f1bd17b535fb7b7a4fcd75ee1ae4765687964"
)


def test_encode_varint() -> None:
    assert encode_varint(0) == b"\x00"
    assert encode_varint(127) == b"\x7f"
    assert encode_varint(128) == b"\x80\x01"


def test_load_field_paths_count() -> None:
    paths = load_field_paths()
    assert len(paths) == 177
    assert paths[0] == "bluetooth_setting.connection_quality"


@pytest.mark.skipif(
    not CAPTURE_PATH.is_file() or CAPTURE_PATH.stat().st_size != CAPTURE_BULK_LEN,
    reason="177-path Frida GetStates capture not available",
)
def test_build_matches_capture_static_section() -> None:
    paths = load_field_paths()
    built = build_get_states_with_auth_request(
        paths,
        session_random=CAPTURE_SESSION_RANDOM,
        session_id=CAPTURE_SESSION_ID,
        auth_token=CAPTURE_AUTH_TOKEN,
    )
    capture = CAPTURE_PATH.read_bytes()
    assert len(built) == len(capture) == 6558
    assert built == capture


def test_build_static_prefix_matches_capture() -> None:
    if not CAPTURE_PATH.is_file() or CAPTURE_PATH.stat().st_size != CAPTURE_BULK_LEN:
        pytest.skip("177-path Frida GetStates capture not available")
    paths = load_field_paths()
    built = build_get_states_with_auth_request(
        paths,
        session_random=CAPTURE_SESSION_RANDOM,
        session_id=CAPTURE_SESSION_ID,
        auth_token=CAPTURE_AUTH_TOKEN,
    )
    capture = CAPTURE_PATH.read_bytes()
    # Field paths (6473 bytes) are session-independent.
    assert built[:6473] == capture[:6473]


SMALL_CAPTURE_HEX = (
    "0a4e0a1a0a18636c69656e745f636f6e74726f6c2e6d757465782e616e7912300a08"
    "7af2777ca8bdfbe71a2466356164366662352d303134322d346666342d616164342d"
    "3866633163303566613863391220f2a2c319441b632413147c1daf6ff87ea6b05ece"
    "a0a003eb29357d925106b86d"
)
SMALL_SESSION_RANDOM = bytes.fromhex("7af2777ca8bdfbe7")
SMALL_SESSION_ID = "f5ad6fb5-0142-4ff4-aad4-8fc1c05fa8c9"
SMALL_AUTH_TOKEN = bytes.fromhex(
    "f2a2c319441b632413147c1daf6ff87ea6b05ecea0a003eb29357d925106b86d"
)


def test_build_small_get_states_matches_frida_capture() -> None:
    capture = binascii.unhexlify(SMALL_CAPTURE_HEX)
    built = build_small_get_states_with_auth_request(
        "client_control.mutex.any",
        session_random=SMALL_SESSION_RANDOM,
        session_id=SMALL_SESSION_ID,
        auth_token=SMALL_AUTH_TOKEN,
    )
    assert built == capture
