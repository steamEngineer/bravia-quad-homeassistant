"""Tests for mapping-driven gRPC entities (TCP parity)."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.components.number import NumberMode
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, State
from homeassistant.helpers.restore_state import StoredState, async_get

from custom_components.bravia_quad.const import (
    DOMAIN,
    FEATURE_AAV,
    FEATURE_DRC,
)
from custom_components.bravia_quad.grpc_entity_registry import (
    entity_spec_for_mapping,
    entity_spec_for_path,
)
from custom_components.bravia_quad.grpc_mapped_entities import (
    BraviaGrpcBassLevelSelect,
    BraviaGrpcMappedSelect,
    BraviaGrpcMappedSwitch,
    mapped_number_entities,
    mapped_select_entities,
    mapped_sensor_entities,
    mapped_switch_entities,
)
from custom_components.bravia_quad.grpc_mapping import (
    mapping_for_grpc_path,
    mappings_for_platform,
)
from custom_components.bravia_quad.grpc_value_normalize import (
    denormalize_for_exec,
    grpc_exec_unavailable_reason,
    normalize_grpc_value,
)


def test_drc_maps_to_sound_setting_drc() -> None:
    mapping = mapping_for_grpc_path("sound_setting.drc")
    assert mapping is not None
    assert mapping.tcp_feature == FEATURE_DRC
    assert mapping.ha_platform == "select"


def test_aav_maps_to_auto_volume_not_tv_audio() -> None:
    mapping = mapping_for_grpc_path("sound_setting.auto_volume")
    assert mapping is not None
    assert mapping.tcp_feature == FEATURE_AAV
    assert mapping_for_grpc_path("system_setting.tv_audio") is None


def test_drc_denormalize_round_trip() -> None:
    mapping = mapping_for_grpc_path("sound_setting.drc")
    assert mapping is not None
    kind, payload = denormalize_for_exec(mapping, "auto")
    assert kind == "string_value"
    assert payload == "auto"
    assert normalize_grpc_value(mapping, payload) == "auto"


def test_cec_power_off_sync_mapping_and_options() -> None:
    from custom_components.bravia_quad.grpc_value_normalize import (
        ha_options_for_mapping,
    )

    mapping = mapping_for_grpc_path("system_setting.cec_power_off_sync")
    assert mapping is not None
    assert mapping.ha_platform == "select"
    assert mapping.verified is True
    assert ha_options_for_mapping(mapping) == ["auto", "on", "off"]
    kind, payload = denormalize_for_exec(mapping, "auto")
    assert kind == "string_value"
    assert payload == "auto"
    assert normalize_grpc_value(mapping, payload) == "auto"


def test_cec_power_off_sync_in_mapped_select_entities(
    grpc_client: MagicMock, grpc_entry: MagicMock
) -> None:
    select_paths = {
        e._grpc_path for e in mapped_select_entities(grpc_client, grpc_entry)
    }
    assert "system_setting.cec_power_off_sync" in select_paths


def test_dimmer_mapping_options_and_exec() -> None:
    from custom_components.bravia_quad.grpc_value_normalize import (
        ha_options_for_mapping,
    )

    mapping = mapping_for_grpc_path("system_setting.dimmer")
    assert mapping is not None
    assert mapping.ha_platform == "select"
    spec = entity_spec_for_mapping(mapping)
    assert spec.translation_key == "display_brightness"
    assert spec.unique_id_suffix == "display_brightness"
    assert ha_options_for_mapping(mapping) == ["bright", "dark", "off"]
    kind, payload = denormalize_for_exec(mapping, "dark")
    assert kind == "string_value"
    assert payload == "dark"
    assert normalize_grpc_value(mapping, payload) == "dark"
    kind, payload = denormalize_for_exec(mapping, "off")
    assert kind == "string_value"
    assert payload == "off"


def test_auto_volume_bool_exec() -> None:
    mapping = mapping_for_grpc_path("sound_setting.auto_volume")
    assert mapping is not None
    kind, payload = denormalize_for_exec(mapping, True)
    assert kind == "bool_value"
    assert payload is True


def test_voice_zoom_level_number_spec_and_range(
    grpc_client: MagicMock, grpc_entry: MagicMock
) -> None:
    from custom_components.bravia_quad.grpc_mapped_entities import (
        BraviaGrpcMappedNumber,
        _number_range,
    )

    mapping = mapping_for_grpc_path("sound_setting.voice_zoom")
    assert mapping is not None
    spec = entity_spec_for_mapping(mapping)
    assert spec.translation_key == "voice_zoom_level"
    assert spec.unique_id_suffix == "voice_zoom_level"
    lo, hi = _number_range(mapping)
    assert lo == 0
    assert hi == 2

    entity = BraviaGrpcMappedNumber(
        grpc_client, grpc_entry, spec, native_min_value=lo, native_max_value=hi
    )
    assert entity._attr_mode == NumberMode.SLIDER
    assert entity._attr_native_step == 1


def test_mapped_number_omit_zero_and_capability_range(
    grpc_client: MagicMock, grpc_entry: MagicMock
) -> None:
    from custom_components.bravia_quad.grpc.get_capabilities_response import (
        CapabilityMeta,
    )
    from custom_components.bravia_quad.grpc_mapped_entities import (
        BraviaGrpcMappedNumber,
        _number_range,
    )

    mapping = mapping_for_grpc_path("sound_setting.volume.rear")
    assert mapping is not None
    spec = entity_spec_for_mapping(mapping)
    index = {
        "sound_setting.volume.rear": CapabilityMeta(
            name="sound_setting.volume.rear",
            type="int",
            min=-10,
            max=10,
        )
    }
    grpc_client.capability_index = index
    grpc_client.notify_state = {"sound_setting.volume.rear": None}
    lo, hi = _number_range(mapping, capability_index=index)
    assert (lo, hi) == (-10.0, 10.0)
    entity = BraviaGrpcMappedNumber(
        grpc_client, grpc_entry, spec, native_min_value=lo, native_max_value=hi
    )
    assert entity._attr_native_value == 0.0


def test_av_sync_mapped_numbers_match_tcp_slider(
    grpc_client: MagicMock, grpc_entry: MagicMock
) -> None:
    from custom_components.bravia_quad.grpc_mapped_entities import (
        BraviaGrpcMappedNumber,
        _number_range,
    )

    for path in ("sound_setting.av_sync.hdmi_0", "sound_setting.av_sync.arc"):
        mapping = mapping_for_grpc_path(path)
        assert mapping is not None
        spec = entity_spec_for_mapping(mapping)
        lo, hi = _number_range(mapping)
        entity = BraviaGrpcMappedNumber(
            grpc_client, grpc_entry, spec, native_min_value=lo, native_max_value=hi
        )
        assert entity._attr_mode == NumberMode.SLIDER
        assert entity._attr_native_step == 25
        assert entity._attr_native_unit_of_measurement == "ms"


def test_voice_zoom_unavailable_reason_from_parent_path() -> None:
    notify_state = {
        "sound_setting.voice_zoom.unavailable_reason": "unsupported_tv",
    }
    reason = grpc_exec_unavailable_reason(
        notify_state, "sound_setting.voice_zoom.on_off"
    )
    assert reason == "unsupported_tv"


def test_voice_zoom_none_reason_is_available() -> None:
    notify_state = {"sound_setting.voice_zoom.unavailable_reason": "none"}
    assert (
        grpc_exec_unavailable_reason(notify_state, "sound_setting.voice_zoom.on_off")
        is None
    )


def test_playback_command_false_availability_none_reason_is_available() -> None:
    notify_state = {
        "playback_control.playback_command.availability": False,
        "playback_control.playback_command.unavailable_reason": "none",
    }
    assert (
        grpc_exec_unavailable_reason(notify_state, "playback_control.playback_command")
        is None
    )


def _entity_suffixes(entities: list, grpc_entry: MagicMock) -> set[str]:
    prefix = f"{grpc_entry.unique_id}_"
    return {e._attr_unique_id.removeprefix(prefix) for e in entities}


def test_switch_factory_includes_power_and_aav(
    grpc_client: MagicMock, grpc_entry: MagicMock
) -> None:
    entities = mapped_switch_entities(grpc_client, grpc_entry)
    suffixes = _entity_suffixes(entities, grpc_entry)
    assert "power" in suffixes
    assert "advanced_auto_volume" in suffixes


def test_select_and_number_both_exist_availability_flips(
    grpc_client: MagicMock, grpc_entry: MagicMock
) -> None:
    """Bass select and subwoofer number always exist; availability follows link."""
    grpc_client.notify_state = {
        "speaker_connection_setting.connection_status.sw": "disconnected"
    }
    selects = mapped_select_entities(grpc_client, grpc_entry)
    numbers = mapped_number_entities(grpc_client, grpc_entry)
    assert "bass_level_select" in _entity_suffixes(selects, grpc_entry)
    assert "subwoofer_level" in _entity_suffixes(numbers, grpc_entry)

    bass = next(e for e in selects if e._attr_unique_id.endswith("_bass_level_select"))
    sub = next(e for e in numbers if e._attr_unique_id.endswith("_subwoofer_level"))
    assert bass.available is True
    assert sub.available is False

    grpc_client.notify_state = {
        "speaker_connection_setting.connection_status.sw": "connected"
    }
    assert bass.available is False
    assert sub.available is True


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("min", "min"),
        ("mid", "mid"),
        ("max", "max"),
        (0, "min"),
        (1, "mid"),
        (2, "max"),
    ],
)
def test_bass_select_shows_min_mid_max_not_int(
    grpc_client: MagicMock,
    grpc_entry: MagicMock,
    raw: str | int,
    expected: str,
) -> None:
    """gRPC bass normalizes to int; select must display min/mid/max labels."""
    grpc_client.notify_state = {"sound_setting.volume.bass": raw}
    entities = mapped_select_entities(grpc_client, grpc_entry)
    bass = next(e for e in entities if e._attr_unique_id.endswith("_bass_level_select"))
    assert bass._attr_current_option == expected
    assert bass._attr_options == ["min", "mid", "max"]


async def test_bass_select_sync_after_exec_keeps_enum_labels(
    hass: HomeAssistant,
    grpc_client: MagicMock,
    grpc_entry: MagicMock,
) -> None:
    """Post-exec sync must keep min/mid/max labels, not TCP ints 0/1/2."""
    grpc_client.notify_state = {"sound_setting.volume.bass": "max"}

    async def _exec(path: str, kind: str, payload: str) -> bool:
        grpc_client.notify_state["sound_setting.volume.bass"] = payload
        return True

    grpc_client.async_exec_denormalized = AsyncMock(side_effect=_exec)
    mapping = mapping_for_grpc_path("sound_setting.volume.bass")
    assert mapping is not None
    spec = entity_spec_for_mapping(mapping)
    bass = BraviaGrpcBassLevelSelect(grpc_client, grpc_entry, spec)
    bass.hass = hass
    bass.async_write_ha_state = MagicMock()

    await bass.async_select_option("min")

    assert bass._attr_current_option == "min"
    assert bass._attr_options == ["min", "mid", "max"]


def test_number_factory_volume_and_step_interval(
    grpc_client: MagicMock, grpc_entry: MagicMock
) -> None:
    entities = mapped_number_entities(grpc_client, grpc_entry)
    suffixes = _entity_suffixes(entities, grpc_entry)
    assert "volume" in suffixes
    assert "volume_step_interval" in suffixes


def test_sensor_factory_includes_ipv4(
    grpc_client: MagicMock, grpc_entry: MagicMock
) -> None:
    entities = mapped_sensor_entities(grpc_client, grpc_entry)
    suffixes = _entity_suffixes(entities, grpc_entry)
    assert "ip_address" in suffixes


def test_entity_spec_volume_unique_id(grpc_entry: MagicMock) -> None:
    spec = entity_spec_for_path("volume")
    assert spec is not None
    assert spec.unique_id_suffix == "volume"
    assert spec.translation_key == "volume"


def test_mappings_include_bass_and_subwoofer_paths() -> None:
    bass = mapping_for_grpc_path("sound_setting.volume.bass")
    sub = mapping_for_grpc_path("sound_setting.volume.subwoofer")
    assert bass is not None
    assert bass.ha_platform == "select"
    assert sub is not None
    assert sub.ha_platform == "number"
    assert sub.writable is True


def test_mappings_exclude_handcrafted_from_platform_selects() -> None:
    paths = {m.grpc_path for m in mappings_for_platform("select", writable=True)}
    assert "sound_setting.sound_effect" not in paths


def test_mapped_select_entities_are_config(
    grpc_client: MagicMock, grpc_entry: MagicMock
) -> None:
    """Mapped selects belong in Configuration; input lives on media player."""
    switches = mapped_switch_entities(grpc_client, grpc_entry)
    assert switches
    assert all(e.entity_category == EntityCategory.CONFIG for e in switches)

    selects = mapped_select_entities(grpc_client, grpc_entry)
    assert selects
    assert all(e.entity_category == EntityCategory.CONFIG for e in selects)
    assert not any(e._attr_unique_id.endswith("_input") for e in selects)

    numbers = mapped_number_entities(grpc_client, grpc_entry)
    assert numbers
    assert all(e.entity_category == EntityCategory.CONFIG for e in numbers)


@pytest.mark.asyncio
async def test_notify_only_mapped_switch_restores_on_added(
    hass: HomeAssistant, grpc_client: MagicMock, grpc_entry: MagicMock
) -> None:
    mapping = mapping_for_grpc_path("sound_setting.auto_volume")
    assert mapping is not None
    spec = entity_spec_for_mapping(mapping)
    entity = BraviaGrpcMappedSwitch(grpc_client, grpc_entry, spec)
    entity.entity_id = f"switch.{DOMAIN}_serial123_advanced_auto_volume"
    entity.hass = hass
    entity.async_write_ha_state = MagicMock()
    grpc_client.merge_notify_cache = MagicMock()

    async_get(hass).last_states[entity.entity_id] = StoredState(
        State(entity.entity_id, "on"),
        None,
        datetime.now(tz=UTC),
    )

    await entity.async_added_to_hass()

    assert entity._attr_is_on is True
    grpc_client.merge_notify_cache.assert_called_once_with(
        {"sound_setting.auto_volume": True}
    )


@pytest.mark.asyncio
async def test_notify_only_mapped_select_restores_on_added(
    hass: HomeAssistant, grpc_client: MagicMock, grpc_entry: MagicMock
) -> None:
    mapping = mapping_for_grpc_path("sound_setting.drc")
    assert mapping is not None
    spec = entity_spec_for_mapping(mapping)
    entity = BraviaGrpcMappedSelect(grpc_client, grpc_entry, spec)
    entity.entity_id = f"select.{DOMAIN}_serial123_drc"
    entity.hass = hass
    entity.async_write_ha_state = MagicMock()
    grpc_client.merge_notify_cache = MagicMock()

    async_get(hass).last_states[entity.entity_id] = StoredState(
        State(entity.entity_id, "auto"),
        None,
        datetime.now(tz=UTC),
    )

    await entity.async_added_to_hass()

    assert entity._attr_current_option == "auto"
    grpc_client.merge_notify_cache.assert_called_once_with(
        {"sound_setting.drc": "auto"}
    )
