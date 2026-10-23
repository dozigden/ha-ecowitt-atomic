"""Soil discovery through the HTTP client and HA's registries."""

from datetime import timedelta

from custom_components.ecowitt_atomic.const import CONF_BASE_URL, CONF_MAC, DOMAIN
from custom_components.ecowitt_atomic.diagnostics import (
    async_get_config_entry_diagnostics,
)
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.util import dt as dt_util

from .conftest import BASE_URL, MAC, SECOND_MAC


def responses(
    aioclient_mock,
    live_payload,
    channels,
    *,
    registrations=None,
    soil_channels=None,
    multi_channels=None,
    temperature_channels=None,
    base_url=BASE_URL,
    mac=MAC,
):
    """Provide synthetic HTTP payloads without mocking the integration client."""
    aioclient_mock.get(
        f"{base_url}/get_version",
        json={"version": "Version: GW2000A_V3.3.2", "sensorid_page": "2"},
    )
    aioclient_mock.get(f"{base_url}/get_network_info", json={"mac": mac})
    aioclient_mock.get(
        f"{base_url}/get_livedata_info", json={**live_payload, "ch_soil": channels}
    )
    aioclient_mock.get(f"{base_url}/get_sensors_info?page=1", json=[])
    aioclient_mock.get(
        f"{base_url}/get_sensors_info?page=2",
        json=registrations
        if registrations is not None
        else [
            {"type": "847", "id": "ABC", "name": "Soil moisture CH1", "img": "wh51"},
            {"type": "985", "id": "DEF", "name": "Soil moisture CH5", "img": "wh51"},
        ],
    )

    aioclient_mock.get(
        f"{base_url}/get_cli_soilad",
        json=soil_channels
        if soil_channels is not None
        else [
            {"ch": "1", "id": "0xABC", "soilVal": "0"},
            {"ch": "5", "id": "0xDEF", "soilVal": "0"},
        ],
    )

    aioclient_mock.get(
        f"{base_url}/get_cli_multiCh",
        json=multi_channels if multi_channels is not None else [],
    )
    aioclient_mock.get(
        f"{base_url}/get_cli_wh34",
        json=temperature_channels if temperature_channels is not None else [],
    )


def soil_entity(entity_registry, slot=847, mac=MAC):
    """Look up an entity using integration identity, independent of its name."""
    return entity_registry.async_get_entity_id(
        "sensor", DOMAIN, f"{mac}::{slot}::soil_moisture"
    )


async def load(hass, entry):
    """Load an entry through HA."""
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def refresh(hass, entry):
    """Poll and finish entity discovery tasks."""
    await entry.runtime_data.coordinator.async_refresh()
    await hass.async_block_till_done()


