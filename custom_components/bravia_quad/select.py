"""Select platform for Bravia Quad controls."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from homeassistant.components.select import SelectEntity
from homeassistant.const import EntityCategory
from homeassistant.helpers import entity_registry as er

from .const import (
    BASS_LEVEL_OPTIONS,
    BASS_LEVEL_VALUES_TO_OPTIONS,
    CONF_HAS_SUBWOOFER,
    DOMAIN,
    INPUT_OPTIONS,
    INPUT_VALUES_TO_OPTIONS,
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
    """Set up Bravia Quad select entities from a config entry."""
    client: BraviaQuadClient = hass.data[DOMAIN][entry.entry_id]

    # Create select entities
    entities: list[SelectEntity] = [
        BraviaQuadInputSelect(client, entry),
    ]

    # Add bass level select only if no subwoofer detected
    if not entry.data.get(CONF_HAS_SUBWOOFER, False):
        entities.append(BraviaQuadBassLevelSelect(hass, client, entry))

    async_add_entities(entities)


class BraviaQuadInputSelect(SelectEntity):
    """Representation of a Bravia Quad input selector."""

    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_translation_key = "input"

    def __init__(self, client: BraviaQuadClient, entry: ConfigEntry) -> None:
        """Initialize the input select entity."""
        self._client = client
        self._attr_unique_id = f"{DOMAIN}_{entry.entry_id}_input"
        self._attr_options = list(INPUT_OPTIONS.keys())
        current_input_value = client.input
        self._attr_current_option = INPUT_VALUES_TO_OPTIONS.get(
            current_input_value, next(iter(INPUT_OPTIONS.keys()), "TV (eARC)")
        )
        self._attr_device_info = get_device_info(entry)

        # Register for input notifications
        self._client.register_notification_callback(
            "main.input", self._on_input_notification
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
        except (OSError, TimeoutError):
            _LOGGER.exception("Failed to update input")


class BraviaQuadBassLevelSelect(SelectEntity):
    """Representation of a Bravia Quad bass level selector (for non-subwoofer mode)."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_translation_key = "bass_level"

    def __init__(
        self, hass: HomeAssistant, client: BraviaQuadClient, entry: ConfigEntry
    ) -> None:
        """Initialize the bass level select entity."""
        self._hass = hass
        self._client = client
        self._entry = entry
        self._reloading = False
        self._attr_unique_id = f"{DOMAIN}_{entry.entry_id}_bass_level_select"
        self._attr_options = list(BASS_LEVEL_OPTIONS.keys())
        current_bass_value = client.bass_level
        self._attr_current_option = BASS_LEVEL_VALUES_TO_OPTIONS.get(
            current_bass_value, "MID"
        )
        self._attr_device_info = get_device_info(entry)

        # Register for bass level notifications
        self._client.register_notification_callback(
            "main.bassstep", self._on_bass_level_notification
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
        except (OSError, TimeoutError):
            _LOGGER.exception("Failed to update bass level")
