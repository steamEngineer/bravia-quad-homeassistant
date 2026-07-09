"""Switch platform for Bravia Quad controls."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import TYPE_CHECKING, Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.const import EntityCategory
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er

from .const import (
    AAV_OFF,
    AAV_ON,
    AUTO_STANDBY_OFF,
    AUTO_STANDBY_ON,
    AUTO_UPDATE_OFF,
    AUTO_UPDATE_ON,
    DOMAIN,
    EXTERNAL_CONTROL_OFF,
    EXTERNAL_CONTROL_ON,
    FEATURE_AAV,
    FEATURE_AUTO_STANDBY,
    FEATURE_AUTO_UPDATE,
    FEATURE_EXTERNAL_CONTROL,
    FEATURE_HDMI_CEC,
    FEATURE_NET_BT_STANDBY,
    FEATURE_NIGHT_MODE,
    FEATURE_POWER,
    FEATURE_SOUND_FIELD,
    FEATURE_VOICE_ENHANCER,
    FEATURE_VOICE_ZOOM,
    HDMI_CEC_OFF,
    HDMI_CEC_ON,
    NET_BT_STANDBY_OFF,
    NET_BT_STANDBY_ON,
    NIGHT_MODE_OFF,
    NIGHT_MODE_ON,
    POWER_OFF,
    POWER_ON,
    SOUND_FIELD_OFF,
    SOUND_FIELD_ON,
    TRANSPORT_GRPC,
    VOICE_ENHANCER_OFF,
    VOICE_ENHANCER_ON,
    VOICE_ZOOM_OFF,
    VOICE_ZOOM_ON,
)
from .entity import (
    BraviaQuadNotificationMixin,
    entity_unique_id,
    get_device_info,
)
from .grpc_mapped_entities import mapped_switch_entities
from .helpers import verify_feature_value

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
    """Set up Bravia Quad switches from a config entry."""
    data = entry.runtime_data

    if data.transport == TRANSPORT_GRPC:
        if data.grpc_client is None:
            return
        # Legacy select → gRPC switch; TCP transport keeps tri-state select.
        registry = er.async_get(hass)
        arc_unique_id = entity_unique_id(entry, "audio_return_channel")
        for entity_entry in er.async_entries_for_config_entry(registry, entry.entry_id):
            if (
                entity_entry.entity_id.startswith("select.")
                and entity_entry.unique_id == arc_unique_id
            ):
                registry.async_remove(entity_entry.entity_id)
                break
        async_add_entities(
            mapped_switch_entities(data.grpc_client, entry),
            update_before_add=True,
        )
        return

    if data.tcp_client is None:
        return
    client = data.tcp_client

    entities = [
        BraviaQuadPowerSwitch(client, entry),
        BraviaQuadHdmiCecSwitch(client, entry),
        BraviaQuadAutoStandbySwitch(client, entry),
        BraviaQuadVoiceEnhancerSwitch(client, entry),
        BraviaQuadSoundFieldSwitch(client, entry),
        BraviaQuadNightModeSwitch(client, entry),
        BraviaQuadAdvancedAutoVolumeSwitch(client, entry),
        BraviaQuadAutoUpdateSwitch(client, entry),
        BraviaQuadNetBtStandbySwitch(client, entry),
        BraviaQuadVoiceZoomSwitch(client, entry),
        BraviaQuadExternalControlSwitch(client, entry),
    ]

    async_add_entities(entities, update_before_add=True)


class BraviaQuadPowerSwitch(BraviaQuadNotificationMixin, SwitchEntity):
    """Representation of a Bravia Quad power switch."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_entity_registry_enabled_default = False
    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_translation_key = "power"
    _notification_feature = FEATURE_POWER

    def __init__(self, client: BraviaQuadClient, entry: ConfigEntry) -> None:
        """Initialize the switch."""
        self._client = client
        self._attr_unique_id = entity_unique_id(entry, "power")
        self._attr_is_on = client.power_state == POWER_ON
        self._attr_device_info = get_device_info(entry)

    async def _on_notification(self, value: str) -> None:
        """Handle power state notification."""
        self._attr_is_on = value == POWER_ON
        self.async_write_ha_state()

    async def async_turn_on(self, **_kwargs: Any) -> None:
        """Turn the device on."""
        success = await self._client.async_set_power(POWER_ON)
        if success:
            self._attr_is_on = True
            self.async_write_ha_state()
        else:
            _LOGGER.error("Failed to turn on Bravia Quad")

    async def async_turn_off(self, **_kwargs: Any) -> None:
        """Turn the device off."""
        success = await self._client.async_set_power(POWER_OFF)
        if success:
            self._attr_is_on = False
            self.async_write_ha_state()
        else:
            _LOGGER.error("Failed to turn off Bravia Quad")

    async def async_update(self) -> None:
        """Update the switch state."""
        try:
            power_state = await self._client.async_get_power()
            self._attr_is_on = power_state == POWER_ON
        except (OSError, TimeoutError):
            _LOGGER.exception("Failed to update power state")


