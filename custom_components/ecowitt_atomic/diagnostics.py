"""Gateway diagnostics."""

from copy import deepcopy
from typing import NotRequired, TypedDict

from homeassistant.core import HomeAssistant

from .capabilities import SENSOR_DESCRIPTIONS
from .data import AtomicConfigEntry
from .models import Reading


class RawApiDiagnostics(TypedDict):
    """Unmodified decoded responses from one polling attempt."""

    captured_at: str
    complete: bool
    responses: dict[str, object]


class ReadingDiagnostics(TypedDict):
    """A parsed reading exported in diagnostics."""

    value: float
    unit: str


class GatewayDiagnostics(TypedDict):
    """Parsed diagnostics and raw API responses for a loaded gateway."""

    state: str
    readings: dict[str, ReadingDiagnostics]
    model: NotRequired[str]
    firmware: NotRequired[str]
    last_poll_successful: NotRequired[bool]
    ecowitt_sensors: NotRequired[dict[str, dict[str, ReadingDiagnostics]]]
    raw_api: NotRequired[RawApiDiagnostics]


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,  # noqa: ARG001
    entry: AtomicConfigEntry,
) -> GatewayDiagnostics:
    """Return saved polling data without making gateway requests."""
    if not hasattr(entry, "runtime_data"):
        return {"state": entry.state.value, "readings": {}}

    data = entry.runtime_data
    diagnostics: GatewayDiagnostics = {
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
    if (batch := data.coordinator.raw_api) is not None:
        diagnostics["raw_api"] = {
            "captured_at": batch.captured_at,
            "complete": batch.complete,
            "responses": deepcopy(batch.responses),
        }
    return diagnostics
