"""Shared helpers for Bravia Quad integration."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING, Any, Protocol, cast

from homeassistant.components.number import NumberMode, RestoreNumber
from homeassistant.const import CONF_HOST, CONF_MAC, EntityCategory
from homeassistant.core import State
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.restore_state import (
    StoredState,
)
from homeassistant.helpers.restore_state import (
    async_get as async_get_restore_state,
)
from homeassistant.util import dt as dt_util

from .const import DOMAIN, MAX_VOLUME_STEP_INTERVAL

if TYPE_CHECKING:
    from homeassistant.components.select import SelectEntity
    from homeassistant.components.switch import SwitchEntity
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant

    from .bravia_grpc_client import BraviaGrpcClientAsync
    from .bravia_quad_client import BraviaQuadClient
    from .grpc_mapping import GrpcTcpMapping

_LOGGER = logging.getLogger(__name__)


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

    Handles entry_id-based, IP-based, and MAC-based legacy formats.
    """
    legacy_keys = _legacy_keys(entry)
    if not legacy_keys:
        return

    target_key = require_unique_id(entry)
    for legacy_key in legacy_keys:
        _migrate_device(hass, legacy_key, target_key)
        _migrate_entities(hass, entry.entry_id, legacy_key, target_key)


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
    old_prefix = f"{DOMAIN}_{legacy_key}_"
    new_prefix = f"{DOMAIN}_{target_key}_"
    migrated_count = 0

    # Get all entities for this config entry
    entities = er.async_entries_for_config_entry(entity_registry, config_entry_id)

    for entity_entry in entities:
        if not entity_entry.unique_id or not entity_entry.unique_id.startswith(
            old_prefix
        ):
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
    """
    Return device info to link an entity to its device.

    Returns only identifiers so HA matches the entity to the device
    without overwriting the manufacturer/model set during setup.
    """
    return DeviceInfo(identifiers={(DOMAIN, require_unique_id(entry))})


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
        unique_id = f"{DOMAIN}_{uid}_{suffix}"
        if entity_id := entity_registry.async_get_entity_id(
            "select", DOMAIN, unique_id
        ):
            entity_registry.async_remove(entity_id)


class BraviaQuadAvailabilityMixin(Entity):
    """
    Mixin that tracks connection availability for Bravia Quad entities.

    Subclasses must define:
    - _client: BraviaQuadClient instance

    Provides an `available` property that reflects the TCP connection state
    and automatically updates HA when the connection drops or recovers.
    """

    _client: BraviaQuadClient

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self._client.is_connected

    def _on_availability_changed(self, _available: bool) -> None:  # noqa: FBT001
        """Handle connection availability change."""
        self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        """Register availability callback when entity is added."""
        await super().async_added_to_hass()
        self._client.register_availability_callback(self._on_availability_changed)

    async def async_will_remove_from_hass(self) -> None:
        """Unregister availability callback when entity is removed."""
        self._client.unregister_availability_callback(self._on_availability_changed)
        await super().async_will_remove_from_hass()


class BraviaQuadNotificationMixin(BraviaQuadAvailabilityMixin):
    """
    Mixin for entities that subscribe to Bravia Quad notifications.

    Subclasses must define:
    - _client: BraviaQuadClient instance
    - _notification_feature: str - the feature name to subscribe to
    - _on_notification: async callback method to handle notifications
    """

    _notification_feature: str

    async def _on_notification(self, value: str) -> None:
        """Handle notification callback. Override in subclass."""
        raise NotImplementedError

    async def async_added_to_hass(self) -> None:
        """Register notification callback when entity is added."""
        await super().async_added_to_hass()
        self._client.register_notification_callback(
            self._notification_feature, self._on_notification
        )

    async def async_will_remove_from_hass(self) -> None:
        """Unregister notification callback when entity is removed."""
        await super().async_will_remove_from_hass()
        self._client.unregister_notification_callback(
            self._notification_feature, self._on_notification
        )


class BraviaGrpcPathMixin(Entity):
    """
    Mixin for entities driven by gRPC field paths.

    Subclasses must define:
    - _grpc_client: BraviaGrpcClientAsync
    - _grpc_path: str
    - _on_grpc_state(value): async handler
    """

    _grpc_client: BraviaGrpcClientAsync
    _grpc_path: str

    @property
    def available(self) -> bool:
        """Entity is available when gRPC is connected."""
        return self._grpc_client.is_connected

    def _grpc_state_callback(self, update: Any) -> None:
        """Filter notify stream updates for this entity's path."""
        if update.path != self._grpc_path:
            return
        self.hass.async_create_task(self._on_grpc_state(update.value))

    async def _on_grpc_state(self, value: Any) -> None:
        """Handle gRPC state update. Override in subclass."""
        raise NotImplementedError

    async def async_added_to_hass(self) -> None:
        """Register gRPC notify callback when entity is added."""
        await super().async_added_to_hass()
        self._grpc_client.add_state_callback(self._grpc_state_callback)
        cached = self._grpc_client.notify_state.get(self._grpc_path)
        if cached is not None:
            await self._on_grpc_state(cached)

    async def async_will_remove_from_hass(self) -> None:
        """Remove gRPC callback when entity is removed."""
        self._grpc_client.remove_state_callback(self._grpc_state_callback)
        await super().async_will_remove_from_hass()


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


# Grace period (seconds) after a transition ends during which device
# notifications are still suppressed.  This prevents stale in-flight
# notifications from snapping the slider back to an intermediate value.
TRANSITION_NOTIFICATION_GRACE_PERIOD = 0.5


