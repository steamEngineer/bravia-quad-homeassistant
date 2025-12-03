"""Switch platform for Bravia Quad controls."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo, EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    DOMAIN,
    POWER_ON,
    POWER_OFF,
    FEATURE_VOICE_ENHANCER,
    FEATURE_SOUND_FIELD,
    FEATURE_NIGHT_MODE,
    VOICE_ENHANCER_ON,
    VOICE_ENHANCER_OFF,
    SOUND_FIELD_ON,
    SOUND_FIELD_OFF,
    NIGHT_MODE_ON,
    NIGHT_MODE_OFF,
)
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
        BraviaQuadVoiceEnhancerSwitch(client, entry),
        BraviaQuadSoundFieldSwitch(client, entry),
        BraviaQuadNightModeSwitch(client, entry),
    ]
    
    # Fetch initial states
    for entity in entities:
        await entity.async_update()
    
    async_add_entities(entities)


class BraviaQuadPowerSwitch(SwitchEntity):
    """Representation of a Bravia Quad power switch."""

    def __init__(self, client: BraviaQuadClient, entry: ConfigEntry) -> None:
        """Initialize the switch."""
        self._client = client
        self._entry = entry
        self._attr_has_entity_name = True
        self._attr_name = "Power"
        self._attr_unique_id = f"{DOMAIN}_{entry.entry_id}_power"
        # Initialize from client's current state
        self._attr_is_on = client.power_state == POWER_ON
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.data.get("name", "Bravia Quad"),
            manufacturer="Sony",
            model="Bravia Quad",
            configuration_url=f"http://{entry.data['host']}",
        )
        
        # Register for power notifications
        self._client.register_notification_callback(
            "main.power",
            self._on_power_notification
        )

    async def _on_power_notification(self, value: str) -> None:
        """Handle power state notification."""
        self._attr_is_on = value == POWER_ON
        self.async_write_ha_state()

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the device on."""
        success = await self._client.async_set_power(POWER_ON)
        if success:
            self._attr_is_on = True
            self.async_write_ha_state()
        else:
            _LOGGER.error("Failed to turn on Bravia Quad")

    async def async_turn_off(self, **kwargs: Any) -> None:
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
            self.async_write_ha_state()
        except Exception as err:
            _LOGGER.error("Failed to update power state: %s", err)


class BraviaQuadVoiceEnhancerSwitch(SwitchEntity):
    """Representation of a Bravia Quad voice enhancer switch."""

    def __init__(self, client: BraviaQuadClient, entry: ConfigEntry) -> None:
        """Initialize the voice enhancer switch."""
        self._client = client
        self._entry = entry
        self._attr_has_entity_name = True
        self._attr_name = "Voice Enhancer"
        self._attr_unique_id = f"{DOMAIN}_{entry.entry_id}_voice_enhancer"
        # Initialize from client's current state
        self._attr_is_on = client.voice_enhancer == VOICE_ENHANCER_ON
        self._attr_entity_category = EntityCategory.CONFIG
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.data.get("name", "Bravia Quad"),
            manufacturer="Sony",
            model="Bravia Quad",
            configuration_url=f"http://{entry.data['host']}",
        )
        
        # Register for voice enhancer notifications
        self._client.register_notification_callback(
            FEATURE_VOICE_ENHANCER,
            self._on_voice_enhancer_notification
        )

    async def _on_voice_enhancer_notification(self, value: str) -> None:
        """Handle voice enhancer state notification."""
        self._attr_is_on = value == VOICE_ENHANCER_ON
        self.async_write_ha_state()

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn voice enhancer on."""
        success = await self._client.async_set_voice_enhancer(VOICE_ENHANCER_ON)
        if success:
            self._attr_is_on = True
            self.async_write_ha_state()
        else:
            _LOGGER.error("Failed to turn on voice enhancer")

    async def async_turn_off(self, **kwargs: Any) -> None:
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
            self.async_write_ha_state()
        except Exception as err:
            _LOGGER.error("Failed to update voice enhancer state: %s", err)


class BraviaQuadSoundFieldSwitch(SwitchEntity):
    """Representation of a Bravia Quad sound field switch."""

    def __init__(self, client: BraviaQuadClient, entry: ConfigEntry) -> None:
        """Initialize the sound field switch."""
        self._client = client
        self._entry = entry
        self._attr_has_entity_name = True
        self._attr_name = "Sound Field"
        self._attr_unique_id = f"{DOMAIN}_{entry.entry_id}_sound_field"
        # Initialize from client's current state
        self._attr_is_on = client.sound_field == SOUND_FIELD_ON
        self._attr_entity_category = EntityCategory.CONFIG
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.data.get("name", "Bravia Quad"),
            manufacturer="Sony",
            model="Bravia Quad",
            configuration_url=f"http://{entry.data['host']}",
        )
        
        # Register for sound field notifications
        self._client.register_notification_callback(
            FEATURE_SOUND_FIELD,
            self._on_sound_field_notification
        )

    async def _on_sound_field_notification(self, value: str) -> None:
        """Handle sound field state notification."""
        self._attr_is_on = value == SOUND_FIELD_ON
        self.async_write_ha_state()

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn sound field on."""
        success = await self._client.async_set_sound_field(SOUND_FIELD_ON)
        if success:
            self._attr_is_on = True
            self.async_write_ha_state()
        else:
            _LOGGER.error("Failed to turn on sound field")

    async def async_turn_off(self, **kwargs: Any) -> None:
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
            self.async_write_ha_state()
        except Exception as err:
            _LOGGER.error("Failed to update sound field state: %s", err)


class BraviaQuadNightModeSwitch(SwitchEntity):
    """Representation of a Bravia Quad night mode switch."""

    def __init__(self, client: BraviaQuadClient, entry: ConfigEntry) -> None:
        """Initialize the night mode switch."""
        self._client = client
        self._entry = entry
        self._attr_has_entity_name = True
        self._attr_name = "Night Mode"
        self._attr_unique_id = f"{DOMAIN}_{entry.entry_id}_night_mode"
        # Initialize from client's current state
        self._attr_is_on = client.night_mode == NIGHT_MODE_ON
        self._attr_entity_category = EntityCategory.CONFIG
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.data.get("name", "Bravia Quad"),
            manufacturer="Sony",
            model="Bravia Quad",
            configuration_url=f"http://{entry.data['host']}",
        )
        
        # Register for night mode notifications
        self._client.register_notification_callback(
            FEATURE_NIGHT_MODE,
            self._on_night_mode_notification
        )

    async def _on_night_mode_notification(self, value: str) -> None:
        """Handle night mode state notification."""
        self._attr_is_on = value == NIGHT_MODE_ON
        self.async_write_ha_state()

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn night mode on."""
        success = await self._client.async_set_night_mode(NIGHT_MODE_ON)
        if success:
            self._attr_is_on = True
            self.async_write_ha_state()
        else:
            _LOGGER.error("Failed to turn on night mode")

    async def async_turn_off(self, **kwargs: Any) -> None:
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
            self.async_write_ha_state()
        except Exception as err:
            _LOGGER.error("Failed to update night mode state: %s", err)

