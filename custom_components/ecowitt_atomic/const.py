"""Constants for Ecowitt Atomic."""

import logging
from datetime import timedelta

DOMAIN = "ecowitt_atomic"
CONF_BASE_URL = "base_url"
CONF_MAC = "mac"
POLL_INTERVAL = timedelta(seconds=30)
REQUEST_TIMEOUT = 10
LOGGER = logging.getLogger(__package__)
