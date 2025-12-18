"""Shared helpers for Bravia Quad integration."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from homeassistant.const import CONF_MAC, CONF_NAME
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC, DeviceInfo

from .const import CONF_MODEL, DEFAULT_MODEL, DOMAIN

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)


def migrate_legacy_identifiers(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """
    Migrate legacy device and entity identifiers from entry_id to unique_id format.

    This handles legacy entries created before discovery support was added,
    where devices and entities used entry.entry_id instead of entry.unique_id.
    """
    if entry.unique_id is None or entry.unique_id == entry.entry_id:
        # No migration needed - either no unique_id or they're the same
        return

    # Type narrowing: unique_id is now confirmed to be str
    unique_id: str = entry.unique_id

    _migrate_device(hass, entry.entry_id, unique_id)
    _migrate_entities(hass, entry.entry_id, unique_id)


def _migrate_device(hass: HomeAssistant, entry_id: str, unique_id: str) -> None:
    """Migrate device identifier from entry_id to unique_id format."""
    device_registry = dr.async_get(hass)

    old_identifier = (DOMAIN, entry_id)
    new_identifier = (DOMAIN, unique_id)

    # Find old device with entry_id-based identifier
    old_device = device_registry.async_get_device(identifiers={old_identifier})
    if old_device is None:
        return

    # Check if new device already exists
    new_device = device_registry.async_get_device(identifiers={new_identifier})

    if new_device:
        # Both devices exist - remove the old one (entities already migrated)
        _LOGGER.debug("Removing legacy device %s (new device exists)", old_device.id)
        device_registry.async_remove_device(old_device.id)
    else:
        # Migrate the old device to new identifier
        _LOGGER.debug(
            "Migrating device identifier: %s -> %s",
            old_identifier,
            new_identifier,
        )
        device_registry.async_update_device(
            old_device.id,
            new_identifiers={new_identifier},
        )

    _LOGGER.info("Migrated device from legacy identifier format")


def _migrate_entities(hass: HomeAssistant, entry_id: str, unique_id: str) -> None:
    """Migrate entity unique_ids from entry_id to unique_id format."""
    entity_registry = er.async_get(hass)
    old_prefix = f"{DOMAIN}_{entry_id}_"
    new_prefix = f"{DOMAIN}_{unique_id}_"
    migrated_count = 0

    # Get all entities for this config entry
    entities = er.async_entries_for_config_entry(entity_registry, entry_id)

    for entity_entry in entities:
        if not entity_entry.unique_id.startswith(old_prefix):
            continue

        # Build new unique_id by replacing the prefix
        suffix = entity_entry.unique_id[len(old_prefix) :]
        new_unique_id = f"{new_prefix}{suffix}"

        # Check if an entity with the new unique_id already exists
        existing = entity_registry.async_get_entity_id(
            entity_entry.domain,
            entity_entry.platform,
            new_unique_id,
        )

        if existing:
            # New entity exists, remove the old one
            _LOGGER.debug(
                "Removing duplicate legacy entity %s (new entity exists)",
                entity_entry.entity_id,
            )
            entity_registry.async_remove(entity_entry.entity_id)
        else:
            # Migrate to new unique_id
            _LOGGER.debug(
                "Migrating entity %s: %s -> %s",
                entity_entry.entity_id,
                entity_entry.unique_id,
                new_unique_id,
            )
            entity_registry.async_update_entity(
                entity_entry.entity_id, new_unique_id=new_unique_id
            )
        migrated_count += 1

    if migrated_count > 0:
        _LOGGER.info(
            "Migrated %d entities from legacy unique_id format", migrated_count
        )


def get_device_info(entry: ConfigEntry) -> DeviceInfo:
    """Return device info for a Bravia Quad device."""
    # Build connections set if MAC address is available
    connections: set[tuple[str, str]] = set()
    if CONF_MAC in entry.data:
        connections.add((CONNECTION_NETWORK_MAC, entry.data[CONF_MAC]))

    # unique_id must be set - all config flows set it via MAC address or host
    if entry.unique_id is None:
        msg = (
            f"Config entry {entry.entry_id} has no unique_id. "
            "This indicates a bug in the config flow."
        )
        raise ValueError(msg)

    return DeviceInfo(
        identifiers={(DOMAIN, entry.unique_id)},
        connections=connections,
        name=entry.data.get(CONF_NAME, DEFAULT_MODEL),
        manufacturer="Sony",
        model=entry.data.get(CONF_MODEL, DEFAULT_MODEL),
        configuration_url=f"http://{entry.data['host']}",
    )
