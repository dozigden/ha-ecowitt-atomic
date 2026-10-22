"""Shared weather observations stay with their gateway."""

from custom_components.ecowitt_atomic.api import GatewayError
from custom_components.ecowitt_atomic.const import DOMAIN
from custom_components.ecowitt_atomic.diagnostics import (
    async_get_config_entry_diagnostics,
)
from custom_components.ecowitt_atomic.mapping_engine import apply_gateway_mappings
from custom_components.ecowitt_atomic.mappings import GATEWAY_READING_MAPPINGS
from custom_components.ecowitt_atomic.models import Reading
from custom_components.ecowitt_atomic.parsers import (
    parse_rain_depth,
    parse_rain_rate,
    parse_vpd,
    parse_wind_direction,
    parse_wind_speed,
)
import pytest

from homeassistant.helpers import entity_registry as er

from .conftest import MAC
from .test_integration import entity_id, setup


def observations(payload):
    """Interpret the gateway's shared reading groups."""
    return apply_gateway_mappings(payload, GATEWAY_READING_MAPPINGS)


@pytest.mark.parametrize(
    ("parser", "value", "expected", "unit"),
    [
        (parse_wind_speed, "0.0 m/s", 0, "m/s"),
        (parse_wind_speed, "36 km/h", 10, "m/s"),
        (parse_wind_speed, "10 mph", 4.4704, "m/s"),
        (parse_wind_speed, "10 knots", 18520 / 3600, "m/s"),
        (parse_rain_depth, "1.0 in", 25.4, "mm"),
        (parse_rain_depth, "0.0 mm", 0, "mm"),
        (parse_rain_rate, "2 in/Hr", 50.8, "mm/h"),
        (parse_rain_rate, "1.2 mm/Hr", 1.2, "mm/h"),
        (parse_vpd, "0.158 kPa", 0.158, "kPa"),
        (parse_wind_direction, "0", 0, "°"),
        (parse_wind_direction, "360", 360, "°"),
    ],
)
def test_units(parser, value, expected, unit):
    """Convert readings while preserving calm wind and zero rain."""
    reading = parser(value)
    assert reading.value == pytest.approx(expected)
    assert reading.unit == unit


@pytest.mark.parametrize(
    "parser",
    [
        parse_wind_speed,
        parse_rain_depth,
        parse_rain_rate,
        parse_vpd,
        parse_wind_direction,
    ],
)
@pytest.mark.parametrize(
    "value", [None, True, "--", "nan", "inf", {}, "-1", "-1 mm", "1 wrong"]
)
def test_invalid_values(parser, value):
    """Reject missing, nonfinite, negative and unsupported values."""
    assert parser(value) is None


def test_shared_mapping_context():
    """Preserve literal IDs and separate conventional and piezo rainfall."""
    result = observations(
        {
            "common_list": [
                {"id": "0x02", "val": "68", "unit": "F"},
                {"id": "0x07", "val": "83%"},
                {"id": "0x03", "val": "3.2", "unit": "C"},
                {"id": "3", "val": "5.9", "unit": "C"},
                {"id": "4", "val": "4.1", "unit": "C"},
                {"id": "5", "val": "0.158 kPa"},
                {"id": "0x0B", "val": "0.0 m/s"},
                {"id": "0x0C", "val": "1.0 m/s"},
                {"id": "0x19", "val": "2.0 m/s"},
                {"id": "0x0A", "val": "120"},
                {"id": "0x6D", "val": "180"},
                {"id": "unknown", "val": "42"},
            ],
            "rain": [{"id": "0x7D", "val": "1 in"}, {"id": "0x10", "val": "2 in"}],
            "piezoRain": [
                {"id": "0x7D", "val": "3 mm"},
                {"id": "0x10", "val": "4 mm"},
                {"id": "srain_piezo", "val": "2"},
                {"id": "0x13", "val": "223.8 mm", "ws85_ver": "116", "ws90_ver": "100"},
            ],
        }
    )
    assert {key: reading.value for key, reading in result.items()} == {
        "outdoor_temperature": 20,
        "outdoor_humidity": 83,
        "dew_point": 3.2,
        "feels_like": 5.9,
        "apparent_temperature": 4.1,
        "vpd": 0.158,
        "wind_speed": 0,
        "wind_gust": 1,
        "wind_daily_maximum": 2,
        "wind_direction": 120,
        "wind_direction_10_minute_average": 180,
        "rain_hour": 25.4,
        "rain_day": 50.8,
        "piezo_rain_hour": 3,
        "piezo_rain_day": 4,
        "piezo_rain_year": 223.8,
    }