async def test_soil_discovery_and_later_poll(
    hass, entry, aioclient_mock, live_payload, entity_registry, device_registry, freezer
):
    """Create distinct devices and discover a previously offline Ecowitt sensor."""
    responses(
        aioclient_mock,
        live_payload,
        [{"channel": "1", "humidity": "35%", "name": "Bed"}],
    )
    await load(hass, entry)
    entity_id = soil_entity(entity_registry)
    state = hass.states.get(entity_id)
    assert state.state == "35.0"
    assert state.attributes["device_class"] == "moisture"
    assert state.attributes["unit_of_measurement"] == "%"
    assert state.attributes["state_class"] == "measurement"
    assert soil_entity(entity_registry, 985) is None
    devices = dr.async_entries_for_config_entry(device_registry, entry.entry_id)
    assert len(devices) == 3
    offline_device = device_registry.async_get_device_by_identifier(
        (DOMAIN, f"{MAC}::985"), entry.entry_id
    )
    assert offline_device is not None
    offline_entities = er.async_entries_for_device(entity_registry, offline_device.id)
    assert {
        e.unique_id: hass.states.get(e.entity_id).state for e in offline_entities
    } == {
        f"{MAC}::985::gateway_name": "Soil moisture CH5",
        f"{MAC}::985::radio_id": "DEF",
    }
    soil_device = device_registry.async_get(
        entity_registry.async_get(entity_id).device_id
    )
    assert soil_device.identifiers == {(DOMAIN, f"{MAC}::847")}
    assert soil_device.name == "Bed"
    assert soil_device.via_device_id != soil_device.id
    assert device_registry.async_get(soil_device.via_device_id).identifiers == {
        (DOMAIN, MAC)
    }

    aioclient_mock.clear_requests()
    responses(
        aioclient_mock,
        live_payload,
        [{"channel": "1", "humidity": "36%"}, {"channel": "5", "humidity": "0%"}],
    )
    freezer.tick(timedelta(seconds=61))
    async_fire_time_changed(hass, dt_util.utcnow())
    await hass.async_block_till_done()
    assert hass.states.get(entity_id).state == "36.0"
    assert hass.states.get(soil_entity(entity_registry, 985)).state == "0.0"
    assert (
        entity_registry.async_get(soil_entity(entity_registry, 985)).device_id
        == offline_device.id
    )
    await refresh(hass, entry)
    assert len(er.async_entries_for_config_entry(entity_registry, entry.entry_id)) == 10
    assert len(dr.async_entries_for_config_entry(device_registry, entry.entry_id)) == 3
    diagnostics = await async_get_config_entry_diagnostics(hass, entry)
    assert diagnostics["ecowitt_sensors"]["847"]["soil_moisture"]["value"] == 36
    assert all(
        private not in str(diagnostics) for private in (MAC, BASE_URL, "ABC", "Bed")
    )


@pytest.mark.parametrize(
    "missing", ["channel", "reading", "invalid", "registration", "metadata"]
)
async def test_missing_soil_data_and_reload(
    hass, entry, aioclient_mock, live_payload, entity_registry, device_registry, missing
):
    """Keep identity and user settings through absence and a fresh coordinator."""
    responses(
        aioclient_mock,
        live_payload,
        [{"channel": "1", "humidity": "35%", "name": "Bed"}],
    )
    await load(hass, entry)
    original_id = soil_entity(entity_registry)
    entity_registry.async_update_entity(
        original_id, new_entity_id="sensor.my_moisture", name="My moisture"
    )
    await hass.async_block_till_done()
    device_id = entity_registry.async_get("sensor.my_moisture").device_id
    device_registry.async_update_device(device_id, name_by_user="My bed")
    aioclient_mock.clear_requests()
    channels = [] if missing == "channel" else [{"channel": "1"}]
    if missing == "invalid":
        channels[0]["humidity"] = "--"
    if missing in {"registration", "metadata"}:
        channels[0]["humidity"] = "44%"
    responses(
        aioclient_mock,
        live_payload,
        channels,
        registrations=[] if missing == "registration" else None,
        soil_channels=[] if missing == "metadata" else None,
    )
    await refresh(hass, entry)
    assert hass.states.get("sensor.my_moisture").state == "unknown"
    old_coordinator = entry.runtime_data.coordinator
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.runtime_data.coordinator is not old_coordinator
    assert soil_entity(entity_registry) == "sensor.my_moisture"
    assert hass.states.get("sensor.my_moisture").state == "unknown"
    assert entity_registry.async_get("sensor.my_moisture").name == "My moisture"
    device = device_registry.async_get(device_id)
    assert device.name == "Bed"
    assert device.name_by_user == "My bed"
    assert len(er.async_entries_for_config_entry(entity_registry, entry.entry_id)) == 9


