"""HA devices, entities, coordinator availability, and gateway lifecycles."""

from datetime import timedelta
from unittest.mock import AsyncMock, patch

import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.ecowitt_atomic.api import (
    EcowittApiClient,
    GatewayError,
    UnsupportedGateway,
)
from custom_components.ecowitt_atomic.const import CONF_BASE_URL, CONF_MAC, DOMAIN
from custom_components.ecowitt_atomic.diagnostics import (
    async_get_config_entry_diagnostics,
)
from custom_components.ecowitt_atomic.models import GatewayInfo, Reading
from homeassistant.config_entries import ConfigEntryState
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util

from .conftest import BASE_URL, MAC, SECOND_MAC

pytestmark = pytest.mark.usefixtures("mock_api")


async def setup(hass, entry):
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


def entity_id(entity_registry, key, mac=MAC):
    return entity_registry.async_get_entity_id("sensor", DOMAIN, f"{mac}::{key}")


async def advance(hass, freezer, seconds):
    freezer.tick(timedelta(seconds=seconds))
    async_fire_time_changed(hass, dt_util.utcnow())
    await hass.async_block_till_done()


async def test_setup_and_unload(
    hass, entry, mock_api, device_registry, entity_registry, freezer
):
    await setup(hass, entry)
    assert entry.state is ConfigEntryState.LOADED
    devices = dr.async_entries_for_config_entry(device_registry, entry.entry_id)
    assert len(devices) == 1
    assert devices[0].identifiers == {(DOMAIN, MAC)}
    assert devices[0].connections == {(dr.CONNECTION_NETWORK_MAC, MAC)}
    assert devices[0].model == "GW2000A"
    assert devices[0].name == "GW2000A (020000000001)"
    assert devices[0].sw_version == "3.3.2"
    entities = er.async_entries_for_config_entry(entity_registry, entry.entry_id)
    assert len(entities) == 4
    assert {item.device_id for item in entities} == {devices[0].id}
    temperature_id = entity_id(entity_registry, "indoor_temperature")
    state = hass.states.get(temperature_id)
    assert state.state == "21.5"
    assert state.attributes["unit_of_measurement"] == "°C"
    assert state.attributes["device_class"] == "temperature"
    assert state.attributes["state_class"] == "measurement"
    await advance(hass, freezer, 31)
    assert mock_api.async_get_readings.await_count == 2
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    count = mock_api.async_get_readings.await_count
    await advance(hass, freezer, 100)
    assert mock_api.async_get_readings.await_count == count
    assert len(er.async_entries_for_config_entry(entity_registry, entry.entry_id)) == 4


@pytest.mark.parametrize(
    "remaining_readings", [{"indoor_humidity": Reading(60, "%")}, {}]
)
async def test_missing_readings_become_unknown(
    hass, entry, mock_api, entity_registry, freezer, remaining_readings
):
    await setup(hass, entry)
    temp_id = entity_id(entity_registry, "indoor_temperature")
    humidity_id = entity_id(entity_registry, "indoor_humidity")
    mock_api.async_get_readings.return_value = remaining_readings
    await advance(hass, freezer, 31)
    assert entry.runtime_data.coordinator.last_update_success
    assert hass.states.get(temp_id).state == "unknown"
    assert hass.states.get(humidity_id).state == (
        "60" if "indoor_humidity" in remaining_readings else "unknown"
    )
    assert len(er.async_entries_for_config_entry(entity_registry, entry.entry_id)) == 4
    diagnostics = await async_get_config_entry_diagnostics(hass, entry)
    assert "indoor_temperature" not in diagnostics["readings"]
    mock_api.async_get_readings.return_value = {"indoor_temperature": Reading(22, "°C")}
    await entry.runtime_data.coordinator.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get(temp_id).state == "22"
    assert hass.states.get(humidity_id).state == "unknown"


