"""Tests for GetNonce wire encoding."""

from __future__ import annotations

from custom_components.bravia_quad.grpc.get_nonce_request import (
    build_get_nonce_request,
    parse_get_nonce_response,
)

SESSION_ID = "32c23a22-5dae-4e79-8d4f-337079c56064"
NONCE_RESP = bytes.fromhex(
    "0a081c270da607cd392212207b2552045abc95fd9caaf1331e1ad23047f82db9c9b35dc171ff986cc473c4a6"
)


def test_build_get_nonce_request() -> None:
    req = build_get_nonce_request(SESSION_ID)
    assert req.startswith(b"\x0a")
    assert SESSION_ID.encode() in req


def test_parse_get_nonce_response() -> None:
    parsed = parse_get_nonce_response(NONCE_RESP)
    assert parsed is not None
    nonce, token = parsed
    assert len(nonce) == 8
    assert len(token) == 32
    assert nonce.hex() == "1c270da607cd3922"
    assert (
        token.hex()
        == "7b2552045abc95fd9caaf1331e1ad23047f82db9c9b35dc171ff986cc473c4a6"
    )
