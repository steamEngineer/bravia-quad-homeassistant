"""Sensor platform for Bravia Quad diagnostics."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import TYPE_CHECKING

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.const import EntityCategory, UnitOfTemperature

from . import BraviaQuadData
from .const import (
    DOMAIN,
    FEATURE_360SSM,
    FEATURE_DESTINATION,
    FEATURE_DEVICE_NAME,
    FEATURE_DHCP,
    FEATURE_IP_ADDRESS,
    FEATURE_LANGUAGE,
    FEATURE_NETWORK_MODE,
    FEATURE_TEMPERATURE,
    FEATURE_TIMEZONE,
    FEATURE_VOICE_ZOOM_LEVEL,
)
from .helpers import BraviaQuadNotificationMixin, get_device_info

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from .bravia_quad_client import BraviaQuadClient

_LOGGER = logging.getLogger(__name__)

SCAN_INTERVAL = timedelta(seconds=60)

PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Bravia Quad sensor entities."""
    data: BraviaQuadData = hass.data[DOMAIN][entry.entry_id]
    client = data.tcp_client

    async_add_entities(
        [
            BraviaQuadTemperatureSensor(client, entry),
            BraviaQuadTimezoneSensor(client, entry),
            BraviaQuad360SsmSensor(client, entry),
            BraviaQuadVoiceZoomLevelSensor(client, entry),
            BraviaQuadNetworkModeSensor(client, entry),
            BraviaQuadIpAddressSensor(client, entry),
            BraviaQuadDeviceNameSensor(client, entry),
            BraviaQuadDestinationSensor(client, entry),
            BraviaQuadLanguageSensor(client, entry),
            BraviaQuadDhcpSensor(client, entry),
        ],
        update_before_add=True,
    )


class BraviaQuadTemperatureSensor(BraviaQuadNotificationMixin, SensorEntity):
    """Bravia Quad internal temperature sensor."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_has_entity_name = True
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_should_poll = True
    _attr_translation_key = "temperature"
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _notification_feature = FEATURE_TEMPERATURE

    def __init__(self, client: BraviaQuadClient, entry: ConfigEntry) -> None:
        """Initialize the temperature sensor."""
        self._client = client
        self._attr_unique_id = f"{DOMAIN}_{entry.unique_id}_temperature"
        self._attr_native_value = None
        self._attr_device_info = get_device_info(entry)

    async def _on_notification(self, value: str) -> None:
        """Handle temperature notification."""
        self._attr_native_value = _parse_temperature(value)
        self.async_write_ha_state()

    async def async_update(self) -> None:
        """Update temperature state."""
        try:
            value = await self._client.async_get_temperature()
            self._attr_native_value = _parse_temperature(value)
        except (OSError, TimeoutError):
            _LOGGER.exception("Failed to update temperature")


def _parse_temperature(value: str | None) -> float | None:
    """Parse temperature from 'F:xxx,C:yyy' format to Celsius float."""
    if not value:
        return None
    try:
        for part in value.split(","):
            part = part.strip()
            if part.startswith("C:"):
                return float(part[2:])
    except (ValueError, IndexError):
        pass
    return None


class BraviaQuadTimezoneSensor(BraviaQuadNotificationMixin, SensorEntity):
    """Bravia Quad timezone sensor."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_has_entity_name = True
    _attr_should_poll = True
    _attr_translation_key = "timezone"
    _attr_entity_registry_enabled_default = False
    _notification_feature = FEATURE_TIMEZONE

    def __init__(self, client: BraviaQuadClient, entry: ConfigEntry) -> None:
        """Initialize the timezone sensor."""
        self._client = client
        self._attr_unique_id = f"{DOMAIN}_{entry.unique_id}_timezone"
        self._attr_native_value = None
        self._attr_device_info = get_device_info(entry)

    async def _on_notification(self, value: str) -> None:
        """Handle timezone notification."""
        self._attr_native_value = value
        self.async_write_ha_state()

    async def async_update(self) -> None:
        """Update timezone state."""
        try:
            self._attr_native_value = await self._client.async_get_timezone()
        except (OSError, TimeoutError):
            _LOGGER.exception("Failed to update timezone")


