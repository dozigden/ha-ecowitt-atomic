"""HTTP validation, URL normalization, and internal reading parsing."""

import aiohttp
import pytest

from custom_components.ecowitt_atomic.api import (
    EcowittApiClient,
    GatewayError,
    UnsupportedGateway,
    normalize_base_url,
    normalize_mac,
)
from custom_components.ecowitt_atomic.models import parse_internal_readings
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
    ],
)
def test_url_normalization(supplied, expected):
    assert normalize_base_url(supplied) == expected


@pytest.mark.parametrize(
    "supplied",
    [
        "",
        "http://",
        "ftp://gateway.example",
        "http://user:secret@gateway.example",
        "gateway.example/path",
        "gateway.example?key=value",
        "gateway.example#fragment",
        "gateway.example:99999",
        "gateway.example:bad",
        "two hosts",
        "http://[bad]",
    ],
)
def test_invalid_urls(supplied):
    with pytest.raises(ValueError):
        normalize_base_url(supplied)


def test_internal_readings_only(live_payload):
    readings = parse_internal_readings(live_payload)
    assert {key: reading.value for key, reading in readings.items()} == {
        "indoor_temperature": 21.5,
        "indoor_humidity": 55,
        "absolute_pressure": 1000,
        "relative_pressure": 1005,
    }


def test_converts_gateway_units(live_payload):
    live_payload["wh25"][0].update(
        intemp="68", unit="F", abs="29.53 inHg", rel="750.06 mmHg"
    )
    readings = parse_internal_readings(live_payload)
    assert readings["indoor_temperature"].value == 20
    assert readings["absolute_pressure"].value == pytest.approx(1000.02, abs=0.1)
    assert readings["relative_pressure"].value == pytest.approx(1000.0, abs=0.1)


@pytest.mark.parametrize("value", ["--", "", None, "NaN", "inf", True, [], {}])
def test_invalid_values_are_missing(live_payload, value):
    live_payload["wh25"][0].update(intemp=value, inhumi=value, abs=value, rel=value)
    assert parse_internal_readings(live_payload) == {}


def test_zero_is_valid_and_unitless_pressure_is_not(live_payload):
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
    assert parse_internal_readings(payload) == {}


async def test_http_api(hass, aioclient_mock, live_payload):
    client = EcowittApiClient(BASE_URL, async_get_clientsession(hass))
    aioclient_mock.get(
        f"{BASE_URL}/get_version", json={"version": "Version: GW2000A_V3.3.2"}
    )
    aioclient_mock.get(
        f"{BASE_URL}/get_network_info",
        json={"mac": "02-00-00-00-00-01", "ethIP": "192.0.2.1"},
    )
    aioclient_mock.get(f"{BASE_URL}/get_livedata_info", json=live_payload)
    info = await client.async_get_info()
    assert info.firmware == "3.3.2"
    assert info.mac == MAC
    assert (await client.async_get_readings())["indoor_temperature"].value == 21.5
    assert aioclient_mock.call_count == 3


@pytest.mark.parametrize(
    "value",
    ["02:ab:cd:ef:00:01", "02-AB-CD-EF-00-01", "02ABCDEF0001", "02ab.cdef.0001"],
)
def test_mac_normalization(value):
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
        {"exc": aiohttp.ClientConnectionError()},
        {"exc": TimeoutError()},
    ],
)
async def test_bad_http_response(hass, aioclient_mock, kwargs):
    aioclient_mock.get(f"{BASE_URL}/get_livedata_info", **kwargs)
    client = EcowittApiClient(BASE_URL, async_get_clientsession(hass))
    with pytest.raises(GatewayError):
        await client.async_get_readings()


@pytest.mark.parametrize("version", ["Version: GW3000_V1.0.0", "unexpected", None])
async def test_unverified_model_rejected(hass, aioclient_mock, version):
    aioclient_mock.get(f"{BASE_URL}/get_version", json={"version": version})
    client = EcowittApiClient(BASE_URL, async_get_clientsession(hass))
    with pytest.raises(UnsupportedGateway):
        await client.async_get_info()
