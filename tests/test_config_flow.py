"""Tests for the Bravia Quad config flow."""

from __future__ import annotations

from contextlib import contextmanager
from ipaddress import ip_address as make_ip_address
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, patch

from homeassistant.config_entries import SOURCE_USER, SOURCE_ZEROCONF
from homeassistant.const import CONF_HOST, CONF_MAC, CONF_NAME
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.bravia_quad.config_flow import BraviaQuadConfigFlow
from custom_components.bravia_quad.const import (
    CONF_GRPC_DEBUG,
    CONF_GRPC_KEYS,
    CONF_GRPC_OAUTH_REDIRECT,
    CONF_HAS_SUBWOOFER,
    CONF_MANUFACTURER,
    CONF_MODEL,
    CONF_MODEL_ID,
    CONF_SERIAL,
    CONF_TRANSPORT,
    DOMAIN,
    MODEL_ID_TO_NAME,
    TRANSPORT_GRPC,
    TRANSPORT_TCP,
)

if TYPE_CHECKING:
    from collections.abc import Generator

    from homeassistant.core import HomeAssistant

TEST_HOST = "192.168.1.100"
TEST_MAC_FORMATTED = "60:ff:9e:12:34:56"
TEST_MODEL = "Bravia Theatre Quad"
TEST_SERIAL = "1234567"
TEST_MODEL_ID = "HT-A9M2"
TEST_MANUFACTURER = "SONY"
TEST_DEVICE_NAME = "Living Room BRAVIA Theatre Quad"
TEST_GRPC_KEYS = '{"session_id": "test"}'


def _setup_client_identity(client: AsyncMock) -> None:
    """Configure identity method return values on a client mock."""
    client.async_get_serial_number = AsyncMock(return_value=TEST_SERIAL)
    client.async_get_model_type = AsyncMock(return_value=TEST_MODEL_ID)
    client.async_get_manufacturer = AsyncMock(return_value=TEST_MANUFACTURER)
    client.async_get_mac_address = AsyncMock(return_value=TEST_MAC_FORMATTED)
    client.async_get_device_name = AsyncMock(return_value=TEST_DEVICE_NAME)


def _setup_tcp_client(client: AsyncMock, *, has_subwoofer: bool = True) -> None:
    """Configure a TCP client mock for validate_input."""
    client.async_connect = AsyncMock()
    client.async_disconnect = AsyncMock()
    client.async_test_connection = AsyncMock(return_value=True)
    client.async_detect_subwoofer = AsyncMock(return_value=has_subwoofer)
    _setup_client_identity(client)


@contextmanager
def _patch_tcp_client(
    *,
    has_subwoofer: bool = True,
    **client_overrides: Any,
) -> Generator[AsyncMock]:
    """Patch BraviaQuadClient in config flow with a configured mock."""
    with patch(
        "custom_components.bravia_quad.config_flow.BraviaQuadClient",
        autospec=True,
    ) as client_mock:
        client = client_mock.return_value
        _setup_tcp_client(client, has_subwoofer=has_subwoofer)
        for name, value in client_overrides.items():
            setattr(client, name, value)
        yield client


async def _enter_host(hass: HomeAssistant, flow_id: str) -> dict:
    """Submit host in the user step."""
    return await hass.config_entries.flow.async_configure(
        flow_id,
        user_input={CONF_HOST: TEST_HOST},
    )


async def _select_tcp_transport(hass: HomeAssistant, flow_id: str) -> dict:
    """Select TCP transport in the config flow."""
    return await hass.config_entries.flow.async_configure(
        flow_id,
        user_input={CONF_TRANSPORT: TRANSPORT_TCP},
    )


async def _select_grpc_transport(hass: HomeAssistant, flow_id: str) -> dict:
    """Select gRPC transport in the config flow."""
    return await hass.config_entries.flow.async_configure(
        flow_id,
        user_input={CONF_TRANSPORT: TRANSPORT_GRPC},
    )


async def _continue_grpc_oauth(hass: HomeAssistant, flow_id: str) -> dict:
    """Continue past the Sony OAuth link step."""
    return await hass.config_entries.flow.async_configure(flow_id, user_input={})


async def _submit_grpc_oauth_redirect(
    hass: HomeAssistant, flow_id: str, redirect: str = "ssh-app://signin?code=abc"
) -> dict:
    """Submit the OAuth redirect on the callback step."""
    return await hass.config_entries.flow.async_configure(
        flow_id,
        user_input={CONF_GRPC_OAUTH_REDIRECT: redirect},
    )


async def _confirm_setup(hass: HomeAssistant, flow_id: str) -> dict:
    """Confirm setup in the user_confirm step."""
    result = await hass.config_entries.flow.async_configure(flow_id, user_input={})
    await hass.async_block_till_done()
    return result