@pytest.mark.parametrize("disabled", [False, True])
@pytest.mark.parametrize(
    "capability",
    ["soil_moisture", "temperature", "humidity", "gateway_name", "radio_id"],
)
async def test_restore_capability_without_previous_runtime(
    hass,
    entry,
    aioclient_mock,
    live_payload,
    entity_registry,
    device_registry,
    disabled,
    capability,
):
    """Existing HA registrations suffice on startup with no live soil data."""
    entry.add_to_hass(hass)
    device = device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, f"{MAC}::847")},
        name="Remembered bed",
    )
    registered = entity_registry.async_get_or_create(
        "sensor",
        DOMAIN,
        f"{MAC}::847::{capability}",
        config_entry=entry,
        device_id=device.id,
        disabled_by=er.RegistryEntryDisabler.USER if disabled else None,
    )
    responses(aioclient_mock, live_payload, [], registrations=[], soil_channels=[])
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert (
        entity_registry.async_get_entity_id(
            "sensor", DOMAIN, f"{MAC}::847::{capability}"
        )
        == registered.entity_id
    )
    assert entity_registry.async_get(registered.entity_id).device_id == device.id
    assert device_registry.async_get(device.id).name == "Remembered bed"
    state = hass.states.get(registered.entity_id)
    if disabled:
        assert state is None
        assert (
            entity_registry.async_get(registered.entity_id).disabled_by
            is er.RegistryEntryDisabler.USER
        )
    else:
        assert state.state == "unknown"


async def test_channel_mapping_changes_and_ambiguity(
    hass, entry, aioclient_mock, live_payload, entity_registry
):
    """Follow current API ownership without changing the registered identity."""
    responses(aioclient_mock, live_payload, [{"channel": "1", "humidity": "35%"}])
    await load(hass, entry)
    entity_id = soil_entity(entity_registry)
    device_id = entity_registry.async_get(entity_id).device_id
    for ambiguous, expected, entity_count in (
        (False, "42.0", 9),
        (True, "unknown", 10),
        (False, "42.0", 10),
    ):
        aioclient_mock.clear_requests()
        registrations = [{"type": "847", "id": "ABC", "img": "wh51"}]
        if ambiguous:
            registrations.append({"type": "912", "id": "ABC"})
        responses(
            aioclient_mock,
            live_payload,
            [
                {"channel": "1", "humidity": "99%"},
                {"channel": "12", "humidity": "42%"},
            ],
            registrations=registrations,
            soil_channels=[{"ch": "12", "id": "0xABC"}],
        )
        await refresh(hass, entry)
        assert soil_entity(entity_registry) == entity_id
        assert entity_registry.async_get(entity_id).device_id == device_id
        assert hass.states.get(entity_id).state == expected
        assert soil_entity(entity_registry, 912) is None
        assert (
            len(er.async_entries_for_config_entry(entity_registry, entry.entry_id))
            == entity_count
        )


@pytest.mark.parametrize(
    "failed_endpoint",
    ["get_sensors_info?page=1", "get_cli_soilad", "get_cli_multiCh", "get_cli_wh34"],
)
@pytest.mark.no_fail_on_log_exception
async def test_soil_gateway_isolation_and_recovery(
    hass, entry, aioclient_mock, live_payload, entity_registry, failed_endpoint
):
    """A failed metadata request affects only its owning gateway."""
    other_url = "http://other.example"
    other_entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=SECOND_MAC,
        data={CONF_BASE_URL: other_url, CONF_MAC: SECOND_MAC},
        version=1,
    )
    responses(aioclient_mock, live_payload, [{"channel": "1", "humidity": "35%"}])
    responses(
        aioclient_mock,
        live_payload,
        [{"channel": "1", "humidity": "60%"}],
        base_url=other_url,
        mac=SECOND_MAC,
    )
    await load(hass, entry)
    await load(hass, other_entry)
    first_id = soil_entity(entity_registry)
    second_id = soil_entity(entity_registry, mac=SECOND_MAC)
    assert first_id != second_id
    assert (
        entity_registry.async_get(first_id).device_id
        != entity_registry.async_get(second_id).device_id
    )
    aioclient_mock.clear_requests()
    aioclient_mock.get(f"{BASE_URL}/get_livedata_info", json=live_payload)
    aioclient_mock.get(f"{BASE_URL}/get_version", json={"sensorid_page": "1"})
    if failed_endpoint != "get_sensors_info?page=1":
        aioclient_mock.get(f"{BASE_URL}/get_sensors_info?page=1", json=[])
    if failed_endpoint in {"get_cli_multiCh", "get_cli_wh34"}:
        aioclient_mock.get(f"{BASE_URL}/get_cli_soilad", json=[])
    if failed_endpoint == "get_cli_wh34":
        aioclient_mock.get(f"{BASE_URL}/get_cli_multiCh", json=[])
    aioclient_mock.get(f"{BASE_URL}/{failed_endpoint}", status=503)
    responses(
        aioclient_mock,
        live_payload,
        [{"channel": "1", "humidity": "61%"}],
        base_url=other_url,
        mac=SECOND_MAC,
    )
    await refresh(hass, entry)
    await refresh(hass, other_entry)
    assert hass.states.get(first_id).state == "unavailable"
    assert hass.states.get(second_id).state == "61.0"
    aioclient_mock.clear_requests()
    responses(aioclient_mock, live_payload, [{"channel": "1", "humidity": "40%"}])
    await refresh(hass, entry)
    assert hass.states.get(first_id).state == "40.0"
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get(second_id).state == "61.0"


