"""Tests for the Bravia Quad integration initialization."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import Platform

from custom_components.bravia_quad.const import DOMAIN

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from pytest_homeassistant_custom_component.common import MockConfigEntry


@pytest.fixture
def platforms() -> list[Platform]:
    """Return the platforms to be loaded for this test."""
    return [Platform.SWITCH]


@pytest.mark.usefixtures("mock_bravia_quad_client")
async def test_setup_entry(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    platforms: list[Platform],
) -> None:
    """Test setup of a config entry."""
    mock_config_entry.add_to_hass(hass)

    with patch("custom_components.bravia_quad.PLATFORMS", platforms):
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

    assert mock_config_entry.state is ConfigEntryState.LOADED
    assert DOMAIN in hass.data
    assert mock_config_entry.entry_id in hass.data[DOMAIN]


@pytest.mark.usefixtures("mock_bravia_quad_client")
async def test_unload_entry(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    platforms: list[Platform],
) -> None:
    """Test unload of a config entry."""
    mock_config_entry.add_to_hass(hass)

    with patch("custom_components.bravia_quad.PLATFORMS", platforms):
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

    assert mock_config_entry.state is ConfigEntryState.LOADED

    await hass.config_entries.async_unload(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    assert mock_config_entry.state is ConfigEntryState.NOT_LOADED
    assert mock_config_entry.entry_id not in hass.data[DOMAIN]


async def test_setup_entry_connection_error(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test setup entry when connection fails."""
    mock_config_entry.add_to_hass(hass)

    with (
        patch(
            "custom_components.bravia_quad.BraviaQuadClient",
            autospec=True,
        ) as client_mock,
        patch("custom_components.bravia_quad.PLATFORMS", [Platform.SWITCH]),
    ):
        client = client_mock.return_value
        client.async_connect.side_effect = OSError("Connection refused")

        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

    assert mock_config_entry.state is ConfigEntryState.SETUP_RETRY


async def test_setup_entry_test_connection_error(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_bravia_quad_client: MagicMock,
) -> None:
    """Test setup entry when test connection fails."""
    mock_config_entry.add_to_hass(hass)

    mock_bravia_quad_client.async_test_connection.side_effect = TimeoutError(
        "Connection timeout"
    )

    with patch("custom_components.bravia_quad.PLATFORMS", [Platform.SWITCH]):
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

    assert mock_config_entry.state is ConfigEntryState.SETUP_RETRY
