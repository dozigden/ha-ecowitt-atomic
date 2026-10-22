"""Diagnostics tests."""

import logging

from custom_components.ecowitt_atomic.api import GatewayError, UnsupportedGatewayError
from custom_components.ecowitt_atomic.const import DOMAIN
from custom_components.ecowitt_atomic.diagnostics import (
    async_get_config_entry_diagnostics,
)
from custom_components.ecowitt_atomic.models import TextReading
import pytest

from homeassistant.config_entries import ConfigEntryState
from homeassistant.setup import async_setup_component

from .conftest import MAC


@pytest.mark.parametrize(
    ("scenario", "expected_state"),
    [
        ("unload", ConfigEntryState.NOT_LOADED),
        ("connection_failure", ConfigEntryState.SETUP_RETRY),
        ("unsupported_gateway", ConfigEntryState.SETUP_ERROR),
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
    elif scenario == "unsupported_gateway":
        mock_api.async_get_info.side_effect = UnsupportedGatewayError(
            "unsupported model"
        )
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


async def test_mapped_metadata_stays_out_of_downloads(
    hass, entry, mock_api, live_payload, entity_registry
):
    """Text diagnostics stay visible as entities and excluded from downloads."""
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
