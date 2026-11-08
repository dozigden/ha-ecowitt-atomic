"""Singleton property ownership, typed readings and HA lifecycle."""

from custom_components.ecowitt_atomic.catalogue import singleton_property
from custom_components.ecowitt_atomic.const import DOMAIN
from custom_components.ecowitt_atomic.mapping_engine import apply_reading_mappings
from custom_components.ecowitt_atomic.mappings import READING_MAPPINGS
from custom_components.ecowitt_atomic.models import Reading, TextReading
from custom_components.ecowitt_atomic.parsers import (
    parse_ecowitt_sensors,
    parse_firmware_version,
    parse_voltage,
)
import pytest

from .conftest import MAC
from .test_soil_integration import load, refresh, responses


@pytest.mark.parametrize("field", ["ws85cap_volt", "wh85cap_volt", "WS85CAP_VOLT"])
def test_singleton_aliases(field):
    """WS and WH identify the same unique catalogue entry."""
    assert singleton_property(field) == (49, "cap_volt")


@pytest.mark.parametrize(
    "field",
    [
        "wh31cap_volt",
        "ws51_ver",
        "wh41_ver",
        "wh55_ver",
        "wh34_ver",
        "wh35_ver",
        "wh48_ver",
        "wh54_ver",
        "ws999cap_volt",
        "ws085_ver",
        "voltage",
        "ws85",
        "prefix_ws85_ver",
        "wn85_ver",
    ],
)
def test_non_singleton_or_unknown_designation(field):
    """Channel and reserved catalogue families cannot resolve by name alone."""
    assert singleton_property(field) is None


def mapped(payload, registrations):
    """Apply production mappings to a single gateway snapshot."""
    return apply_reading_mappings(
        payload,
        {},
        parse_ecowitt_sensors(registrations),
        READING_MAPPINGS,
        registrations=registrations,
    )


def test_independent_owners_and_capabilities():
    """One rain record can carry diagnostics for distinct registered owners."""
    result = mapped(
        {
            "piezoRain": [
                {
                    "id": "0x13",
                    "val": "200 mm",
                    "voltage": "3.1",
                    "ws85cap_volt": "2.5",
                    "wh85_ver": "118",
                    "wh90cap_volt": "5.3",
                    "ws90_ver": "156",
                    "ws85unknown": "88",
                    "wh31cap_volt": "3.0",
                }
            ]
        },
        [
            {"type": "49", "id": "ABC", "img": "unfamiliar", "name": "Custom"},
            {"type": "48", "id": "DEF"},
            {"type": "6", "id": "123"},
        ],
    )
    assert result[49].readings["capacitor_voltage"] == Reading(2.5, "V")
    assert result[49].readings["firmware_version"] == TextReading("1.1.8")
    assert result[48].readings["capacitor_voltage"] == Reading(5.3, "V")
    assert result[48].readings["firmware_version"] == TextReading("1.5.6")
    assert "capacitor_voltage" not in result[6].readings
    assert "voltage" not in result[49].readings
    assert "unknown" not in result[49].readings


@pytest.mark.parametrize(
    "registrations",
    [
        [],
        [{"type": "49", "id": "FFFFFFFF"}],
        [{"type": "49", "id": "FFFFFFFE"}],
        [{"type": "49", "id": "ABC"}, {"type": "49", "id": "DEF"}],
        [{"type": "847", "id": "ABC", "img": "wh85", "name": "WS85"}],
    ],
)
def test_registration_required(registrations):
    """Never create owners from fields, invalid registrations, images or names."""
    result = mapped({"piezoRain": [{"ws85cap_volt": "2.5"}]}, registrations)
    assert all("capacitor_voltage" not in item.readings for item in result.values())


@pytest.mark.parametrize("group", ["common_list", "rain", "unrecognised"])
def test_source_context(group):
    """Named fields are interpreted only in the declared API group."""
    result = mapped({group: [{"ws85cap_volt": "2.5"}]}, [{"type": "49", "id": "ABC"}])
    assert "capacitor_voltage" not in result[49].readings


