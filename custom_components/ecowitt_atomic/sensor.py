"""Sensor entities for the gateway's own internal readings."""

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, UnitOfPressure, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .data import AtomicConfigEntry
from .entity import GatewayEntity

PARALLEL_UPDATES = 0

DESCRIPTIONS = (
    SensorEntityDescription(
        key="indoor_temperature",
        translation_key="indoor_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
    ),
    SensorEntityDescription(
        key="indoor_humidity",
        translation_key="indoor_humidity",
        device_class=SensorDeviceClass.HUMIDITY,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
    ),
    SensorEntityDescription(
        key="absolute_pressure",
        translation_key="absolute_pressure",
        device_class=SensorDeviceClass.ATMOSPHERIC_PRESSURE,
        native_unit_of_measurement=UnitOfPressure.HPA,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
    ),
    SensorEntityDescription(
        key="relative_pressure",
        translation_key="relative_pressure",
        device_class=SensorDeviceClass.ATMOSPHERIC_PRESSURE,
        native_unit_of_measurement=UnitOfPressure.HPA,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: AtomicConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Create fixed gateway entities; retain them through missing readings."""
    async_add_entities(
        GatewaySensor(entry, description) for description in DESCRIPTIONS
    )


class GatewaySensor(GatewayEntity, SensorEntity):
    """Expose a gateway reading using coordinator availability."""

    def __init__(
        self, entry: AtomicConfigEntry, description: SensorEntityDescription
    ) -> None:
        super().__init__(entry)
        self.entity_description = description
        self._attr_unique_id = f"{entry.runtime_data.info.mac}::{description.key}"

    @property
    def native_value(self) -> float | None:
        reading = self.coordinator.data.get(self.entity_description.key)
        return reading.value if reading else None
