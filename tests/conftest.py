"""Fixtures for the Bravia Quad integration tests."""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.const import CONF_HOST, Platform
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.bravia_quad.bravia_http_client import (
    DeviceDetails,
    FirmwareUpdateStatus,
    LatestFirmwareInfo,
    SystemInfo,
)
from custom_components.bravia_quad.const import (
    CONF_HAS_SUBWOOFER,
    CONF_TRANSPORT,
    DOMAIN,
    TRANSPORT_TCP,
)

if TYPE_CHECKING:
    from collections.abc import Generator

    from homeassistant.core import HomeAssistant


REPO_ROOT = Path(__file__).resolve().parents[1]


def frida_fixture_dir() -> Path:
    """Gitignored Frida wire captures; override with BRAVIA_QUAD_FRIDA_FIXTURE_DIR."""
    return Path(
        os.environ.get("BRAVIA_QUAD_FRIDA_FIXTURE_DIR", REPO_ROOT / ".cache/frida")
    )


def get_entity_id_by_unique_id_suffix(
    entity_registry: er.EntityRegistry,
    suffix: str,
    *,
    platform: str | None = None,
) -> str | None:
    """Get entity_id from the registry by unique_id suffix."""
    for entry in entity_registry.entities.values():
        if not entry.unique_id or not entry.unique_id.endswith(suffix):
            continue
        if platform is not None and entry.domain != platform:
            continue
        # `_volume` also matches `_advanced_auto_volume` via endswith.
        if suffix == "_volume" and entry.unique_id.endswith("_advanced_auto_volume"):
            continue
        return entry.entity_id
    return None


async def enable_entity(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    entity_registry: er.EntityRegistry,
    entity_id: str,
    platforms: list[Platform],
) -> None:
    """Enable a disabled entity and reload the integration."""
    entity_registry.async_update_entity(entity_id, disabled_by=None)
    with patch("custom_components.bravia_quad.PLATFORMS", platforms):
        await hass.config_entries.async_reload(mock_config_entry.entry_id)
        await hass.async_block_till_done()


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(
    enable_custom_integrations: None,
) -> None:
    """Enable custom integrations for all tests."""
    return


@pytest.fixture(autouse=True)
def mock_zeroconf() -> Generator[None]:
    """Mock zeroconf to prevent socket errors in tests."""
    with patch(
        "homeassistant.components.zeroconf.async_setup",
        return_value=True,
    ):
        yield


