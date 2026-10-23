"""Ecowitt Atomic."""

from awesomeversion.awesomeversion import AwesomeVersion

from homeassistant.const import (
    Platform,
    __version__ as HA_VERSION,  # noqa: N812
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryError, ConfigEntryNotReady
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.device_registry import DeviceEntry
from homeassistant.helpers.typing import ConfigType

from .api import (
    EcowittApiClient,
    GatewayError,
    UnsupportedGatewayError,
    normalize_base_url,
)
from .const import CONF_BASE_URL, DOMAIN, LOGGER, MIN_HA_VERSION
from .coordinator import GatewayCoordinator
from .data import AtomicConfigEntry, GatewayData
from .devices import async_setup_devices
from .gateway import async_get_gateway_info

PLATFORMS = [Platform.SENSOR]
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(
    hass: HomeAssistant,  # noqa: ARG001
    config: ConfigType,  # noqa: ARG001
) -> bool:
    """Integration setup."""
    if AwesomeVersion(HA_VERSION) < AwesomeVersion(MIN_HA_VERSION):  # pragma: no cover
        msg = (
            "This integration requires at least Home Assistant version "
            f"{MIN_HA_VERSION}, you are running version {HA_VERSION}. "
            "Please upgrade Home Assistant to continue using this integration."
        )
        LOGGER.critical(msg)
        return False

    return True


async def async_setup_entry(hass: HomeAssistant, entry: AtomicConfigEntry) -> bool:
    """Set up a gateway."""
    try:
        base_url = normalize_base_url(entry.data.get(CONF_BASE_URL))
    except (ValueError, UnicodeError) as err:
        raise ConfigEntryError("Invalid gateway address") from err
    client = EcowittApiClient(base_url, async_get_clientsession(hass))
    try:
        info = await async_get_gateway_info(client)
    except UnsupportedGatewayError as err:
        raise ConfigEntryError(str(err)) from err
    except GatewayError as err:
        raise ConfigEntryNotReady(str(err)) from err
    if info.mac != entry.unique_id:
        raise ConfigEntryError("The address belongs to a different gateway MAC")
    coordinator = GatewayCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = GatewayData(info, coordinator)
    async_setup_devices(hass, entry)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: AtomicConfigEntry) -> bool:
    """Unload a gateway."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_config_entry_device(
    hass: HomeAssistant,  # noqa: ARG001
    entry: AtomicConfigEntry,  # noqa: ARG001
    device: DeviceEntry,  # noqa: ARG001
) -> bool:
    """Allow removal; reload may rediscover the gateway."""
    return True
