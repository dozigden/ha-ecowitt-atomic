"""Discovery from registrations and API-provided soil channel identities."""

from custom_components.ecowitt_atomic.api import EcowittApiClient, GatewayError
from custom_components.ecowitt_atomic.gateway import async_read_gateway
from custom_components.ecowitt_atomic.mapping_engine import apply_reading_mappings
from custom_components.ecowitt_atomic.mappings import SOIL_MOISTURE_MAPPING
from custom_components.ecowitt_atomic.parsers import parse_ecowitt_sensors
import pytest

from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .conftest import BASE_URL


def parse(registrations, live, metadata):
    """Apply identity discovery before reading attribution."""
    return apply_reading_mappings(
        live,
        {"get_cli_soilad": metadata},
        parse_ecowitt_sensors(registrations),
        (SOIL_MOISTURE_MAPPING,),
        registrations=registrations,
    )


@pytest.mark.parametrize(("channel", "slot"), [(1, 847), (8, 3), (9, 101), (16, 6)])
def test_soil_ownership_comes_from_radio_id(channel, slot):
    """Ignore model, type meaning, names, array order and familiar slot numbers."""
    registrations = [
        {"type": "14", "id": "AAA", "img": "wh51", "name": "Soil moisture CH1"},
        {"type": str(slot), "id": "0X000123", "img": "unfamiliar", "name": "Other"},
    ]
    live = {
        "ch_soil": [{"channel": str(channel), "humidity": "0%", "name": "Bed"}],
        "ch_aisle": [{"channel": str(channel), "humidity": "95%"}],
    }
    metadata = [{"ch": str(channel), "id": "0x123", "soilVal": "99"}]
    result = parse(registrations, live, metadata)
    assert set(result) == {14, slot}
    assert not result[14].readings
    assert result[slot].radio_id == "123"
    assert result[slot].name == "Bed"
    assert result[slot].registration_name == "Other"
    assert result[slot].readings["soil_moisture"].value == 0
    assert result[slot].readings["soil_moisture"].unit == "%"


def test_registration_discovery_is_independent_of_reading_support():
    """Retain unfamiliar identities without inferring capabilities."""
    result = parse_ecowitt_sensors(
        [
            {"type": "847", "id": "ABC", "img": "unfamiliar", "name": "New hardware"},
            {"type": "14", "id": "DEF", "img": "wh51", "name": "Soil moisture CH1"},
            {"type": "6", "id": "123", "name": "Temperature"},
        ]
    )
    assert set(result) == {847, 14, 6}
    assert all(not ecowitt_sensor.readings for ecowitt_sensor in result.values())


@pytest.mark.parametrize(
    "value", ["--", "", None, "NaN", "inf", True, {}, [], "101%", "-1%", "12 C"]
)
def test_invalid_live_reading_is_not_replaced_by_calibration(value):
    """Identity and calibration values alone supply no reading capability."""
    result = parse(
        [{"type": "847", "id": "ABC", "name": "Registered"}],
        {"ch_soil": [{"channel": "1", "humidity": value}]},
        [{"ch": "1", "id": "0xABC", "soilVal": "50", "nowAd": "200"}],
    )
    assert result[847].name == "Registered"
    assert not result[847].readings


@pytest.mark.parametrize(
    "radio_id", ["FFFFFFFF", "0xfffffffe", "--", None, True, "not hex"]
)
def test_invalid_registration_id_is_not_a_physical_identity(radio_id):
    """Exclude sentinel and malformed radio IDs independently of type."""
    assert not parse_ecowitt_sensors([{"type": "847", "id": radio_id}])


@pytest.mark.parametrize(
    "metadata",
    [
        [],
        [{"ch": "2", "id": "ABC"}],
        [{"ch": "1", "id": "DEF"}],
        [{"ch": "1", "id": "FFFFFFFF"}],
        [{"ch": "1", "id": "--"}],
    ],
)
def test_missing_or_invalid_metadata_does_not_fall_back_to_type(metadata):
    """Even the familiar CH1/type14 combination requires an explicit link."""
    result = parse(
        [{"type": "14", "id": "ABC", "img": "wh51"}],
        {"ch_soil": [{"channel": "1", "humidity": "30%"}]},
        metadata,
    )
    assert not result[14].readings


def test_no_live_soil_group_does_not_discover_from_metadata():
    """Neither calibration data nor another group's humidity implies moisture."""
    result = parse(
        [{"type": "847", "id": "ABC"}],
        {"ch_aisle": [{"channel": "1", "humidity": "70%"}]},
        [{"ch": "1", "id": "ABC", "soilVal": "30"}],
    )
    assert not result[847].readings