async def test_user_flow_success(hass: HomeAssistant, mock_setup_entry: None) -> None:
    """Test successful user flow with confirmation step."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"

    result = await _enter_host(hass, result["flow_id"])
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "transport"

    with _patch_tcp_client():
        result = await _select_tcp_transport(hass, result["flow_id"])

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user_confirm"

    with _patch_tcp_client():
        result = await _confirm_setup(hass, result["flow_id"])

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
        CONF_TRANSPORT: TRANSPORT_TCP,
    }
    assert result["result"].unique_id == TEST_SERIAL


async def test_user_flow_success_no_subwoofer(
    hass: HomeAssistant, mock_setup_entry: None
) -> None:
    """Test successful user flow without subwoofer."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )

    result = await _enter_host(hass, result["flow_id"])
    assert result["step_id"] == "transport"

    with _patch_tcp_client(has_subwoofer=False):
        result = await _select_tcp_transport(hass, result["flow_id"])

    assert result["step_id"] == "user_confirm"

    with _patch_tcp_client(has_subwoofer=False):
        result = await _confirm_setup(hass, result["flow_id"])

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_HAS_SUBWOOFER] is False


async def test_user_flow_connection_error(hass: HomeAssistant) -> None:
    """Test user flow when connection fails on transport step."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )

    result = await _enter_host(hass, result["flow_id"])
    assert result["step_id"] == "transport"

    with _patch_tcp_client(
        async_connect=AsyncMock(side_effect=OSError("Connection refused"))
    ):
        result = await _select_tcp_transport(hass, result["flow_id"])

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "transport"
    assert result["errors"] == {"base": "cannot_connect"}


async def test_user_flow_test_connection_fails(hass: HomeAssistant) -> None:
    """Test user flow when test connection returns False."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )

    result = await _enter_host(hass, result["flow_id"])

    with _patch_tcp_client(async_test_connection=AsyncMock(return_value=False)):
        result = await _select_tcp_transport(hass, result["flow_id"])

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "transport"
    assert result["errors"] == {"base": "cannot_connect"}


