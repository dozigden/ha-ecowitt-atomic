"""Ecowitt Atomic configuration flow."""

from collections.abc import Mapping
from typing import Literal

import probatio

from homeassistant.config_entries import (
    SOURCE_RECONFIGURE,
    ConfigFlow,
    ConfigFlowResult,
)
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import (
    EcowittApiClient,
    GatewayError,
    UnsupportedGatewayError,
    normalize_base_url,
)
from .const import CONF_BASE_URL, DOMAIN
from .data import GatewayConfigData
from .gateway import async_get_gateway_info, async_read_gateway


class AtomicConfigFlow(ConfigFlow, domain=DOMAIN):
    """Use the gateway MAC as the config-entry identity."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, object] | None = None
    ) -> ConfigFlowResult:
        """Connect a gateway."""
        return await self._async_gateway_step("user", user_input)

    async def async_step_reconfigure(
        self, user_input: dict[str, object] | None = None
    ) -> ConfigFlowResult:
        """Reject a different gateway at the new address."""
        return await self._async_gateway_step("reconfigure", user_input)

    async def _async_gateway_step(
        self,
        step_id: Literal["user", "reconfigure"],
        user_input: Mapping[str, object] | None,
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                base_url = normalize_base_url(user_input.get(CONF_BASE_URL))
            except ValueError, UnicodeError:
                errors[CONF_BASE_URL] = "invalid_url"
            else:
                client = EcowittApiClient(base_url, async_get_clientsession(self.hass))
                try:
                    info = await async_get_gateway_info(client)
                    await self.async_set_unique_id(info.mac)
                    if self.source == SOURCE_RECONFIGURE:
                        self._abort_if_unique_id_mismatch(reason="wrong_gateway")
                    else:
                        self._abort_if_unique_id_configured()
                    if not (await async_read_gateway(client)).gateway:
                        errors["base"] = "no_readings"
                except UnsupportedGatewayError:
                    errors["base"] = "unsupported_gateway"
                except GatewayError:
                    errors["base"] = "cannot_connect"
                if not errors:
                    data = GatewayConfigData(base_url=base_url, mac=info.mac)
                    if self.source == SOURCE_RECONFIGURE:
                        return self.async_update_reload_and_abort(
                            self._get_reconfigure_entry(),
                            data_updates=data,
                        )
                    return self.async_create_entry(
                        title=info.name,
                        data=data,
                    )
        return self.async_show_form(
            step_id=step_id,
            data_schema=probatio.Schema({probatio.Required(CONF_BASE_URL): str}),
            errors=errors,
        )
