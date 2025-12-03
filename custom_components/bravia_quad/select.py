"""Select platform for Bravia Quad controls."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo, EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    DOMAIN,
    INPUT_OPTIONS,
    INPUT_VALUES_TO_OPTIONS,
    BASS_LEVEL_OPTIONS,
    BASS_LEVEL_VALUES_TO_OPTIONS,
)
from .bravia_quad_client import BraviaQuadClient

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Bravia Quad select entities from a config entry."""
    client: BraviaQuadClient = hass.data[DOMAIN][entry.entry_id]
    
    # Create all select entities
    entities = [
        BraviaQuadInputSelect(client, entry),
        BraviaQuadBassLevelSelect(client, entry),
    ]
    
    async_add_entities(entities)


class BraviaQuadInputSelect(SelectEntity):
    """Representation of a Bravia Quad input selector."""

    _attr_should_poll = False

    def __init__(self, client: BraviaQuadClient, entry: ConfigEntry) -> None:
        """Initialize the input select entity."""
        self._client = client
        self._entry = entry
        self._attr_has_entity_name = True
        self._attr_name = "Source"
        self._attr_unique_id = f"{DOMAIN}_{entry.entry_id}_input"
        self._attr_options = list(INPUT_OPTIONS.keys())
        # Initialize current option from client's current input
        current_input_value = client.input
        self._attr_current_option = INPUT_VALUES_TO_OPTIONS.get(current_input_value, list(INPUT_OPTIONS.keys())[0])
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.data.get("name", "Bravia Quad"),
            manufacturer="Sony",
            model="Bravia Quad",
            configuration_url=f"http://{entry.data['host']}",
        )
        
        # Register for input notifications
        self._client.register_notification_callback(
            "main.input",
            self._on_input_notification
        )

    async def _on_input_notification(self, value: str) -> None:
        """Handle input notification."""
        # Convert value (e.g., "tv") to display option (e.g., "TV (eARC)")
        option = INPUT_VALUES_TO_OPTIONS.get(value)
        if option:
            self._attr_current_option = option
            self.async_write_ha_state()
        else:
            _LOGGER.warning("Unknown input value received: %s", value)

    async def async_select_option(self, option: str) -> None:
        """Change the selected option."""
        # Convert display option (e.g., "TV (eARC)") to value (e.g., "tv")
        input_value = INPUT_OPTIONS.get(option)
        if not input_value:
            _LOGGER.error("Invalid input option: %s", option)
            return
        
        success = await self._client.async_set_input(input_value)
        if success:
            self._attr_current_option = option
            self.async_write_ha_state()
        else:
            _LOGGER.error("Failed to set input to %s", option)

    async def async_update(self) -> None:
        """Update the current input."""
        try:
            input_value = await self._client.async_get_input()
            # Convert value to display option
            option = INPUT_VALUES_TO_OPTIONS.get(input_value)
            if option:
                self._attr_current_option = option
            else:
                _LOGGER.warning("Unknown input value: %s", input_value)
        except Exception as err:
            _LOGGER.error("Failed to update input: %s", err)


class BraviaQuadBassLevelSelect(SelectEntity):
    """Representation of a Bravia Quad bass level selector."""

    _attr_should_poll = False

    def __init__(self, client: BraviaQuadClient, entry: ConfigEntry) -> None:
        """Initialize the bass level select entity."""
        self._client = client
        self._entry = entry
        self._attr_has_entity_name = True
        self._attr_name = "Bass Level"
        self._attr_unique_id = f"{DOMAIN}_{entry.entry_id}_bass_level"
        self._attr_options = list(BASS_LEVEL_OPTIONS.keys())
        # Initialize current option from client's current bass level
        current_bass_value = client.bass_level
        self._attr_current_option = BASS_LEVEL_VALUES_TO_OPTIONS.get(current_bass_value, list(BASS_LEVEL_OPTIONS.keys())[1])
        self._attr_entity_category = EntityCategory.CONFIG
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.data.get("name", "Bravia Quad"),
            manufacturer="Sony",
            model="Bravia Quad",
            configuration_url=f"http://{entry.data['host']}",
        )
        
        # Register for bass level notifications
        self._client.register_notification_callback(
            "main.bassstep",
            self._on_bass_level_notification
        )

    async def _on_bass_level_notification(self, value: str) -> None:
        """Handle bass level notification."""
        try:
            bass_level = int(value)
            # Convert value (0-2) to display option (MIN/MID/MAX)
            option = BASS_LEVEL_VALUES_TO_OPTIONS.get(bass_level)
            if option:
                self._attr_current_option = option
                self.async_write_ha_state()
            else:
                _LOGGER.warning("Unknown bass level value received: %s", value)
        except (ValueError, TypeError):
            _LOGGER.warning("Invalid bass level notification value: %s", value)

    async def async_select_option(self, option: str) -> None:
        """Change the selected option."""
        # Convert display option (e.g., "MID") to value (e.g., 1)
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
            # Convert value to display option
            option = BASS_LEVEL_VALUES_TO_OPTIONS.get(bass_level_value)
            if option:
                self._attr_current_option = option
            else:
                _LOGGER.warning("Unknown bass level value: %s", bass_level_value)
        except Exception as err:
            _LOGGER.error("Failed to update bass level: %s", err)
