"""Shared helpers for Bravia Quad integration."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from homeassistant.const import CONF_MAC
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC, DeviceInfo

from .const import DOMAIN

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)


def migrate_entity_unique_ids(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """
    Migrate entity unique_ids from entry_id to unique_id format.

    This handles legacy entries created before discovery support was added,
    where entities used entry.entry_id instead of entry.unique_id.
    """
    if entry.unique_id is None or entry.unique_id == entry.entry_id:
        # No migration needed - either no unique_id or they're the same
        return

    entity_registry = er.async_get(hass)
    old_prefix = f"{DOMAIN}_{entry.entry_id}_"
    new_prefix = f"{DOMAIN}_{entry.unique_id}_"
    migrated_count = 0

    # Get all entities for this config entry
    entities = er.async_entries_for_config_entry(entity_registry, entry.entry_id)

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
        name=entry.data.get("name", "Bravia Quad"),
        manufacturer="Sony",
        model="Bravia Quad",
        configuration_url=f"http://{entry.data['host']}",
    )