class BraviaQuadHdmiCecSwitch(BraviaQuadNotificationMixin, SwitchEntity):
    """Representation of a Bravia Quad HDMI CEC switch."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_translation_key = "hdmi_cec"
    _notification_feature = FEATURE_HDMI_CEC

    def __init__(self, client: BraviaQuadClient, entry: ConfigEntry) -> None:
        """Initialize the HDMI CEC switch."""
        self._client = client
        self._attr_unique_id = entity_unique_id(entry, "hdmi_cec")
        self._attr_is_on = client.hdmi_cec == HDMI_CEC_ON
        self._attr_device_info = get_device_info(entry)

    async def _on_notification(self, value: str) -> None:
        """Handle HDMI CEC notification."""
        self._attr_is_on = value == HDMI_CEC_ON
        self.async_write_ha_state()

    async def async_turn_on(self, **_kwargs: Any) -> None:
        """Enable HDMI CEC."""
        success = await self._client.async_set_hdmi_cec(HDMI_CEC_ON)
        if success:
            self._attr_is_on = True
            self.async_write_ha_state()
        else:
            _LOGGER.error("Failed to enable HDMI CEC")

    async def async_turn_off(self, **_kwargs: Any) -> None:
        """Disable HDMI CEC."""
        success = await self._client.async_set_hdmi_cec(HDMI_CEC_OFF)
        if success:
            self._attr_is_on = False
            self.async_write_ha_state()
        else:
            _LOGGER.error("Failed to disable HDMI CEC")

    async def async_update(self) -> None:
        """Update HDMI CEC state."""
        try:
            hdmi_cec_state = await self._client.async_get_hdmi_cec()
            self._attr_is_on = hdmi_cec_state == HDMI_CEC_ON
        except (OSError, TimeoutError):
            _LOGGER.exception("Failed to update HDMI CEC state")


class BraviaQuadAutoStandbySwitch(BraviaQuadNotificationMixin, SwitchEntity):
    """Representation of a Bravia Quad auto standby switch."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_translation_key = "auto_standby"
    _notification_feature = FEATURE_AUTO_STANDBY

    def __init__(self, client: BraviaQuadClient, entry: ConfigEntry) -> None:
        """Initialize the auto standby switch."""
        self._client = client
        self._attr_unique_id = entity_unique_id(entry, "auto_standby")
        self._attr_is_on = client.auto_standby == AUTO_STANDBY_ON
        self._attr_device_info = get_device_info(entry)

    async def _on_notification(self, value: str) -> None:
        """Handle auto standby notification."""
        self._attr_is_on = value == POWER_ON
        self.async_write_ha_state()

    async def async_turn_on(self, **_kwargs: Any) -> None:
        """Enable auto standby."""
        success = await self._client.async_set_auto_standby(AUTO_STANDBY_ON)
        if success:
            self._attr_is_on = True
            self.async_write_ha_state()
        else:
            _LOGGER.error("Failed to enable auto standby")

    async def async_turn_off(self, **_kwargs: Any) -> None:
        """Disable auto standby."""
        success = await self._client.async_set_auto_standby(AUTO_STANDBY_OFF)
        if success:
            self._attr_is_on = False
            self.async_write_ha_state()
        else:
            _LOGGER.error("Failed to disable auto standby")

    async def async_update(self) -> None:
        """Update auto standby state."""
        try:
            auto_standby_state = await self._client.async_get_auto_standby()
            self._attr_is_on = auto_standby_state == AUTO_STANDBY_ON
        except (OSError, TimeoutError):
            _LOGGER.exception("Failed to update auto standby state")


