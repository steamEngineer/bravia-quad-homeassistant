"""Number platform for Bravia Quad controls."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import TYPE_CHECKING, Any

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.const import EntityCategory
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er

from .const import (
    CONF_HAS_SUBWOOFER,
    DOMAIN,
    FEATURE_AV_SYNC,
    FEATURE_BASS_LEVEL,
    FEATURE_REAR_LEVEL,
    FEATURE_TV_AV_SYNC,
    FEATURE_VOLUME,
    MAX_AV_SYNC,
    MAX_BASS_LEVEL,
    MAX_REAR_LEVEL,
    MIN_AV_SYNC,
    MIN_BASS_LEVEL,
    MIN_REAR_LEVEL,
    TRANSPORT_GRPC,
    TRANSPORT_TCP,
)
from .entity import (
    BraviaQuadNotificationMixin,
    BraviaQuadVolumeStepIntervalNumber,
    VolumeTransitionMixin,
    entity_unique_id,
    get_device_info,
)
from .grpc_mapped_entities import mapped_number_entities
from .helpers import (
    raise_set_rejected,
    remove_entities_by_unique_id_suffixes,
    verify_feature_value,
)

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from . import BraviaQuadConfigEntry
    from .bravia_quad_client import BraviaQuadClient

_LOGGER = logging.getLogger(__name__)

SCAN_INTERVAL = timedelta(seconds=60)
PARALLEL_UPDATES = 1

# Constants for validation ranges
MAX_VOLUME = 100


async def async_setup_entry(
    _hass: HomeAssistant,
    entry: BraviaQuadConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Bravia Quad number entities from a config entry."""
    data = entry.runtime_data

    if data.transport == TRANSPORT_GRPC:
        if data.grpc_client is None:
            return
        # Former switch platform for the same unique_id suffix.
        remove_entities_by_unique_id_suffixes(
            er.async_get(_hass),
            entry,
            "switch",
            ("dts_dialog_control",),
        )
        async_add_entities(
            mapped_number_entities(data.grpc_client, entry),
            update_before_add=True,
        )
        return

    if data.transport != TRANSPORT_TCP or data.tcp_client is None:
        return

    client = data.tcp_client

    # Create number entities
    entities: list[NumberEntity] = [
        BraviaQuadVolumeNumber(client, entry),
        BraviaQuadRearLevelNumber(client, entry),
        BraviaQuadVolumeStepIntervalNumber(entry, client),
    ]

    # Only add bass level slider if subwoofer is detected
    if entry.data.get(CONF_HAS_SUBWOOFER, False):
        entities.append(BraviaQuadBassLevelNumber(client, entry))

    entities.append(BraviaQuadAvSyncNumber(client, entry))
    entities.append(BraviaQuadTvAvSyncNumber(client, entry))

    async_add_entities(entities, update_before_add=True)


class BraviaQuadVolumeNumber(
    VolumeTransitionMixin, BraviaQuadNotificationMixin, NumberEntity
):
    """Representation of a Bravia Quad volume control."""

    _attr_entity_category = EntityCategory.CONFIG
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
        self._attr_unique_id = entity_unique_id(entry, "volume")
        self._attr_native_value = client.volume
        self._attr_device_info = get_device_info(entry)
        self._init_volume_transition()

    async def _on_notification(self, value: Any) -> None:
        """Handle volume notification."""
        if self.should_suppress_volume_notification():
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
        previous_value = self._attr_native_value
        current_volume = int(previous_value or 0)

        # Set optimistic UI state immediately for smooth slider feedback
        self._attr_native_value = target_volume
        self.async_write_ha_state()

        success = await self._async_set_volume_with_transition(
            current_volume, target_volume
        )

        if not success:
            # Restore previous state since the device didn't change
            self._attr_native_value = previous_value
            self.async_write_ha_state()
            _LOGGER.error("Failed to set volume to %d", target_volume)

    async def async_added_to_hass(self) -> None:
        """Register callbacks and cancel volume transition on remove."""
        await super().async_added_to_hass()
        self.async_on_remove(self._cancel_volume_transition)

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
        self._attr_unique_id = entity_unique_id(entry, "rear_level")
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
        self._attr_unique_id = entity_unique_id(entry, "bass_level_slider")
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


