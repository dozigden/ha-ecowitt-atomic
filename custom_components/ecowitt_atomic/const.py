"""Constants for Ecowitt Atomic."""

from datetime import timedelta
import logging

DOMAIN = "ecowitt_atomic"
MIN_HA_VERSION = "2026.10.2"
CONF_BASE_URL = "base_url"
CONF_MAC = "mac"
POLL_INTERVAL = timedelta(minutes=1)
REQUEST_TIMEOUT = 10
SOIL_MOISTURE = "soil_moisture"
TEMPERATURE = "temperature"
HUMIDITY = "humidity"
GATEWAY_NAME = "gateway_name"
RADIO_ID = "radio_id"
BATTERY = "battery"
RSSI = "rssi"
LOGGER = logging.getLogger(__package__)
