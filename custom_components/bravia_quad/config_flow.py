"""Config flow for Bravia Quad integration."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_HOST, CONF_MAC, CONF_NAME
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import format_mac

from .bravia_quad_client import BraviaQuadClient
from .const import (
    CONF_HAS_SUBWOOFER,
    CONF_MANUFACTURER,
    CONF_MODEL,
    CONF_MODEL_ID,
    CONF_SERIAL,
    DEFAULT_NAME,
    DOMAIN,
    MODEL_ID_TO_NAME,
)

if TYPE_CHECKING:
    from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
    }
)


class CannotConnectError(HomeAssistantError):
    """Error to indicate we cannot connect."""


def _discovery_matches_entry(
    entry: ConfigEntry,
    discovered_host: str | None,
    discovered_mac: str | None,
) -> bool:
    """Return True if zeroconf discovery belongs to this config entry."""
    unique_id = entry.unique_id
    if unique_id is None:
        return False

    if discovered_host and unique_id == discovered_host:
        return True

    if discovered_mac and unique_id == discovered_mac:
        return True

    stored_serial = entry.data.get(CONF_SERIAL)
    # ponytail: manual setup may store TCP active MAC instead of AirPlay WiFi MAC;
    # host updates for those entries use the reauth flow instead.
    return bool(
        stored_serial
        and unique_id == stored_serial
        and discovered_mac
        and entry.data.get(CONF_MAC) == discovered_mac
    )


async def validate_connection(host: str) -> None:
    """
    Validate we can connect to the device (without subwoofer detection).

    Used for reauth flow where we only need to verify connectivity.
    """
    client = BraviaQuadClient(host, DEFAULT_NAME)

    try:
        _LOGGER.debug("Validating connection to Bravia Quad at %s", host)
        await client.async_connect()
        await asyncio.sleep(0.2)

        result = await client.async_test_connection()
        if not result:
            msg = "No response from device. Please verify IP control is enabled."
            raise CannotConnectError(msg)

    except (OSError, TimeoutError) as err:
        _LOGGER.exception("Connection error")
        msg = f"Error connecting to device: {err}"
        raise CannotConnectError(msg) from err
    finally:
        await client.async_disconnect()


async def validate_input(host: str) -> dict[str, Any]:
    """
    Validate the user input allows us to connect and detect subwoofer.

    Used for initial setup where we need full device detection.
    """
    # Create a temporary client to test connection
    client = BraviaQuadClient(host, DEFAULT_NAME)

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

        # Fetch permanent device identity
        serial = await client.async_get_serial_number()
        model_type = await client.async_get_model_type()
        manufacturer = await client.async_get_manufacturer()
        mac = await client.async_get_mac_address()
        device_name = await client.async_get_device_name()

    except (OSError, TimeoutError) as err:
        _LOGGER.exception("Connection error")
        msg = f"Error connecting to device: {err}"
        raise CannotConnectError(msg) from err
    finally:
        await client.async_disconnect()

    result: dict[str, Any] = {
        CONF_HAS_SUBWOOFER: has_subwoofer,
    }
    if serial:
        result[CONF_SERIAL] = serial
    if model_type:
        result[CONF_MODEL_ID] = model_type
        result[CONF_MODEL] = MODEL_ID_TO_NAME.get(model_type, model_type)
    if manufacturer:
        result[CONF_MANUFACTURER] = manufacturer
    if mac:
        result[CONF_MAC] = format_mac(mac)
    if device_name:
        result[CONF_NAME] = device_name
    return result


class BraviaQuadConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Bravia Quad."""

    VERSION = 1
    MINOR_VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._discovered_host: str | None = None
        self._discovered_name: str | None = None
        self._discovered_mac: str | None = None
        self._discovered_model: str | None = None
        self._user_host: str | None = None
        self._user_info: dict[str, Any] | None = None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step where user enters IP address."""
        errors: dict[str, str] = {}

        if user_input is not None:
            host = user_input[CONF_HOST]
            self._user_host = host
            try:
                info = await validate_input(host)
            except CannotConnectError:
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                # Store result and proceed to confirmation step
                self._user_info = info
                return await self.async_step_user_confirm()

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
        )

    async def async_step_user_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle user confirmation after successful connection test."""
        if user_input is not None:
            if (host := self._user_host) is None or self._user_info is None:
                # Session lost, restart the flow
                return await self.async_step_user()

            # Use serial number as unique_id (stable across IP/MAC changes)
            unique_id = self._user_info.get(CONF_SERIAL, host)
            await self.async_set_unique_id(unique_id)
            self._abort_if_unique_id_configured()

            entry_data = {CONF_HOST: host, **self._user_info}
            title = self._user_info.get(CONF_NAME, DEFAULT_NAME)
            return self.async_create_entry(title=title, data=entry_data)

        return self.async_show_form(
            step_id="user_confirm",
            description_placeholders={"host": self._user_host or ""},
        )

    async def async_step_zeroconf(
        self, discovery_info: ZeroconfServiceInfo
    ) -> ConfigFlowResult:
        """Handle a flow initialized by zeroconf discovery."""
        _LOGGER.debug("Bravia Quad device found via zeroconf: %s", discovery_info)

        # Get device information from AirPlay properties
        self._discovered_host = discovery_info.host
        self._discovered_name = discovery_info.name.split("._")[
            0
        ]  # Clean up service name
        device_id = discovery_info.properties.get("deviceid", "")
        if device_id:
            self._discovered_mac = format_mac(device_id)
        # Capture model from Zeroconf properties (e.g., "Bravia Theatre Quad")
        self._discovered_model = discovery_info.properties.get("model")

        # Check if there's an existing entry for this device.
        for entry in self._async_current_entries():
            if _discovery_matches_entry(
                entry, self._discovered_host, self._discovered_mac
            ):
                await self.async_set_unique_id(entry.unique_id)
                self._abort_if_unique_id_configured(
                    updates={CONF_HOST: self._discovered_host}
                )
                return self.async_abort(reason="already_configured")

        # No existing entry found; use MAC temporarily until we get serial
        unique_id = self._discovered_mac or self._discovered_host
        await self.async_set_unique_id(unique_id)
        self._abort_if_unique_id_configured(updates={CONF_HOST: self._discovered_host})

        self.context["title_placeholders"] = {"name": self._discovered_name}
        return await self.async_step_zeroconf_confirm()

    async def async_step_zeroconf_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle user confirmation of discovered device."""
        errors: dict[str, str] = {}

        if user_input is not None:
            if (host := self._discovered_host) is None:
                return self.async_abort(reason="unknown")
            try:
                info = await validate_input(host)
            except CannotConnectError:
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected exception during zeroconf confirmation")
                errors["base"] = "unknown"
            else:
                entry_data = {CONF_HOST: host, **info}
                # Zeroconf provides WiFi MAC and model; merge with TCP data
                if self._discovered_mac:
                    entry_data[CONF_MAC] = self._discovered_mac
                if self._discovered_model:
                    entry_data[CONF_MODEL] = self._discovered_model

                # Migrate unique_id to serial if available
                if CONF_SERIAL in info:
                    await self.async_set_unique_id(info[CONF_SERIAL])

                title = self._discovered_name or info.get(CONF_NAME, DEFAULT_NAME)
                return self.async_create_entry(title=title, data=entry_data)

        return self.async_show_form(
            step_id="zeroconf_confirm",
            description_placeholders={"name": self._discovered_name or DEFAULT_NAME},
            errors=errors,
        )

    async def async_step_reauth(self, _entry_data: dict[str, Any]) -> ConfigFlowResult:
        """Handle re-authentication when the device becomes unreachable."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle user input for re-authentication."""
        errors: dict[str, str] = {}
        reauth_entry = self._get_reauth_entry()

        if user_input is not None:
            new_host = user_input[CONF_HOST]
            try:
                await validate_connection(new_host)
            except CannotConnectError:
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected exception during reauth")
                errors["base"] = "unknown"
            else:
                # Update the config entry with the new host
                return self.async_update_reload_and_abort(
                    reauth_entry,
                    data_updates={CONF_HOST: new_host},
                )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_HOST, default=reauth_entry.data.get(CONF_HOST)
                    ): str,
                }
            ),
            description_placeholders={"name": reauth_entry.title},
            errors=errors,
        )
