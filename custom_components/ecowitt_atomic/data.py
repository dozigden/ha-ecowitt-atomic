"""Typed runtime data scoped to a gateway's config entry."""

from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry

from .coordinator import GatewayCoordinator
from .models import GatewayInfo


@dataclass
class GatewayData:
    """Runtime state of one configured gateway."""

    info: GatewayInfo
    coordinator: GatewayCoordinator


type AtomicConfigEntry = ConfigEntry[GatewayData]
