"""Tests for ExecCommandWithAuth wire encoding."""

from __future__ import annotations

import binascii

import pytest

from custom_components.bravia_quad.grpc.exec_command_request import (
    build_exec_command_signing_preimage,
    build_exec_command_with_auth_request,
    legacy_value_to_kwargs,
    parse_exec_response,
    sign_exec_auth_token,
)

VOLUME_CAPTURE_HEX = (
    "0a680a440a100a0e0a06766f6c756d6510012202083c12300a0892f127335ad9a5171"
    "a2465336330666232372d613133612d343934632d623734342d383834356230336439666632"
    "122035006fd9f72a88a35ea7caf42fb03e6b35763dbca013e1cc83faad0902a1ec77"
)
VOLUME_SESSION_RANDOM = bytes.fromhex("92f127335ad9a517")
VOLUME_SESSION_ID = "e3c0fb27-a13a-494c-b744-8845b03d9ff2"
VOLUME_AUTH_TOKEN = bytes.fromhex(
    "35006fd9f72a88a35ea7caf42fb03e6b35763dbca013e1cc83faad0902a1ec77"
)

NIGHT_CAPTURE_HEX = (
    "0a7a0a560a220a200a18736f756e645f73657474696e672e6e696768745f6d6f646510"
    "012a02080112300a08db866bae293bf69a1a2436363234643030642d343835312d343531"
    "342d383931332d6162306232326132643535381220a6d29ff1dafdd6ab9b6eaca557a453"
    "34313948e8e0ab287f58e85977ca71462e"
)
NIGHT_SESSION_RANDOM = bytes.fromhex("db866bae293bf69a")
NIGHT_SESSION_ID = "6624d00d-4851-4514-8913-ab0b22a2d558"
NIGHT_AUTH_TOKEN = bytes.fromhex(
    "a6d29ff1dafdd6ab9b6eaca557a45334313948e8e0ab287f58e85977ca71462e"
)

BASS_CAPTURE_HEX = (
    "0a7e0a5a0a260a240a19736f756e645f73657474696e672e766f6c756d652e6261737310"
    "0132050a036d617812300a08db866bae293bf69a1a2436363234643030642d343835312d"
    "343531342d383931332d61623062323261326435353812202f84ce6488e22205de25162f4"
    "11766fa590e3ae964b8942e7b32191cf724b158"
)
BASS_SESSION_RANDOM = NIGHT_SESSION_RANDOM
BASS_SESSION_ID = NIGHT_SESSION_ID
BASS_AUTH_TOKEN = bytes.fromhex(
    "2f84ce6488e22205de25162f411766fa590e3ae964b8942e7b32191cf724b158"
)

NEURAL_CAPTURE_HEX = (
    "0a84010a600a2c0a2a0a1a736f756e645f73657474696e672e736f756e645f6566666563"
    "741001320a0a084e657572616c3a5812300a087af2777ca8bdfbe71a2466356164366662"
    "352d303134322d346666342d616164342d38666331633035666138633912205b8700bc6e"
    "f3a414a0c65805412773840a2ee7773fd8bd97a0cf12aed3cf478e"
)
NEURAL_SESSION_RANDOM = bytes.fromhex("7af2777ca8bdfbe7")
NEURAL_SESSION_ID = "f5ad6fb5-0142-4ff4-aad4-8fc1c05fa8c9"
NEURAL_AUTH_TOKEN = bytes.fromhex(
    "5b8700bc6ef3a414a0c65805412773840a2ee7773fd8bd97a0cf12aed3cf478e"
)

# Frida hmacApplyMac capture (device fw 3.9.1, volume=56) — key is Sony Seeds hmac_key
HMAC_KEY = "b5c224e9a0f21f6c8b45aedcfc7dd9be345961086c68fec87a81ee243af1e5f9"
HMAC_SESSION_RANDOM = bytes.fromhex("5f3ff23bce69a1f9")
HMAC_SESSION_ID = "15571bf1-3c73-4777-8d1b-f8664f04b315"
HMAC_PREIMAGE_HEX = (
    "0a100a0e0a06766f6c756d6510012202083812300a085f3ff23bce69a1f91a243135353731"
    "6266312d336337332d343737372d386431622d663836363466303462333135"
)
HMAC_AUTH_TOKEN = bytes.fromhex(
    "1ec4668e5a390ccf2d5b268445172002def69f73cfe68946d17082cb92f45ba6"
)


