"""Tests for the Bravia Quad select platform."""

from __future__ import annotations

from typing import TYPE_CHECKING, NamedTuple
from unittest.mock import patch

import pytest
from homeassistant.const import ATTR_ENTITY_ID, CONF_HOST, Platform
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.bravia_quad.const import CONF_HAS_SUBWOOFER, DOMAIN

from .conftest import get_entity_id_by_unique_id_suffix

if TYPE_CHECKING:
    from unittest.mock import MagicMock

    from homeassistant.core import HomeAssistant

SELECT_DOMAIN = "select"


class InputSelectTestCase(NamedTuple):
    """Test case for input select options."""

    option: str
    expected_value: str


# Options are now the API values directly (used as translation keys)
INPUT_SELECT_TEST_CASES = [
    InputSelectTestCase("hdmi1", "hdmi1"),
    InputSelectTestCase("spotify", "spotify"),
    InputSelectTestCase("bluetooth", "bluetooth"),
    InputSelectTestCase("airplay2", "airplay2"),
    InputSelectTestCase("tv", "tv"),
]


@pytest.fixture
def platforms() -> list[Platform]:
    """Return the platforms to be loaded for this test."""
    return [Platform.SELECT]


@pytest.fixture
def mock_config_entry_no_subwoofer() -> MockConfigEntry:
    """Return a mocked config entry without subwoofer."""
    return MockConfigEntry(
        title="Bravia Quad",
        domain=DOMAIN,
        data={
            CONF_HOST: "192.168.1.100",
            CONF_HAS_SUBWOOFER: False,
        },
        unique_id="192.168.1.100",
        entry_id="test_entry_id_no_sub",
    )


# =============================================================================
# Input Select Tests
# =============================================================================


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
    # Mock returns "tv" - state is now the API value
    assert state.state == "tv"


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
    assert state.state == "tv"  # Mock returns "tv"

    mock_bravia_quad_client.async_set_input.return_value = True

    await hass.services.async_call(
        SELECT_DOMAIN,
        "select_option",
        {ATTR_ENTITY_ID: entity_id, "option": "hdmi1"},
        blocking=True,
    )

    mock_bravia_quad_client.async_set_input.assert_called_once_with("hdmi1")


@pytest.mark.parametrize(
    ("option", "expected_value"),
    INPUT_SELECT_TEST_CASES,
    ids=[tc.option for tc in INPUT_SELECT_TEST_CASES],
)
@pytest.mark.usefixtures("init_integration")
async def test_input_select_options_parametrized(
    hass: HomeAssistant,
    mock_bravia_quad_client: MagicMock,
    entity_registry: er.EntityRegistry,
    option: str,
    expected_value: str,
) -> None:
    """Test selecting various input options."""
    entity_id = get_entity_id_by_unique_id_suffix(entity_registry, "_input")
    assert entity_id is not None

    mock_bravia_quad_client.async_set_input.return_value = True

    await hass.services.async_call(
        SELECT_DOMAIN,
        "select_option",
        {ATTR_ENTITY_ID: entity_id, "option": option},
        blocking=True,
    )

    mock_bravia_quad_client.async_set_input.assert_called_once_with(expected_value)


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
        {ATTR_ENTITY_ID: entity_id, "option": "spotify"},
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
        {ATTR_ENTITY_ID: entity_id, "option": "bluetooth"},
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
        {ATTR_ENTITY_ID: entity_id, "option": "airplay2"},
        blocking=True,
    )

    mock_bravia_quad_client.async_set_input.assert_called_once_with("airplay2")


@pytest.mark.usefixtures("init_integration")
async def test_input_select_fails(
    hass: HomeAssistant,
    mock_bravia_quad_client: MagicMock,
    entity_registry: er.EntityRegistry,
) -> None:
    """Test input select when API call fails."""
    entity_id = get_entity_id_by_unique_id_suffix(entity_registry, "_input")
    assert entity_id is not None

    # Mock API failure
    mock_bravia_quad_client.async_set_input.return_value = False

    # Get initial state
    initial_state = hass.states.get(entity_id)
    assert initial_state is not None

    await hass.services.async_call(
        SELECT_DOMAIN,
        "select_option",
        {ATTR_ENTITY_ID: entity_id, "option": "hdmi1"},
        blocking=True,
    )

    # State should remain unchanged after failure
    state = hass.states.get(entity_id)
    assert state is not None
    assert state.state == initial_state.state


