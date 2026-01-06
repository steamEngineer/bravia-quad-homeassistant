"""Tests for the Bravia Quad notification callback functionality."""

from __future__ import annotations

from typing import TYPE_CHECKING, NamedTuple

import pytest
from homeassistant.const import Platform

from custom_components.bravia_quad.const import (
    FEATURE_AAV,
    FEATURE_AUTO_STANDBY,
    FEATURE_DRC,
    FEATURE_HDMI_CEC,
    FEATURE_INPUT,
    FEATURE_NIGHT_MODE,
    FEATURE_POWER,
    FEATURE_REAR_LEVEL,
    FEATURE_SOUND_FIELD,
    FEATURE_VOICE_ENHANCER,
    FEATURE_VOLUME,
)

from .conftest import get_entity_id_by_unique_id_suffix

if TYPE_CHECKING:
    from collections.abc import Callable
    from unittest.mock import MagicMock

    from homeassistant.core import HomeAssistant
    from homeassistant.helpers import entity_registry as er
    from pytest_homeassistant_custom_component.common import MockConfigEntry


class SwitchTestCase(NamedTuple):
    """Test case parameters for switch notification tests."""

    entity_suffix: str
    feature: str
    on_value: str
    off_value: str


class NumberTestCase(NamedTuple):
    """Test case parameters for number notification tests."""

    entity_suffix: str
    feature: str
    initial_value: str
    new_value: str


class SelectTestCase(NamedTuple):
    """Test case parameters for select notification tests."""

    entity_suffix: str
    feature: str
    test_values: list[tuple[str, str]]


# Expected notification features by platform
SWITCH_FEATURES = {
    FEATURE_POWER,
    FEATURE_HDMI_CEC,
    FEATURE_AUTO_STANDBY,
    FEATURE_VOICE_ENHANCER,
    FEATURE_SOUND_FIELD,
    FEATURE_NIGHT_MODE,
    FEATURE_AAV,
}

NUMBER_FEATURES = {
    FEATURE_VOLUME,
    FEATURE_REAR_LEVEL,
}

SELECT_FEATURES = {
    FEATURE_INPUT,
    FEATURE_DRC,
}

# Test case definitions
SWITCH_TEST_CASES = [
    SwitchTestCase("_power", FEATURE_POWER, "on", "off"),
    SwitchTestCase("_hdmi_cec", FEATURE_HDMI_CEC, "on", "off"),
    SwitchTestCase("_night_mode", FEATURE_NIGHT_MODE, "on", "off"),
    SwitchTestCase("_sound_field", FEATURE_SOUND_FIELD, "on", "off"),
    SwitchTestCase("_voice_enhancer", FEATURE_VOICE_ENHANCER, "upon", "upoff"),
    SwitchTestCase("_advanced_auto_volume", FEATURE_AAV, "on", "off"),
]

NUMBER_TEST_CASES = [
    NumberTestCase("_volume", FEATURE_VOLUME, "50", "75"),
    NumberTestCase("_rear_level", FEATURE_REAR_LEVEL, "0", "5"),
]

SELECT_TEST_CASES = [
    SelectTestCase(
        "_input",
        FEATURE_INPUT,
        [("hdmi1", "HDMI In"), ("bluetooth", "Bluetooth"), ("tv", "TV (eARC)")],
    ),
    SelectTestCase(
        "_drc",
        FEATURE_DRC,
        [("on", "On"), ("off", "Off"), ("auto", "Auto")],
    ),
]


def _get_registered_callback(mock_client: MagicMock, feature: str) -> Callable | None:
    """Get the callback registered for a specific feature."""
    for call_args in mock_client.register_notification_callback.call_args_list:
        if call_args[0][0] == feature:
            return call_args[0][1]
    return None


# --- Callback Registration Tests ---


@pytest.fixture
def platforms() -> list[Platform]:
    """Return all platforms to test notification registration."""
    return [Platform.NUMBER, Platform.SELECT, Platform.SWITCH]


@pytest.mark.usefixtures("init_integration")
async def test_callbacks_registered_on_setup(
    mock_bravia_quad_client: MagicMock,
) -> None:
    """Test that entity callbacks are registered when entities are added."""
    register_calls = (
        mock_bravia_quad_client.register_notification_callback.call_args_list
    )
    registered_features = {call_args[0][0] for call_args in register_calls}

    # Test all platform features are registered
    all_expected = SWITCH_FEATURES | NUMBER_FEATURES | SELECT_FEATURES
    for feature in all_expected:
        assert feature in registered_features, f"Feature {feature} not registered"


