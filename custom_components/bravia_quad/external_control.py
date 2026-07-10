"""Ensure TCP external control is enabled for gRPC setups that will use TCP-RPC."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from .bravia_quad_client import BraviaQuadClient
from .const import DEFAULT_NAME, EXTERNAL_CONTROL_ON

if TYPE_CHECKING:
    from .bravia_grpc_client import BraviaGrpcClientAsync

_LOGGER = logging.getLogger(__name__)

GRPC_EXTERNAL_CONTROL_PATH = "system_setting.external_control"


@dataclass(frozen=True, slots=True)
class ExternalControlEnsureResult:
    """Outcome of checking/enabling system.externalcontrol over TCP."""

    was_already_on: bool
    enabled_via: str | None
    tcp_reachable: bool
    external_control_on: bool
    error: str | None = None


async def async_ensure_external_control_enabled(
    host: str,
    *,
    name: str = DEFAULT_NAME,
    grpc_client: BraviaGrpcClientAsync | None = None,
) -> ExternalControlEnsureResult:
    """
    Ensure TCP ``system.externalcontrol`` is on before gRPC+TCP hybrid control.

    Reads the flag over TCP when possible. When off, enables via TCP first; if that
    fails, logs a warning and falls back to gRPC ``system_setting.external_control``.

    TCP connect failures are logged at debug (expected on gRPC-only models with no
    ``:33336`` listener). GetCapabilities does not advertise this path on current
    firmware, so it cannot gate the probe.
    """
    tcp = BraviaQuadClient(host, name)
    try:
        await tcp.async_connect()
    except (OSError, TimeoutError) as err:
        _LOGGER.debug(
            "Could not open TCP control plane on %s to verify external control: %s",
            host,
            err,
        )
        return await _grpc_fallback_enable(host, grpc_client, tcp_reachable=False)

    try:
        current = await tcp.async_get_external_control()
        if current == EXTERNAL_CONTROL_ON:
            _LOGGER.debug("External control already enabled on %s (TCP)", host)
            return ExternalControlEnsureResult(
                was_already_on=True,
                enabled_via=None,
                tcp_reachable=True,
                external_control_on=True,
            )

        _LOGGER.warning(
            "External control is off on %s; enabling via TCP before gRPC session use",
            host,
        )
        if await tcp.async_set_external_control(EXTERNAL_CONTROL_ON):
            verified = await tcp.async_get_external_control()
            if verified == EXTERNAL_CONTROL_ON:
                _LOGGER.info("Enabled external control on %s via TCP", host)
                return ExternalControlEnsureResult(
                    was_already_on=False,
                    enabled_via="tcp",
                    tcp_reachable=True,
                    external_control_on=True,
                )

        _LOGGER.warning(
            "TCP failed to enable external control on %s; trying gRPC fallback",
            host,
        )
        return await _grpc_fallback_enable(
            host,
            grpc_client,
            tcp_reachable=True,
            tcp_client=tcp,
        )
    finally:
        await tcp.async_disconnect()


async def _grpc_fallback_enable(
    host: str,
    grpc_client: BraviaGrpcClientAsync | None,
    *,
    tcp_reachable: bool,
    tcp_client: BraviaQuadClient | None = None,
) -> ExternalControlEnsureResult:
    """Enable external control via gRPC when TCP check/set is unavailable or failed."""
    if grpc_client is None or not grpc_client.is_connected:
        msg = "gRPC client not connected; cannot enable external control"
        log = _LOGGER.debug if not tcp_reachable else _LOGGER.error
        log(
            "External control is off on %s and %s",
            host,
            msg.lower(),
        )
        return ExternalControlEnsureResult(
            was_already_on=False,
            enabled_via=None,
            tcp_reachable=tcp_reachable,
            external_control_on=False,
            error=msg,
        )

    ok = await grpc_client.async_exec_command(
        GRPC_EXTERNAL_CONTROL_PATH,
        bool_value=True,
    )
    if not ok:
        msg = "gRPC ExecCommand for external control returned failure"
        log = _LOGGER.debug if not tcp_reachable else _LOGGER.error
        log(
            "External control is off on %s and could not be enabled via TCP or gRPC",
            host,
        )
        return ExternalControlEnsureResult(
            was_already_on=False,
            enabled_via=None,
            tcp_reachable=tcp_reachable,
            external_control_on=False,
            error=msg,
        )

    verified_on = False
    verify_tcp = tcp_client
    own_tcp = False
    if verify_tcp is None:
        verify_tcp = BraviaQuadClient(host, DEFAULT_NAME)
        own_tcp = True
        try:
            await verify_tcp.async_connect()
        except (OSError, TimeoutError):
            verify_tcp = None

    if verify_tcp is not None:
        try:
            verified_on = (
                await verify_tcp.async_get_external_control() == EXTERNAL_CONTROL_ON
            )
        finally:
            if own_tcp:
                await verify_tcp.async_disconnect()

    if verified_on:
        _LOGGER.info(
            "Enabled external control on %s via gRPC fallback (TCP verify OK)",
            host,
        )
    elif not tcp_reachable:
        _LOGGER.debug(
            "gRPC external-control fallback on %s with no TCP plane "
            "(expected on gRPC-only models)",
            host,
        )
    else:
        _LOGGER.warning(
            "Enabled external control on %s via gRPC fallback "
            "(TCP verify inconclusive)",
            host,
        )

    return ExternalControlEnsureResult(
        was_already_on=False,
        enabled_via="grpc",
        tcp_reachable=tcp_reachable,
        external_control_on=verified_on or ok,
        error=None if verified_on or ok else "gRPC enable unverified",
    )
