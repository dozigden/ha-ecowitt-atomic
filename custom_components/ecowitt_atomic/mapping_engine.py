"""Resolve ownership and evaluate reading mappings."""

from collections import Counter, defaultdict
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace

from .models import EcowittSensorData, Reading, TextReading
from .parsers import is_json_object, parse_radio_id, parse_text, unique_records


@dataclass(frozen=True)
class LiveGroup:
    """A record group in get_livedata_info."""

    name: str


@dataclass(frozen=True)
class RegistrationRecords:
    """Records from get_sensors_info."""


@dataclass(frozen=True)
class OwnRegistration:
    """The identity of the registration record itself."""


@dataclass(frozen=True)
class ChannelRadioJoin:
    """Link a live channel to registration through metadata's radio ID."""

    endpoint: str
    live_channel: str
    metadata_channel: str
    metadata_radio_id: str


@dataclass(frozen=True)
class FieldReading:
    """Interpret a field as a recognised capability."""

    field: str
    key: str
    parser: Callable[[object], Reading | TextReading | None]

    def parse(self, record: Mapping[str, object]) -> Reading | TextReading | None:
        """Parse this field from its source record."""
        return self.parser(record.get(self.field))


@dataclass(frozen=True)
class UnitFieldReading:
    """Interpret a value with a unit supplied in another field."""

    field: str
    key: str
    unit_field: str
    parser: Callable[[object, object], Reading | None]

    def parse(self, record: Mapping[str, object]) -> Reading | None:
        """Parse the value and unit from their source record."""
        return self.parser(record.get(self.field), record.get(self.unit_field))


@dataclass(frozen=True)
class MappingRule:
    """Describe a source, its owner and its understood readings."""

    source: LiveGroup | RegistrationRecords
    owner: ChannelRadioJoin | OwnRegistration
    readings: tuple[FieldReading | UnitFieldReading, ...]
    name_field: str | None = None


@dataclass(frozen=True)
class GatewayReadingMapping:
    """One identified observation in a shared gateway group."""

    source: LiveGroup
    item_id: str
    reading: FieldReading | UnitFieldReading


def apply_gateway_mappings(
    payload: Mapping[str, object], rules: Sequence[GatewayReadingMapping]
) -> dict[str, Reading]:
    """Map shared observations to gateway reading keys."""
    candidates: dict[str, list[Reading]] = defaultdict(list)
    for rule in rules:
        group = payload.get(rule.source.name)
        if not isinstance(group, list):
            continue
        records = [
            record
            for record in group
            if is_json_object(record) and record.get("id") == rule.item_id
        ]
        if len(records) != 1:
            continue
        reading = rule.reading.parse(records[0])
        if isinstance(reading, Reading):
            candidates[rule.reading.key].append(reading)
    return {key: values[0] for key, values in candidates.items() if len(values) == 1}


@dataclass(frozen=True)
class _Observation:
    """One mapping's proposed reading and device name."""

    capability_key: str
    reading: Reading | TextReading
    source_name: str | None


def metadata_endpoints(rules: Sequence[MappingRule]) -> tuple[str, ...]:
    """List distinct metadata dependencies in declaration order."""
    endpoints: list[str] = []
    for rule in rules:
        if isinstance(rule.owner, ChannelRadioJoin):
            endpoint = rule.owner.endpoint
            if endpoint not in endpoints:
                endpoints.append(endpoint)
    return tuple(endpoints)


def apply_reading_mappings(
    payload: Mapping[str, object],
    metadata: Mapping[str, Sequence[Mapping[str, object]]],
    ecowitt_sensors: Mapping[int, EcowittSensorData],
    rules: Sequence[MappingRule],
    *,
    registrations: Sequence[Mapping[str, object]],
) -> dict[int, EcowittSensorData]:
    """Resolve owners, parse readings and merge this poll's observations."""
    observations_by_slot: dict[int, list[_Observation]] = defaultdict(list)
    for rule in rules:
        owned_records = _resolve_records(
            rule, payload, metadata, ecowitt_sensors, registrations
        )
        for slot, record in owned_records.items():
            source_name = None
            if rule.name_field:
                parsed_name = parse_text(record.get(rule.name_field))
                if parsed_name is not None:
                    source_name = parsed_name.value

            for reading_mapping in rule.readings:
                reading = reading_mapping.parse(record)
                if reading is None:
                    continue
                observations_by_slot[slot].append(
                    _Observation(
                        capability_key=reading_mapping.key,
                        reading=reading,
                        source_name=source_name,
                    )
                )

    result: dict[int, EcowittSensorData] = {}
    for slot, ecowitt_sensor in ecowitt_sensors.items():
        result[slot] = _merge_observations(ecowitt_sensor, observations_by_slot[slot])
    return result


