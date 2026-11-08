# Ecowitt Atomic

Ecowitt Atomic is an opinionated Ecowitt integration for Home Assistant. It may
or may not be ready for other people to use.

It puts readings on the device for the Ecowitt sensor they came from when that
can be established purely from the gateway's local API data. When it can't,
those readings stay as sensors on the gateway device. This isn't ideal, but it
is painfully *correct* — and that's the point of this integration. Hence
opinionated :)

In practice, readings from Ecowitt sensors you can have many of, such as
soil moisture and temperature/humidity channels, appear on their corresponding
devices in Home Assistant. Shared outdoor weather, wind, and rain readings stay
on the gateway device.

Registered Ecowitt sensors still get their own devices with available diagnostics,
eg battery and signal stregth.

<!-- ha-marketplace:exclude-start -->
## Installation

[![Open your Home Assistant instance and open a repository in the Marketplace.](https://my.home-assistant.io/badges/marketplace_repository.svg)](https://my.home-assistant.io/redirect/marketplace_repository/?owner=dozigden&repository=ha-ecowitt-atomic&category=integration)
<!-- ha-marketplace:exclude-end -->
