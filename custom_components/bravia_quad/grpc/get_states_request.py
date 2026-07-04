"""Build GetStatesWithAuth request bytes (wire format differs from .proto)."""

from __future__ import annotations

from pathlib import Path

_FIELD_PATHS_FILE = Path(__file__).with_name("all_field_paths.txt")


def encode_varint(value: int) -> bytes:
    """Encode an unsigned integer as a protobuf varint."""
    out = bytearray()
    while value > 0x7F:
        out.append((value & 0x7F) | 0x80)
        value >>= 7
    out.append(value)
    return bytes(out)


def encode_signed_varint(value: int) -> bytes:
    """Encode int32/int64 as protobuf varint (sign-extended when negative)."""
    if value < 0:
        value &= (1 << 64) - 1
    out = bytearray()
    while True:
        bits = value & 0x7F
        value >>= 7
        if value:
            out.append(bits | 0x80)
        else:
            out.append(bits)
            break
    return bytes(out)


def load_field_paths(path: Path | None = None) -> list[str]:
    """Load gRPC field paths from ``all_field_paths.txt``."""
    field_paths_file = path or _FIELD_PATHS_FILE
    field_paths: list[str] = []
    with field_paths_file.open(encoding="utf-8") as handle:
        in_list = False
        for line in handle:
            stripped = line.strip()
            if "ALL_FIELD_PATHS = [" in stripped:
                in_list = True
                continue
            if not in_list:
                continue
            if stripped == "]":
                break
            if stripped.startswith('"') and stripped.endswith('",'):
                field_paths.append(stripped[1:-2])
            elif stripped.startswith('"') and stripped.endswith('"'):
                field_paths.append(stripped[1:-1])
                break
    if not field_paths:
        msg = f"No field paths found in {field_paths_file}"
        raise ValueError(msg)
    return field_paths


def build_get_states_with_auth_request(
    field_paths: list[str],
    *,
    session_random: bytes,
    session_id: str,
    auth_token: bytes,
) -> bytes:
    """
    Return serialized GetStatesWithAuth request matching BRAVIA Connect captures.

    Top-level layout (6558 bytes with 177 paths on fw 001.454):
      field 1 (6521 B): nested path list + embedded session block (field 2 / 0x12)
      field 2 (34 B): auth_token (32 B HMAC-SHA256)
    """
    if len(session_random) != 8:
        msg = f"session_random must be 8 bytes, got {len(session_random)}"
        raise ValueError(msg)
    if len(auth_token) != 32:
        msg = f"auth_token must be 32 bytes, got {len(auth_token)}"
        raise ValueError(msg)

    inner_parts = b""
    for path in field_paths:
        path_bytes = path.encode("utf-8")
        inner_parts += b"\x0a" + encode_varint(len(path_bytes)) + path_bytes

    nested_field = b"\x0a" + encode_varint(len(inner_parts)) + inner_parts

    session_id_bytes = session_id.encode("utf-8")
    embedded_data = (
        b"\x0a\x08"
        + session_random
        + b"\x1a"
        + encode_varint(len(session_id_bytes))
        + session_id_bytes
    )
    embedded_field = b"\x12" + encode_varint(len(embedded_data)) + embedded_data

    field1_content = nested_field + embedded_field
    field_list_bytes = b"\x0a" + encode_varint(len(field1_content)) + field1_content
    auth_token_bytes = b"\x12" + encode_varint(len(auth_token)) + auth_token
    return field_list_bytes + auth_token_bytes


def build_small_get_states_with_auth_request(
    field_path: str,
    *,
    session_random: bytes,
    session_id: str,
    auth_token: bytes,
) -> bytes:
    """
    Return a single-path GetStatesWithAuth request (app mutex preflight).

    Used before ExecCommandWithAuth to obtain a rolling ``auth_token`` for the
    command body. Layout matches Frida capture for ``client_control.mutex.any``.
    """
    if len(session_random) != 8:
        msg = f"session_random must be 8 bytes, got {len(session_random)}"
        raise ValueError(msg)
    if len(auth_token) != 32:
        msg = f"auth_token must be 32 bytes, got {len(auth_token)}"
        raise ValueError(msg)

    path_bytes = field_path.encode("utf-8")
    depth2 = b"\x0a" + encode_varint(len(path_bytes)) + path_bytes
    depth1 = b"\x0a" + encode_varint(len(depth2)) + depth2

    session_id_bytes = session_id.encode("utf-8")
    embedded_data = (
        b"\x0a\x08"
        + session_random
        + b"\x1a"
        + encode_varint(len(session_id_bytes))
        + session_id_bytes
    )
    embedded_field = b"\x12" + encode_varint(len(embedded_data)) + embedded_data

    inner = depth1 + embedded_field
    field_list_bytes = b"\x0a" + encode_varint(len(inner)) + inner
    auth_token_bytes = b"\x12" + encode_varint(len(auth_token)) + auth_token
    return field_list_bytes + auth_token_bytes


def extract_auth_token_from_states_response(raw: bytes) -> bytes | None:
    """Return trailing 32-byte auth token from a GetStatesWithAuth response body."""
    marker = b"\x12\x20"
    idx = raw.rfind(marker)
    if idx < 0 or idx + 34 > len(raw):
        return None
    return raw[idx + 2 : idx + 34]