@pytest.mark.parametrize("duplicate", ["2.5", "3.1", "--"])
@pytest.mark.parametrize("separate_record", [False, True])
def test_ambiguous_aliases(duplicate, separate_record):
    """Repeated owners/properties are ambiguous even with invalid or equal values."""
    records = [{"ws85cap_volt": "2.5", "ws85_ver": "118"}]
    if separate_record:
        records.append({"wh85cap_volt": duplicate})
    else:
        records[0]["wh85cap_volt"] = duplicate
    result = mapped({"piezoRain": records}, [{"type": "49", "id": "ABC"}])
    assert "capacitor_voltage" not in result[49].readings
    assert result[49].readings["firmware_version"] == TextReading("1.1.8")


@pytest.mark.parametrize("value", [None, "--", "nan", "inf", -1, True, {}, "2.5 V"])
def test_invalid_voltage(value):
    """Reject missing, malformed and negative voltage values."""
    assert parse_voltage(value) is None


@pytest.mark.parametrize("value", [0, "0", 2.5, "2.5"])
def test_voltage(value):
    """Preserve valid voltage including an empty capacitor."""
    assert parse_voltage(value) == Reading(float(value), "V")


@pytest.mark.parametrize("value", [None, "--", "", True, 118, "1180", "1.1.8", "bad"])
def test_unrecognised_firmware_encoding(value):
    """Do not invent formatting for firmware encodings we have not verified."""
    assert parse_firmware_version(value) is None


async def test_named_property_lifecycle(
    hass,
    entry,
    aioclient_mock,
    live_payload,
    entity_registry,
    device_registry,
):
    """Discover independent diagnostics and retain device links through reload."""
    registrations = [{"type": "49", "id": "ABC"}]
    live_payload["piezoRain"] = [{"ws85cap_volt": "--", "ws85_ver": "118"}]
    responses(aioclient_mock, live_payload, [], registrations=registrations)
    await load(hass, entry)
    capacitor_uid = f"{MAC}::49::capacitor_voltage"
    assert entity_registry.async_get_entity_id("sensor", DOMAIN, capacitor_uid) is None
    version_id = entity_registry.async_get_entity_id(
        "sensor",
        DOMAIN,
        f"{MAC}::49::firmware_version",
    )
    assert hass.states.get(version_id).state == "1.1.8"

    live_payload["piezoRain"] = [{"wh85cap_volt": "2.5", "wh85_ver": "--"}]
    aioclient_mock.clear_requests()
    responses(aioclient_mock, live_payload, [], registrations=registrations)
    await refresh(hass, entry)
    capacitor_id = entity_registry.async_get_entity_id("sensor", DOMAIN, capacitor_uid)
    device = device_registry.async_get_device_by_identifier(
        (DOMAIN, f"{MAC}::49"),
        entry.entry_id,
    )
    assert entity_registry.async_get(capacitor_id).device_id == device.id
    assert entity_registry.async_get(version_id).device_id == device.id
    assert entity_registry.async_get(capacitor_id).entity_category.value == "diagnostic"
    state = hass.states.get(capacitor_id)
    assert float(state.state) == 2.5
    assert state.attributes["unit_of_measurement"] == "V"
    assert state.attributes["device_class"] == "voltage"
    assert state.attributes["state_class"] == "measurement"
    assert hass.states.get(version_id).state == "unknown"

    aioclient_mock.clear_requests()
    responses(aioclient_mock, live_payload, [], registrations=[])
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    for entity_id in (capacitor_id, version_id):
        assert hass.states.get(entity_id).state == "unknown"
        assert entity_registry.async_get(entity_id).device_id == device.id

    aioclient_mock.clear_requests()
    responses(aioclient_mock, live_payload, [], registrations=registrations)
    await refresh(hass, entry)
    assert float(hass.states.get(capacitor_id).state) == 2.5
