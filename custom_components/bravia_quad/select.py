"""Select platform for Bravia Quad controls."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import TYPE_CHECKING

from homeassistant.components.select import SelectEntity
from homeassistant.const import EntityCategory
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er

from .const import (
    AUDIO_RETURN_CHANNEL_OPTIONS,
    BASS_LEVEL_OPTIONS,
    BASS_LEVEL_VALUES_TO_OPTIONS,
    BT_CONNECTION_QUALITY_OPTIONS,
    CONF_HAS_SUBWOOFER,
    DOMAIN,
    DRC_OPTIONS,
    DUAL_MONO_OPTIONS,
    FEATURE_AUDIO_RETURN_CHANNEL,
    FEATURE_BASS_LEVEL,
    FEATURE_BT_CONNECTION_QUALITY,
    FEATURE_DRC,
    FEATURE_DUAL_MONO,
    FEATURE_HDMI_PASSTHROUGH,
    FEATURE_HDMI_STANDBY_LINK,
    FEATURE_IMAX_MODE,
    HDMI_PASSTHROUGH_OPTIONS,
    HDMI_STANDBY_LINK_OPTIONS,
    IMAX_MODE_OPTIONS,
    TRANSPORT_GRPC,
)
from .entity import (
    BraviaQuadNotificationMixin,
    entity_unique_id,
    get_device_info,
)
from .grpc_mapped_entities import mapped_select_entities
from .helpers import (
    GATED_CAPABILITY_SELECT_SUFFIXES,
    prune_gated_unique_id_suffixes,
    raise_set_rejected,
    unique_id_suffixes_for_entities,
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


async def async_setup_entry(
    hass: HomeAssistant,
    entry: BraviaQuadConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Bravia Quad select entities from a config entry."""
    data = entry.runtime_data

    if data.transport == TRANSPORT_GRPC:
        if data.grpc_client is None:
            return
        entities = mapped_select_entities(data.grpc_client, entry)
        prune_gated_unique_id_suffixes(
            hass,
            entry,
            "select",
            gated_suffixes=GATED_CAPABILITY_SELECT_SUFFIXES,
            created_suffixes=unique_id_suffixes_for_entities(entry, entities),
        )
        async_add_entities(entities, update_before_add=True)
        return

    if data.tcp_client is None:
        return
    client = data.tcp_client

    # Remove legacy switch entity after IMAX mode became a select
    registry = er.async_get(hass)
    imax_unique_id = entity_unique_id(entry, "imax_mode")
    for entity_entry in er.async_entries_for_config_entry(registry, entry.entry_id):
        if (
            entity_entry.entity_id.startswith("switch.")
            and entity_entry.unique_id == imax_unique_id
        ):
            registry.async_remove(entity_entry.entity_id)
            break

    # Create select entities
    entities: list[SelectEntity] = []

    # Add bass level select only if no subwoofer detected
    if not entry.data.get(CONF_HAS_SUBWOOFER, False):
        entities.append(BraviaQuadBassLevelSelect(hass, client, entry))

    # Add Dynamic Range Compressor select (polling-based)
    entities.append(BraviaQuadDynamicRangeCompressorSelect(client, entry))

    # Add new polling-based selects
    entities.append(BraviaQuadHdmiPassthroughSelect(client, entry))
    entities.append(BraviaQuadImaxModeSelect(client, entry))
    entities.append(BraviaQuadDualMonoSelect(client, entry))
    entities.append(BraviaQuadBtConnectionQualitySelect(client, entry))
    entities.append(BraviaQuadHdmiStandbyLinkSelect(client, entry))
    entities.append(BraviaQuadAudioReturnChannelSelect(client, entry))

    async_add_entities(entities, update_before_add=True)


