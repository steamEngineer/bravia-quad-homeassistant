"""Tests for the Bravia Quad config flow."""

from __future__ import annotations

from ipaddress import ip_address as make_ip_address
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, patch

from homeassistant.config_entries import SOURCE_USER, SOURCE_ZEROCONF
from homeassistant.const import CONF_HOST, CONF_MAC, CONF_NAME
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.bravia_quad.const import (
    CONF_HAS_SUBWOOFER,
    CONF_MANUFACTURER,
    CONF_MODEL,
    CONF_MODEL_ID,
    CONF_SERIAL,
    DOMAIN,
    MODEL_ID_TO_NAME,
)

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

TEST_HOST = "192.168.1.100"
TEST_MAC_FORMATTED = "60:ff:9e:12:34:56"
TEST_MODEL = "Bravia Theatre Quad"
TEST_SERIAL = "1234567"
TEST_MODEL_ID = "HT-A9M2"
TEST_MANUFACTURER = "SONY"
TEST_DEVICE_NAME = "Living Room BRAVIA Theatre Quad"
TEST_A9_HOST = "192.168.1.101"
TEST_A9_MAC_FORMATTED = "aa:bb:cc:dd:ee:11"
TEST_A9_SERIAL = "7654321"


def _setup_client_identity(client: AsyncMock) -> None:
    """Configure identity method return values on a client mock."""
    client.async_get_serial_number = AsyncMock(return_value=TEST_SERIAL)
    client.async_get_model_type = AsyncMock(return_value=TEST_MODEL_ID)
    client.async_get_manufacturer = AsyncMock(return_value=TEST_MANUFACTURER)
    client.async_get_mac_address = AsyncMock(return_value=TEST_MAC_FORMATTED)
    client.async_get_device_name = AsyncMock(return_value=TEST_DEVICE_NAME)


async def test_user_flow_success(hass: HomeAssistant, mock_setup_entry: None) -> None:
    """Test successful user flow with confirmation step."""
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
        _setup_client_identity(client)

        # First step: enter IP address
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={CONF_HOST: TEST_HOST},
        )

    # Should show confirmation step
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user_confirm"

    with patch(
        "custom_components.bravia_quad.config_flow.BraviaQuadClient",
        autospec=True,
    ) as client_mock:
        client = client_mock.return_value
        client.async_connect = AsyncMock()
        client.async_disconnect = AsyncMock()
        client.async_test_connection = AsyncMock(return_value=True)
        client.async_detect_subwoofer = AsyncMock(return_value=True)

        # Confirm step: user confirms to add device
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], user_input={}
        )
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == TEST_DEVICE_NAME
    assert result["data"] == {
        CONF_HOST: TEST_HOST,
        CONF_HAS_SUBWOOFER: True,
        CONF_SERIAL: TEST_SERIAL,
        CONF_MODEL_ID: TEST_MODEL_ID,
        CONF_MODEL: MODEL_ID_TO_NAME[TEST_MODEL_ID],
        CONF_MANUFACTURER: TEST_MANUFACTURER,
        CONF_MAC: TEST_MAC_FORMATTED,
        CONF_NAME: TEST_DEVICE_NAME,
    }
    assert result["result"].unique_id == TEST_SERIAL


async def test_user_flow_success_no_subwoofer(
    hass: HomeAssistant, mock_setup_entry: None
) -> None:
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
        _setup_client_identity(client)

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={CONF_HOST: TEST_HOST},
        )

    # Should show confirmation step
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user_confirm"

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
            user_input={CONF_HOST: TEST_HOST},
        )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
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
            user_input={CONF_HOST: TEST_HOST},
        )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
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
            user_input={CONF_HOST: TEST_HOST},
        )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {"base": "cannot_connect"}


