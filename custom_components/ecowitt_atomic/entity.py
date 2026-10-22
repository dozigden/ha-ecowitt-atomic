"""Shared gateway entity behaviour."""

from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import GatewayCoordinator
from .data import AtomicConfigEntry
from .devices import gateway_device_info


class GatewayEntity(CoordinatorEntity[GatewayCoordinator]):
    """Entity belonging to the gateway device."""

    _attr_has_entity_name = True

    def __init__(self, entry: AtomicConfigEntry) -> None:
        """Attach gateway metadata and the coordinator."""
        super().__init__(entry.runtime_data.coordinator)
        self._attr_device_info = gateway_device_info(entry)
