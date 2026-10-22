"""Temperature and humidity discovery from channel-linked live readings."""

from custom_components.ecowitt_atomic.const import DOMAIN
from custom_components.ecowitt_atomic.diagnostics import (
    async_get_config_entry_diagnostics,
)
from custom_components.ecowitt_atomic.mapping_engine import apply_reading_mappings
from custom_components.ecowitt_atomic.mappings import (
    READING_MAPPINGS,
    TEMPERATURE_HUMIDITY_MAPPING,
    TEMPERATURE_MAPPING,
)
from custom_components.ecowitt_atomic.models import Reading
from custom_components.ecowitt_atomic.parsers import (
    parse_ecowitt_sensors,
    parse_temperature,
)
import pytest

from homeassistant.helpers import device_registry as dr, entity_registry as er

from .conftest import MAC
from .test_soil_integration import load, refresh, responses


@pytest.mark.parametrize(
    ("value", "unit", "expected"),
    [
        ("0", "C", 0),
        ("-12.5", "°C", -12.5),
        ("68", "F", 20),
        (32, " f ", 0),
        ("--", "C", None),
        (None, "C", None),
        (True, "C", None),
        ("nan", "C", None),
        ("inf", "F", None),
        ("12", None, None),
        ("12", "K", None),
        ("12", True, None),
    ],
)
def test_temperature_units(value, unit, expected):
    """Normalize supported units and reject invalid readings."""
    reading = parse_temperature(value, unit)
    if expected is None:
        assert reading is None
    else:
        assert reading.unit == "°C"
        assert reading.value == pytest.approx(expected)


def test_mapping_uses_context_and_radio_links():
    """Attribute capabilities across formats without relying on type or model."""
    registrations = [
        {"type": "985", "id": "ABC", "img": "future"},
        {"type": "847", "id": "DEF", "img": "wh31"},
    ]
    result = apply_reading_mappings(
        {
            "ch_aisle": [
                {"channel": "3", "temp": "68", "unit": "F", "humidity": "90%"}
            ],
            "ch_soil": [{"channel": "3", "humidity": "30%"}],
        },
        {
            "get_cli_multiCh": [
                {"channel": "3", "id": "0x00abc", "temp": "5.0", "humi": "4"}
            ],
            "get_cli_soilad": [{"ch": "3", "id": "0xABC"}],
        },
        parse_ecowitt_sensors(registrations),
        READING_MAPPINGS,
        registrations=(),
    )
    assert result[985].readings == {
        "temperature": Reading(20, "°C"),
        "humidity": Reading(90, "%"),
        "soil_moisture": Reading(30, "%"),
    }
    assert result[847].readings == {}


@pytest.mark.parametrize(
    ("record", "expected"),
    [
        ({"temp": "0", "unit": "C"}, {"temperature": Reading(0, "°C")}),
        ({"temp": "--", "unit": "C", "humidity": "0%"}, {"humidity": Reading(0, "%")}),
        ({"temp": "10", "humidity": "40%"}, {"humidity": Reading(40, "%")}),
        (
            {"temp": "10", "unit": "C", "humidity": "101%"},
            {"temperature": Reading(10, "°C")},
        ),
        ({}, {}),
    ],
)
def test_independent_reading_discovery(record, expected):
    """Each valid field independently establishes a capability."""
    registrations = [{"type": "847", "id": "ABC", "img": "wh31"}]
    result = apply_reading_mappings(
        {"ch_aisle": [{"channel": "1", **record}]},
        {"get_cli_multiCh": [{"channel": "1", "id": "ABC", "temp": "5", "humi": "4"}]},
        parse_ecowitt_sensors(registrations),
        (TEMPERATURE_HUMIDITY_MAPPING,),
        registrations=(),
    )
    assert result[847].readings == expected


@pytest.mark.parametrize(
    ("mapping", "group", "endpoint"),
    [
        (TEMPERATURE_HUMIDITY_MAPPING, "ch_aisle", "get_cli_multiCh"),
        (TEMPERATURE_MAPPING, "ch_temp", "get_cli_wh34"),
    ],
)
@pytest.mark.parametrize(
    "metadata",
    [
        [],
        [{"channel": "1", "id": "DEF"}],
        [{"channel": "1", "id": "ABC"}, {"channel": "1", "id": "DEF"}],
        [{"channel": "1", "id": "ABC"}, {"channel": "2", "id": "ABC"}],
    ],
)
def test_missing_or_ambiguous_ownership(metadata, mapping, group, endpoint):
    """Require a unique metadata link before attributing live readings."""
    result = apply_reading_mappings(
        {group: [{"channel": "1", "temp": "12", "unit": "C", "humidity": "50%"}]},
        {endpoint: metadata},
        parse_ecowitt_sensors([{"type": "6", "id": "ABC", "img": "wh31"}]),
        (mapping,),
        registrations=(),
    )
    assert result[6].readings == {}


