# Ecowitt Atomic

Currently under development. Do not use.

## Installation and setup

1. Copy `custom_components/ecowitt_atomic` into your HA configuration's
   `custom_components` directory, then restart Home Assistant.
2. Go to **Settings → Devices & services → Add integration → Ecowitt Atomic**.
3. Enter the gateway's IP address, hostname, or HTTP/HTTPS base URL. A bare address
   defaults to HTTP. Credentials, paths, queries, and fragments are not accepted.
4. Repeat to add another gateway. The integration reads its MAC address from
   `get_network_info` to identify the hardware, so IP addresses and hostname
   aliases for the same gateway cannot create duplicate entries.

## Development

This integration is unreleased. HA development state is disposable: breaking
changes can require recreating the dedicated development instance. We do not
maintain migrations or compatibility with earlier development builds.