@pytest.mark.parametrize("img", ["wh34", "unfamiliar", None])
async def test_registration_devices_without_readings(
    hass, entry, aioclient_mock, live_payload, entity_registry, device_registry, img
):
    """Discover valid registrations regardless of image and retain offline devices."""
    registrations = [
        {"type": "847", "id": "ABC", "img": "wh51", "signal": "--"},
        {"type": "6", "id": "DEF", "name": "SoilTemp CH1", "img": img},
        {"type": "99", "id": "FFFFFFFF", "img": "wh51"},
        {"type": "100", "id": "FFFFFFFE", "img": "wh51"},
    ]
    responses(
        aioclient_mock, live_payload, [], registrations=registrations, soil_channels=[]
    )
    await load(hass, entry)
    device = device_registry.async_get_device_by_identifier(
        (DOMAIN, f"{MAC}::847"), entry.entry_id
    )
    assert device is not None
    assert device.name == "Ecowitt sensor 847"
    assert len(dr.async_entries_for_config_entry(device_registry, entry.entry_id)) == 3
    assert len(er.async_entries_for_config_entry(entity_registry, entry.entry_id)) == 7
    other_device = device_registry.async_get_device_by_identifier(
        (DOMAIN, f"{MAC}::6"), entry.entry_id
    )
    assert other_device is not None
    assert other_device.via_device_id == device.via_device_id
    assert {
        e.unique_id: hass.states.get(e.entity_id).state
        for e in er.async_entries_for_device(entity_registry, other_device.id)
    } == {
        f"{MAC}::6::gateway_name": "SoilTemp CH1",
        f"{MAC}::6::radio_id": "DEF",
    }
    assert [
        e.unique_id for e in er.async_entries_for_device(entity_registry, device.id)
    ] == [f"{MAC}::847::radio_id"]
    aioclient_mock.clear_requests()
    responses(aioclient_mock, live_payload, [], registrations=[], soil_channels=[])
    await refresh(hass, entry)
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    dr.async_cleanup(hass, device_registry, entity_registry)
    assert device_registry.async_get(device.id) is not None
    assert device_registry.async_get(other_device.id) is not None
    assert [
        e.unique_id for e in er.async_entries_for_device(entity_registry, device.id)
    ] == [f"{MAC}::847::radio_id"]
    aioclient_mock.clear_requests()
    responses(
        aioclient_mock,
        live_payload,
        [],
        registrations=[{"type": "985", "id": "123"}],
        soil_channels=[],
    )
    await refresh(hass, entry)
    later_device = device_registry.async_get_device_by_identifier(
        (DOMAIN, f"{MAC}::985"), entry.entry_id
    )
    assert later_device is not None
    assert [
        e.unique_id
        for e in er.async_entries_for_device(entity_registry, later_device.id)
    ] == [f"{MAC}::985::radio_id"]