@pytest.mark.no_fail_on_log_exception
async def test_failed_poll_makes_entities_unavailable_until_recovery(
    hass, entry, mock_api, entity_registry, freezer
):
    await setup(hass, entry)
    temp_id = entity_id(entity_registry, "indoor_temperature")
    mock_api.async_get_readings.side_effect = GatewayError("offline")
    await advance(hass, freezer, 31)
    assert not entry.runtime_data.coordinator.last_update_success
    entities = er.async_entries_for_config_entry(entity_registry, entry.entry_id)
    assert len(entities) == 4
    assert all(
        hass.states.get(entity.entity_id).state == "unavailable" for entity in entities
    )
    await advance(hass, freezer, 31)
    assert hass.states.get(temp_id).state == "unavailable"
    mock_api.async_get_readings.side_effect = None
    mock_api.async_get_readings.return_value = {"indoor_temperature": Reading(22, "°C")}
    await entry.runtime_data.coordinator.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get(temp_id).state == "22"
    assert (
        hass.states.get(entity_id(entity_registry, "indoor_humidity")).state
        == "unknown"
    )


@pytest.mark.no_fail_on_log_exception
async def test_gateway_isolation_and_reload(
    hass, entry, mock_api, entity_registry, freezer
):
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
    second_api.async_get_info.return_value = GatewayInfo("GW2000A", "3.3.2", SECOND_MAC)
    second_api.async_get_readings.return_value = {
        "indoor_temperature": Reading(19, "°C")
    }
    with patch(
        "custom_components.ecowitt_atomic.EcowittApiClient", return_value=second_api
    ):
        await setup(hass, second_entry)
    second = second_entry.runtime_data.coordinator
    assert first is not second
    first.client.async_get_readings = AsyncMock(side_effect=GatewayError("offline"))
    await advance(hass, freezer, 31)
    assert (
        hass.states.get(entity_id(entity_registry, "indoor_temperature")).state
        == "unavailable"
    )
    other_id = entity_id(entity_registry, "indoor_temperature", SECOND_MAC)
    assert hass.states.get(other_id).state == "19"
    first.client.async_get_readings.side_effect = None
    first.client.async_get_readings.return_value = {
        "indoor_temperature": Reading(24, "°C")
    }
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get(other_id).state == "19"
    assert await hass.config_entries.async_unload(entry.entry_id)
    await second.async_refresh()
    assert second.last_update_success


@pytest.mark.parametrize(
    ("failure", "expected"),
    [
        (GatewayError("offline"), ConfigEntryState.SETUP_RETRY),
        (UnsupportedGateway("unverified model"), ConfigEntryState.SETUP_ERROR),
    ],
)
async def test_setup_failure(hass, entry, mock_api, failure, expected):
    entry.add_to_hass(hass)
    mock_api.async_get_info.side_effect = failure
    assert not await hass.config_entries.async_setup(entry.entry_id)
    assert entry.state is expected


async def test_initial_empty_readings_are_unknown(
    hass, entry, mock_api, entity_registry
):
    mock_api.async_get_readings.return_value = {}
    await setup(hass, entry)
    assert entry.state is ConfigEntryState.LOADED
    entities = er.async_entries_for_config_entry(entity_registry, entry.entry_id)
    assert len(entities) == 4
    assert all(
        hass.states.get(entity.entity_id).state == "unknown" for entity in entities
    )


async def test_diagnostics_allowlist(hass, entry):
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


async def test_address_reuse_by_different_hardware_rejected(
    hass, entry, mock_api, device_registry
):
    entry.add_to_hass(hass)
    mock_api.async_get_info.return_value = GatewayInfo("GW2000A", "3.3.2", SECOND_MAC)
    assert not await hass.config_entries.async_setup(entry.entry_id)
    assert entry.state is ConfigEntryState.SETUP_ERROR
    assert entry.unique_id == MAC
    assert not dr.async_entries_for_config_entry(device_registry, entry.entry_id)


async def test_manual_device_removal_and_rediscovery(
    hass, entry, device_registry, entity_registry
):
    from custom_components.ecowitt_atomic import async_remove_config_entry_device

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
