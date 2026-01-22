"""Number platform for Bravia Quad controls."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

from homeassistant.components.number import NumberEntity, NumberMode, RestoreNumber
from homeassistant.const import EntityCategory

from .const import (
    CONF_HAS_SUBWOOFER,
    DOMAIN,
    FEATURE_BASS_LEVEL,
    FEATURE_REAR_LEVEL,
    FEATURE_VOLUME,
    MAX_BASS_LEVEL,
    MAX_REAR_LEVEL,
    MAX_VOLUME_STEP_INTERVAL,
    MIN_BASS_LEVEL,
    MIN_REAR_LEVEL,
)
from .helpers import BraviaQuadNotificationMixin, get_device_info

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from .bravia_quad_client import BraviaQuadClient

_LOGGER = logging.getLogger(__name__)

# Constants for validation ranges
MAX_VOLUME = 100


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Bravia Quad number entities from a config entry."""
    client: BraviaQuadClient = hass.data[DOMAIN][entry.entry_id]

    # Create number entities
    entities: list[NumberEntity] = [
        BraviaQuadVolumeNumber(client, entry),
        BraviaQuadRearLevelNumber(client, entry),
        BraviaQuadVolumeStepIntervalNumber(client, entry),
    ]

    # Only add bass level slider if subwoofer is detected
    if entry.data.get(CONF_HAS_SUBWOOFER, False):
        entities.append(BraviaQuadBassLevelNumber(client, entry))

    async_add_entities(entities)


class BraviaQuadVolumeNumber(BraviaQuadNotificationMixin, NumberEntity):
    """Representation of a Bravia Quad volume control."""

    _attr_entity_registry_enabled_default = False
    _attr_has_entity_name = True
    _attr_mode = NumberMode.SLIDER
    _attr_native_max_value = MAX_VOLUME
    _attr_native_min_value = 0
    _attr_native_step = 1
    _attr_should_poll = False
    _attr_translation_key = "volume"
    _notification_feature = FEATURE_VOLUME

    def __init__(self, client: BraviaQuadClient, entry: ConfigEntry) -> None:
        """Initialize the volume number entity."""
        self._client = client
        self._attr_unique_id = f"{DOMAIN}_{entry.unique_id}_volume"
        self._attr_native_value = client.volume
        self._attr_device_info = get_device_info(entry)
        self._transition_task: asyncio.Task[None] | None = None
        self._transition_in_progress = False
        self._transition_generation = 0

    async def _on_notification(self, value: Any) -> None:
        """Handle volume notification."""
        # Skip UI updates during transition to prevent jerky slider movement
        if self._transition_in_progress:
            return

        try:
            volume = int(value)
            if 0 <= volume <= MAX_VOLUME:
                self._attr_native_value = volume
                self.async_write_ha_state()
        except (ValueError, TypeError):
            _LOGGER.warning("Invalid volume notification value: %s", value)

    async def async_set_native_value(self, value: float) -> None:
        """Set the volume value."""
        target_volume = int(value)
        current_volume = int(self._attr_native_value or 0)
        interval_ms = self._client.volume_step_interval

        # Cancel any existing transition
        if self._transition_task:
            self._transition_task.cancel()
            self._transition_task = None

        if interval_ms <= 0 or current_volume == target_volume:
            self._transition_in_progress = False
            success = await self._client.async_set_volume(target_volume)
            if success:
                self._attr_native_value = target_volume
                self.async_write_ha_state()
            else:
                _LOGGER.error("Failed to set volume to %d", target_volume)
            return

        # Start transition - set target value immediately for smooth UI
        self._attr_native_value = target_volume
        self.async_write_ha_state()
        self._transition_in_progress = True

        # Increment generation before starting task so the task can capture it
        self._transition_generation += 1
        generation = self._transition_generation

        self._transition_task = self.hass.async_create_task(
            self._async_volume_transition(
                current_volume, target_volume, interval_ms, generation
            )
        )

    async def async_will_remove_from_hass(self) -> None:
        """Cancel any ongoing transition when entity is removed."""
        if self._transition_task:
            self._transition_task.cancel()
            self._transition_task = None
        self._transition_in_progress = False
        await super().async_will_remove_from_hass()

    async def _async_volume_transition(
        self, start_volume: int, end_volume: int, interval_ms: int, generation: int
    ) -> None:
        """Transition volume smoothly over time."""
        steps = abs(end_volume - start_volume)
        if steps == 0:
            self._transition_in_progress = False
            return

        # Use interval_ms as the delay between steps
        delay = interval_ms / 1000.0
        step_increment = 1 if end_volume > start_volume else -1

        try:
            for i in range(1, steps + 1):
                # Wait BEFORE sending the next step as requested:
                # "volume is at 25 and I want it to go to 50, wait 223ms, send 26,
                # wait 223ms, send 27 etc..."
                await asyncio.sleep(delay)

                next_volume = start_volume + (i * step_increment)
                success = await self._client.async_set_volume(next_volume)
                if not success:
                    _LOGGER.warning("Failed to set volume step to %d", next_volume)
                    break
        except asyncio.CancelledError:
            _LOGGER.debug("Volume transition cancelled")
        finally:
            # Only reset flag if this is still the active transition generation
            # (avoids race condition when a new transition cancels this one)
            if self._transition_generation == generation:
                self._transition_in_progress = False
                self._transition_task = None

    async def async_update(self) -> None:
        """Update the volume value."""
        try:
            volume = await self._client.async_get_volume()
            self._attr_native_value = volume
        except (OSError, TimeoutError):
            _LOGGER.exception("Failed to update volume")