async def test_user_flow_duplicate_entry(
    hass: HomeAssistant,
) -> None:
    """Test user flow when entry already exists."""
    existing_entry = MockConfigEntry(
        title=TEST_DEVICE_NAME,
        domain=DOMAIN,
        data={
            CONF_HOST: TEST_HOST,
            CONF_HAS_SUBWOOFER: True,
            CONF_SERIAL: TEST_SERIAL,
            CONF_MODEL_ID: TEST_MODEL_ID,
            CONF_MODEL: MODEL_ID_TO_NAME[TEST_MODEL_ID],
            CONF_MANUFACTURER: TEST_MANUFACTURER,
            CONF_MAC: TEST_MAC_FORMATTED,
            CONF_NAME: TEST_DEVICE_NAME,
        },
        unique_id=TEST_SERIAL,
    )
    existing_entry.add_to_hass(hass)

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
        _setup_client_identity(client)

        # Enter IP
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={CONF_HOST: TEST_HOST},
        )

    # Should show confirmation step
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user_confirm"

    with patch(
        "custom_components.bravia_quad.config_flow.BraviaQuadClient",
        autospec=True,
    ) as client_mock:
        client = client_mock.return_value
        client.async_connect = AsyncMock()
        client.async_disconnect = AsyncMock()
        client.async_test_connection = AsyncMock(return_value=True)
        client.async_detect_subwoofer = AsyncMock(return_value=True)

        # Confirm - should abort due to duplicate
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], user_input={}
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
            user_input={CONF_HOST: TEST_HOST},
        )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {"base": "unknown"}


async def test_zeroconf_discovery(hass: HomeAssistant, mock_setup_entry: None) -> None:
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
        _setup_client_identity(client)

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], user_input={}
        )
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_HOST] == TEST_HOST
    assert result["data"][CONF_MAC] == TEST_MAC_FORMATTED
    assert result["data"][CONF_MODEL] == TEST_MODEL
    assert result["data"][CONF_SERIAL] == TEST_SERIAL
    assert result["data"][CONF_MODEL_ID] == TEST_MODEL_ID
    assert result["data"][CONF_MANUFACTURER] == TEST_MANUFACTURER
    assert result["data"][CONF_NAME] == TEST_DEVICE_NAME
    # Unique ID should be serial number
    assert result["result"].unique_id == TEST_SERIAL


async def test_zeroconf_discovery_without_deviceid(
    hass: HomeAssistant, mock_setup_entry: None
) -> None:
    """Test zeroconf discovery uses IP-based unique_id when deviceid is missing."""
    discovery_info = ZeroconfServiceInfo(
        ip_address=make_ip_address(TEST_HOST),
        ip_addresses=[make_ip_address(TEST_HOST)],
        port=7000,
        hostname="bravia-quad.local",
        type="_airplay._tcp.local.",
        name="Living Room._airplay._tcp.local.",
        properties={
            "model": "Bravia Theatre Quad",
            # No deviceid property
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
        _setup_client_identity(client)

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], user_input={}
        )
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_HOST] == TEST_HOST
    # MAC comes from validate_input even when zeroconf deviceid is missing
    assert result["data"][CONF_MAC] == TEST_MAC_FORMATTED
    assert result["data"][CONF_SERIAL] == TEST_SERIAL
    assert result["data"][CONF_MODEL_ID] == TEST_MODEL_ID
    assert result["data"][CONF_MANUFACTURER] == TEST_MANUFACTURER
    assert result["data"][CONF_NAME] == TEST_DEVICE_NAME
    # Unique ID should be serial number
    assert result["result"].unique_id == TEST_SERIAL


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

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"

    # Verify the existing entry was updated with the discovered host
    assert existing_entry.data[CONF_HOST] == TEST_HOST