class BraviaQuadBassLevelSelect(BraviaQuadNotificationMixin, SelectEntity):
    """Representation of a Bravia Quad bass level selector (for non-subwoofer mode)."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_translation_key = "bass_level"
    _notification_feature = FEATURE_BASS_LEVEL

    def __init__(
        self, hass: HomeAssistant, client: BraviaQuadClient, entry: ConfigEntry
    ) -> None:
        """Initialize the bass level select entity."""
        self._hass = hass
        self._client = client
        self._entry = entry
        self._reloading = False
        self._attr_unique_id = entity_unique_id(entry, "bass_level_select")
        self._attr_options = list(BASS_LEVEL_OPTIONS.keys())
        current_bass_value = client.bass_level
        self._attr_current_option = BASS_LEVEL_VALUES_TO_OPTIONS.get(
            current_bass_value, "mid"
        )
        self._attr_device_info = get_device_info(entry)

    async def _on_notification(self, value: str) -> None:
        """Handle bass level notification."""
        try:
            bass_level = int(value)
            # Convert value (0-2) to option key (min/mid/max)
            option = BASS_LEVEL_VALUES_TO_OPTIONS.get(bass_level)
            if option:
                self._attr_current_option = option
                self.async_write_ha_state()
            # Value outside 0-2 range - subwoofer must be connected
            # Trigger auto-reload to switch to slider entity
            elif not self._reloading:
                self._reloading = True
                _LOGGER.info(
                    "Bass level %d is outside 0-2 range - "
                    "subwoofer detected, reloading integration",
                    bass_level,
                )
                await self._trigger_subwoofer_reload()
        except (ValueError, TypeError):
            _LOGGER.warning("Invalid bass level notification value: %s", value)

    async def _trigger_subwoofer_reload(self) -> None:
        """Update subwoofer detection and reload integration."""
        # Remove this select entity from registry
        entity_registry = er.async_get(self._hass)
        if self._attr_unique_id and (
            old_entity := entity_registry.async_get_entity_id(
                "select",
                DOMAIN,
                self._attr_unique_id,
            )
        ):
            _LOGGER.debug("Removing bass level select entity: %s", old_entity)
            entity_registry.async_remove(old_entity)

        # Update entry data with subwoofer detected
        new_data = {**self._entry.data, CONF_HAS_SUBWOOFER: True}
        self._hass.config_entries.async_update_entry(self._entry, data=new_data)

        # Reload the integration to recreate entities
        await self._hass.config_entries.async_reload(self._entry.entry_id)

    async def async_select_option(self, option: str) -> None:
        """Change the selected option."""
        bass_level = BASS_LEVEL_OPTIONS.get(option)
        if bass_level is None:
            _LOGGER.error("Invalid bass level option: %s", option)
            return

        success = await self._client.async_set_bass_level(bass_level)
        if success:
            self._attr_current_option = option
            self.async_write_ha_state()
        else:
            _LOGGER.error("Failed to set bass level to %s", option)

    async def async_update(self) -> None:
        """Update the current bass level."""
        try:
            bass_level_value = await self._client.async_get_bass_level()
            # Convert value to option key
            option = BASS_LEVEL_VALUES_TO_OPTIONS.get(bass_level_value)
            if option:
                self._attr_current_option = option
            else:
                _LOGGER.warning("Unknown bass level value: %s", bass_level_value)
        except (OSError, TimeoutError):
            _LOGGER.exception("Failed to update bass level")


class BraviaQuadDynamicRangeCompressorSelect(BraviaQuadNotificationMixin, SelectEntity):
    """Representation of a Bravia Quad Dynamic Range Compressor selector."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_translation_key = "drc"
    _notification_feature = FEATURE_DRC

    def __init__(self, client: BraviaQuadClient, entry: ConfigEntry) -> None:
        """Initialize the Dynamic Range Compressor select entity."""
        self._client = client
        self._attr_unique_id = entity_unique_id(entry, "drc")
        self._attr_options = DRC_OPTIONS
        # Initialize current option from client's current DRC state
        current_drc_value = client.drc
        self._attr_current_option = (
            current_drc_value if current_drc_value in DRC_OPTIONS else "auto"
        )
        self._attr_device_info = get_device_info(entry)

    async def _on_notification(self, value: str) -> None:
        """Handle Dynamic Range Compressor notification."""
        if value in DRC_OPTIONS:
            self._attr_current_option = value
            self.async_write_ha_state()
        else:
            _LOGGER.warning("Unknown DRC value received: %s", value)

    async def async_select_option(self, option: str) -> None:
        """Change the selected option."""
        if option not in DRC_OPTIONS:
            _LOGGER.error("Invalid DRC option: %s", option)
            return

        success = await self._client.async_set_drc(option)
        if success:
            self._attr_current_option = option
            self.async_write_ha_state()
        else:
            _LOGGER.error("Failed to set DRC to %s", option)

    async def async_update(self) -> None:
        """Update the current DRC state."""
        try:
            drc_value = await self._client.async_get_drc()
            if drc_value in DRC_OPTIONS:
                self._attr_current_option = drc_value
            else:
                _LOGGER.warning("Unknown DRC value: %s", drc_value)
        except (OSError, TimeoutError):
            _LOGGER.exception("Failed to update DRC state")