@pytest.mark.parametrize("missing", ["registration", "name"])
async def test_gateway_name_metadata_and_restoration(
    hass, entry, aioclient_mock, live_payload, entity_registry, device_registry, missing
):
    """Keep the registration name distinct from live and user names across reload."""
    responses(
        aioclient_mock,
        live_payload,
        [{"channel": "1", "humidity": "35%", "name": "Tomato bed"}],
    )
    await load(hass, entry)
    entity_id = entity_registry.async_get_entity_id(
        "sensor", DOMAIN, f"{MAC}::847::gateway_name"
    )
    registered = entity_registry.async_get(entity_id)
    assert registered.entity_category.value == "diagnostic"
    assert registered.disabled_by is None
    state = hass.states.get(entity_id)
    assert state.state == "Soil moisture CH1"
    assert "unit_of_measurement" not in state.attributes
    assert "state_class" not in state.attributes
    assert device_registry.async_get(registered.device_id).name == "Tomato bed"
    assert device_registry.async_get(registered.device_id).model == "Soil moisture"
    device_registry.async_update_device(
        registered.device_id, name_by_user="My tomatoes"
    )
    aioclient_mock.clear_requests()
    responses(
        aioclient_mock,
        live_payload,
        [],
        registrations=[
            {"type": "847", "id": "ABC", "img": "wh51", "name": "New gateway label"}
        ],
        soil_channels=[],
    )
    await refresh(hass, entry)
    assert hass.states.get(entity_id).state == "New gateway label"
    assert device_registry.async_get(registered.device_id).model == "New gateway label"
    assert device_registry.async_get(registered.device_id).name_by_user == "My tomatoes"
    aioclient_mock.clear_requests()
    responses(
        aioclient_mock,
        live_payload,
        [],
        registrations=[]
        if missing == "registration"
        else [{"type": "847", "id": "ABC", "img": "wh51"}],
        soil_channels=[],
    )
    await refresh(hass, entry)
    assert hass.states.get(entity_id).state == "unknown"
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get(entity_id).state == "unknown"
    assert entity_registry.async_get(entity_id).device_id == registered.device_id
    assert device_registry.async_get(registered.device_id).model == "New gateway label"
    aioclient_mock.clear_requests()
    responses(aioclient_mock, live_payload, [], soil_channels=[])
    await refresh(hass, entry)
    assert hass.states.get(entity_id).state == "Soil moisture CH1"
    assert device_registry.async_get(registered.device_id).model == "Soil moisture"


@pytest.mark.parametrize("absent_id", [None, "FFFFFFFF", "FFFFFFFE", "invalid"])
async def test_radio_id_diagnostic(
    hass, entry, aioclient_mock, live_payload, entity_registry, absent_id
):
    """Expose offline radio IDs without changing device identity when the ID changes."""
    responses(
        aioclient_mock,
        live_payload,
        [],
        registrations=[{"type": "847", "id": "0x00abc", "img": "wh51"}],
        soil_channels=[],
    )
    await load(hass, entry)
    entity_id = entity_registry.async_get_entity_id(
        "sensor", DOMAIN, f"{MAC}::847::radio_id"
    )
    registered = entity_registry.async_get(entity_id)
    assert registered.entity_category.value == "diagnostic"
    assert registered.disabled_by is None
    assert hass.states.get(entity_id).state == "ABC"
    assert "unit_of_measurement" not in hass.states.get(entity_id).attributes
    assert "state_class" not in hass.states.get(entity_id).attributes
    assert soil_entity(entity_registry) is None
    aioclient_mock.clear_requests()
    responses(
        aioclient_mock,
        live_payload,
        [],
        registrations=[{"type": "847", "id": absent_id, "img": "wh51"}],
        soil_channels=[],
    )
    await refresh(hass, entry)
    assert hass.states.get(entity_id).state == "unknown"
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get(entity_id).state == "unknown"
    aioclient_mock.clear_requests()
    responses(
        aioclient_mock,
        live_payload,
        [],
        registrations=[{"type": "847", "id": "0x00def", "img": "wh51"}],
        soil_channels=[],
    )
    await refresh(hass, entry)
    assert hass.states.get(entity_id).state == "DEF"
    assert entity_registry.async_get(entity_id).device_id == registered.device_id
    assert len(er.async_entries_for_config_entry(entity_registry, entry.entry_id)) == 5
