"""UI configuration for Ecowitt Atomic."""

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    SOURCE_RECONFIGURE,
    ConfigFlow,
    ConfigFlowResult,
)
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import EcowittApiClient, GatewayError, UnsupportedGateway, normalize_base_url
from .const import CONF_BASE_URL, CONF_MAC, DOMAIN


class AtomicConfigFlow(ConfigFlow, domain=DOMAIN):
    """Identify a gateway by MAC, keeping its base URL as connection data."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        return await self._async_gateway_step("user", user_input)

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Change the address only after confirming the same hardware MAC."""
        return await self._async_gateway_step("reconfigure", user_input)

    async def _async_gateway_step(
        self, step_id: str, user_input: dict[str, Any] | None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                base_url = normalize_base_url(user_input[CONF_BASE_URL])
            except ValueError, UnicodeError:
                errors[CONF_BASE_URL] = "invalid_url"
            else:
                client = EcowittApiClient(base_url, async_get_clientsession(self.hass))
                try:
                    info = await client.async_get_info()
                    await self.async_set_unique_id(info.mac)
                    if self.source == SOURCE_RECONFIGURE:
                        self._abort_if_unique_id_mismatch(reason="wrong_gateway")
                    else:
                        self._abort_if_unique_id_configured()
                    if not await client.async_get_readings():
                        errors["base"] = "no_readings"
                except UnsupportedGateway:
                    errors["base"] = "unsupported_gateway"
                except GatewayError:
                    errors["base"] = "cannot_connect"
                if not errors:
                    if self.source == SOURCE_RECONFIGURE:
                        return self.async_update_reload_and_abort(
                            self._get_reconfigure_entry(),
                            data_updates={CONF_BASE_URL: base_url, CONF_MAC: info.mac},
                        )
                    return self.async_create_entry(
                        title=info.name,
                        data={CONF_BASE_URL: base_url, CONF_MAC: info.mac},
                    )
        return self.async_show_form(
            step_id=step_id,
            data_schema=vol.Schema({vol.Required(CONF_BASE_URL): str}),
            errors=errors,
        )
