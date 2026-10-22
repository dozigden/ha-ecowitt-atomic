"""Standalone temperature discovery through channel metadata."""

from custom_components.ecowitt_atomic.const import DOMAIN

from homeassistant.helpers import entity_registry as er

from .conftest import MAC
from .test_soil_integration import load, refresh, responses


async def test_temperature_discovery_and_retention(
    hass, entry, aioclient_mock, live_payload, entity_registry, device_registry
):
    """Use the radio link and live reading, retaining identity across absence."""
    registrations = [
        {"type": "847", "id": "ABC", "name": "Temp CH3", "img": "future"},
        {"type": "31", "id": "DEF", "name": "Temp CH1", "img": "wh34"},
    ]
    metadata = [{"channel": "3", "id": "0x00abc", "temp": "5.0"}]
    live_payload["ch_temp"] = [
        {
            "channel": "3",
            "name": "Compost",
            "temp": "--",
            "unit": "C",
            "battery": "3",
            "voltage": "1.34",
            "humidity": "50%",
        }
    ]
    responses(
        aioclient_mock,
        live_payload,
        [],
        registrations=registrations,
        temperature_channels=metadata,
    )
    await load(hass, entry)
    device = device_registry.async_get_device_by_identifier(
        (DOMAIN, f"{MAC}::847"), entry.entry_id
    )
    unique_id = f"{MAC}::847::temperature"
    assert device is not None
    assert entity_registry.async_get_entity_id("sensor", DOMAIN, unique_id) is None
    assert len(er.async_entries_for_device(entity_registry, device.id)) == 2

    for value, unit, expected in [("32", "F", "0.0"), ("-2.5", "C", "-2.5")]:
        live_payload["ch_temp"][0].update(temp=value, unit=unit)
        aioclient_mock.clear_requests()
        responses(
            aioclient_mock,
            live_payload,
            [],
            registrations=registrations,
            temperature_channels=metadata,
        )
        await refresh(hass, entry)
        entity_id = entity_registry.async_get_entity_id("sensor", DOMAIN, unique_id)
        registered = entity_registry.async_get(entity_id)
        assert registered.device_id == device.id
        state = hass.states.get(entity_id)
        assert state.state == expected
        assert state.attributes["device_class"] == "temperature"
        assert state.attributes["state_class"] == "measurement"
        assert state.attributes["unit_of_measurement"] == "°C"
    assert {
        e.unique_id for e in er.async_entries_for_device(entity_registry, device.id)
    } == {unique_id, f"{MAC}::847::gateway_name", f"{MAC}::847::radio_id"}
    assert (
        entity_registry.async_get_entity_id("sensor", DOMAIN, f"{MAC}::31::temperature")
        is None
    )

    aioclient_mock.clear_requests()
    live_payload["ch_temp"] = []
    responses(aioclient_mock, live_payload, [], registrations=[])
    await refresh(hass, entry)
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert entity_registry.async_get_entity_id("sensor", DOMAIN, unique_id) == entity_id
    assert entity_registry.async_get(entity_id).device_id == device.id
    assert hass.states.get(entity_id).state == "unknown"