class BraviaQuad360SsmSensor(BraviaQuadNotificationMixin, SensorEntity):
    """Bravia Quad 360SSM sensor."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_has_entity_name = True
    _attr_should_poll = True
    _attr_translation_key = "ssm_360"
    _attr_entity_registry_enabled_default = False
    _notification_feature = FEATURE_360SSM

    def __init__(self, client: BraviaQuadClient, entry: ConfigEntry) -> None:
        """Initialize the 360SSM sensor."""
        self._client = client
        self._attr_unique_id = f"{DOMAIN}_{entry.unique_id}_360ssm"
        self._attr_native_value = None
        self._attr_device_info = get_device_info(entry)

    async def _on_notification(self, value: str) -> None:
        """Handle 360SSM notification."""
        self._attr_native_value = value
        self.async_write_ha_state()

    async def async_update(self) -> None:
        """Update 360SSM state."""
        try:
            self._attr_native_value = await self._client.async_get_360ssm()
        except (OSError, TimeoutError):
            _LOGGER.exception("Failed to update 360SSM")


class BraviaQuadVoiceZoomLevelSensor(BraviaQuadNotificationMixin, SensorEntity):
    """Bravia Quad voice zoom level sensor."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_has_entity_name = True
    _attr_should_poll = True
    _attr_entity_registry_enabled_default = False
    _attr_translation_key = "voice_zoom_level"
    _notification_feature = FEATURE_VOICE_ZOOM_LEVEL

    def __init__(self, client: BraviaQuadClient, entry: ConfigEntry) -> None:
        """Initialize the voice zoom level sensor."""
        self._client = client
        self._attr_unique_id = f"{DOMAIN}_{entry.unique_id}_voice_zoom_level"
        self._attr_native_value = None
        self._attr_device_info = get_device_info(entry)

    async def _on_notification(self, value: str) -> None:
        """Handle voice zoom level notification."""
        try:
            self._attr_native_value = int(value)
            self.async_write_ha_state()
        except (ValueError, TypeError):
            pass

    async def async_update(self) -> None:
        """Update voice zoom level."""
        try:
            self._attr_native_value = await self._client.async_get_voice_zoom_level()
        except (OSError, TimeoutError):
            _LOGGER.exception("Failed to update voice zoom level")


class BraviaQuadNetworkModeSensor(BraviaQuadNotificationMixin, SensorEntity):
    """Bravia Quad network mode sensor."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_has_entity_name = True
    _attr_should_poll = True
    _attr_translation_key = "network_mode"
    _notification_feature = FEATURE_NETWORK_MODE

    def __init__(self, client: BraviaQuadClient, entry: ConfigEntry) -> None:
        """Initialize the network mode sensor."""
        self._client = client
        self._attr_unique_id = f"{DOMAIN}_{entry.unique_id}_network_mode"
        self._attr_native_value = None
        self._attr_device_info = get_device_info(entry)

    async def _on_notification(self, value: str) -> None:
        """Handle network mode notification."""
        self._attr_native_value = value
        self.async_write_ha_state()

    async def async_update(self) -> None:
        """Update network mode state."""
        try:
            self._attr_native_value = await self._client.async_get_network_mode()
        except (OSError, TimeoutError):
            _LOGGER.exception("Failed to update network mode")


class BraviaQuadIpAddressSensor(BraviaQuadNotificationMixin, SensorEntity):
    """Bravia Quad IP address sensor."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_has_entity_name = True
    _attr_should_poll = True
    _attr_translation_key = "ip_address"
    _notification_feature = FEATURE_IP_ADDRESS

    def __init__(self, client: BraviaQuadClient, entry: ConfigEntry) -> None:
        """Initialize the IP address sensor."""
        self._client = client
        self._attr_unique_id = f"{DOMAIN}_{entry.unique_id}_ip_address"
        self._attr_native_value = None
        self._attr_device_info = get_device_info(entry)

    async def _on_notification(self, value: str) -> None:
        """Handle IP address notification."""
        self._attr_native_value = value
        self.async_write_ha_state()

    async def async_update(self) -> None:
        """Update IP address state."""
        try:
            self._attr_native_value = await self._client.async_get_ip_address()
        except (OSError, TimeoutError):
            _LOGGER.exception("Failed to update IP address")