@pytest.mark.parametrize("group", [None, {}, "bad", [None, 1, []]])
def test_malformed_groups(group):
    """Malformed groups do not prevent other gateway readings."""
    assert observations({"common_list": group, "rain": group, "piezoRain": group}) == {}


def test_duplicate_and_unrecognised_ids():
    """Reject duplicate records without confusing decimal and hexadecimal IDs."""
    assert observations(
        {
            "common_list": [
                {"id": "0x02", "val": "20", "unit": "C"},
                {"id": "0x02", "val": "--", "unit": "C"},
                {"id": 3, "val": "18", "unit": "C"},
                {"id": "0x05", "val": "4 kPa"},
                {"id": "0x0A", "val": "361"},
                {"id": "0x07", "val": "0%"},
            ]
        }
    ) == {"outdoor_humidity": Reading(0, "%")}


@pytest.mark.no_fail_on_log_exception
async def test_gateway_discovery_and_source_changes(
    hass, entry, mock_api, live_payload, entity_registry, device_registry
):
    """Retain gateway entities through source changes, missing data and reload."""
    live_payload["common_list"] = [{"id": "0x02", "val": "--", "unit": "C"}]
    mock_api.async_get_registrations.return_value = [{"type": "5", "id": "ABC"}]
    await setup(hass, entry)
    assert entity_id(entity_registry, "outdoor_temperature") is None

    live_payload["common_list"] = [
        {"id": "0x02", "val": "8", "unit": "C"},
        {"id": "0x0A", "val": "350"},
    ]
    live_payload["piezoRain"] = [
        {"id": "0x10", "val": "12.3 mm", "ws85_ver": "116"},
        {"id": "0x7D", "val": "1.2 mm"},
    ]
    await entry.runtime_data.coordinator.async_refresh()
    await hass.async_block_till_done()
    keys = [
        "outdoor_temperature",
        "wind_direction",
        "piezo_rain_day",
        "piezo_rain_hour",
    ]
    ids = {key: entity_id(entity_registry, key) for key in keys}
    gateway = device_registry.async_get_device_by_identifier(
        (DOMAIN, MAC), entry.entry_id
    )
    assert all(
        entity_registry.async_get(eid).device_id == gateway.id for eid in ids.values()
    )
    assert hass.states.get(ids["outdoor_temperature"]).state == "8.0"
    assert (
        hass.states.get(ids["wind_direction"]).attributes["state_class"]
        == "measurement_angle"
    )
    assert (
        hass.states.get(ids["piezo_rain_day"]).attributes["state_class"]
        == "total_increasing"
    )
    assert "state_class" not in hass.states.get(ids["piezo_rain_hour"]).attributes
    assert all(
        len(e.unique_id.split("::")) == 2
        for e in er.async_entries_for_config_entry(entity_registry, entry.entry_id)
        if e.unique_id.endswith(tuple(keys))
    )

    mock_api.async_get_registrations.return_value = [{"type": "48", "id": "DEF"}]
    live_payload["common_list"][0]["val"] = "9"
    live_payload["piezoRain"][0] = {"id": "0x10", "val": "13 mm", "ws90_ver": "100"}
    await entry.runtime_data.coordinator.async_refresh()
    await hass.async_block_till_done()
    assert {key: entity_id(entity_registry, key) for key in keys} == ids
    assert hass.states.get(ids["outdoor_temperature"]).state == "9.0"
    assert hass.states.get(ids["piezo_rain_day"]).state == "13.0"
    diagnostics = await async_get_config_entry_diagnostics(hass, entry)
    assert diagnostics["readings"]["piezo_rain_day"] == {"value": 13, "unit": "mm"}
    assert "piezo_rain_day" not in diagnostics["ecowitt_sensors"]["48"]

    live_payload.pop("common_list")
    live_payload.pop("piezoRain")
    mock_api.async_get_registrations.return_value = []
    await entry.runtime_data.coordinator.async_refresh()
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert {key: entity_id(entity_registry, key) for key in keys} == ids
    assert all(hass.states.get(eid).state == "unknown" for eid in ids.values())
    assert all(
        entity_registry.async_get(eid).device_id == gateway.id for eid in ids.values()
    )

    mock_api.async_get_live_data.side_effect = GatewayError("offline")
    await entry.runtime_data.coordinator.async_refresh()
    await hass.async_block_till_done()
    assert all(hass.states.get(eid).state == "unavailable" for eid in ids.values())
    mock_api.async_get_live_data.side_effect = None
    live_payload["common_list"] = [{"id": "0x02", "val": "10", "unit": "C"}]
    await entry.runtime_data.coordinator.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get(ids["outdoor_temperature"]).state == "10.0"