class BraviaQuadVoiceEnhancerSwitch(BraviaQuadNotificationMixin, SwitchEntity):
    """Representation of a Bravia Quad voice enhancer switch."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_translation_key = "voice_enhancer"
    _notification_feature = FEATURE_VOICE_ENHANCER

    def __init__(self, client: BraviaQuadClient, entry: ConfigEntry) -> None:
        """Initialize the voice enhancer switch."""
        self._client = client
        self._attr_unique_id = entity_unique_id(entry, "voice_enhancer")
        self._attr_is_on = client.voice_enhancer == VOICE_ENHANCER_ON
        self._attr_device_info = get_device_info(entry)

    async def _on_notification(self, value: str) -> None:
        """Handle voice enhancer state notification."""
        self._attr_is_on = value == VOICE_ENHANCER_ON
        self.async_write_ha_state()

    async def async_turn_on(self, **_kwargs: Any) -> None:
        """Turn voice enhancer on."""
        success = await self._client.async_set_voice_enhancer(VOICE_ENHANCER_ON)
        if success:
            self._attr_is_on = True
            self.async_write_ha_state()
        else:
            _LOGGER.error("Failed to turn on voice enhancer")

    async def async_turn_off(self, **_kwargs: Any) -> None:
        """Turn voice enhancer off."""
        success = await self._client.async_set_voice_enhancer(VOICE_ENHANCER_OFF)
        if success:
            self._attr_is_on = False
            self.async_write_ha_state()
        else:
            _LOGGER.error("Failed to turn off voice enhancer")

    async def async_update(self) -> None:
        """Update the switch state."""
        try:
            voice_enhancer_state = await self._client.async_get_voice_enhancer()
            self._attr_is_on = voice_enhancer_state == VOICE_ENHANCER_ON
        except (OSError, TimeoutError):
            _LOGGER.exception("Failed to update voice enhancer state")


class BraviaQuadSoundFieldSwitch(BraviaQuadNotificationMixin, SwitchEntity):
    """Representation of a Bravia Quad sound field switch."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_translation_key = "sound_field"
    _notification_feature = FEATURE_SOUND_FIELD

    def __init__(self, client: BraviaQuadClient, entry: ConfigEntry) -> None:
        """Initialize the sound field switch."""
        self._client = client
        self._attr_unique_id = entity_unique_id(entry, "sound_field")
        self._attr_is_on = client.sound_field == SOUND_FIELD_ON
        self._attr_device_info = get_device_info(entry)

    async def _on_notification(self, value: str) -> None:
        """Handle sound field state notification."""
        self._attr_is_on = value == SOUND_FIELD_ON
        self.async_write_ha_state()

    async def async_turn_on(self, **_kwargs: Any) -> None:
        """Turn sound field on."""
        success = await self._client.async_set_sound_field(SOUND_FIELD_ON)
        if success:
            self._attr_is_on = True
            self.async_write_ha_state()
        else:
            _LOGGER.error("Failed to turn on sound field")

    async def async_turn_off(self, **_kwargs: Any) -> None:
        """Turn sound field off."""
        success = await self._client.async_set_sound_field(SOUND_FIELD_OFF)
        if success:
            self._attr_is_on = False
            self.async_write_ha_state()
        else:
            _LOGGER.error("Failed to turn off sound field")

    async def async_update(self) -> None:
        """Update the switch state."""
        try:
            sound_field_state = await self._client.async_get_sound_field()
            self._attr_is_on = sound_field_state == SOUND_FIELD_ON
        except (OSError, TimeoutError):
            _LOGGER.exception("Failed to update sound field state")


