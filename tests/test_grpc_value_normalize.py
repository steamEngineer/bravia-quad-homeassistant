"""Tests for gRPC → TCP value normalization."""

from __future__ import annotations

from custom_components.bravia_quad.const import (
    FEATURE_POWER,
    FEATURE_REAR_LEVEL,
    FEATURE_VOICE_ENHANCER,
    FEATURE_VOLUME,
    MUTE_OFF,
    MUTE_ON,
    POWER_OFF,
    POWER_ON,
    VOICE_ENHANCER_OFF,
    VOICE_ENHANCER_ON,
)
from custom_components.bravia_quad.grpc_mapping import mapping_for_grpc_path
from custom_components.bravia_quad.grpc_value_normalize import (
    denormalize_for_exec,
    normalize_grpc_value,
)


def test_normalize_input_source_airplay() -> None:
    mapping = mapping_for_grpc_path("playback_control.function")
    assert mapping is not None
    assert normalize_grpc_value(mapping, "airplay") == "airplay2"
    assert normalize_grpc_value(mapping, "spotify") == "spotify"
    kind, payload = denormalize_for_exec(mapping, "airplay2")
    assert kind == "string_value"
    assert payload == "airplay"


def test_normalize_power_bool() -> None:
    mapping = mapping_for_grpc_path("power")
    assert mapping is not None
    assert normalize_grpc_value(mapping, True) == POWER_ON
    assert normalize_grpc_value(mapping, False) == POWER_OFF


def test_normalize_volume_int() -> None:
    mapping = mapping_for_grpc_path("volume")
    assert mapping is not None
    assert mapping.tcp_feature == FEATURE_VOLUME
    assert normalize_grpc_value(mapping, 34) == 34


def test_normalize_rear_signed_int() -> None:
    mapping = mapping_for_grpc_path("sound_setting.volume.rear")
    assert mapping is not None
    assert mapping.tcp_feature == FEATURE_REAR_LEVEL
    assert normalize_grpc_value(mapping, -3) == -3


def test_normalize_voice_mode_bool() -> None:
    mapping = mapping_for_grpc_path("sound_setting.voice_mode")
    assert mapping is not None
    assert mapping.tcp_feature == FEATURE_VOICE_ENHANCER
    assert normalize_grpc_value(mapping, True) == VOICE_ENHANCER_ON
    assert normalize_grpc_value(mapping, False) == VOICE_ENHANCER_OFF


def test_normalize_mute_bool() -> None:
    mapping = mapping_for_grpc_path("mute")
    assert mapping is not None
    assert normalize_grpc_value(mapping, True) == MUTE_ON
    assert normalize_grpc_value(mapping, False) == MUTE_OFF


def test_normalize_bass_string() -> None:
    mapping = mapping_for_grpc_path("sound_setting.volume.bass")
    assert mapping is not None
    assert normalize_grpc_value(mapping, "mid") == 1


def test_normalize_subwoofer_int() -> None:
    mapping = mapping_for_grpc_path("sound_setting.volume.subwoofer")
    assert mapping is not None
    assert normalize_grpc_value(mapping, "5") == 5
    assert normalize_grpc_value(mapping, -3) == -3


def test_denormalize_subwoofer_int() -> None:
    mapping = mapping_for_grpc_path("sound_setting.volume.subwoofer")
    assert mapping is not None
    kind, payload = denormalize_for_exec(mapping, 4)
    assert kind == "int_value"
    assert payload == 4
    kind, payload = denormalize_for_exec(mapping, -2)
    assert kind == "int_value"
    assert payload == -2


def test_denormalize_rear_int() -> None:
    mapping = mapping_for_grpc_path("sound_setting.volume.rear")
    assert mapping is not None
    kind, payload = denormalize_for_exec(mapping, -3)
    assert kind == "int_value"
    assert payload == -3


def test_exec_rear_negative_signed_varint_preimage() -> None:
    """Rear/sub exec uses int wire with sign-extended protobuf varint."""
    from custom_components.bravia_quad.grpc.exec_command_request import (
        build_exec_command_signing_preimage,
    )
    from custom_components.bravia_quad.grpc.get_states_request import (
        encode_signed_varint,
    )

    assert encode_signed_varint(-3) == bytes.fromhex("fdffffffffffffffff01")

    preimage = build_exec_command_signing_preimage(
        "sound_setting.volume.rear",
        session_random=b"\xdb\x86\x6b\xae\x29\x3b\xf6\x9a",
        session_id="6624d00d-4851-4514-8913-ab0b22a2d558",
        int_value=-3,
    )
    assert bytes.fromhex("fdffffffffffffffff01") in preimage


def test_sound_effect_mapping_is_grpc_only() -> None:
    mapping = mapping_for_grpc_path("sound_setting.sound_effect")
    assert mapping is not None
    assert mapping.tcp_feature is None
    assert mapping.ha_platform == "select"


def test_skip_availability_paths() -> None:
    mapping = mapping_for_grpc_path("sound_setting.sound_field")
    assert mapping is not None
    fake = type(
        "M",
        (),
        {
            "grpc_path": "sound_setting.sound_field.availability",
            "tcp_feature": FEATURE_POWER,
        },
    )()
    assert normalize_grpc_value(fake, True) is None


def test_bt_quality_value_map() -> None:
    mapping = mapping_for_grpc_path("bluetooth_setting.connection_quality")
    assert mapping is not None
    assert normalize_grpc_value(mapping, "sound_quality") == "prioritysound"
    kind, payload = denormalize_for_exec(mapping, "priorityconnection")
    assert kind == "string_value"
    assert payload == "stable_connection"


def test_earc_bool_normalizes_to_select_option() -> None:
    mapping = mapping_for_grpc_path("system_setting.earc")
    assert mapping is not None
    assert normalize_grpc_value(mapping, True) == "earc"
    assert normalize_grpc_value(mapping, False) == "off"


def test_volume_denormalize_uses_int_value() -> None:
    mapping = mapping_for_grpc_path("volume")
    assert mapping is not None
    kind, payload = denormalize_for_exec(mapping, 42)
    assert kind == "int_value"
    assert payload == 42


def test_normalize_grpc_only_bool_path() -> None:
    mapping = mapping_for_grpc_path("sound_setting.dsee_ultimate")
    assert mapping is not None
    assert normalize_grpc_value(mapping, True) is True
    assert normalize_grpc_value(mapping, "upon") is True


def test_normalize_raee_measured() -> None:
    mapping = mapping_for_grpc_path("sound_optimization.raee.is_measured")
    assert mapping is not None
    assert normalize_grpc_value(mapping, True) == "true"
    assert normalize_grpc_value(mapping, '{"a":1}') == '{"a": 1}'


def test_tcp_seed_denormalize_drc() -> None:
    mapping = mapping_for_grpc_path("sound_setting.drc")
    assert mapping is not None
    _, value = denormalize_for_exec(mapping, "auto")
    assert value == "auto"


def test_tcp_seed_denormalize_aav_bool() -> None:
    mapping = mapping_for_grpc_path("sound_setting.auto_volume")
    assert mapping is not None
    _, on_val = denormalize_for_exec(mapping, "on")
    _, off_val = denormalize_for_exec(mapping, "off")
    assert on_val is True
    assert off_val is False


def test_tcp_seed_denormalize_earc() -> None:
    mapping = mapping_for_grpc_path("system_setting.earc")
    assert mapping is not None
    _, value = denormalize_for_exec(mapping, "earc")
    assert value == "earc"
