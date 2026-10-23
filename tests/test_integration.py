"""Integration lifecycle tests."""

from datetime import timedelta
from unittest.mock import AsyncMock, patch

from custom_components.ecowitt_atomic import async_remove_config_entry_device
from custom_components.ecowitt_atomic.api import (
    EcowittApiClient,
    GatewayError,
    UnsupportedGatewayError,
)
from custom_components.ecowitt_atomic.const import CONF_BASE_URL, CONF_MAC, DOMAIN
from custom_components.ecowitt_atomic.diagnostics import (
    async_get_config_entry_diagnostics,
)
from custom_components.ecowitt_atomic.models import GatewayInfo
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from homeassistant.config_entries import ConfigEntryState
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.util import dt as dt_util

from .conftest import BASE_URL, MAC, SECOND_MAC

pytestmark = pytest.mark.usefixtures("mock_api")


async def setup(hass, entry):
    """Load a gateway entry and its entities."""
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


def entity_id(entity_registry, key, mac=MAC):
    """Find a reading's entity through its unique ID."""
    return entity_registry.async_get_entity_id("sensor", DOMAIN, f"{mac}::{key}")


async def advance(hass, freezer, seconds):
    """Advance the clock and run scheduled updates."""
    freezer.tick(timedelta(seconds=seconds))
    async_fire_time_changed(hass, dt_util.utcnow())
    await hass.async_block_till_done()


async def test_setup_and_unload(
    hass, entry, mock_api, device_registry, entity_registry, freezer
):
    """Create gateway entities and stop polling on unload."""
    await setup(hass, entry)
    assert entry.state is ConfigEntryState.LOADED
    devices = dr.async_entries_for_config_entry(device_registry, entry.entry_id)
    assert len(devices) == 1
    assert devices[0].identifiers == {(DOMAIN, MAC)}
    assert devices[0].connections == {(dr.CONNECTION_NETWORK_MAC, MAC)}
    assert devices[0].model == "GW2000A"
    assert devices[0].name == "GW2000A (020000000001)"
    assert devices[0].sw_version == "3.3.2"
    assert devices[0].configuration_url == BASE_URL
    entities = er.async_entries_for_config_entry(entity_registry, entry.entry_id)
    assert len(entities) == 4
    assert {item.device_id for item in entities} == {devices[0].id}
    temperature_id = entity_id(entity_registry, "indoor_temperature")
    state = hass.states.get(temperature_id)
    assert state.state == "21.5"
    assert state.attributes["unit_of_measurement"] == "°C"
    assert state.attributes["device_class"] == "temperature"
    assert state.attributes["state_class"] == "measurement"
    await advance(hass, freezer, 30)
    assert mock_api.async_get_live_data.await_count == 1
    await advance(hass, freezer, 31)
    assert mock_api.async_get_live_data.await_count == 2
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    count = mock_api.async_get_live_data.await_count
    await advance(hass, freezer, 100)
    assert mock_api.async_get_live_data.await_count == count
    assert len(er.async_entries_for_config_entry(entity_registry, entry.entry_id)) == 4


@pytest.mark.parametrize("remaining_readings", [{"inhumi": "60%"}, {}])
async def test_missing_readings_become_unknown(
    hass, entry, mock_api, entity_registry, freezer, remaining_readings
):
    """Clear omitted readings without deleting entities."""
    await setup(hass, entry)
    temp_id = entity_id(entity_registry, "indoor_temperature")
    humidity_id = entity_id(entity_registry, "indoor_humidity")
    mock_api.async_get_live_data.return_value = {"wh25": [remaining_readings]}
    await advance(hass, freezer, 61)
    assert entry.runtime_data.coordinator.last_update_success
    assert hass.states.get(temp_id).state == "unknown"
    assert hass.states.get(humidity_id).state == (
        "60.0" if "inhumi" in remaining_readings else "unknown"
    )
    assert len(er.async_entries_for_config_entry(entity_registry, entry.entry_id)) == 4
    diagnostics = await async_get_config_entry_diagnostics(hass, entry)
    assert "indoor_temperature" not in diagnostics["readings"]
    mock_api.async_get_live_data.return_value = {
        "wh25": [{"intemp": "22", "unit": "C"}]
    }
    await entry.runtime_data.coordinator.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get(temp_id).state == "22.0"
    assert hass.states.get(humidity_id).state == "unknown"


