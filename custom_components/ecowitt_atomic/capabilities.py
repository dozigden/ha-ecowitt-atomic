"""HA sensor definitions for gateway and Ecowitt sensor readings."""

from dataclasses import dataclass

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    PERCENTAGE,
    SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
    EntityCategory,
    UnitOfPressure,
    UnitOfTemperature,
)

from .const import (
    BATTERY,
    GATEWAY_NAME,
    HUMIDITY,
    RADIO_ID,
    RSSI,
    SOIL_MOISTURE,
    TEMPERATURE,
)

GATEWAY_SENSOR_DESCRIPTIONS = (
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


@dataclass(frozen=True, kw_only=True)
class AtomicSensorDescription(SensorEntityDescription):
    """Describe an entity and whether its value may appear in downloads."""

    include_in_diagnostics: bool = False


SENSOR_DESCRIPTIONS = {
    description.key: description
    for description in (
        AtomicSensorDescription(
            key=RSSI,
            translation_key="rssi",
            device_class=SensorDeviceClass.SIGNAL_STRENGTH,
            native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
            state_class=SensorStateClass.MEASUREMENT,
            suggested_display_precision=0,
            entity_category=EntityCategory.DIAGNOSTIC,
            include_in_diagnostics=True,
        ),
        AtomicSensorDescription(
            key=BATTERY,
            translation_key="battery",
            device_class=SensorDeviceClass.BATTERY,
            native_unit_of_measurement=PERCENTAGE,
            state_class=SensorStateClass.MEASUREMENT,
            suggested_display_precision=0,
            entity_category=EntityCategory.DIAGNOSTIC,
            include_in_diagnostics=True,
        ),
        AtomicSensorDescription(
            key=TEMPERATURE,
            translation_key="temperature",
            device_class=SensorDeviceClass.TEMPERATURE,
            native_unit_of_measurement=UnitOfTemperature.CELSIUS,
            state_class=SensorStateClass.MEASUREMENT,
            suggested_display_precision=1,
            include_in_diagnostics=True,
        ),
        AtomicSensorDescription(
            key=HUMIDITY,
            translation_key="humidity",
            device_class=SensorDeviceClass.HUMIDITY,
            native_unit_of_measurement=PERCENTAGE,
            state_class=SensorStateClass.MEASUREMENT,
            suggested_display_precision=0,
            include_in_diagnostics=True,
        ),
        AtomicSensorDescription(
            key=SOIL_MOISTURE,
            translation_key="soil_moisture",
            device_class=SensorDeviceClass.MOISTURE,
            native_unit_of_measurement=PERCENTAGE,
            state_class=SensorStateClass.MEASUREMENT,
            suggested_display_precision=0,
            include_in_diagnostics=True,
        ),
        AtomicSensorDescription(
            key=GATEWAY_NAME,
            translation_key="gateway_name",
            entity_category=EntityCategory.DIAGNOSTIC,
        ),
        AtomicSensorDescription(
            key=RADIO_ID,
            translation_key="radio_id",
            entity_category=EntityCategory.DIAGNOSTIC,
        ),
    )
}
