"""Tests for the Bravia Quad switch platform."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from homeassistant.const import (
    ATTR_ENTITY_ID,
    SERVICE_TURN_OFF,
    SERVICE_TURN_ON,
    Platform,
)
from homeassistant.helpers import entity_registry as er

if TYPE_CHECKING:
    from unittest.mock import MagicMock

    from homeassistant.core import HomeAssistant

SWITCH_DOMAIN = "switch"


@pytest.fixture
def platforms() -> list[Platform]:
    """Return the platforms to be loaded for this test."""
    return [Platform.SWITCH]


def get_entity_id_by_unique_id_suffix(
    entity_registry: er.EntityRegistry, suffix: str
) -> str | None:
    """Get entity_id from the registry by unique_id suffix."""
    for entry in entity_registry.entities.values():
        if entry.unique_id and entry.unique_id.endswith(suffix):
            return entry.entity_id
    return None


@pytest.mark.usefixtures("init_integration")
async def test_switch_entities(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
) -> None:
    """Test switch entities are created correctly."""
    # Verify all expected switch entities exist with correct unique_ids
    expected_entities = {
        "_power": "on",  # Default power state
        "_hdmi_cec": "off",
        "_auto_standby": "off",
        "_voice_enhancer": "off",
        "_sound_field": "off",
        "_night_mode": "off",
    }

    for suffix, expected_state in expected_entities.items():
        entity_id = get_entity_id_by_unique_id_suffix(entity_registry, suffix)
        assert entity_id is not None, f"Entity with suffix {suffix} not found"

        state = hass.states.get(entity_id)
        assert state is not None, f"State for {entity_id} not found"
        assert state.state == expected_state, f"Expected {expected_state} for {suffix}"


@pytest.mark.usefixtures("init_integration")
async def test_power_switch_turn_on(
    hass: HomeAssistant,
    mock_bravia_quad_client: MagicMock,
    entity_registry: er.EntityRegistry,
) -> None:
    """Test turning on the power switch."""
    entity_id = get_entity_id_by_unique_id_suffix(entity_registry, "_power")
    assert entity_id is not None

    # Verify initial state
    state = hass.states.get(entity_id)
    assert state is not None

    # Set power to off, then turn on
    mock_bravia_quad_client.power_state = "off"
    mock_bravia_quad_client.async_set_power.return_value = True

    await hass.services.async_call(
        SWITCH_DOMAIN,
        SERVICE_TURN_ON,
        {ATTR_ENTITY_ID: entity_id},
        blocking=True,
    )

    mock_bravia_quad_client.async_set_power.assert_called_once_with("on")


@pytest.mark.usefixtures("init_integration")
async def test_power_switch_turn_off(
    hass: HomeAssistant,
    mock_bravia_quad_client: MagicMock,
    entity_registry: er.EntityRegistry,
) -> None:
    """Test turning off the power switch."""
    entity_id = get_entity_id_by_unique_id_suffix(entity_registry, "_power")
    assert entity_id is not None

    mock_bravia_quad_client.async_set_power.return_value = True

    await hass.services.async_call(
        SWITCH_DOMAIN,
        SERVICE_TURN_OFF,
        {ATTR_ENTITY_ID: entity_id},
        blocking=True,
    )

    mock_bravia_quad_client.async_set_power.assert_called_once_with("off")


@pytest.mark.usefixtures("init_integration")
async def test_hdmi_cec_switch_turn_on(
    hass: HomeAssistant,
    mock_bravia_quad_client: MagicMock,
    entity_registry: er.EntityRegistry,
) -> None:
    """Test turning on the HDMI CEC switch."""
    entity_id = get_entity_id_by_unique_id_suffix(entity_registry, "_hdmi_cec")
    assert entity_id is not None

    mock_bravia_quad_client.async_set_hdmi_cec.return_value = True

    await hass.services.async_call(
        SWITCH_DOMAIN,
        SERVICE_TURN_ON,
        {ATTR_ENTITY_ID: entity_id},
        blocking=True,
    )

    mock_bravia_quad_client.async_set_hdmi_cec.assert_called_once_with("on")


@pytest.mark.usefixtures("init_integration")
async def test_hdmi_cec_switch_turn_off(
    hass: HomeAssistant,
    mock_bravia_quad_client: MagicMock,
    entity_registry: er.EntityRegistry,
) -> None:
    """Test turning off the HDMI CEC switch."""
    entity_id = get_entity_id_by_unique_id_suffix(entity_registry, "_hdmi_cec")
    assert entity_id is not None

    mock_bravia_quad_client.async_set_hdmi_cec.return_value = True

    await hass.services.async_call(
        SWITCH_DOMAIN,
        SERVICE_TURN_OFF,
        {ATTR_ENTITY_ID: entity_id},
        blocking=True,
    )

    mock_bravia_quad_client.async_set_hdmi_cec.assert_called_once_with("off")


@pytest.mark.usefixtures("init_integration")
async def test_auto_standby_switch_turn_on(
    hass: HomeAssistant,
    mock_bravia_quad_client: MagicMock,
    entity_registry: er.EntityRegistry,
) -> None:
    """Test turning on the auto standby switch."""
    entity_id = get_entity_id_by_unique_id_suffix(entity_registry, "_auto_standby")
    assert entity_id is not None

    mock_bravia_quad_client.async_set_auto_standby.return_value = True

    await hass.services.async_call(
        SWITCH_DOMAIN,
        SERVICE_TURN_ON,
        {ATTR_ENTITY_ID: entity_id},
        blocking=True,
    )

    mock_bravia_quad_client.async_set_auto_standby.assert_called_once_with("on")


@pytest.mark.usefixtures("init_integration")
async def test_voice_enhancer_switch_turn_on(
    hass: HomeAssistant,
    mock_bravia_quad_client: MagicMock,
    entity_registry: er.EntityRegistry,
) -> None:
    """Test turning on the voice enhancer switch."""
    entity_id = get_entity_id_by_unique_id_suffix(entity_registry, "_voice_enhancer")
    assert entity_id is not None

    mock_bravia_quad_client.async_set_voice_enhancer.return_value = True

    await hass.services.async_call(
        SWITCH_DOMAIN,
        SERVICE_TURN_ON,
        {ATTR_ENTITY_ID: entity_id},
        blocking=True,
    )

    mock_bravia_quad_client.async_set_voice_enhancer.assert_called_once_with("upon")


@pytest.mark.usefixtures("init_integration")
async def test_sound_field_switch_turn_on(
    hass: HomeAssistant,
    mock_bravia_quad_client: MagicMock,
    entity_registry: er.EntityRegistry,
) -> None:
    """Test turning on the sound field switch."""
    entity_id = get_entity_id_by_unique_id_suffix(entity_registry, "_sound_field")
    assert entity_id is not None

    mock_bravia_quad_client.async_set_sound_field.return_value = True

    await hass.services.async_call(
        SWITCH_DOMAIN,
        SERVICE_TURN_ON,
        {ATTR_ENTITY_ID: entity_id},
        blocking=True,
    )

    mock_bravia_quad_client.async_set_sound_field.assert_called_once_with("on")


@pytest.mark.usefixtures("init_integration")
async def test_night_mode_switch_turn_on(
    hass: HomeAssistant,
    mock_bravia_quad_client: MagicMock,
    entity_registry: er.EntityRegistry,
) -> None:
    """Test turning on the night mode switch."""
    entity_id = get_entity_id_by_unique_id_suffix(entity_registry, "_night_mode")
    assert entity_id is not None

    mock_bravia_quad_client.async_set_night_mode.return_value = True

    await hass.services.async_call(
        SWITCH_DOMAIN,
        SERVICE_TURN_ON,
        {ATTR_ENTITY_ID: entity_id},
        blocking=True,
    )

    mock_bravia_quad_client.async_set_night_mode.assert_called_once_with("on")


@pytest.mark.usefixtures("init_integration")
async def test_auto_standby_switch_turn_off(
    hass: HomeAssistant,
    mock_bravia_quad_client: MagicMock,
    entity_registry: er.EntityRegistry,
) -> None:
    """Test turning off the auto standby switch."""
    entity_id = get_entity_id_by_unique_id_suffix(entity_registry, "_auto_standby")
    assert entity_id is not None

    mock_bravia_quad_client.async_set_auto_standby.return_value = True

    await hass.services.async_call(
        SWITCH_DOMAIN,
        SERVICE_TURN_OFF,
        {ATTR_ENTITY_ID: entity_id},
        blocking=True,
    )

    mock_bravia_quad_client.async_set_auto_standby.assert_called_once_with("off")


@pytest.mark.usefixtures("init_integration")
async def test_voice_enhancer_switch_turn_off(
    hass: HomeAssistant,
    mock_bravia_quad_client: MagicMock,
    entity_registry: er.EntityRegistry,
) -> None:
    """Test turning off the voice enhancer switch."""
    entity_id = get_entity_id_by_unique_id_suffix(entity_registry, "_voice_enhancer")
    assert entity_id is not None

    mock_bravia_quad_client.async_set_voice_enhancer.return_value = True

    await hass.services.async_call(
        SWITCH_DOMAIN,
        SERVICE_TURN_OFF,
        {ATTR_ENTITY_ID: entity_id},
        blocking=True,
    )

    mock_bravia_quad_client.async_set_voice_enhancer.assert_called_once_with("upoff")


@pytest.mark.usefixtures("init_integration")
async def test_sound_field_switch_turn_off(
    hass: HomeAssistant,
    mock_bravia_quad_client: MagicMock,
    entity_registry: er.EntityRegistry,
) -> None:
    """Test turning off the sound field switch."""
    entity_id = get_entity_id_by_unique_id_suffix(entity_registry, "_sound_field")
    assert entity_id is not None

    mock_bravia_quad_client.async_set_sound_field.return_value = True

    await hass.services.async_call(
        SWITCH_DOMAIN,
        SERVICE_TURN_OFF,
        {ATTR_ENTITY_ID: entity_id},
        blocking=True,
    )

    mock_bravia_quad_client.async_set_sound_field.assert_called_once_with("off")


@pytest.mark.usefixtures("init_integration")
async def test_night_mode_switch_turn_off(
    hass: HomeAssistant,
    mock_bravia_quad_client: MagicMock,
    entity_registry: er.EntityRegistry,
) -> None:
    """Test turning off the night mode switch."""
    entity_id = get_entity_id_by_unique_id_suffix(entity_registry, "_night_mode")
    assert entity_id is not None

    mock_bravia_quad_client.async_set_night_mode.return_value = True

    await hass.services.async_call(
        SWITCH_DOMAIN,
        SERVICE_TURN_OFF,
        {ATTR_ENTITY_ID: entity_id},
        blocking=True,
    )

    mock_bravia_quad_client.async_set_night_mode.assert_called_once_with("off")
