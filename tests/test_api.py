"""API and reading parser tests."""

import aiohttp
from custom_components.ecowitt_atomic.api import (
    EcowittApiClient,
    GatewayError,
    UnsupportedGatewayError,
    normalize_base_url,
    normalize_mac,
)
from custom_components.ecowitt_atomic.parsers import parse_internal_readings
import pytest

from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .conftest import BASE_URL, MAC


@pytest.mark.parametrize(
    ("supplied", "expected"),
    [
        (" Gateway.Example/ ", BASE_URL),
        ("HTTP://Gateway.Example:80///", BASE_URL),
        ("https://Gateway.Example:443/", "https://gateway.example"),
        ("gateway.example:8080", "http://gateway.example:8080"),
        ("[2001:db8::1]:8080", "http://[2001:db8::1]:8080"),
        ("192.0.2.1/", "http://192.0.2.1"),
        ("http://bücher.example/", "http://xn--bcher-kva.example"),
    ],
)
def test_url_normalization(supplied: str, expected: str) -> None:
    """Normalize equivalent connection addresses."""
    assert normalize_base_url(supplied) == expected


@pytest.mark.parametrize(
    ("supplied", "message"),
    [
        ("", "Enter a gateway host or base URL"),
        ("http://", "Enter an HTTP base URL"),
        ("ftp://gateway.example", "Enter an HTTP base URL"),
        ("http://user:secret@gateway.example", "Enter an HTTP base URL"),
        ("http://@gateway.example", "Enter an HTTP base URL"),
        ("gateway.example/path", "Enter an HTTP base URL"),
        ("gateway.example/path/..", "Enter an HTTP base URL"),
        ("gateway.example/%2F", "Enter an HTTP base URL"),
        ("gateway.example?key=value", "Enter an HTTP base URL"),
        ("gateway.example?", "Enter an HTTP base URL"),
        ("gateway.example#fragment", "Enter an HTTP base URL"),
        ("gateway.example#", "Enter an HTTP base URL"),
        ("gateway.example/\\", "Enter an HTTP base URL"),
        ("gateway.example:99999", "Port out of range"),
        ("gateway.example:bad", "port can't be converted"),
        ("two hosts", "Enter a gateway host or base URL"),
        ("http://[bad]", "IPv6 content between brackets is not valid"),
    ],
)
def test_invalid_urls(supplied: str, message: str) -> None:
    """Reject unsupported address forms."""
    with pytest.raises(ValueError, match=message):
        normalize_base_url(supplied)


def test_internal_readings_only(live_payload):
    """Exclude external Ecowitt sensor readings."""
    live_payload["common_list"] = [{"id": "0x02", "val": "8.0", "unit": "C"}]
    readings = parse_internal_readings(live_payload)
    assert {key: reading.value for key, reading in readings.items()} == {
        "indoor_temperature": 21.5,
        "indoor_humidity": 55,
        "absolute_pressure": 1000,
        "relative_pressure": 1005,
    }


def test_converts_gateway_units(live_payload):
    """Convert readings to canonical units."""
    live_payload["wh25"][0].update(
        intemp="68", unit="F", abs="29.53 inHg", rel="750.06 mmHg"
    )
    readings = parse_internal_readings(live_payload)
    assert readings["indoor_temperature"].value == 20
    assert readings["absolute_pressure"].value == pytest.approx(1000.02, abs=0.1)
    assert readings["relative_pressure"].value == pytest.approx(1000.0, abs=0.1)


@pytest.mark.parametrize("value", ["--", "", None, "NaN", "inf", True, [], {}])
def test_invalid_values_are_missing(live_payload, value):
    """Discard invalid readings."""
    live_payload["wh25"][0].update(intemp=value, inhumi=value, abs=value, rel=value)
    assert parse_internal_readings(live_payload) == {}


def test_zero_is_valid_and_unitless_pressure_is_not(live_payload):
    """Preserve zero readings and reject unitless pressure."""
    live_payload["wh25"][0].update(
        intemp="0", inhumi="0%", abs="1000", rel="1005 wrong"
    )
    readings = parse_internal_readings(live_payload)
    assert set(readings) == {"indoor_temperature", "indoor_humidity"}
    assert readings["indoor_humidity"].value == 0


@pytest.mark.parametrize(
    "payload", [{}, {"wh25": []}, {"wh25": "bad"}, {"wh25": [None]}]
)
def test_missing_indoor_group(payload):
    """Handle an absent or malformed indoor group."""
    assert parse_internal_readings(payload) == {}