@pytest.mark.no_fail_on_log_exception
async def test_failed_poll_makes_entities_unavailable_until_recovery(
    hass, entry, mock_api, entity_registry, freezer
):
    """Mark failed polls unavailable and recover from current data."""
    await setup(hass, entry)
    temp_id = entity_id(entity_registry, "indoor_temperature")
    mock_api.async_get_live_data.side_effect = GatewayError("offline")
    await advance(hass, freezer, 61)
    assert not entry.runtime_data.coordinator.last_update_success
    entities = er.async_entries_for_config_entry(entity_registry, entry.entry_id)
    assert len(entities) == 4
    assert all(
        hass.states.get(entity.entity_id).state == "unavailable" for entity in entities
    )
    await advance(hass, freezer, 61)
    assert hass.states.get(temp_id).state == "unavailable"
    mock_api.async_get_live_data.side_effect = None
    mock_api.async_get_live_data.return_value = {
        "wh25": [{"intemp": "22", "unit": "C"}]
    }
    await entry.runtime_data.coordinator.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get(temp_id).state == "22.0"
    assert (
        hass.states.get(entity_id(entity_registry, "indoor_humidity")).state
        == "unknown"
    )


@pytest.mark.no_fail_on_log_exception
async def test_gateway_isolation_and_reload(hass, entry, entity_registry, freezer):
    """Keep gateway polling and reloads independent."""
    await setup(hass, entry)
    first = entry.runtime_data.coordinator
    second_entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=SECOND_MAC,
        title="Other gateway",
        data={CONF_BASE_URL: "http://other.example", CONF_MAC: SECOND_MAC},
        version=1,
    )
    second_api = AsyncMock(spec=EcowittApiClient)
    second_api.base_url = "http://other.example"
    second_api.async_get_info.return_value = GatewayInfo("GW2000A", "3.3.2", SECOND_MAC)
    second_api.async_get_live_data.return_value = {
        "wh25": [{"intemp": "19", "unit": "C"}]
    }
    second_api.async_get_registrations.return_value = []
    second_api.async_get_channel_metadata.return_value = []
    with patch(
        "custom_components.ecowitt_atomic.EcowittApiClient", return_value=second_api
    ):
        await setup(hass, second_entry)
    second = second_entry.runtime_data.coordinator
    assert first is not second
    first.client.async_get_live_data = AsyncMock(side_effect=GatewayError("offline"))
    await advance(hass, freezer, 61)
    assert (
        hass.states.get(entity_id(entity_registry, "indoor_temperature")).state
        == "unavailable"
    )
    other_id = entity_id(entity_registry, "indoor_temperature", SECOND_MAC)
    assert hass.states.get(other_id).state == "19.0"
    first.client.async_get_live_data.side_effect = None
    first.client.async_get_live_data.return_value = {
        "wh25": [{"intemp": "24", "unit": "C"}]
    }
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get(other_id).state == "19.0"
    assert await hass.config_entries.async_unload(entry.entry_id)
    await second.async_refresh()
    assert second.last_update_success


async def test_unverified_model_setup_rejected(hass, entry, mock_api):
    """Apply the gateway support policy when loading a stored entry."""
    entry.add_to_hass(hass)
    mock_api.async_get_info.return_value = GatewayInfo("GW3000", "1.0.0", MAC)
    assert not await hass.config_entries.async_setup(entry.entry_id)
    assert entry.state is ConfigEntryState.SETUP_ERROR
    mock_api.async_get_live_data.assert_not_awaited()


