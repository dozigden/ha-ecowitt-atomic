"""Gateway information and readings from the Ecowitt HTTP API."""

import math
import re
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class GatewayInfo:
    """Model and firmware reported by the gateway."""

    model: str
    firmware: str
    mac: str

    @property
    def name(self) -> str:
        """Name the gateway using its model and full MAC without separators."""
        return f"{self.model} ({self.mac.replace(':', '').upper()})"


@dataclass(frozen=True)
class Reading:
    """A gateway-internal measurement in a canonical unit."""

    value: float
    unit: str


def _number(value: Any) -> float | None:
    """Reject placeholders, malformed numbers, booleans, and non-finite values."""
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        return None
    try:
        number = float(value)
    except ValueError, OverflowError:
        return None
    return number if math.isfinite(number) else None


def _pressure(value: Any) -> Reading | None:
    """Convert a pressure with an explicit API unit to hPa."""
    if not isinstance(value, str):
        return None
    match = re.fullmatch(
        r"\s*([+-]?\d+(?:\.\d+)?)\s*(hpa|mb|inhg|mmhg)\s*", value, re.I
    )
    if not match:
        return None
    number = _number(match[1])
    if number is None or number <= 0:
        return None
    factor = {"hpa": 1, "mb": 1, "inhg": 33.8638866667, "mmhg": 1.33322387415}
    return Reading(number * factor[match[2].lower()], "hPa")


def parse_internal_readings(payload: dict[str, Any]) -> dict[str, Reading]:
    """Read only the indoor group; external Ecowitt sensor groups are ignored."""
    group = payload.get("wh25")
    if not isinstance(group, list) or not group or not isinstance(group[0], dict):
        return {}
    indoor = group[0]
    readings: dict[str, Reading] = {}
    temperature = _number(indoor.get("intemp"))
    unit = str(indoor.get("unit", "")).strip().upper().replace("°", "")
    if temperature is not None and unit in {"C", "F"}:
        readings["indoor_temperature"] = Reading(
            temperature if unit == "C" else (temperature - 32) * 5 / 9, "°C"
        )
    humidity_raw = indoor.get("inhumi")
    if isinstance(humidity_raw, str):
        humidity_raw = humidity_raw.strip().removesuffix("%")
    humidity = _number(humidity_raw)
    if humidity is not None and 0 <= humidity <= 100:
        readings["indoor_humidity"] = Reading(humidity, "%")
    for field, key in (("abs", "absolute_pressure"), ("rel", "relative_pressure")):
        if (pressure := _pressure(indoor.get(field))) is not None:
            readings[key] = pressure
    return readings
