"""Diagnostics downloads remain usable when gateway setup is not loaded."""

import logging

import pytest

from custom_components.ecowitt_atomic.api import GatewayError, UnsupportedGateway
from homeassistant.config_entries import ConfigEntryState
from homeassistant.setup import async_setup_component


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
    # Access-log timestamp formatting is incompatible with the frozen test clock.
    caplog.set_level(logging.WARNING, logger="aiohttp.access")
    assert await async_setup_component(hass, "diagnostics", {})
    entry.add_to_hass(hass)
    if scenario == "connection_failure":
        mock_api.async_get_info.side_effect = GatewayError("private connection detail")
    elif scenario == "unsupported_gateway":
        mock_api.async_get_info.side_effect = UnsupportedGateway("unsupported model")
    elif scenario == "reading_request_failure":
        mock_api.async_get_readings.side_effect = GatewayError("reading request failed")

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
