"""Config flow for Bravia Quad integration."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_HOST, CONF_MAC, CONF_NAME
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import format_mac

from .bravia_quad_client import BraviaQuadClient

if TYPE_CHECKING:
    from homeassistant.helpers.service_info.dhcp import DhcpServiceInfo
    from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo

from .const import CONF_HAS_SUBWOOFER, DOMAIN

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Optional(CONF_NAME, default="Bravia Quad"): str,
    }
)


async def validate_input(data: dict[str, Any]) -> dict[str, Any]:
    """Validate the user input allows us to connect and detect subwoofer."""
    host = data[CONF_HOST]

    # Create a temporary client to test connection
    client = BraviaQuadClient(host, data.get(CONF_NAME, "Bravia Quad"))

    try:
        _LOGGER.info("Attempting to connect to Bravia Quad at %s", host)
        await client.async_connect()
        _LOGGER.info("Connection established, testing with power status request")

        # Give connection a moment to stabilize
        await asyncio.sleep(0.2)

        result = await client.async_test_connection()
        _LOGGER.info("Test connection result: %s", result)

        if not result:
            msg = "No response from device. Please verify IP control is enabled."
            raise CannotConnectError(msg)

        # Detect subwoofer presence
        _LOGGER.info("Detecting subwoofer presence...")
        has_subwoofer = await client.async_detect_subwoofer()
        _LOGGER.info("Subwoofer detection result: %s", has_subwoofer)

    except (OSError, TimeoutError) as err:
        _LOGGER.exception("Connection error")
        msg = f"Error connecting to device: {err}"
        raise CannotConnectError(msg) from err
    finally:
        await client.async_disconnect()

    return {
        "title": data.get(CONF_NAME, "Bravia Quad"),
        CONF_HAS_SUBWOOFER: has_subwoofer,
    }


class BraviaQuadConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Bravia Quad."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._discovered_host: str | None = None
        self._discovered_name: str | None = None
        self._discovered_mac: str | None = None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                info = await validate_input(user_input)
            except CannotConnectError:
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                await self.async_set_unique_id(user_input[CONF_HOST])
                self._abort_if_unique_id_configured()
                # Add subwoofer detection result to entry data
                entry_data = {
                    **user_input,
                    CONF_HAS_SUBWOOFER: info[CONF_HAS_SUBWOOFER],
                }
                return self.async_create_entry(title=info["title"], data=entry_data)

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
        )

    async def async_step_zeroconf(
        self, discovery_info: ZeroconfServiceInfo
    ) -> ConfigFlowResult:
        """Handle a flow initialized by zeroconf discovery."""
        _LOGGER.debug("Bravia Quad device found via zeroconf: %s", discovery_info)

        # Check if this is a Bravia Theatre Quad device
        model = discovery_info.properties.get("model", "")
        if "bravia" not in model.lower():
            return self.async_abort(reason="not_bravia_quad")

        # Get device information from AirPlay properties
        self._discovered_host = discovery_info.host
        self._discovered_name = discovery_info.name.split("._")[
            0
        ]  # Clean up service name
        device_id = discovery_info.properties.get("deviceid", "")
        if device_id:
            self._discovered_mac = format_mac(device_id)

        # Check if there's an existing entry configured with IP as unique_id
        # If so, migrate it to use MAC as unique_id
        if self._discovered_mac:
            for entry in self._async_current_entries():
                if entry.unique_id == self._discovered_host:
                    # Migrate from IP-based to MAC-based unique_id
                    self.hass.config_entries.async_update_entry(
                        entry,
                        unique_id=self._discovered_mac,
                        data={**entry.data, CONF_MAC: self._discovered_mac},
                    )
                    return self.async_abort(reason="already_configured")

        # Use MAC address as unique ID if available, otherwise use host
        unique_id = self._discovered_mac or self._discovered_host
        await self.async_set_unique_id(unique_id)
        self._abort_if_unique_id_configured(updates={CONF_HOST: self._discovered_host})

        self.context["title_placeholders"] = {"name": self._discovered_name}
        return await self.async_step_zeroconf_confirm()

    async def async_step_dhcp(
        self, discovery_info: DhcpServiceInfo
    ) -> ConfigFlowResult:
        """Handle a flow initialized by DHCP discovery."""
        _LOGGER.debug("Bravia Quad device found via DHCP: %s", discovery_info)

        self._discovered_host = discovery_info.ip
        self._discovered_mac = format_mac(discovery_info.macaddress)
        self._discovered_name = discovery_info.hostname or "Bravia Quad"

        # Check if there's an existing entry configured with IP as unique_id
        # If so, migrate it to use MAC as unique_id
        for entry in self._async_current_entries():
            if entry.unique_id == self._discovered_host:
                # Migrate from IP-based to MAC-based unique_id
                self.hass.config_entries.async_update_entry(
                    entry,
                    unique_id=self._discovered_mac,
                    data={**entry.data, CONF_MAC: self._discovered_mac},
                )
                return self.async_abort(reason="already_configured")

        # Use MAC address as unique ID
        await self.async_set_unique_id(self._discovered_mac)
        self._abort_if_unique_id_configured(updates={CONF_HOST: self._discovered_host})

        # Test if this is actually a Bravia Quad by trying to connect
        try:
            client = BraviaQuadClient(self._discovered_host, self._discovered_name)
            await client.async_connect()
            result = await client.async_test_connection()
            await client.async_disconnect()
            if not result:
                return self.async_abort(reason="not_bravia_quad")
        except (OSError, TimeoutError):
            return self.async_abort(reason="cannot_connect")

        self.context["title_placeholders"] = {"name": self._discovered_name}
        return await self.async_step_dhcp_confirm()

    async def async_step_dhcp_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle user confirmation of DHCP discovered device."""
        errors: dict[str, str] = {}

        if user_input is not None:
            data = {
                CONF_HOST: self._discovered_host,
                CONF_NAME: self._discovered_name,
            }
            try:
                info = await validate_input(data)
            except CannotConnectError:
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected exception during DHCP confirmation")
                errors["base"] = "unknown"
            else:
                entry_data = {
                    CONF_HOST: self._discovered_host,
                    CONF_NAME: self._discovered_name,
                    CONF_MAC: self._discovered_mac,
                    CONF_HAS_SUBWOOFER: info[CONF_HAS_SUBWOOFER],
                }
                return self.async_create_entry(
                    title=self._discovered_name or "Bravia Quad",
                    data=entry_data,
                )

        return self.async_show_form(
            step_id="dhcp_confirm",
            description_placeholders={"name": self._discovered_name or "Bravia Quad"},
            errors=errors,
        )

    async def async_step_zeroconf_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle user confirmation of discovered device."""
        errors: dict[str, str] = {}

        if user_input is not None:
            # Test connection to the discovered device
            data = {
                CONF_HOST: self._discovered_host,
                CONF_NAME: self._discovered_name,
            }
            try:
                info = await validate_input(data)
            except CannotConnectError:
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected exception during zeroconf confirmation")
                errors["base"] = "unknown"
            else:
                entry_data = {
                    CONF_HOST: self._discovered_host,
                    CONF_NAME: self._discovered_name,
                    CONF_HAS_SUBWOOFER: info[CONF_HAS_SUBWOOFER],
                }
                if self._discovered_mac:
                    entry_data[CONF_MAC] = self._discovered_mac
                return self.async_create_entry(
                    title=self._discovered_name or "Bravia Quad",
                    data=entry_data,
                )

        return self.async_show_form(
            step_id="zeroconf_confirm",
            description_placeholders={"name": self._discovered_name or "Bravia Quad"},
            errors=errors,
        )


class CannotConnectError(HomeAssistantError):
    """Error to indicate we cannot connect."""
