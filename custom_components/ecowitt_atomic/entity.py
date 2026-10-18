"""Shared HA entity and gateway device metadata."""

from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_BASE_URL, DOMAIN
from .coordinator import GatewayCoordinator
from .data import AtomicConfigEntry


class GatewayEntity(CoordinatorEntity[GatewayCoordinator]):
    """An entity belonging to the gateway's device."""

    _attr_has_entity_name = True

    def __init__(self, entry: AtomicConfigEntry) -> None:
        super().__init__(entry.runtime_data.coordinator)
        base_url = entry.data[CONF_BASE_URL]
        info = entry.runtime_data.info
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, info.mac)},
            connections={(CONNECTION_NETWORK_MAC, info.mac)},
            manufacturer="Ecowitt",
            model=info.model,
            sw_version=info.firmware,
            name=info.name,
            configuration_url=base_url,
        )