class BraviaQuadNightModeSwitch(BraviaQuadNotificationMixin, SwitchEntity):
    """Representation of a Bravia Quad night mode switch."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_translation_key = "night_mode"
    _notification_feature = FEATURE_NIGHT_MODE

    def __init__(self, client: BraviaQuadClient, entry: ConfigEntry) -> None:
        """Initialize the night mode switch."""
        self._client = client
        self._attr_unique_id = entity_unique_id(entry, "night_mode")
        self._attr_is_on = client.night_mode == NIGHT_MODE_ON
        self._attr_device_info = get_device_info(entry)

    async def _on_notification(self, value: str) -> None:
        """Handle night mode state notification."""
        self._attr_is_on = value == NIGHT_MODE_ON
        self.async_write_ha_state()

    async def async_turn_on(self, **_kwargs: Any) -> None:
        """Turn night mode on."""
        success = await self._client.async_set_night_mode(NIGHT_MODE_ON)
        if success:
            self._attr_is_on = True
            self.async_write_ha_state()
        else:
            _LOGGER.error("Failed to turn on night mode")

    async def async_turn_off(self, **_kwargs: Any) -> None:
        """Turn night mode off."""
        success = await self._client.async_set_night_mode(NIGHT_MODE_OFF)
        if success:
            self._attr_is_on = False
            self.async_write_ha_state()
        else:
            _LOGGER.error("Failed to turn off night mode")

    async def async_update(self) -> None:
        """Update the switch state."""
        try:
            night_mode_state = await self._client.async_get_night_mode()
            self._attr_is_on = night_mode_state == NIGHT_MODE_ON
        except (OSError, TimeoutError):
            _LOGGER.exception("Failed to update night mode state")


class BraviaQuadAdvancedAutoVolumeSwitch(BraviaQuadNotificationMixin, SwitchEntity):
    """Representation of a Bravia Quad Advanced Auto Volume switch."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_translation_key = "auto_volume"
    _notification_feature = FEATURE_AAV

    def __init__(self, client: BraviaQuadClient, entry: ConfigEntry) -> None:
        """Initialize the Advanced Auto Volume switch."""
        self._client = client
        self._attr_unique_id = entity_unique_id(entry, "advanced_auto_volume")
        # Initialize from client's current state
        self._attr_is_on = client.aav == AAV_ON
        self._attr_device_info = get_device_info(entry)

    async def _on_notification(self, value: str) -> None:
        """Handle Advanced Auto Volume state notification."""
        self._attr_is_on = value == AAV_ON
        self.async_write_ha_state()

    async def async_turn_on(self, **_kwargs: Any) -> None:
        """Turn Advanced Auto Volume on."""
        success = await self._client.async_set_aav(AAV_ON)
        if success:
            self._attr_is_on = True
            self.async_write_ha_state()
        else:
            _LOGGER.error("Failed to turn on Advanced Auto Volume")

    async def async_turn_off(self, **_kwargs: Any) -> None:
        """Turn Advanced Auto Volume off."""
        success = await self._client.async_set_aav(AAV_OFF)
        if success:
            self._attr_is_on = False
            self.async_write_ha_state()
        else:
            _LOGGER.error("Failed to turn off Advanced Auto Volume")

    async def async_update(self) -> None:
        """Update the switch state."""
        try:
            aav_state = await self._client.async_get_aav()
            self._attr_is_on = aav_state == AAV_ON
        except (OSError, TimeoutError):
            _LOGGER.exception("Failed to update Advanced Auto Volume state")


