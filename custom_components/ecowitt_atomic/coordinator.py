"""One polling coordinator per gateway."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import EcowittApiClient, GatewayError
from .const import DOMAIN, LOGGER, POLL_INTERVAL
from .models import Reading

if TYPE_CHECKING:
    from .data import AtomicConfigEntry


class GatewayCoordinator(DataUpdateCoordinator[dict[str, Reading]]):
    """Share the latest gateway readings and polling status with its entities."""

    def __init__(
        self, hass: HomeAssistant, entry: AtomicConfigEntry, client: EcowittApiClient
    ) -> None:
        super().__init__(
            hass,
            LOGGER,
            name=DOMAIN,
            config_entry=entry,
            update_interval=POLL_INTERVAL,
        )
        self.client = client

    async def _async_update_data(self) -> dict[str, Reading]:
        try:
            return await self.client.async_get_readings()
        except GatewayError as err:
            raise UpdateFailed(str(err)) from err
