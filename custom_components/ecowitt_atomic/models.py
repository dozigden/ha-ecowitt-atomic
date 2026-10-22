"""Gateway data models."""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class GatewayInfo:
    """Gateway identity and firmware."""

    model: str
    firmware: str
    mac: str

    @property
    def name(self) -> str:
        """Return the model and compact MAC."""
        return f"{self.model} ({self.mac.replace(':', '').upper()})"


@dataclass(frozen=True)
class Reading:
    """A reading in canonical units."""

    value: float
    unit: str


@dataclass(frozen=True)
class TextReading:
    """A text value supplied to a sensor entity."""

    value: str


@dataclass(frozen=True)
class EcowittSensorData:
    """Registered Ecowitt sensor metadata and current readings."""

    name: str
    radio_id: str
    readings: dict[str, Reading | TextReading] = field(default_factory=dict)
    img: str | None = None
    registration_name: str | None = None


@dataclass(frozen=True)
class GatewayReadings:
    """Current gateway and attributed Ecowitt sensor readings."""

    gateway: dict[str, Reading] = field(default_factory=dict)
    ecowitt_sensors: dict[int, EcowittSensorData] = field(default_factory=dict)
