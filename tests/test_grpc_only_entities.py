"""Tests for notify-only gRPC entity restore (mapping-driven layer)."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest
from homeassistant.core import HomeAssistant, State
from homeassistant.helpers.restore_state import StoredState, async_get

from custom_components.bravia_quad.const import DOMAIN
from custom_components.bravia_quad.grpc_entity_registry import entity_spec_for_path
from custom_components.bravia_quad.grpc_mapped_entities import (
    BraviaGrpcMappedSelect,
    BraviaGrpcMappedSwitch,
    mapped_select_entities,
    mapped_switch_entities,
)
from custom_components.bravia_quad.helpers import (
    persist_notify_only_restore_state,
    restore_notify_only_select,
    restore_notify_only_switch,
)

GRPC_PATH_DSEE = "sound_setting.dsee_ultimate"
GRPC_PATH_DTS_DIALOG = "sound_setting.dts_dialog_control"
GRPC_PATH_SSM360_HEIGHT = "speaker_sound_setting.360ssm_height"


def test_mapped_grpc_switch_and_select_factories_include_former_handcrafted(
    grpc_client: MagicMock, grpc_entry: MagicMock
) -> None:
    switch_paths = {
        e._grpc_path for e in mapped_switch_entities(grpc_client, grpc_entry)
    }
    select_paths = {
        e._grpc_path for e in mapped_select_entities(grpc_client, grpc_entry)
    }
    assert GRPC_PATH_DSEE in switch_paths
    assert GRPC_PATH_DTS_DIALOG in switch_paths
    assert GRPC_PATH_SSM360_HEIGHT in select_paths
    assert "speaker_sound_setting.center_speaker_mode" in select_paths


@pytest.mark.asyncio
async def test_restore_notify_only_switch_seeds_cache(
    hass: HomeAssistant, grpc_client: MagicMock, grpc_entry: MagicMock
) -> None:
    spec = entity_spec_for_path(GRPC_PATH_DSEE)
    assert spec is not None
    entity = BraviaGrpcMappedSwitch(grpc_client, grpc_entry, spec)
    entity.entity_id = f"switch.{DOMAIN}_serial123_dsee_ultimate"
    entity.hass = hass
    entity._attr_is_on = None
    grpc_client.merge_notify_cache = MagicMock()

    async_get(hass).last_states[entity.entity_id] = StoredState(
        State(entity.entity_id, "on"),
        None,
        datetime.now(tz=UTC),
    )

    restored = await restore_notify_only_switch(entity, grpc_client, GRPC_PATH_DSEE)

    assert restored is True
    assert entity._attr_is_on is True
    grpc_client.merge_notify_cache.assert_called_once_with({GRPC_PATH_DSEE: True})


@pytest.mark.asyncio
async def test_dsee_switch_restores_on_added_to_hass(
    hass: HomeAssistant, grpc_client: MagicMock, grpc_entry: MagicMock
) -> None:
    spec = entity_spec_for_path(GRPC_PATH_DSEE)
    assert spec is not None
    entity = BraviaGrpcMappedSwitch(grpc_client, grpc_entry, spec)
    entity.entity_id = f"switch.{DOMAIN}_serial123_dsee_ultimate"
    entity.hass = hass
    entity.async_write_ha_state = MagicMock()
    grpc_client.merge_notify_cache = MagicMock()
    grpc_client.notify_state = {}

    async_get(hass).last_states[entity.entity_id] = StoredState(
        State(entity.entity_id, "off"),
        None,
        datetime.now(tz=UTC),
    )

    await entity.async_added_to_hass()

    assert entity._attr_is_on is False
    grpc_client.merge_notify_cache.assert_called_once_with({GRPC_PATH_DSEE: False})
    entity.async_write_ha_state.assert_called_once()


@pytest.mark.asyncio
async def test_dts_dialog_restores_on_added_to_hass(
    hass: HomeAssistant, grpc_client: MagicMock, grpc_entry: MagicMock
) -> None:
    spec = entity_spec_for_path(GRPC_PATH_DTS_DIALOG)
    assert spec is not None
    entity = BraviaGrpcMappedSwitch(grpc_client, grpc_entry, spec)
    entity.entity_id = f"switch.{DOMAIN}_serial123_dts_dialog_control"
    entity.hass = hass
    entity.async_write_ha_state = MagicMock()
    grpc_client.merge_notify_cache = MagicMock()
    grpc_client.notify_state = {}

    async_get(hass).last_states[entity.entity_id] = StoredState(
        State(entity.entity_id, "on"),
        None,
        datetime.now(tz=UTC),
    )

    await entity.async_added_to_hass()

    assert entity._attr_is_on is True
    grpc_client.merge_notify_cache.assert_called_once_with({GRPC_PATH_DTS_DIALOG: True})


@pytest.mark.asyncio
async def test_ssm_height_restores_on_added_to_hass(
    hass: HomeAssistant, grpc_client: MagicMock, grpc_entry: MagicMock
) -> None:
    spec = entity_spec_for_path(GRPC_PATH_SSM360_HEIGHT)
    assert spec is not None
    entity = BraviaGrpcMappedSelect(grpc_client, grpc_entry, spec)
    entity.entity_id = f"select.{DOMAIN}_serial123_ssm_360_height"
    entity.hass = hass
    entity.async_write_ha_state = MagicMock()
    grpc_client.merge_notify_cache = MagicMock()
    grpc_client.notify_state = {}

    async_get(hass).last_states[entity.entity_id] = StoredState(
        State(entity.entity_id, "high"),
        None,
        datetime.now(tz=UTC),
    )

    await entity.async_added_to_hass()

    assert entity._attr_current_option == "high"
    grpc_client.merge_notify_cache.assert_called_once_with(
        {GRPC_PATH_SSM360_HEIGHT: "high"}
    )


@pytest.mark.asyncio
async def test_restore_notify_only_select_seeds_cache(
    hass: HomeAssistant, grpc_client: MagicMock, grpc_entry: MagicMock
) -> None:
    spec = entity_spec_for_path(GRPC_PATH_SSM360_HEIGHT)
    assert spec is not None
    entity = BraviaGrpcMappedSelect(grpc_client, grpc_entry, spec)
    entity.entity_id = f"select.{DOMAIN}_serial123_ssm_360_height"
    entity.hass = hass
    grpc_client.merge_notify_cache = MagicMock()

    async_get(hass).last_states[entity.entity_id] = StoredState(
        State(entity.entity_id, "low"),
        None,
        datetime.now(tz=UTC),
    )

    restored = await restore_notify_only_select(
        entity, grpc_client, GRPC_PATH_SSM360_HEIGHT, entity._attr_options
    )

    assert restored is True
    assert entity._attr_current_option == "low"
    grpc_client.merge_notify_cache.assert_called_once_with(
        {GRPC_PATH_SSM360_HEIGHT: "low"}
    )


@pytest.mark.asyncio
async def test_persist_notify_only_restore_state_overwrites_unavailable(
    hass: HomeAssistant, grpc_client: MagicMock, grpc_entry: MagicMock
) -> None:
    spec = entity_spec_for_path(GRPC_PATH_SSM360_HEIGHT)
    assert spec is not None
    entity = BraviaGrpcMappedSelect(grpc_client, grpc_entry, spec)
    entity.entity_id = f"select.{DOMAIN}_serial123_ssm_360_height"
    entity.hass = hass
    entity._attr_current_option = "mid"

    async_get(hass).last_states[entity.entity_id] = StoredState(
        State(entity.entity_id, "unavailable"),
        None,
        datetime.now(tz=UTC),
    )

    persist_notify_only_restore_state(entity, "mid")

    restored = async_get(hass).last_states[entity.entity_id].state.state
    assert restored == "mid"


@pytest.mark.asyncio
async def test_restore_notify_only_select_falls_back_to_notify_cache(
    hass: HomeAssistant, grpc_client: MagicMock, grpc_entry: MagicMock
) -> None:
    spec = entity_spec_for_path(GRPC_PATH_SSM360_HEIGHT)
    assert spec is not None
    entity = BraviaGrpcMappedSelect(grpc_client, grpc_entry, spec)
    entity.entity_id = f"select.{DOMAIN}_serial123_ssm_360_height"
    entity.hass = hass
    entity._attr_current_option = None
    grpc_client.merge_notify_cache = MagicMock()
    grpc_client.notify_state = {GRPC_PATH_SSM360_HEIGHT: "high"}

    restored = await restore_notify_only_select(
        entity, grpc_client, GRPC_PATH_SSM360_HEIGHT, entity._attr_options
    )

    assert restored is True
    assert entity._attr_current_option == "high"
    grpc_client.merge_notify_cache.assert_called_once_with(
        {GRPC_PATH_SSM360_HEIGHT: "high"}
    )
