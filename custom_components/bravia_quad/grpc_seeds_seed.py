"""Sony Seeds cloud seed for gRPC-unreadable entity paths."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .grpc.credentials import GrpcCredentialsRefreshError, async_get_device_states
from .grpc_mapping import NOTIFY_ONLY_GRPC_PATHS

if TYPE_CHECKING:
    from .bravia_grpc_client import BraviaGrpcClientAsync

_LOGGER = logging.getLogger(__name__)

_SOUND_EFFECT_PATH = "sound_setting.sound_effect"

# Paths filled from Seeds when unset in notify cache (see docs/seeds-cloud-states.md).
SEEDS_SEED_PATHS: frozenset[str] = frozenset(NOTIFY_ONLY_GRPC_PATHS) | {
    _SOUND_EFFECT_PATH
}


def parse_seeds_device_states(raw: dict[str, Any]) -> dict[str, Any]:
    """Parse GET /devices/{id}/states into grpc_path → value."""
    states = raw.get("states")
    if not isinstance(states, list):
        return {}
    parsed: dict[str, Any] = {}
    for item in states:
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        if name is None or "value" not in item:
            continue
        parsed[str(name)] = item["value"]
    return parsed


async def async_seed_from_seeds(
    hass: Any,
    credentials: dict[str, Any],
    grpc_client: BraviaGrpcClientAsync,
    *,
    paths: frozenset[str] | None = None,
) -> int:
    """Fetch Seeds /states and merge unset allowlisted paths into notify cache."""
    access_token = credentials.get("access_token")
    device_id = credentials.get("device_id")
    if not access_token or not device_id:
        return 0

    allowlist = paths or SEEDS_SEED_PATHS
    pending = {path for path in allowlist if grpc_client.notify_state.get(path) is None}
    if not pending:
        return 0

    session = async_get_clientsession(hass)
    try:
        raw = await async_get_device_states(session, device_id, access_token)
    except GrpcCredentialsRefreshError as err:
        _LOGGER.debug(
            "Seeds state seed skipped for %s: %s",
            grpc_client.host,
            err,
        )
        return 0
    except OSError as err:
        _LOGGER.debug(
            "Seeds state seed skipped for %s: %s",
            grpc_client.host,
            err,
        )
        return 0

    flat = parse_seeds_device_states(raw)
    updates = {path: flat[path] for path in pending if path in flat}
    if not updates:
        return 0

    grpc_client.merge_notify_cache(updates)
    _LOGGER.info(
        "Seeds seeded %d unset gRPC entity path(s) on %s",
        len(updates),
        grpc_client.host,
    )
    return len(updates)