@pytest.mark.usefixtures("init_integration")
async def test_input_notification_unknown_value(
    hass: HomeAssistant,
    mock_bravia_quad_client: MagicMock,
    entity_registry: er.EntityRegistry,
) -> None:
    """Test input notification with unknown value logs warning."""
    entity_id = get_entity_id_by_unique_id_suffix(entity_registry, "_input")
    assert entity_id is not None

    # Get the registered callback
    callback = mock_bravia_quad_client.register_notification_callback.call_args_list[0][
        0
    ][1]

    # Trigger callback with unknown value
    await callback("unknown_input")

    # State should remain unchanged
    state = hass.states.get(entity_id)
    assert state is not None
    assert state.state == "tv"


# =============================================================================
# DRC Select Tests
# =============================================================================


@pytest.mark.usefixtures("init_integration")
async def test_drc_select_entity_exists(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
) -> None:
    """Test DRC select entity is created."""
    entity_id = get_entity_id_by_unique_id_suffix(entity_registry, "_drc")
    assert entity_id is not None, "DRC select entity not found"

    state = hass.states.get(entity_id)
    assert state is not None
    # Default mock value is "auto"
    assert state.state == "auto"


@pytest.mark.parametrize(
    ("option", "expected_value"),
    [
        ("auto", "auto"),
        ("on", "on"),
        ("off", "off"),
    ],
    ids=["auto", "on", "off"],
)
@pytest.mark.usefixtures("init_integration")
async def test_drc_select_options(
    hass: HomeAssistant,
    mock_bravia_quad_client: MagicMock,
    entity_registry: er.EntityRegistry,
    option: str,
    expected_value: str,
) -> None:
    """Test selecting DRC options."""
    entity_id = get_entity_id_by_unique_id_suffix(entity_registry, "_drc")
    assert entity_id is not None

    mock_bravia_quad_client.async_set_drc.return_value = True

    await hass.services.async_call(
        SELECT_DOMAIN,
        "select_option",
        {ATTR_ENTITY_ID: entity_id, "option": option},
        blocking=True,
    )

    mock_bravia_quad_client.async_set_drc.assert_called_once_with(expected_value)


@pytest.mark.usefixtures("init_integration")
async def test_drc_select_fails(
    hass: HomeAssistant,
    mock_bravia_quad_client: MagicMock,
    entity_registry: er.EntityRegistry,
) -> None:
    """Test DRC select when API call fails."""
    entity_id = get_entity_id_by_unique_id_suffix(entity_registry, "_drc")
    assert entity_id is not None

    mock_bravia_quad_client.async_set_drc.return_value = False

    initial_state = hass.states.get(entity_id)
    assert initial_state is not None

    await hass.services.async_call(
        SELECT_DOMAIN,
        "select_option",
        {ATTR_ENTITY_ID: entity_id, "option": "on"},
        blocking=True,
    )

    # State should remain unchanged after failure
    state = hass.states.get(entity_id)
    assert state is not None
    assert state.state == initial_state.state


@pytest.mark.usefixtures("init_integration")
async def test_drc_notification_updates_state(
    hass: HomeAssistant,
    mock_bravia_quad_client: MagicMock,
    entity_registry: er.EntityRegistry,
) -> None:
    """Test DRC notification updates entity state."""
    entity_id = get_entity_id_by_unique_id_suffix(entity_registry, "_drc")
    assert entity_id is not None

    # Find the DRC callback (third registered callback - after input and bass_level)
    # The order depends on entity registration
    callbacks = mock_bravia_quad_client.register_notification_callback.call_args_list
    drc_callback = None
    for call in callbacks:
        if call[0][0] == "audio.drangecomp":
            drc_callback = call[0][1]
            break

    assert drc_callback is not None, "DRC callback not found"

    # Trigger callback with "on" value
    await drc_callback("on")

    state = hass.states.get(entity_id)
    assert state is not None
    assert state.state == "on"


