"""TCP seed for gRPC notify-only entity paths."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from .bravia_quad_client import BraviaQuadClient
from .const import DEFAULT_NAME
from .grpc_mapping import mappings_for_tcp_seed
from .grpc_value_normalize import denormalize_for_exec

if TYPE_CHECKING:
    from .bravia_grpc_client import BraviaGrpcClientAsync

_LOGGER = logging.getLogger(__name__)


async def async_seed_notify_only_from_tcp(
    host: str,
    grpc_client: BraviaGrpcClientAsync,
    *,
    name: str = DEFAULT_NAME,
) -> int:
    """TCP-get unset entity paths; return count seeded."""
    pending = mappings_for_tcp_seed(grpc_client.notify_state)
    if not pending:
        return 0

    tcp = BraviaQuadClient(host, name)
    try:
        await tcp.async_connect()
    except (ConnectionError, OSError, TimeoutError) as err:
        _LOGGER.debug(
            "TCP seed skipped for unset entity paths on %s: %s",
            host,
            err,
        )
        return 0

    seeded = 0
    try:
        for mapping in pending:
            tcp_feature = mapping.tcp_feature
            if tcp_feature is None:
                continue
            raw = await tcp.async_get_tcp_feature(tcp_feature)
            if raw is None:
                continue
            if not raw:
                continue
            _, value = denormalize_for_exec(mapping, raw)
            if value is None:
                continue
            grpc_client.merge_notify_cache({mapping.grpc_path: value})
            seeded += 1
    finally:
        await tcp.async_disconnect()

    if seeded:
        _LOGGER.info(
            "TCP seeded %d unset gRPC entity path(s) on %s",
            seeded,
            host,
        )
    return seeded