@pytest.mark.parametrize(
    ("failure", "expected"),
    [
        (GatewayError("offline"), ConfigEntryState.SETUP_RETRY),
        (UnsupportedGatewayError("unverified model"), ConfigEntryState.SETUP_ERROR),
    ],
)
async def test_setup_failure(hass, entry, mock_api, failure, expected):
    """Map connection and model failures to setup states."""
    entry.add_to_hass(hass)
    mock_api.async_get_info.side_effect = failure
    assert not await hass.config_entries.async_setup(entry.entry_id)
    assert entry.state is expected


@pytest.mark.parametrize("address", [None, 123, "gateway.example/path"])
async def test_invalid_stored_address(hass, entry, mock_api, address):
    """Reject malformed stored connection data before requests."""
    entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(entry, data={CONF_BASE_URL: address})
    assert not await hass.config_entries.async_setup(entry.entry_id)
    assert entry.state is ConfigEntryState.SETUP_ERROR
    mock_api.async_get_info.assert_not_awaited()


async def test_initial_empty_readings_are_unknown(
    hass, entry, mock_api, entity_registry
):
    """Load existing entries even when readings are missing."""
    mock_api.async_get_live_data.return_value = {}
    await setup(hass, entry)
    assert entry.state is ConfigEntryState.LOADED
    entities = er.async_entries_for_config_entry(entity_registry, entry.entry_id)
    assert len(entities) == 4
    assert all(
        hass.states.get(entity.entity_id).state == "unknown" for entity in entities
    )


async def test_diagnostics_allowlist(hass, entry):
    """Exclude connection details from diagnostics."""
    await setup(hass, entry)
    diagnostics = await async_get_config_entry_diagnostics(hass, entry)
    assert diagnostics["model"] == "GW2000A"
    assert diagnostics["readings"]["indoor_temperature"]["value"] == 21.5
    assert BASE_URL not in str(diagnostics)
    assert "base_url" not in diagnostics
    assert MAC not in str(diagnostics)


async def test_same_mac_new_address_preserves_registry(
    hass, entry, entity_registry, device_registry
):
    """Retain registry entries when the connection address changes."""
    await setup(hass, entry)
    old_device = dr.async_entries_for_config_entry(device_registry, entry.entry_id)[0]
    old_entity_ids = {
        e.entity_id
        for e in er.async_entries_for_config_entry(entity_registry, entry.entry_id)
    }
    hass.config_entries.async_update_entry(
        entry, data={**entry.data, CONF_BASE_URL: "http://new.example"}
    )
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert (
        dr.async_entries_for_config_entry(device_registry, entry.entry_id)[0].id
        == old_device.id
    )
    assert {
        e.entity_id
        for e in er.async_entries_for_config_entry(entity_registry, entry.entry_id)
    } == old_entity_ids
    assert entry.unique_id == MAC
    assert entry.runtime_data.coordinator.client.base_url == "http://new.example"
    assert (
        device_registry.async_get(old_device.id).configuration_url
        == "http://new.example"
    )


async def test_address_reuse_by_different_hardware_rejected(
    hass, entry, mock_api, device_registry
):
    """Reject hardware identity changes at a stored address."""
    entry.add_to_hass(hass)
    mock_api.async_get_info.return_value = GatewayInfo("GW2000A", "3.3.2", SECOND_MAC)
    assert not await hass.config_entries.async_setup(entry.entry_id)
    assert entry.state is ConfigEntryState.SETUP_ERROR
    assert entry.unique_id == MAC
    assert not dr.async_entries_for_config_entry(device_registry, entry.entry_id)


async def test_manual_device_removal_and_rediscovery(
    hass, entry, device_registry, entity_registry
):
    """Allow removal and rediscovery on reload."""
    await setup(hass, entry)
    device = dr.async_entries_for_config_entry(device_registry, entry.entry_id)[0]
    assert entry.supports_remove_device
    assert await async_remove_config_entry_device(hass, entry, device)
    device_registry.async_remove_device(device.id)
    await hass.async_block_till_done()
    assert not er.async_entries_for_config_entry(entity_registry, entry.entry_id)
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert len(dr.async_entries_for_config_entry(device_registry, entry.entry_id)) == 1
    assert len(er.async_entries_for_config_entry(entity_registry, entry.entry_id)) == 4
