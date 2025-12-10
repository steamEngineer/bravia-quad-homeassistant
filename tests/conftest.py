"""Fixtures for the Bravia Quad integration tests."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.const import CONF_HOST, CONF_NAME, Platform
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.bravia_quad.const import (
    CONF_HAS_SUBWOOFER,
    DOMAIN,
)

if TYPE_CHECKING:
    from collections.abc import Generator

    from homeassistant.core import HomeAssistant


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(
    enable_custom_integrations: None,
) -> None:
    """Enable custom integrations for all tests."""
    return


@pytest.fixture
def mock_config_entry() -> MockConfigEntry:
    """Return the default mocked config entry."""
    return MockConfigEntry(
        title="Bravia Quad",
        domain=DOMAIN,
        data={
            CONF_HOST: "192.168.1.100",
            CONF_NAME: "Bravia Quad",
            CONF_HAS_SUBWOOFER: True,
        },
        unique_id="192.168.1.100",
        entry_id="test_entry_id",  # Fixed entry_id for stable snapshots
    )


@pytest.fixture
def mock_config_entry_no_subwoofer() -> MockConfigEntry:
    """Return a mocked config entry without subwoofer."""
    return MockConfigEntry(
        title="Bravia Quad",
        domain=DOMAIN,
        data={
            CONF_HOST: "192.168.1.100",
            CONF_NAME: "Bravia Quad",
            CONF_HAS_SUBWOOFER: False,
        },
        unique_id="192.168.1.100",
        entry_id="test_entry_id_no_sub",  # Fixed entry_id for stable snapshots
    )


@pytest.fixture
def mock_setup_entry() -> Generator[None]:
    """Mock setting up a config entry."""
    with patch(
        "custom_components.bravia_quad.async_setup_entry",
        return_value=True,
    ):
        yield


@pytest.fixture
def mock_bravia_quad_client() -> Generator[MagicMock]:
    """Return a mocked BraviaQuadClient."""
    with (
        patch(
            "custom_components.bravia_quad.BraviaQuadClient",
            autospec=True,
        ) as client_mock,
        patch(
            "custom_components.bravia_quad.config_flow.BraviaQuadClient",
            new=client_mock,
        ),
    ):
        client = client_mock.return_value

        # Setup async methods
        client.async_connect = AsyncMock()
        client.async_disconnect = AsyncMock()
        client.async_test_connection = AsyncMock(return_value=True)
        client.async_detect_subwoofer = AsyncMock(return_value=True)
        client.async_listen_for_notifications = AsyncMock()
        client.async_fetch_all_states = AsyncMock()

        # Power
        client.async_get_power = AsyncMock(return_value="on")
        client.async_set_power = AsyncMock(return_value=True)
        client.power_state = "on"

        # Volume
        client.async_get_volume = AsyncMock(return_value=50)
        client.async_set_volume = AsyncMock(return_value=True)
        client.volume = 50

        # Input
        client.async_get_input = AsyncMock(return_value="tv")
        client.async_set_input = AsyncMock(return_value=True)
        client.input = "tv"

        # Rear level
        client.async_get_rear_level = AsyncMock(return_value=0)
        client.async_set_rear_level = AsyncMock(return_value=True)
        client.rear_level = 0

        # Bass level
        client.async_get_bass_level = AsyncMock(return_value=0)
        client.async_set_bass_level = AsyncMock(return_value=True)
        client.bass_level = 0

        # Voice enhancer
        client.async_get_voice_enhancer = AsyncMock(return_value="upoff")
        client.async_set_voice_enhancer = AsyncMock(return_value=True)
        client.voice_enhancer = "upoff"

        # Sound field
        client.async_get_sound_field = AsyncMock(return_value="off")
        client.async_set_sound_field = AsyncMock(return_value=True)
        client.sound_field = "off"

        # Night mode
        client.async_get_night_mode = AsyncMock(return_value="off")
        client.async_set_night_mode = AsyncMock(return_value=True)
        client.night_mode = "off"

        # HDMI CEC
        client.async_get_hdmi_cec = AsyncMock(return_value="off")
        client.async_set_hdmi_cec = AsyncMock(return_value=True)
        client.hdmi_cec = "off"

        # Auto standby
        client.async_get_auto_standby = AsyncMock(return_value="off")
        client.async_set_auto_standby = AsyncMock(return_value=True)
        client.auto_standby = "off"

        # Send command (for bluetooth pairing)
        client.async_send_command = AsyncMock(return_value={"value": "ACK"})

        # Notification callbacks
        client.register_notification_callback = MagicMock()

        yield client


@pytest.fixture
def platforms() -> list[Platform]:
    """Return the platforms to be loaded for this test."""
    return [Platform.BUTTON, Platform.NUMBER, Platform.SELECT, Platform.SWITCH]


@pytest.fixture
async def init_integration(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_bravia_quad_client: MagicMock,
    platforms: list[Platform],
) -> MockConfigEntry:
    """Set up the Bravia Quad integration for testing."""
    mock_config_entry.add_to_hass(hass)

    with patch("custom_components.bravia_quad.PLATFORMS", platforms):
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

    return mock_config_entry
