"""Verify a real gateway through HA's setup flow in a disposable HA instance."""

import argparse
import asyncio
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory

from homeassistant import bootstrap, loader
from homeassistant.config_entries import SOURCE_USER
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

ROOT = Path(__file__).resolve().parent.parent


async def smoke(base_url: str) -> dict:
    """Create a real HA config entry and inspect its device and entity states."""
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
                    raise RuntimeError("An internal reading is not available")
                states[entity.unique_id.rsplit("::", 1)[1]] = {
                    "state": state.state,
                    "unit": state.attributes.get("unit_of_measurement"),
                }
            if len(devices) != 1 or len(states) != 4:
                raise RuntimeError(
                    "Expected one gateway device and four sensor entities"
                )
            mac = entry.runtime_data.info.mac
            if entry.unique_id != mac or devices[0].identifiers != {
                ("ecowitt_atomic", mac)
            }:
                raise RuntimeError("Gateway identity is not based on its hardware MAC")
            if any(not entity.unique_id.startswith(f"{mac}::") for entity in entities):
                raise RuntimeError(
                    "Entity identities are not scoped to the gateway MAC"
                )
            # Exercise the real client's next poll through the same coordinator.
            await entry.runtime_data.coordinator.async_refresh()
            if not entry.runtime_data.coordinator.last_update_success:
                raise RuntimeError("Gateway refresh failed")
            return {
                "capturedAtUtc": datetime.now(UTC).isoformat(),
                "model": devices[0].model,
                "firmware": devices[0].sw_version,
                "devices": len(devices),
                "entities": states,
                "refreshSuccessful": True,
                "identityUsesMac": True,
            }
        finally:
            await hass.async_stop()
            sys.path.remove(directory)


def main() -> None:
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
