"""Config flow for Bravia Quad integration."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.exceptions import HomeAssistantError

from .const import DOMAIN
from .bravia_quad_client import BraviaQuadClient

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Optional(CONF_NAME, default="Bravia Quad"): str,
    }
)


async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    """Validate the user input allows us to connect."""
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
        
        await client.async_disconnect()
        
        if not result:
            raise CannotConnect("No response from device. Please verify IP control is enabled.")
        
        return {"title": data.get(CONF_NAME, "Bravia Quad")}
    except Exception as err:
        if isinstance(err, CannotConnect):
            raise
        _LOGGER.exception("Unexpected exception: %s", err)
        raise CannotConnect(f"Error connecting to device: {err}") from err


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Bravia Quad."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}
        
        if user_input is not None:
            try:
                info = await validate_input(self.hass, user_input)
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                await self.async_set_unique_id(user_input[CONF_HOST])
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title=info["title"], data=user_input)

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
        )


class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""