class BraviaQuadAutoUpdateSwitch(BraviaQuadNotificationMixin, SwitchEntity):
    """Representation of a Bravia Quad auto update switch."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_translation_key = "auto_update"
    _notification_feature = FEATURE_AUTO_UPDATE

    def __init__(self, client: BraviaQuadClient, entry: ConfigEntry) -> None:
        """Initialize the auto update switch."""
        self._client = client
        self._attr_unique_id = entity_unique_id(entry, "auto_update")
        self._attr_is_on = client.auto_update == AUTO_UPDATE_ON
        self._attr_device_info = get_device_info(entry)

    async def _on_notification(self, value: str) -> None:
        """Handle auto update notification."""
        self._attr_is_on = value == AUTO_UPDATE_ON
        self.async_write_ha_state()

    async def async_turn_on(self, **_kwargs: Any) -> None:
        """Enable auto update."""
        requested = AUTO_UPDATE_ON
        if not await self._client.async_set_auto_update(requested):
            _LOGGER.error("Failed to enable auto update")
            return
        try:
            actual = await self._client.async_get_auto_update()
        except (OSError, TimeoutError) as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="verify_read_failed",
                translation_placeholders={
                    "feature": "auto update",
                    "requested": requested,
                },
            ) from err
        self._attr_is_on = actual == AUTO_UPDATE_ON
        verify_feature_value(
            requested=requested,
            actual=actual,
            valid_values={AUTO_UPDATE_ON, AUTO_UPDATE_OFF},
            feature_label="auto update",
        )
        self.async_write_ha_state()

    async def async_turn_off(self, **_kwargs: Any) -> None:
        """Disable auto update."""
        requested = AUTO_UPDATE_OFF
        if not await self._client.async_set_auto_update(requested):
            _LOGGER.error("Failed to disable auto update")
            return
        try:
            actual = await self._client.async_get_auto_update()
        except (OSError, TimeoutError) as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="verify_read_failed",
                translation_placeholders={
                    "feature": "auto update",
                    "requested": requested,
                },
            ) from err
        self._attr_is_on = actual == AUTO_UPDATE_ON
        verify_feature_value(
            requested=requested,
            actual=actual,
            valid_values={AUTO_UPDATE_ON, AUTO_UPDATE_OFF},
            feature_label="auto update",
        )
        self.async_write_ha_state()

    async def async_update(self) -> None:
        """Update auto update state."""
        try:
            value = await self._client.async_get_auto_update()
            self._attr_is_on = value == AUTO_UPDATE_ON
        except (OSError, TimeoutError):
            _LOGGER.exception("Failed to update auto update state")


class BraviaQuadNetBtStandbySwitch(BraviaQuadNotificationMixin, SwitchEntity):
    """Representation of a Bravia Quad network/Bluetooth standby switch."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_has_entity_name = True
    _attr_should_poll = True
    _attr_translation_key = "net_bt_standby"
    _notification_feature = FEATURE_NET_BT_STANDBY

    def __init__(self, client: BraviaQuadClient, entry: ConfigEntry) -> None:
        """Initialize the network/Bluetooth standby switch."""
        self._client = client
        self._attr_unique_id = entity_unique_id(entry, "net_bt_standby")
        self._attr_is_on = None
        self._attr_device_info = get_device_info(entry)

    async def _on_notification(self, value: str) -> None:
        """Handle network/Bluetooth standby notification."""
        self._attr_is_on = value == NET_BT_STANDBY_ON
        self.async_write_ha_state()

    async def async_turn_on(self, **_kwargs: Any) -> None:
        """Enable network/Bluetooth standby."""
        requested = NET_BT_STANDBY_ON
        if not await self._client.async_set_net_bt_standby(requested):
            _LOGGER.error("Failed to enable network/Bluetooth standby")
            return
        try:
            actual = await self._client.async_get_net_bt_standby()
        except (OSError, TimeoutError) as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="verify_read_failed",
                translation_placeholders={
                    "feature": "network/Bluetooth standby",
                    "requested": requested,
                },
            ) from err
        self._attr_is_on = actual == NET_BT_STANDBY_ON
        verify_feature_value(
            requested=requested,
            actual=actual,
            valid_values={NET_BT_STANDBY_ON, NET_BT_STANDBY_OFF},
            feature_label="network/Bluetooth standby",
        )
        self.async_write_ha_state()

    async def async_turn_off(self, **_kwargs: Any) -> None:
        """Disable network/Bluetooth standby."""
        requested = NET_BT_STANDBY_OFF
        if not await self._client.async_set_net_bt_standby(requested):
            _LOGGER.error("Failed to disable network/Bluetooth standby")
            return
        try:
            actual = await self._client.async_get_net_bt_standby()
        except (OSError, TimeoutError) as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="verify_read_failed",
                translation_placeholders={
                    "feature": "network/Bluetooth standby",
                    "requested": requested,
                },
            ) from err
        self._attr_is_on = actual == NET_BT_STANDBY_ON
        verify_feature_value(
            requested=requested,
            actual=actual,
            valid_values={NET_BT_STANDBY_ON, NET_BT_STANDBY_OFF},
            feature_label="network/Bluetooth standby",
        )
        self.async_write_ha_state()

    async def async_update(self) -> None:
        """Update network/Bluetooth standby state."""
        try:
            value = await self._client.async_get_net_bt_standby()
            self._attr_is_on = value == NET_BT_STANDBY_ON
        except (OSError, TimeoutError):
            _LOGGER.exception("Failed to update network/Bluetooth standby state")


