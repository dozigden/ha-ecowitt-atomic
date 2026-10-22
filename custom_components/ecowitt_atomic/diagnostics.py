"""Gateway diagnostics."""

from typing import NotRequired, TypedDict

from homeassistant.core import HomeAssistant

from .capabilities import SENSOR_DESCRIPTIONS
from .data import AtomicConfigEntry
from .models import Reading


class ReadingDiagnostics(TypedDict):
    """A parsed reading exported in diagnostics."""

    value: float
    unit: str


class GatewayDiagnostics(TypedDict):
    """Allowlisted diagnostics with optional loaded-gateway details."""

    state: str
    readings: dict[str, ReadingDiagnostics]
    model: NotRequired[str]
    firmware: NotRequired[str]
    last_poll_successful: NotRequired[bool]
    ecowitt_sensors: NotRequired[dict[str, dict[str, ReadingDiagnostics]]]


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,  # noqa: ARG001
    entry: AtomicConfigEntry,
) -> GatewayDiagnostics:
    """Return setup state and parsed readings."""
    if not hasattr(entry, "runtime_data"):
        return {"state": entry.state.value, "readings": {}}

    data = entry.runtime_data
    return {
        "state": entry.state.value,
        "model": data.info.model,
        "firmware": data.info.firmware,
        "last_poll_successful": data.coordinator.last_update_success,
        "readings": {
            key: {
                "value": value.value,
                "unit": value.unit,
            }
            for key, value in data.coordinator.data.gateway.items()
        },
        "ecowitt_sensors": {
            str(slot): {
                key: {"value": reading.value, "unit": reading.unit}
                for key, reading in ecowitt_sensor.readings.items()
                if (description := SENSOR_DESCRIPTIONS.get(key))
                and description.include_in_diagnostics
                and isinstance(reading, Reading)
            }
            for slot, ecowitt_sensor in data.coordinator.data.ecowitt_sensors.items()
        },
    }
