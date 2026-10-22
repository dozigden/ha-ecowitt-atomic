"""Synthetic gateway fixtures. Keep local captures out of fixtures."""

from unittest.mock import patch

from custom_components.ecowitt_atomic.api import normalize_base_url
from custom_components.ecowitt_atomic.const import CONF_BASE_URL, CONF_MAC, DOMAIN
from custom_components.ecowitt_atomic.models import GatewayInfo
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

BASE_URL = "http://gateway.example"
MAC = "02:00:00:00:00:01"
SECOND_MAC = "02:00:00:00:00:02"


@pytest.fixture(autouse=True)
def custom_integrations(enable_custom_integrations):
    """Enable custom integrations."""


@pytest.fixture(autouse=True)
def stable_time(freezer):
    """Freeze the clock for polling tests."""
    freezer.move_to("2026-10-17T12:00:00+00:00")


@pytest.fixture
def live_payload():
    """Provide indoor readings and unrelated Ecowitt sensor groups."""
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
    """Provide a MAC-identified config entry."""
    return MockConfigEntry(
        domain=DOMAIN,
        unique_id=MAC,
        title="Test gateway",
        data={CONF_BASE_URL: BASE_URL, CONF_MAC: MAC},
        version=1,
    )


@pytest.fixture
def mock_api(live_payload):
    """Replace gateway requests with synthetic data."""
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

        def create_client(base_url, _session):
            """Retain the normalized address on the mocked client."""
            client.base_url = normalize_base_url(base_url)
            return client

        client_class.side_effect = create_client
        client.async_get_info.return_value = GatewayInfo("GW2000A", "3.3.2", MAC)
        client.async_get_live_data.return_value = live_payload
        client.async_get_registrations.return_value = []
        client.async_get_channel_metadata.return_value = []
        yield client
