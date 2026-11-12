"""Diagnostics tests."""

from copy import deepcopy
import logging
from unittest.mock import patch

from custom_components.ecowitt_atomic.api import GatewayError, InvalidGatewayError
from custom_components.ecowitt_atomic.const import DOMAIN
from custom_components.ecowitt_atomic.diagnostics import (
    async_get_config_entry_diagnostics,
)
from custom_components.ecowitt_atomic.models import TextReading
import pytest

from homeassistant.config_entries import ConfigEntryState
from homeassistant.setup import async_setup_component

from .conftest import BASE_URL, MAC


@pytest.fixture
def raw_responses(live_payload):
    """Provide unrecognised fields alongside explicit ownership links."""
    return {
        "get_livedata_info": {
            **live_payload,
            "common_list": [{"id": "0x02", "val": "8.0", "unit": "C"}],
            "ch_soil": [{"channel": "1", "humidity": "30%", "name": "Live label"}],
            "unrecognised_group": [{"reading": "12.34", "flags": [False, None, 0]}],
        },
        "get_version": {"version": "Version: GW2000A_V3.3.2", "sensorid_page": "2"},
        "get_sensors_info?page=1": [
            {"type": "847", "id": "0x00abc", "name": "Private label", "img": "wh51"},
            {"type": "999", "id": "ABC123", "img": "unrecognised", "extra": "kept"},
        ],
        "get_sensors_info?page=2": [
            {"type": "848", "id": "fffffffe"},
            {"type": "849", "id": "FFFFFFFF"},
        ],
        "get_cli_soilad": [{"ch": "1", "id": "ABC", "name": "Soil label"}],
        "get_cli_multiCh": [],
        "get_cli_wh34": [],
    }


@pytest.fixture
async def loaded_raw_gateway(hass, entry, aioclient_mock, raw_responses):
    """Set up a gateway through the real API client using synthetic JSON."""
    aioclient_mock.get(f"{BASE_URL}/get_network_info", json={"mac": MAC})
    for endpoint, payload in raw_responses.items():
        aioclient_mock.get(f"{BASE_URL}/{endpoint}", json=payload)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_raw_batch_download(
    hass, loaded_raw_gateway, aioclient_mock, raw_responses, hass_client, caplog
):
    """Download every poll response unchanged, including names and unknown fields."""
    caplog.set_level(logging.WARNING, logger="aiohttp.access")
    assert await async_setup_component(hass, "diagnostics", {})
    entry = loaded_raw_gateway
    coordinator = entry.runtime_data.coordinator
    calls_before = aioclient_mock.call_count
    saved_batch = deepcopy(coordinator.raw_api)

    client = await hass_client()
    response = await client.get(f"/api/diagnostics/config_entry/{entry.entry_id}")
    assert response.status == 200
    diagnostics = (await response.json())["data"]
    raw = diagnostics["raw_api"]
    assert raw == {
        "captured_at": "2026-10-17T12:00:00+00:00",
        "complete": True,
        "responses": raw_responses,
    }
    assert aioclient_mock.call_count == calls_before
    assert coordinator.raw_api == saved_batch
    assert coordinator.raw_api.responses == raw_responses
    assert coordinator.data.ecowitt_sensors[847].radio_id == "ABC"
    assert diagnostics["ecowitt_sensors"]["847"]["soil_moisture"]["value"] == 30


@pytest.mark.parametrize(
    ("kwargs", "captured"),
    [
        ({"status": 500, "text": "private error body"}, False),
        ({"text": "not JSON"}, False),
        ({"exc": TimeoutError()}, False),
        ({"json": {"unexpected": ["shape"]}}, True),
    ],
)
async def test_failed_batch_and_recovery(
    hass, loaded_raw_gateway, aioclient_mock, raw_responses, freezer, kwargs, captured
):
    """Replace old responses after failure, retaining decoded malformed JSON."""
    coordinator = loaded_raw_gateway.runtime_data.coordinator
    aioclient_mock.clear_requests()
    for endpoint in ("get_livedata_info", "get_version", "get_sensors_info?page=1"):
        aioclient_mock.get(f"{BASE_URL}/{endpoint}", json=raw_responses[endpoint])
    failed_endpoint = "get_sensors_info?page=2"
    aioclient_mock.get(f"{BASE_URL}/{failed_endpoint}", **kwargs)
    freezer.tick(1)
    await coordinator.async_refresh()
    diagnostics = await async_get_config_entry_diagnostics(hass, loaded_raw_gateway)
    raw = diagnostics["raw_api"]
    assert not diagnostics["last_poll_successful"]
    assert not raw["complete"]
    assert raw["captured_at"] == "2026-10-17T12:00:01+00:00"
    expected_endpoints = {"get_livedata_info", "get_version", "get_sensors_info?page=1"}
    if captured:
        expected_endpoints.add(failed_endpoint)
        assert raw["responses"][failed_endpoint] == kwargs["json"]
    assert set(raw["responses"]) == expected_endpoints
    assert "private error body" not in str(diagnostics)

    aioclient_mock.clear_requests()
    for endpoint, payload in raw_responses.items():
        aioclient_mock.get(f"{BASE_URL}/{endpoint}", json=payload)
    freezer.tick(1)
    await coordinator.async_refresh()
    assert coordinator.last_update_success
    assert coordinator.raw_api.complete
    assert coordinator.raw_api.captured_at == "2026-10-17T12:00:02+00:00"
    assert coordinator.raw_api.responses == raw_responses


