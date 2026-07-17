"""HTTP client for the Bravia Theatre web management API (port 54545)."""

from __future__ import annotations

import asyncio
import logging
import time
from contextlib import suppress
from dataclasses import dataclass
from enum import Enum
from typing import Any
from xml.etree import ElementTree as ET

import aiohttp

_LOGGER = logging.getLogger(__name__)

HTTP_API_PORT = 54545
HTTP_API_ENDPOINT = "/fcgi-bin/request.fcgi"
HTTP_API_TIMEOUT = 15
HTTP_PROBE_TIMEOUT = 2.0

# Sony update info server. The path components (am_cid/am_sid) are
# model-level identifiers sourced from the device's
# attributes.parameters in Sony's cloud registration data.
# The release URL ID is from Sony's support site.
SONY_UPDATE_INFO_BASE = "https://info.update.sony.net"
SONY_RELEASE_BASE = "https://www.sony.co.uk/electronics/support/software"


# Per-model update server paths, release page IDs, and firmware
# update time estimates.
# To add a new model: find am_cid/am_sid in the Sony app's device
# database (device_and_group.db -> attributes.parameters), the
# release URL ID from the Sony support site, and the update estimate
# from attributes.fw_update_main_unit.estimate_time_sec.
@dataclass(frozen=True)
class ModelInfo:
    """Per-model metadata for Sony update server and firmware estimates."""

    am_cid: str
    am_sid: str
    release_id: str
    fw_update_estimate_sec: int


SONY_MODEL_INFO: dict[str, ModelInfo] = {
    "BRAVIA Theatre Quad": ModelInfo(
        am_cid="HA002",
        am_sid="HT00014",
        release_id="00342249",
        fw_update_estimate_sec=360,
    ),
}


class FirmwareUpdateStatus(Enum):
    """Result of a firmware update availability check."""

    UP_TO_DATE = "up_to_date"
    UPDATE_AVAILABLE = "update_available"
    ERROR = "error"


@dataclass
class SystemInfo:
    """System information from the device."""

    version: str | None = None
    model_name: str | None = None


@dataclass
class DeviceDetails:
    """Device details from the device."""

    device_name: str | None = None
    connection_type: str | None = None
    internet: str | None = None
    ipv4_address: str | None = None
    ipv6_address: str | None = None
    wifi_signal: str | None = None
    mac_wired: str | None = None
    mac_wireless: str | None = None


@dataclass
class LatestFirmwareInfo:
    """Latest firmware version info from Sony's update server."""

    version: str | None = None
    release_url: str | None = None