class BraviaQuadRearLevelNumber(BraviaQuadNotificationMixin, NumberEntity):
    """Representation of a Bravia Quad rear level control."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_has_entity_name = True
    _attr_mode = NumberMode.SLIDER
    _attr_native_max_value = MAX_REAR_LEVEL
    _attr_native_min_value = MIN_REAR_LEVEL
    _attr_native_step = 1
    _attr_should_poll = False
    _attr_translation_key = "rear_level"
    _notification_feature = FEATURE_REAR_LEVEL

    def __init__(self, client: BraviaQuadClient, entry: ConfigEntry) -> None:
        """Initialize the rear level number entity."""
        self._client = client
        self._attr_unique_id = f"{DOMAIN}_{entry.unique_id}_rear_level"
        self._attr_native_value = client.rear_level
        self._attr_device_info = get_device_info(entry)

    async def _on_notification(self, value: Any) -> None:
        """Handle rear level notification."""
        try:
            rear_level = int(value)
            if MIN_REAR_LEVEL <= rear_level <= MAX_REAR_LEVEL:
                self._attr_native_value = rear_level
                self.async_write_ha_state()
        except (ValueError, TypeError):
            _LOGGER.warning("Invalid rear level notification value: %s", value)

    async def async_set_native_value(self, value: float) -> None:
        """Set the rear level value."""
        rear_level = int(value)
        success = await self._client.async_set_rear_level(rear_level)
        if success:
            self._attr_native_value = rear_level
            self.async_write_ha_state()
        else:
            _LOGGER.error("Failed to set rear level to %d", rear_level)

    async def async_update(self) -> None:
        """Update the rear level value."""
        try:
            rear_level = await self._client.async_get_rear_level()
            self._attr_native_value = rear_level
        except (OSError, TimeoutError):
            _LOGGER.exception("Failed to update rear level")


class BraviaQuadBassLevelNumber(BraviaQuadNotificationMixin, NumberEntity):
    """Representation of a Bravia Quad bass level control."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_has_entity_name = True
    _attr_mode = NumberMode.SLIDER
    _attr_native_max_value = MAX_BASS_LEVEL
    _attr_native_min_value = MIN_BASS_LEVEL
    _attr_native_step = 1
    _attr_should_poll = False
    _attr_translation_key = "bass_level"
    _notification_feature = FEATURE_BASS_LEVEL

    def __init__(self, client: BraviaQuadClient, entry: ConfigEntry) -> None:
        """Initialize the bass level number entity."""
        self._client = client
        self._attr_unique_id = f"{DOMAIN}_{entry.unique_id}_bass_level_slider"
        self._attr_native_value = client.bass_level
        self._attr_device_info = get_device_info(entry)

    async def _on_notification(self, value: Any) -> None:
        """Handle bass level notification."""
        try:
            bass_level = int(value)
            if MIN_BASS_LEVEL <= bass_level <= MAX_BASS_LEVEL:
                self._attr_native_value = bass_level
                self.async_write_ha_state()
        except (ValueError, TypeError):
            _LOGGER.warning("Invalid bass level notification value: %s", value)

    async def async_set_native_value(self, value: float) -> None:
        """Set the bass level value."""
        bass_level = int(value)
        success = await self._client.async_set_bass_level(bass_level)
        if success:
            self._attr_native_value = bass_level
            self.async_write_ha_state()
        else:
            _LOGGER.error("Failed to set bass level to %d", bass_level)

    async def async_update(self) -> None:
        """Update the bass level value."""
        try:
            bass_level = await self._client.async_get_bass_level()
            self._attr_native_value = bass_level
        except (OSError, TimeoutError):
            _LOGGER.exception("Failed to update bass level")


class BraviaQuadVolumeStepIntervalNumber(RestoreNumber):
    """Representation of a Bravia Quad volume step interval control."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_has_entity_name = True
    _attr_mode = NumberMode.BOX
    _attr_native_max_value = MAX_VOLUME_STEP_INTERVAL
    _attr_native_min_value = 0
    _attr_native_step = 1
    _attr_native_unit_of_measurement = "ms"
    _attr_translation_key = "volume_step_interval"

    def __init__(self, client: BraviaQuadClient, entry: ConfigEntry) -> None:
        """Initialize the volume step interval number entity."""
        self._client = client
        self._attr_unique_id = f"{DOMAIN}_{entry.unique_id}_volume_step_interval"
        self._attr_native_value = client.volume_step_interval
        self._attr_device_info = get_device_info(entry)

    async def async_added_to_hass(self) -> None:
        """Restore previous state on restart."""
        await super().async_added_to_hass()
        if (
            last_state := await self.async_get_last_number_data()
        ) is not None and last_state.native_value is not None:
            self._attr_native_value = last_state.native_value
            self._client.volume_step_interval = int(last_state.native_value)

    async def async_set_native_value(self, value: float) -> None:
        """Set the volume step interval."""
        self._client.volume_step_interval = int(value)
        self._attr_native_value = value
        self.async_write_ha_state()
