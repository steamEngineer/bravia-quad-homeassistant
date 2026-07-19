"""Shared entity bases for Bravia Quad."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING, Any, Protocol

from homeassistant.components.number import NumberMode, RestoreNumber
from homeassistant.const import EntityCategory
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity

from .const import DOMAIN, MAX_VOLUME_STEP_INTERVAL
from .helpers import require_unique_id

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant

    from .bravia_grpc_client import BraviaGrpcClientAsync
    from .bravia_quad_client import BraviaQuadClient

_LOGGER = logging.getLogger(__name__)

# Grace period (seconds) after a transition ends during which device
# notifications are still suppressed.  This prevents stale in-flight
# notifications from snapping the slider back to an intermediate value.
TRANSITION_NOTIFICATION_GRACE_PERIOD = 0.5


def entity_unique_id(entry: ConfigEntry, suffix: str) -> str:
    """Return entity unique_id as ``{config_entry.unique_id}_{suffix}``."""
    return f"{require_unique_id(entry)}_{suffix}"


def get_device_info(entry: ConfigEntry) -> DeviceInfo:
    """
    Return device info to link an entity to its device.

    Returns only identifiers so HA matches the entity to the device
    without overwriting the manufacturer/model set during setup.
    """
    return DeviceInfo(identifiers={(DOMAIN, require_unique_id(entry))})


class BraviaQuadAvailabilityMixin(Entity):
    """
    Mixin that tracks connection availability for Bravia Quad entities.

    Subclasses must define:
    - _client: BraviaQuadClient instance

    Provides an `available` property that reflects the TCP connection state
    and automatically updates HA when the connection drops or recovers.
    """

    _client: BraviaQuadClient
    _unavailable_logged: bool = False

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self._client.is_connected

    def _on_availability_changed(self, available: bool) -> None:  # noqa: FBT001
        """Handle connection availability change."""
        if not available:
            if not self._unavailable_logged:
                _LOGGER.info("%s is unavailable", self.entity_id)
                self._unavailable_logged = True
        elif self._unavailable_logged:
            _LOGGER.info("%s is back online", self.entity_id)
            self._unavailable_logged = False
        self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        """Register availability callback when entity is added."""
        await super().async_added_to_hass()
        self._client.register_availability_callback(self._on_availability_changed)
        self.async_on_remove(
            lambda: self._client.unregister_availability_callback(
                self._on_availability_changed
            )
        )


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
        self.async_on_remove(
            lambda: self._client.unregister_notification_callback(
                self._notification_feature, self._on_notification
            )
        )


class BraviaGrpcAvailabilityMixin(Entity):
    """
    Mixin that tracks gRPC session availability for HA entities.

    Subclasses must define _grpc_client: BraviaGrpcClientAsync.
    """

    _grpc_client: BraviaGrpcClientAsync
    _unavailable_logged: bool = False

    @property
    def available(self) -> bool:
        """Entity is available when gRPC is connected."""
        return self._grpc_client.is_connected

    def _on_grpc_availability_changed(self, available: bool) -> None:  # noqa: FBT001
        """Handle gRPC session availability change."""
        if not available:
            if not self._unavailable_logged:
                _LOGGER.info("%s is unavailable", self.entity_id)
                self._unavailable_logged = True
        elif self._unavailable_logged:
            _LOGGER.info("%s is back online", self.entity_id)
            self._unavailable_logged = False
        self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        """Register gRPC availability callback when entity is added."""
        await super().async_added_to_hass()
        self._grpc_client.register_availability_callback(
            self._on_grpc_availability_changed
        )
        self.async_on_remove(
            lambda: self._grpc_client.unregister_availability_callback(
                self._on_grpc_availability_changed
            )
        )


class BraviaGrpcPathMixin(BraviaGrpcAvailabilityMixin):
    """
    Mixin for entities driven by gRPC field paths.

    Subclasses must define:
    - _grpc_client: BraviaGrpcClientAsync
    - _grpc_path: str
    - _on_grpc_state(value): async handler
    """

    _grpc_path: str

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
        self.async_on_remove(
            lambda: self._grpc_client.remove_state_callback(self._grpc_state_callback)
        )
        cached = self._grpc_client.notify_state.get(self._grpc_path)
        if cached is not None:
            await self._on_grpc_state(cached)


class VolumeStepClient(Protocol):
    """TCP client used by VolumeTransitionMixin default volume stepping."""

    volume_step_interval: int

    async def async_set_volume(self, volume: int) -> bool:
        """Set absolute volume on the device."""
        ...

    async def async_get_volume(self) -> int:
        """Return current volume from the device."""
        ...


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
        """Initialize volume step interval number."""
        self._volume_step_client = volume_step_client
        self._attr_entity_registry_enabled_default = enabled_default
        self._attr_unique_id = entity_unique_id(entry, "volume_step_interval")
        self._attr_device_info = get_device_info(entry)
        self._attr_native_value = volume_step_client.volume_step_interval

    async def async_added_to_hass(self) -> None:
        """Restore last interval and apply to the client."""
        await super().async_added_to_hass()
        if (
            last_state := await self.async_get_last_number_data()
        ) is not None and last_state.native_value is not None:
            self._attr_native_value = last_state.native_value
        if self._attr_native_value is None:
            return
        self._volume_step_client.volume_step_interval = int(self._attr_native_value)

    async def async_set_native_value(self, value: float) -> None:
        """Set the volume step interval."""
        interval = int(value)
        self._volume_step_client.volume_step_interval = interval
        self._attr_native_value = value
        self.async_write_ha_state()