async def test_zeroconf_discovery_already_configured_by_mac(
    hass: HomeAssistant,
) -> None:
    """Test zeroconf discovery updates host when already configured by MAC."""
    # Create existing entry with MAC as unique_id
    existing_entry = MockConfigEntry(
        domain=DOMAIN,
        title="Bravia Quad",
        data={
            CONF_HOST: "192.168.1.50",  # Old IP
            CONF_MAC: TEST_MAC_FORMATTED,
            CONF_HAS_SUBWOOFER: True,
        },
        unique_id=TEST_MAC_FORMATTED,
    )
    existing_entry.add_to_hass(hass)

    discovery_info = ZeroconfServiceInfo(
        ip_address=make_ip_address(TEST_HOST),  # New IP
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

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"

    # Verify the host was updated to the new IP
    assert existing_entry.data[CONF_HOST] == TEST_HOST


async def test_zeroconf_does_not_hijack_unrelated_serial_entry(
    hass: HomeAssistant,
) -> None:
    """Test unrelated zeroconf discovery does not repoint a serial-based entry."""
    quad_entry = MockConfigEntry(
        domain=DOMAIN,
        title=TEST_DEVICE_NAME,
        data={
            CONF_HOST: TEST_HOST,
            CONF_MAC: TEST_MAC_FORMATTED,
            CONF_HAS_SUBWOOFER: True,
            CONF_SERIAL: TEST_SERIAL,
            CONF_MODEL_ID: TEST_MODEL_ID,
            CONF_MODEL: MODEL_ID_TO_NAME[TEST_MODEL_ID],
            CONF_MANUFACTURER: TEST_MANUFACTURER,
            CONF_NAME: TEST_DEVICE_NAME,
        },
        unique_id=TEST_SERIAL,
    )
    quad_entry.add_to_hass(hass)

    discovery_info = ZeroconfServiceInfo(
        ip_address=make_ip_address(TEST_A9_HOST),
        ip_addresses=[make_ip_address(TEST_A9_HOST)],
        port=7000,
        hostname="ht-a9.local",
        type="_airplay._tcp.local.",
        name="HT-A9._airplay._tcp.local.",
        properties={
            "model": "HT-A9",
            "deviceid": "AA:BB:CC:DD:EE:11",
        },
    )

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_ZEROCONF}, data=discovery_info
    )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "zeroconf_confirm"
    assert quad_entry.data[CONF_HOST] == TEST_HOST


async def test_zeroconf_updates_serial_entry_on_mac_match(
    hass: HomeAssistant,
) -> None:
    """Test zeroconf discovery updates host for serial entry with matching MAC."""
    existing_entry = MockConfigEntry(
        domain=DOMAIN,
        title=TEST_DEVICE_NAME,
        data={
            CONF_HOST: "192.168.1.50",
            CONF_MAC: TEST_MAC_FORMATTED,
            CONF_HAS_SUBWOOFER: True,
            CONF_SERIAL: TEST_SERIAL,
            CONF_MODEL_ID: TEST_MODEL_ID,
            CONF_MODEL: MODEL_ID_TO_NAME[TEST_MODEL_ID],
            CONF_MANUFACTURER: TEST_MANUFACTURER,
            CONF_NAME: TEST_DEVICE_NAME,
        },
        unique_id=TEST_SERIAL,
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

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert existing_entry.data[CONF_HOST] == TEST_HOST


async def test_zeroconf_two_serial_entries_updates_correct_one(
    hass: HomeAssistant,
) -> None:
    """Test zeroconf only updates the entry whose MAC matches discovery."""
    quad_entry = MockConfigEntry(
        domain=DOMAIN,
        title=TEST_DEVICE_NAME,
        entry_id="quad_entry",
        data={
            CONF_HOST: TEST_HOST,
            CONF_MAC: TEST_MAC_FORMATTED,
            CONF_HAS_SUBWOOFER: True,
            CONF_SERIAL: TEST_SERIAL,
            CONF_MODEL_ID: TEST_MODEL_ID,
            CONF_MODEL: MODEL_ID_TO_NAME[TEST_MODEL_ID],
            CONF_MANUFACTURER: TEST_MANUFACTURER,
            CONF_NAME: TEST_DEVICE_NAME,
        },
        unique_id=TEST_SERIAL,
    )
    a9_entry = MockConfigEntry(
        domain=DOMAIN,
        title="HT-A9",
        entry_id="a9_entry",
        data={
            CONF_HOST: "192.168.1.50",
            CONF_MAC: TEST_A9_MAC_FORMATTED,
            CONF_HAS_SUBWOOFER: True,
            CONF_SERIAL: TEST_A9_SERIAL,
            CONF_MODEL_ID: "HT-A9",
            CONF_MODEL: "HT-A9",
            CONF_MANUFACTURER: TEST_MANUFACTURER,
            CONF_NAME: "HT-A9",
        },
        unique_id=TEST_A9_SERIAL,
    )
    quad_entry.add_to_hass(hass)
    a9_entry.add_to_hass(hass)

    discovery_info = ZeroconfServiceInfo(
        ip_address=make_ip_address(TEST_A9_HOST),
        ip_addresses=[make_ip_address(TEST_A9_HOST)],
        port=7000,
        hostname="ht-a9.local",
        type="_airplay._tcp.local.",
        name="HT-A9._airplay._tcp.local.",
        properties={
            "model": "HT-A9",
            "deviceid": "AA:BB:CC:DD:EE:11",
        },
    )

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_ZEROCONF}, data=discovery_info
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert quad_entry.data[CONF_HOST] == TEST_HOST
    assert a9_entry.data[CONF_HOST] == TEST_A9_HOST


