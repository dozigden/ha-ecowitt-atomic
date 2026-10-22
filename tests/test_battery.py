"""Battery display-code interpretation and entity lifecycle."""

from custom_components.ecowitt_atomic.const import DOMAIN
from custom_components.ecowitt_atomic.diagnostics import (
    async_get_config_entry_diagnostics,
)
from custom_components.ecowitt_atomic.models import Reading
from custom_components.ecowitt_atomic.parsers import parse_battery
import pytest

from homeassistant.helpers import entity_registry as er

from .conftest import BASE_URL, MAC
from .test_soil_integration import load, refresh, responses


@pytest.mark.parametrize("as_string", [False, True])
@pytest.mark.parametrize(
    ("code", "expected"), [(0, 100), (1, 10), (2, 25), (3, 50), (4, 75), (5, 100)]
)
def test_battery_percentages(code, expected, as_string):
    """Map normal/low status and icon levels to the agreed percentages."""
    assert parse_battery(str(code) if as_string else code) == Reading(expected, "%")


@pytest.mark.parametrize(
    "value",
    [6, "6", 9, "9", 7, "8", None, "", "--", True, False, -1, 1.5, "1.5", [], {}],
)
def test_unknown_battery(value):
    """DC, unknown and invalid codes supply no percentage."""
    assert parse_battery(value) is None


@pytest.mark.parametrize("initial", ["6", "9", None])
@pytest.mark.no_fail_on_log_exception
async def test_battery_discovery_and_retention(
    hass, entry, aioclient_mock, live_payload, entity_registry, device_registry, initial
):
    """Discover from registration, retain unknown values and recover after failure."""
    registrations = [
        {"type": "847", "id": "ABC", "img": "future", "batt": initial},
        {"type": "31", "id": "DEF", "batt": "5"},
        {"type": "99", "id": "FFFFFFFF", "batt": "5"},
        {"type": "100", "id": "FFFFFFFE", "batt": "5"},
    ]
    live_payload["ch_temp"] = [{"channel": "1", "battery": "1", "voltage": "1.34"}]
    responses(aioclient_mock, live_payload, [], registrations=registrations)
    await load(hass, entry)
    unique_id = f"{MAC}::847::battery"
    assert entity_registry.async_get_entity_id("sensor", DOMAIN, unique_id) is None
    other_id = entity_registry.async_get_entity_id(
        "sensor", DOMAIN, f"{MAC}::31::battery"
    )
    assert float(hass.states.get(other_id).state) == 100
    assert {
        e.unique_id
        for e in er.async_entries_for_config_entry(entity_registry, entry.entry_id)
        if e.unique_id.endswith("::battery")
    } == {f"{MAC}::31::battery"}

    registrations[0]["batt"] = "1"
    aioclient_mock.clear_requests()
    responses(aioclient_mock, live_payload, [], registrations=registrations)
    await refresh(hass, entry)
    entity_id = entity_registry.async_get_entity_id("sensor", DOMAIN, unique_id)
    registered = entity_registry.async_get(entity_id)
    device = device_registry.async_get_device_by_identifier(
        (DOMAIN, f"{MAC}::847"), entry.entry_id
    )
    assert registered.device_id == device.id
    assert registered.entity_category.value == "diagnostic"
    state = hass.states.get(entity_id)
    assert float(state.state) == 10
    assert state.attributes["device_class"] == "battery"
    assert state.attributes["unit_of_measurement"] == "%"
    assert state.attributes["state_class"] == "measurement"
    diagnostics = await async_get_config_entry_diagnostics(hass, entry)
    assert diagnostics["ecowitt_sensors"]["847"]["battery"] == {
        "value": 10,
        "unit": "%",
    }

    for code in ("6", "9", None):
        registrations[0]["batt"] = code
        aioclient_mock.clear_requests()
        responses(aioclient_mock, live_payload, [], registrations=registrations)
        await refresh(hass, entry)
        assert hass.states.get(entity_id).state == "unknown"
    aioclient_mock.clear_requests()
    responses(aioclient_mock, live_payload, [], registrations=[])
    await refresh(hass, entry)
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert entity_registry.async_get_entity_id("sensor", DOMAIN, unique_id) == entity_id
    assert entity_registry.async_get(entity_id).device_id == device.id
    assert hass.states.get(entity_id).state == "unknown"

    aioclient_mock.clear_requests()
    aioclient_mock.get(f"{BASE_URL}/get_livedata_info", status=503)
    await refresh(hass, entry)
    assert hass.states.get(entity_id).state == "unavailable"
    registrations[0]["batt"] = "0"
    aioclient_mock.clear_requests()
    responses(aioclient_mock, live_payload, [], registrations=registrations)
    await refresh(hass, entry)
    assert float(hass.states.get(entity_id).state) == 100
