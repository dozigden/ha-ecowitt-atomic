"""Synthetic gateway fixtures; never import private local captures."""

from unittest.mock import patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ecowitt_atomic.const import CONF_BASE_URL, CONF_MAC, DOMAIN
from custom_components.ecowitt_atomic.models import GatewayInfo, parse_internal_readings

BASE_URL = "http://gateway.example"
MAC = "02:00:00:00:00:01"
SECOND_MAC = "02:00:00:00:00:02"


@pytest.fixture(autouse=True)
def custom_integrations(enable_custom_integrations):
    """Enable the custom integration for HA's real loading path."""


@pytest.fixture(autouse=True)
def stable_time(freezer):
    freezer.move_to("2026-10-17T12:00:00+00:00")


@pytest.fixture
def live_payload():
    return {
        "wh25": [
            {
                "intemp": "21.5",
                "unit": "C",
                "inhumi": "55%",
                "abs": "1000.0 hPa",
                "rel": "1005.0 hPa",
            }
        ],
        "common_list": [{"id": "0x02", "val": "8.0", "unit": "C"}],
        "ch_aisle": [{"channel": "1", "temp": "12.0", "humidity": "90%"}],
    }


@pytest.fixture
def entry():
    return MockConfigEntry(
        domain=DOMAIN,
        unique_id=MAC,
        title="Test gateway",
        data={CONF_BASE_URL: BASE_URL, CONF_MAC: MAC},
        version=1,
    )


@pytest.fixture
def mock_api(live_payload):
    with (
        patch(
            "custom_components.ecowitt_atomic.EcowittApiClient", autospec=True
        ) as client_class,
        patch(
            "custom_components.ecowitt_atomic.config_flow.EcowittApiClient",
            client_class,
        ),
    ):
        client = client_class.return_value
        client.async_get_info.return_value = GatewayInfo("GW2000A", "3.3.2", MAC)
        client.async_get_readings.return_value = parse_internal_readings(live_payload)
        yield client
