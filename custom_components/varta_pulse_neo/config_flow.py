"""Config flow for the VARTA pulse neo integration."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import (
    CONF_HOST,
    CONF_PASSWORD,
    CONF_PORT,
    CONF_SCAN_INTERVAL,
    CONF_USERNAME,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.selector import (
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .api import VartaClient, VartaConnectionError, VartaDeviceInfo, VartaError
from .const import (
    CONF_UNIT_ID,
    CONF_WEB_HTTPS,
    DEFAULT_NAME,
    DEFAULT_PORT,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_UNIT_ID,
    DEFAULT_WEB_USERNAME,
    DOMAIN,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
)
from .web import (
    VartaWebAuthError,
    VartaWebError,
    VartaWebLockedError,
    create_web_client,
)

PASSWORD_SELECTOR = TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD))


def _user_schema(defaults: dict[str, Any]) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(CONF_HOST, default=defaults.get(CONF_HOST, "")): str,
            vol.Required(
                CONF_PORT, default=defaults.get(CONF_PORT, DEFAULT_PORT)
            ): vol.All(vol.Coerce(int), vol.Range(min=1, max=65535)),
            vol.Required(
                CONF_UNIT_ID, default=defaults.get(CONF_UNIT_ID, DEFAULT_UNIT_ID)
            ): vol.All(vol.Coerce(int), vol.Range(min=0, max=255)),
            vol.Optional(
                CONF_USERNAME,
                default=defaults.get(CONF_USERNAME, DEFAULT_WEB_USERNAME),
            ): str,
            vol.Optional(
                CONF_PASSWORD, default=defaults.get(CONF_PASSWORD, "")
            ): PASSWORD_SELECTOR,
            vol.Optional(
                CONF_WEB_HTTPS, default=defaults.get(CONF_WEB_HTTPS, False)
            ): bool,
        }
    )


async def _probe_web(hass: HomeAssistant, data: dict[str, Any]) -> None:
    """Check the web interface login if a password was entered."""
    if not data.get(CONF_PASSWORD):
        return
    client = create_web_client(hass, data)
    try:
        await client.get_data()
    finally:
        await client.close()


def _web_error(err: VartaWebError) -> str:
    if isinstance(err, VartaWebLockedError):
        return "account_locked"
    if isinstance(err, VartaWebAuthError):
        return "invalid_auth"
    return "web_cannot_connect"


async def _probe(data: dict[str, Any]) -> VartaDeviceInfo:
    client = VartaClient(data[CONF_HOST], data[CONF_PORT], data[CONF_UNIT_ID])
    try:
        info = await client.read_device_info()
        await client.read_data()
    finally:
        await client.close()
    return info


class VartaConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for VARTA pulse neo."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for host, port and unit id."""
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                info = await _probe(user_input)
            except VartaConnectionError:
                errors["base"] = "cannot_connect"
            except VartaError:
                errors["base"] = "modbus_error"
            else:
                await self.async_set_unique_id(info.serial or user_input[CONF_HOST])
                self._abort_if_unique_id_configured(updates=user_input)
                try:
                    await _probe_web(self.hass, user_input)
                except VartaWebError as err:
                    errors["base"] = _web_error(err)
                else:
                    return self.async_create_entry(title=DEFAULT_NAME, data=user_input)

        return self.async_show_form(
            step_id="user",
            data_schema=_user_schema(user_input or {}),
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Change host, port or unit id of an existing entry."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                info = await _probe(user_input)
            except VartaConnectionError:
                errors["base"] = "cannot_connect"
            except VartaError:
                errors["base"] = "modbus_error"
            else:
                await self.async_set_unique_id(info.serial or user_input[CONF_HOST])
                self._abort_if_unique_id_mismatch(reason="wrong_device")
                try:
                    await _probe_web(self.hass, user_input)
                except VartaWebError as err:
                    errors["base"] = _web_error(err)
                else:
                    return self.async_update_reload_and_abort(
                        entry, data_updates=user_input
                    )

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=_user_schema(user_input or dict(entry.data)),
            errors=errors,
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """The web interface rejected the stored credentials."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for new web interface credentials."""
        entry = self._get_reauth_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            data = {**entry.data, **user_input}
            try:
                await _probe_web(self.hass, data)
            except VartaWebError as err:
                errors["base"] = _web_error(err)
            else:
                return self.async_update_reload_and_abort(
                    entry, data_updates=user_input
                )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_USERNAME,
                        default=entry.data.get(CONF_USERNAME, DEFAULT_WEB_USERNAME),
                    ): str,
                    vol.Required(CONF_PASSWORD): PASSWORD_SELECTOR,
                }
            ),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Return the options flow."""
        return VartaOptionsFlow()


class VartaOptionsFlow(OptionsFlow):
    """Options: polling interval."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_SCAN_INTERVAL,
                        default=self.config_entry.options.get(
                            CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
                        ),
                    ): vol.All(
                        vol.Coerce(int),
                        vol.Range(min=MIN_SCAN_INTERVAL, max=MAX_SCAN_INTERVAL),
                    ),
                }
            ),
        )