class BraviaQuadAvSyncNumber(BraviaQuadNotificationMixin, NumberEntity):
    """Representation of a Bravia Quad AV sync number."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_has_entity_name = True
    _attr_should_poll = True
    _attr_translation_key = "av_sync"
    _attr_mode = NumberMode.SLIDER
    _attr_native_min_value = MIN_AV_SYNC
    _attr_native_max_value = MAX_AV_SYNC
    _attr_native_step = 25
    _attr_native_unit_of_measurement = "ms"
    _notification_feature = FEATURE_AV_SYNC

    def __init__(self, client: BraviaQuadClient, entry: ConfigEntry) -> None:
        """Initialize the AV sync number."""
        self._client = client
        self._attr_unique_id = entity_unique_id(entry, "av_sync")
        self._attr_native_value = None
        self._attr_device_info = get_device_info(entry)

    async def _on_notification(self, value: str) -> None:
        """Handle AV sync notification."""
        try:
            av_sync = int(value)
        except (ValueError, TypeError):
            _LOGGER.warning("Invalid AV sync notification value: %s", value)
            return
        if MIN_AV_SYNC <= av_sync <= MAX_AV_SYNC:
            self._attr_native_value = av_sync
            self.async_write_ha_state()

    async def async_set_native_value(self, value: float) -> None:
        """Set AV sync delay."""
        int_value = int(value)
        if not await self._client.async_set_av_sync(int_value):
            raise_set_rejected("AV sync", str(int_value))
        try:
            actual = await self._client.async_get_av_sync()
        except (OSError, TimeoutError) as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="verify_read_failed",
                translation_placeholders={
                    "feature": "AV sync",
                    "requested": str(int_value),
                },
            ) from err
        self._attr_native_value = verify_feature_value(
            requested=int_value,
            actual=actual,
            feature_label="AV sync",
            mismatch_hint="The device may only accept 0 ms on the current input path.",
        )
        self.async_write_ha_state()

    async def async_update(self) -> None:
        """Update AV sync state."""
        try:
            self._attr_native_value = await self._client.async_get_av_sync()
        except (OSError, TimeoutError):
            _LOGGER.exception("Failed to update AV sync state")


class BraviaQuadTvAvSyncNumber(BraviaQuadNotificationMixin, NumberEntity):
    """Representation of a Bravia Quad TV AV sync number."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_has_entity_name = True
    _attr_should_poll = True
    _attr_translation_key = "tv_av_sync"
    _attr_mode = NumberMode.SLIDER
    _attr_native_min_value = MIN_AV_SYNC
    _attr_native_max_value = MAX_AV_SYNC
    _attr_native_step = 25
    _attr_native_unit_of_measurement = "ms"
    _notification_feature = FEATURE_TV_AV_SYNC

    def __init__(self, client: BraviaQuadClient, entry: ConfigEntry) -> None:
        """Initialize the TV AV sync number."""
        self._client = client
        self._attr_unique_id = entity_unique_id(entry, "tv_av_sync")
        self._attr_native_value = None
        self._attr_device_info = get_device_info(entry)

    async def _on_notification(self, value: str) -> None:
        """Handle TV AV sync notification."""
        try:
            av_sync = int(value)
        except (ValueError, TypeError):
            _LOGGER.warning("Invalid TV AV sync notification value: %s", value)
            return
        if MIN_AV_SYNC <= av_sync <= MAX_AV_SYNC:
            self._attr_native_value = av_sync
            self.async_write_ha_state()

    async def async_set_native_value(self, value: float) -> None:
        """Set TV AV sync delay."""
        int_value = int(value)
        if not await self._client.async_set_tv_av_sync(int_value):
            raise_set_rejected("TV AV sync", str(int_value))
        try:
            actual = await self._client.async_get_tv_av_sync()
        except (OSError, TimeoutError) as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="verify_read_failed",
                translation_placeholders={
                    "feature": "TV AV sync",
                    "requested": str(int_value),
                },
            ) from err
        self._attr_native_value = verify_feature_value(
            requested=int_value,
            actual=actual,
            feature_label="TV AV sync",
            mismatch_hint="The device may only accept 0 ms on the current input path.",
        )
        self.async_write_ha_state()

    async def async_update(self) -> None:
        """Update TV AV sync state."""
        try:
            self._attr_native_value = await self._client.async_get_tv_av_sync()
        except (OSError, TimeoutError):
            _LOGGER.exception("Failed to update TV AV sync state")
