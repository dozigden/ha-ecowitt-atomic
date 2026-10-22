"""Gateway and discovered sensor entities."""

from homeassistant.components.sensor import (
    SensorEntity,
    SensorEntityDescription,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .capabilities import (
    GATEWAY_OBSERVATION_DESCRIPTIONS,
    GATEWAY_SENSOR_DESCRIPTIONS,
    SENSOR_DESCRIPTIONS,
)
from .const import DOMAIN
from .coordinator import GatewayCoordinator
from .data import AtomicConfigEntry
from .devices import ecowitt_device_info, gateway_device_info
from .entity import GatewayEntity

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: AtomicConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Restore registered entities and discover mapped capabilities."""
    device_registry = dr.async_get(hass)
    gateway = device_registry.async_get_or_create(
        config_entry_id=entry.entry_id, **gateway_device_info(entry)
    )
    async_add_entities(
        GatewaySensor(entry, description) for description in GATEWAY_SENSOR_DESCRIPTIONS
    )
    registry = er.async_get(hass)
    mac = entry.runtime_data.info.mac
    restored: set[tuple[int, str]] = set()
    restored_gateway: set[str] = set()
    for registered in er.async_entries_for_config_entry(registry, entry.entry_id):
        if registered.domain != "sensor" or registered.platform != DOMAIN:
            continue
        parts = registered.unique_id.split("::")
        if (
            len(parts) == 2
            and parts[0] == mac
            and parts[1] in GATEWAY_OBSERVATION_DESCRIPTIONS
        ):
            restored_gateway.add(parts[1])
        if (
            len(parts) == 3
            and parts[0] == mac
            and parts[1].isascii()
            and parts[1].isdecimal()
            and parts[2] in SENSOR_DESCRIPTIONS
        ):
            restored.add((int(parts[1]), parts[2]))

    added: set[tuple[int, str]] = set()
    added_gateway: set[str] = set()

    @callback
    def discover() -> None:
        coordinator = entry.runtime_data.coordinator
        if not coordinator.last_update_success:
            return
        gateway_keys = restored_gateway | (
            coordinator.data.gateway.keys() & GATEWAY_OBSERVATION_DESCRIPTIONS.keys()
        )
        new_gateway_keys = gateway_keys - added_gateway
        added_gateway.update(new_gateway_keys)
        async_add_entities(
            GatewaySensor(entry, GATEWAY_OBSERVATION_DESCRIPTIONS[key])
            for key in sorted(new_gateway_keys)
        )
        discovered = set(restored)
        for slot, ecowitt_sensor in coordinator.data.ecowitt_sensors.items():
            discovered.update(
                (slot, key)
                for key in ecowitt_sensor.readings
                if key in SENSOR_DESCRIPTIONS
            )
        new_entities = discovered - added
        added.update(new_entities)
        async_add_entities(
            EcowittSensor(
                entry, slot, SENSOR_DESCRIPTIONS[key], gateway.id, device_registry
            )
            for slot, key in sorted(new_entities)
        )

    entry.async_on_unload(entry.runtime_data.coordinator.async_add_listener(discover))
    discover()


class GatewaySensor(GatewayEntity, SensorEntity):
    """Sensor for an internal reading or shared gateway observation."""

    def __init__(
        self, entry: AtomicConfigEntry, description: SensorEntityDescription
    ) -> None:
        """Bind the reading description and unique ID."""
        super().__init__(entry)
        self.entity_description = description
        self._attr_unique_id = f"{entry.runtime_data.info.mac}::{description.key}"

    @property
    def native_value(self) -> float | None:
        """Return None when the reading is missing."""
        reading = self.coordinator.data.gateway.get(self.entity_description.key)
        return reading.value if reading else None


class EcowittSensor(CoordinatorEntity[GatewayCoordinator], SensorEntity):
    """Sensor entity belonging to a registered Ecowitt sensor."""

    _attr_has_entity_name = True

    def __init__(
        self,
        entry: AtomicConfigEntry,
        slot: int,
        description: SensorEntityDescription,
        gateway_device_id: str,
        device_registry: dr.DeviceRegistry,
    ) -> None:
        """Bind a registered Ecowitt sensor slot to its current reading."""
        super().__init__(entry.runtime_data.coordinator)
        self.entity_description = description
        self._slot = slot
        identifier = (DOMAIN, f"{entry.runtime_data.info.mac}::{slot}")
        self._attr_unique_id = f"{identifier[1]}::{self.entity_description.key}"
        self._attr_device_info = ecowitt_device_info(
            entry, slot, gateway_device_id, device_registry
        )

    @property
    def native_value(self) -> float | str | None:
        """Return the current mapped value."""
        ecowitt_sensor = self.coordinator.data.ecowitt_sensors.get(self._slot)
        if ecowitt_sensor is None:
            return None
        reading = ecowitt_sensor.readings.get(self.entity_description.key)
        return reading.value if reading else None