@pytest.mark.parametrize(
    "duplicate",
    [
        "registration_type",
        "registration_radio",
        "metadata_channel",
        "metadata_radio",
        "live_channel",
    ],
)
def test_ambiguous_ownership_is_not_guessed(duplicate):
    """Reject ambiguous joins without relying on a radio ID uniqueness assumption."""
    registrations = [{"type": "847", "id": "ABC"}]
    metadata = [{"ch": "1", "id": "0xABC"}]
    channels = [{"channel": "1", "humidity": "30%"}]
    if duplicate == "registration_type":
        registrations.append({"type": "847", "id": "DEF"})
    elif duplicate == "registration_radio":
        registrations.append({"type": "14", "id": "0X00abc", "img": "wh51"})
    elif duplicate == "metadata_channel":
        metadata.append({"ch": "1", "id": "DEF"})
    elif duplicate == "metadata_radio":
        metadata.append({"ch": "2", "id": "ABC"})
        channels.append({"channel": "2", "humidity": "40%"})
    else:
        channels.append({"channel": "1", "humidity": "40%"})
    result = parse(registrations, {"ch_soil": channels}, metadata)
    assert all(not ecowitt_sensor.readings for ecowitt_sensor in result.values())


@pytest.mark.parametrize("page_count", [2, 4])
async def test_registration_pagination_and_soil_metadata(
    hass, aioclient_mock, live_payload, page_count
):
    """Join metadata with a registration found on the last reported page."""
    live_payload["ch_soil"] = [{"channel": "1", "humidity": "37%"}]
    aioclient_mock.get(f"{BASE_URL}/get_livedata_info", json=live_payload)
    aioclient_mock.get(
        f"{BASE_URL}/get_version", json={"sensorid_page": str(page_count)}
    )
    for page in range(1, page_count + 1):
        records = [{"type": "847", "id": "ABC"}] if page == page_count else []
        aioclient_mock.get(f"{BASE_URL}/get_sensors_info?page={page}", json=records)
    aioclient_mock.get(
        f"{BASE_URL}/get_cli_soilad", json=[{"ch": "1", "id": "0x00abc"}]
    )
    aioclient_mock.get(f"{BASE_URL}/get_cli_multiCh", json=[])
    aioclient_mock.get(f"{BASE_URL}/get_cli_wh34", json=[])
    result = await async_read_gateway(
        EcowittApiClient(BASE_URL, async_get_clientsession(hass))
    )
    assert result.ecowitt_sensors[847].readings["soil_moisture"].value == 37
    assert result.gateway["indoor_temperature"].value == 21.5
    assert aioclient_mock.call_count == 5 + page_count


@pytest.mark.parametrize("page_count", ["0", "17", "garbage", "2.5", True, None, []])
async def test_invalid_pagination_fails_poll(hass, aioclient_mock, page_count):
    """Do not silently accept a partial registration inventory."""
    aioclient_mock.get(f"{BASE_URL}/get_livedata_info", json={})
    aioclient_mock.get(f"{BASE_URL}/get_version", json={"sensorid_page": page_count})
    with pytest.raises(GatewayError, match="page count"):
        await EcowittApiClient(
            BASE_URL, async_get_clientsession(hass)
        ).async_get_registrations()


@pytest.mark.parametrize(
    "endpoint",
    ["get_sensors_info?page=1", "get_cli_soilad", "get_cli_multiCh", "get_cli_wh34"],
)
@pytest.mark.parametrize("records", [{}, [None], "invalid"])
async def test_invalid_metadata_fails_poll(hass, aioclient_mock, endpoint, records):
    """Reject malformed registration and soil channel metadata responses."""
    aioclient_mock.get(f"{BASE_URL}/get_livedata_info", json={})
    aioclient_mock.get(f"{BASE_URL}/get_version", json={"sensorid_page": "1"})
    aioclient_mock.get(
        f"{BASE_URL}/get_sensors_info?page=1",
        json=records if endpoint.startswith("get_sensors_info") else [],
    )
    aioclient_mock.get(
        f"{BASE_URL}/get_cli_soilad",
        json=records if endpoint == "get_cli_soilad" else [],
    )
    aioclient_mock.get(
        f"{BASE_URL}/get_cli_multiCh",
        json=records if endpoint == "get_cli_multiCh" else [],
    )
    aioclient_mock.get(
        f"{BASE_URL}/get_cli_wh34",
        json=records if endpoint == "get_cli_wh34" else [],
    )
    with pytest.raises(GatewayError, match="metadata"):
        await async_read_gateway(
            EcowittApiClient(BASE_URL, async_get_clientsession(hass))
        )