def _resolve_records(
    rule: MappingRule,
    payload: Mapping[str, object],
    metadata: Mapping[str, Sequence[Mapping[str, object]]],
    ecowitt_sensors: Mapping[int, EcowittSensorData],
    registrations: Sequence[Mapping[str, object]],
) -> dict[int, Mapping[str, object]]:
    """Select source records and link them to registered Ecowitt sensors."""
    if isinstance(rule.source, RegistrationRecords) and isinstance(
        rule.owner, OwnRegistration
    ):
        return {
            slot: record
            for slot, record in unique_records(registrations, "type").items()
            if slot in ecowitt_sensors
        }

    if isinstance(rule.source, LiveGroup) and isinstance(rule.owner, ChannelRadioJoin):
        group = payload.get(rule.source.name)
        if not isinstance(group, list):
            return {}
        live_records = [record for record in group if is_json_object(record)]
        channel_metadata = metadata.get(rule.owner.endpoint, ())
        return _resolve_channels(
            rule.owner, live_records, channel_metadata, ecowitt_sensors
        )

    raise ValueError("Unsupported mapping source and owner combination")


def _resolve_channels(
    owner: ChannelRadioJoin,
    records: Sequence[Mapping[str, object]],
    metadata: Sequence[Mapping[str, object]],
    ecowitt_sensors: Mapping[int, EcowittSensorData],
) -> dict[int, Mapping[str, object]]:
    """Return records with an unambiguous registered owner."""
    registered_slots_by_radio_id: dict[str, list[int]] = defaultdict(list)
    for slot, ecowitt_sensor in ecowitt_sensors.items():
        registered_slots_by_radio_id[ecowitt_sensor.radio_id].append(slot)

    metadata_by_channel = unique_records(metadata, owner.metadata_channel)
    metadata_count_by_radio_id = Counter(
        parse_radio_id(record.get(owner.metadata_radio_id)) for record in metadata
    )
    live_records_by_channel = unique_records(records, owner.live_channel)

    owned_records: dict[int, Mapping[str, object]] = {}
    for channel, live_record in live_records_by_channel.items():
        channel_metadata = metadata_by_channel.get(channel)
        if channel_metadata is None:
            continue
        radio_id = parse_radio_id(channel_metadata.get(owner.metadata_radio_id))
        if radio_id is None:
            continue

        # The radio ID must identify one metadata channel and one registration.
        if metadata_count_by_radio_id[radio_id] != 1:
            continue
        matching_slots = registered_slots_by_radio_id.get(radio_id, [])
        if len(matching_slots) != 1:
            continue

        slot = matching_slots[0]
        owned_records[slot] = live_record
    return owned_records


def _merge_observations(
    ecowitt_sensor: EcowittSensorData,
    observations: Sequence[_Observation],
) -> EcowittSensorData:
    """Build one Ecowitt sensor's current readings and name."""
    candidates_by_capability: dict[str, list[_Observation]] = defaultdict(list)
    for observation in observations:
        candidates_by_capability[observation.capability_key].append(observation)

    readings: dict[str, Reading | TextReading] = {}
    source_names: list[str] = []
    for capability_key, candidates in candidates_by_capability.items():
        # Multiple producers are ambiguous, even if their current values agree.
        if len(candidates) != 1:
            continue
        observation = candidates[0]
        readings[capability_key] = observation.reading
        if (
            observation.source_name is not None
            and observation.source_name not in source_names
        ):
            source_names.append(observation.source_name)

    name = ecowitt_sensor.name
    if len(source_names) == 1:
        name = source_names[0]
    return replace(ecowitt_sensor, readings=readings, name=name)
