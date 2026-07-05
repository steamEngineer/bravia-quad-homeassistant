"""Tests for gRPC ExecCommand preflight and retry behavior."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import grpc
import pytest

from custom_components.bravia_quad.grpc.client import BraviaGrpcClient


@pytest.fixture
def grpc_client() -> BraviaGrpcClient:
    client = BraviaGrpcClient("127.0.0.1")
    client.authenticated = True
    client.session_id = "session-abc"
    client.session_random = b"\x01" * 8
    client.auth_token = b"\x02" * 32
    client.hmac_key_hex = "ab" * 32
    client.channel = MagicMock()
    return client


def test_exec_command_calls_preflight_before_send(
    grpc_client: BraviaGrpcClient,
) -> None:
    with (
        patch.object(
            grpc_client, "_ensure_preflight_exec_auth_token", return_value=True
        ) as preflight,
        patch.object(
            grpc_client, "_send_exec_command", return_value=(True, False)
        ) as send,
    ):
        ok = grpc_client.exec_command("volume", int_value=33)

    assert ok is True
    preflight.assert_called_once()
    send.assert_called_once_with("volume", {"int_value": 33})


def test_exec_command_fails_when_preflight_fails(
    grpc_client: BraviaGrpcClient,
) -> None:
    with (
        patch.object(
            grpc_client, "_ensure_preflight_exec_auth_token", return_value=False
        ),
        patch.object(grpc_client, "_send_exec_command") as send,
    ):
        ok = grpc_client.exec_command("volume", int_value=33)

    assert ok is False
    send.assert_not_called()


def test_exec_command_recovers_when_initial_preflight_refresh_succeeds(
    grpc_client: BraviaGrpcClient,
) -> None:
    with (
        patch.object(
            grpc_client,
            "_preflight_exec_auth_token",
            side_effect=[False, True],
        ) as preflight,
        patch.object(
            grpc_client, "_refresh_session_tokens", return_value=True
        ) as refresh,
        patch.object(
            grpc_client, "_send_exec_command", return_value=(True, False)
        ) as send,
    ):
        ok = grpc_client.exec_command("power", bool_value=True)

    assert ok is True
    assert preflight.call_count == 2
    refresh.assert_called_once()
    send.assert_called_once()


def test_exec_command_retries_on_invalid_argument(
    grpc_client: BraviaGrpcClient,
) -> None:
    with (
        patch.object(
            grpc_client, "_ensure_preflight_exec_auth_token", return_value=True
        ),
        patch.object(
            grpc_client, "_refresh_session_tokens", return_value=True
        ) as refresh,
        patch.object(grpc_client, "_preflight_exec_auth_token", return_value=True),
        patch.object(
            grpc_client,
            "_send_exec_command",
            side_effect=[(False, True), (True, False)],
        ) as send,
    ):
        ok = grpc_client.exec_command(
            "playback_control.playback_command",
            string_value="pause",
        )

    assert ok is True
    assert send.call_count == 2
    refresh.assert_called_once()


def test_exec_command_no_retry_on_other_rpc_error(
    grpc_client: BraviaGrpcClient,
) -> None:
    with (
        patch.object(
            grpc_client, "_ensure_preflight_exec_auth_token", return_value=True
        ),
        patch.object(grpc_client, "_refresh_session_tokens") as refresh,
        patch.object(grpc_client, "_send_exec_command", return_value=(False, False)),
    ):
        ok = grpc_client.exec_command("volume", int_value=10)

    assert ok is False
    refresh.assert_not_called()


def test_preflight_uses_signed_get_states_and_mutex(
    grpc_client: BraviaGrpcClient,
) -> None:
    with (
        patch.object(
            grpc_client, "get_states_dict", return_value={"power": "on"}
        ) as gs,
        patch.object(grpc_client, "acquire_client_mutex", return_value=True) as mutex,
    ):
        ok = grpc_client._preflight_exec_auth_token()

    assert ok is True
    gs.assert_called_once_with(use_signed_auth=True)
    assert mutex.call_count == 2
    mutex.assert_called_with(use_signed_auth=True)


def test_preflight_fails_when_full_get_states_fails(
    grpc_client: BraviaGrpcClient,
) -> None:
    with (
        patch.object(grpc_client, "get_states_dict", return_value=None),
        patch.object(grpc_client, "acquire_client_mutex") as mutex,
    ):
        ok = grpc_client._preflight_exec_auth_token()

    assert ok is False
    mutex.assert_not_called()


def test_preflight_fails_when_mutex_fails(
    grpc_client: BraviaGrpcClient,
) -> None:
    with (
        patch.object(grpc_client, "get_states_dict", return_value={"power": "on"}),
        patch.object(grpc_client, "acquire_client_mutex", return_value=False),
    ):
        ok = grpc_client._preflight_exec_auth_token()

    assert ok is False


def test_send_exec_command_invalid_argument_flag(
    grpc_client: BraviaGrpcClient,
) -> None:
    rpc_error = grpc.RpcError()
    rpc_error.code = MagicMock(return_value=grpc.StatusCode.INVALID_ARGUMENT)
    rpc_error.details = MagicMock(return_value="invalid argument!")

    with (
        patch.object(grpc_client, "_sign_exec_auth_token", return_value=True),
        patch(
            "custom_components.bravia_quad.grpc.client.build_exec_command_with_auth_request",
            return_value=b"exec-req",
        ),
    ):
        unary = MagicMock()
        unary.future.return_value.result.side_effect = rpc_error
        grpc_client.channel.unary_unary.return_value = unary
        success, invalid = grpc_client._send_exec_command("volume", {"int_value": 5})

    assert success is False
    assert invalid is True
