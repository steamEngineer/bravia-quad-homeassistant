"""Tests for the Bravia Quad reconnection and availability functionality."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.const import STATE_UNAVAILABLE, Platform

from custom_components.bravia_quad.bravia_quad_client import BraviaQuadClient

from .conftest import get_entity_id_by_unique_id_suffix

if TYPE_CHECKING:
    from collections.abc import Callable

    from homeassistant.core import HomeAssistant
    from homeassistant.helpers import entity_registry as er


def _get_availability_callback(mock_client: MagicMock) -> Callable | None:
    """Get the last registered availability callback."""
    callback = None
    for call_args in mock_client.register_availability_callback.call_args_list:
        callback = call_args[0][0]
    return callback


def _notify_all_availability(mock_client: MagicMock, *, available: bool) -> None:
    """Invoke all registered availability callbacks, simulating the real client."""
    for call_args in mock_client.register_availability_callback.call_args_list:
        callback = call_args[0][0]
        callback(available)


@pytest.fixture
def platforms() -> list[Platform]:
    """Return platforms to test."""
    return [Platform.BUTTON, Platform.MEDIA_PLAYER, Platform.SWITCH]


def _setup_mock_stream(client: BraviaQuadClient) -> MagicMock:
    """Set up mock reader/writer on client and mark connected."""
    mock_reader = MagicMock()
    client._reader = mock_reader
    client._writer = MagicMock()
    client._writer.close = MagicMock()
    client._writer.wait_closed = AsyncMock()
    client._connected = True
    return mock_reader


# --- Client unit tests ---


class TestClientReconnection:
    """Tests for BraviaQuadClient reconnection logic."""

    async def test_mark_disconnected_notifies_availability(self) -> None:
        """Test that _async_mark_disconnected notifies availability callbacks."""
        client = BraviaQuadClient("192.168.1.100", "Test")
        callback = MagicMock()
        client.register_availability_callback(callback)

        client._connected = True

        await client._async_mark_disconnected()

        assert not client.is_connected
        callback.assert_called_once_with(False)

    async def test_mark_disconnected_when_already_disconnected(self) -> None:
        """Test that _async_mark_disconnected is a no-op when already disconnected."""
        client = BraviaQuadClient("192.168.1.100", "Test")
        callback = MagicMock()
        client.register_availability_callback(callback)

        client._connected = False

        await client._async_mark_disconnected()

        callback.assert_not_called()

    async def test_mark_disconnected_fails_pending_commands(self) -> None:
        """Test that pending commands are failed on disconnect."""
        client = BraviaQuadClient("192.168.1.100", "Test")
        client._connected = True

        loop = asyncio.get_running_loop()
        future = loop.create_future()
        client._pending_responses[42] = future

        await client._async_mark_disconnected()

        assert future.done()
        with pytest.raises(ConnectionError):
            future.result()

    async def test_register_unregister_availability_callback(self) -> None:
        """Test registering and unregistering availability callbacks."""
        client = BraviaQuadClient("192.168.1.100", "Test")
        callback = MagicMock()

        client.register_availability_callback(callback)
        assert callback in client._availability_callbacks

        client.unregister_availability_callback(callback)
        assert callback not in client._availability_callbacks

    async def test_unregister_nonexistent_callback_is_safe(self) -> None:
        """Test that unregistering a non-existent callback doesn't raise."""
        client = BraviaQuadClient("192.168.1.100", "Test")
        callback = MagicMock()

        # Should not raise
        client.unregister_availability_callback(callback)

    async def test_notification_loop_stops_on_eof(self) -> None:
        """Test that the notification loop stops when EOF is received."""
        client = BraviaQuadClient("192.168.1.100", "Test")
        availability_callback = MagicMock()
        client.register_availability_callback(availability_callback)

        mock_reader = _setup_mock_stream(client)
        mock_reader.read = AsyncMock(return_value=b"")

        client._listening = True
        await client._notification_loop()

        assert not client.is_connected
        assert not client._listening
        availability_callback.assert_called_with(False)

    async def test_notification_loop_stops_on_os_error(self) -> None:
        """Test that the notification loop stops on OSError."""
        client = BraviaQuadClient("192.168.1.100", "Test")
        availability_callback = MagicMock()
        client.register_availability_callback(availability_callback)

        mock_reader = _setup_mock_stream(client)
        mock_reader.read = AsyncMock(side_effect=OSError("Connection reset"))

        client._listening = True
        await client._notification_loop()

        assert not client.is_connected
        assert not client._listening
        availability_callback.assert_called_with(False)


