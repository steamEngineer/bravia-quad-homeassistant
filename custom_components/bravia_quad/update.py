"""Update platform for Bravia Theatre firmware updates."""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import timedelta
from typing import TYPE_CHECKING, Any

from homeassistant.components.update import UpdateEntity, UpdateEntityFeature
from homeassistant.const import EntityCategory
from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr

from .bravia_http_client import (
    SONY_MODEL_INFO,
    BraviaHttpClient,
    FirmwareUpdateStatus,
    LatestFirmwareInfo,
)
from .const import DOMAIN
from .helpers import get_device_info, require_unique_id

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from . import BraviaQuadData
    from .bravia_quad_client import BraviaQuadClient

_LOGGER = logging.getLogger(__name__)

SCAN_INTERVAL = timedelta(hours=4)

PARALLEL_UPDATES = 1

DEFAULT_FW_UPDATE_ESTIMATE_SEC = 600


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Bravia Theatre firmware update entity."""
    data: BraviaQuadData = hass.data[DOMAIN][entry.entry_id]

    async_add_entities(
        [BraviaQuadFirmwareUpdate(data.http_client, data.tcp_client, entry)],
        update_before_add=True,
    )


class BraviaQuadFirmwareUpdate(UpdateEntity):
    """Firmware update entity backed by the HTTP management API."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_has_entity_name = True
    _attr_translation_key = "firmware"
    _attr_supported_features = (
        UpdateEntityFeature.INSTALL | UpdateEntityFeature.PROGRESS
    )

    def __init__(
        self,
        http_client: BraviaHttpClient,
        tcp_client: BraviaQuadClient | None,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the firmware update entity."""
        self._http_client = http_client
        self._tcp_client = tcp_client
        self._entry = entry
        self._attr_unique_id = f"{DOMAIN}_{entry.unique_id}_firmware_update"
        self._attr_device_info = get_device_info(entry)
        self._installed_version: str | None = None
        self._model_name: str | None = None
        self._update_available = False
        self._latest_fw: LatestFirmwareInfo | None = None
        self._install_started_at: float = 0
        self._delayed_refresh_task: asyncio.Task[None] | None = None
        self._reconnect_refresh_task: asyncio.Task[None] | None = None

    async def async_added_to_hass(self) -> None:
        """Register TCP availability callback for reconnect detection."""
        await super().async_added_to_hass()
        if self._tcp_client is None:
            return
        self._tcp_client.register_availability_callback(self._on_tcp_availability)
        self.async_on_remove(
            lambda: self._tcp_client.unregister_availability_callback(  # type: ignore[union-attr]
                self._on_tcp_availability
            )
        )

    @callback
    def _on_tcp_availability(self, available: bool) -> None:  # noqa: FBT001
        """Recheck firmware when TCP reconnects after an update."""
        if not available:
            return
        self._install_started_at = 0
        self._reconnect_refresh_task = self.hass.async_create_task(
            self._async_refresh_firmware()
        )

    async def _async_refresh_firmware(self) -> None:
        """Recheck firmware status after reconnect."""
        await self.async_update()
        self.async_write_ha_state()

    @property
    def installed_version(self) -> str | None:
        """Return the installed firmware version."""
        return self._installed_version

    @property
    def latest_version(self) -> str | None:
        """Return the latest available firmware version."""
        if self._update_available:
            if self._latest_fw and self._latest_fw.version:
                return self._latest_fw.version
            return "Newer version"
        return self._installed_version

    @property
    def release_url(self) -> str | None:
        """Return a link to the release notes."""
        if self._latest_fw:
            return self._latest_fw.release_url
        return None

    @property
    def in_progress(self) -> bool | int:
        """Return update progress as a percentage, or False."""
        if self._install_started_at == 0:
            return False
        elapsed = time.monotonic() - self._install_started_at
        estimate = self._fw_update_estimate_sec
        if elapsed >= estimate:
            return False
        return min(int(elapsed / estimate * 100), 99)

    @property
    def _fw_update_estimate_sec(self) -> int:
        """Return the estimated update time for the current model."""
        if self._model_name and self._model_name in SONY_MODEL_INFO:
            return SONY_MODEL_INFO[self._model_name].fw_update_estimate_sec
        return DEFAULT_FW_UPDATE_ESTIMATE_SEC

    async def async_install(
        self,
        version: str | None,
        backup: bool,  # noqa: FBT001
        **kwargs: Any,
    ) -> None:
        """Trigger the firmware update on the device."""
        del version, backup, kwargs
        success = await self._http_client.async_request_firmware_update()
        if not success:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="firmware_update_failed",
            )
        self._install_started_at = time.monotonic()
        self._latest_fw = None

        self._delayed_refresh_task = self.hass.async_create_task(
            self._async_delayed_refresh(self._fw_update_estimate_sec)
        )

    async def async_will_remove_from_hass(self) -> None:
        """Cancel pending tasks on removal."""
        for task in (self._delayed_refresh_task, self._reconnect_refresh_task):
            if task and not task.done():
                task.cancel()

    async def async_update(self) -> None:
        """Poll the device for firmware status."""
        _LOGGER.debug("Polling firmware status")
        if self.in_progress is not False:
            _LOGGER.debug("Skipping poll, install in progress")
            return

        system_info = await self._http_client.async_get_system_info()
        if system_info.version is not None:
            self._installed_version = system_info.version
            self._update_device_sw_version(system_info.version)
        if system_info.model_name is not None:
            self._model_name = system_info.model_name

        status = await self._http_client.async_check_firmware_update()
        match status:
            case FirmwareUpdateStatus.UPDATE_AVAILABLE:
                self._update_available = True
                if not self._latest_fw or not self._latest_fw.version:
                    self._latest_fw = (
                        await self._http_client.async_get_latest_firmware_info(
                            self._model_name
                        )
                    )
            case FirmwareUpdateStatus.UP_TO_DATE:
                self._update_available = False
                self._latest_fw = None
                self._install_started_at = 0
            case FirmwareUpdateStatus.ERROR:
                pass

    async def _async_delayed_refresh(self, delay: int) -> None:
        """Backstop refresh after install cooldown expires."""
        await asyncio.sleep(delay)
        if self._install_started_at == 0:
            return
        self._install_started_at = 0
        await self.async_update()
        self.async_write_ha_state()

    def _update_device_sw_version(self, version: str) -> None:
        """Update the device registry with the current firmware version."""
        device_registry = dr.async_get(self.hass)
        device = device_registry.async_get_device(
            identifiers={(DOMAIN, require_unique_id(self._entry))}
        )
        if device and device.sw_version != version:
            device_registry.async_update_device(device.id, sw_version=version)
