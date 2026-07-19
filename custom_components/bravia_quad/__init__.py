"""The Bravia Quad integration."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_MAC, CONF_NAME, EVENT_HOMEASSISTANT_STOP, Platform
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .bravia_http_client import HTTP_API_PORT, BraviaHttpClient
from .bravia_quad_client import BraviaQuadClient
from .const import (
    CONF_HAS_SUBWOOFER,
    CONF_MANUFACTURER,
    CONF_MODEL,
    CONF_MODEL_ID,
    CONF_SERIAL,
    DEFAULT_MODEL,
    DEFAULT_NAME,
    DOMAIN,
    MODEL_ID_TO_NAME,
    TRANSPORT_TCP,
)
from .grpc_refresh import async_setup_grpc_client
from .helpers import (
    async_apply_has_subwoofer,
    migrate_legacy_identifiers,
    remove_legacy_group_subdevices,
    remove_legacy_input_select,
    require_unique_id,
)
from .transport import (
    detect_subwoofer_from_grpc,
    migrate_transport_entry,
    resolve_transport,
)

if TYPE_CHECKING:
    from homeassistant.core import Event, HomeAssistant

    from .bravia_grpc_client import BraviaGrpcClientAsync


@dataclass
class BraviaQuadData:
    """Runtime data for a Bravia Quad config entry."""

    transport: str
    http_client: BraviaHttpClient
    tcp_client: BraviaQuadClient | None = None
    grpc_client: BraviaGrpcClientAsync | None = None


type BraviaQuadConfigEntry = ConfigEntry[BraviaQuadData]


_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.BUTTON,
    Platform.MEDIA_PLAYER,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
    Platform.UPDATE,
]


async def async_setup_entry(hass: HomeAssistant, entry: BraviaQuadConfigEntry) -> bool:
    """Set up Bravia Quad from a config entry."""
    migrate_transport_entry(hass, entry)
    transport = resolve_transport(entry)

    session = async_get_clientsession(hass)
    http_client = BraviaHttpClient(entry.data["host"], session)
    await http_client.async_probe_reachable()

    tcp_client: BraviaQuadClient | None = None
    grpc_client: BraviaGrpcClientAsync | None = None

    if transport == TRANSPORT_TCP:
        tcp_client = await _setup_tcp_client(hass, entry)
    else:
        grpc_client = await async_setup_grpc_client(hass, entry)
        if grpc_client is None:
            raise ConfigEntryNotReady
        await _async_recompute_grpc_subwoofer(hass, entry, grpc_client)

    migrate_legacy_identifiers(hass, entry)

    if transport == TRANSPORT_TCP:
        if tcp_client is None:
            msg = "TCP transport requires tcp_client"
            raise ConfigEntryNotReady(msg)
        await _register_device(hass, entry, http_client, tcp_client=tcp_client)
    else:
        await _register_device(hass, entry, http_client, _grpc_client=grpc_client)

    entry.runtime_data = BraviaQuadData(
        transport=transport,
        http_client=http_client,
        tcp_client=tcp_client,
        grpc_client=grpc_client,
    )
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    if grpc_client is not None:
        grpc_client.dispatch_snapshot_callbacks()

    entry.async_on_unload(entry.add_update_listener(_async_options_updated))

    if grpc_client is not None:

        async def _async_stop_grpc(_event: Event) -> None:
            await grpc_client.async_disconnect()

        entry.async_on_unload(
            hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, _async_stop_grpc)
        )

    return True


async def _async_recompute_grpc_subwoofer(
    hass: HomeAssistant,
    entry: BraviaQuadConfigEntry,
    grpc_client: BraviaGrpcClientAsync,
) -> None:
    """Correct CONF_HAS_SUBWOOFER from seeded notify_state (no reload)."""
    detected = detect_subwoofer_from_grpc(grpc_client.notify_state)
    if await async_apply_has_subwoofer(hass, entry, has_subwoofer=detected):
        _LOGGER.info("gRPC subwoofer detection at setup: %s", detected)


async def _async_options_updated(
    hass: HomeAssistant, entry: BraviaQuadConfigEntry
) -> None:
    """Reload when integration options change."""
    # Feature-reason persistence writes entry.data and must not reload.
    meta = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    if isinstance(meta, dict) and meta.pop("_suppress_entry_reload", False):
        return
    await hass.config_entries.async_reload(entry.entry_id)


async def _setup_tcp_client(
    hass: HomeAssistant, entry: BraviaQuadConfigEntry
) -> BraviaQuadClient:
    """Connect TCP control plane and seed device state."""
    client = BraviaQuadClient(
        entry.data["host"], entry.data.get(CONF_NAME, DEFAULT_NAME)
    )

    try:
        await client.async_connect()
        await client.async_test_connection()
    except (OSError, TimeoutError) as err:
        await client.async_disconnect()
        raise ConfigEntryNotReady from err

    await asyncio.sleep(0.2)
    await client.async_listen_for_notifications()

    await _backfill_identity(hass, entry, client)
    await client.async_fetch_all_states()

    if CONF_HAS_SUBWOOFER not in entry.data:
        _LOGGER.info("Detecting subwoofer for existing entry...")
        try:
            has_subwoofer = await client.async_detect_subwoofer()
        except (OSError, TimeoutError):
            _LOGGER.warning(
                "Subwoofer detection failed due to connection error, "
                "defaulting to False"
            )
            has_subwoofer = False
        new_data = {**entry.data, CONF_HAS_SUBWOOFER: has_subwoofer}
        hass.config_entries.async_update_entry(entry, data=new_data)
        _LOGGER.info("Subwoofer detection complete: %s", has_subwoofer)

    return client


async def _backfill_identity(
    hass: HomeAssistant, entry: BraviaQuadConfigEntry, client: BraviaQuadClient
) -> None:
    """Backfill permanent identity for entries created before this version."""
    if CONF_MODEL_ID in entry.data:
        return

    _LOGGER.info("Backfilling device identity for existing entry...")
    updates: dict[str, str] = {}

    try:
        serial = await client.async_get_serial_number()
        if serial:
            updates[CONF_SERIAL] = serial
    except (OSError, TimeoutError):
        _LOGGER.debug("Failed to fetch serial number")

    try:
        model_type = await client.async_get_model_type()
        if model_type:
            updates[CONF_MODEL_ID] = model_type
            if CONF_MODEL not in entry.data:
                updates[CONF_MODEL] = MODEL_ID_TO_NAME.get(model_type, model_type)
    except (OSError, TimeoutError):
        _LOGGER.debug("Failed to fetch model type")

    try:
        manufacturer = await client.async_get_manufacturer()
        if manufacturer:
            updates[CONF_MANUFACTURER] = manufacturer
    except (OSError, TimeoutError):
        _LOGGER.debug("Failed to fetch manufacturer")

    try:
        mac = await client.async_get_mac_address()
        if mac and CONF_MAC not in entry.data:
            updates[CONF_MAC] = dr.format_mac(mac)
    except (OSError, TimeoutError):
        _LOGGER.debug("Failed to fetch MAC address")

    if updates:
        new_unique_id = updates.get(CONF_SERIAL)
        hass.config_entries.async_update_entry(
            entry,
            data={**entry.data, **updates},
            unique_id=new_unique_id or entry.unique_id,
        )
        _LOGGER.info("Backfilled device identity: %s", list(updates.keys()))


async def _register_device(
    hass: HomeAssistant,
    entry: BraviaQuadConfigEntry,
    http_client: BraviaHttpClient,
    *,
    tcp_client: BraviaQuadClient | None = None,
    _grpc_client: BraviaGrpcClientAsync | None = None,
) -> None:
    """Create or update the device registry entry."""
    manufacturer = entry.data.get(CONF_MANUFACTURER, "Sony")
    model = entry.data.get(CONF_MODEL, DEFAULT_MODEL)
    model_id = entry.data.get(CONF_MODEL_ID)
    serial = entry.data.get(CONF_SERIAL)

    firmware_version: str | None = None
    if http_client.reachable:
        try:
            system_info = await http_client.async_get_system_info()
            if system_info:
                firmware_version = system_info.version
        except OSError:
            _LOGGER.debug("Failed to fetch firmware version from HTTP")

    if firmware_version is None and tcp_client is not None:
        try:
            firmware_version = await tcp_client.async_get_firmware_version()
        except (OSError, TimeoutError):
            _LOGGER.debug("Failed to fetch firmware version from TCP")

    connections: set[tuple[str, str]] = set()
    if CONF_MAC in entry.data:
        connections.add((dr.CONNECTION_NETWORK_MAC, entry.data[CONF_MAC]))

    if tcp_client is not None:
        try:
            active_mac = await tcp_client.async_get_mac_address()
            if active_mac:
                connections.add((dr.CONNECTION_NETWORK_MAC, dr.format_mac(active_mac)))
        except (OSError, TimeoutError):
            _LOGGER.debug("Failed to fetch active MAC from TCP")

    configuration_url = (
        f"http://{entry.data['host']}:{HTTP_API_PORT}"
        if http_client.reachable
        else None
    )
    dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, require_unique_id(entry))},
        connections=connections,
        name=entry.data.get(CONF_NAME, DEFAULT_NAME),
        manufacturer=manufacturer,
        model=model,
        model_id=model_id,
        serial_number=serial,
        sw_version=firmware_version,
        configuration_url=configuration_url,
    )
    remove_legacy_group_subdevices(dr.async_get(hass), entry)
    remove_legacy_input_select(er.async_get(hass), entry)


async def async_unload_entry(hass: HomeAssistant, entry: BraviaQuadConfigEntry) -> bool:
    """Unload a config entry."""
    # Setup may fail before runtime_data is assigned (ConfigEntryNotReady).
    if hasattr(entry, "runtime_data"):
        data = entry.runtime_data
        if data.tcp_client:
            await data.tcp_client.async_disconnect()
        if data.grpc_client:
            await data.grpc_client.async_disconnect()

    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
