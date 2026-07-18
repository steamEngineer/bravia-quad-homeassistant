"""Tests for the Bravia Quad sensor platform."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.const import Platform
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_component import async_update_entity

from custom_components.bravia_quad.bravia_http_client import DeviceDetails
from custom_components.bravia_quad.const import TRANSPORT_GRPC, TRANSPORT_TCP
from custom_components.bravia_quad.sensor import http_sensor_descriptions
from custom_components.bravia_quad.transport import GRPC_PATH_MAC_WIRED

from .conftest import get_entity_id_by_unique_id_suffix

if TYPE_CHECKING:
    from unittest.mock import MagicMock

    from homeassistant.core import HomeAssistant
    from pytest_homeassistant_custom_component.common import MockConfigEntry


@pytest.fixture
def platforms() -> list[Platform]:
    """Override platforms to only load sensors."""
    return [Platform.SENSOR]


def test_http_mac_wired_omitted_when_grpc_caps_lack_wired_path() -> None:
    """A8-shaped caps: no HTTP wired MAC when GetCapabilities omits the path."""
    keys = {
        d.key
        for d in http_sensor_descriptions(
            transport=TRANSPORT_GRPC,
            capability_paths=frozenset(
                {
                    "system_setting.ipv4_address",
                    "system_setting.wifi_mac_address_wireless",
                }
            ),
        )
    }
    assert "mac_wired" not in keys
    assert "mac_wireless" in keys
    assert "internet" in keys


def test_http_mac_wired_kept_when_grpc_caps_include_wired_path() -> None:
    """Quad-shaped caps: HTTP wired MAC remains when the gRPC path is advertised."""
    keys = {
        d.key
        for d in http_sensor_descriptions(
            transport=TRANSPORT_GRPC,
            capability_paths=frozenset({GRPC_PATH_MAC_WIRED}),
        )
    }
    assert "mac_wired" in keys


def test_http_mac_wired_kept_on_caps_soft_fallback() -> None:
    """Soft-fallback (caps None): keep HTTP wired MAC like gRPC mapped soft-allow."""
    keys = {
        d.key
        for d in http_sensor_descriptions(
            transport=TRANSPORT_GRPC,
            capability_paths=None,
        )
    }
    assert "mac_wired" in keys


def test_http_mac_wired_kept_on_tcp_transport() -> None:
    """TCP transport always registers HTTP wired MAC (no gRPC caps gate)."""
    keys = {
        d.key
        for d in http_sensor_descriptions(
            transport=TRANSPORT_TCP,
            capability_paths=frozenset(),
        )
    }
    assert "mac_wired" in keys


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


@pytest.mark.usefixtures("init_integration")
async def test_http_sensor_internet(
    hass: HomeAssistant,
) -> None:
    """Test HTTP internet status sensor value."""
    state = hass.states.get("sensor.bravia_theatre_internet")
    assert state is not None
    assert state.state == "connected"


@pytest.mark.usefixtures("mock_bravia_quad_client")
async def test_http_sensors_skipped_when_management_port_unreachable(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_bravia_http_client: MagicMock,
) -> None:
    """No HTTP diagnostic sensors when the :54545 probe fails."""
    mock_bravia_http_client.reachable = False
    mock_bravia_http_client.async_probe_reachable = AsyncMock(return_value=False)
    mock_config_entry.add_to_hass(hass)
    with patch("custom_components.bravia_quad.PLATFORMS", [Platform.SENSOR]):
        assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

    assert hass.states.get("sensor.bravia_theatre_internet") is None


@pytest.mark.usefixtures("init_integration_all")
async def test_http_disabled_sensors_when_enabled(
    hass: HomeAssistant,
) -> None:
    """Test disabled-by-default HTTP sensors show values when enabled."""
    ipv6 = hass.states.get("sensor.bravia_theatre_ip_address_ipv6")
    assert ipv6 is not None
    assert ipv6.state == "fe80::1"


@pytest.mark.usefixtures("init_integration_all")
async def test_ipv6_multi_address_separated_by_newline(
    hass: HomeAssistant,
    mock_bravia_http_client: MagicMock,
) -> None:
    """Test comma-separated IPv6 addresses are split by newline."""
    mock_bravia_http_client.async_get_device_details.return_value = DeviceDetails(
        ipv6_address="2001:db8::1/64,2001:db8::2/128",
    )

    await async_update_entity(hass, "sensor.bravia_theatre_ip_address_ipv6")
    await hass.async_block_till_done()

    state = hass.states.get("sensor.bravia_theatre_ip_address_ipv6")
    assert state is not None
    assert state.state == "2001:db8::1/64\n2001:db8::2/128"


@pytest.mark.usefixtures("init_integration")
async def test_http_sensor_unavailable_when_unreachable(
    hass: HomeAssistant,
    mock_bravia_http_client: MagicMock,
) -> None:
    """Test HTTP sensor goes unavailable when HTTP API returns empty data."""
    mock_bravia_http_client.async_get_device_details.return_value = DeviceDetails()

    await async_update_entity(hass, "sensor.bravia_theatre_internet")
    await hass.async_block_till_done()

    state = hass.states.get("sensor.bravia_theatre_internet")
    assert state is not None
    assert state.state == "unavailable"


@pytest.mark.usefixtures("init_integration")
async def test_http_sensor_recovers_from_unavailable(
    hass: HomeAssistant,
    mock_bravia_http_client: MagicMock,
) -> None:
    """Test HTTP sensor recovers when HTTP API returns data again."""
    mock_bravia_http_client.async_get_device_details.return_value = DeviceDetails()
    await async_update_entity(hass, "sensor.bravia_theatre_internet")
    await hass.async_block_till_done()

    state = hass.states.get("sensor.bravia_theatre_internet")
    assert state.state == "unavailable"

    mock_bravia_http_client.async_get_device_details.return_value = DeviceDetails(
        internet="connected",
    )
    await async_update_entity(hass, "sensor.bravia_theatre_internet")
    await hass.async_block_till_done()

    state = hass.states.get("sensor.bravia_theatre_internet")
    assert state.state == "connected"