class BraviaQuadHdmiPassthroughSelect(BraviaQuadNotificationMixin, SelectEntity):
    """Representation of a Bravia Quad HDMI passthrough selector."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_has_entity_name = True
    _attr_should_poll = True
    _attr_translation_key = "hdmi_passthrough"
    _notification_feature = FEATURE_HDMI_PASSTHROUGH

    def __init__(self, client: BraviaQuadClient, entry: ConfigEntry) -> None:
        """Initialize the HDMI passthrough select."""
        self._client = client
        self._attr_unique_id = entity_unique_id(entry, "hdmi_passthrough")
        self._attr_options = HDMI_PASSTHROUGH_OPTIONS
        current = None
        self._attr_current_option = (
            current if current in HDMI_PASSTHROUGH_OPTIONS else "auto"
        )
        self._attr_device_info = get_device_info(entry)

    async def _on_notification(self, value: str) -> None:
        """Handle notification."""
        if value in HDMI_PASSTHROUGH_OPTIONS:
            self._attr_current_option = value
            self.async_write_ha_state()

    async def async_select_option(self, option: str) -> None:
        """Change the selected option."""
        if option not in HDMI_PASSTHROUGH_OPTIONS:
            _LOGGER.error("Invalid HDMI passthrough option: %s", option)
            return
        success = await self._client.async_set_hdmi_passthrough(option)
        if not success:
            _LOGGER.error("Failed to set HDMI passthrough to %s", option)
            return
        # Re-read to verify device accepted the value
        try:
            actual = await self._client.async_get_hdmi_passthrough()
            if actual in HDMI_PASSTHROUGH_OPTIONS:
                self._attr_current_option = actual
            else:
                self._attr_current_option = option
        except (OSError, TimeoutError):
            self._attr_current_option = option
        self.async_write_ha_state()

    async def async_update(self) -> None:
        """Update the current state."""
        try:
            value = await self._client.async_get_hdmi_passthrough()
            if value in HDMI_PASSTHROUGH_OPTIONS:
                self._attr_current_option = value
        except (OSError, TimeoutError):
            _LOGGER.exception("Failed to update HDMI passthrough state")


class BraviaQuadImaxModeSelect(BraviaQuadNotificationMixin, SelectEntity):
    """Representation of a Bravia Quad IMAX Enhanced mode selector."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_translation_key = "imax_mode"

    _notification_feature = FEATURE_IMAX_MODE

    def __init__(self, client: BraviaQuadClient, entry: ConfigEntry) -> None:
        """Initialize the IMAX mode select."""
        self._client = client
        self._attr_unique_id = entity_unique_id(entry, "imax_mode")
        self._attr_options = list(IMAX_MODE_OPTIONS)
        current = client.imax_mode
        self._attr_current_option = current if current in IMAX_MODE_OPTIONS else "auto"
        self._attr_device_info = get_device_info(entry)

    async def _on_notification(self, value: str) -> None:
        """Handle IMAX mode notification."""
        if value in IMAX_MODE_OPTIONS:
            self._attr_current_option = value
            self.async_write_ha_state()
        else:
            _LOGGER.warning("Unknown IMAX mode value received: %s", value)

    async def async_select_option(self, option: str) -> None:
        """Change the IMAX mode."""
        if option not in IMAX_MODE_OPTIONS:
            _LOGGER.error("Invalid IMAX mode option: %s", option)
            return

        if not await self._client.async_set_imax_mode(option):
            raise_set_rejected("IMAX mode", option)

        try:
            actual = await self._client.async_get_imax_mode()
        except (OSError, TimeoutError) as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="verify_read_failed",
                translation_placeholders={
                    "feature": "IMAX mode",
                    "requested": option,
                },
            ) from err

        self._attr_current_option = verify_feature_value(
            requested=option,
            actual=actual,
            valid_values=set(IMAX_MODE_OPTIONS),
            feature_label="IMAX mode",
            mismatch_hint=(
                "IMAX Enhanced may require a compatible TV and Sony wireless subwoofer."
            ),
        )
        self.async_write_ha_state()

    async def async_update(self) -> None:
        """Update the current IMAX mode."""
        try:
            value = await self._client.async_get_imax_mode()
            if value in IMAX_MODE_OPTIONS:
                self._attr_current_option = value
            else:
                _LOGGER.warning("Unknown IMAX mode value: %s", value)
        except (OSError, TimeoutError):
            _LOGGER.exception("Failed to update IMAX mode state")