class BraviaQuadDeviceNameSensor(BraviaQuadNotificationMixin, SensorEntity):
    """Bravia Quad device name sensor."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_has_entity_name = True
    _attr_should_poll = True
    _attr_translation_key = "device_name"
    _notification_feature = FEATURE_DEVICE_NAME

    def __init__(self, client: BraviaQuadClient, entry: ConfigEntry) -> None:
        """Initialize the device name sensor."""
        self._client = client
        self._attr_unique_id = f"{DOMAIN}_{entry.unique_id}_device_name"
        self._attr_native_value = None
        self._attr_device_info = get_device_info(entry)

    async def _on_notification(self, value: str) -> None:
        """Handle device name notification."""
        self._attr_native_value = value
        self.async_write_ha_state()

    async def async_update(self) -> None:
        """Update device name state."""
        try:
            self._attr_native_value = await self._client.async_get_device_name()
        except (OSError, TimeoutError):
            _LOGGER.exception("Failed to update device name")


class BraviaQuadDestinationSensor(BraviaQuadNotificationMixin, SensorEntity):
    """Bravia Quad destination sensor."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_has_entity_name = True
    _attr_should_poll = True
    _attr_entity_registry_enabled_default = False
    _attr_translation_key = "destination"
    _notification_feature = FEATURE_DESTINATION

    def __init__(self, client: BraviaQuadClient, entry: ConfigEntry) -> None:
        """Initialize the destination sensor."""
        self._client = client
        self._attr_unique_id = f"{DOMAIN}_{entry.unique_id}_destination"
        self._attr_native_value = None
        self._attr_device_info = get_device_info(entry)

    async def _on_notification(self, value: str) -> None:
        """Handle destination notification."""
        self._attr_native_value = value
        self.async_write_ha_state()

    async def async_update(self) -> None:
        """Update destination state."""
        try:
            self._attr_native_value = await self._client.async_get_destination()
        except (OSError, TimeoutError):
            _LOGGER.exception("Failed to update destination")


class BraviaQuadLanguageSensor(BraviaQuadNotificationMixin, SensorEntity):
    """Bravia Quad language sensor."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_has_entity_name = True
    _attr_should_poll = True
    _attr_entity_registry_enabled_default = False
    _attr_translation_key = "language"
    _notification_feature = FEATURE_LANGUAGE

    def __init__(self, client: BraviaQuadClient, entry: ConfigEntry) -> None:
        """Initialize the language sensor."""
        self._client = client
        self._attr_unique_id = f"{DOMAIN}_{entry.unique_id}_language"
        self._attr_native_value = None
        self._attr_device_info = get_device_info(entry)

    async def _on_notification(self, value: str) -> None:
        """Handle language notification."""
        self._attr_native_value = value
        self.async_write_ha_state()

    async def async_update(self) -> None:
        """Update language state."""
        try:
            self._attr_native_value = await self._client.async_get_language()
        except (OSError, TimeoutError):
            _LOGGER.exception("Failed to update language")


class BraviaQuadDhcpSensor(BraviaQuadNotificationMixin, SensorEntity):
    """Bravia Quad DHCP sensor."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_has_entity_name = True
    _attr_should_poll = True
    _attr_entity_registry_enabled_default = False
    _attr_translation_key = "dhcp"
    _notification_feature = FEATURE_DHCP

    def __init__(self, client: BraviaQuadClient, entry: ConfigEntry) -> None:
        """Initialize the DHCP sensor."""
        self._client = client
        self._attr_unique_id = f"{DOMAIN}_{entry.unique_id}_dhcp"
        self._attr_native_value = None
        self._attr_device_info = get_device_info(entry)

    async def _on_notification(self, value: str) -> None:
        """Handle DHCP notification."""
        self._attr_native_value = value
        self.async_write_ha_state()

    async def async_update(self) -> None:
        """Update DHCP state."""
        try:
            self._attr_native_value = await self._client.async_get_dhcp()
        except (OSError, TimeoutError):
            _LOGGER.exception("Failed to update DHCP")
