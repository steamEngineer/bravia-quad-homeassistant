"""Config flow for Bravia Quad integration."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import TYPE_CHECKING, Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_HOST, CONF_MAC, CONF_NAME
from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.device_registry import format_mac
from homeassistant.helpers.selector import (
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from .bravia_grpc_client import BraviaGrpcClientAsync
from .bravia_quad_client import BraviaQuadClient
from .const import (
    CONF_GRPC_DEBUG,
    CONF_GRPC_DEVICE_ID,
    CONF_GRPC_KEYS,
    CONF_GRPC_OAUTH_REDIRECT,
    CONF_HAS_SUBWOOFER,
    CONF_MANUFACTURER,
    CONF_MODEL,
    CONF_MODEL_ID,
    CONF_SERIAL,
    CONF_TRANSPORT,
    DEFAULT_NAME,
    DOMAIN,
    MODEL_ID_TO_NAME,
    TRANSPORT_GRPC,
    TRANSPORT_TCP,
)
from .external_control import async_ensure_external_control_enabled
from .grpc.credentials import (
    GrpcCredentialsRefreshError,
    GrpcOAuthError,
    async_credentials_from_oauth,
    async_exchange_oauth_redirect,
    async_list_oauth_devices,
    credentials_to_json,
    start_oauth_login,
)
from .transport import identity_from_grpc_snapshot, resolve_transport

if TYPE_CHECKING:
    from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
    }
)

STEP_TRANSPORT_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_TRANSPORT, default=TRANSPORT_GRPC): SelectSelector(
            SelectSelectorConfig(
                options=[TRANSPORT_GRPC, TRANSPORT_TCP],
                translation_key="transport",
                mode=SelectSelectorMode.LIST,
            )
        ),
    }
)

STEP_GRPC_OAUTH_CALLBACK_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_GRPC_OAUTH_REDIRECT): str,
    }
)

STEP_REAUTH_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
    }
)

OPTIONS_SCHEMA_GRPC = vol.Schema(
    {
        vol.Optional(CONF_GRPC_DEBUG, default=False): bool,
    }
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
    client = BraviaQuadClient(host, DEFAULT_NAME)

    try:
        _LOGGER.info("Attempting to connect to Bravia Quad at %s", host)
        await client.async_connect()
        _LOGGER.info("Connection established, testing with power status request")

        await asyncio.sleep(0.2)

        result = await client.async_test_connection()
        _LOGGER.info("Test connection result: %s", result)

        if not result:
            msg = "No response from device. Please verify IP control is enabled."
            raise CannotConnectError(msg)

        _LOGGER.info("Detecting subwoofer presence...")
        has_subwoofer = await client.async_detect_subwoofer()
        _LOGGER.info("Subwoofer detection result: %s", has_subwoofer)

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
        CONF_TRANSPORT: TRANSPORT_TCP,
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


async def validate_grpc_input(host: str, keys_json: str) -> dict[str, Any]:
    """Validate gRPC credentials and fetch device identity via GetStates."""
    try:
        grpc_client = BraviaGrpcClientAsync.from_keys_json(host, keys_json)
    except (ValueError, json.JSONDecodeError) as err:
        msg = "Invalid Sony Seeds keys JSON"
        raise InvalidGrpcKeysError(msg) from err

    try:
        if not await grpc_client.async_connect():
            msg = "gRPC authentication failed. Check Sony Seeds keys."
            raise CannotConnectError(msg)

        await async_ensure_external_control_enabled(host, grpc_client=grpc_client)

        snapshot = await grpc_client.async_get_states_dict()
        if not snapshot:
            snapshot = await grpc_client.async_get_states_app_sequence()
        if not snapshot:
            msg = "GetStates snapshot failed over gRPC"
            raise CannotConnectError(msg)
    except OSError as err:
        msg = f"gRPC connection error: {err}"
        raise CannotConnectError(msg) from err
    finally:
        await grpc_client.async_disconnect()

    info = identity_from_grpc_snapshot(snapshot)
    info[CONF_TRANSPORT] = TRANSPORT_GRPC
    info[CONF_GRPC_KEYS] = keys_json
    return info


class BraviaQuadConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Bravia Quad."""

    VERSION = 1
    MINOR_VERSION = 2

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._discovered_host: str | None = None
        self._discovered_name: str | None = None
        self._discovered_mac: str | None = None
        self._discovered_model: str | None = None
        self._host: str | None = None
        self._setup_info: dict[str, Any] | None = None
        self._transport: str | None = None
        self._oauth_authorize_url: str | None = None
        self._oauth_code_verifier: str | None = None
        self._oauth_state: str | None = None
        self._oauth_token_response: dict[str, Any] | None = None
        self._oauth_devices: list[dict[str, Any]] | None = None
        self._reauth_entry: ConfigEntry | None = None

    def _begin_grpc_oauth(self) -> None:
        """Generate PKCE parameters for a fresh Sony Seeds login."""
        auth_url, code_verifier, state = start_oauth_login()
        self._oauth_authorize_url = auth_url
        self._oauth_code_verifier = code_verifier
        self._oauth_state = state
        self._oauth_token_response = None
        self._oauth_devices = None

    async def _finish_grpc_oauth(
        self,
        redirect_or_code: str,
        *,
        device_id: str | None = None,
    ) -> dict[str, Any]:
        """Exchange OAuth redirect for credentials and validate gRPC connectivity."""
        if (
            self._host is None
            or self._oauth_code_verifier is None
            or self._oauth_state is None
        ):
            msg = "Sony OAuth login was not started"
            raise HomeAssistantError(msg)

        session = async_get_clientsession(self.hass)
        if device_id is not None:
            if self._oauth_token_response is None:
                msg = "Sony OAuth token exchange missing"
                raise HomeAssistantError(msg)
            credentials = await async_credentials_from_oauth(
                session,
                self._oauth_token_response,
                device_id=device_id,
            )
        else:
            token_response = await async_exchange_oauth_redirect(
                session,
                redirect_or_code,
                self._oauth_code_verifier,
                expected_state=self._oauth_state,
            )
            devices = await async_list_oauth_devices(session, token_response)
            if len(devices) > 1:
                self._oauth_token_response = token_response
                self._oauth_devices = devices
                raise GrpcOAuthDeviceSelectionError
            credentials = await async_credentials_from_oauth(
                session, token_response, device_id=devices[0]["device_id"]
            )

        keys_json = credentials_to_json(credentials)
        return await validate_grpc_input(self._host, keys_json)

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step where user enters IP address."""
        if user_input is not None:
            self._host = user_input[CONF_HOST]
            return await self.async_step_transport()

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors={}
        )

    async def async_step_transport(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Choose TCP or gRPC connection method."""
        if self._host is None:
            return await self.async_step_user()

        errors: dict[str, str] = {}

        if user_input is not None:
            self._transport = user_input[CONF_TRANSPORT]
            if self._transport == TRANSPORT_TCP:
                try:
                    self._setup_info = await validate_input(self._host)
                except CannotConnectError:
                    errors["base"] = "cannot_connect"
                except Exception:
                    _LOGGER.exception("Unexpected exception")
                    errors["base"] = "unknown"
                else:
                    return await self.async_step_user_confirm()
            else:
                self._begin_grpc_oauth()
                return await self.async_step_grpc_oauth()

        return self.async_show_form(
            step_id="transport",
            data_schema=STEP_TRANSPORT_SCHEMA,
            errors=errors,
        )

    async def async_step_grpc_oauth(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show Sony Seeds login URL before collecting the OAuth redirect."""
        if self._host is None:
            return await self.async_step_user()

        if self._oauth_authorize_url is None:
            self._begin_grpc_oauth()

        if user_input is not None:
            return await self.async_step_grpc_oauth_callback()

        return self.async_show_form(
            step_id="grpc_oauth",
            data_schema=vol.Schema({}),
            description_placeholders={
                "authorize_url": self._oauth_authorize_url or "",
            },
        )

    async def async_step_grpc_oauth_callback(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Collect OAuth redirect and exchange it for gRPC session keys."""
        if self._host is None or self._oauth_code_verifier is None:
            return await self.async_step_grpc_oauth()

        errors: dict[str, str] = {}

        if user_input is not None:
            redirect = user_input[CONF_GRPC_OAUTH_REDIRECT]
            try:
                self._setup_info = await self._finish_grpc_oauth(redirect)
            except GrpcOAuthDeviceSelectionError:
                return await self.async_step_grpc_oauth_device()
            except GrpcOAuthError:
                errors["base"] = "invalid_oauth_redirect"
            except GrpcCredentialsRefreshError:
                errors["base"] = "oauth_failed"
            except InvalidGrpcKeysError:
                errors["base"] = "invalid_grpc_keys"
            except CannotConnectError:
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected exception during gRPC OAuth")
                errors["base"] = "unknown"
            else:
                if self._reauth_entry is not None:
                    return self._complete_grpc_reauth()
                return await self.async_step_user_confirm()

        return self.async_show_form(
            step_id="grpc_oauth_callback",
            data_schema=STEP_GRPC_OAUTH_CALLBACK_SCHEMA,
            errors=errors,
        )

    async def async_step_grpc_oauth_device(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Choose a Sony IoT device when the account has more than one."""
        if self._oauth_devices is None or self._oauth_token_response is None:
            return await self.async_step_grpc_oauth_callback()

        errors: dict[str, str] = {}
        device_options = {
            device["device_id"]: device.get("name") or device["device_id"]
            for device in self._oauth_devices
        }

        if user_input is not None:
            try:
                self._setup_info = await self._finish_grpc_oauth(
                    "",
                    device_id=user_input[CONF_GRPC_DEVICE_ID],
                )
            except InvalidGrpcKeysError:
                errors["base"] = "invalid_grpc_keys"
            except CannotConnectError:
                errors["base"] = "cannot_connect"
            except GrpcCredentialsRefreshError:
                errors["base"] = "oauth_failed"
            except Exception:
                _LOGGER.exception("Unexpected exception during gRPC device selection")
                errors["base"] = "unknown"
            else:
                if self._reauth_entry is not None:
                    return self._complete_grpc_reauth()
                return await self.async_step_user_confirm()

        return self.async_show_form(
            step_id="grpc_oauth_device",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_GRPC_DEVICE_ID): vol.In(device_options),
                }
            ),
            errors=errors,
        )

    def _complete_grpc_reauth(self) -> ConfigFlowResult:
        """Apply gRPC reauth updates after successful OAuth."""
        reauth_entry = self._reauth_entry
        if reauth_entry is None or self._host is None or self._setup_info is None:
            msg = "Reauth state missing after gRPC OAuth"
            raise HomeAssistantError(msg)

        data_updates: dict[str, Any] = {CONF_HOST: self._host}
        if keys := self._setup_info.get(CONF_GRPC_KEYS):
            data_updates[CONF_GRPC_KEYS] = keys
        return self.async_update_reload_and_abort(
            reauth_entry,
            data_updates=data_updates,
        )

    async def async_step_user_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle user confirmation after successful connection test."""
        if user_input is not None:
            if self._host is None or self._setup_info is None:
                return await self.async_step_user()

            unique_id = self._setup_info.get(CONF_SERIAL, self._host)
            await self.async_set_unique_id(unique_id)
            self._abort_if_unique_id_configured()

            entry_data = {CONF_HOST: self._host, **self._setup_info}
            title = self._setup_info.get(CONF_NAME, DEFAULT_NAME)
            return self.async_create_entry(title=title, data=entry_data)

        return self.async_show_form(
            step_id="user_confirm",
            description_placeholders={"host": self._host or ""},
        )

    async def async_step_zeroconf(
        self, discovery_info: ZeroconfServiceInfo
    ) -> ConfigFlowResult:
        """Handle a flow initialized by zeroconf discovery."""
        _LOGGER.debug("Bravia Quad device found via zeroconf: %s", discovery_info)

        self._discovered_host = discovery_info.host
        self._discovered_name = discovery_info.name.split("._")[0]
        device_id = discovery_info.properties.get("deviceid", "")
        if device_id:
            self._discovered_mac = format_mac(device_id)
        self._discovered_model = discovery_info.properties.get("model")
        self._host = self._discovered_host

        for entry in self._async_current_entries():
            if entry.unique_id in (
                self._discovered_host,
                self._discovered_mac,
            ):
                await self.async_set_unique_id(entry.unique_id)
                self._abort_if_unique_id_configured(
                    updates={CONF_HOST: self._discovered_host}
                )
                return self.async_abort(reason="already_configured")
            if entry.data.get(CONF_SERIAL) and entry.unique_id == entry.data.get(
                CONF_SERIAL
            ):
                await self.async_set_unique_id(entry.unique_id)
                self._abort_if_unique_id_configured(
                    updates={CONF_HOST: self._discovered_host}
                )
                return self.async_abort(reason="already_configured")

        unique_id = self._discovered_mac or self._discovered_host
        await self.async_set_unique_id(unique_id)
        self._abort_if_unique_id_configured(updates={CONF_HOST: self._discovered_host})

        self.context["title_placeholders"] = {"name": self._discovered_name}
        return await self.async_step_zeroconf_confirm()

    async def async_step_zeroconf_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle user confirmation of discovered device."""
        if user_input is not None:
            return await self.async_step_transport()

        return self.async_show_form(
            step_id="zeroconf_confirm",
            description_placeholders={"name": self._discovered_name or DEFAULT_NAME},
            errors={},
        )

    async def async_step_reauth(self, _entry_data: dict[str, Any]) -> ConfigFlowResult:
        """Handle re-authentication when the device becomes unreachable."""
        self._reauth_entry = self._get_reauth_entry()
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle user input for re-authentication."""
        errors: dict[str, str] = {}
        reauth_entry = self._reauth_entry or self._get_reauth_entry()
        is_grpc = resolve_transport(reauth_entry) == TRANSPORT_GRPC

        if user_input is not None:
            self._host = user_input[CONF_HOST]
            if is_grpc:
                self._begin_grpc_oauth()
                return await self.async_step_grpc_oauth()

            try:
                await validate_connection(self._host)
            except CannotConnectError:
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected exception during reauth")
                errors["base"] = "unknown"
            else:
                return self.async_update_reload_and_abort(
                    reauth_entry,
                    data_updates={CONF_HOST: self._host},
                )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=self.add_suggested_values_to_schema(
                STEP_REAUTH_SCHEMA,
                {CONF_HOST: reauth_entry.data.get(CONF_HOST)},
            ),
            description_placeholders={"name": reauth_entry.title},
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: ConfigEntry,
    ) -> BraviaQuadOptionsFlowHandler:
        """Return options flow handler."""
        return BraviaQuadOptionsFlowHandler(config_entry)


class BraviaQuadOptionsFlowHandler(OptionsFlow):
    """Handle gRPC debug option for gRPC transport entries."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Initialize options flow."""
        self._entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage gRPC debug logging (gRPC transport only)."""
        if resolve_transport(self._entry) != TRANSPORT_GRPC:
            return self.async_abort(reason="not_grpc_transport")

        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        options = self._entry.options
        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(
                OPTIONS_SCHEMA_GRPC,
                {
                    CONF_GRPC_DEBUG: options.get(CONF_GRPC_DEBUG, False),
                },
            ),
        )


class CannotConnectError(HomeAssistantError):
    """Error to indicate we cannot connect."""


class GrpcOAuthDeviceSelectionError(HomeAssistantError):
    """Error to indicate the user must pick a Sony IoT device."""


class InvalidGrpcKeysError(HomeAssistantError):
    """Error to indicate Sony Seeds keys JSON is invalid."""