@pytest.mark.parametrize(
    (
        "capture_hex",
        "command_path",
        "kwargs",
        "session_random",
        "session_id",
        "auth_token",
    ),
    [
        (
            VOLUME_CAPTURE_HEX,
            "volume",
            {"int_value": 60},
            VOLUME_SESSION_RANDOM,
            VOLUME_SESSION_ID,
            VOLUME_AUTH_TOKEN,
        ),
        (
            NIGHT_CAPTURE_HEX,
            "sound_setting.night_mode",
            {"bool_value": True},
            NIGHT_SESSION_RANDOM,
            NIGHT_SESSION_ID,
            NIGHT_AUTH_TOKEN,
        ),
        (
            BASS_CAPTURE_HEX,
            "sound_setting.volume.bass",
            {"string_value": "max"},
            BASS_SESSION_RANDOM,
            BASS_SESSION_ID,
            BASS_AUTH_TOKEN,
        ),
        (
            NEURAL_CAPTURE_HEX,
            "sound_setting.sound_effect",
            {"string_value": "Neural:X"},
            NEURAL_SESSION_RANDOM,
            NEURAL_SESSION_ID,
            NEURAL_AUTH_TOKEN,
        ),
    ],
)
def test_build_matches_frida_capture(
    capture_hex: str,
    command_path: str,
    kwargs: dict,
    session_random: bytes,
    session_id: str,
    auth_token: bytes,
) -> None:
    capture = binascii.unhexlify(capture_hex)
    built = build_exec_command_with_auth_request(
        command_path,
        session_random=session_random,
        session_id=session_id,
        auth_token=auth_token,
        **kwargs,
    )
    assert built == capture


def test_parse_exec_response_success() -> None:
    assert parse_exec_response(b"\x08\x01") is True
    assert parse_exec_response(b"\x08\x00") is False


def test_legacy_value_to_kwargs_bool_path() -> None:
    assert legacy_value_to_kwargs("sound_setting.night_mode", 1) == {"bool_value": True}


def test_legacy_value_to_kwargs_int_path() -> None:
    assert legacy_value_to_kwargs("volume", 60) == {"int_value": 60}


def test_build_rejects_multiple_values() -> None:
    with pytest.raises(ValueError, match="exactly one"):
        build_exec_command_with_auth_request(
            "volume",
            session_random=VOLUME_SESSION_RANDOM,
            session_id=VOLUME_SESSION_ID,
            auth_token=VOLUME_AUTH_TOKEN,
            int_value=60,
            bool_value=True,
        )


def test_build_rejects_missing_value() -> None:
    with pytest.raises(ValueError, match="exactly one"):
        build_exec_command_with_auth_request(
            "volume",
            session_random=VOLUME_SESSION_RANDOM,
            session_id=VOLUME_SESSION_ID,
            auth_token=VOLUME_AUTH_TOKEN,
        )


def test_build_rejects_bad_auth_token_length() -> None:
    with pytest.raises(ValueError, match="auth_token must be 32 bytes"):
        build_exec_command_with_auth_request(
            "volume",
            session_random=VOLUME_SESSION_RANDOM,
            session_id=VOLUME_SESSION_ID,
            auth_token=b"\x00" * 16,
            int_value=60,
        )


def test_signing_preimage_matches_cmd_block_inner() -> None:
    preimage = build_exec_command_signing_preimage(
        "volume",
        session_random=VOLUME_SESSION_RANDOM,
        session_id=VOLUME_SESSION_ID,
        int_value=60,
    )
    capture = binascii.unhexlify(VOLUME_CAPTURE_HEX)
    # Outer field 1 cmd_block: tag 0x0a, len 0x44, then 68-byte inner preimage.
    assert capture[2:4] == b"\x0a\x44"
    assert preimage == capture[4:72]


def test_sign_exec_auth_token_matches_frida_capture() -> None:
    preimage = build_exec_command_signing_preimage(
        "volume",
        session_random=HMAC_SESSION_RANDOM,
        session_id=HMAC_SESSION_ID,
        int_value=56,
    )
    assert preimage.hex() == HMAC_PREIMAGE_HEX
    signed = sign_exec_auth_token(
        HMAC_KEY,
        "volume",
        session_random=HMAC_SESSION_RANDOM,
        session_id=HMAC_SESSION_ID,
        int_value=56,
    )
    assert signed == HMAC_AUTH_TOKEN
    wire = build_exec_command_with_auth_request(
        "volume",
        session_random=HMAC_SESSION_RANDOM,
        session_id=HMAC_SESSION_ID,
        auth_token=signed,
        int_value=56,
    )
    assert wire.endswith(HMAC_AUTH_TOKEN)
    assert wire[4:72] == preimage


def test_cache_exec_value_updates_notify_state() -> None:
    from custom_components.bravia_quad.grpc.client import BraviaGrpcClient

    client = BraviaGrpcClient("127.0.0.1")
    client._cache_exec_value(
        "sound_setting.sound_effect",
        {"string_value": "Neural:X"},
    )
    assert client.notify_state["sound_setting.sound_effect"] == "Neural:X"
