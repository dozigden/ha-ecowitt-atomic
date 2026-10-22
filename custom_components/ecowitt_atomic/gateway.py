"""Validate gateway support and assemble reading snapshots."""

from .api import EcowittApiClient, UnsupportedGatewayError
from .mapping_engine import (
    apply_gateway_mappings,
    apply_reading_mappings,
    metadata_endpoints,
)
from .mappings import GATEWAY_READING_MAPPINGS, READING_MAPPINGS
from .models import GatewayInfo, GatewayReadings
from .parsers import parse_ecowitt_sensors, parse_internal_readings


async def async_get_gateway_info(client: EcowittApiClient) -> GatewayInfo:
    """Identify a gateway and require a verified model."""
    info = await client.async_get_info()
    if info.model != "GW2000A":
        raise UnsupportedGatewayError(
            "Reading mappings are currently verified for GW2000A only"
        )
    return info


async def async_read_gateway(client: EcowittApiClient) -> GatewayReadings:
    """Fetch and interpret one snapshot for setup validation or polling."""
    payload = await client.async_get_live_data()
    registrations = await client.async_get_registrations()
    metadata = {
        endpoint: await client.async_get_channel_metadata(endpoint)
        for endpoint in metadata_endpoints(READING_MAPPINGS)
    }
    return GatewayReadings(
        gateway={
            **parse_internal_readings(payload),
            **apply_gateway_mappings(payload, GATEWAY_READING_MAPPINGS),
        },
        ecowitt_sensors=apply_reading_mappings(
            payload,
            metadata,
            parse_ecowitt_sensors(registrations),
            READING_MAPPINGS,
            registrations=registrations,
        ),
    )
