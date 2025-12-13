"""Tests for the Bravia Quad config flow."""

from __future__ import annotations

from ipaddress import ip_address as make_ip_address
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, patch

from homeassistant.config_entries import SOURCE_DHCP, SOURCE_USER, SOURCE_ZEROCONF
from homeassistant.const import CONF_HOST, CONF_MAC, CONF_NAME
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers.service_info.dhcp import DhcpServiceInfo
from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.bravia_quad.const import CONF_HAS_SUBWOOFER, DOMAIN

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

TEST_HOST = "192.168.1.100"
TEST_MAC = "60:ff:9e:12:34:56"
TEST_MAC_FORMATTED = "60:ff:9e:12:34:56"


async def test_user_flow_success(hass: HomeAssistant) -> None:
    """Test successful user flow."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {}

    with patch(
        "custom_components.bravia_quad.config_flow.BraviaQuadClient",
        autospec=True,
    ) as client_mock:
        client = client_mock.return_value
        client.async_connect = AsyncMock()
        client.async_disconnect = AsyncMock()
        client.async_test_connection = AsyncMock(return_value=True)
        client.async_detect_subwoofer = AsyncMock(return_value=True)

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={
                CONF_HOST: TEST_HOST,
                CONF_NAME: "Living Room",
            },
        )
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Living Room"
    assert result["data"] == {
        CONF_HOST: TEST_HOST,
        CONF_NAME: "Living Room",
        CONF_HAS_SUBWOOFER: True,
    }
    # User flow uses host as unique_id (no MAC available)
    assert result["result"].unique_id == TEST_HOST


async def test_user_flow_success_no_subwoofer(hass: HomeAssistant) -> None:
    """Test successful user flow without subwoofer."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )

    with patch(
        "custom_components.bravia_quad.config_flow.BraviaQuadClient",
        autospec=True,
    ) as client_mock:
        client = client_mock.return_value
        client.async_connect = AsyncMock()
        client.async_disconnect = AsyncMock()
        client.async_test_connection = AsyncMock(return_value=True)
        client.async_detect_subwoofer = AsyncMock(return_value=False)

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={
                CONF_HOST: TEST_HOST,
                CONF_NAME: "Bravia Quad",
            },
        )
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_HAS_SUBWOOFER] is False


async def test_user_flow_connection_error(hass: HomeAssistant) -> None:
    """Test user flow when connection fails."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM

    with patch(
        "custom_components.bravia_quad.config_flow.BraviaQuadClient",
        autospec=True,
    ) as client_mock:
        client = client_mock.return_value
        client.async_connect = AsyncMock(side_effect=OSError("Connection refused"))
        client.async_disconnect = AsyncMock()

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={
                CONF_HOST: TEST_HOST,
                CONF_NAME: "Bravia Quad",
            },
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}


async def test_user_flow_test_connection_fails(hass: HomeAssistant) -> None:
    """Test user flow when test connection returns False."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )

    with patch(
        "custom_components.bravia_quad.config_flow.BraviaQuadClient",
        autospec=True,
    ) as client_mock:
        client = client_mock.return_value
        client.async_connect = AsyncMock()
        client.async_disconnect = AsyncMock()
        client.async_test_connection = AsyncMock(return_value=False)

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={
                CONF_HOST: TEST_HOST,
                CONF_NAME: "Bravia Quad",
            },
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}


