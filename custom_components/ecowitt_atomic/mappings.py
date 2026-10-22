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
    GatewayReadingMapping,
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
    parse_rain_depth,
    parse_rain_rate,
    parse_rssi,
    parse_temperature,
    parse_text,
    parse_vpd,
    parse_wind_direction,
    parse_wind_speed,
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


GATEWAY_READING_MAPPINGS = (
    *(
        GatewayReadingMapping(
            LiveGroup("common_list"),
            item_id,
            UnitFieldReading("val", key, "unit", parse_temperature),
        )
        for item_id, key in (
            ("0x02", "outdoor_temperature"),
            ("0x03", "dew_point"),
            ("3", "feels_like"),
            ("4", "apparent_temperature"),
        )
    ),
    GatewayReadingMapping(
        LiveGroup("common_list"),
        "0x07",
        FieldReading("val", "outdoor_humidity", parse_percentage),
    ),
    GatewayReadingMapping(
        LiveGroup("common_list"), "5", FieldReading("val", "vpd", parse_vpd)
    ),
    *(
        GatewayReadingMapping(
            LiveGroup("common_list"),
            item_id,
            FieldReading("val", key, parse_wind_speed),
        )
        for item_id, key in (
            ("0x0B", "wind_speed"),
            ("0x0C", "wind_gust"),
            ("0x19", "wind_daily_maximum"),
        )
    ),
    *(
        GatewayReadingMapping(
            LiveGroup("common_list"),
            item_id,
            FieldReading("val", key, parse_wind_direction),
        )
        for item_id, key in (
            ("0x0A", "wind_direction"),
            ("0x6D", "wind_direction_10_minute_average"),
        )
    ),
    *(
        GatewayReadingMapping(
            LiveGroup(group),
            item_id,
            FieldReading("val", f"{prefix}_{period}", parse_rain_depth),
        )
        for group, prefix in (
            ("rain", "rain"),
            ("piezoRain", "piezo_rain"),
        )
        for item_id, period in (
            ("0x0D", "event"),
            ("0x7D", "hour"),
            ("0x7C", "24_hours"),
            ("0x10", "day"),
            ("0x11", "week"),
            ("0x12", "month"),
            ("0x13", "year"),
        )
    ),
    *(
        GatewayReadingMapping(
            LiveGroup(group), "0x0E", FieldReading("val", key, parse_rain_rate)
        )
        for group, key in (("rain", "rain_rate"), ("piezoRain", "piezo_rain_rate"))
    ),
)