@pytest.fixture
def mock_config_entry() -> MockConfigEntry:
    """Return the default mocked config entry."""
    return MockConfigEntry(
        title="Bravia Quad",
        domain=DOMAIN,
        data={
            CONF_HOST: "192.168.1.100",
            CONF_HAS_SUBWOOFER: True,
            CONF_TRANSPORT: TRANSPORT_TCP,
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
            CONF_HAS_SUBWOOFER: False,
            CONF_TRANSPORT: TRANSPORT_TCP,
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


def _setup_feature_mocks(client: MagicMock) -> None:  # noqa: PLR0915
    """Configure feature-specific mock attributes on the client."""
    # Power
    client.async_get_power = AsyncMock(return_value="on")
    client.async_set_power = AsyncMock(return_value=True)
    client.power_state = "on"

    # Volume
    client.async_get_volume = AsyncMock(return_value=50)
    client.async_set_volume = AsyncMock(return_value=True)
    client.volume = 50
    client.volume_step_interval = 0

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

    # Advanced Auto Volume
    client.async_get_aav = AsyncMock(return_value="off")
    client.async_set_aav = AsyncMock(return_value=True)
    client.aav = "off"

    # Mute
    client.async_get_mute = AsyncMock(return_value="off")
    client.async_set_mute = AsyncMock(return_value=True)
    client.mute = "off"

    # Device identity
    client.async_get_mac_address = AsyncMock(return_value="aa:bb:cc:dd:ee:ff")
    client.async_get_serial_number = AsyncMock(return_value="1234567")
    client.async_get_firmware_version = AsyncMock(return_value="001.100")
    client.async_get_model_type = AsyncMock(return_value="HT-A9M2")
    client.async_get_manufacturer = AsyncMock(return_value="SONY")
    client.serial_number = "1234567"
    client.firmware_version = "001.100"
    client.model_type = "HT-A9M2"
    client.manufacturer = "SONY"
    client.async_get_device_name = AsyncMock(return_value="Test BRAVIA Theatre Quad")

    # HDMI Passthrough
    client.async_get_hdmi_passthrough = AsyncMock(return_value="auto")
    client.async_set_hdmi_passthrough = AsyncMock(return_value=True)

    # Dual Mono
    client.async_get_dual_mono = AsyncMock(return_value="main")
    client.async_set_dual_mono = AsyncMock(return_value=True)

    # Auto Update
    client.async_get_auto_update = AsyncMock(return_value="off")
    client.async_set_auto_update = AsyncMock(return_value=True)
    client.auto_update = "off"

    # IMAX Mode
    client.async_get_imax_mode = AsyncMock(return_value="auto")
    client.async_set_imax_mode = AsyncMock(return_value=True)
    client.imax_mode = "auto"

    # AV Sync
    client.async_get_av_sync = AsyncMock(return_value=0)
    client.async_set_av_sync = AsyncMock(return_value=True)

    # TV AV Sync
    client.async_get_tv_av_sync = AsyncMock(return_value=0)
    client.async_set_tv_av_sync = AsyncMock(return_value=True)

    # Bluetooth Connection Quality
    client.async_get_bt_connection_quality = AsyncMock(return_value="prioritysound")
    client.async_set_bt_connection_quality = AsyncMock(return_value=True)

    # External Control
    client.async_get_external_control = AsyncMock(return_value="on")
    client.async_set_external_control = AsyncMock(return_value=True)

    # HDMI Standby Link
    client.async_get_hdmi_standby_link = AsyncMock(return_value="auto")
    client.async_set_hdmi_standby_link = AsyncMock(return_value=True)

    # Net/BT Standby
    client.async_get_net_bt_standby = AsyncMock(return_value="off")
    client.async_set_net_bt_standby = AsyncMock(return_value=True)

    # Voice Zoom
    client.async_get_voice_zoom = AsyncMock(return_value="off")
    client.async_set_voice_zoom = AsyncMock(return_value=True)
    client.voice_zoom = "off"

    # Audio Return Channel
    client.async_get_audio_return_channel = AsyncMock(return_value="arc")
    client.async_set_audio_return_channel = AsyncMock(return_value=True)

    # Voice Zoom Level (read-only)
    client.async_get_voice_zoom_level = AsyncMock(return_value=1)

    # Diagnostic sensors (read-only)
    client.async_get_timezone = AsyncMock(return_value="America/New_York|-300")
    client.async_get_temperature = AsyncMock(return_value="F:134,C:57")
    client.async_get_360ssm = AsyncMock(return_value="on")
    client.async_get_network_mode = AsyncMock(return_value="wired")
    client.async_get_ip_address = AsyncMock(return_value="192.168.1.100")
    client.async_get_device_name = AsyncMock(return_value="Test BRAVIA Theatre Quad")
    client.async_get_destination = AsyncMock(return_value="us")
    client.async_get_language = AsyncMock(return_value="english")
    client.async_get_dhcp = AsyncMock(return_value="on")


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

        _setup_feature_mocks(client)

        # Send command (for bluetooth pairing)
        client.async_send_command = AsyncMock(return_value={"value": "ACK"})

        # Notification callbacks
        client.register_notification_callback = MagicMock()
        client.unregister_notification_callback = MagicMock()

        # Availability
        client.register_availability_callback = MagicMock()
        client.unregister_availability_callback = MagicMock()
        client.is_connected = True

        yield client


@pytest.fixture(autouse=True)
def mock_bravia_http_client() -> Generator[MagicMock]:
    """Return a mocked BraviaHttpClient."""
    with patch(
        "custom_components.bravia_quad.BraviaHttpClient",
        autospec=True,
    ) as client_mock:
        client = client_mock.return_value

        client.reachable = True
        client.async_probe_reachable = AsyncMock(return_value=True)
        client.async_get_system_info = AsyncMock(
            return_value=SystemInfo(version="001.100", model_name="BRAVIA Theatre Quad")
        )
        client.async_get_device_details = AsyncMock(
            return_value=DeviceDetails(
                device_name="Living Room",
                connection_type="wired",
                internet="connected",
                ipv4_address="192.168.1.100",
                ipv6_address="fe80::1",
                wifi_signal=None,
                mac_wired="aa:bb:cc:dd:ee:ff",
                mac_wireless="11:22:33:44:55:66",
            )
        )
        client.async_check_firmware_update = AsyncMock(
            return_value=FirmwareUpdateStatus.UP_TO_DATE
        )
        client.async_request_firmware_update = AsyncMock(return_value=True)
        client.async_get_latest_firmware_info = AsyncMock(
            return_value=LatestFirmwareInfo(
                version="001.200",
                release_url="https://www.sony.co.uk/electronics/support/software/00342249",
            )
        )

        yield client


@pytest.fixture
def platforms() -> list[Platform]:
    """Return the platforms to be loaded for this test."""
    return [
        Platform.BUTTON,
        Platform.NUMBER,
        Platform.SELECT,
        Platform.SENSOR,
        Platform.SWITCH,
    ]


async def _await_entity_states(
    hass: HomeAssistant, entity_ids: list[str], *, attempts: int = 50
) -> None:
    """Wait for enabled entities to appear in the state machine after reload."""
    for entity_id in entity_ids:
        for _ in range(attempts):
            if hass.states.get(entity_id) is not None:
                break
            await hass.async_block_till_done()
        else:
            msg = f"Entity state not available after reload: {entity_id}"
            raise AssertionError(msg)


async def _setup_integration_with_suffixes_enabled(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    platforms: list[Platform],
    suffixes: list[str],
) -> MockConfigEntry:
    """Set up the integration and enable disabled entities matching suffixes."""
    mock_config_entry.add_to_hass(hass)

    with patch("custom_components.bravia_quad.PLATFORMS", platforms):
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

    entity_registry = er.async_get(hass)
    entities_to_enable = []
    for suffix in suffixes:
        entity_id = get_entity_id_by_unique_id_suffix(entity_registry, suffix)
        if entity_id is None:
            continue
        entry = entity_registry.async_get(entity_id)
        if entry and entry.disabled_by is not None:
            entities_to_enable.append(entity_id)

    if entities_to_enable:
        for entity_id in entities_to_enable:
            entity_registry.async_update_entity(entity_id, disabled_by=None)
        with patch("custom_components.bravia_quad.PLATFORMS", platforms):
            await hass.config_entries.async_reload(mock_config_entry.entry_id)
            await hass.async_block_till_done()
        await _await_entity_states(hass, entities_to_enable)

    return mock_config_entry


@pytest.fixture
async def init_integration(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_bravia_quad_client: MagicMock,
    mock_bravia_http_client: MagicMock,
    platforms: list[Platform],
) -> MockConfigEntry:
    """Set up the Bravia Quad integration for testing."""
    mock_config_entry.add_to_hass(hass)

    with patch("custom_components.bravia_quad.PLATFORMS", platforms):
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

    return mock_config_entry


@pytest.fixture
async def init_integration_volume(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_bravia_quad_client: MagicMock,
    mock_bravia_http_client: MagicMock,
    platforms: list[Platform],
) -> MockConfigEntry:
    """Set up the integration with the volume step interval entity enabled."""
    return await _setup_integration_with_suffixes_enabled(
        hass,
        mock_config_entry,
        platforms,
        ["_volume", "_volume_step_interval"],
    )


@pytest.fixture
async def init_integration_all(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_bravia_quad_client: MagicMock,
    mock_bravia_http_client: MagicMock,
    platforms: list[Platform],
) -> MockConfigEntry:
    """Set up the Bravia Quad integration with all entities enabled."""
    mock_config_entry.add_to_hass(hass)

    with patch("custom_components.bravia_quad.PLATFORMS", platforms):
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

    # Enable all disabled entities
    entity_registry = er.async_get(hass)
    entities_to_enable = [
        entry.entity_id
        for entry in entity_registry.entities.values()
        if entry.disabled_by is not None
    ]

    if entities_to_enable:
        for entity_id in entities_to_enable:
            entity_registry.async_update_entity(entity_id, disabled_by=None)
        with patch("custom_components.bravia_quad.PLATFORMS", platforms):
            await hass.config_entries.async_reload(mock_config_entry.entry_id)
            await hass.async_block_till_done()
        await _await_entity_states(hass, entities_to_enable)

    return mock_config_entry


@pytest.fixture
def grpc_client() -> MagicMock:
    """Return a mocked BraviaGrpcClientAsync for entity unit tests."""
    client = MagicMock()
    client.is_connected = True
    client.notify_state = {}
    client.capability_paths = None
    client.capability_index = None
    client.volume_step_interval = 0
    client.async_exec_command = AsyncMock(return_value=True)
    client.add_state_callback = MagicMock()
    client.remove_state_callback = MagicMock()
    client.register_availability_callback = MagicMock()
    client.unregister_availability_callback = MagicMock()
    return client


@pytest.fixture
def grpc_entry() -> MagicMock:
    """Return a mocked config entry for gRPC entity unit tests."""
    entry = MagicMock()
    entry.unique_id = "serial123"
    entry.data = {}
    return entry
