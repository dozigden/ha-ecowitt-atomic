"""Assemble gateway reading snapshots from recognised API data."""

from .api import EcowittApiClient
from .mapping_engine import (
    apply_gateway_mappings,
    apply_reading_mappings,
    metadata_endpoints,
)
from .mappings import GATEWAY_READING_MAPPINGS, READING_MAPPINGS
from .models import GatewayReadings
from .parsers import parse_ecowitt_sensors, parse_internal_readings


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