async def test_user_flow_timeout_error(hass: HomeAssistant) -> None:
    """Test user flow when connection times out."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )

    with patch(
        "custom_components.bravia_quad.config_flow.BraviaQuadClient",
        autospec=True,
    ) as client_mock:
        client = client_mock.return_value
        client.async_connect = AsyncMock(side_effect=TimeoutError("Connection timeout"))
        client.async_disconnect = AsyncMock()

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={
                CONF_HOST: TEST_HOST,
                CONF_NAME: "Bravia Quad",
            },
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}


async def test_user_flow_duplicate_entry(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test user flow when entry already exists."""
    mock_config_entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )

    with patch(
        "custom_components.bravia_quad.config_flow.BraviaQuadClient",
        autospec=True,
    ) as client_mock:
        client = client_mock.return_value
        client.async_connect = AsyncMock()
        client.async_disconnect = AsyncMock()
        client.async_test_connection = AsyncMock(return_value=True)
        client.async_detect_subwoofer = AsyncMock(return_value=True)

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={
                CONF_HOST: TEST_HOST,  # Same host as mock_config_entry
                CONF_NAME: "Another Name",
            },
        )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_user_flow_unknown_error(hass: HomeAssistant) -> None:
    """Test user flow when an unknown error occurs."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )

    with patch(
        "custom_components.bravia_quad.config_flow.BraviaQuadClient",
        autospec=True,
    ) as client_mock:
        client = client_mock.return_value
        client.async_connect = AsyncMock()
        client.async_disconnect = AsyncMock()
        client.async_test_connection = AsyncMock(side_effect=RuntimeError("Unexpected"))

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={
                CONF_HOST: TEST_HOST,
                CONF_NAME: "Bravia Quad",
            },
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "unknown"}


async def test_zeroconf_discovery(hass: HomeAssistant) -> None:
    """Test zeroconf discovery creates entry with MAC-based unique_id."""
    discovery_info = ZeroconfServiceInfo(
        ip_address=make_ip_address(TEST_HOST),
        ip_addresses=[make_ip_address(TEST_HOST)],
        port=7000,
        hostname="bravia-quad.local",
        type="_airplay._tcp.local.",
        name="Living Room._airplay._tcp.local.",
        properties={
            "model": "Bravia Theatre Quad",
            "deviceid": "60:FF:9E:12:34:56",
            "manufacturer": "Sony Corporation",
        },
    )

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_ZEROCONF}, data=discovery_info
    )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "zeroconf_confirm"

    with patch(
        "custom_components.bravia_quad.config_flow.BraviaQuadClient",
        autospec=True,
    ) as client_mock:
        client = client_mock.return_value
        client.async_connect = AsyncMock()
        client.async_disconnect = AsyncMock()
        client.async_test_connection = AsyncMock(return_value=True)
        client.async_detect_subwoofer = AsyncMock(return_value=True)

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], user_input={}
        )
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_HOST] == TEST_HOST
    assert result["data"][CONF_MAC] == TEST_MAC_FORMATTED
    # Unique ID should be MAC address
    assert result["result"].unique_id == TEST_MAC_FORMATTED


async def test_zeroconf_discovery_not_bravia(hass: HomeAssistant) -> None:
    """Test zeroconf discovery aborts for non-Bravia devices."""
    discovery_info = ZeroconfServiceInfo(
        ip_address=make_ip_address(TEST_HOST),
        ip_addresses=[make_ip_address(TEST_HOST)],
        port=7000,
        hostname="other-device.local",
        type="_airplay._tcp.local.",
        name="Other Device._airplay._tcp.local.",
        properties={
            "model": "Other Speaker",
            "deviceid": "AA:BB:CC:DD:EE:FF",
        },
    )

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_ZEROCONF}, data=discovery_info
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "not_bravia_quad"


async def test_zeroconf_discovery_migrates_existing_ip_entry(
    hass: HomeAssistant,
) -> None:
    """Test zeroconf discovery migrates existing IP-based entry to MAC-based."""
    # Create existing entry with IP as unique_id
    existing_entry = MockConfigEntry(
        domain=DOMAIN,
        title="Bravia Quad",
        data={
            CONF_HOST: TEST_HOST,
            CONF_NAME: "Bravia Quad",
            CONF_HAS_SUBWOOFER: True,
        },
        unique_id=TEST_HOST,  # Old IP-based unique_id
    )
    existing_entry.add_to_hass(hass)

    discovery_info = ZeroconfServiceInfo(
        ip_address=make_ip_address(TEST_HOST),
        ip_addresses=[make_ip_address(TEST_HOST)],
        port=7000,
        hostname="bravia-quad.local",
        type="_airplay._tcp.local.",
        name="Living Room._airplay._tcp.local.",
        properties={
            "model": "Bravia Theatre Quad",
            "deviceid": "60:FF:9E:12:34:56",
        },
    )

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_ZEROCONF}, data=discovery_info
    )

    # Flow should abort after migrating
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"

    # Verify the entry was migrated
    assert existing_entry.unique_id == TEST_MAC_FORMATTED
    assert existing_entry.data[CONF_MAC] == TEST_MAC_FORMATTED


async def test_dhcp_discovery(hass: HomeAssistant) -> None:
    """Test DHCP discovery creates entry with MAC-based unique_id."""
    discovery_info = DhcpServiceInfo(
        ip=TEST_HOST,
        hostname="bravia-quad",
        macaddress="60ff9e123456",
    )

    with patch(
        "custom_components.bravia_quad.config_flow.BraviaQuadClient",
        autospec=True,
    ) as client_mock:
        client = client_mock.return_value
        client.async_connect = AsyncMock()
        client.async_disconnect = AsyncMock()
        client.async_test_connection = AsyncMock(return_value=True)
        client.async_detect_subwoofer = AsyncMock(return_value=True)

        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_DHCP}, data=discovery_info
        )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "dhcp_confirm"

    with patch(
        "custom_components.bravia_quad.config_flow.BraviaQuadClient",
        autospec=True,
    ) as client_mock:
        client = client_mock.return_value
        client.async_connect = AsyncMock()
        client.async_disconnect = AsyncMock()
        client.async_test_connection = AsyncMock(return_value=True)
        client.async_detect_subwoofer = AsyncMock(return_value=False)

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], user_input={}
        )
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_HOST] == TEST_HOST
    assert result["data"][CONF_MAC] == TEST_MAC_FORMATTED
    assert result["data"][CONF_HAS_SUBWOOFER] is False
    # Unique ID should be MAC address
    assert result["result"].unique_id == TEST_MAC_FORMATTED


async def test_dhcp_discovery_not_bravia(hass: HomeAssistant) -> None:
    """Test DHCP discovery aborts when device is not a Bravia Quad."""
    discovery_info = DhcpServiceInfo(
        ip=TEST_HOST,
        hostname="other-device",
        macaddress="60ff9e123456",
    )

    with patch(
        "custom_components.bravia_quad.config_flow.BraviaQuadClient",
        autospec=True,
    ) as client_mock:
        client = client_mock.return_value
        client.async_connect = AsyncMock()
        client.async_disconnect = AsyncMock()
        # Connection test fails - not a Bravia Quad
        client.async_test_connection = AsyncMock(return_value=False)

        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_DHCP}, data=discovery_info
        )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "not_bravia_quad"


async def test_dhcp_discovery_connection_error(hass: HomeAssistant) -> None:
    """Test DHCP discovery aborts when connection fails."""
    discovery_info = DhcpServiceInfo(
        ip=TEST_HOST,
        hostname="bravia-quad",
        macaddress="60ff9e123456",
    )

    with patch(
        "custom_components.bravia_quad.config_flow.BraviaQuadClient",
        autospec=True,
    ) as client_mock:
        client = client_mock.return_value
        client.async_connect = AsyncMock(side_effect=OSError("Connection refused"))
        client.async_disconnect = AsyncMock()

        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_DHCP}, data=discovery_info
        )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "cannot_connect"


async def test_dhcp_discovery_migrates_existing_ip_entry(
    hass: HomeAssistant,
) -> None:
    """Test DHCP discovery migrates existing IP-based entry to MAC-based."""
    # Create existing entry with IP as unique_id
    existing_entry = MockConfigEntry(
        domain=DOMAIN,
        title="Bravia Quad",
        data={
            CONF_HOST: TEST_HOST,
            CONF_NAME: "Bravia Quad",
            CONF_HAS_SUBWOOFER: True,
        },
        unique_id=TEST_HOST,  # Old IP-based unique_id
    )
    existing_entry.add_to_hass(hass)

    discovery_info = DhcpServiceInfo(
        ip=TEST_HOST,
        hostname="bravia-quad",
        macaddress="60ff9e123456",
    )

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_DHCP}, data=discovery_info
    )

    # Flow should abort after migrating
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"

    # Verify the entry was migrated
    assert existing_entry.unique_id == TEST_MAC_FORMATTED
    assert existing_entry.data[CONF_MAC] == TEST_MAC_FORMATTED


async def test_dhcp_discovery_already_configured_by_mac(
    hass: HomeAssistant,
) -> None:
    """Test DHCP discovery updates host when already configured by MAC."""
    # Create existing entry with MAC as unique_id
    existing_entry = MockConfigEntry(
        domain=DOMAIN,
        title="Bravia Quad",
        data={
            CONF_HOST: "192.168.1.50",  # Old IP
            CONF_NAME: "Bravia Quad",
            CONF_MAC: TEST_MAC_FORMATTED,
            CONF_HAS_SUBWOOFER: True,
        },
        unique_id=TEST_MAC_FORMATTED,
    )
    existing_entry.add_to_hass(hass)

    discovery_info = DhcpServiceInfo(
        ip=TEST_HOST,  # New IP
        hostname="bravia-quad",
        macaddress="60ff9e123456",
    )

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_DHCP}, data=discovery_info
    )

    # Flow should abort - already configured
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"

    # Verify the host was updated to the new IP
    assert existing_entry.data[CONF_HOST] == TEST_HOST