class BraviaQuadVoiceZoomSwitch(BraviaQuadNotificationMixin, SwitchEntity):
    """Representation of a Bravia Quad voice zoom switch."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_entity_registry_enabled_default = False
    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_translation_key = "voice_zoom"
    _notification_feature = FEATURE_VOICE_ZOOM

    def __init__(self, client: BraviaQuadClient, entry: ConfigEntry) -> None:
        """Initialize the voice zoom switch."""
        self._client = client
        self._attr_unique_id = entity_unique_id(entry, "voice_zoom")
        self._attr_is_on = client.voice_zoom == VOICE_ZOOM_ON
        self._attr_device_info = get_device_info(entry)

    async def _on_notification(self, value: str) -> None:
        """Handle voice zoom notification."""
        self._attr_is_on = value == VOICE_ZOOM_ON
        self.async_write_ha_state()

    async def async_turn_on(self, **_kwargs: Any) -> None:
        """Enable voice zoom."""
        success = await self._client.async_set_voice_zoom(VOICE_ZOOM_ON)
        if success:
            await self._verify_state()
        else:
            _LOGGER.error("Failed to enable voice zoom")

    async def async_turn_off(self, **_kwargs: Any) -> None:
        """Disable voice zoom."""
        success = await self._client.async_set_voice_zoom(VOICE_ZOOM_OFF)
        if success:
            await self._verify_state()
        else:
            _LOGGER.error("Failed to disable voice zoom")

    async def _verify_state(self) -> None:
        """Re-read state from device to verify SET was accepted."""
        try:
            value = await self._client.async_get_voice_zoom()
            self._attr_is_on = value == VOICE_ZOOM_ON
        except (OSError, TimeoutError):
            pass
        self.async_write_ha_state()

    async def async_update(self) -> None:
        """Update voice zoom state."""
        try:
            value = await self._client.async_get_voice_zoom()
            self._attr_is_on = value == VOICE_ZOOM_ON
        except (OSError, TimeoutError):
            _LOGGER.exception("Failed to update voice zoom state")


class BraviaQuadExternalControlSwitch(BraviaQuadNotificationMixin, SwitchEntity):
    """Representation of a Bravia Quad external control switch."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_entity_registry_enabled_default = False
    _attr_has_entity_name = True
    _attr_should_poll = True
    _attr_translation_key = "external_control"
    _notification_feature = FEATURE_EXTERNAL_CONTROL

    def __init__(self, client: BraviaQuadClient, entry: ConfigEntry) -> None:
        """Initialize the external control switch."""
        self._client = client
        self._attr_unique_id = entity_unique_id(entry, "external_control")
        self._attr_is_on = None
        self._attr_device_info = get_device_info(entry)

    async def _on_notification(self, value: str) -> None:
        """Handle external control notification."""
        self._attr_is_on = value == EXTERNAL_CONTROL_ON
        self.async_write_ha_state()

    async def async_turn_on(self, **_kwargs: Any) -> None:
        """Enable external control."""
        requested = EXTERNAL_CONTROL_ON
        if not await self._client.async_set_external_control(requested):
            _LOGGER.error("Failed to enable external control")
            return
        try:
            actual = await self._client.async_get_external_control()
        except (OSError, TimeoutError) as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="verify_read_failed",
                translation_placeholders={
                    "feature": "external control",
                    "requested": requested,
                },
            ) from err
        self._attr_is_on = actual == EXTERNAL_CONTROL_ON
        verify_feature_value(
            requested=requested,
            actual=actual,
            valid_values={EXTERNAL_CONTROL_ON, EXTERNAL_CONTROL_OFF},
            feature_label="external control",
        )
        self.async_write_ha_state()

    async def async_turn_off(self, **_kwargs: Any) -> None:
        """Disable external control."""
        requested = EXTERNAL_CONTROL_OFF
        if not await self._client.async_set_external_control(requested):
            _LOGGER.error("Failed to disable external control")
            return
        try:
            actual = await self._client.async_get_external_control()
        except (OSError, TimeoutError) as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="verify_read_failed",
                translation_placeholders={
                    "feature": "external control",
                    "requested": requested,
                },
            ) from err
        self._attr_is_on = actual == EXTERNAL_CONTROL_ON
        verify_feature_value(
            requested=requested,
            actual=actual,
            valid_values={EXTERNAL_CONTROL_ON, EXTERNAL_CONTROL_OFF},
            feature_label="external control",
        )
        self.async_write_ha_state()

    async def async_update(self) -> None:
        """Update external control state."""
        try:
            value = await self._client.async_get_external_control()
            self._attr_is_on = value == EXTERNAL_CONTROL_ON
        except (OSError, TimeoutError):
            _LOGGER.exception("Failed to update external control state")
