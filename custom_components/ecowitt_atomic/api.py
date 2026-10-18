"""Async client for Ecowitt's local HTTP/JSON API."""

import json
import re
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import aiohttp

from .const import REQUEST_TIMEOUT
from .models import GatewayInfo, Reading, parse_internal_readings


class GatewayError(Exception):
    """A gateway request or response could not be used."""


class UnsupportedGateway(GatewayError):
    """Internal reading support has not been verified for this gateway model."""


def normalize_mac(value: Any) -> str:
    """Normalize a unicast hardware MAC without accepting missing placeholders."""
    if not isinstance(value, str) or not re.fullmatch(
        r"(?:[0-9a-fA-F]{12}|(?:[0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}|"
        r"(?:[0-9a-fA-F]{2}-){5}[0-9a-fA-F]{2}|"
        r"(?:[0-9a-fA-F]{4}\.){2}[0-9a-fA-F]{4})",
        value.strip(),
    ):
        raise ValueError("Gateway did not return a valid MAC address")
    compact = re.sub(r"[:.\-]", "", value.strip()).lower()
    if compact == "000000000000" or int(compact[:2], 16) & 1:
        raise ValueError("Gateway did not return a unicast hardware MAC address")
    return ":".join(compact[index : index + 2] for index in range(0, 12, 2))


def normalize_base_url(value: str) -> str:
    """Normalize a host or HTTP base URL without losing ports or IPv6 brackets."""
    value = value.strip()
    if not value or any(character.isspace() for character in value):
        raise ValueError("Enter a gateway host or base URL")
    if "://" not in value:
        value = f"http://{value}"
    parts = urlsplit(value)
    if (
        parts.scheme.lower() not in {"http", "https"}
        or not parts.hostname
        or parts.username is not None
        or parts.password is not None
        or parts.query
        or parts.fragment
        or parts.path.strip("/")
        or "?" in value
        or "#" in value
        or "\\" in value
    ):
        raise ValueError("Enter an HTTP base URL without credentials, path, or query")
    host = parts.hostname.lower().encode("idna").decode("ascii")
    port = parts.port  # Validate the port, including its range.
    if ":" in host:
        host = f"[{host}]"
    if port is not None and (parts.scheme.lower(), port) not in {
        ("http", 80),
        ("https", 443),
    }:
        host = f"{host}:{port}"
    return urlunsplit((parts.scheme.lower(), host, "", "", ""))


class EcowittApiClient:
    """Fetch supported gateway information and internal readings."""

    def __init__(self, base_url: str, session: aiohttp.ClientSession) -> None:
        self.base_url = normalize_base_url(base_url)
        self._session = session

    async def _get(self, endpoint: str) -> dict[str, Any]:
        """Request JSON without following redirects or including payloads in errors."""
        try:
            async with self._session.get(
                f"{self.base_url}/{endpoint}",
                timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT),
                allow_redirects=False,
            ) as response:
                if response.status != 200:
                    raise GatewayError(f"Gateway returned HTTP {response.status}")
                payload = await response.json()
        except (
            TimeoutError,
            aiohttp.ClientError,
            json.JSONDecodeError,
            UnicodeError,
        ) as err:
            raise GatewayError("Could not read gateway JSON") from err
        if not isinstance(payload, dict):
            raise GatewayError("Gateway returned an unexpected JSON structure")
        return payload

    async def async_get_info(self) -> GatewayInfo:
        """Verify the model before attributing indoor readings to the gateway."""
        payload = await self._get("get_version")
        version = payload.get("version")
        match = (
            re.fullmatch(r"Version:\s*(GW\w+)_V([\w.\-]+)", version)
            if isinstance(version, str)
            else None
        )
        if match is None:
            raise UnsupportedGateway("Could not identify a supported Ecowitt gateway")
        # GW2000A is the hardware verified for this first implementation pass.
        if match[1] != "GW2000A":
            raise UnsupportedGateway(
                "Internal readings are currently verified for GW2000A only"
            )
        network = await self._get("get_network_info")
        try:
            mac = normalize_mac(network.get("mac"))
        except ValueError as err:
            raise GatewayError(
                "Gateway did not return a valid hardware MAC address"
            ) from err
        return GatewayInfo(model=match[1], firmware=match[2], mac=mac)

    async def async_get_readings(self) -> dict[str, Reading]:
        """Get indoor readings without requesting configuration or credentials."""
        return parse_internal_readings(await self._get("get_livedata_info"))
