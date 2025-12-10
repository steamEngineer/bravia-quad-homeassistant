"""Tests for the Bravia Quad select platform."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from homeassistant.const import ATTR_ENTITY_ID, Platform
from homeassistant.helpers import entity_registry as er

if TYPE_CHECKING:
    from unittest.mock import MagicMock

    from homeassistant.core import HomeAssistant

SELECT_DOMAIN = "select"


@pytest.fixture
def platforms() -> list[Platform]:
    """Return the platforms to be loaded for this test."""
    return [Platform.SELECT]


def get_entity_id_by_unique_id_suffix(
    entity_registry: er.EntityRegistry, suffix: str
) -> str | None:
    """Get entity_id from the registry by unique_id suffix."""
    for entry in entity_registry.entities.values():
        if entry.unique_id and entry.unique_id.endswith(suffix):
            return entry.entity_id
    return None


@pytest.mark.usefixtures("init_integration")
async def test_select_entities(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
) -> None:
    """Test select entities are created correctly."""
    # Verify expected select entities exist
    entity_id = get_entity_id_by_unique_id_suffix(entity_registry, "_input")
    assert entity_id is not None, "Input select entity not found"

    state = hass.states.get(entity_id)
    assert state is not None
    # Mock returns "tv" which maps to "TV (eARC)"
    assert state.state == "TV (eARC)"


@pytest.mark.usefixtures("init_integration")
async def test_input_select_option(
    hass: HomeAssistant,
    mock_bravia_quad_client: MagicMock,
    entity_registry: er.EntityRegistry,
) -> None:
    """Test selecting an input option."""
    entity_id = get_entity_id_by_unique_id_suffix(entity_registry, "_input")
    assert entity_id is not None

    # Verify initial state
    state = hass.states.get(entity_id)
    assert state is not None
    assert state.state == "TV (eARC)"  # Mock returns "tv" which maps to "TV (eARC)"

    mock_bravia_quad_client.async_set_input.return_value = True

    await hass.services.async_call(
        SELECT_DOMAIN,
        "select_option",
        {ATTR_ENTITY_ID: entity_id, "option": "HDMI In"},
        blocking=True,
    )

    mock_bravia_quad_client.async_set_input.assert_called_once_with("hdmi1")


@pytest.mark.usefixtures("init_integration")
async def test_input_select_spotify(
    hass: HomeAssistant,
    mock_bravia_quad_client: MagicMock,
    entity_registry: er.EntityRegistry,
) -> None:
    """Test selecting Spotify input."""
    entity_id = get_entity_id_by_unique_id_suffix(entity_registry, "_input")
    assert entity_id is not None

    mock_bravia_quad_client.async_set_input.return_value = True

    await hass.services.async_call(
        SELECT_DOMAIN,
        "select_option",
        {ATTR_ENTITY_ID: entity_id, "option": "Spotify"},
        blocking=True,
    )

    mock_bravia_quad_client.async_set_input.assert_called_once_with("spotify")


@pytest.mark.usefixtures("init_integration")
async def test_input_select_bluetooth(
    hass: HomeAssistant,
    mock_bravia_quad_client: MagicMock,
    entity_registry: er.EntityRegistry,
) -> None:
    """Test selecting Bluetooth input."""
    entity_id = get_entity_id_by_unique_id_suffix(entity_registry, "_input")
    assert entity_id is not None

    mock_bravia_quad_client.async_set_input.return_value = True

    await hass.services.async_call(
        SELECT_DOMAIN,
        "select_option",
        {ATTR_ENTITY_ID: entity_id, "option": "Bluetooth"},
        blocking=True,
    )

    mock_bravia_quad_client.async_set_input.assert_called_once_with("bluetooth")


@pytest.mark.usefixtures("init_integration")
async def test_input_select_airplay(
    hass: HomeAssistant,
    mock_bravia_quad_client: MagicMock,
    entity_registry: er.EntityRegistry,
) -> None:
    """Test selecting Airplay input."""
    entity_id = get_entity_id_by_unique_id_suffix(entity_registry, "_input")
    assert entity_id is not None

    mock_bravia_quad_client.async_set_input.return_value = True

    await hass.services.async_call(
        SELECT_DOMAIN,
        "select_option",
        {ATTR_ENTITY_ID: entity_id, "option": "Airplay"},
        blocking=True,
    )

    mock_bravia_quad_client.async_set_input.assert_called_once_with("airplay2")
