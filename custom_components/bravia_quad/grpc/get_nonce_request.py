"""Build GetNonce request bytes (proto-shaped; matches live Quad)."""

from __future__ import annotations

from .get_states_request import encode_varint


def build_get_nonce_request(session_id: str) -> bytes:
    """Return serialized GetNonce request: field 1 = session_id string."""
    sid = session_id.encode("utf-8")
    return b"\x0a" + encode_varint(len(sid)) + sid


def parse_get_nonce_response(raw: bytes) -> tuple[bytes, bytes] | None:
    """
    Parse GetNonce response: field 1 = 8-byte nonce, field 2 = 32-byte HMAC/token.

    Same top-level layout as GetSessionRandom on fw 001.454.
    """
    if len(raw) < 44:
        return None
    if raw[0:2] != b"\x0a\x08":
        return None
    nonce = raw[2:10]
    if raw[10:12] != b"\x12\x20":
        return None
    token = raw[12:44]
    if len(nonce) != 8 or len(token) != 32:
        return None
    return nonce, token
