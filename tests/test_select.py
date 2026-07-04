"""Tests for the Bravia Quad select platform."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.const import ATTR_ENTITY_ID, CONF_HOST, Platform
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.bravia_quad.const import (
    CONF_HAS_SUBWOOFER,
    CONF_TRANSPORT,
    DOMAIN,
    TRANSPORT_TCP,
)

from .conftest import get_entity_id_by_unique_id_suffix

if TYPE_CHECKING:
    from unittest.mock import MagicMock

    from homeassistant.core import HomeAssistant

SELECT_DOMAIN = "select"


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
            CONF_TRANSPORT: TRANSPORT_TCP,
        },
        unique_id="192.168.1.100",
        entry_id="test_entry_id_no_sub",
    )


# =============================================================================
# Select entity setup
# =============================================================================


@pytest.mark.usefixtures("init_integration")
async def test_select_entities(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
) -> None:
    """Test select entities are created correctly."""
    expected_entities = {
        "_drc": "auto",
    }

    for suffix, expected_state in expected_entities.items():
        entity_id = get_entity_id_by_unique_id_suffix(entity_registry, suffix)
        assert entity_id is not None, f"Entity with suffix {suffix} not found"

        state = hass.states.get(entity_id)
        assert state is not None, f"State for {entity_id} not found"
        assert state.state == expected_state, f"Expected {expected_state} for {suffix}"

    assert get_entity_id_by_unique_id_suffix(entity_registry, "_input") is None


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
    mock_bravia_http_client: MagicMock,
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


@pytest.mark.usefixtures("init_integration")
async def test_new_select_entities(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
) -> None:
    """Test that new select entities are created."""
    for suffix in (
        "_hdmi_passthrough",
        "_imax_mode",
        "_bt_connection_quality",
        "_hdmi_standby_link",
        "_audio_return_channel",
    ):
        entity_id = get_entity_id_by_unique_id_suffix(entity_registry, suffix)
        assert entity_id is not None, f"Entity with suffix {suffix} not found"
        state = hass.states.get(entity_id)
        assert state is not None, f"State for {entity_id} not found"

    # Dual mono is disabled by default (option values unconfirmed)
    entity_id = get_entity_id_by_unique_id_suffix(entity_registry, "_dual_mono")
    assert entity_id is not None
    assert hass.states.get(entity_id) is None


@pytest.mark.usefixtures("init_integration")
async def test_hdmi_passthrough_select_option(
    hass: HomeAssistant,
    mock_bravia_quad_client: MagicMock,
    entity_registry: er.EntityRegistry,
) -> None:
    """Test selecting HDMI passthrough option."""
    mock_bravia_quad_client.async_get_hdmi_passthrough = AsyncMock(return_value="on")
    entity_id = get_entity_id_by_unique_id_suffix(entity_registry, "_hdmi_passthrough")
    assert entity_id is not None
    await hass.services.async_call(
        "select",
        "select_option",
        {"entity_id": entity_id, "option": "on"},
        blocking=True,
    )
    mock_bravia_quad_client.async_set_hdmi_passthrough.assert_called_once_with("on")


@pytest.mark.usefixtures("init_integration_all")
async def test_dual_mono_select_option(
    hass: HomeAssistant,
    mock_bravia_quad_client: MagicMock,
    entity_registry: er.EntityRegistry,
) -> None:
    """Test selecting dual mono option."""
    mock_bravia_quad_client.async_get_dual_mono = AsyncMock(return_value="sub")
    entity_id = get_entity_id_by_unique_id_suffix(entity_registry, "_dual_mono")
    assert entity_id is not None
    await hass.services.async_call(
        "select",
        "select_option",
        {"entity_id": entity_id, "option": "sub"},
        blocking=True,
    )
    mock_bravia_quad_client.async_set_dual_mono.assert_called_once_with("sub")


@pytest.mark.usefixtures("init_integration")
async def test_audio_return_channel_select_option(
    hass: HomeAssistant,
    mock_bravia_quad_client: MagicMock,
    entity_registry: er.EntityRegistry,
) -> None:
    """Test selecting a stable audio return channel option with re-read."""
    mock_bravia_quad_client.async_get_audio_return_channel = AsyncMock(
        return_value="off"
    )
    entity_id = get_entity_id_by_unique_id_suffix(
        entity_registry, "_audio_return_channel"
    )
    assert entity_id is not None
    await hass.services.async_call(
        "select",
        "select_option",
        {"entity_id": entity_id, "option": "off"},
        blocking=True,
    )
    mock_bravia_quad_client.async_set_audio_return_channel.assert_called_once_with(
        "off"
    )
    state = hass.states.get(entity_id)
    assert state is not None
    assert state.state == "off"


@pytest.mark.usefixtures("init_integration")
async def test_bt_connection_quality_select_option(
    hass: HomeAssistant,
    mock_bravia_quad_client: MagicMock,
    entity_registry: er.EntityRegistry,
) -> None:
    """Test selecting Bluetooth connection quality."""
    mock_bravia_quad_client.async_get_bt_connection_quality = AsyncMock(
        return_value="priorityconnection"
    )
    entity_id = get_entity_id_by_unique_id_suffix(
        entity_registry, "_bt_connection_quality"
    )
    assert entity_id is not None
    await hass.services.async_call(
        "select",
        "select_option",
        {"entity_id": entity_id, "option": "priorityconnection"},
        blocking=True,
    )
    mock_bravia_quad_client.async_set_bt_connection_quality.assert_called_once_with(
        "priorityconnection"
    )


@pytest.mark.usefixtures("init_integration")
async def test_imax_mode_select_shows_auto(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
) -> None:
    """Test IMAX mode select shows auto, not switch ON."""
    entity_id = get_entity_id_by_unique_id_suffix(entity_registry, "_imax_mode")
    assert entity_id is not None
    state = hass.states.get(entity_id)
    assert state is not None
    assert state.state == "auto"
    assert state.domain == "select"


@pytest.mark.usefixtures("init_integration")
async def test_imax_mode_select_option_stable(
    hass: HomeAssistant,
    mock_bravia_quad_client: MagicMock,
    entity_registry: er.EntityRegistry,
) -> None:
    """Test selecting a stable IMAX mode updates state."""
    mock_bravia_quad_client.async_get_imax_mode = AsyncMock(return_value="auto")
    entity_id = get_entity_id_by_unique_id_suffix(entity_registry, "_imax_mode")
    assert entity_id is not None
    await hass.services.async_call(
        "select",
        "select_option",
        {"entity_id": entity_id, "option": "auto"},
        blocking=True,
    )
    mock_bravia_quad_client.async_set_imax_mode.assert_called_once_with("auto")
    assert hass.states.get(entity_id).state == "auto"


@pytest.mark.usefixtures("init_integration")
async def test_imax_mode_select_option_reverts(
    hass: HomeAssistant,
    mock_bravia_quad_client: MagicMock,
    entity_registry: er.EntityRegistry,
) -> None:
    """Test IMAX mode stays auto when device rejects off."""
    mock_bravia_quad_client.async_get_imax_mode = AsyncMock(return_value="auto")
    mock_bravia_quad_client.async_set_imax_mode = AsyncMock(return_value=True)

    entity_id = get_entity_id_by_unique_id_suffix(entity_registry, "_imax_mode")
    assert entity_id is not None

    with pytest.raises(Exception, match="kept IMAX mode"):
        await hass.services.async_call(
            "select",
            "select_option",
            {"entity_id": entity_id, "option": "off"},
            blocking=True,
        )

    assert hass.states.get(entity_id).state == "auto"
    mock_bravia_quad_client.async_set_imax_mode.assert_called_once_with("off")


@pytest.mark.usefixtures("init_integration")
async def test_audio_return_channel_earc_reverts(
    hass: HomeAssistant,
    mock_bravia_quad_client: MagicMock,
    entity_registry: er.EntityRegistry,
) -> None:
    """Test eARC selection fails when device reports arc."""
    mock_bravia_quad_client.async_get_audio_return_channel = AsyncMock(
        return_value="arc"
    )
    mock_bravia_quad_client.async_set_audio_return_channel = AsyncMock(
        return_value=True
    )
    entity_id = get_entity_id_by_unique_id_suffix(
        entity_registry, "_audio_return_channel"
    )
    assert entity_id is not None

    with pytest.raises(Exception, match="kept audio return channel"):
        await hass.services.async_call(
            "select",
            "select_option",
            {"entity_id": entity_id, "option": "earc"},
            blocking=True,
        )

    assert hass.states.get(entity_id).state == "arc"
    mock_bravia_quad_client.async_set_audio_return_channel.assert_called_once_with(
        "earc"
    )
