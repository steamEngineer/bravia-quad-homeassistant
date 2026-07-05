"""Tests for gRPC session availability callbacks."""

from __future__ import annotations

from unittest.mock import MagicMock

from custom_components.bravia_quad.bravia_grpc_client import BraviaGrpcClientAsync


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