class BraviaQuadDualMonoSelect(BraviaQuadNotificationMixin, SelectEntity):
    """
    Representation of a Bravia Quad dual mono selector.

    Option values (main/sub/main_sub) are unconfirmed on real hardware.
    Disabled by default until verified.
    """

    _attr_entity_category = EntityCategory.CONFIG
    _attr_entity_registry_enabled_default = False
    _attr_has_entity_name = True
    _attr_should_poll = True
    _attr_translation_key = "dual_mono"
    _notification_feature = FEATURE_DUAL_MONO

    def __init__(self, client: BraviaQuadClient, entry: ConfigEntry) -> None:
        """Initialize the dual mono select."""
        self._client = client
        self._attr_unique_id = entity_unique_id(entry, "dual_mono")
        self._attr_options = DUAL_MONO_OPTIONS
        current = None
        self._attr_current_option = current if current in DUAL_MONO_OPTIONS else "main"
        self._attr_device_info = get_device_info(entry)

    async def _on_notification(self, value: str) -> None:
        """Handle notification."""
        if value in DUAL_MONO_OPTIONS:
            self._attr_current_option = value
            self.async_write_ha_state()

    async def async_select_option(self, option: str) -> None:
        """Change the selected option."""
        if option not in DUAL_MONO_OPTIONS:
            _LOGGER.error("Invalid dual mono option: %s", option)
            return
        success = await self._client.async_set_dual_mono(option)
        if not success:
            _LOGGER.error("Failed to set dual mono to %s", option)
            return
        # Re-read to verify device accepted the value
        try:
            actual = await self._client.async_get_dual_mono()
            if actual in DUAL_MONO_OPTIONS:
                self._attr_current_option = actual
            else:
                self._attr_current_option = option
        except (OSError, TimeoutError):
            self._attr_current_option = option
        self.async_write_ha_state()

    async def async_update(self) -> None:
        """Update the current state."""
        try:
            value = await self._client.async_get_dual_mono()
            if value in DUAL_MONO_OPTIONS:
                self._attr_current_option = value
        except (OSError, TimeoutError):
            _LOGGER.exception("Failed to update dual mono state")


