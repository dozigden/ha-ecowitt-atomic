"""Supported Ecowitt API reading mappings."""

from .const import (
    BATTERY,
    GATEWAY_NAME,
    HUMIDITY,
    RADIO_ID,
    RSSI,
    SOIL_MOISTURE,
    TEMPERATURE,
)
from .mapping_engine import (
    ChannelRadioJoin,
    FieldReading,
    LiveGroup,
    MappingRule,
    OwnRegistration,
    RegistrationRecords,
    UnitFieldReading,
)
from .parsers import (
    parse_battery,
    parse_percentage,
    parse_radio_id_reading,
    parse_rssi,
    parse_temperature,
    parse_text,
)

SOIL_MOISTURE_MAPPING = MappingRule(
    source=LiveGroup("ch_soil"),
    owner=ChannelRadioJoin(
        endpoint="get_cli_soilad",
        live_channel="channel",
        metadata_channel="ch",
        metadata_radio_id="id",
    ),
    readings=(FieldReading("humidity", SOIL_MOISTURE, parse_percentage),),
    name_field="name",
)

TEMPERATURE_HUMIDITY_MAPPING = MappingRule(
    source=LiveGroup("ch_aisle"),
    owner=ChannelRadioJoin(
        endpoint="get_cli_multiCh",
        live_channel="channel",
        metadata_channel="channel",
        metadata_radio_id="id",
    ),
    readings=(
        UnitFieldReading("temp", TEMPERATURE, "unit", parse_temperature),
        FieldReading("humidity", HUMIDITY, parse_percentage),
    ),
    name_field="name",
)

TEMPERATURE_MAPPING = MappingRule(
    source=LiveGroup("ch_temp"),
    owner=ChannelRadioJoin(
        endpoint="get_cli_wh34",
        live_channel="channel",
        metadata_channel="channel",
        metadata_radio_id="id",
    ),
    readings=(UnitFieldReading("temp", TEMPERATURE, "unit", parse_temperature),),
    name_field="name",
)

REGISTRATION_MAPPING = MappingRule(
    source=RegistrationRecords(),
    owner=OwnRegistration(),
    readings=(
        FieldReading("name", GATEWAY_NAME, parse_text),
        FieldReading("id", RADIO_ID, parse_radio_id_reading),
        FieldReading("batt", BATTERY, parse_battery),
        FieldReading("rssi", RSSI, parse_rssi),
    ),
)

READING_MAPPINGS = (
    SOIL_MOISTURE_MAPPING,
    TEMPERATURE_HUMIDITY_MAPPING,
    TEMPERATURE_MAPPING,
    REGISTRATION_MAPPING,
)
