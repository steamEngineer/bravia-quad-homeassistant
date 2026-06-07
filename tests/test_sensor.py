"""Tests for the Bravia Quad sensor platform."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from homeassistant.const import Platform
from homeassistant.helpers import entity_registry as er

from .conftest import get_entity_id_by_unique_id_suffix

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant


@pytest.fixture
def platforms() -> list[Platform]:
    """Override platforms to only load sensors."""
    return [Platform.SENSOR]


@pytest.mark.usefixtures("init_integration")
async def test_enabled_sensor_entities(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
) -> None:
    """Test that enabled sensor entities are created with correct state."""
    test_cases = {
        "_temperature": "57.0",
        "_network_mode": "wired",
        "_ip_address": "192.168.1.100",
        "_device_name": "Test BRAVIA Theatre Quad",
    }
    for suffix, expected_state in test_cases.items():
        entity_id = get_entity_id_by_unique_id_suffix(entity_registry, suffix)
        assert entity_id is not None, f"Entity with suffix {suffix} not found"
        state = hass.states.get(entity_id)
        assert state is not None, f"State for {entity_id} not found"
        assert state.state == expected_state, (
            f"Expected {expected_state} for {suffix}, got {state.state}"
        )


@pytest.mark.usefixtures("init_integration")
async def test_disabled_sensor_entities(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
) -> None:
    """Test that diagnostic sensors are disabled by default."""
    for suffix in (
        "_timezone",
        "_360ssm",
        "_voice_zoom_level",
        "_destination",
        "_language",
        "_dhcp",
    ):
        entity_id = get_entity_id_by_unique_id_suffix(entity_registry, suffix)
        assert entity_id is not None, f"Entity with suffix {suffix} not found"
        state = hass.states.get(entity_id)
        assert state is None, f"{entity_id} should be disabled by default"


@pytest.mark.usefixtures("init_integration_all")
async def test_timezone_sensor_value(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
) -> None:
    """Test timezone sensor shows correct value when enabled."""
    entity_id = get_entity_id_by_unique_id_suffix(entity_registry, "_timezone")
    assert entity_id is not None
    state = hass.states.get(entity_id)
    assert state is not None
    assert state.state == "America/New_York|-300"


@pytest.mark.usefixtures("init_integration_all")
async def test_voice_zoom_level_sensor_value(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
) -> None:
    """Test voice zoom level sensor shows correct value when enabled."""
    entity_id = get_entity_id_by_unique_id_suffix(entity_registry, "_voice_zoom_level")
    assert entity_id is not None
    state = hass.states.get(entity_id)
    assert state is not None
    assert state.state == "1"
