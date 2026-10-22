"""Parse Ecowitt API records and readings."""

from collections.abc import Mapping, Sequence
import math
import re
from typing import TypeGuard

from .models import EcowittSensorData, Reading, TextReading


def is_json_object(value: object) -> TypeGuard[dict[str, object]]:
    """Check dictionary keys without assuming field types."""
    return isinstance(value, dict) and all(isinstance(key, str) for key in value)


def _number(value: object) -> float | None:
    """Return None for missing or invalid numbers."""
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        return None
    try:
        number = float(value)
    except ValueError, OverflowError:
        return None
    return number if math.isfinite(number) else None


def _pressure(value: object) -> Reading | None:
    """Parse pressure as hPa; unitless values are invalid."""
    if not isinstance(value, str):
        return None
    match = re.fullmatch(
        r"\s*([+-]?\d+(?:\.\d+)?)\s*(hpa|mb|inhg|mmhg)\s*", value, re.IGNORECASE
    )
    if not match:
        return None
    number = _number(match[1])
    if number is None or number <= 0:
        return None
    factor = {"hpa": 1, "mb": 1, "inhg": 33.8638866667, "mmhg": 1.33322387415}
    return Reading(number * factor[match[2].lower()], "hPa")


def parse_percentage(value: object) -> Reading | None:
    """Parse a percentage, including a valid zero."""
    if isinstance(value, str):
        value = value.strip().removesuffix("%")
    number = _number(value)
    return Reading(number, "%") if number is not None and 0 <= number <= 100 else None


def parse_temperature(value: object, raw_unit: object) -> Reading | None:
    """Parse Celsius or Fahrenheit as Celsius."""
    temperature = _number(value)
    unit = (
        raw_unit.strip().upper().removeprefix("°") if isinstance(raw_unit, str) else ""
    )
    if temperature is None or unit not in {"C", "F"}:
        return None
    return Reading(temperature if unit == "C" else (temperature - 32) * (5 / 9), "°C")


def parse_battery(value: object) -> Reading | None:
    """Represent gateway battery display codes as coarse percentages."""
    code = _integer(value)
    percentages = {0: 100, 1: 10, 2: 25, 3: 50, 4: 75, 5: 100}
    percentage = percentages.get(code) if code is not None else None
    return Reading(percentage, "%") if percentage is not None else None


def parse_rssi(value: object) -> Reading | None:
    """Parse registration RSSI as dBm."""
    number = _number(value)
    return Reading(number, "dBm") if number is not None else None


def _integer(value: object) -> int | None:
    """Parse a nonnegative decimal identifier."""
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return value
    if isinstance(value, str) and re.fullmatch(r"[0-9]+", value):
        return int(value)
    return None


def parse_radio_id(value: object) -> str | None:
    """Normalize radio IDs, excluding disabled and unreceived sentinels."""
    if not isinstance(value, str) or not re.fullmatch(
        r"(?:0[xX])?[0-9a-fA-F]{1,8}", value
    ):
        return None
    number = int(value, 16)
    return f"{number:X}" if number not in {0xFFFFFFFF, 0xFFFFFFFE} else None


def parse_text(value: object) -> TextReading | None:
    """Parse a nonempty, trimmed text value."""
    if isinstance(value, str) and value.strip():
        return TextReading(value.strip())
    return None


def parse_radio_id_reading(value: object) -> TextReading | None:
    """Parse a normalized radio ID for display."""
    radio_id = parse_radio_id(value)
    return TextReading(radio_id) if radio_id is not None else None


def unique_records(
    records: Sequence[Mapping[str, object]], key: str
) -> dict[int, Mapping[str, object]]:
    """Index decimal identifiers without choosing between duplicate records."""
    indexed: dict[int, Mapping[str, object]] = {}
    seen: set[int] = set()
    for record in records:
        identifier = _integer(record.get(key))
        if identifier is None:
            continue
        if identifier in seen:
            indexed.pop(identifier, None)
            continue
        seen.add(identifier)
        indexed[identifier] = record
    return indexed


def parse_ecowitt_sensors(
    registrations: Sequence[Mapping[str, object]],
) -> dict[int, EcowittSensorData]:
    """Discover registered identities without assigning reading capabilities."""
    ecowitt_sensors: dict[int, EcowittSensorData] = {}
    for slot, record in unique_records(registrations, "type").items():
        if (radio_id := parse_radio_id(record.get("id"))) is None:
            continue
        name = record.get("name")
        img = record.get("img")
        ecowitt_sensors[slot] = EcowittSensorData(
            name=name.strip()
            if isinstance(name, str) and name.strip()
            else f"Ecowitt sensor {slot}",
            radio_id=radio_id,
            img=img if isinstance(img, str) else None,
            registration_name=name.strip()
            if isinstance(name, str) and name.strip()
            else None,
        )
    return ecowitt_sensors


def parse_internal_readings(payload: Mapping[str, object]) -> dict[str, Reading]:
    """Read the wh25 group used for gateway-internal readings."""
    group = payload.get("wh25")
    if not isinstance(group, list) or not group:
        return {}
    indoor: object = group[0]
    if not is_json_object(indoor):
        return {}
    readings: dict[str, Reading] = {}
    if (
        temperature := parse_temperature(indoor.get("intemp"), indoor.get("unit"))
    ) is not None:
        readings["indoor_temperature"] = temperature
    if (humidity := parse_percentage(indoor.get("inhumi"))) is not None:
        readings["indoor_humidity"] = humidity
    for field_name, key in (("abs", "absolute_pressure"), ("rel", "relative_pressure")):
        if (pressure := _pressure(indoor.get(field_name))) is not None:
            readings[key] = pressure
    return readings
