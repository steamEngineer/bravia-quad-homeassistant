"""Tests for the Bravia Quad number platform."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest
from homeassistant.const import ATTR_ENTITY_ID, Platform
from homeassistant.helpers import entity_registry as er

if TYPE_CHECKING:
    from unittest.mock import MagicMock

    from homeassistant.core import HomeAssistant
    from pytest_homeassistant_custom_component.common import MockConfigEntry

NUMBER_DOMAIN = "number"


@pytest.fixture
def platforms() -> list[Platform]:
    """Return the platforms to be loaded for this test."""
    return [Platform.NUMBER]


def get_entity_id_by_unique_id_suffix(
    entity_registry: er.EntityRegistry, suffix: str
) -> str | None:
    """Get entity_id from the registry by unique_id suffix."""
    for entry in entity_registry.entities.values():
        if entry.unique_id and entry.unique_id.endswith(suffix):
            return entry.entity_id
    return None


@pytest.mark.usefixtures("init_integration")
async def test_number_entities(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
) -> None:
    """Test number entities are created correctly."""
    # Verify expected number entities exist (with subwoofer)
    expected_entities = {
        "_volume": "50",
        "_rear_level": "0",
        "_bass_level_slider": "0",
    }

    for suffix, expected_state in expected_entities.items():
        entity_id = get_entity_id_by_unique_id_suffix(entity_registry, suffix)
        assert entity_id is not None, f"Entity with suffix {suffix} not found"

        state = hass.states.get(entity_id)
        assert state is not None, f"State for {entity_id} not found"
        assert state.state == expected_state, f"Expected {expected_state} for {suffix}"


@pytest.mark.usefixtures("init_integration")
async def test_volume_number_set_value(
    hass: HomeAssistant,
    mock_bravia_quad_client: MagicMock,
    entity_registry: er.EntityRegistry,
) -> None:
    """Test setting the volume value."""
    entity_id = get_entity_id_by_unique_id_suffix(entity_registry, "_volume")
    assert entity_id is not None

    # Verify initial state
    state = hass.states.get(entity_id)
    assert state is not None
    assert state.state == "50"  # Mock default value

    mock_bravia_quad_client.async_set_volume.return_value = True

    await hass.services.async_call(
        NUMBER_DOMAIN,
        "set_value",
        {ATTR_ENTITY_ID: entity_id, "value": 75},
        blocking=True,
    )

    mock_bravia_quad_client.async_set_volume.assert_called_once_with(75)


@pytest.mark.usefixtures("init_integration")
async def test_rear_level_number_set_value(
    hass: HomeAssistant,
    mock_bravia_quad_client: MagicMock,
    entity_registry: er.EntityRegistry,
) -> None:
    """Test setting the rear level value."""
    entity_id = get_entity_id_by_unique_id_suffix(entity_registry, "_rear_level")
    assert entity_id is not None

    # Verify initial state
    state = hass.states.get(entity_id)
    assert state is not None
    assert state.state == "0"  # Mock default value

    mock_bravia_quad_client.async_set_rear_level.return_value = True

    await hass.services.async_call(
        NUMBER_DOMAIN,
        "set_value",
        {ATTR_ENTITY_ID: entity_id, "value": 5},
        blocking=True,
    )

    mock_bravia_quad_client.async_set_rear_level.assert_called_once_with(5)


@pytest.mark.usefixtures("init_integration")
async def test_bass_level_number_set_value(
    hass: HomeAssistant,
    mock_bravia_quad_client: MagicMock,
    entity_registry: er.EntityRegistry,
) -> None:
    """Test setting the bass level value (with subwoofer)."""
    entity_id = get_entity_id_by_unique_id_suffix(entity_registry, "_bass_level_slider")
    assert entity_id is not None

    # Verify initial state (bass level slider is created when has_subwoofer=True)
    state = hass.states.get(entity_id)
    assert state is not None
    assert state.state == "0"  # Mock default value

    mock_bravia_quad_client.async_set_bass_level.return_value = True

    await hass.services.async_call(
        NUMBER_DOMAIN,
        "set_value",
        {ATTR_ENTITY_ID: entity_id, "value": 3},
        blocking=True,
    )

    mock_bravia_quad_client.async_set_bass_level.assert_called_once_with(3)


@pytest.fixture
def platforms_no_subwoofer() -> list[Platform]:
    """Return the platforms to be loaded for this test."""
    return [Platform.NUMBER]


@pytest.mark.usefixtures("mock_bravia_quad_client")
async def test_bass_level_not_created_without_subwoofer(
    hass: HomeAssistant,
    mock_config_entry_no_subwoofer: MockConfigEntry,
    platforms_no_subwoofer: list[Platform],
    entity_registry: er.EntityRegistry,
) -> None:
    """Test that bass level slider is not created without subwoofer."""
    mock_config_entry_no_subwoofer.add_to_hass(hass)

    with patch("custom_components.bravia_quad.PLATFORMS", platforms_no_subwoofer):
        await hass.config_entries.async_setup(mock_config_entry_no_subwoofer.entry_id)
        await hass.async_block_till_done()

    # Bass level slider should NOT exist when subwoofer is not present
    entity_id = get_entity_id_by_unique_id_suffix(entity_registry, "_bass_level_slider")
    assert entity_id is None