async def test_inflight_batch_is_not_exposed(
    hass, loaded_raw_gateway, aioclient_mock, raw_responses
):
    """A download during polling sees the previous finished batch."""
    coordinator = loaded_raw_gateway.runtime_data.coordinator
    previous = await async_get_config_entry_diagnostics(hass, loaded_raw_gateway)
    aioclient_mock.clear_requests()
    for endpoint, payload in raw_responses.items():
        aioclient_mock.get(
            f"{BASE_URL}/{endpoint}",
            json={"new_poll": True} if endpoint == "get_livedata_info" else payload,
        )
    get_registrations = coordinator.client.async_get_registrations

    async def inspect_during_poll():
        """Inspect after live data arrives but before the rest of the batch."""
        assert (
            await async_get_config_entry_diagnostics(hass, loaded_raw_gateway)
            == previous
        )
        return await get_registrations()

    with patch.object(
        coordinator.client, "async_get_registrations", inspect_during_poll
    ):
        await coordinator.async_refresh()
    assert coordinator.raw_api.responses["get_livedata_info"] == {"new_poll": True}


@pytest.mark.parametrize(
    ("scenario", "expected_state"),
    [
        ("unload", ConfigEntryState.NOT_LOADED),
        ("connection_failure", ConfigEntryState.SETUP_RETRY),
        ("invalid_gateway", ConfigEntryState.SETUP_ERROR),
        ("reading_request_failure", ConfigEntryState.SETUP_RETRY),
    ],
)
async def test_download_without_runtime_data(
    hass, entry, mock_api, hass_client, caplog, scenario, expected_state
):
    # aiohttp's access logger cannot format the frozen test clock.
    """Download diagnostics after unload or setup failure."""
    caplog.set_level(logging.WARNING, logger="aiohttp.access")
    assert await async_setup_component(hass, "diagnostics", {})
    entry.add_to_hass(hass)
    if scenario == "connection_failure":
        mock_api.async_get_info.side_effect = GatewayError("private connection detail")
    elif scenario == "invalid_gateway":
        mock_api.async_get_info.side_effect = InvalidGatewayError("invalid version")
    elif scenario == "reading_request_failure":
        mock_api.async_get_live_data.side_effect = GatewayError(
            "reading request failed"
        )

    loaded = await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    if scenario == "unload":
        assert loaded
        assert await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()
    else:
        assert not loaded
    assert entry.state is expected_state
    assert not hasattr(entry, "runtime_data")

    client = await hass_client()
    response = await client.get(f"/api/diagnostics/config_entry/{entry.entry_id}")
    assert response.status == 200
    assert (await response.json())["data"] == {
        "state": expected_state.value,
        "readings": {},
    }


async def test_mapped_metadata_stays_out_of_parsed_diagnostics(
    hass, entry, mock_api, live_payload, entity_registry
):
    """Text diagnostics stay visible as entities and excluded from parsed readings."""
    mock_api.async_get_live_data.return_value = {
        **live_payload,
        "ch_soil": [{"channel": "1", "humidity": "30%", "name": "Live label"}],
    }
    mock_api.async_get_registrations.return_value = [
        {"type": "847", "id": "0x00abc", "name": "Private label", "img": "wh51"}
    ]
    mock_api.async_get_channel_metadata.return_value = [{"ch": "1", "id": "ABC"}]
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    values = entry.runtime_data.coordinator.data.ecowitt_sensors[847].readings
    for key, expected in (("gateway_name", "Private label"), ("radio_id", "ABC")):
        assert values[key] == TextReading(expected)
        entity_id = entity_registry.async_get_entity_id(
            "sensor", DOMAIN, f"{MAC}::847::{key}"
        )
        assert hass.states.get(entity_id).state == expected

    diagnostics = await async_get_config_entry_diagnostics(hass, entry)
    assert diagnostics["ecowitt_sensors"] == {
        "847": {"soil_moisture": {"value": 30.0, "unit": "%"}}
    }
    assert all(
        private not in str(diagnostics)
        for private in (
            "Private label",
            "Live label",
            "ABC",
            "gateway_name",
            "radio_id",
        )
    )