async def test_zeroconf_confirm_connection_error(hass: HomeAssistant) -> None:
    """Test zeroconf confirm step handles connection errors."""
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

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "zeroconf_confirm"

    with patch(
        "custom_components.bravia_quad.config_flow.BraviaQuadClient",
        autospec=True,
    ) as client_mock:
        client = client_mock.return_value
        client.async_connect = AsyncMock(side_effect=OSError("Connection refused"))
        client.async_disconnect = AsyncMock()

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], user_input={}
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}


async def test_zeroconf_confirm_unknown_error(hass: HomeAssistant) -> None:
    """Test zeroconf confirm step handles unknown errors."""
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

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "zeroconf_confirm"

    with patch(
        "custom_components.bravia_quad.config_flow.BraviaQuadClient",
        autospec=True,
    ) as client_mock:
        client = client_mock.return_value
        client.async_connect = AsyncMock()
        client.async_disconnect = AsyncMock()
        client.async_test_connection = AsyncMock(side_effect=RuntimeError("Unexpected"))

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], user_input={}
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "unknown"}


async def test_reauth_flow_success(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_setup_entry: None,
) -> None:
    """Test successful reauth flow updates host."""
    mock_config_entry.add_to_hass(hass)

    result = await mock_config_entry.start_reauth_flow(hass)

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"

    new_host = "192.168.1.200"

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
            user_input={CONF_HOST: new_host},
        )
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert mock_config_entry.data[CONF_HOST] == new_host


async def test_reauth_flow_connection_error(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test reauth flow handles connection errors."""
    mock_config_entry.add_to_hass(hass)

    result = await mock_config_entry.start_reauth_flow(hass)

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"

    with patch(
        "custom_components.bravia_quad.config_flow.BraviaQuadClient",
        autospec=True,
    ) as client_mock:
        client = client_mock.return_value
        client.async_connect = AsyncMock(side_effect=OSError("Connection refused"))
        client.async_disconnect = AsyncMock()

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={CONF_HOST: "192.168.1.200"},
        )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"
    assert result["errors"] == {"base": "cannot_connect"}


async def test_reauth_flow_unknown_error(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test reauth flow handles unknown errors."""
    mock_config_entry.add_to_hass(hass)

    result = await mock_config_entry.start_reauth_flow(hass)

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"

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
            user_input={CONF_HOST: "192.168.1.200"},
        )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"
    assert result["errors"] == {"base": "unknown"}
