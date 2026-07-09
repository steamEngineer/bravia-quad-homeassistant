"""Tests for gRPC session availability callbacks."""

from __future__ import annotations

import logging
from unittest.mock import MagicMock

import pytest
from homeassistant.core import HomeAssistant

from custom_components.bravia_quad.bravia_grpc_client import BraviaGrpcClientAsync
from custom_components.bravia_quad.button import BraviaGrpcDetectSubwooferButton
from custom_components.bravia_quad.entity import BraviaGrpcAvailabilityMixin


def test_set_connected_notifies_availability_callbacks() -> None:
    """Connection changes should invoke registered availability callbacks."""
    client = BraviaGrpcClientAsync(
        "192.168.1.50",
        device_id="dev",
        key_id="kid",
        session_key="s" * 64,
        hmac_key="h" * 64,
    )
    callback = MagicMock()
    client.register_availability_callback(callback)

    client._set_connected(connected=True)
    callback.assert_called_once_with(True)

    client._set_connected(connected=False)
    assert callback.call_args_list[-1] == ((False,),)


def test_set_connected_skips_duplicate_notifications() -> None:
    """Repeated connection state should not re-notify callbacks."""
    client = BraviaGrpcClientAsync(
        "192.168.1.50",
        device_id="dev",
        key_id="kid",
        session_key="s" * 64,
        hmac_key="h" * 64,
    )
    callback = MagicMock()
    client.register_availability_callback(callback)

    client._set_connected(connected=True)
    client._set_connected(connected=True)
    callback.assert_called_once_with(True)


def test_grpc_detect_subwoofer_button_unavailable_when_disconnected(
    grpc_client: MagicMock, grpc_entry: MagicMock
) -> None:
    """gRPC detect-subwoofer button tracks session availability."""
    hass = MagicMock(spec=HomeAssistant)
    button = BraviaGrpcDetectSubwooferButton(hass, grpc_client, grpc_entry)
    button.entity_id = "button.bravia_theatre_detect_subwoofer"
    button.async_write_ha_state = MagicMock()

    grpc_client.is_connected = False
    assert button.available is False

    grpc_client.is_connected = True
    assert button.available is True


def test_grpc_availability_mixin_logs_once(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """gRPC availability mixin logs unavailable once and recovery once."""

    class _Entity(BraviaGrpcAvailabilityMixin):
        def __init__(self) -> None:
            self._grpc_client = MagicMock()
            self.entity_id = "switch.test_entity"
            self.async_write_ha_state = MagicMock()

    entity = _Entity()

    with caplog.at_level(logging.INFO):
        entity._on_grpc_availability_changed(False)
        entity._on_grpc_availability_changed(False)
        unavailable = [
            r
            for r in caplog.records
            if "is unavailable" in r.getMessage() and entity.entity_id in r.getMessage()
        ]
        assert len(unavailable) == 1

        entity._on_grpc_availability_changed(True)
        recovery = [
            r
            for r in caplog.records
            if "is back online" in r.getMessage() and entity.entity_id in r.getMessage()
        ]
        assert len(recovery) == 1
