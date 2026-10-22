"""Ecowitt local HTTP/JSON API."""

from http import HTTPStatus
import json
import re

import aiohttp
from yarl import URL

from homeassistant.helpers.device_registry import format_mac

from .const import REQUEST_TIMEOUT
from .models import GatewayInfo
from .parsers import is_json_object


class GatewayError(Exception):
    """Gateway request or response failure."""


class UnsupportedGatewayError(GatewayError):
    """Unverified gateway model."""


def normalize_mac(value: object) -> str:
    """Require a nonzero unicast MAC address."""
    if not isinstance(value, str) or not re.fullmatch(
        r"(?:[0-9a-fA-F]{12}|(?:[0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}|"
        r"(?:[0-9a-fA-F]{2}-){5}[0-9a-fA-F]{2}|"
        r"(?:[0-9a-fA-F]{4}\.){2}[0-9a-fA-F]{4})",
        value.strip(),
    ):
        raise ValueError("Gateway did not return a valid MAC address")
    mac = format_mac(value.strip())
    if mac == "00:00:00:00:00:00" or int(mac[:2], 16) & 1:
        raise ValueError("Gateway did not return a unicast hardware MAC address")
    return mac


def normalize_base_url(value: object) -> str:
    """Accept a host or HTTP(S) origin."""
    if not isinstance(value, str):
        raise ValueError("Enter a gateway host or base URL")
    value = value.strip()
    if not value or any(character.isspace() for character in value):
        raise ValueError("Enter a gateway host or base URL")
    if "://" not in value:
        value = f"http://{value}"
    # Check components before normalization can remove credentials or path segments.
    url = URL(value, encoded=True)
    if (
        url.scheme not in {"http", "https"}
        or not url.raw_host
        or "@" in url.raw_authority
        or url.raw_path.strip("/")
        or "?" in value
        or "#" in value
        or "\\" in value
    ):
        raise ValueError("Enter an HTTP base URL without credentials, path, or query")
    return str(URL(value).origin())


class EcowittApiClient:
    """Ecowitt LAN API client."""

    def __init__(self, base_url: str, session: aiohttp.ClientSession) -> None:
        """Bind a gateway address to the shared session."""
        self.base_url = normalize_base_url(base_url)
        self._session = session

    async def _get(self, endpoint: str) -> object:
        """Do not follow redirects or include response data in errors."""
        try:
            async with self._session.get(
                f"{self.base_url}/{endpoint}",
                timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT),
                allow_redirects=False,
            ) as response:
                if response.status != HTTPStatus.OK:
                    raise GatewayError(f"Gateway returned HTTP {response.status}")
                payload: object = await response.json()
        except (
            TimeoutError,
            aiohttp.ClientError,
            json.JSONDecodeError,
            UnicodeError,
        ) as err:
            raise GatewayError("Could not read gateway JSON") from err
        return payload

    async def _get_object(self, endpoint: str) -> dict[str, object]:
        payload = await self._get(endpoint)
        if not is_json_object(payload):
            raise GatewayError("Gateway returned an unexpected JSON structure")
        return payload

    async def _get_records(self, endpoint: str) -> list[dict[str, object]]:
        payload = await self._get(endpoint)
        if not isinstance(payload, list):
            raise GatewayError("Invalid Ecowitt sensor metadata list")
        records: list[dict[str, object]] = []
        for record in payload:
            if not is_json_object(record):
                raise GatewayError("Invalid Ecowitt sensor metadata record")
            records.append(record)
        return records

    async def async_get_info(self) -> GatewayInfo:
        """Read gateway identity and firmware."""
        payload = await self._get_object("get_version")
        version = payload.get("version")
        match = (
            re.fullmatch(r"Version:\s*(GW\w+)_V([\w.\-]+)", version)
            if isinstance(version, str)
            else None
        )
        if match is None:
            raise UnsupportedGatewayError(
                "Could not identify a supported Ecowitt gateway"
            )
        network = await self._get_object("get_network_info")
        try:
            mac = normalize_mac(network.get("mac"))
        except ValueError as err:
            raise GatewayError(
                "Gateway did not return a valid hardware MAC address"
            ) from err
        return GatewayInfo(model=match[1], firmware=match[2], mac=mac)

    async def async_get_live_data(self) -> dict[str, object]:
        """Fetch live data."""
        return await self._get_object("get_livedata_info")

    async def async_get_channel_metadata(
        self, endpoint: str
    ) -> list[dict[str, object]]:
        """Fetch records from the requested channel metadata endpoint."""
        return await self._get_records(endpoint)

    async def async_get_registrations(self) -> list[dict[str, object]]:
        """Fetch every registration page, including unoccupied slots."""
        version = await self._get_object("get_version")
        # Older firmware uses the specification's two pages without this field.
        raw_pages = version.get("sensorid_page", "2")
        if isinstance(raw_pages, bool) or not isinstance(raw_pages, (str, int)):
            raise GatewayError("Invalid Ecowitt sensor page count")
        if not re.fullmatch(r"[0-9]+", str(raw_pages)) or not 1 <= int(raw_pages) <= 16:
            raise GatewayError("Invalid Ecowitt sensor page count")
        registrations: list[dict[str, object]] = []
        for page in range(1, int(raw_pages) + 1):
            registrations.extend(
                await self._get_records(f"get_sensors_info?page={page}")
            )
        return registrations
