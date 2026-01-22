"""Tests for the Bravia Quad media player platform."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest
from homeassistant.components.media_player import (
    ATTR_INPUT_SOURCE,
    ATTR_MEDIA_VOLUME_LEVEL,
    DOMAIN as MEDIA_PLAYER_DOMAIN,
    SERVICE_SELECT_SOURCE,
    SERVICE_TURN_OFF,
    SERVICE_TURN_ON,
    SERVICE_VOLUME_DOWN,
    SERVICE_VOLUME_SET,
    SERVICE_VOLUME_UP,
    MediaPlayerEntityFeature,
    MediaPlayerState,
)
from homeassistant.const import ATTR_ENTITY_ID, ATTR_SUPPORTED_FEATURES, Platform
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.bravia_quad.const import DOMAIN

if TYPE_CHECKING:
    from unittest.mock import MagicMock

    from homeassistant.core import HomeAssistant
    from homeassistant.helpers import entity_registry as er


@pytest.fixture
def platforms() -> list[Platform]:
    """Return the platforms to be loaded for this test."""
    return [Platform.MEDIA_PLAYER]


@pytest.fixture
async def init_integration_with_media_player(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_bravia_quad_client: MagicMock,
    entity_registry: er.EntityRegistry,
    platforms: list[Platform],
) -> MockConfigEntry:
    """Set up the integration with the media player entity enabled."""
    mock_config_entry.add_to_hass(hass)

    with patch("custom_components.bravia_quad.PLATFORMS", platforms):
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

    # Enable the disabled media player entity
    for entry in entity_registry.entities.values():
        if entry.platform == DOMAIN and entry.domain == MEDIA_PLAYER_DOMAIN:
            entity_registry.async_update_entity(entry.entity_id, disabled_by=None)
            break

    await hass.config_entries.async_reload(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    return mock_config_entry


def _get_media_player_entity_id(hass: HomeAssistant) -> str:
    """Get the media player entity ID."""
    entity_ids = [
        entity_id
        for entity_id in hass.states.async_entity_ids(MEDIA_PLAYER_DOMAIN)
        if entity_id.startswith(f"{MEDIA_PLAYER_DOMAIN}.{DOMAIN}")
        or entity_id.startswith(f"{MEDIA_PLAYER_DOMAIN}.bravia")
    ]
    assert len(entity_ids) == 1, f"Expected 1 media player entity, found {entity_ids}"
    return entity_ids[0]


@pytest.mark.usefixtures("init_integration_with_media_player")
async def test_media_player_entity_created(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
) -> None:
    """Test media player entity is created correctly."""
    entity_id = _get_media_player_entity_id(hass)
    state = hass.states.get(entity_id)

    assert state is not None
    assert state.state == MediaPlayerState.ON

    # Verify supported features
    expected_features = (
        MediaPlayerEntityFeature.TURN_ON
        | MediaPlayerEntityFeature.TURN_OFF
        | MediaPlayerEntityFeature.VOLUME_SET
        | MediaPlayerEntityFeature.VOLUME_STEP
        | MediaPlayerEntityFeature.SELECT_SOURCE
    )
    assert state.attributes[ATTR_SUPPORTED_FEATURES] == expected_features

    # Verify initial attributes
    assert state.attributes[ATTR_MEDIA_VOLUME_LEVEL] == 0.5  # 50/100
    assert state.attributes[ATTR_INPUT_SOURCE] == "TV (eARC)"


@pytest.mark.usefixtures("init_integration_with_media_player")
async def test_media_player_turn_on(
    hass: HomeAssistant,
    mock_bravia_quad_client: MagicMock,
) -> None:
    """Test turning on the media player."""
    entity_id = _get_media_player_entity_id(hass)

    mock_bravia_quad_client.async_set_power.return_value = True

    await hass.services.async_call(
        MEDIA_PLAYER_DOMAIN,
        SERVICE_TURN_ON,
        {ATTR_ENTITY_ID: entity_id},
        blocking=True,
    )

    mock_bravia_quad_client.async_set_power.assert_called_once_with("on")


@pytest.mark.usefixtures("init_integration_with_media_player")
async def test_media_player_turn_off(
    hass: HomeAssistant,
    mock_bravia_quad_client: MagicMock,
) -> None:
    """Test turning off the media player."""
    entity_id = _get_media_player_entity_id(hass)

    mock_bravia_quad_client.async_set_power.return_value = True

    await hass.services.async_call(
        MEDIA_PLAYER_DOMAIN,
        SERVICE_TURN_OFF,
        {ATTR_ENTITY_ID: entity_id},
        blocking=True,
    )

    mock_bravia_quad_client.async_set_power.assert_called_once_with("off")

    # Verify state updated
    state = hass.states.get(entity_id)
    assert state.state == MediaPlayerState.OFF


@pytest.mark.usefixtures("init_integration_with_media_player")
async def test_media_player_set_volume(
    hass: HomeAssistant,
    mock_bravia_quad_client: MagicMock,
) -> None:
    """Test setting volume level."""
    entity_id = _get_media_player_entity_id(hass)

    mock_bravia_quad_client.async_set_volume.return_value = True

    await hass.services.async_call(
        MEDIA_PLAYER_DOMAIN,
        SERVICE_VOLUME_SET,
        {
            ATTR_ENTITY_ID: entity_id,
            ATTR_MEDIA_VOLUME_LEVEL: 0.75,
        },
        blocking=True,
    )

    # Volume step interval is 0, so direct set
    mock_bravia_quad_client.async_set_volume.assert_called_once_with(75)

    # Verify state updated
    state = hass.states.get(entity_id)
    assert state.attributes[ATTR_MEDIA_VOLUME_LEVEL] == 0.75


@pytest.mark.usefixtures("init_integration_with_media_player")
async def test_media_player_volume_up(
    hass: HomeAssistant,
    mock_bravia_quad_client: MagicMock,
) -> None:
    """Test volume up."""
    entity_id = _get_media_player_entity_id(hass)

    mock_bravia_quad_client.async_set_volume.return_value = True

    await hass.services.async_call(
        MEDIA_PLAYER_DOMAIN,
        SERVICE_VOLUME_UP,
        {ATTR_ENTITY_ID: entity_id},
        blocking=True,
    )

    # Default volume is 50, so should call with 51
    mock_bravia_quad_client.async_set_volume.assert_called_once_with(51)


@pytest.mark.usefixtures("init_integration_with_media_player")
async def test_media_player_volume_down(
    hass: HomeAssistant,
    mock_bravia_quad_client: MagicMock,
) -> None:
    """Test volume down."""
    entity_id = _get_media_player_entity_id(hass)

    mock_bravia_quad_client.async_set_volume.return_value = True

    await hass.services.async_call(
        MEDIA_PLAYER_DOMAIN,
        SERVICE_VOLUME_DOWN,
        {ATTR_ENTITY_ID: entity_id},
        blocking=True,
    )

    # Default volume is 50, so should call with 49
    mock_bravia_quad_client.async_set_volume.assert_called_once_with(49)


@pytest.mark.usefixtures("init_integration_with_media_player")
async def test_media_player_select_source(
    hass: HomeAssistant,
    mock_bravia_quad_client: MagicMock,
) -> None:
    """Test selecting input source."""
    entity_id = _get_media_player_entity_id(hass)

    mock_bravia_quad_client.async_set_input.return_value = True

    await hass.services.async_call(
        MEDIA_PLAYER_DOMAIN,
        SERVICE_SELECT_SOURCE,
        {
            ATTR_ENTITY_ID: entity_id,
            ATTR_INPUT_SOURCE: "HDMI In",
        },
        blocking=True,
    )

    mock_bravia_quad_client.async_set_input.assert_called_once_with("hdmi1")

    # Verify state updated
    state = hass.states.get(entity_id)
    assert state.attributes[ATTR_INPUT_SOURCE] == "HDMI In"


@pytest.mark.usefixtures("init_integration_with_media_player")
async def test_media_player_select_source_spotify(
    hass: HomeAssistant,
    mock_bravia_quad_client: MagicMock,
) -> None:
    """Test selecting Spotify source."""
    entity_id = _get_media_player_entity_id(hass)

    mock_bravia_quad_client.async_set_input.return_value = True

    await hass.services.async_call(
        MEDIA_PLAYER_DOMAIN,
        SERVICE_SELECT_SOURCE,
        {
            ATTR_ENTITY_ID: entity_id,
            ATTR_INPUT_SOURCE: "Spotify",
        },
        blocking=True,
    )

    mock_bravia_quad_client.async_set_input.assert_called_once_with("spotify")


@pytest.mark.usefixtures("init_integration_with_media_player")
async def test_media_player_source_list(
    hass: HomeAssistant,
) -> None:
    """Test source list contains all expected sources."""
    entity_id = _get_media_player_entity_id(hass)
    state = hass.states.get(entity_id)

    expected_sources = ["TV (eARC)", "HDMI In", "Spotify", "Bluetooth", "Airplay"]
    assert state.attributes["source_list"] == expected_sources


@pytest.mark.usefixtures("init_integration_with_media_player")
async def test_media_player_notification_callbacks_registered(
    hass: HomeAssistant,
    mock_bravia_quad_client: MagicMock,
) -> None:
    """Test that notification callbacks are registered for all features."""
    # Verify callbacks were registered for power, volume, and input
    registered_features = [
        call[0][0]
        for call in mock_bravia_quad_client.register_notification_callback.call_args_list
    ]

    assert "main.power" in registered_features
    assert "main.volumestep" in registered_features
    assert "main.input" in registered_features


@pytest.mark.usefixtures("init_integration_with_media_player")
async def test_media_player_off_state(
    hass: HomeAssistant,
    mock_bravia_quad_client: MagicMock,
) -> None:
    """Test media player shows OFF state when power is off."""
    # Setup with power off
    mock_bravia_quad_client.power_state = "off"

    # Reload to get new state
    entity_id = _get_media_player_entity_id(hass)

    # Simulate power off via service
    mock_bravia_quad_client.async_set_power.return_value = True
    await hass.services.async_call(
        MEDIA_PLAYER_DOMAIN,
        SERVICE_TURN_OFF,
        {ATTR_ENTITY_ID: entity_id},
        blocking=True,
    )

    state = hass.states.get(entity_id)
    assert state.state == MediaPlayerState.OFF
