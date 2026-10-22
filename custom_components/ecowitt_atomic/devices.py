"""Register gateway and Ecowitt sensor devices independently of entities."""

import re

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr

from .const import DOMAIN
from .data import AtomicConfigEntry


def gateway_device_info(entry: AtomicConfigEntry) -> dr.DeviceInfo:
    """Describe the gateway device."""
    info = entry.runtime_data.info
    return dr.DeviceInfo(
        identifiers={(DOMAIN, info.mac)},
        connections={(dr.CONNECTION_NETWORK_MAC, info.mac)},
        manufacturer="Ecowitt",
        model=info.model,
        sw_version=info.firmware,
        name=info.name,
        configuration_url=entry.runtime_data.coordinator.client.base_url,
    )


def ecowitt_device_info(
    entry: AtomicConfigEntry,
    slot: int,
    gateway_device_id: str,
    registry: dr.DeviceRegistry,
) -> dr.DeviceInfo:
    """Describe an Ecowitt sensor without overwriting its remembered name."""
    identifier = (DOMAIN, f"{entry.runtime_data.info.mac}::{slot}")
    info = dr.DeviceInfo(
        identifiers={identifier},
        manufacturer="Ecowitt",
        via_device_id=gateway_device_id,
        configuration_url=entry.runtime_data.coordinator.client.base_url,
    )
    ecowitt_sensor = entry.runtime_data.coordinator.data.ecowitt_sensors.get(slot)
    if ecowitt_sensor and ecowitt_sensor.registration_name:
        model = re.sub(
            r"(?:^|\s+)CH[0-9]+$",
            "",
            ecowitt_sensor.registration_name,
            flags=re.IGNORECASE,
        ).strip()
        if model:
            info["model"] = model
    if registry.async_get_device_by_identifier(identifier, entry.entry_id) is None:
        info["name"] = (
            ecowitt_sensor.name if ecowitt_sensor else f"Ecowitt sensor {slot}"
        )
    return info


@callback
def async_setup_devices(hass: HomeAssistant, entry: AtomicConfigEntry) -> None:
    """Create devices from registrations on setup and subsequent polls."""
    registry = dr.async_get(hass)
    gateway = registry.async_get_or_create(
        config_entry_id=entry.entry_id, **gateway_device_info(entry)
    )
    coordinator = entry.runtime_data.coordinator

    @callback
    def discover() -> None:
        if not coordinator.last_update_success:
            return
        for slot in coordinator.data.ecowitt_sensors:
            registry.async_get_or_create(
                config_entry_id=entry.entry_id,
                **ecowitt_device_info(entry, slot, gateway.id, registry),
            )

    entry.async_on_unload(coordinator.async_add_listener(discover))
    discover()
