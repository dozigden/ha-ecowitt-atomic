"""Ecowitt Atomic: device oriented Ecowitt integration."""

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryError, ConfigEntryNotReady
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.device_registry import DeviceEntry

from .api import EcowittApiClient, GatewayError, UnsupportedGateway
from .const import CONF_BASE_URL, DOMAIN
from .coordinator import GatewayCoordinator
from .data import AtomicConfigEntry, GatewayData

PLATFORMS = [Platform.SENSOR]
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup_entry(hass: HomeAssistant, entry: AtomicConfigEntry) -> bool:
    """Set up one gateway and perform its first refresh before creating entities."""
    client = EcowittApiClient(entry.data[CONF_BASE_URL], async_get_clientsession(hass))
    try:
        info = await client.async_get_info()
    except UnsupportedGateway as err:
        raise ConfigEntryError(str(err)) from err
    except GatewayError as err:
        raise ConfigEntryNotReady(str(err)) from err
    if info.mac != entry.unique_id:
        raise ConfigEntryError("The address belongs to a different gateway MAC")
    coordinator = GatewayCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = GatewayData(info, coordinator)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: AtomicConfigEntry) -> bool:
    """Unload only the platforms belonging to this gateway."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_config_entry_device(
    hass: HomeAssistant, entry: AtomicConfigEntry, device: DeviceEntry
) -> bool:
    """Allow manual removal; setup may discover the gateway device again."""
    return True
