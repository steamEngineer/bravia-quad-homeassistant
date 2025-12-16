"""Switch platform for Bravia Quad controls."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.const import EntityCategory

from .const import (
    AUTO_STANDBY_OFF,
    AUTO_STANDBY_ON,
    DOMAIN,
    FEATURE_AUTO_STANDBY,
    FEATURE_HDMI_CEC,
    FEATURE_NIGHT_MODE,
    FEATURE_SOUND_FIELD,
    FEATURE_VOICE_ENHANCER,
    HDMI_CEC_OFF,
    HDMI_CEC_ON,
    NIGHT_MODE_OFF,
    NIGHT_MODE_ON,
    POWER_OFF,
    POWER_ON,
    SOUND_FIELD_OFF,
    SOUND_FIELD_ON,
    VOICE_ENHANCER_OFF,
    VOICE_ENHANCER_ON,
)
from .helpers import get_device_info

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from .bravia_quad_client import BraviaQuadClient

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Bravia Quad switches from a config entry."""
    client: BraviaQuadClient = hass.data[DOMAIN][entry.entry_id]

    # Create all switch entities
    entities = [
        BraviaQuadPowerSwitch(client, entry),
        BraviaQuadHdmiCecSwitch(client, entry),
        BraviaQuadAutoStandbySwitch(client, entry),
        BraviaQuadVoiceEnhancerSwitch(client, entry),
        BraviaQuadSoundFieldSwitch(client, entry),
        BraviaQuadNightModeSwitch(client, entry),
    ]

    async_add_entities(entities)


class BraviaQuadPowerSwitch(SwitchEntity):
    """Representation of a Bravia Quad power switch."""

    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_translation_key = "power"

    def __init__(self, client: BraviaQuadClient, entry: ConfigEntry) -> None:
        """Initialize the switch."""
        self._client = client
        self._attr_unique_id = f"{DOMAIN}_{entry.entry_id}_power"
        self._attr_is_on = client.power_state == POWER_ON
        self._attr_device_info = get_device_info(entry)

        # Register for power notifications
        self._client.register_notification_callback(
            "main.power", self._on_power_notification
        )

    async def _on_power_notification(self, value: str) -> None:
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


class BraviaQuadHdmiCecSwitch(SwitchEntity):
    """Representation of a Bravia Quad HDMI CEC switch."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_translation_key = "hdmi_cec"

    def __init__(self, client: BraviaQuadClient, entry: ConfigEntry) -> None:
        """Initialize the HDMI CEC switch."""
        self._client = client
        self._attr_unique_id = f"{DOMAIN}_{entry.entry_id}_hdmi_cec"
        self._attr_is_on = client.hdmi_cec == HDMI_CEC_ON
        self._attr_device_info = get_device_info(entry)

        self._client.register_notification_callback(
            FEATURE_HDMI_CEC, self._on_hdmi_cec_notification
        )

    async def _on_hdmi_cec_notification(self, value: str) -> None:
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


class BraviaQuadAutoStandbySwitch(SwitchEntity):
    """Representation of a Bravia Quad auto standby switch."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_translation_key = "auto_standby"

    def __init__(self, client: BraviaQuadClient, entry: ConfigEntry) -> None:
        """Initialize the auto standby switch."""
        self._client = client
        self._attr_unique_id = f"{DOMAIN}_{entry.entry_id}_auto_standby"
        self._attr_is_on = client.auto_standby == AUTO_STANDBY_ON
        self._attr_device_info = get_device_info(entry)

        self._client.register_notification_callback(
            FEATURE_AUTO_STANDBY, self._on_auto_standby_notification
        )

    async def _on_auto_standby_notification(self, value: str) -> None:
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


class BraviaQuadVoiceEnhancerSwitch(SwitchEntity):
    """Representation of a Bravia Quad voice enhancer switch."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_translation_key = "voice_enhancer"

    def __init__(self, client: BraviaQuadClient, entry: ConfigEntry) -> None:
        """Initialize the voice enhancer switch."""
        self._client = client
        self._attr_unique_id = f"{DOMAIN}_{entry.entry_id}_voice_enhancer"
        self._attr_is_on = client.voice_enhancer == VOICE_ENHANCER_ON
        self._attr_device_info = get_device_info(entry)

        # Register for voice enhancer notifications
        self._client.register_notification_callback(
            FEATURE_VOICE_ENHANCER, self._on_voice_enhancer_notification
        )

    async def _on_voice_enhancer_notification(self, value: str) -> None:
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


class BraviaQuadSoundFieldSwitch(SwitchEntity):
    """Representation of a Bravia Quad sound field switch."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_translation_key = "sound_field"

    def __init__(self, client: BraviaQuadClient, entry: ConfigEntry) -> None:
        """Initialize the sound field switch."""
        self._client = client
        self._attr_unique_id = f"{DOMAIN}_{entry.entry_id}_sound_field"
        self._attr_is_on = client.sound_field == SOUND_FIELD_ON
        self._attr_device_info = get_device_info(entry)

        # Register for sound field notifications
        self._client.register_notification_callback(
            FEATURE_SOUND_FIELD, self._on_sound_field_notification
        )

    async def _on_sound_field_notification(self, value: str) -> None:
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


class BraviaQuadNightModeSwitch(SwitchEntity):
    """Representation of a Bravia Quad night mode switch."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_translation_key = "night_mode"

    def __init__(self, client: BraviaQuadClient, entry: ConfigEntry) -> None:
        """Initialize the night mode switch."""
        self._client = client
        self._attr_unique_id = f"{DOMAIN}_{entry.entry_id}_night_mode"
        self._attr_is_on = client.night_mode == NIGHT_MODE_ON
        self._attr_device_info = get_device_info(entry)

        # Register for night mode notifications
        self._client.register_notification_callback(
            FEATURE_NIGHT_MODE, self._on_night_mode_notification
        )

    async def _on_night_mode_notification(self, value: str) -> None:
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
