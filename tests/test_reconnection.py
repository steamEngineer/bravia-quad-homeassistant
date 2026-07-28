"""Tests for the Bravia Quad reconnection and availability functionality."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import pytest
from homeassistant.const import STATE_UNAVAILABLE, Platform

from custom_components.bravia_quad.bravia_quad_client import BraviaQuadClient

from .conftest import get_entity_id_by_unique_id_suffix

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers import entity_registry as er


def _notify_all_availability(mock_client: MagicMock, *, available: bool) -> None:
    """Invoke all registered availability callbacks, simulating the real client."""
    for call_args in mock_client.register_availability_callback.call_args_list:
        callback = call_args[0][0]
        callback(available)


@pytest.fixture
def platforms() -> list[Platform]:
    """Return platforms to test."""
    return [Platform.BUTTON, Platform.MEDIA_PLAYER, Platform.SWITCH]


# --- Adapter unit tests ---


class TestClientReconnection:
    """Tests for BraviaQuadClient adapter availability / reconnect hooks."""

    async def test_connection_lost_notifies_availability(self) -> None:
        """Library connection-lost hook marks unavailable."""
        client = BraviaQuadClient("192.168.1.100", "Test")
        callback = MagicMock()
        client.register_availability_callback(callback)

        client._connected = True
        client._on_lib_connection_lost()

        assert not client.is_connected
        callback.assert_called_once_with(False)

    async def test_connection_lost_when_already_disconnected(self) -> None:
        """Connection-lost hook is a no-op when already disconnected."""
        client = BraviaQuadClient("192.168.1.100", "Test")
        callback = MagicMock()
        client.register_availability_callback(callback)

        client._connected = False
        client._on_lib_connection_lost()

        callback.assert_not_called()

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

        client.unregister_availability_callback(callback)

    async def test_reconnect_fetches_state_and_notifies(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """After reconnect, device state is fetched and availability restored."""
        client = BraviaQuadClient("192.168.1.100", "Test")
        availability_callback = MagicMock()
        client.register_availability_callback(availability_callback)

        fetch_called = asyncio.Event()

        async def _fake_fetch() -> None:
            fetch_called.set()

        monkeypatch.setattr(client, "async_fetch_all_states", _fake_fetch)

        await client._async_on_lib_reconnect()

        try:
            await asyncio.wait_for(fetch_called.wait(), timeout=1.0)
        except TimeoutError:
            pytest.fail("State fetch was not triggered after reconnect")

        assert client.is_connected
        availability_callback.assert_called_with(True)

        for task in list(client._background_tasks):
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
        client._background_tasks.clear()


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


@pytest.mark.usefixtures("init_integration")
async def test_availability_logs_once_on_disconnect_and_recovery(
    hass: HomeAssistant,
    mock_bravia_quad_client: MagicMock,
    entity_registry: er.EntityRegistry,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Log unavailable once on disconnect and once on recovery."""
    entity_id = get_entity_id_by_unique_id_suffix(entity_registry, "_media_player")
    assert entity_id is not None

    with caplog.at_level(logging.INFO):
        mock_bravia_quad_client.is_connected = False
        _notify_all_availability(mock_bravia_quad_client, available=False)
        await hass.async_block_till_done()
        _notify_all_availability(mock_bravia_quad_client, available=False)
        await hass.async_block_till_done()

        unavailable_logs = [
            r
            for r in caplog.records
            if r.levelno == logging.INFO and "is unavailable" in r.getMessage()
        ]
        assert any(entity_id in r.getMessage() for r in unavailable_logs)
        assert sum(1 for r in unavailable_logs if entity_id in r.getMessage()) == 1

        mock_bravia_quad_client.is_connected = True
        _notify_all_availability(mock_bravia_quad_client, available=True)
        await hass.async_block_till_done()

        recovery_logs = [
            r
            for r in caplog.records
            if r.levelno == logging.INFO and "is back online" in r.getMessage()
        ]
        assert sum(1 for r in recovery_logs if entity_id in r.getMessage()) == 1
