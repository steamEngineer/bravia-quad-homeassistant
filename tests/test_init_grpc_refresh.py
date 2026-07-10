"""Tests for gRPC setup-time Sony Seeds key refresh."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.const import CONF_HOST
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.bravia_quad.const import (
    CONF_GRPC_KEYS,
    CONF_HAS_SUBWOOFER,
    CONF_TRANSPORT,
    DOMAIN,
    TRANSPORT_GRPC,
)
from custom_components.bravia_quad.grpc_refresh import async_setup_grpc_client

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

TEST_HOST = "192.168.1.100"
TEST_KEYS = {
    "device_id": "dev-1",
    "key_id": "kid-1",
    "session_key": "sk",
    "hmac_key": "hk",
    "refresh_token": "rt",
    "session_keys_expires_at": 9999999999,
}


@pytest.fixture(autouse=True)
def _mock_ensure_external_control() -> None:
    """Avoid live TCP during gRPC setup tests."""
    with patch(
        "custom_components.bravia_quad.grpc_refresh.async_ensure_external_control_enabled",
        new=AsyncMock(),
    ):
        yield


def _grpc_client_mock(
    *, connect_results: list[bool], transport_error: bool = False
) -> MagicMock:
    mock_client = MagicMock()
    mock_client.async_connect = AsyncMock(side_effect=connect_results)
    mock_client.async_fetch_capabilities = AsyncMock(return_value=frozenset({"power"}))
    mock_client.async_seed_notify_from_snapshot = AsyncMock(return_value=1)
    mock_client.async_backfill_entity_paths = AsyncMock(return_value=(0, 0, 0))
    mock_client.async_start_notify = AsyncMock()
    mock_client.async_warmup_notify = AsyncMock(return_value=frozenset())
    mock_client.async_disconnect = AsyncMock()
    mock_client.set_refresh_keys_callback = MagicMock()
    mock_client.update_keys = MagicMock()
    mock_client.is_transport_error = transport_error
    mock_client._client = MagicMock(last_rpc_error=None)
    return mock_client


@pytest.fixture
def grpc_config_entry() -> MockConfigEntry:
    """gRPC transport config entry with refreshable keys."""
    return MockConfigEntry(
        title="Office Quads",
        domain=DOMAIN,
        data={
            CONF_HOST: TEST_HOST,
            CONF_TRANSPORT: TRANSPORT_GRPC,
            CONF_GRPC_KEYS: json.dumps(TEST_KEYS),
            CONF_HAS_SUBWOOFER: False,
        },
        unique_id="8804927",
    )


async def test_setup_grpc_refreshes_after_auth_failure(
    hass: HomeAssistant, grpc_config_entry: MockConfigEntry
) -> None:
    """Setup should refresh keys and retry when the first auth attempt fails."""
    grpc_config_entry.add_to_hass(hass)
    refreshed_keys = {**TEST_KEYS, "key_id": "kid-2"}
    mock_client = _grpc_client_mock(connect_results=[False, True])

    with (
        patch(
            "custom_components.bravia_quad.grpc_refresh.async_refresh_grpc_keys",
            new=AsyncMock(return_value=refreshed_keys),
        ) as mock_refresh,
        patch(
            "custom_components.bravia_quad.grpc_refresh.BraviaGrpcClientAsync.from_keys_json",
            return_value=mock_client,
        ),
    ):
        client = await async_setup_grpc_client(hass, grpc_config_entry)

    assert client is mock_client
    mock_refresh.assert_awaited_once()
    mock_client.update_keys.assert_called_once_with(refreshed_keys)
    assert mock_client.async_connect.await_count == 2


async def test_setup_grpc_raises_auth_failed_when_refresh_impossible(
    hass: HomeAssistant,
) -> None:
    """Missing refresh token should surface ConfigEntryAuthFailed."""
    keys_without_refresh = {
        "device_id": "dev-1",
        "key_id": "kid-1",
        "session_key": "sk",
        "hmac_key": "hk",
        "session_keys_expires_at": 9999999999,
    }
    entry = MockConfigEntry(
        title="Office Quads",
        domain=DOMAIN,
        data={
            CONF_HOST: TEST_HOST,
            CONF_TRANSPORT: TRANSPORT_GRPC,
            CONF_GRPC_KEYS: json.dumps(keys_without_refresh),
            CONF_HAS_SUBWOOFER: False,
        },
        unique_id="8804927",
    )
    entry.add_to_hass(hass)
    mock_client = _grpc_client_mock(connect_results=[False])

    with (
        patch(
            "custom_components.bravia_quad.grpc_refresh.BraviaGrpcClientAsync.from_keys_json",
            return_value=mock_client,
        ),
        pytest.raises(ConfigEntryAuthFailed),
    ):
        await async_setup_grpc_client(hass, entry)


async def test_setup_grpc_raises_not_ready_when_refresh_and_retry_fail(
    hass: HomeAssistant, grpc_config_entry: MockConfigEntry
) -> None:
    """Transient gRPC failure after refresh should raise ConfigEntryNotReady."""
    grpc_config_entry.add_to_hass(hass)
    refreshed_keys = {**TEST_KEYS, "key_id": "kid-2"}
    mock_client = _grpc_client_mock(connect_results=[False, False])

    with (
        patch(
            "custom_components.bravia_quad.grpc_refresh.async_refresh_grpc_keys",
            new=AsyncMock(return_value=refreshed_keys),
        ),
        patch(
            "custom_components.bravia_quad.grpc_refresh.BraviaGrpcClientAsync.from_keys_json",
            return_value=mock_client,
        ),
        pytest.raises(ConfigEntryNotReady),
    ):
        await async_setup_grpc_client(hass, grpc_config_entry)


async def test_setup_grpc_skips_key_refresh_on_transport_error(
    hass: HomeAssistant, grpc_config_entry: MockConfigEntry
) -> None:
    """Connection refused must not mint new Sony Seeds keys."""
    grpc_config_entry.add_to_hass(hass)
    mock_client = _grpc_client_mock(connect_results=[False], transport_error=True)

    with (
        patch(
            "custom_components.bravia_quad.grpc_refresh.async_refresh_grpc_keys",
            new=AsyncMock(),
        ) as mock_refresh,
        patch(
            "custom_components.bravia_quad.grpc_refresh.BraviaGrpcClientAsync.from_keys_json",
            return_value=mock_client,
        ),
        pytest.raises(ConfigEntryNotReady),
    ):
        await async_setup_grpc_client(hass, grpc_config_entry)

    mock_refresh.assert_not_awaited()
    mock_client.update_keys.assert_not_called()
    assert mock_client.async_connect.await_count == 1
