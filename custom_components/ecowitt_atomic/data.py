"""Config-entry runtime data."""

from dataclasses import dataclass
from typing import TypedDict

from homeassistant.config_entries import ConfigEntry

from .coordinator import GatewayCoordinator
from .models import GatewayInfo


class GatewayConfigData(TypedDict):
    """Stored gateway connection and identity."""

    base_url: str
    mac: str


@dataclass
class GatewayData:
    """Gateway information and polling coordinator."""

    info: GatewayInfo
    coordinator: GatewayCoordinator


type AtomicConfigEntry = ConfigEntry[GatewayData]
