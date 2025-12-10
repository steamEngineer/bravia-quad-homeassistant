"""Tests for the Bravia Quad button platform."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from homeassistant.const import ATTR_ENTITY_ID, Platform
from homeassistant.helpers import entity_registry as er

if TYPE_CHECKING:
    from unittest.mock import MagicMock

    from homeassistant.core import HomeAssistant

BUTTON_DOMAIN = "button"


@pytest.fixture
def platforms() -> list[Platform]:
    """Return the platforms to be loaded for this test."""
    return [Platform.BUTTON]


def get_entity_id_by_unique_id_suffix(
    entity_registry: er.EntityRegistry, suffix: str
) -> str | None:
    """Get entity_id from the registry by unique_id suffix."""
    for entry in entity_registry.entities.values():
        if entry.unique_id and entry.unique_id.endswith(suffix):
            return entry.entity_id
    return None


@pytest.mark.usefixtures("init_integration")
async def test_button_entities(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
) -> None:
    """Test button entities are created correctly."""
    # Verify all expected button entities exist
    expected_suffixes = ["_detect_subwoofer", "_bluetooth_pairing"]

    for suffix in expected_suffixes:
        entity_id = get_entity_id_by_unique_id_suffix(entity_registry, suffix)
        assert entity_id is not None, f"Entity with suffix {suffix} not found"

        state = hass.states.get(entity_id)
        assert state is not None, f"State for {entity_id} not found"


@pytest.mark.usefixtures("init_integration")
async def test_detect_subwoofer_button_press(
    hass: HomeAssistant,
    mock_bravia_quad_client: MagicMock,
    entity_registry: er.EntityRegistry,
) -> None:
    """Test pressing the detect subwoofer button."""
    entity_id = get_entity_id_by_unique_id_suffix(entity_registry, "_detect_subwoofer")
    assert entity_id is not None

    # Verify entity exists
    state = hass.states.get(entity_id)
    assert state is not None

    mock_bravia_quad_client.async_detect_subwoofer.return_value = True

    await hass.services.async_call(
        BUTTON_DOMAIN,
        "press",
        {ATTR_ENTITY_ID: entity_id},
        blocking=True,
    )

    mock_bravia_quad_client.async_detect_subwoofer.assert_called_once()


@pytest.mark.usefixtures("init_integration")
async def test_bluetooth_pairing_button_press(
    hass: HomeAssistant,
    mock_bravia_quad_client: MagicMock,
    entity_registry: er.EntityRegistry,
) -> None:
    """Test pressing the Bluetooth pairing button."""
    entity_id = get_entity_id_by_unique_id_suffix(entity_registry, "_bluetooth_pairing")
    assert entity_id is not None

    # Verify entity exists
    state = hass.states.get(entity_id)
    assert state is not None

    await hass.services.async_call(
        BUTTON_DOMAIN,
        "press",
        {ATTR_ENTITY_ID: entity_id},
        blocking=True,
    )

    # The bluetooth pairing button calls async_send_command twice:
    # once to set bluetooth.mode to "Off", then to "RX"
    assert mock_bravia_quad_client.async_send_command.call_count == 2
