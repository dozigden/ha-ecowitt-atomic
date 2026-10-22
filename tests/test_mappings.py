"""Mapping composition using synthetic reading formats."""

from dataclasses import replace

from custom_components.ecowitt_atomic import api, gateway
from custom_components.ecowitt_atomic.mapping_engine import (
    ChannelRadioJoin,
    FieldReading,
    LiveGroup,
    MappingRule,
    apply_reading_mappings,
)
from custom_components.ecowitt_atomic.mappings import (
    READING_MAPPINGS,
    REGISTRATION_MAPPING,
)
from custom_components.ecowitt_atomic.models import Reading, TextReading
from custom_components.ecowitt_atomic.parsers import (
    parse_ecowitt_sensors,
    parse_percentage,
)
import pytest

from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .conftest import BASE_URL


@pytest.fixture
def registrations():
    """Provide identities without inferred reading capabilities."""
    return parse_ecowitt_sensors(
        [
            {"type": "847", "id": "ABC", "name": "Registered"},
            {"type": "985", "id": "DEF", "name": "Offline"},
        ]
    )


@pytest.fixture
def rule():
    """Use field names unrelated to the production soil format."""
    return MappingRule(
        source=LiveGroup("synthetic"),
        owner=ChannelRadioJoin(
            endpoint="get_test_metadata",
            live_channel="index",
            metadata_channel="number",
            metadata_radio_id="radio",
        ),
        readings=(
            FieldReading("first", "first_capability", parse_percentage),
            FieldReading("second", "second_capability", parse_percentage),
        ),
        name_field="label",
    )


@pytest.fixture
def metadata():
    """Link a channel to a radio ID with a different representation."""
    return {"get_test_metadata": [{"number": "3", "radio": "0x00abc"}]}


def test_fields_discover_independent_capabilities(rule, metadata, registrations):
    """One invalid reading must not suppress another or create a capability."""
    result = apply_reading_mappings(
        {
            "synthetic": [
                {
                    "index": "3",
                    "first": "--",
                    "second": "0%",
                    "unmapped": "80%",
                    "label": " New name ",
                }
            ]
        },
        metadata,
        registrations,
        (rule,),
        registrations=(),
    )
    assert result[847].readings == {"second_capability": Reading(0, "%")}
    assert result[847].name == "New name"
    assert result[847].registration_name == "Registered"
    assert result[985] == registrations[985]
    assert not registrations[847].readings
    assert registrations[847].name == "Registered"


@pytest.mark.parametrize("reverse", [False, True])
def test_groups_merge_on_identity(rule, metadata, registrations, reverse):
    """Different groups can supply capabilities for the same physical identity."""
    other = replace(
        rule,
        source=LiveGroup("another"),
        readings=(FieldReading("third", "third_capability", parse_percentage),),
    )
    rules = (other, rule) if reverse else (rule, other)
    result = apply_reading_mappings(
        {
            "synthetic": [{"index": "3", "first": "20%", "label": "Bed"}],
            "another": [{"index": "3", "third": "50%", "label": "Bed"}],
        },
        metadata,
        registrations,
        rules,
        registrations=(),
    )
    assert result[847].readings == {
        "first_capability": Reading(20, "%"),
        "third_capability": Reading(50, "%"),
    }
    assert result[847].name == "Bed"
    assert not result[985].readings


@pytest.mark.parametrize("reverse", [False, True])
@pytest.mark.parametrize("other_value", ["20%", "60%"])
def test_multiple_producers_do_not_overwrite(
    rule, metadata, registrations, reverse, other_value
):
    """Reject competing producers, including coincidentally equal readings."""
    other = replace(
        rule,
        source=LiveGroup("another"),
        readings=(FieldReading("value", "first_capability", parse_percentage),),
    )
    rules = (other, rule) if reverse else (rule, other)
    result = apply_reading_mappings(
        {
            "synthetic": [{"index": "3", "first": "20%", "second": "40%"}],
            "another": [{"index": "3", "value": other_value}],
        },
        metadata,
        registrations,
        rules,
        registrations=(),
    )
    assert result[847].readings == {"second_capability": Reading(40, "%")}


@pytest.mark.parametrize("reverse", [False, True])
def test_conflicting_names_do_not_depend_on_rule_order(
    rule, metadata, registrations, reverse
):
    """Keep independent readings without arbitrarily choosing a display name."""
    other = replace(
        rule,
        source=LiveGroup("another"),
        readings=(FieldReading("third", "third_capability", parse_percentage),),
    )
    result = apply_reading_mappings(
        {
            "synthetic": [{"index": "3", "first": "20%", "label": "One"}],
            "another": [{"index": "3", "third": "50%", "label": "Two"}],
        },
        metadata,
        registrations,
        (other, rule) if reverse else (rule, other),
        registrations=(),
    )
    assert result[847].name == "Registered"
    assert len(result[847].readings) == 2


