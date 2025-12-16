"""Button platform for Bravia Quad controls."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from homeassistant.components.button import ButtonEntity
from homeassistant.const import EntityCategory
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er

from .const import CONF_HAS_SUBWOOFER, DOMAIN
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
    """Set up Bravia Quad button entities from a config entry."""
    client: BraviaQuadClient = hass.data[DOMAIN][entry.entry_id]

    entities = [
        BraviaQuadDetectSubwooferButton(hass, client, entry),
        BraviaQuadBluetoothPairingButton(client, entry),
    ]

    async_add_entities(entities)


class BraviaQuadDetectSubwooferButton(ButtonEntity):
    """Button to detect subwoofer presence."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_has_entity_name = True
    _attr_icon = "mdi:speaker-wireless"
    _attr_should_poll = False
    _attr_translation_key = "detect_subwoofer"

    def __init__(
        self, hass: HomeAssistant, client: BraviaQuadClient, entry: ConfigEntry
    ) -> None:
        """Initialize the detect subwoofer button entity."""
        self._hass = hass
        self._client = client
        self._entry = entry
        self._detection_lock = asyncio.Lock()
        self._attr_unique_id = f"{DOMAIN}_{entry.entry_id}_detect_subwoofer"
        self._attr_device_info = get_device_info(entry)

    async def async_press(self) -> None:
        """Handle button press to detect subwoofer."""
        # Prevent concurrent detections with a lock
        if self._detection_lock.locked():
            _LOGGER.debug("Subwoofer detection already in progress, ignoring request")
            return

        async with self._detection_lock:
            _LOGGER.info("Starting subwoofer detection...")

            try:
                has_subwoofer = await self._client.async_detect_subwoofer()
            except (OSError, TimeoutError):
                _LOGGER.exception("Subwoofer detection failed due to connection error")
                raise HomeAssistantError(
                    translation_domain=DOMAIN,
                    translation_key="detection_failed",
                ) from None

            # Get current value to check if it changed
            current_value = self._entry.data.get(CONF_HAS_SUBWOOFER)

            if current_value != has_subwoofer:
                _LOGGER.info(
                    "Subwoofer detection result changed: %s -> %s",
                    current_value,
                    has_subwoofer,
                )
                # Remove the old bass level entity before reload
                # If switching TO subwoofer, remove the select entity
                # If switching FROM subwoofer, remove the slider entity
                entity_registry = er.async_get(self._hass)
                if has_subwoofer:
                    # Remove the select entity (no subwoofer -> subwoofer)
                    old_unique_id = f"{DOMAIN}_{self._entry.entry_id}_bass_level_select"
                else:
                    # Remove the slider entity (subwoofer -> no subwoofer)
                    old_unique_id = f"{DOMAIN}_{self._entry.entry_id}_bass_level_slider"

                if old_entity := entity_registry.async_get_entity_id(
                    "number" if not has_subwoofer else "select",
                    DOMAIN,
                    old_unique_id,
                ):
                    _LOGGER.debug("Removing stale bass level entity: %s", old_entity)
                    entity_registry.async_remove(old_entity)

                # Update entry data with new detection result
                new_data = {**self._entry.data, CONF_HAS_SUBWOOFER: has_subwoofer}
                self._hass.config_entries.async_update_entry(self._entry, data=new_data)

                # Reload the integration to recreate entities with correct type.
                # A full reload is simpler and more robust than dynamic entity
                # swapping, and the brief reconnection is acceptable for this
                # rare operation.
                if not await self._hass.config_entries.async_reload(
                    self._entry.entry_id
                ):
                    raise HomeAssistantError(
                        translation_domain=DOMAIN,
                        translation_key="reload_failed",
                    )
            else:
                _LOGGER.info(
                    "Subwoofer detection result unchanged: %s",
                    has_subwoofer,
                )


class BraviaQuadBluetoothPairingButton(ButtonEntity):
    """Button to trigger Bluetooth pairing mode."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_has_entity_name = True
    _attr_icon = "mdi:bluetooth"
    _attr_should_poll = False
    _attr_translation_key = "bluetooth_pairing"

    def __init__(self, client: BraviaQuadClient, entry: ConfigEntry) -> None:
        """Initialize the Bluetooth pairing button entity."""
        self._client = client
        self._attr_unique_id = f"{DOMAIN}_{entry.entry_id}_bluetooth_pairing"
        self._attr_device_info = get_device_info(entry)

    async def async_press(self) -> None:
        """Handle button press to trigger Bluetooth pairing mode."""
        _LOGGER.info("Triggering Bluetooth pairing mode...")

        try:
            # Step 1: Verify the source is currently bluetooth,
            # if not change to bluetooth
            current_input = await self._client.async_get_input()
            if current_input != "bluetooth":
                _LOGGER.info(
                    "Current input is %s, switching to bluetooth", current_input
                )
                success = await self._client.async_set_input("bluetooth")
                if not success:
                    _LOGGER.error("Failed to switch input to bluetooth")
                    msg = "Failed to switch input to Bluetooth. Please try again."
                    raise HomeAssistantError(msg)
            else:
                _LOGGER.debug("Input is already set to bluetooth")

            # Step 2: Send command to set bluetooth.mode to "Off"
            command_off = {
                "id": 0,
                "type": "set",
                "feature": "bluetooth.mode",
                "value": "Off",
            }
            _LOGGER.debug("Setting bluetooth.mode to Off")
            response = await self._client.async_send_command(command_off)
            if not response or response.get("value") != "ACK":
                _LOGGER.warning(
                    "Unexpected response when setting bluetooth.mode to Off: %s",
                    response,
                )

            # Step 3: Wait 500ms
            await asyncio.sleep(0.5)

            # Step 4: Send command to set bluetooth.mode to "RX"
            command_rx = {
                "id": 0,
                "type": "set",
                "feature": "bluetooth.mode",
                "value": "RX",
            }
            _LOGGER.debug("Setting bluetooth.mode to RX")
            response = await self._client.async_send_command(command_rx)
            if not response or response.get("value") != "ACK":
                _LOGGER.warning(
                    "Unexpected response when setting bluetooth.mode to RX: %s",
                    response,
                )

            _LOGGER.info("Bluetooth pairing mode triggered successfully")

        except (OSError, TimeoutError) as err:
            _LOGGER.exception(
                "Bluetooth pairing trigger failed due to connection error"
            )
            msg = (
                "Failed to trigger Bluetooth pairing mode due to a "
                "connection error. Please try again."
            )
            raise HomeAssistantError(msg) from err
