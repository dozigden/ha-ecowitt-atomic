"""Registration RSSI parsing and discovery."""

from custom_components.ecowitt_atomic.const import DOMAIN
from custom_components.ecowitt_atomic.diagnostics import (
    async_get_config_entry_diagnostics,
)
from custom_components.ecowitt_atomic.models import Reading
from custom_components.ecowitt_atomic.parsers import parse_rssi
import pytest

from homeassistant.helpers import entity_registry as er

from .conftest import MAC
from .test_soil_integration import load, refresh, responses


@pytest.mark.parametrize("value", ["-50", -50, -50.0])
def test_rssi(value):
    """Preserve signed signal strength in dBm."""
    assert parse_rssi(value) == Reading(-50, "dBm")


@pytest.mark.parametrize(
    "value", [None, "--", "", "bad", True, False, "nan", "inf", float("-inf"), [], {}]
)
def test_invalid_rssi(value):
    """Missing and malformed values supply no reading."""
    assert parse_rssi(value) is None


async def test_rssi_discovery_and_retention(
    hass, entry, aioclient_mock, live_payload, entity_registry, device_registry
):
    """Discover RSSI across registrations and retain entities when it disappears."""
    registrations = [
        {"type": "847", "id": "ABC", "img": "future", "rssi": "--", "signal": "4"},
        {"type": "31", "id": "DEF", "rssi": "-75", "signal": "--"},
        {"type": "99", "id": "FFFFFFFF", "rssi": "-50"},
        {"type": "100", "id": "FFFFFFFE", "rssi": "-50"},
    ]
    responses(aioclient_mock, live_payload, [], registrations=registrations)
    await load(hass, entry)
    unique_id = f"{MAC}::847::rssi"
    assert entity_registry.async_get_entity_id("sensor", DOMAIN, unique_id) is None
    other_id = entity_registry.async_get_entity_id("sensor", DOMAIN, f"{MAC}::31::rssi")
    assert float(hass.states.get(other_id).state) == -75
    assert {
        e.unique_id
        for e in er.async_entries_for_config_entry(entity_registry, entry.entry_id)
        if e.unique_id.endswith("::rssi")
    } == {f"{MAC}::31::rssi"}

    registrations[0]["rssi"] = "-84"
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
    assert float(state.state) == -84
    assert state.attributes["device_class"] == "signal_strength"
    assert state.attributes["unit_of_measurement"] == "dBm"
    assert state.attributes["state_class"] == "measurement"
    diagnostics = await async_get_config_entry_diagnostics(hass, entry)
    assert diagnostics["ecowitt_sensors"]["847"]["rssi"] == {
        "value": -84,
        "unit": "dBm",
    }

    for value in ("--", None):
        registrations[0]["rssi"] = value
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

    registrations[0]["rssi"] = "-52"
    aioclient_mock.clear_requests()
    responses(aioclient_mock, live_payload, [], registrations=registrations)
    await refresh(hass, entry)
    assert float(hass.states.get(entity_id).state) == -52