@pytest.mark.usefixtures("init_integration")
async def test_drc_notification_unknown_value(
    hass: HomeAssistant,
    mock_bravia_quad_client: MagicMock,
    entity_registry: er.EntityRegistry,
) -> None:
    """Test DRC notification with unknown value logs warning."""
    entity_id = get_entity_id_by_unique_id_suffix(entity_registry, "_drc")
    assert entity_id is not None

    callbacks = mock_bravia_quad_client.register_notification_callback.call_args_list
    drc_callback = None
    for call in callbacks:
        if call[0][0] == "audio.drangecomp":
            drc_callback = call[0][1]
            break

    assert drc_callback is not None

    initial_state = hass.states.get(entity_id)
    assert initial_state is not None

    # Trigger callback with unknown value
    await drc_callback("unknown_drc")

    # State should remain unchanged
    state = hass.states.get(entity_id)
    assert state is not None
    assert state.state == initial_state.state


# =============================================================================
# Bass Level Select Tests (Non-Subwoofer Mode)
# =============================================================================


async def test_bass_level_select_created_without_subwoofer(
    hass: HomeAssistant,
    mock_config_entry_no_subwoofer: MockConfigEntry,
    mock_bravia_quad_client: MagicMock,
) -> None:
    """Test bass level select is created when no subwoofer is detected."""
    mock_config_entry_no_subwoofer.add_to_hass(hass)

    with patch("custom_components.bravia_quad.PLATFORMS", [Platform.SELECT]):
        await hass.config_entries.async_setup(mock_config_entry_no_subwoofer.entry_id)
        await hass.async_block_till_done()

    entity_registry = er.async_get(hass)
    entity_id = get_entity_id_by_unique_id_suffix(entity_registry, "_bass_level_select")
    assert entity_id is not None, "Bass level select entity not found"

    state = hass.states.get(entity_id)
    assert state is not None
    # Default mock bass_level=0 maps to "min"
    assert state.state == "min"


async def test_bass_level_select_not_created_with_subwoofer(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_bravia_quad_client: MagicMock,
) -> None:
    """Test bass level select is NOT created when subwoofer is detected."""
    mock_config_entry.add_to_hass(hass)

    with patch("custom_components.bravia_quad.PLATFORMS", [Platform.SELECT]):
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

    entity_registry = er.async_get(hass)
    entity_id = get_entity_id_by_unique_id_suffix(entity_registry, "_bass_level_select")
    assert entity_id is None, "Bass level select should not exist with subwoofer"


@pytest.mark.parametrize(
    ("option", "expected_value"),
    [
        ("min", 0),
        ("mid", 1),
        ("max", 2),
    ],
    ids=["min", "mid", "max"],
)
async def test_bass_level_select_options(
    hass: HomeAssistant,
    mock_config_entry_no_subwoofer: MockConfigEntry,
    mock_bravia_quad_client: MagicMock,
    option: str,
    expected_value: int,
) -> None:
    """Test selecting bass level options."""
    mock_config_entry_no_subwoofer.add_to_hass(hass)

    with patch("custom_components.bravia_quad.PLATFORMS", [Platform.SELECT]):
        await hass.config_entries.async_setup(mock_config_entry_no_subwoofer.entry_id)
        await hass.async_block_till_done()

    entity_registry = er.async_get(hass)
    entity_id = get_entity_id_by_unique_id_suffix(entity_registry, "_bass_level_select")
    assert entity_id is not None

    mock_bravia_quad_client.async_set_bass_level.return_value = True

    await hass.services.async_call(
        SELECT_DOMAIN,
        "select_option",
        {ATTR_ENTITY_ID: entity_id, "option": option},
        blocking=True,
    )

    mock_bravia_quad_client.async_set_bass_level.assert_called_once_with(expected_value)


async def test_bass_level_select_fails(
    hass: HomeAssistant,
    mock_config_entry_no_subwoofer: MockConfigEntry,
    mock_bravia_quad_client: MagicMock,
) -> None:
    """Test bass level select when API call fails."""
    mock_config_entry_no_subwoofer.add_to_hass(hass)

    with patch("custom_components.bravia_quad.PLATFORMS", [Platform.SELECT]):
        await hass.config_entries.async_setup(mock_config_entry_no_subwoofer.entry_id)
        await hass.async_block_till_done()

    entity_registry = er.async_get(hass)
    entity_id = get_entity_id_by_unique_id_suffix(entity_registry, "_bass_level_select")
    assert entity_id is not None

    mock_bravia_quad_client.async_set_bass_level.return_value = False

    initial_state = hass.states.get(entity_id)
    assert initial_state is not None

    await hass.services.async_call(
        SELECT_DOMAIN,
        "select_option",
        {ATTR_ENTITY_ID: entity_id, "option": "max"},
        blocking=True,
    )

    # State should remain unchanged after failure
    state = hass.states.get(entity_id)
    assert state is not None
    assert state.state == initial_state.state