async def test_wh31_discovery_and_retention(
    hass, entry, aioclient_mock, live_payload, entity_registry, device_registry
):
    """Discover readings separately and retain their devices through a reload."""
    registrations = [
        {"type": "847", "id": "ABC", "img": "wh31", "name": "Temp & Humidity CH3"},
        {"type": "985", "id": "DEF", "img": "wh31", "name": "Temp & Humidity CH5"},
        {"type": "123", "id": "FFFFFFFF", "img": "wh31"},
    ]
    metadata = [
        {"channel": "3", "id": "0xABC", "temp": "5.0", "humi": "4"},
        {"channel": "5", "id": "0xDEF", "temp": "0.0", "humi": "0"},
    ]
    live_payload["ch_aisle"] = [
        {
            "channel": "3",
            "name": "Greenhouse",
            "temp": "68",
            "unit": "F",
            "humidity": "--",
        }
    ]
    responses(
        aioclient_mock,
        live_payload,
        [],
        registrations=registrations,
        multi_channels=metadata,
    )
    await load(hass, entry)
    devices = dr.async_entries_for_config_entry(device_registry, entry.entry_id)
    assert len(devices) == 3
    device = device_registry.async_get_device_by_identifier(
        (DOMAIN, f"{MAC}::847"), entry.entry_id
    )
    offline_device = device_registry.async_get_device_by_identifier(
        (DOMAIN, f"{MAC}::985"), entry.entry_id
    )
    assert device.name == "Greenhouse"
    assert device.model == "Temp & Humidity"
    assert device_registry.async_get(device.via_device_id).identifiers == {
        (DOMAIN, MAC)
    }
    assert {
        e.unique_id
        for e in er.async_entries_for_device(entity_registry, offline_device.id)
    } == {f"{MAC}::985::gateway_name", f"{MAC}::985::radio_id"}
    temperature_id = entity_registry.async_get_entity_id(
        "sensor", DOMAIN, f"{MAC}::847::temperature"
    )
    state = hass.states.get(temperature_id)
    assert float(state.state) == 20
    assert state.attributes["device_class"] == "temperature"
    assert state.attributes["unit_of_measurement"] == "°C"
    assert state.attributes["state_class"] == "measurement"
    assert (
        entity_registry.async_get_entity_id("sensor", DOMAIN, f"{MAC}::847::humidity")
        is None
    )

    live_payload["ch_aisle"] = [
        {"channel": "3", "temp": "--", "unit": "C", "humidity": "0%"},
        {"channel": "5", "temp": "-5", "unit": "C", "humidity": "50%"},
    ]
    aioclient_mock.clear_requests()
    responses(
        aioclient_mock,
        live_payload,
        [],
        registrations=registrations,
        multi_channels=metadata,
    )
    await refresh(hass, entry)
    assert hass.states.get(temperature_id).state == "unknown"
    humidity_id = entity_registry.async_get_entity_id(
        "sensor", DOMAIN, f"{MAC}::847::humidity"
    )
    state = hass.states.get(humidity_id)
    assert float(state.state) == 0
    assert state.attributes["device_class"] == "humidity"
    assert state.attributes["unit_of_measurement"] == "%"
    assert state.attributes["state_class"] == "measurement"
    assert entity_registry.async_get(humidity_id).device_id == device.id
    later_temperature = entity_registry.async_get_entity_id(
        "sensor", DOMAIN, f"{MAC}::985::temperature"
    )
    assert entity_registry.async_get(later_temperature).device_id == offline_device.id
    diagnostics = await async_get_config_entry_diagnostics(hass, entry)
    assert diagnostics["ecowitt_sensors"]["985"]["temperature"] == {
        "value": -5,
        "unit": "°C",
    }
    assert diagnostics["ecowitt_sensors"]["985"]["humidity"] == {
        "value": 50,
        "unit": "%",
    }

    original = {
        e.unique_id: (e.entity_id, e.device_id)
        for e in er.async_entries_for_config_entry(entity_registry, entry.entry_id)
    }
    aioclient_mock.clear_requests()
    live_payload["ch_aisle"] = []
    responses(aioclient_mock, live_payload, [], registrations=[])
    await refresh(hass, entry)
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert {
        e.unique_id: (e.entity_id, e.device_id)
        for e in er.async_entries_for_config_entry(entity_registry, entry.entry_id)
    } == original
    assert hass.states.get(humidity_id).state == "unknown"
    assert hass.states.get(later_temperature).state == "unknown"
