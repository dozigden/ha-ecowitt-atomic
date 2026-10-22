"""Configuration flow tests."""

from unittest.mock import patch

from custom_components.ecowitt_atomic.api import GatewayError, UnsupportedGatewayError
from custom_components.ecowitt_atomic.const import CONF_BASE_URL, CONF_MAC, DOMAIN
from custom_components.ecowitt_atomic.models import GatewayInfo
import pytest

from homeassistant.config_entries import SOURCE_RECONFIGURE, SOURCE_USER
from homeassistant.data_entry_flow import FlowResultType

from .conftest import BASE_URL, MAC, SECOND_MAC

pytestmark = pytest.mark.usefixtures("mock_api")


async def test_unverified_model_rejected(hass, mock_api):
    """Apply the gateway support policy before creating an entry."""
    mock_api.async_get_info.return_value = GatewayInfo("GW3000", "1.0.0", MAC)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}, data={CONF_BASE_URL: BASE_URL}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "unsupported_gateway"}
    mock_api.async_get_live_data.assert_not_awaited()


async def test_configure_gateway(hass):
    """Create a MAC-identified entry from a normalized address."""
    with patch("custom_components.ecowitt_atomic.async_setup_entry", return_value=True):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_USER}
        )
        assert result["type"] is FlowResultType.FORM
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_BASE_URL: "Gateway.Example:80/"}
        )
        await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "GW2000A (020000000001)"
    assert result["data"] == {CONF_BASE_URL: BASE_URL, CONF_MAC: MAC}
    assert result["result"].unique_id == MAC
    assert result["result"].version == 1


@pytest.mark.parametrize(
    "address", ["HTTP://Gateway.Example:80/", "different-alias.example"]
)
async def test_duplicate_by_hardware_mac(hass, entry, mock_api, address):
    """Reject aliases for an already configured gateway."""
    entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_USER},
        data={CONF_BASE_URL: address},
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    mock_api.async_get_info.assert_awaited_once()
    mock_api.async_get_live_data.assert_not_awaited()


async def test_distinct_hardware_can_use_same_address(hass, entry, mock_api):
    """Distinguish gateways by hardware identity."""
    entry.add_to_hass(hass)
    mock_api.async_get_info.return_value = GatewayInfo("GW2000A", "3.3.2", SECOND_MAC)
    with patch("custom_components.ecowitt_atomic.async_setup_entry", return_value=True):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_USER}, data={CONF_BASE_URL: BASE_URL}
        )
        await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["result"].unique_id == SECOND_MAC


async def test_reconfigure_address(hass, entry):
    """Accept a new address for the same gateway."""
    entry.add_to_hass(hass)
    with patch("custom_components.ecowitt_atomic.async_setup_entry", return_value=True):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_RECONFIGURE, "entry_id": entry.entry_id}
        )
        assert result["step_id"] == "reconfigure"
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_BASE_URL: "new-address.example"}
        )
        await hass.async_block_till_done()
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert entry.unique_id == MAC
    assert entry.data == {CONF_BASE_URL: "http://new-address.example", CONF_MAC: MAC}


async def test_reconfigure_wrong_gateway(hass, entry, mock_api):
    """Reject a different gateway at the new address."""
    entry.add_to_hass(hass)
    mock_api.async_get_info.return_value = GatewayInfo("GW2000A", "3.3.2", SECOND_MAC)
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_RECONFIGURE, "entry_id": entry.entry_id},
        data={CONF_BASE_URL: "other.example"},
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "wrong_gateway"
    assert entry.data[CONF_BASE_URL] == BASE_URL


@pytest.mark.parametrize(
    ("failure", "expected"),
    [
        (GatewayError("offline"), "cannot_connect"),
        (UnsupportedGatewayError("unverified"), "unsupported_gateway"),
    ],
)
async def test_connection_errors(hass, mock_api, failure, expected):
    """Show connection and model validation errors."""
    mock_api.async_get_info.side_effect = failure
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}, data={CONF_BASE_URL: BASE_URL}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": expected}


@pytest.mark.parametrize(
    "data",
    [
        {CONF_BASE_URL: "gateway.example/path"},
        {},
        {CONF_BASE_URL: None},
        {CONF_BASE_URL: 123},
        {CONF_BASE_URL: False},
        {CONF_BASE_URL: ["gateway.example"]},
        {CONF_BASE_URL: {"host": "gateway.example"}},
    ],
)
async def test_invalid_url(hass, mock_api, data):
    """Reject missing, mistyped, and invalid addresses before requests."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_USER},
        data=data,
    )
    assert result["errors"] == {CONF_BASE_URL: "invalid_url"}
    mock_api.async_get_info.assert_not_awaited()


async def test_no_readings(hass, mock_api):
    """Require a valid reading during initial setup."""
    mock_api.async_get_live_data.return_value = {}
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}, data={CONF_BASE_URL: BASE_URL}
    )
    assert result["errors"] == {"base": "no_readings"}


@pytest.mark.parametrize(
    "operation",
    [
        "async_get_live_data",
        "async_get_registrations",
        "async_get_channel_metadata",
    ],
)
async def test_setup_checks_the_complete_poll(hass, mock_api, operation):
    """Keep initial validation sensitive to every required gateway response."""
    getattr(mock_api, operation).side_effect = GatewayError("request failed")
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}, data={CONF_BASE_URL: BASE_URL}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}