async def test_http_api(hass, aioclient_mock, live_payload):
    """Read identity and preserve the live-data response without interpreting it."""
    client = EcowittApiClient(BASE_URL, async_get_clientsession(hass))
    aioclient_mock.get(
        f"{BASE_URL}/get_version", json={"version": "Version: GW2000A_V3.3.2"}
    )
    aioclient_mock.get(
        f"{BASE_URL}/get_network_info",
        json={"mac": "02-00-00-00-00-01", "ethIP": "192.0.2.1"},
    )
    aioclient_mock.get(f"{BASE_URL}/get_livedata_info", json=live_payload)
    for page in (1, 2):
        aioclient_mock.get(f"{BASE_URL}/get_sensors_info?page={page}", json=[])
    aioclient_mock.get(f"{BASE_URL}/get_cli_soilad", json=[])
    info = await client.async_get_info()
    assert info.firmware == "3.3.2"
    assert info.mac == MAC
    assert await client.async_get_live_data() == live_payload
    assert await client.async_get_registrations() == []
    assert await client.async_get_channel_metadata("get_cli_soilad") == []
    assert aioclient_mock.call_count == 7


async def test_registration_client_preserves_api_records(hass, aioclient_mock):
    """Pagination must not filter slots or interpret identities and readings."""
    first_page = [{"type": "14", "id": "FFFFFFFF", "name": "Unreceived"}]
    second_page = [{"type": "847", "id": "0x00abc", "name": "Unfamiliar"}]
    aioclient_mock.get(f"{BASE_URL}/get_version", json={"sensorid_page": "2"})
    for page, records in enumerate((first_page, second_page), start=1):
        aioclient_mock.get(f"{BASE_URL}/get_sensors_info?page={page}", json=records)
    client = EcowittApiClient(BASE_URL, async_get_clientsession(hass))
    assert await client.async_get_registrations() == first_page + second_page
    assert aioclient_mock.call_count == 3


async def test_channel_metadata_preserves_fields(hass, aioclient_mock):
    """The client supplies metadata without normalizing or parsing its fields."""
    records = [{"ch": "01", "id": "0x00abc", "soilVal": "30", "name": " Bed "}]
    aioclient_mock.get(f"{BASE_URL}/get_cli_soilad", json=records)
    client = EcowittApiClient(BASE_URL, async_get_clientsession(hass))
    assert await client.async_get_channel_metadata("get_cli_soilad") == records
    assert aioclient_mock.call_count == 1


@pytest.mark.parametrize(
    "value",
    ["02:ab:cd:ef:00:01", "02-AB-CD-EF-00-01", "02ABCDEF0001", "02ab.cdef.0001"],
)
def test_mac_normalization(value):
    """Normalize the supported MAC formats."""
    assert normalize_mac(value) == "02:ab:cd:ef:00:01"


@pytest.mark.parametrize(
    "value",
    [
        None,
        "",
        "--",
        "00:00:00:00:00:00",
        "ff:ff:ff:ff:ff:ff",
        "01:00:00:00:00:01",
        "not-a-mac",
        "02:00:00",
        {},
        1234,
    ],
)
async def test_invalid_mac_blocks_identification(hass, aioclient_mock, value):
    """Reject missing or invalid gateway identities."""
    aioclient_mock.get(
        f"{BASE_URL}/get_version", json={"version": "Version: GW2000A_V3.3.2"}
    )
    aioclient_mock.get(f"{BASE_URL}/get_network_info", json={"mac": value})
    client = EcowittApiClient(BASE_URL, async_get_clientsession(hass))
    with pytest.raises(GatewayError):
        await client.async_get_info()


@pytest.mark.parametrize(
    "kwargs",
    [
        {"status": 503},
        {"status": 302},
        {"text": "not json"},
        {"json": []},
        {"json": "gateway.example"},
        {"json": 123},
        {"json": False},
        {"exc": aiohttp.ClientConnectionError()},
        {"exc": TimeoutError()},
    ],
)
async def test_bad_http_response(hass, aioclient_mock, kwargs):
    """Report HTTP and decoding failures as gateway errors."""
    aioclient_mock.get(f"{BASE_URL}/get_livedata_info", **kwargs)
    client = EcowittApiClient(BASE_URL, async_get_clientsession(hass))
    with pytest.raises(GatewayError):
        await client.async_get_live_data()


@pytest.mark.parametrize("version", ["unexpected", None])
async def test_unrecognised_identity_rejected(hass, aioclient_mock, version):
    """Reject responses that cannot identify a gateway."""
    aioclient_mock.get(f"{BASE_URL}/get_version", json={"version": version})
    client = EcowittApiClient(BASE_URL, async_get_clientsession(hass))
    with pytest.raises(UnsupportedGatewayError):
        await client.async_get_info()


async def test_client_decodes_other_gateway_models(hass, aioclient_mock):
    """Decode gateway identity for the support check."""
    aioclient_mock.get(
        f"{BASE_URL}/get_version", json={"version": "Version: GW3000_V1.0.0"}
    )
    aioclient_mock.get(f"{BASE_URL}/get_network_info", json={"mac": MAC})
    info = await EcowittApiClient(
        BASE_URL, async_get_clientsession(hass)
    ).async_get_info()
    assert (info.model, info.firmware, info.mac) == ("GW3000", "1.0.0", MAC)
