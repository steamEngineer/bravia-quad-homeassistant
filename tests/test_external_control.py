"""Tests for external control ensure helper."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from custom_components.bravia_quad.external_control import (
    ExternalControlEnsureResult,
    async_ensure_external_control_enabled,
)

TEST_HOST = "192.168.1.100"


def _tcp_mock(
    *,
    connect_ok: bool = True,
    get_values: list[str | None] | None = None,
    set_ok: bool = True,
) -> MagicMock:
    mock = MagicMock()
    mock.async_connect = (
        AsyncMock() if connect_ok else AsyncMock(side_effect=OSError("refused"))
    )
    mock.async_disconnect = AsyncMock()
    mock.async_get_external_control = AsyncMock(
        side_effect=get_values if get_values is not None else ["on"]
    )
    mock.async_set_external_control = AsyncMock(return_value=set_ok)
    return mock


def _grpc_mock(
    *,
    connected: bool = True,
    exec_ok: bool = True,
    capability_paths: frozenset[str] | None = None,
) -> MagicMock:
    mock = MagicMock()
    mock.is_connected = connected
    mock.async_exec_command = AsyncMock(return_value=exec_ok)
    mock.capability_paths = capability_paths
    return mock


async def test_skips_when_path_absent_from_capabilities() -> None:
    """No TCP probe or gRPC exec when GetCapabilities omits external_control."""
    grpc = _grpc_mock(capability_paths=frozenset({"power"}))
    with patch(
        "custom_components.bravia_quad.external_control.BraviaQuadClient",
    ) as tcp_cls:
        result = await async_ensure_external_control_enabled(
            TEST_HOST, grpc_client=grpc
        )

    assert result == ExternalControlEnsureResult(
        was_already_on=False,
        enabled_via=None,
        tcp_reachable=False,
        external_control_on=False,
        skipped=True,
    )
    tcp_cls.assert_not_called()
    grpc.async_exec_command.assert_not_called()


async def test_probes_when_path_present_in_capabilities() -> None:
    """TCP ensure still runs when capabilities advertise external_control."""
    tcp = _tcp_mock(get_values=["on"])
    grpc = _grpc_mock(
        capability_paths=frozenset({"system_setting.external_control", "power"})
    )
    with patch(
        "custom_components.bravia_quad.external_control.BraviaQuadClient",
        return_value=tcp,
    ):
        result = await async_ensure_external_control_enabled(
            TEST_HOST, grpc_client=grpc
        )

    assert result == ExternalControlEnsureResult(
        was_already_on=True,
        enabled_via=None,
        tcp_reachable=True,
        external_control_on=True,
    )
    tcp.async_connect.assert_awaited()
    grpc.async_exec_command.assert_not_called()


async def test_probes_when_capabilities_none() -> None:
    """Soft-fail capabilities (None) keep legacy TCP → gRPC fallback."""
    grpc = _grpc_mock(capability_paths=None)
    verify_tcp = _tcp_mock(get_values=["on"])
    with patch(
        "custom_components.bravia_quad.external_control.BraviaQuadClient",
        side_effect=[_tcp_mock(connect_ok=False), verify_tcp],
    ):
        result = await async_ensure_external_control_enabled(
            TEST_HOST, grpc_client=grpc
        )

    assert result.enabled_via == "grpc"
    assert result.tcp_reachable is False
    assert result.external_control_on is True
    assert result.skipped is False


async def test_already_on_skips_enable() -> None:
    """No set/exec when TCP reports external control on."""
    tcp = _tcp_mock(get_values=["on"])
    with patch(
        "custom_components.bravia_quad.external_control.BraviaQuadClient",
        return_value=tcp,
    ):
        result = await async_ensure_external_control_enabled(TEST_HOST)

    assert result == ExternalControlEnsureResult(
        was_already_on=True,
        enabled_via=None,
        tcp_reachable=True,
        external_control_on=True,
    )
    tcp.async_set_external_control.assert_not_called()


async def test_enables_via_tcp_when_off() -> None:
    """Off flag is turned on over TCP without gRPC fallback."""
    tcp = _tcp_mock(get_values=["off", "on"])
    with patch(
        "custom_components.bravia_quad.external_control.BraviaQuadClient",
        return_value=tcp,
    ):
        result = await async_ensure_external_control_enabled(TEST_HOST)

    assert result.enabled_via == "tcp"
    assert result.external_control_on is True
    tcp.async_set_external_control.assert_awaited_once_with("on")


async def test_tcp_set_failure_falls_back_to_grpc() -> None:
    """Failed TCP set triggers gRPC ExecCommand fallback."""
    tcp = _tcp_mock(get_values=["off", "on"], set_ok=False)
    grpc = _grpc_mock()
    with patch(
        "custom_components.bravia_quad.external_control.BraviaQuadClient",
        return_value=tcp,
    ):
        result = await async_ensure_external_control_enabled(
            TEST_HOST, grpc_client=grpc
        )

    assert result.enabled_via == "grpc"
    assert result.external_control_on is True
    grpc.async_exec_command.assert_awaited_once_with(
        "system_setting.external_control",
        bool_value=True,
    )


async def test_tcp_unreachable_uses_grpc_fallback() -> None:
    """When TCP cannot connect, gRPC fallback is attempted."""
    grpc = _grpc_mock()
    verify_tcp = _tcp_mock(get_values=["on"])
    with patch(
        "custom_components.bravia_quad.external_control.BraviaQuadClient",
        side_effect=[_tcp_mock(connect_ok=False), verify_tcp],
    ):
        result = await async_ensure_external_control_enabled(
            TEST_HOST, grpc_client=grpc
        )

    assert result.enabled_via == "grpc"
    assert result.tcp_reachable is False
    assert result.external_control_on is True


async def test_both_transports_fail() -> None:
    """Return error when TCP and gRPC enable both fail."""
    tcp = _tcp_mock(get_values=["off"], set_ok=False)
    grpc = _grpc_mock(exec_ok=False)
    with patch(
        "custom_components.bravia_quad.external_control.BraviaQuadClient",
        return_value=tcp,
    ):
        result = await async_ensure_external_control_enabled(
            TEST_HOST, grpc_client=grpc
        )

    assert result.external_control_on is False
    assert result.error is not None
