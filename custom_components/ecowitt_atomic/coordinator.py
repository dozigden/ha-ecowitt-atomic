"""Gateway polling."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import EcowittApiClient, GatewayError
from .const import DOMAIN, LOGGER, POLL_INTERVAL
from .gateway import async_read_gateway
from .models import GatewayReadings

if TYPE_CHECKING:
    from .data import AtomicConfigEntry


class GatewayCoordinator(DataUpdateCoordinator[GatewayReadings]):
    """Polling shared by one gateway's entities."""

    def __init__(
        self, hass: HomeAssistant, entry: AtomicConfigEntry, client: EcowittApiClient
    ) -> None:
        """Poll the gateway every 30 seconds."""
        super().__init__(
            hass,
            LOGGER,
            name=DOMAIN,
            config_entry=entry,
            update_interval=POLL_INTERVAL,
        )
        self.client = client

    async def _async_update_data(self) -> GatewayReadings:
        try:
            return await async_read_gateway(self.client)
        except GatewayError as err:
            raise UpdateFailed(str(err)) from err