# --- Integration-level entity availability tests ---


@pytest.mark.usefixtures("init_integration")
async def test_entities_available_when_connected(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
) -> None:
    """Test that entities are available when client is connected."""
    entity_id = get_entity_id_by_unique_id_suffix(entity_registry, "_media_player")
    assert entity_id is not None

    state = hass.states.get(entity_id)
    assert state is not None
    assert state.state != STATE_UNAVAILABLE


@pytest.mark.usefixtures("init_integration")
async def test_entities_unavailable_when_disconnected(
    hass: HomeAssistant,
    mock_bravia_quad_client: MagicMock,
    entity_registry: er.EntityRegistry,
) -> None:
    """Test that entities become unavailable when connection is lost."""
    entity_id = get_entity_id_by_unique_id_suffix(entity_registry, "_media_player")
    assert entity_id is not None

    mock_bravia_quad_client.is_connected = False
    _notify_all_availability(mock_bravia_quad_client, available=False)
    await hass.async_block_till_done()

    state = hass.states.get(entity_id)
    assert state is not None
    assert state.state == STATE_UNAVAILABLE


@pytest.mark.usefixtures("init_integration")
async def test_entities_recover_after_reconnect(
    hass: HomeAssistant,
    mock_bravia_quad_client: MagicMock,
    entity_registry: er.EntityRegistry,
) -> None:
    """Test that entities recover availability after reconnection."""
    entity_id = get_entity_id_by_unique_id_suffix(entity_registry, "_media_player")
    assert entity_id is not None

    mock_bravia_quad_client.is_connected = False
    _notify_all_availability(mock_bravia_quad_client, available=False)
    await hass.async_block_till_done()

    state = hass.states.get(entity_id)
    assert state is not None
    assert state.state == STATE_UNAVAILABLE

    mock_bravia_quad_client.is_connected = True
    _notify_all_availability(mock_bravia_quad_client, available=True)
    await hass.async_block_till_done()

    state = hass.states.get(entity_id)
    assert state is not None
    assert state.state != STATE_UNAVAILABLE


@pytest.mark.usefixtures("init_integration")
async def test_switch_unavailable_when_disconnected(
    hass: HomeAssistant,
    mock_bravia_quad_client: MagicMock,
    entity_registry: er.EntityRegistry,
) -> None:
    """Test that switch entities become unavailable when disconnected."""
    entity_id = get_entity_id_by_unique_id_suffix(entity_registry, "_night_mode")
    assert entity_id is not None

    mock_bravia_quad_client.is_connected = False
    _notify_all_availability(mock_bravia_quad_client, available=False)
    await hass.async_block_till_done()

    state = hass.states.get(entity_id)
    assert state is not None
    assert state.state == STATE_UNAVAILABLE


@pytest.mark.usefixtures("init_integration")
async def test_button_unavailable_when_disconnected(
    hass: HomeAssistant,
    mock_bravia_quad_client: MagicMock,
    entity_registry: er.EntityRegistry,
) -> None:
    """Test that button entities become unavailable when disconnected."""
    entity_id = get_entity_id_by_unique_id_suffix(entity_registry, "_detect_subwoofer")
    if entity_id is None:
        pytest.skip("Detect subwoofer button not found")

    mock_bravia_quad_client.is_connected = False
    _notify_all_availability(mock_bravia_quad_client, available=False)
    await hass.async_block_till_done()

    state = hass.states.get(entity_id)
    assert state is not None
    assert state.state == STATE_UNAVAILABLE
