"""Tests for the Bravia Quad firmware update platform."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest
from homeassistant.components.update import DOMAIN as UPDATE_DOMAIN
from homeassistant.components.update import SERVICE_INSTALL
from homeassistant.const import ATTR_ENTITY_ID, Platform
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_component import async_update_entity

from custom_components.bravia_quad.bravia_http_client import (
    FirmwareUpdateStatus,
    LatestFirmwareInfo,
    SystemInfo,
)

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from pytest_homeassistant_custom_component.common import MockConfigEntry

ENTITY_ID = "update.bravia_theatre_firmware_update"


@pytest.fixture
def platforms() -> list[Platform]:
    """Return the platforms to load."""
    return [Platform.UPDATE]


@pytest.mark.usefixtures("init_integration")
async def test_update_entity_created(
    hass: HomeAssistant,
) -> None:
    """Test that the firmware update entity is created."""
    state = hass.states.get(ENTITY_ID)
    assert state is not None


@pytest.mark.usefixtures("init_integration")
async def test_update_entity_up_to_date(
    hass: HomeAssistant,
) -> None:
    """Test update entity shows up to date when no update available."""
    state = hass.states.get(ENTITY_ID)
    assert state is not None
    assert state.state == "off"
    assert state.attributes["installed_version"] == "001.100"
    assert state.attributes["latest_version"] == "001.100"


async def test_update_entity_update_available(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_bravia_quad_client: MagicMock,
    mock_bravia_http_client: MagicMock,
) -> None:
    """Test update entity detects available firmware update."""
    mock_bravia_http_client.async_check_firmware_update.return_value = (
        FirmwareUpdateStatus.UPDATE_AVAILABLE
    )
    mock_bravia_http_client.async_get_latest_firmware_info.return_value = (
        LatestFirmwareInfo(
            version="001.200",
            release_url="https://www.sony.co.uk/electronics/support/software/00342249",
        )
    )

    mock_config_entry.add_to_hass(hass)
    with patch("custom_components.bravia_quad.PLATFORMS", [Platform.UPDATE]):
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

    state = hass.states.get(ENTITY_ID)
    assert state is not None
    assert state.state == "on"
    assert state.attributes["installed_version"] == "001.100"
    assert state.attributes["latest_version"] == "001.200"
    assert (
        state.attributes["release_url"]
        == "https://www.sony.co.uk/electronics/support/software/00342249"
    )


async def test_update_entity_install(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_bravia_quad_client: MagicMock,
    mock_bravia_http_client: MagicMock,
) -> None:
    """Test triggering firmware install."""
    mock_bravia_http_client.async_check_firmware_update.return_value = (
        FirmwareUpdateStatus.UPDATE_AVAILABLE
    )

    mock_config_entry.add_to_hass(hass)
    with patch("custom_components.bravia_quad.PLATFORMS", [Platform.UPDATE]):
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

    await hass.services.async_call(
        UPDATE_DOMAIN,
        SERVICE_INSTALL,
        {ATTR_ENTITY_ID: ENTITY_ID},
        blocking=True,
    )

    mock_bravia_http_client.async_request_firmware_update.assert_called_once()


async def test_update_entity_install_failure(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_bravia_quad_client: MagicMock,
    mock_bravia_http_client: MagicMock,
) -> None:
    """Test firmware install failure raises error."""
    mock_bravia_http_client.async_check_firmware_update.return_value = (
        FirmwareUpdateStatus.UPDATE_AVAILABLE
    )
    mock_bravia_http_client.async_request_firmware_update.return_value = False

    mock_config_entry.add_to_hass(hass)
    with patch("custom_components.bravia_quad.PLATFORMS", [Platform.UPDATE]):
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            UPDATE_DOMAIN,
            SERVICE_INSTALL,
            {ATTR_ENTITY_ID: ENTITY_ID},
            blocking=True,
        )


@pytest.mark.usefixtures("init_integration")
async def test_update_entity_firmware_check_error(
    hass: HomeAssistant,
    mock_bravia_http_client: MagicMock,
) -> None:
    """Test update entity when firmware check returns error."""
    # Override return value for the update call
    mock_bravia_http_client.async_check_firmware_update.return_value = (
        FirmwareUpdateStatus.ERROR
    )

    await async_update_entity(hass, ENTITY_ID)
    await hass.async_block_till_done()

    # State should remain unchanged (still shows installed version)
    state = hass.states.get(ENTITY_ID)
    assert state is not None
    assert state.attributes["installed_version"] == "001.100"


@pytest.mark.usefixtures("init_integration")
async def test_update_entity_version_from_http(
    hass: HomeAssistant,
    mock_bravia_http_client: MagicMock,
) -> None:
    """Test update entity reads installed version from HTTP, not TCP."""
    mock_bravia_http_client.async_get_system_info.return_value = SystemInfo(
        version="001.200", model_name="BRAVIA Theatre Quad"
    )

    await async_update_entity(hass, ENTITY_ID)
    await hass.async_block_till_done()

    state = hass.states.get(ENTITY_ID)
    assert state is not None
    assert state.attributes["installed_version"] == "001.200"


async def test_update_entity_in_progress_after_install(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_bravia_quad_client: MagicMock,
    mock_bravia_http_client: MagicMock,
) -> None:
    """Test update entity shows in_progress after install is triggered."""
    mock_bravia_http_client.async_check_firmware_update.return_value = (
        FirmwareUpdateStatus.UPDATE_AVAILABLE
    )

    mock_config_entry.add_to_hass(hass)
    with patch("custom_components.bravia_quad.PLATFORMS", [Platform.UPDATE]):
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

    await hass.services.async_call(
        UPDATE_DOMAIN,
        SERVICE_INSTALL,
        {ATTR_ENTITY_ID: ENTITY_ID},
        blocking=True,
    )

    state = hass.states.get(ENTITY_ID)
    assert state is not None
    assert state.attributes["in_progress"] is not False


@pytest.mark.usefixtures("init_integration")
async def test_update_entity_version_persists_through_error(
    hass: HomeAssistant,
    mock_bravia_http_client: MagicMock,
) -> None:
    """Test installed version persists when HTTP API returns empty."""
    state = hass.states.get(ENTITY_ID)
    assert state.attributes["installed_version"] == "001.100"

    # Simulate HTTP failure: system info returns empty
    mock_bravia_http_client.async_get_system_info.return_value = SystemInfo()
    mock_bravia_http_client.async_check_firmware_update.return_value = (
        FirmwareUpdateStatus.ERROR
    )

    await async_update_entity(hass, ENTITY_ID)
    await hass.async_block_till_done()

    state = hass.states.get(ENTITY_ID)
    assert state.attributes["installed_version"] == "001.100"


async def test_update_entity_newer_version_fallback(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_bravia_quad_client: MagicMock,
    mock_bravia_http_client: MagicMock,
) -> None:
    """Test fallback to 'Newer version' when Sony server is unreachable."""
    mock_bravia_http_client.async_check_firmware_update.return_value = (
        FirmwareUpdateStatus.UPDATE_AVAILABLE
    )
    # Sony server returns empty (unreachable)
    mock_bravia_http_client.async_get_latest_firmware_info.return_value = (
        LatestFirmwareInfo()
    )

    mock_config_entry.add_to_hass(hass)
    with patch("custom_components.bravia_quad.PLATFORMS", [Platform.UPDATE]):
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

    state = hass.states.get(ENTITY_ID)
    assert state is not None
    assert state.state == "on"
    assert state.attributes["latest_version"] == "Newer version"


async def test_update_entity_tcp_reconnect_refreshes(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_bravia_quad_client: MagicMock,
    mock_bravia_http_client: MagicMock,
) -> None:
    """Test TCP reconnect triggers firmware status recheck."""
    mock_config_entry.add_to_hass(hass)
    with patch("custom_components.bravia_quad.PLATFORMS", [Platform.UPDATE]):
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

    # Capture the availability callback registered on the TCP client
    register_call = mock_bravia_quad_client.register_availability_callback
    assert register_call.call_count >= 1
    # The update entity's callback is the one registered via async_added_to_hass
    availability_cb = register_call.call_args_list[-1][0][0]

    # Change firmware version and simulate reconnect
    mock_bravia_http_client.async_get_system_info.return_value = SystemInfo(
        version="001.300", model_name="BRAVIA Theatre Quad"
    )
    availability_cb(True)
    await hass.async_block_till_done()

    state = hass.states.get(ENTITY_ID)
    assert state is not None
    assert state.attributes["installed_version"] == "001.300"