class VolumeStepClient(Protocol):
    """TCP client used by VolumeTransitionMixin default volume stepping."""

    volume_step_interval: int

    async def async_set_volume(self, volume: int) -> bool: ...

    async def async_get_volume(self) -> int: ...


class VolumeTransitionMixin:
    """
    Mixin that provides smooth volume transition logic.

    Subclasses must have:
    - self.hass: HomeAssistant
    - self.async_write_ha_state(): method
    - volume_step_interval property (ms between steps)
    - _async_volume_step(volume: int) -> bool

    Device notifications are suppressed while a transition is running **and**
    for a short grace period after it finishes so that stale notifications
    (still in-flight from the device) do not snap the slider back.  User
    actions (e.g. moving the slider) are never blocked.
    """

    hass: HomeAssistant

    if TYPE_CHECKING:
        _client: VolumeStepClient

    def _init_volume_transition(self) -> None:
        """Initialize volume transition state. Call from __init__."""
        self._transition_task: asyncio.Task[None] | None = None
        self._transition_in_progress: bool = False
        self._transition_generation: int = 0
        self._notification_suppressed_until: float = 0.0

    @property
    def volume_step_interval(self) -> int:
        """Return configured volume step interval in milliseconds."""
        return self._client.volume_step_interval

    async def _async_volume_step(self, volume: int) -> bool:
        """Set volume on the device; override for non-TCP transports."""
        return await self._client.async_set_volume(volume)

    @property
    def volume_transition_in_progress(self) -> bool:
        """Return whether a volume transition is in progress."""
        return self._transition_in_progress

    def should_suppress_volume_notification(self) -> bool:
        """
        Return True when device notifications should be ignored.

        Notifications are suppressed while a transition is active and
        for a short grace period afterwards so that stale in-flight
        notifications from the device do not snap the UI back.
        """
        if self._transition_in_progress:
            return True
        return time.monotonic() < self._notification_suppressed_until

    def _cancel_volume_transition(self) -> None:
        """Cancel any in-progress volume transition."""
        if self._transition_task:
            self._transition_task.cancel()
            self._transition_task = None
        if self._transition_in_progress:
            self._transition_in_progress = False
            self._notification_suppressed_until = (
                time.monotonic() + TRANSITION_NOTIFICATION_GRACE_PERIOD
            )

    async def _async_set_volume_with_transition(
        self,
        current_volume: int,
        target_volume: int,
    ) -> bool:
        """
        Set volume, using smooth transition if interval is configured.

        Returns True if the volume was set successfully (immediate) or a
        background transition was started.  Returns False only when an
        immediate set_volume call fails.
        Callers should set optimistic state before calling this method.
        """
        interval_ms = self.volume_step_interval

        # Cancel any existing transition
        self._cancel_volume_transition()

        if interval_ms <= 0 or current_volume == target_volume:
            self._transition_in_progress = False
            return await self._async_volume_step(target_volume)

        # Start background transition
        self._transition_in_progress = True
        self._transition_generation += 1
        generation = self._transition_generation

        self._transition_task = self.hass.async_create_task(
            self._async_volume_transition(
                current_volume, target_volume, interval_ms, generation
            )
        )
        return True

    async def _async_volume_transition(
        self,
        start_volume: int,
        end_volume: int,
        interval_ms: int,
        generation: int,
    ) -> None:
        """Transition volume smoothly one step at a time."""
        steps = abs(end_volume - start_volume)
        if steps == 0:
            self._transition_in_progress = False
            return

        delay = interval_ms / 1000.0
        step_increment = 1 if end_volume > start_volume else -1

        try:
            for i in range(1, steps + 1):
                await asyncio.sleep(delay)
                next_volume = start_volume + (i * step_increment)
                success = await self._async_volume_step(next_volume)
                if not success:
                    _LOGGER.warning("Failed to set volume step to %d", next_volume)
                    break
        except asyncio.CancelledError:
            _LOGGER.debug("Volume transition cancelled")
        finally:
            if self._transition_generation == generation:
                self._transition_in_progress = False
                self._notification_suppressed_until = (
                    time.monotonic() + TRANSITION_NOTIFICATION_GRACE_PERIOD
                )
                self._transition_task = None


class BraviaQuadVolumeStepIntervalNumber(RestoreNumber):
    """Local volume step interval for smooth volume transitions."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_has_entity_name = True
    _attr_mode = NumberMode.BOX
    _attr_native_max_value = MAX_VOLUME_STEP_INTERVAL
    _attr_native_min_value = 0
    _attr_native_step = 1
    _attr_native_unit_of_measurement = "ms"
    _attr_should_poll = False
    _attr_translation_key = "volume_step_interval"

    def __init__(
        self,
        entry: ConfigEntry,
        volume_step_client: BraviaQuadClient | BraviaGrpcClientAsync,
        *,
        enabled_default: bool = True,
    ) -> None:
        self._volume_step_client = volume_step_client
        self._attr_entity_registry_enabled_default = enabled_default
        self._attr_unique_id = f"{DOMAIN}_{entry.unique_id}_volume_step_interval"
        self._attr_device_info = get_device_info(entry)
        self._attr_native_value = volume_step_client.volume_step_interval

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if (
            last_state := await self.async_get_last_number_data()
        ) is not None and last_state.native_value is not None:
            self._attr_native_value = last_state.native_value
        if self._attr_native_value is None:
            return
        self._volume_step_client.volume_step_interval = int(self._attr_native_value)

    async def async_set_native_value(self, value: float) -> None:
        interval = int(value)
        self._volume_step_client.volume_step_interval = interval
        self._attr_native_value = value
        self.async_write_ha_state()