@pytest.mark.parametrize(
    ("payload", "metadata"),
    [
        ({}, {}),
        ({"synthetic": None}, {}),
        ({"synthetic": [None, {"index": "3", "first": "25%"}]}, {}),
        (
            {"synthetic": [{"index": "3", "first": "25%"}]},
            {"get_test_metadata": [{"number": "3", "radio": "999"}]},
        ),
    ],
)
def test_missing_source_or_owner_clears_current_readings(
    rule, registrations, payload, metadata
):
    """Do not carry old values forward or manufacture an owner."""
    registrations[847] = replace(
        registrations[847], readings={"first_capability": Reading(10, "%")}
    )
    result = apply_reading_mappings(
        payload, metadata, registrations, (rule,), registrations=()
    )
    assert set(result) == set(registrations)
    assert all(not ecowitt_sensor.readings for ecowitt_sensor in result.values())
    assert registrations[847].readings == {"first_capability": Reading(10, "%")}


async def test_poll_fetches_declared_metadata_once(
    hass, aioclient_mock, monkeypatch, rule, metadata
):
    """The enabled mappings determine requests, including shared dependencies."""
    other = replace(
        rule,
        source=LiveGroup("another"),
        readings=(FieldReading("value", "third_capability", parse_percentage),),
    )
    separate = replace(
        other,
        source=LiveGroup("separate"),
        owner=replace(rule.owner, endpoint="get_other_metadata"),
    )
    monkeypatch.setattr(gateway, "READING_MAPPINGS", (rule, other, separate))
    aioclient_mock.get(
        f"{BASE_URL}/get_livedata_info",
        json={
            "synthetic": [{"index": "3", "first": "20%"}],
            "another": [{"index": "3", "value": "50%"}],
            "separate": [{"index": "3", "value": "80%"}],
        },
    )
    aioclient_mock.get(f"{BASE_URL}/get_version", json={"sensorid_page": "1"})
    aioclient_mock.get(
        f"{BASE_URL}/get_sensors_info?page=1",
        json=[{"type": "847", "id": "ABC"}, {"type": "985", "id": "DEF"}],
    )
    aioclient_mock.get(
        f"{BASE_URL}/get_test_metadata", json=metadata["get_test_metadata"]
    )
    aioclient_mock.get(
        f"{BASE_URL}/get_other_metadata",
        json=[{"number": "3", "radio": "DEF"}],
    )
    result = await gateway.async_read_gateway(
        api.EcowittApiClient(BASE_URL, async_get_clientsession(hass))
    )
    assert result.ecowitt_sensors[847].readings == {
        "first_capability": Reading(20, "%"),
        "third_capability": Reading(50, "%"),
    }
    assert result.ecowitt_sensors[985].readings == {
        "third_capability": Reading(80, "%")
    }
    assert aioclient_mock.call_count == 5


def test_registration_and_live_capabilities_share_identity():
    """Registration metadata and measurements contribute to the same device."""
    raw = [
        {"type": "847", "id": "0x00abc", "name": " Gateway label "},
        {"type": "985", "id": "DEF"},
        {"type": "99", "id": "FFFFFFFF", "name": "Unreceived"},
    ]
    result = apply_reading_mappings(
        {"ch_soil": [{"channel": "1", "humidity": "0%", "name": "Bed"}]},
        {"get_cli_soilad": [{"ch": "1", "id": "ABC"}]},
        parse_ecowitt_sensors(raw),
        READING_MAPPINGS,
        registrations=raw,
    )
    assert set(result) == {847, 985}
    assert result[847].name == "Bed"
    assert result[847].readings == {
        "soil_moisture": Reading(0, "%"),
        "gateway_name": TextReading("Gateway label"),
        "radio_id": TextReading("ABC"),
    }
    assert result[985].readings == {"radio_id": TextReading("DEF")}


@pytest.mark.parametrize("name", [None, "", " \t ", 123, False, {}, []])
def test_invalid_registration_name_supplies_no_text_capability(name):
    """Missing names still allow radio-ID diagnostics on a registered device."""
    raw = [{"type": "847", "id": "0x000abc", "name": name}]
    result = apply_reading_mappings(
        {}, {}, parse_ecowitt_sensors(raw), READING_MAPPINGS, registrations=raw
    )
    assert result[847].readings == {"radio_id": TextReading("ABC")}


def test_ambiguous_registration_identity_supplies_no_capabilities():
    """A duplicate type cannot gain diagnostic entities through its raw records."""
    raw = [
        {"type": "847", "id": "ABC", "name": "One"},
        {"type": "847", "id": "DEF", "name": "Two"},
    ]
    assert not apply_reading_mappings(
        {}, {}, parse_ecowitt_sensors(raw), READING_MAPPINGS, registrations=raw
    )


async def test_registration_mapping_needs_no_channel_metadata(
    hass, aioclient_mock, monkeypatch
):
    """Registration-only discovery uses the existing inventory requests."""
    monkeypatch.setattr(gateway, "READING_MAPPINGS", (REGISTRATION_MAPPING,))
    aioclient_mock.get(f"{BASE_URL}/get_livedata_info", json={})
    aioclient_mock.get(f"{BASE_URL}/get_version", json={"sensorid_page": "1"})
    aioclient_mock.get(
        f"{BASE_URL}/get_sensors_info?page=1",
        json=[{"type": "847", "id": "0x00abc", "name": "Offline"}],
    )
    result = await gateway.async_read_gateway(
        api.EcowittApiClient(BASE_URL, async_get_clientsession(hass))
    )
    assert result.ecowitt_sensors[847].readings == {
        "gateway_name": TextReading("Offline"),
        "radio_id": TextReading("ABC"),
    }
    assert aioclient_mock.call_count == 3
