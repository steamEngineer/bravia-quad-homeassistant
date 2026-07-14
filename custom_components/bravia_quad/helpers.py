"""Shared helpers for Bravia Quad integration."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, cast

from homeassistant.const import CONF_HOST, CONF_MAC
from homeassistant.core import State
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.restore_state import (
    StoredState,
)
from homeassistant.helpers.restore_state import (
    async_get as async_get_restore_state,
)
from homeassistant.util import dt as dt_util

from .const import CONF_HAS_SUBWOOFER, DOMAIN

if TYPE_CHECKING:
    from homeassistant.components.select import SelectEntity
    from homeassistant.components.switch import SwitchEntity
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity import Entity

    from .bravia_grpc_client import BraviaGrpcClientAsync
    from .grpc_mapping import GrpcTcpMapping

_LOGGER = logging.getLogger(__name__)


async def async_apply_has_subwoofer(
    hass: HomeAssistant,
    entry: ConfigEntry,
    *,
    has_subwoofer: bool,
    reload: bool = False,
) -> bool:
    """
    Persist CONF_HAS_SUBWOOFER from topology detection.

    gRPC bass/subwoofer entities both exist and flip availability on link
    status, so this only updates entry data unless *reload* is True.
    Returns True when the stored flag changed.
    """
    if entry.data.get(CONF_HAS_SUBWOOFER) == has_subwoofer:
        return False

    _LOGGER.info(
        "Subwoofer detection result changed: %s -> %s",
        entry.data.get(CONF_HAS_SUBWOOFER),
        has_subwoofer,
    )
    hass.config_entries.async_update_entry(
        entry, data={**entry.data, CONF_HAS_SUBWOOFER: has_subwoofer}
    )

    if not reload:
        return True

    if not await hass.config_entries.async_reload(entry.entry_id):
        raise HomeAssistantError(
            translation_domain=DOMAIN,
            translation_key="reload_failed",
        )
    return True


def verify_feature_value[T: (str, int)](
    *,
    requested: T,
    actual: T | None,
    feature_label: str,
    valid_values: set[T] | None = None,
    mismatch_hint: str | None = None,
) -> T:
    """Raise HomeAssistantError if the device value differs from what was requested."""
    if actual is None:
        raise HomeAssistantError(
            translation_domain=DOMAIN,
            translation_key="verify_read_failed",
            translation_placeholders={
                "feature": feature_label,
                "requested": str(requested),
            },
        )

    if valid_values is not None and actual not in valid_values:
        raise HomeAssistantError(
            translation_domain=DOMAIN,
            translation_key="verify_unexpected_value",
            translation_placeholders={
                "feature": feature_label,
                "actual": str(actual),
            },
        )

    if actual != requested:
        placeholders: dict[str, str] = {
            "feature": feature_label,
            "requested": str(requested),
            "actual": str(actual),
        }
        if mismatch_hint:
            placeholders["hint"] = mismatch_hint
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="verify_value_mismatch_hint",
                translation_placeholders=placeholders,
            )
        raise HomeAssistantError(
            translation_domain=DOMAIN,
            translation_key="verify_value_mismatch",
            translation_placeholders=placeholders,
        )

    return actual


def raise_set_rejected(feature_label: str, requested: str) -> None:
    """Raise HomeAssistantError when the device rejects a SET command."""
    raise HomeAssistantError(
        translation_domain=DOMAIN,
        translation_key="verify_set_rejected",
        translation_placeholders={
            "feature": feature_label,
            "requested": requested,
        },
    )


def require_unique_id(entry: ConfigEntry) -> str:
    """Return config entry unique_id or raise if missing."""
    if entry.unique_id is None:
        msg = (
            f"Config entry {entry.entry_id} has no unique_id. "
            "This indicates a bug in the config flow."
        )
        raise ValueError(msg)
    return entry.unique_id


def _legacy_keys(entry: ConfigEntry) -> set[str]:
    """Return legacy identifier keys that differ from the current unique_id."""
    target = entry.unique_id
    if target is None:
        return set()
    keys = {entry.entry_id, entry.data.get(CONF_HOST), entry.data.get(CONF_MAC)}
    return {key for key in keys if key and key != target}


def migrate_legacy_identifiers(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """
    Migrate legacy device and entity identifiers to the current unique_id.

    Handles entry_id-based, IP-based, and MAC-based legacy formats, then
    strips the historical ``{DOMAIN}_`` entity unique_id prefix.
    """
    if entry.unique_id is None:
        return

    legacy_keys = _legacy_keys(entry)
    target_key = entry.unique_id
    for legacy_key in legacy_keys:
        _migrate_device(hass, legacy_key, target_key)
        _migrate_entities(hass, entry.entry_id, legacy_key, target_key)
    _migrate_domain_prefixed_entities(hass, entry.entry_id, target_key)


def _migrate_device(hass: HomeAssistant, legacy_key: str, target_key: str) -> None:
    """Migrate device identifier from legacy_key to target_key format."""
    device_registry = dr.async_get(hass)

    old_identifier = (DOMAIN, legacy_key)
    new_identifier = (DOMAIN, target_key)

    # Find old device with legacy identifier
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


def _migrate_entities(
    hass: HomeAssistant, config_entry_id: str, legacy_key: str, target_key: str
) -> None:
    """Migrate entity unique_ids from legacy_key prefix to target_key prefix."""
    entity_registry = er.async_get(hass)
    # Historical formats: DOMAIN_legacy_suffix and (post-strip) legacy_suffix
    old_prefixes = (f"{DOMAIN}_{legacy_key}_", f"{legacy_key}_")
    new_prefix = f"{target_key}_"
    migrated_count = 0

    # Get all entities for this config entry
    entities = er.async_entries_for_config_entry(entity_registry, config_entry_id)

    for entity_entry in entities:
        if not entity_entry.unique_id:
            continue

        matched_prefix: str | None = None
        for old_prefix in old_prefixes:
            if entity_entry.unique_id.startswith(old_prefix):
                matched_prefix = old_prefix
                break
        if matched_prefix is None:
            continue

        # Build new unique_id by replacing the prefix
        suffix = entity_entry.unique_id[len(matched_prefix) :]
        new_unique_id = f"{new_prefix}{suffix}"
        if entity_entry.unique_id == new_unique_id:
            continue

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


def _migrate_domain_prefixed_entities(
    hass: HomeAssistant, config_entry_id: str, target_key: str
) -> None:
    """Strip historical ``{DOMAIN}_{target_key}_`` entity unique_id prefix."""
    entity_registry = er.async_get(hass)
    old_prefix = f"{DOMAIN}_{target_key}_"
    new_prefix = f"{target_key}_"
    migrated_count = 0

    entities = er.async_entries_for_config_entry(entity_registry, config_entry_id)
    for entity_entry in entities:
        if not entity_entry.unique_id or not entity_entry.unique_id.startswith(
            old_prefix
        ):
            continue

        suffix = entity_entry.unique_id[len(old_prefix) :]
        new_unique_id = f"{new_prefix}{suffix}"
        existing = entity_registry.async_get_entity_id(
            entity_entry.domain,
            entity_entry.platform,
            new_unique_id,
        )
        if existing:
            _LOGGER.debug(
                "Removing duplicate domain-prefixed entity %s",
                entity_entry.entity_id,
            )
            entity_registry.async_remove(entity_entry.entity_id)
        else:
            entity_registry.async_update_entity(
                entity_entry.entity_id, new_unique_id=new_unique_id
            )
        migrated_count += 1

    if migrated_count > 0:
        _LOGGER.info(
            "Migrated %d entities off domain-prefixed unique_id format",
            migrated_count,
        )


def remove_legacy_group_subdevices(
    device_registry: dr.DeviceRegistry, entry: ConfigEntry
) -> None:
    """Remove Bravia Connect-style sub-devices from a prior grouping experiment."""
    uid = require_unique_id(entry)
    for suffix in ("playback", "sound", "sync", "wireless", "hdmi", "system"):
        legacy_ids = cast("set[tuple[str, str]]", {(DOMAIN, uid, suffix)})
        device = device_registry.async_get_device(identifiers=legacy_ids)
        if device is not None:
            device_registry.async_remove_device(device.id)


def remove_legacy_input_select(
    entity_registry: er.EntityRegistry, entry: ConfigEntry
) -> None:
    """Remove standalone selects superseded by the media player."""
    uid = require_unique_id(entry)
    for suffix in ("input", "sound_effect"):
        for unique_id in (f"{uid}_{suffix}", f"{DOMAIN}_{uid}_{suffix}"):
            if entity_id := entity_registry.async_get_entity_id(
                "select", DOMAIN, unique_id
            ):
                entity_registry.async_remove(entity_id)


async def _async_get_entity_last_state(entity: Entity) -> State | None:
    """Return persisted HA state from the previous run, if any."""
    if entity.hass is None or entity.entity_id is None:
        return None
    stored = async_get_restore_state(entity.hass).last_states.get(entity.entity_id)
    if stored is None:
        return None
    return stored.state


def _coerce_select_option(value: Any, options: list[str]) -> str | None:
    """Map a notify/exec value to a select option."""
    if value is None:
        return None
    text = str(value)
    if text in options:
        return text
    lower_map = {opt.lower(): opt for opt in options}
    return lower_map.get(text.lower())


def persist_notify_only_restore_state(entity: Entity, state: str | None) -> None:
    """Keep last good HA state when unload saves unknown/unavailable."""
    if (
        not state
        or state in ("unknown", "unavailable")
        or entity.hass is None
        or entity.entity_id is None
    ):
        return
    async_get_restore_state(entity.hass).last_states[entity.entity_id] = StoredState(
        State(entity.entity_id, state),
        None,
        dt_util.utcnow(),
    )


async def restore_last_select_option(entity: SelectEntity, options: list[str]) -> bool:
    """Apply last HA state to a select when gRPC has no initial value."""
    last = await _async_get_entity_last_state(entity)
    if last is None or last.state in ("unknown", "unavailable", ""):
        return False
    if last.state not in options:
        options.append(last.state)
        entity._attr_options = options
    entity._attr_current_option = last.state
    entity.async_write_ha_state()
    return True


async def restore_last_switch_state(entity: SwitchEntity) -> bool:
    """Apply last HA on/off state when gRPC has no initial value."""
    last = await _async_get_entity_last_state(entity)
    if last is None or last.state not in ("on", "off"):
        return False
    entity._attr_is_on = last.state == "on"
    entity.async_write_ha_state()
    return True


async def restore_notify_only_switch(
    entity: SwitchEntity,
    grpc_client: BraviaGrpcClientAsync,
    grpc_path: str,
) -> bool:
    """Restore last HA on/off for unreadable gRPC paths and seed notify cache."""
    last = await _async_get_entity_last_state(entity)
    is_on: bool | None = None
    if last is not None and last.state in ("on", "off"):
        is_on = last.state == "on"
    if is_on is None:
        cached = grpc_client.notify_state.get(grpc_path)
        if isinstance(cached, bool):
            is_on = cached
        elif isinstance(cached, int):
            is_on = cached != 0
    if is_on is None:
        return False
    entity._attr_is_on = is_on
    grpc_client.merge_notify_cache({grpc_path: is_on})
    return True


async def restore_notify_only_select(
    entity: SelectEntity,
    grpc_client: BraviaGrpcClientAsync,
    grpc_path: str,
    options: list[str],
    *,
    mapping: GrpcTcpMapping | None = None,
) -> bool:
    """Restore last HA option for unreadable gRPC paths and seed notify cache."""
    last = await _async_get_entity_last_state(entity)
    option: str | None = None
    if last is not None and last.state not in ("unknown", "unavailable", ""):
        option = last.state
    if option is None:
        option = _coerce_select_option(grpc_client.notify_state.get(grpc_path), options)
    if option is None:
        return False
    if option not in options:
        options.append(option)
        entity._attr_options = options
    entity._attr_current_option = option
    if mapping is not None:
        from .grpc_value_normalize import denormalize_for_exec

        _, cache_value = denormalize_for_exec(mapping, option)
    else:
        cache_value = option
    if cache_value is not None:
        grpc_client.merge_notify_cache({grpc_path: cache_value})
    return True