class BraviaHttpClient:
    """Client for the Bravia Theatre HTTP management API."""

    # Device details change rarely. Cache results for this many seconds
    # so that multiple sensor updates in the same poll cycle share one
    # HTTP call instead of each making their own.
    DEVICE_DETAILS_CACHE_TTL = 30

    def __init__(self, host: str, session: aiohttp.ClientSession) -> None:
        """Initialize the client."""
        self._host = host
        self._session = session
        self._url = f"http://{host}:{HTTP_API_PORT}{HTTP_API_ENDPOINT}"
        self._timeout = aiohttp.ClientTimeout(total=HTTP_API_TIMEOUT)
        self._device_details_cache: DeviceDetails | None = None
        self._device_details_cache_time: float = 0
        self._reachable = False

    @property
    def reachable(self) -> bool:
        """Return whether the last probe found a listener on :54545."""
        return self._reachable

    async def async_probe_reachable(self) -> bool:
        """
        Probe whether the HTTP management port accepts TCP connections.

        Uses a short connect timeout so gRPC-only models (no :54545 listener)
        fail fast instead of waiting for the full API timeout on every call.
        """
        try:
            _reader, writer = await asyncio.wait_for(
                asyncio.open_connection(self._host, HTTP_API_PORT),
                timeout=HTTP_PROBE_TIMEOUT,
            )
        except (OSError, TimeoutError) as err:
            _LOGGER.debug(
                "HTTP management API unreachable on %s:%s: %s",
                self._host,
                HTTP_API_PORT,
                err,
            )
            self._reachable = False
            return False

        writer.close()
        with suppress(OSError):
            await writer.wait_closed()
        self._reachable = True
        return True

    async def async_get_latest_firmware_info(
        self, model_name: str | None
    ) -> LatestFirmwareInfo:
        """Fetch the latest firmware version from Sony's update server."""
        if model_name is None or model_name not in SONY_MODEL_INFO:
            _LOGGER.debug("No Sony update info mapping for model: %s", model_name)
            return LatestFirmwareInfo()

        model = SONY_MODEL_INFO[model_name]
        url = f"{SONY_UPDATE_INFO_BASE}/{model.am_cid}/{model.am_sid}/info/info.xml"
        release_url = f"{SONY_RELEASE_BASE}/{model.release_id}"

        try:
            async with self._session.get(url, timeout=self._timeout) as resp:
                resp.raise_for_status()
                text = await resp.text()
        except (aiohttp.ClientError, TimeoutError):
            _LOGGER.debug("Failed to fetch update info from Sony")
            return LatestFirmwareInfo()

        return self._parse_update_info_xml(text, release_url)

    @staticmethod
    def _parse_update_info_xml(
        text: str, release_url: str | None = None
    ) -> LatestFirmwareInfo:
        """Parse Sony's update info XML to extract the latest version."""
        # The response has non-XML lines before the declaration; skip them.
        xml_start = text.find("<?xml")
        if xml_start < 0:
            return LatestFirmwareInfo()

        try:
            root = ET.fromstring(text[xml_start:])  # noqa: S314
        except ET.ParseError:
            _LOGGER.debug("Failed to parse Sony update info XML")
            return LatestFirmwareInfo()

        # Find the first Distribution element with a firmware Version.
        dist = root.find(".//Distribution")
        if dist is None:
            return LatestFirmwareInfo()

        version = dist.get("Version")
        if not version:
            return LatestFirmwareInfo()

        _LOGGER.debug("Latest firmware from Sony: %s", version)
        return LatestFirmwareInfo(
            version=version,
            release_url=release_url,
        )

    async def async_get_system_info(self) -> SystemInfo:
        """Fetch system version and model name from the device."""
        payload: dict[str, Any] = {
            "type": "http_get",
            "packet": [["system.version", "system.modelname"]],
        }

        try:
            response = await self._async_post(payload)
        except (aiohttp.ClientError, TimeoutError):
            _LOGGER.debug("Failed to fetch system info from %s", self._host)
            return SystemInfo()

        values = self._extract_get_values(response)
        info = SystemInfo(
            version=values.get("system.version"),
            model_name=values.get("system.modelname"),
        )
        _LOGGER.debug("System info from %s: %s", self._host, info)
        return info

    async def async_get_device_details(self) -> DeviceDetails:
        """
        Fetch device details from the device.

        Results are cached for DEVICE_DETAILS_CACHE_TTL seconds so that
        multiple sensor updates in the same poll cycle share one call.
        """
        now = time.monotonic()
        if (
            self._device_details_cache is not None
            and now - self._device_details_cache_time < self.DEVICE_DETAILS_CACHE_TTL
        ):
            return self._device_details_cache

        payload: dict[str, Any] = {
            "type": "http_get",
            "packet": [
                [
                    "network.devicename",
                    "network.connectiontype",
                    "network.internet",
                    "network.macaddress_wired",
                    "network.macaddress_wireless",
                ],
                ["inet4.ipaddress"],
                ["inet6.ipaddress"],
                ["wlan.strength"],
            ],
        }

        try:
            response = await self._async_post(payload)
        except (aiohttp.ClientError, TimeoutError):
            _LOGGER.debug("Failed to fetch device details from %s", self._host)
            return DeviceDetails()

        values = self._extract_get_values(response)
        info = DeviceDetails(
            device_name=self._filter_error_value(values.get("network.devicename")),
            connection_type=self._filter_error_value(
                values.get("network.connectiontype")
            ),
            internet=self._filter_error_value(values.get("network.internet")),
            ipv4_address=self._filter_error_value(values.get("inet4.ipaddress")),
            ipv6_address=self._filter_error_value(values.get("inet6.ipaddress")),
            wifi_signal=self._filter_error_value(values.get("wlan.strength")),
            mac_wired=self._filter_error_value(values.get("network.macaddress_wired")),
            mac_wireless=self._filter_error_value(
                values.get("network.macaddress_wireless")
            ),
        )
        _LOGGER.debug("Device details from %s: %s", self._host, info)
        self._device_details_cache = info
        self._device_details_cache_time = time.monotonic()
        return info

    async def async_check_firmware_update(self) -> FirmwareUpdateStatus:
        """Check if a firmware update is available."""
        payload: dict[str, Any] = {
            "type": "http_get",
            "packet": [["fw.check_update"]],
        }

        try:
            response = await self._async_post(payload)
        except (aiohttp.ClientError, TimeoutError):
            _LOGGER.debug("Failed to check firmware update on %s", self._host)
            return FirmwareUpdateStatus.ERROR

        values = self._extract_get_values(response)
        value = values.get("fw.check_update")
        if value is None:
            _LOGGER.debug(
                "Unexpected firmware check response from %s: %s",
                self._host,
                response,
            )
            return FirmwareUpdateStatus.ERROR

        if value == "ok":
            _LOGGER.debug("Firmware update available on %s", self._host)
            return FirmwareUpdateStatus.UPDATE_AVAILABLE
        if value == "ng":
            _LOGGER.debug("Firmware up to date on %s", self._host)
            return FirmwareUpdateStatus.UP_TO_DATE
        _LOGGER.debug("Unexpected fw.check_update value from %s: %s", self._host, value)
        return FirmwareUpdateStatus.ERROR

    async def async_request_firmware_update(self) -> bool:
        """Request the device to start a firmware update."""
        payload: dict[str, Any] = {
            "type": "http_set",
            "packet": [
                {"id": 0, "feature": "fw.request_update", "value": ""},
            ],
        }

        try:
            response = await self._async_post(payload)
        except (aiohttp.ClientError, TimeoutError):
            _LOGGER.warning("Failed to request firmware update on %s", self._host)
            return False

        value = self._extract_set_value(response)
        if value is None:
            _LOGGER.warning(
                "Unexpected firmware update response from %s: %s",
                self._host,
                response,
            )
            return False

        if value == "ACK":
            _LOGGER.info("Firmware update triggered on %s", self._host)
            return True

        _LOGGER.warning("Firmware update request rejected by %s: %s", self._host, value)
        return False

    async def _async_post(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Send a POST request and return parsed JSON response."""
        async with self._session.post(
            self._url, json=payload, timeout=self._timeout
        ) as resp:
            resp.raise_for_status()
            return await resp.json(content_type=None)

    @staticmethod
    def _extract_get_values(response: dict[str, Any]) -> dict[str, str]:
        """Extract all feature values from an http_get_result response."""
        result: dict[str, str] = {}
        try:
            if response.get("type") != "http_get_result":
                return result
            for group in response["packet"]:
                for item in group:
                    feature = item.get("feature")
                    value = item.get("value")
                    if feature and value is not None:
                        result[feature] = value
        except (KeyError, IndexError, TypeError):
            pass
        return result

    @staticmethod
    def _filter_error_value(value: str | None) -> str | None:
        """Return None for NAK/ERR error sentinels."""
        if value in (None, "NAK", "ERR"):
            return None
        return value

    @staticmethod
    def _extract_set_value(response: dict[str, Any]) -> str | None:
        """Extract the value from an http_set_result response."""
        try:
            if response.get("type") != "http_set_result":
                return None
            return response["packet"][0]["value"]
        except (KeyError, IndexError, TypeError):
            return None