@pytest.mark.usefixtures("init_integration")
async def test_callbacks_unregistered_on_unload(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_bravia_quad_client: MagicMock,
) -> None:
    """Test that callbacks are unregistered when integration is unloaded."""
    register_calls = (
        mock_bravia_quad_client.register_notification_callback.call_args_list
    )
    registered_features = {call_args[0][0] for call_args in register_calls}

    await hass.config_entries.async_unload(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    unregister_calls = (
        mock_bravia_quad_client.unregister_notification_callback.call_args_list
    )
    unregistered_features = {call_args[0][0] for call_args in unregister_calls}

    for feature in registered_features:
        assert feature in unregistered_features, (
            f"Feature {feature} not unregistered on unload"
        )


# --- Switch Notification State Update Tests ---


@pytest.mark.parametrize(
    "test_case",
    SWITCH_TEST_CASES,
    ids=[tc.entity_suffix.lstrip("_") for tc in SWITCH_TEST_CASES],
)
@pytest.mark.usefixtures("init_integration")
async def test_switch_notification_updates_state(
    hass: HomeAssistant,
    mock_bravia_quad_client: MagicMock,
    entity_registry: er.EntityRegistry,
    test_case: SwitchTestCase,
) -> None:
    """Test that switch notifications update entity state."""
    entity_id = get_entity_id_by_unique_id_suffix(
        entity_registry, test_case.entity_suffix
    )
    assert entity_id is not None, f"Entity {test_case.entity_suffix} not found"

    callback = _get_registered_callback(mock_bravia_quad_client, test_case.feature)
    assert callback is not None, f"Callback for {test_case.feature} not registered"

    # Turn on via notification
    await callback(test_case.on_value)
    await hass.async_block_till_done()
    state = hass.states.get(entity_id)
    assert state.state == "on", f"Expected 'on' after {test_case.on_value} notification"

    # Turn off via notification
    await callback(test_case.off_value)
    await hass.async_block_till_done()
    state = hass.states.get(entity_id)
    assert state.state == "off", (
        f"Expected 'off' after {test_case.off_value} notification"
    )


# --- Number Notification State Update Tests ---


def _get_entity_id_by_unique_id_suffix_and_platform(
    entity_registry: er.EntityRegistry, suffix: str, platform: str
) -> str | None:
    """Get entity_id from the registry by unique_id suffix and platform."""
    for entry in entity_registry.entities.values():
        if (
            entry.unique_id
            and entry.unique_id.endswith(suffix)
            and entry.entity_id.startswith(f"{platform}.")
        ):
            return entry.entity_id
    return None


@pytest.mark.parametrize(
    "test_case",
    NUMBER_TEST_CASES,
    ids=[tc.entity_suffix.lstrip("_") for tc in NUMBER_TEST_CASES],
)
@pytest.mark.usefixtures("init_integration")
async def test_number_notification_updates_state(
    hass: HomeAssistant,
    mock_bravia_quad_client: MagicMock,
    entity_registry: er.EntityRegistry,
    test_case: NumberTestCase,
) -> None:
    """Test that number notifications update entity state."""
    entity_id = _get_entity_id_by_unique_id_suffix_and_platform(
        entity_registry, test_case.entity_suffix, "number"
    )
    assert entity_id is not None, f"Entity {test_case.entity_suffix} not found"

    callback = _get_registered_callback(mock_bravia_quad_client, test_case.feature)
    assert callback is not None, f"Callback for {test_case.feature} not registered"

    # Verify initial state
    state = hass.states.get(entity_id)
    assert state.state == test_case.initial_value

    # Update via notification
    await callback(test_case.new_value)
    await hass.async_block_till_done()

    state = hass.states.get(entity_id)
    assert state.state == test_case.new_value


# --- Select Notification State Update Tests ---


@pytest.mark.parametrize(
    "test_case",
    SELECT_TEST_CASES,
    ids=[tc.entity_suffix.lstrip("_") for tc in SELECT_TEST_CASES],
)
@pytest.mark.usefixtures("init_integration")
async def test_select_notification_updates_state(
    hass: HomeAssistant,
    mock_bravia_quad_client: MagicMock,
    entity_registry: er.EntityRegistry,
    test_case: SelectTestCase,
) -> None:
    """Test that select notifications update entity state."""
    entity_id = get_entity_id_by_unique_id_suffix(
        entity_registry, test_case.entity_suffix
    )
    assert entity_id is not None, f"Entity {test_case.entity_suffix} not found"

    callback = _get_registered_callback(mock_bravia_quad_client, test_case.feature)
    assert callback is not None, f"Callback for {test_case.feature} not registered"

    for notification_value, expected_state in test_case.test_values:
        await callback(notification_value)
        await hass.async_block_till_done()

        state = hass.states.get(entity_id)
        assert state.state == expected_state, (
            f"Expected '{expected_state}' after '{notification_value}' notification"
        )
