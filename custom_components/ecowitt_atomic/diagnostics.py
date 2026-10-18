"""Allowlisted diagnostics without gateway addresses or raw payloads."""

from typing import Any

from homeassistant.core import HomeAssistant

from .data import AtomicConfigEntry


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: AtomicConfigEntry
) -> dict[str, Any]:
    """Expose setup state and available runtime details without connection data."""
    data = entry.runtime_data
    if data is None:
        return {"state": entry.state.value, "readings": {}}
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
            for key, value in data.coordinator.data.items()
        },
    }