async def test_bass_level_notification_updates_state(
    hass: HomeAssistant,
    mock_config_entry_no_subwoofer: MockConfigEntry,
    mock_bravia_quad_client: MagicMock,
) -> None:
    """Test bass level notification updates entity state."""
    mock_config_entry_no_subwoofer.add_to_hass(hass)

    with patch("custom_components.bravia_quad.PLATFORMS", [Platform.SELECT]):
        await hass.config_entries.async_setup(mock_config_entry_no_subwoofer.entry_id)
        await hass.async_block_till_done()

    entity_registry = er.async_get(hass)
    entity_id = get_entity_id_by_unique_id_suffix(entity_registry, "_bass_level_select")
    assert entity_id is not None

    # Find the bass level callback
    callbacks = mock_bravia_quad_client.register_notification_callback.call_args_list
    bass_callback = None
    for call in callbacks:
        if call[0][0] == "main.bassstep":
            bass_callback = call[0][1]
            break

    assert bass_callback is not None, "Bass level callback not found"

    # Trigger callback with "2" (max)
    await bass_callback("2")

    state = hass.states.get(entity_id)
    assert state is not None
    assert state.state == "max"


async def test_bass_level_notification_invalid_value(
    hass: HomeAssistant,
    mock_config_entry_no_subwoofer: MockConfigEntry,
    mock_bravia_quad_client: MagicMock,
) -> None:
    """Test bass level notification with invalid (non-numeric) value."""
    mock_config_entry_no_subwoofer.add_to_hass(hass)

    with patch("custom_components.bravia_quad.PLATFORMS", [Platform.SELECT]):
        await hass.config_entries.async_setup(mock_config_entry_no_subwoofer.entry_id)
        await hass.async_block_till_done()

    entity_registry = er.async_get(hass)
    entity_id = get_entity_id_by_unique_id_suffix(entity_registry, "_bass_level_select")
    assert entity_id is not None

    callbacks = mock_bravia_quad_client.register_notification_callback.call_args_list
    bass_callback = None
    for call in callbacks:
        if call[0][0] == "main.bassstep":
            bass_callback = call[0][1]
            break

    assert bass_callback is not None

    initial_state = hass.states.get(entity_id)
    assert initial_state is not None

    # Trigger callback with invalid non-numeric value
    await bass_callback("invalid")

    # State should remain unchanged
    state = hass.states.get(entity_id)
    assert state is not None
    assert state.state == initial_state.state


async def test_bass_level_subwoofer_detection_triggers_reload(
    hass: HomeAssistant,
    mock_config_entry_no_subwoofer: MockConfigEntry,
    mock_bravia_quad_client: MagicMock,
) -> None:
    """Test bass level value outside 0-2 triggers subwoofer detection reload."""
    mock_config_entry_no_subwoofer.add_to_hass(hass)

    with patch("custom_components.bravia_quad.PLATFORMS", [Platform.SELECT]):
        await hass.config_entries.async_setup(mock_config_entry_no_subwoofer.entry_id)
        await hass.async_block_till_done()

    entity_registry = er.async_get(hass)
    entity_id = get_entity_id_by_unique_id_suffix(entity_registry, "_bass_level_select")
    assert entity_id is not None

    callbacks = mock_bravia_quad_client.register_notification_callback.call_args_list
    bass_callback = None
    for call in callbacks:
        if call[0][0] == "main.bassstep":
            bass_callback = call[0][1]
            break

    assert bass_callback is not None

    # Trigger callback with value outside 0-2 range (e.g., 5 = subwoofer mode)
    await bass_callback("5")
    await hass.async_block_till_done()

    # Entry should now have subwoofer detected
    entry = hass.config_entries.async_get_entry(mock_config_entry_no_subwoofer.entry_id)
    assert entry is not None
    assert entry.data.get(CONF_HAS_SUBWOOFER) is True
