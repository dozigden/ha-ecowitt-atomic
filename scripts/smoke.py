"""Check a real gateway in a disposable HA instance."""

import argparse
import asyncio
from datetime import UTC, datetime
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

from homeassistant import bootstrap, loader
from homeassistant.config_entries import SOURCE_USER
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import device_registry as dr, entity_registry as er

ROOT = Path(__file__).resolve().parent.parent


def check_devices(
    devices: list[dr.DeviceEntry], mac: str, ecowitt_slots: set[int]
) -> dr.DeviceEntry:
    """Verify device identities and links to the gateway."""
    gateway = next(
        (device for device in devices if ("ecowitt_atomic", mac) in device.identifiers),
        None,
    )
    if gateway is None:
        raise RuntimeError("Gateway identity is not based on its hardware MAC")
    for slot in ecowitt_slots:
        if not any(
            device.identifiers == {("ecowitt_atomic", f"{mac}::{slot}")}
            and device.via_device_id == gateway.id
            for device in devices
        ):
            raise RuntimeError(
                "Ecowitt sensor device identity or gateway link is invalid"
            )
    return gateway


async def smoke(base_url: str) -> dict:
    """Check setup, discovered readings, identity, refresh and reload."""
    with TemporaryDirectory(prefix="ecowitt-atomic-smoke-") as directory:
        config_dir = Path(directory)
        (config_dir / "custom_components").symlink_to(
            ROOT / "custom_components", target_is_directory=True
        )
        sys.path.insert(0, directory)
        hass = HomeAssistant(directory)
        loader.async_setup(hass)
        try:
            if (
                await bootstrap.async_from_config_dict(
                    {"homeassistant": {"time_zone": "UTC"}}, hass
                )
                is None
            ):
                raise RuntimeError("HA bootstrap failed")
            await hass.async_start()
            result = await hass.config_entries.flow.async_init(
                "ecowitt_atomic",
                context={"source": SOURCE_USER},
                data={"base_url": base_url},
            )
            if result["type"] is not FlowResultType.CREATE_ENTRY:
                raise RuntimeError(
                    f"Gateway setup failed: {result.get('errors', result['type'])}"
                )
            await hass.async_block_till_done()
            entry = result["result"]
            registry = er.async_get(hass)
            devices = dr.async_entries_for_config_entry(
                dr.async_get(hass), entry.entry_id
            )
            entities = er.async_entries_for_config_entry(registry, entry.entry_id)
            states = {}
            for entity in entities:
                state = hass.states.get(entity.entity_id)
                if state is None or state.state in {"unknown", "unavailable"}:
                    raise RuntimeError("A discovered reading is not available")
                states[entity.unique_id.split("::", 1)[1]] = {
                    "state": state.state,
                    "unit": state.attributes.get("unit_of_measurement"),
                }
            readings = entry.runtime_data.coordinator.data
            registered_ecowitt_slots = set(readings.ecowitt_sensors)
            expected_entities = len(readings.gateway) + sum(
                len(readings.ecowitt_sensors[slot].readings)
                for slot in registered_ecowitt_slots
            )
            if (
                len(devices) != 1 + len(registered_ecowitt_slots)
                or len(states) != expected_entities
            ):
                raise RuntimeError(
                    "Device/entity counts do not match registrations/readings"
                )
            mac = entry.runtime_data.info.mac
            if entry.unique_id != mac:
                raise RuntimeError("Config entry identity does not match the gateway")
            gateway = check_devices(devices, mac, registered_ecowitt_slots)
            if any(not entity.unique_id.startswith(f"{mac}::") for entity in entities):
                raise RuntimeError(
                    "Entity identities are not scoped to the gateway MAC"
                )
            await entry.runtime_data.coordinator.async_refresh()
            if not entry.runtime_data.coordinator.last_update_success:
                raise RuntimeError("Gateway refresh failed")
            previous_ids = {entity.unique_id: entity.entity_id for entity in entities}
            if not await hass.config_entries.async_reload(entry.entry_id):
                raise RuntimeError("Gateway reload failed")
            await hass.async_block_till_done()
            restored_ids = {
                entity.unique_id: entity.entity_id
                for entity in er.async_entries_for_config_entry(
                    registry, entry.entry_id
                )
            }
            if any(
                restored_ids.get(key) != value for key, value in previous_ids.items()
            ):
                raise RuntimeError("Reload did not preserve entity identities")
            return {
                "capturedAtUtc": datetime.now(UTC).isoformat(),
                "model": gateway.model,
                "firmware": gateway.sw_version,
                "devices": len(devices),
                "entities": states,
                "refreshSuccessful": True,
                "identityUsesMac": True,
                "reloadPreservesEntities": True,
            }
        finally:
            await hass.async_stop()
            sys.path.remove(directory)


def main() -> None:
    """Run the gateway check and optionally save its report."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("gateway", help="Gateway IP address, hostname, or base URL")
    parser.add_argument(
        "--output-directory", type=Path, help="Save a timestamped local report"
    )
    args = parser.parse_args()
    result = asyncio.run(smoke(args.gateway))
    output = json.dumps(result, indent=2) + "\n"
    if args.output_directory:
        args.output_directory.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.fromisoformat(result["capturedAtUtc"]).strftime(
            "%Y%m%dT%H%M%SZ"
        )
        path = args.output_directory / f"gateway-smoke-{timestamp}.json"
        if path.exists():
            raise FileExistsError(path)
        path.write_text(output)
        print(path)
    print(output)


if __name__ == "__main__":
    main()