class BraviaQuadBtConnectionQualitySelect(BraviaQuadNotificationMixin, SelectEntity):
    """Representation of a Bravia Quad Bluetooth connection quality selector."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_has_entity_name = True
    _attr_should_poll = True
    _attr_translation_key = "bt_connection_quality"
    _notification_feature = FEATURE_BT_CONNECTION_QUALITY

    def __init__(self, client: BraviaQuadClient, entry: ConfigEntry) -> None:
        """Initialize the Bluetooth connection quality select."""
        self._client = client
        self._attr_unique_id = entity_unique_id(entry, "bt_connection_quality")
        self._attr_options = BT_CONNECTION_QUALITY_OPTIONS
        current = None
        self._attr_current_option = (
            current if current in BT_CONNECTION_QUALITY_OPTIONS else "prioritysound"
        )
        self._attr_device_info = get_device_info(entry)

    async def _on_notification(self, value: str) -> None:
        """Handle notification."""
        if value in BT_CONNECTION_QUALITY_OPTIONS:
            self._attr_current_option = value
            self.async_write_ha_state()

    async def async_select_option(self, option: str) -> None:
        """Change the selected option."""
        if option not in BT_CONNECTION_QUALITY_OPTIONS:
            _LOGGER.error("Invalid Bluetooth connection quality option: %s", option)
            return
        success = await self._client.async_set_bt_connection_quality(option)
        if not success:
            _LOGGER.error("Failed to set Bluetooth connection quality to %s", option)
            return
        # Re-read to verify device accepted the value
        try:
            actual = await self._client.async_get_bt_connection_quality()
            if actual in BT_CONNECTION_QUALITY_OPTIONS:
                self._attr_current_option = actual
            else:
                self._attr_current_option = option
        except (OSError, TimeoutError):
            self._attr_current_option = option
        self.async_write_ha_state()

    async def async_update(self) -> None:
        """Update the current state."""
        try:
            value = await self._client.async_get_bt_connection_quality()
            if value in BT_CONNECTION_QUALITY_OPTIONS:
                self._attr_current_option = value
        except (OSError, TimeoutError):
            _LOGGER.exception("Failed to update Bluetooth connection quality state")


class BraviaQuadHdmiStandbyLinkSelect(BraviaQuadNotificationMixin, SelectEntity):
    """Representation of a Bravia Quad HDMI standby link selector."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_has_entity_name = True
    _attr_should_poll = True
    _attr_translation_key = "hdmi_standby_link"
    _notification_feature = FEATURE_HDMI_STANDBY_LINK

    def __init__(self, client: BraviaQuadClient, entry: ConfigEntry) -> None:
        """Initialize the HDMI standby link select."""
        self._client = client
        self._attr_unique_id = entity_unique_id(entry, "hdmi_standby_link")
        self._attr_options = HDMI_STANDBY_LINK_OPTIONS
        current = None
        self._attr_current_option = (
            current if current in HDMI_STANDBY_LINK_OPTIONS else "auto"
        )
        self._attr_device_info = get_device_info(entry)

    async def _on_notification(self, value: str) -> None:
        """Handle notification."""
        if value in HDMI_STANDBY_LINK_OPTIONS:
            self._attr_current_option = value
            self.async_write_ha_state()

    async def async_select_option(self, option: str) -> None:
        """Change the selected option."""
        if option not in HDMI_STANDBY_LINK_OPTIONS:
            _LOGGER.error("Invalid HDMI standby link option: %s", option)
            return
        success = await self._client.async_set_hdmi_standby_link(option)
        if not success:
            _LOGGER.error("Failed to set HDMI standby link to %s", option)
            return
        # Re-read to verify device accepted the value
        try:
            actual = await self._client.async_get_hdmi_standby_link()
            if actual in HDMI_STANDBY_LINK_OPTIONS:
                self._attr_current_option = actual
            else:
                self._attr_current_option = option
        except (OSError, TimeoutError):
            self._attr_current_option = option
        self.async_write_ha_state()

    async def async_update(self) -> None:
        """Update the current state."""
        try:
            value = await self._client.async_get_hdmi_standby_link()
            if value in HDMI_STANDBY_LINK_OPTIONS:
                self._attr_current_option = value
        except (OSError, TimeoutError):
            _LOGGER.exception("Failed to update HDMI standby link state")


class BraviaQuadAudioReturnChannelSelect(BraviaQuadNotificationMixin, SelectEntity):
    """Representation of a Bravia Quad audio return channel selector."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_has_entity_name = True
    _attr_should_poll = True
    _attr_translation_key = "audio_return_channel"
    _notification_feature = FEATURE_AUDIO_RETURN_CHANNEL

    def __init__(self, client: BraviaQuadClient, entry: ConfigEntry) -> None:
        """Initialize the audio return channel select."""
        self._client = client
        self._attr_unique_id = entity_unique_id(entry, "audio_return_channel")
        self._attr_options = AUDIO_RETURN_CHANNEL_OPTIONS
        current = None
        self._attr_current_option = (
            current if current in AUDIO_RETURN_CHANNEL_OPTIONS else "arc"
        )
        self._attr_device_info = get_device_info(entry)

    async def _on_notification(self, value: str) -> None:
        """Handle notification."""
        if value in AUDIO_RETURN_CHANNEL_OPTIONS:
            self._attr_current_option = value
            self.async_write_ha_state()

    async def async_select_option(self, option: str) -> None:
        """Change the selected option."""
        if option not in AUDIO_RETURN_CHANNEL_OPTIONS:
            _LOGGER.error("Invalid audio return channel option: %s", option)
            return
        if not await self._client.async_set_audio_return_channel(option):
            raise_set_rejected("audio return channel", option)
        try:
            actual = await self._client.async_get_audio_return_channel()
        except (OSError, TimeoutError) as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="verify_read_failed",
                translation_placeholders={
                    "feature": "audio return channel",
                    "requested": option,
                },
            ) from err
        self._attr_current_option = verify_feature_value(
            requested=option,
            actual=actual,
            valid_values=set(AUDIO_RETURN_CHANNEL_OPTIONS),
            feature_label="audio return channel",
            mismatch_hint="eARC may report as ARC on some devices.",
        )
        self.async_write_ha_state()

    async def async_update(self) -> None:
        """Update the current state."""
        try:
            value = await self._client.async_get_audio_return_channel()
            if value in AUDIO_RETURN_CHANNEL_OPTIONS:
                self._attr_current_option = value
        except (OSError, TimeoutError):
            _LOGGER.exception("Failed to update audio return channel state")
