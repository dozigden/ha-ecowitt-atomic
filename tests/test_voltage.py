"""Voltage diagnostics from explicitly linked live channels."""

from custom_components.ecowitt_atomic.const import DOMAIN
from custom_components.ecowitt_atomic.diagnostics import (
    async_get_config_entry_diagnostics,
)
from custom_components.ecowitt_atomic.mapping_engine import apply_reading_mappings
from custom_components.ecowitt_atomic.mappings import READING_MAPPINGS
from custom_components.ecowitt_atomic.models import Reading
from custom_components.ecowitt_atomic.parsers import parse_ecowitt_sensors
import pytest

from .conftest import MAC
from .test_soil_integration import load, refresh, responses


@pytest.mark.parametrize(
    ("group", "endpoint", "channel_key"),
    [
        ("ch_soil", "get_cli_soilad", "ch"),
        ("ch_temp", "get_cli_wh34", "channel"),
    ],
)
@pytest.mark.parametrize("ownership", ["valid", "missing", "unregistered", "ambiguous"])
def test_voltage_requires_channel_ownership(group, endpoint, channel_key, ownership):
    """Use explicit links regardless of model, ignoring voltage in other contexts."""
    registrations = [{"type": "847", "id": "ABC", "img": "future", "voltage": "8"}]
    metadata = [{channel_key: "3", "id": "0x00abc", "voltage": "9"}]
    if ownership == "missing":
        metadata = []
    elif ownership == "unregistered":
        metadata[0]["id"] = "DEF"
    elif ownership == "ambiguous":
        metadata.append({channel_key: "3", "id": "DEF"})
    result = apply_reading_mappings(
        {
            group: [{"channel": "3", "voltage": "1.34"}],
            "piezoRain": [{"voltage": "2.90"}],
            "ch_aisle": [{"channel": "3", "voltage": "4"}],
        },
        {endpoint: metadata, "get_cli_multiCh": [{"channel": "3", "id": "ABC"}]},
        parse_ecowitt_sensors(registrations),
        READING_MAPPINGS,
        registrations=registrations,
    )
    readings = result[847].readings
    if ownership == "valid":
        assert readings["voltage"] == Reading(1.34, "V")
    else:
        assert "voltage" not in readings


@pytest.mark.parametrize("group", ["ch_soil", "ch_temp"])
async def test_voltage_diagnostic_lifecycle(
    hass, entry, aioclient_mock, live_payload, entity_registry, device_registry, group
):
    """Discover voltage alone, then retain its device and identity across missing data."""
    registrations = [{"type": "847", "id": "ABC", "img": "future"}]
    record = {"channel": "3", "voltage": "--"}

    def set_responses():
        """Provide the same channel through the appropriate metadata endpoint."""
        aioclient_mock.clear_requests()
        live_payload[group] = [record]
        responses(
            aioclient_mock,
            live_payload,
            [record] if group == "ch_soil" else [],
            registrations=registrations,
            soil_channels=[{"ch": "3", "id": "ABC"}],
            temperature_channels=[{"channel": "3", "id": "ABC"}],
        )

    set_responses()
    await load(hass, entry)
    unique_id = f"{MAC}::847::voltage"
    assert entity_registry.async_get_entity_id("sensor", DOMAIN, unique_id) is None
    device = device_registry.async_get_device_by_identifier(
        (DOMAIN, f"{MAC}::847"), entry.entry_id
    )
    record["voltage"] = "1.32"
    set_responses()
    await refresh(hass, entry)
    entity_id = entity_registry.async_get_entity_id("sensor", DOMAIN, unique_id)
    registered = entity_registry.async_get(entity_id)
    assert registered.device_id == device.id
    assert registered.entity_category.value == "diagnostic"
    state = hass.states.get(entity_id)
    assert state.state == "1.32"
    assert state.attributes["device_class"] == "voltage"
    assert state.attributes["unit_of_measurement"] == "V"
    assert state.attributes["state_class"] == "measurement"
    diagnostics = await async_get_config_entry_diagnostics(hass, entry)
    assert diagnostics["ecowitt_sensors"]["847"]["voltage"] == {
        "value": 1.32,
        "unit": "V",
    }

    for value, expected in [("0", "0.0"), ("--", "unknown"), ("-1", "unknown")]:
        record["voltage"] = value
        set_responses()
        await refresh(hass, entry)
        assert hass.states.get(entity_id).state == expected

    del record["voltage"]
    set_responses()
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get(entity_id).state == "unknown"
    assert entity_registry.async_get_entity_id("sensor", DOMAIN, unique_id) == entity_id
    assert entity_registry.async_get(entity_id).device_id == device.id

    record["voltage"] = "1.40"
    set_responses()
    await refresh(hass, entry)
    assert hass.states.get(entity_id).state == "1.4"