async def test_user_flow_timeout_error(hass: HomeAssistant) -> None:
    """Test user flow when connection times out."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )

    result = await _enter_host(hass, result["flow_id"])

    with _patch_tcp_client(
        async_connect=AsyncMock(side_effect=TimeoutError("Connection timeout"))
    ):
        result = await _select_tcp_transport(hass, result["flow_id"])

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "transport"
    assert result["errors"] == {"base": "cannot_connect"}


async def test_user_flow_duplicate_entry(hass: HomeAssistant) -> None:
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
            CONF_TRANSPORT: TRANSPORT_TCP,
        },
        unique_id=TEST_SERIAL,
    )
    existing_entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )

    result = await _enter_host(hass, result["flow_id"])

    with _patch_tcp_client():
        result = await _select_tcp_transport(hass, result["flow_id"])

    assert result["step_id"] == "user_confirm"

    with _patch_tcp_client():
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

    result = await _enter_host(hass, result["flow_id"])

    with _patch_tcp_client(
        async_test_connection=AsyncMock(side_effect=RuntimeError("Unexpected"))
    ):
        result = await _select_tcp_transport(hass, result["flow_id"])

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "transport"
    assert result["errors"] == {"base": "unknown"}


async def test_user_flow_grpc_success(
    hass: HomeAssistant, mock_setup_entry: None
) -> None:
    """Test successful gRPC transport setup."""
    grpc_setup = {
        CONF_HAS_SUBWOOFER: True,
        CONF_SERIAL: TEST_SERIAL,
        CONF_MODEL_ID: TEST_MODEL_ID,
        CONF_MODEL: MODEL_ID_TO_NAME[TEST_MODEL_ID],
        CONF_MANUFACTURER: TEST_MANUFACTURER,
        CONF_MAC: TEST_MAC_FORMATTED,
        CONF_NAME: TEST_DEVICE_NAME,
        CONF_TRANSPORT: TRANSPORT_GRPC,
        CONF_GRPC_KEYS: TEST_GRPC_KEYS,
    }

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await _enter_host(hass, result["flow_id"])

    with patch.object(
        BraviaQuadConfigFlow,
        "_finish_grpc_oauth",
        new=AsyncMock(return_value=grpc_setup),
    ):
        result = await _select_grpc_transport(hass, result["flow_id"])
        assert result["step_id"] == "grpc_oauth"

        result = await _continue_grpc_oauth(hass, result["flow_id"])
        assert result["step_id"] == "grpc_oauth_callback"

        result = await _submit_grpc_oauth_redirect(hass, result["flow_id"])

    assert result["step_id"] == "user_confirm"
    result = await _confirm_setup(hass, result["flow_id"])

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_TRANSPORT] == TRANSPORT_GRPC
    assert result["data"][CONF_GRPC_KEYS] == TEST_GRPC_KEYS


def _zeroconf_discovery_info(**properties: str) -> ZeroconfServiceInfo:
    """Build zeroconf discovery info for tests."""
    return ZeroconfServiceInfo(
        ip_address=make_ip_address(TEST_HOST),
        ip_addresses=[make_ip_address(TEST_HOST)],
        port=7000,
        hostname="bravia-quad.local",
        type="_airplay._tcp.local.",
        name="Living Room._airplay._tcp.local.",
        properties=properties,
    )


async def test_zeroconf_discovery(hass: HomeAssistant, mock_setup_entry: None) -> None:
    """Test zeroconf discovery creates entry with serial-based unique_id."""
    discovery_info = _zeroconf_discovery_info(
        model="Bravia Theatre Quad",
        deviceid="60:FF:9E:12:34:56",
        manufacturer="Sony Corporation",
    )

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_ZEROCONF}, data=discovery_info
    )
    assert result["step_id"] == "zeroconf_confirm"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input={}
    )
    assert result["step_id"] == "transport"

    with _patch_tcp_client():
        result = await _select_tcp_transport(hass, result["flow_id"])

    assert result["step_id"] == "user_confirm"

    with _patch_tcp_client():
        result = await _confirm_setup(hass, result["flow_id"])

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_HOST] == TEST_HOST
    assert result["data"][CONF_MAC] == TEST_MAC_FORMATTED
    assert result["data"][CONF_MODEL] == MODEL_ID_TO_NAME[TEST_MODEL_ID]
    assert result["data"][CONF_SERIAL] == TEST_SERIAL
    assert result["data"][CONF_MODEL_ID] == TEST_MODEL_ID
    assert result["data"][CONF_MANUFACTURER] == TEST_MANUFACTURER
    assert result["data"][CONF_NAME] == TEST_DEVICE_NAME
    assert result["data"][CONF_TRANSPORT] == TRANSPORT_TCP
    assert result["result"].unique_id == TEST_SERIAL


async def test_zeroconf_discovery_without_deviceid(
    hass: HomeAssistant, mock_setup_entry: None
) -> None:
    """Test zeroconf discovery uses serial unique_id when deviceid is missing."""
    discovery_info = _zeroconf_discovery_info(model="Bravia Theatre Quad")

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_ZEROCONF}, data=discovery_info
    )
    assert result["step_id"] == "zeroconf_confirm"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input={}
    )

    with _patch_tcp_client():
        result = await _select_tcp_transport(hass, result["flow_id"])

    with _patch_tcp_client():
        result = await _confirm_setup(hass, result["flow_id"])

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_MAC] == TEST_MAC_FORMATTED
    assert result["data"][CONF_SERIAL] == TEST_SERIAL
    assert result["result"].unique_id == TEST_SERIAL


async def test_zeroconf_discovery_migrates_existing_ip_entry(
    hass: HomeAssistant,
) -> None:
    """Test zeroconf discovery migrates existing IP-based entry to MAC-based."""
    existing_entry = MockConfigEntry(
        domain=DOMAIN,
        title="Bravia Quad",
        data={
            CONF_HOST: TEST_HOST,
            CONF_HAS_SUBWOOFER: True,
        },
        unique_id=TEST_HOST,
    )
    existing_entry.add_to_hass(hass)

    discovery_info = _zeroconf_discovery_info(
        model="Bravia Theatre Quad",
        deviceid="60:FF:9E:12:34:56",
    )

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_ZEROCONF}, data=discovery_info
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert existing_entry.data[CONF_HOST] == TEST_HOST


async def test_zeroconf_discovery_already_configured_by_mac(
    hass: HomeAssistant,
) -> None:
    """Test zeroconf discovery updates host when already configured by MAC."""
    existing_entry = MockConfigEntry(
        domain=DOMAIN,
        title="Bravia Quad",
        data={
            CONF_HOST: "192.168.1.50",
            CONF_MAC: TEST_MAC_FORMATTED,
            CONF_HAS_SUBWOOFER: True,
        },
        unique_id=TEST_MAC_FORMATTED,
    )
    existing_entry.add_to_hass(hass)

    discovery_info = _zeroconf_discovery_info(
        model="Bravia Theatre Quad",
        deviceid="60:FF:9E:12:34:56",
    )

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_ZEROCONF}, data=discovery_info
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert existing_entry.data[CONF_HOST] == TEST_HOST


async def test_zeroconf_confirm_connection_error(hass: HomeAssistant) -> None:
    """Test zeroconf flow handles connection errors on transport step."""
    discovery_info = _zeroconf_discovery_info(
        model="Bravia Theatre Quad",
        deviceid="60:FF:9E:12:34:56",
    )

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_ZEROCONF}, data=discovery_info
    )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input={}
    )
    assert result["step_id"] == "transport"

    with _patch_tcp_client(
        async_connect=AsyncMock(side_effect=OSError("Connection refused"))
    ):
        result = await _select_tcp_transport(hass, result["flow_id"])

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "transport"
    assert result["errors"] == {"base": "cannot_connect"}


async def test_zeroconf_confirm_unknown_error(hass: HomeAssistant) -> None:
    """Test zeroconf flow handles unknown errors on transport step."""
    discovery_info = _zeroconf_discovery_info(
        model="Bravia Theatre Quad",
        deviceid="60:FF:9E:12:34:56",
    )

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_ZEROCONF}, data=discovery_info
    )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input={}
    )

    with _patch_tcp_client(
        async_test_connection=AsyncMock(side_effect=RuntimeError("Unexpected"))
    ):
        result = await _select_tcp_transport(hass, result["flow_id"])

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "transport"
    assert result["errors"] == {"base": "unknown"}


async def test_reauth_flow_success(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_setup_entry: None,
) -> None:
    """Test successful reauth flow updates host."""
    mock_config_entry.add_to_hass(hass)

    result = await mock_config_entry.start_reauth_flow(hass)
    assert result["step_id"] == "reauth_confirm"

    new_host = "192.168.1.200"

    with _patch_tcp_client():
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

    with _patch_tcp_client(
        async_connect=AsyncMock(side_effect=OSError("Connection refused"))
    ):
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

    with _patch_tcp_client(
        async_test_connection=AsyncMock(side_effect=RuntimeError("Unexpected"))
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={CONF_HOST: "192.168.1.200"},
        )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"
    assert result["errors"] == {"base": "unknown"}


async def test_reauth_flow_grpc_updates_keys(
    hass: HomeAssistant,
    mock_setup_entry: None,
) -> None:
    """Test gRPC reauth runs Sony OAuth and updates stored credentials."""
    entry = MockConfigEntry(
        title=TEST_DEVICE_NAME,
        domain=DOMAIN,
        data={
            CONF_HOST: TEST_HOST,
            CONF_TRANSPORT: TRANSPORT_GRPC,
            CONF_GRPC_KEYS: TEST_GRPC_KEYS,
            CONF_HAS_SUBWOOFER: True,
        },
        unique_id=TEST_SERIAL,
    )
    entry.add_to_hass(hass)

    new_host = "192.168.1.200"
    new_keys = '{"device_id": "dev", "refresh_token": "rt"}'
    grpc_setup = {
        CONF_TRANSPORT: TRANSPORT_GRPC,
        CONF_GRPC_KEYS: new_keys,
        CONF_HAS_SUBWOOFER: True,
    }

    result = await entry.start_reauth_flow(hass)
    assert result["step_id"] == "reauth_confirm"

    with patch.object(
        BraviaQuadConfigFlow,
        "_finish_grpc_oauth",
        new=AsyncMock(return_value={**grpc_setup, CONF_HOST: new_host}),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={CONF_HOST: new_host},
        )
        assert result["step_id"] == "grpc_oauth"

        result = await _continue_grpc_oauth(hass, result["flow_id"])
        result = await _submit_grpc_oauth_redirect(hass, result["flow_id"])
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.data[CONF_HOST] == new_host
    assert entry.data[CONF_GRPC_KEYS] == new_keys


async def test_options_flow_grpc_debug(
    hass: HomeAssistant, mock_setup_entry: None
) -> None:
    """Test gRPC transport options flow stores debug flag."""
    entry = MockConfigEntry(
        title=TEST_DEVICE_NAME,
        domain=DOMAIN,
        data={
            CONF_HOST: TEST_HOST,
            CONF_TRANSPORT: TRANSPORT_GRPC,
            CONF_GRPC_KEYS: TEST_GRPC_KEYS,
            CONF_HAS_SUBWOOFER: True,
        },
        unique_id=TEST_SERIAL,
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["step_id"] == "init"

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={CONF_GRPC_DEBUG: True},
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options[CONF_GRPC_DEBUG] is True


async def test_options_flow_tcp_aborts(hass: HomeAssistant) -> None:
    """Test TCP transport entries cannot open gRPC options."""
    entry = MockConfigEntry(
        title=TEST_DEVICE_NAME,
        domain=DOMAIN,
        data={
            CONF_HOST: TEST_HOST,
            CONF_TRANSPORT: TRANSPORT_TCP,
            CONF_HAS_SUBWOOFER: True,
        },
        unique_id=TEST_HOST,
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "not_grpc_transport"
