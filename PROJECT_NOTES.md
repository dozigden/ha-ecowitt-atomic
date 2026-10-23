# Ecowitt Atomic — project notes

Last updated: 2026-10-23

## Keeping these notes current

The user has requested that this file be maintained throughout the project.
Record useful decisions, verified findings, constraints, references, and unresolved
questions as work progresses. Distinguish confirmed facts from assumptions, and
revise outdated entries. Do not record credentials, tokens, or OAuth callback URLs.

Project-specific agent instructions live in `AGENTS.md`. Keep machine-specific
infrastructure addresses, configuration, and connectivity findings in
[`.local/INFRASTRUCTURE.md`](.local/INFRASTRUCTURE.md). The entire `.local/`
directory is excluded from Git; keep shared project notes free of those details.

## Confirmed direction

- Project icon source: `assets/icon.svg`, supplied by the user on 2026-10-23.
  Original 1024 × 1024 SVG with a solid navy background; rendered successfully.
  Bundled HA brand exports are `brand/icon.png` (256 px) and `brand/icon@2x.png`
  (512 px) inside the integration. Development HA was restarted and authenticated
  requests verified both images, plus logo and dark-icon fallbacks.
- Shared outdoor, derived, wind and rain observations belong to the gateway
  device. Their entity identities must remain stable when the gateway changes
  physical source. Directly attributable readings and registration diagnostics
  remain on the individual devices. This decision supersedes earlier proposals
  to assign aggregated observations using physical-source priority resolvers.
  Conventional and piezo rain remain distinct streams because the API supplies
  separate totals.
- This is an unreleased development project. Do not build migrations or backward
  compatibility for earlier development states. The dedicated HA development
  instance is disposable and can be recreated for breaking changes. Revisit
  compatibility when preparing a supported release; see `AGENTS.md`.
- GitHub Actions runs `scripts/check` on pushes to main, pull requests targeting
  main, and manual dispatch. It uses the project Python pin and locked dependencies.
  Run the same checks locally; build packages with `scripts/package.py`. Automated
  releases and HACS publication remain deferred.
- Keep the development README minimal, retaining "Under development. Do not use."
  On 2026-10-20 the user requested a Mermaid diagram explaining soil moisture
  attribution, with example fields at each endpoint and their HA uses.
  Comments should explain constraints or non-obvious decisions, not repeat code.
- Build a Home Assistant integration with a separate device for each physical
  Ecowitt sensor, grouping its readings into entities, and a separate gateway device.
- Support multiple gateways in the same Home Assistant instance from the start.
  Use one config entry per normalized gateway MAC address, with independent polling
  and runtime state. Each entry owns its gateway device and devices representing
  Ecowitt sensors;
  failure or reload of one gateway must not disrupt the others. Prevent duplicate
  entries for the same MAC, including when reached through different addresses.
  The normalized base URL is connection data and may use an IP or hostname.
- Initial scope is read-only: expose readings and diagnostic information without
  modifying gateway or sensor configuration. Controls are deferred to later work.
- The initial implementation covered the gateway's own internal readings. Soil
  moisture is the first external reading implemented. Continue prioritizing
  hardware readily available for verification.
- Poll each gateway every 30 seconds with a fixed interval; no polling options
  or separate metadata refresh schedule in the first pass.
- Follow HA coordinator availability: failed gateway polls make its entities
  unavailable; successful polls with missing or invalid readings report unknown
  values. Use the latest successful response without carrying omitted readings
  forward. This supersedes the initial 90-second expiry policy.
- Target the latest stable Home Assistant release. Verify and record the exact
  release and its Python requirements when setting up the implementation.
- Device removal is manual. Once discovered, retain devices and their entities
  when readings or Ecowitt sensor registrations disappear; do not automatically prune
  them based on API responses or elapsed time. A manually removed device may be
  rediscovered if the gateway still reports it; no exclusion mechanism for now.
  The expected removal case is a device that is dead or gone.
- Gateway device names and integration entry titles use the model followed by
  the full uppercase MAC in parentheses, with the colons removed. Connection IP
  addresses are excluded from names. The normalized MAC remains the identity.
- Work with Ecowitt devices locally over the LAN.
- Use the newer HTTP/JSON API. The user explicitly confirmed local access.
- Use Ecowitt's linked HTTP API specification **v1.0.6** as the initial reference.
- Ecowitt states that the older TCP API is no longer maintained and will not
  support newly introduced Ecowitt sensors.

## Terminology convention

- Unqualified **device**, **entity**, and **sensor** use Home Assistant meanings.
  Explicitly use **Ecowitt sensor** for the hardware or its API representation,
  and **readings** for its measurements. One Ecowitt sensor maps to a device with
  multiple entities; each HA sensor entity exposes an individual reading.
- Apply this distinction to identifiers, comments, tests, documentation, and
  discussions. See `AGENTS.md` for the coding rule. Preserve upstream API names.

## Fundamental data model: capability-based discovery

- Discover Ecowitt sensors independently of their current readings. Represent
  each Ecowitt sensor with an identity, metadata, recognised capabilities, and
  current typed readings. HA maps the identity to a device, capabilities to entities,
  and readings to entity values. The gateway also supplies its own readings.
- Discover capabilities from recognised API fields and context; do not require
  a retail-model whitelist or restrict an Ecowitt sensor to a fixed family bundle.
  This describes our interpretation of the API, not an Ecowitt capability schema.
- Discover external reading capabilities only from observed, understood readings;
  do not assume them from registration type, model, image, or name. Registration
  establishes identity and metadata independently. A never-seen offline Ecowitt
  sensor therefore gets a device before any reading entities. Registration
  metadata can independently supply diagnostic entities. Create devices directly
  from registrations on setup and later polls;
  entity discovery must not gate device creation.
- Discover all valid registered Ecowitt sensors regardless of `img` or model.
  The user removed the temporary WH51/WH31 creation filter on 2026-10-21.
  Registration diagnostics apply to every discovered device; measurement entities
  still require recognised readings with verified ownership mappings.
- Use existing entity registrations as the record of discovered capabilities,
  rather than maintaining a separate persisted capability catalogue. On setup,
  enumerate this config entry's registrations for our platform, recover the
  Ecowitt sensor identity and reading key from our deterministic unique IDs, and
  instantiate those entities alongside newly discovered ones. Passing the same
  unique IDs to HA preserves existing registrations and user settings. Restore
  entity objects even when current readings or registrations are absent from the
  gateway; do not restore old values as current readings. The unique-ID format
  and device metadata restoration details remain implementation choices.
- Real motivating example: Ecowitt's WH52 combines soil moisture, temperature,
  and electrical conductivity (EC). Its
  [official manual](https://oss.ecowitt.net/uploads/20260608/WH52UserManual.pdf)
  confirms that WH51/WH51L/WH52 share 16 channels. This reinforces that type/slot
  alone cannot prescribe capabilities.
  Each understood capability should produce an entity on the same device without
  a retail-model whitelist. The WH52's local HTTP field layout and attribution
  have not been verified from hardware responses; do not infer them from app
  compatibility alone. New formats or ambiguous ownership may need mappings.
- Keep identity, reading ownership, and reading interpretation separate. Gateway
  MAC + API `type` remains the working Ecowitt sensor identifier; it does not
  prescribe a fixed bundle of entities for a retail model.
- Express support through understood API representations and reading mappings.
  Reuse reading parsers and HA entity definitions across Ecowitt sensor families.
  Add family-specific rules where needed for attribution, units, or status meaning.
- Field names and units alone do not establish meaning: `ch_soil[].humidity` is
  soil moisture, while `ch_aisle[].humidity` is air relative humidity. API context
  must establish both a reading's meaning and its owning Ecowitt sensor.
- Expose additional recognised readings through the shared model once ownership
  and interpretation are established. Do not guess ownership of aggregated data
  or create entities indiscriminately from arbitrary JSON fields.
- Missing readings do not imply changed capabilities or removal of a device or
  entity. Keep registration, reading availability, and entity retention distinct.
- Soil moisture is a concrete first application of this architecture. It should
  establish a reusable path for external Ecowitt sensors, rather than a separate
  implementation for every retail model. Verify new mappings against available
  hardware before relying on them.

## WH31 temperature and humidity — 2026-10-20

- Expanded discovery to WH31 registrations at the user's request. Devices still
  come from registration; temperature and humidity entities are each discovered
  only when their own valid reading arrives. Gateway name and Radio ID diagnostics
  use the existing registration mapping, including for offline Ecowitt sensors.
- Verified on GW2000A V3.3.2: `ch_aisle[].channel` joins
  `get_cli_multiCh[].channel`; metadata `id` then joins the registered radio ID.
  Live `temp` with `unit` supplies temperature, and live `humidity` supplies air
  relative humidity. Metadata `temp` and `humi` are calibration offsets and are
  not used as readings. Private captures are linked in the local infrastructure notes.
- Added one declarative mapping using the existing channel/radio join, plus
  reusable temperature/humidity capability definitions. `UnitFieldReading` passes
  a value and its sibling unit field to a typed parser. The temperature parser is
  shared with internal gateway readings and normalizes Celsius/Fahrenheit to Celsius.
  Unknown or missing units reject only the temperature reading.
- `scripts/check` passes 241 tests, Ruff, formatting, strict mypy and metadata
  validation. Coverage includes independent capability discovery, units, ownership
  ambiguity, soil moisture versus air humidity, offline devices, later readings,
  retained identities, fresh-runtime restoration and failure of the new endpoint.
- A disposable HA instance using the real gateway verified setup, refresh and
  reload, with 11 devices and 36 entities.
- Reviewed the WH31 changes: no actionable findings. Checked channel/radio
  ownership, independent capability discovery, unit conversion, registration-driven
  devices, restoration, diagnostics and handling of the new endpoint's failure.
  The 241-test check run and live smoke above cover the reviewed code.
- Subsequently restarted persistent development HA at the user's request.
  Confirmed frontend readiness and registration of all six WH31 measurement
  entities, bringing the integration to 36 entities. No integration errors
  appeared in the startup logs. The user approved committing the reviewed
  changes on 2026-10-20.

## Standalone temperature — 2026-10-21

- Added temperature from `ch_temp` at the user's request; battery and voltage
  entities remain deferred. Reuses the existing temperature parser, capability
  definition and channel/radio-ID join, without a model or registration-type filter.
- Verified on GW2000A V3.3.2: `get_cli_wh34` returns `channel`, radio `id`,
  configured `name` and a `temp` calibration offset. Join `ch_temp[].channel` to
  metadata `channel`, then metadata `id` to the registered radio ID. Only live
  `temp` and `unit` supply temperature readings. The endpoint is absent from the
  v1.0.6 specification's endpoint list; support here is based on the actual capture.
  This explicit link supersedes the proposed type-based channel mapping.
- All 254 tests, Ruff, strict mypy and metadata checks pass. Tests cover independent
  registration discovery, delayed temperature discovery, unfamiliar registration
  types/images, calibration exclusion, Fahrenheit/Celsius, ambiguous ownership,
  missing readings, reload retention and metadata endpoint failure.
- Updated the smoke script to include every registered Ecowitt sensor, matching
  the removal of the temporary discovery filter. A disposable HA instance verified
  the real gateway with 13 devices and 41 entities, including the standalone
  temperature reading; refresh and reload preserved entity identities.
  Restarted persistent development HA at the user's request and verified readiness
  with no integration errors in the startup logs. Reviewed the mapping, discovery
  changes and lifecycle coverage with no actionable findings. The user approved
  committing and pushing these changes on 2026-10-21.

## Battery display codes — 2026-10-21

- Inspected the GW2000A V3.3.2 web interface's `sensorsID.html`, `liveData.html`
  and `axjs.js`, and extracted the six images in `battImgobj`.
  The registration page interprets `batt` without a model/type-specific branch:
  `0` displays **Normal**, `1` a red low-battery icon, `2`–`5` progressively fuller
  green battery icons (one through four segments), `6` **DC**, and `9` **--**.
  Its missing-value branch also displays Normal; that does not establish a valid
  reading and should not be copied into HA's unknown-value handling.
- The live page uses the same image lookup for `battery`, hiding the icon for
  `0`. This supports a shared interpretation of the gateway's display codes,
  rather than treating registration `batt` as raw radio voltage/count data.
  The specification's type-specific battery comments do not consistently describe
  these observed HTTP display codes.
- The user's hypothesis is supported: some Ecowitt sensors report normal/low
  status, while others report a coarse battery level. The codes do not establish
  percentages or tell us, from `1` alone, which representation the hardware
  supports.
- User-selected percentage representation: codes `0` and `5` map to 100%;
  `1` maps to 10%, `2` to 25%, `3` to 50%, and `4` to 75%. The user revised
  code `1` from 0% to 10% on 2026-10-22. This is an integration
  convention for normal/low status and coarse levels, not a measured charge
  percentage. It avoids needing to distinguish reporting styles per device.
  On 2026-10-22 the user settled on unknown for both code `6` (DC) and code `9`.
  This supersedes the earlier proposal to hide the battery sensor for DC.
  Existing battery entities are retained when these codes arrive. Missing/invalid
  values also provide no battery percentage.
- Implemented the battery percentage sensor on 2026-10-22 at the user's request.
  The existing registration mapping parses `batt`, giving direct ownership across
  all valid registered Ecowitt sensors without a model filter. Battery uses HA's
  battery device class, percent unit, measurement state class and diagnostic
  category; parsed percentages are included in downloadable diagnostics.
- Discovery follows the existing valid-reading rule: codes `0`–`5` discover the
  entity; a first report of `6`/`9` alone does not. Once discovered, the entity is
  retained through DC/unknown codes, missing fields/registrations and reload.
  Failed gateway polls make it unavailable; no separate battery-age inference is
  introduced. Voltage remains deferred.
- All 285 tests, Ruff, strict mypy and metadata checks pass. Coverage includes the
  complete conversion table, invalid codes, unknown-before-discovery, low battery,
  ownership independent of model, diagnostics, retention and failed-poll recovery.
  A disposable HA instance verified 12 battery entities against the real gateway;
  refresh and reload passed. Restarted persistent development HA at the user's
  request and verified readiness with no integration errors in startup logs.
  Timestamped frontend evidence and extracted icons are kept in local notes.
  Reviewed battery mapping, diagnostics and lifecycle coverage with no actionable
  findings. All checks also pass after revising code `1` to 10%; development HA
  has not been restarted for that revision. The user approved committing and
  pushing the battery changes on 2026-10-22.

## RSSI diagnostics — 2026-10-22

- Registration `rssi` supplies an RSSI diagnostic entity in dBm through the
  existing registration mapping, independently of Ecowitt sensor model. Verified
  on GW2000A V3.3.2; all 13 valid registrations include the field, with `--` for
  the offline soil-moisture Ecowitt sensor.
- Discover the entity on its first valid numeric reading. Missing or invalid
  readings then report unknown; retain the entity through disappearance/reload.
  RSSI is the gateway's last reported value and can remain cached after reception
  stops. It does not establish connectivity or freshness.
- All 300 tests, Ruff, strict mypy and metadata checks pass. A disposable HA
  instance verified 12 RSSI entities, 67 total entities and 14 devices against
  the real gateway, including refresh and stable identities after reload.
  Persistent development HA has not been restarted for this change.

## Wind and rain capture — 2026-10-22

- After the user restored their weather station, captured GW2000A V3.3.2 live
  data, registration pages, channel metadata, rain totals/settings, calibration
  and units. A previously unreceived `wh85` registration (type 49, Wind & Rain)
  now has a valid radio ID. All other slot/radio-ID pairs match the previous capture.
- Compared with the previous capture, `common_list` gains wind speed (`0x0B`),
  gust (`0x0C`), day maximum wind (`0x19`), direction (`0x0A`) and ten-minute
  average direction (`0x6D`). The gateway frontend confirms these labels.
- A `piezoRain` group now supplies rate and totals. Its yearly-total record also
  carries `battery`, `voltage`, `ws85cap_volt` and `ws85_ver`. These provide useful
  source-specific context for the pending ownership investigation; this capture
  alone does not establish selection rules when multiple candidates coexist.
- No wind/rain entity mappings added. Raw responses and exact readings remain in
  the timestamped local capture linked from the infrastructure notes.

## Frontend source-selection inspection — 2026-10-22

- The user confirmed WH26 ownership in their setup; the unresolved question is
  attribution in other combinations of Ecowitt sensors. Investigate available
  evidence without contacting Ecowitt.
- Inspected the GW2000A V3.3.2 frontend served by the gateway: device settings,
  calibration, rain totals, registrations, live data, units, weather services,
  network settings and shared JavaScript. Saved timestamped assets and read-only
  API responses locally; no gateway settings were changed.
- `liveData.html` renders `common_list` from `get_livedata_info` directly, using
  measurement IDs for labels. It does not join registrations or resolve owners.
  Conventional `rain` and `piezoRain` are displayed separately. The frontend
  supplies no temperature/wind source-priority algorithm.
- `get_rain_totals` exposes `rainFallPriority` and a `list` defining `0` as
  No rain gauge, `1` as Traditional rain gauge, and `2` as Piezoelectric rain
  gauge. This is a category-level setting, not a radio ID or registration type.
  It does not establish selection between multiple Ecowitt sensors within a
  category, failover behaviour, or physical ownership of accumulated totals.
- `get_device_info.sensorType` controls a checkbox labelled for WH24 transmitters
  (`0` checked, `1` unchecked). It is not a per-measurement active-source field.
  Calibration exposes common offsets/gains and channel-page availability, with
  no ownership link. Captured registrations have no explicit selected-source flag.
- Result: no generic physical-owner resolver established by this inspection.
  Evidence and file/line references are in the local infrastructure notes.

## Shared gateway observations — 2026-10-22

- Added declarative gateway mappings for outdoor temperature/humidity, dew point,
  Feels Like, Apparent temperature, VPD, wind speed/gust/day maximum and current/
  ten-minute-average direction. Conventional `rain` and `piezoRain` each map rate,
  event, hour, 24-hour, day, week, month and year readings to separate gateway keys.
  Literal IDs preserve the distinction between `3` (Feels Like) and `0x03`
  (dew point). Duplicate item IDs are rejected within each source group.
- Mappings use the served GW2000A V3.3.2 frontend and saved captures as
  references for labels and API groups. Hourly rain uses `0x7D`; the frontend
  also contains an older `0x0F` label, which is not mapped here.
- Gateway observations use valid-reading discovery and registry restoration;
  missing readings become unknown and failed polls unavailable. Source switches
  and disappeared registrations do not change observation IDs or device ownership.
  The existing four internal entities retain their setup behaviour.
- Canonical units are Celsius, percent, kPa, m/s, degrees, mm and mm/h. Rainfall
  counters follow installed HA Ecowitt conventions: event/calendar counters are
  total_increasing; rolling hour/24-hour values have no state class. Wind direction
  uses measurement_angle. Unsupported unit strings supply no reading.
- New observations are numeric and included in gateway diagnostics. Parsing stays
  outside the HTTP client; gateway mappings reuse the existing field-reading
  declarations and parsers. No source-priority algorithm is needed.
- Wind conversion covers m/s, km/h, mph and knots. The served unit-settings page
  also offers BFT (Beaufort); that setting is currently unsupported, so wind
  speed/gust/maximum readings in BFT will be absent or unknown.
- Validation: all 363 tests, Ruff, strict mypy and metadata/translation checks
  pass. A disposable real-gateway HA run discovered 18 new gateway observations
  (85 entities across 14 devices overall), with successful refresh and stable
  entity identities after reload. Reports are referenced in local infrastructure
  notes. Subsequently restarted development HA at the user's request and
  confirmed its HTTP readiness check passes.

## Integration structure reference

- Current module responsibilities after the 2026-10-20 structure review:
  - `models.py`: data structures and their derived properties.
  - `parsers.py`: API value validation, unit conversion, registration parsing and
    internal gateway reading extraction.
  - `mapping_engine.py`: typed rule definitions, ownership joins and evaluation.
  - `mappings.py`: declarations of supported API reading mappings.
  - `api.py`: HTTP requests, response validation, pagination and gateway identity
    decoding.
  - `gateway.py`: supported-model validation and snapshot orchestration shared by
    config flow, setup and polling.
  - `coordinator.py`: HA polling, refresh state and error translation.
  - `devices.py`: gateway/Ecowitt sensor device metadata and registration.
  - `capabilities.py`: gateway and discovered HA sensor descriptions.
  - `entity.py` and `sensor.py`: HA entity behaviour, discovery and restoration.
  - `data.py`: HA config-entry data and runtime state.
- The structure refactor preserves parsing, attribution, discovery, identifiers
  and availability. Gateway readings retain their dedicated parser and four
  unconditional entities; changing their ownership/discovery is separate work.
  The client decodes gateway identity, while the shared gateway layer enforces
  the existing GW2000A support restriction.
- Validation: all 243 tests, Ruff, formatting, strict mypy and metadata checks
  pass. Structural comparison also confirms that the 23 moved parser, mapping
  and snapshot definitions retain their implementations. Added coverage verifies
  support-policy enforcement through both configuration and stored-entry setup.
  The user approved committing and pushing the reviewed refactor on 2026-10-20.
  Persistent development HA has not been restarted for this refactor.
- Reviewed the structure refactor: no actionable findings. Checked dependency
  direction, moved imports, config-flow/setup support checks, error handling,
  device metadata and packaging inclusion of the new modules. Structural
  comparison confirms unchanged gateway entity descriptions and mapping
  declarations. The 243-test run above covers the reviewed code; no additional
  live deployment was performed.
- Mapping readability pass: `apply_reading_mappings` now resolves source records,
  parses fields, then merges observations. `_resolve_records` handles source/owner
  selection and `_merge_observations` handles conflicts and naming. Field
  declarations expose `parse(record)`; a private `_Observation` dataclass replaces
  positional reading/name tuples. Ownership and conflict rules are unchanged.
  All 243 tests and project checks pass, and 2,000 deterministic synthetic cases
  matched the committed engine's results. The user approved committing and
  pushing this readability pass on 2026-10-20.
- Second mapping readability pass (2026-10-21): put the public evaluation flow
  before its helpers, group observations by registration slot and merge one
  Ecowitt sensor at a time. Observation fields and channel-join variables now
  state their roles explicitly; singleton name selection uses a simple list.
  All 243 tests and project checks pass. Another 2,000 deterministic comparisons
  matched the committed engine, including multiple Ecowitt sensors, conflicts,
  naming and ambiguous ownership. The user approved committing and pushing
  these changes on 2026-10-21.
- Reviewed the second readability pass: no actionable findings. Observation
  grouping keeps conflicts within each registration slot; names come only from
  accepted readings, and empty observations clear current readings while retaining
  identity and metadata. Channel-join ambiguity checks remain equivalent. The
  existing 243-test run and 2,000 comparisons cover the reviewed code; no live
  HA restart was performed.

- User selected [HA-BoardOil](https://github.com/andrew-codechimp/HA-BoardOil)
  as the structural starting point on 2026-10-17. Reviewed upstream commit
  `89e78db6a25f807e280a58394c9c61157b85f770`. The initial integration now adapts
  that structure and retains the MIT attribution in `LICENSE`.
- Follow its separation of `api.py` (async HTTP client), `models.py` (data models),
  `coordinator.py` (shared polling), `data.py` (typed config-entry runtime data),
  `config_flow.py` (UI setup), `entity.py` (shared entity/device metadata), and
  platform modules such as `sensor.py`. It also provides diagnostics, translations,
  HACS packaging, tests, and lint/validation/release workflows to use as references.
- Adapt this structure to devices representing gateways and Ecowitt sensors, our MAC/type
  identifiers, and read-only scope. BoardOil authentication, service actions,
  card events, and board-specific models are not requirements for this project.
- Upstream sensor synchronization removes entities/devices absent from refreshed
  data. Do not carry over this automatic removal behaviour: Ecowitt device
  removal is a manual user action. Availability can change without deleting
  devices or entities.
- Upstream is MIT licensed, copyright 2026 Andrew Jackson. Preserve the required
  license and copyright notice when reusing code. Its HA/Python version pins are
  reference-project choices; use the latest stable HA baseline for this project
  and determine the corresponding Python version during setup.
- Ruff and mypy settings follow reference commit
  `4bf413ab70218767e60782793d351c3fb9d898da`. Keep our Python 3.14 target and
  component path; CLI scripts allow console output. `scripts/check` runs both.
  Mypy now uses strict mode for the integration and no blanket missing-import
  exemption. Keep untrusted values as `object` until validated; use concrete
  structures for data we control. Explicit `Any` is disallowed in the integration;
  HA form hooks also accept object-valued dictionaries.

## API references

- [Ecowitt official documentation index](https://www.ecowitt.com/api/quickstart/product?id=281):
  lists the local HTTP and TCP specifications and the TCP maintenance notice.
  This index is for WN1980; it does not establish the user's gateway model.
- [HTTP API interface protocol v1.0.6](https://oss.ecowitt.net/uploads/20260114/HTTP%20API%20interface%20Protocol%20%28Generic%29-%28V1.0.6-2026-1-14%29%20.pdf):
  the current HTTP specification linked by that index and the
  [GW2000 index](https://www.ecowitt.com/api/quickstart/product?id=178)
  when checked on 2026-10-20.
- A documented read endpoint is `GET http://<gateway-ip>/get_livedata_info`.
  See the local infrastructure notes for the gateway address and connectivity findings.

## Ecowitt sensor identity and reading mapping

- The HTTP specification documents `GET /get_sensors_info?page=1` and `page=2`.
  Ecowitt sensor records include `type`, hexadecimal `id`, a generic name, `img`,
  battery and signal fields. Use `type` for identity without assuming capabilities.
  Prefer links supplied by API responses for ownership. Following the 2026-10-20
  discussion, documented type mappings may establish ownership where explicit
  links are absent; verify them for supported gateway. Do not use array
  positions or display-name matching.
- Pagination varies across captured responses: captures contain either two pages
  of 32 slots or four pages of 16 slots. The newer version response includes
  `sensorid_page: "4"`. Discover the page count rather than hard-coding two;
  pagination changes alone do not mean devices have disappeared.
- `GET /get_cli_multiCh` provides temperature/humidity channel IDs and configured
  names. Its `temp` and `humi` fields are calibration offsets, not live readings.
- `GET /get_cli_soilad` links soil channel numbers (`ch`) to radio IDs (`id`)
  and supplies names and calibration fields. Use this link for attribution;
  `soilVal` is not a substitute for a live `ch_soil[].humidity` reading.
- Current identity decision (2026-10-17): identify the gateway by its normalized
  MAC address from `GET /get_network_info`. Its normalized base URL is connection
  data only. This supersedes the earlier base-URL identity decision.
- Devices representing Ecowitt sensors use the gateway MAC plus API `type`.
  The `type` decision remains unchanged. Normalize equivalent bare-address, HTTP,
  and trailing-slash connection-address forms consistently.
- Device identities for Ecowitt sensors are scoped to their gateway: the same `type` on two gateways
  produces separate devices. Do not merge Ecowitt sensors across gateways by radio ID,
  even if both gateways receive the same transmitter.
- Accept `type` as sufficiently stable for now; this identifies an Ecowitt sensor slot.
  All 64 slot types retained their meanings across the captured responses.
  Stability after deliberate removal or reassignment remains unverified, and the
  identity scheme may be revised later. A replacement using the same slot would
  retain its identity under this scheme.
- Radio IDs remain useful metadata for correlating responses, rather than part
  of the chosen device identifier. Normalize hexadecimal IDs across endpoints:
  some include `0x` and others omit it. Cross-family radio ID uniqueness remains
  an assumption, not a verified guarantee. Skip ambiguous radio-ID joins.
- The specification uses `FFFFFFFF` for an Ecowitt sensor not yet received and `FFFFFFFE`
  for a disabled Ecowitt sensor. Neither identifies a physical Ecowitt sensor.
- Keep actual device IDs, channel mappings, and response snapshots in `.local/`.
- Name JSON response snapshots with their capture timestamp in UTC:
  `<name>-YYYYMMDDTHHMMSSZ.json`. Retain previous snapshots.
- When presenting an inventory, list each gateway and physical Ecowitt sensor once with all of its
  readings together, including battery and signal information. Treat a standalone
  Ecowitt soil temperature sensor as a device alongside devices for other Ecowitt sensors.

### Declarative mapping feasibility review — 2026-10-20

Initial assessment, followed by the design refinement below: declarative reading
mappings remain suitable, but documentation does not establish complete
physical-device attribution across the current range.

The HTTP specification provides channel/radio-ID metadata for soil,
temperature/humidity, PM2.5 and distance groups. Equivalent joins are not
documented for standalone temperature, leaf wetness or leak groups. A working
standalone-temperature join was subsequently captured through `get_cli_wh34`
(see the 2026-10-21 findings above). Singleton
and aggregated groups need further ownership evidence. The changelog mentions
`ch_ec`, BGT and WBGT without complete response schemas.

The [current GW2001 compatibility and priority table](https://shop.ecowitt.com/en-gb/products/wittboy-gw2001)
confirms that source selection differs by measurement. WN32P can supersede the
gateway's internal temperature, humidity and pressure. Review our current
gateway attribution before supporting that combination. A registered inventory
alone should not be assumed to identify the active source.

The [WN38 manual](https://oss.ecowitt.net/uploads/20260810/WN38Manual.pdf)
confirms WBGT needs other Ecowitt outdoor temperature/humidity readings.
Ownership of such derived readings remains an open design question.

Recommendation: keep device discovery, ownership resolution and capability
interpretation separate. Allow multiple ownership strategies behind typed rule
declarations; retain shared parsers and entity definitions. The initial blanket
restriction on type mappings was relaxed in the subsequent discussion below;
name/image-based ownership guesses remain excluded.
New combinations work automatically only when their formats and ownership links
are already understood. WH52 temperature/EC mapping still needs captures.
These findings do not change implementation scope or establish hardware support.

### Proposed declarative mapping design — 2026-10-20

The user asked to preserve the capability approach while accommodating documented
type-based ownership and weather-source selection. This relaxes the earlier
blanket ban on interpreting type for ownership, not the prohibition on deriving
capabilities from type. The soil-only implementation is recorded below; the
additional ownership strategies remain proposals.

Use frozen, typed Python declarations with three independent parts:

- Source: endpoint and group, optionally selecting records by a literal item ID.
- Owner: a tagged union of explicit channel/radio-ID joins, registered type,
  explicit channel-to-type mapping, or a named source-selection resolver.
- Readings: source field/selector, typed parser and stable capability key. Shared
  capability definitions provide HA platform, units, class and naming metadata.

Concrete examples for a future implementation:

| Group | Owner rule | Reading rule |
| --- | --- | --- |
| `ch_soil` | `channel` joins `/get_cli_soilad.ch`, then radio ID joins registration | `humidity` becomes `soil_moisture` through the percentage parser |
| `lightning` | Registered type `26` (HTTP specification section 7; verify on the supported gateway) | `count` becomes `lightning_count`; `distance` becomes `lightning_distance`, each when valid |
| `rain` | Named conventional-rain source resolver | Item `0x0E`, field `val`, becomes `rain_rate` through a rate/unit parser |

Each owner result must resolve to exactly one valid registration in that gateway,
or explicitly remain unresolved/ambiguous. Rules never invent a physical identity.
Rain selection is a resolver contract, not an implemented algorithm: configured
priority or registration presence alone is not proof of the current source.
Verify selection/failover behaviour before enabling its mapping. Do not copy an
aggregate reading to every candidate. Historical rain totals need separate
ownership consideration because they may span source changes.

The evaluator processes one poll's responses, resolves owners, parses recognised
readings, and merges by device identity and capability key. Conflicting mappings
must not silently overwrite one another. A missing join must not trigger an
implicit type fallback; each mapping names its ownership strategy.

Keep registration-driven devices and HA registry restoration outside this
evaluator. Valid observed readings discover entities;
missing/invalid/ambiguous readings supply no current value and never remove an
entity. Several mappings may add different capabilities to the same identity.
Literal item IDs retain their API representation, independently of radio-ID
normalization. Typed parse results must accommodate future nonnumeric readings.

Implement the first reusable join with existing soil behaviour, then validate a
documented slot mapping. Further resolvers can follow verified examples; avoid
building an expression language or implementing speculative rain attribution.

### Mapping refactor implementation — 2026-10-20

- Replaced the dedicated soil-reading parser with frozen typed declarations in
  `mappings.py`: `LiveGroup`, `ChannelRadioJoin`, `FieldReading`, and `MappingRule`.
  This first refactor enabled the existing soil moisture mapping. Registered-type, channel
  slot tables, selected-source ownership and additional reading types are deferred.
- The coordinator fetches each declared metadata endpoint once through the API
  client, then evaluates mappings against live data and the parsed inventory.
  The existing percentage parser and moisture entity definition share a stable
  capability key. Internal gateway parsing retains its existing path; diagnostic
  entities subsequently moved to mappings as recorded below.
- Multiple mappings can contribute distinct capabilities to one identity.
  Multiple producers for the same capability are rejected, even if values agree.
  Conflicting live names fall back to the inventory name. Evaluation creates fresh
  current readings without mutating input data or retaining old values.
- Existing identifiers, registration-driven device creation, the temporary
  `wh51` creation filter, restoration and availability behaviour are preserved.
  No new production entities or endpoints were added.
- All 176 existing tests pass. Fourteen additional cases cover configurable
  fields, merging, conflicts, missing ownership, stale-value exclusion, and
  fetching shared endpoint dependencies once. `scripts/check` passes all 190
  tests, Ruff, formatting, strict mypy, and metadata/translation validation.
  This validation preceded the client/orchestration separation below.
- Reviewed the refactor against its soil-only scope: no actionable findings.
  Checked ownership ambiguity, mapping composition, endpoint dependencies,
  input mutation, identifiers and HA restoration/availability coverage.
  A temporary differential probe matched the committed soil parser across 2,000
  deterministic synthetic cases using fresh registration inventories. All 190
  tests and project checks pass again. No live-gateway deployment was performed.

### Client and orchestration separation — 2026-10-20

- At the user's request, keep HTTP requests, response-shape validation and
  registration pagination in `EcowittApiClient`. Its public reading-related
  methods return API records: `async_get_live_data`, `async_get_registrations`
  and `async_get_channel_metadata`. Gateway identification remains in the client.
- `async_read_gateway` in `coordinator.py` selects metadata dependencies,
  discovers identities, applies mappings and assembles `GatewayReadings`.
  Polling and config-flow validation share this function. Gateway errors are
  translated at those callers into HA polling failures or form errors.
- Removed the combined client `async_get_readings` method. The client has no
  dependency on mapping declarations or capability interpretation. Request order,
  required endpoints, polling interval, initial validation and HA entity behaviour
  remain unchanged.
- Lifecycle test mocks now supply API-shaped data, exercising the real parsers
  rather than injecting already interpreted readings. Added client tests for
  preserving registration and metadata records, plus setup failures at each
  required request. `scripts/check` passes all 195 tests, Ruff, formatting,
  strict mypy and metadata validation. The user approved committing both
  refactors on 2026-10-20. Development HA has not been restarted.

### Registration diagnostic mappings — 2026-10-20

- Added `RegistrationRecords` and `OwnRegistration` to the mapper. Valid
  registrations supply Gateway name from `name` and Radio ID from `id`.
  Existing trimming, hexadecimal normalization and identity validation apply.
  These capabilities are discovered independently of live measurements.
- Added typed `TextReading` values alongside numeric `Reading` values.
  `capabilities.py` holds the HA sensor descriptions for moisture and both
  diagnostics. A shared `EcowittSensor` class discovers and restores all three
  through their capability keys; the dedicated diagnostic classes were removed.
- Entity/device identifiers, diagnostic categories, offline discovery, the
  temporary creation filter, and retained entities remain unchanged. Missing
  values become unknown; poll failures make entities unavailable.
- Diagnostic downloads require explicit opt-in on each capability description.
  Only soil moisture opts in; names and radio IDs remain excluded from downloads.
- `scripts/check` passes all 210 tests, Ruff, formatting, strict mypy and metadata
  checks. Coverage includes mixed text/numeric mapping, invalid names, duplicate
  registrations, registration-only requests, fresh-runtime restoration of enabled
  and disabled diagnostics, and download exclusions. The user approved committing
  the refactor on 2026-10-20. Development HA has not been restarted.

## Project and task tracking

- Working directory: `/home/luke/projects/ha/ha-ecowitt-atomic`.
- At initial inspection, the directory contained `.codex/config.toml` and no
  application source files; it was not yet a Git repository.
- The bootstrap added application source and initialized a local Git repository
  on branch `main`. The public repository is
  [dozigden/ha-ecowitt-atomic](https://github.com/dozigden/ha-ecowitt-atomic),
  created on 2026-10-18, with `origin` pointing to it. The initial snapshot is
  development code; supported releases and HACS publication remain deferred.
- Project MCP configuration: `.codex/config.toml`.
- BoardOil MCP server name: `boardoil_ecowittflux`.
- BoardOil MCP endpoint: `https://boardoil.brickden.net/mcp`.
- OAuth login completed and authenticated MCP calls succeeded on 2026-10-15.
- Authenticated BoardOil account: **Flux Dev Agent** (`fluxdevagent`).
- Accessible board: **Ecowitt Atomic**, board ID **16**, with **Owner** access
  confirmed on 2026-10-19 after the user's permission update.
- Board layout updated at the user's request on 2026-10-21: removed the empty
  **Ideas** column and renamed **Pending** to **Todo**. Column order is **Todo**,
  **In Progress**, **Done**.
- Initial bootstrap story: **#1 — Bootstrap the HA integration with
  gateway-internal readings**, created in **Todo** on 2026-10-17. Covers the
  scaffold, latest stable HA baseline, multiple gateways, fixed 30-second polling,
  internal readings, simple availability, and development validation.
  Moved to **Done** after bootstrap validation on 2026-10-17; HACS publication
  prerequisites and the persistent development UI onboarding are documented.
- Experiment story: **#3 — Test Ecowitt sensor identity through signal loss,
  restart and return**, created in **In Progress** on 2026-10-18. Records the
  battery-removal timeline, retained registration, cached fields, timing caveats,
  the completed restart, and pending return and multi-day absence checks. The
  current plan leaves the target continuously offline for a few days after the
  restart, before reinserting batteries; the story remains In Progress.
- Discovery story: **#5 — Add soil moisture discovery and entities**, created in
  **Todo** on 2026-10-19 and narrowed at the user's request to soil moisture only.
  Covers discovery from observed moisture readings, one device per Ecowitt sensor,
  and reconstruction of previously discovered moisture entities from HA's
  registries after reload/restart, without a separate capability store or automatic
  pruning. Other reading entities, Ecowitt sensor families, and a general capability
  framework are follow-up work; retain the agreed discovery approach in this slice.
  The first implementation and review incorrectly accepted a static type/channel
  catalogue. Rewritten on 2026-10-19 to use API-provided channel/radio-ID links
  and accept unfamiliar registration types. The earlier review is superseded;
  review of the final implementation completed with no actionable findings.
  The user approved committing and pushing it on 2026-10-19. Stories move to
  **Done** only after review and commit are complete.
- Roadmap stories created in **Todo** on 2026-10-19, ordered after soil moisture:
  **#6 — Review integration testing and local dev deployment**,
  **#7 — Add standalone temperature readings**,
  **#8 — Add channel temperature readings**,
  **#9 — Add channel humidity readings**,
  **#10 — Investigate battery and reception fields**,
  **#11 — Add battery entities**,
  **#12 — Handle individual Ecowitt sensor connectivity**,
  **#13 — Investigate weather-station reading ownership**, and
  **#14 — Verify slot reassignment behaviour**. Later stories are deliberately
  brief; refine their scope when evidence and implementation experience are
  available. Weather-station investigation depends on the user's hardware
  becoming available. HACS is excluded from this roadmap.
- Story **#2 — Add MyPy type checking to project** implemented on 2026-10-18:
  strict checking of the integration, validated object-valued API/config inputs,
  concrete config and diagnostics structures, and no blanket missing-import
  exemption. Explicit `Any` is disallowed, including HA form-hook signatures.
  All checks and 103 tests passed before the upstream merge; story moved to Done.
- If BoardOil tools are unavailable, check authentication as well as configuration:
  the server was configured and enabled but initially required OAuth login.

## Initial implementation and validation

- Integration domain: `ecowitt_atomic`. UI setup creates one config entry and
  gateway device per normalized hardware MAC, with four sensor entities: indoor
  temperature, indoor humidity, absolute pressure, and relative pressure.
- Development baseline: **Home Assistant 2026.10.2**, **Python 3.14.5**. The HA
  release was checked on 2026-10-17 against [official package metadata](https://pypi.org/project/homeassistant/2026.10.2/)
  and [release notes](https://www.home-assistant.io/blog/2026/10/07/release-202610/).
  The Python pin was updated at the user's request on 2026-10-18. Dependencies
  are locked in `uv.lock`.
- The first pass accepts only the verified gateway model. Model details and the
  real-gateway validation report are in the local infrastructure notes. It reads
  `get_version` and `get_network_info` during setup and polls `get_livedata_info`; it exposes only the
  indoor `wh25` group. This pass is intended for built-in indoor readings;
  active external indoor sources remain outside verified support.
- The initial config-entry schema is version 1, with normalized lowercase colon MAC
  identifiers, and HA's MAC connection metadata. The base URL remains configurable
  through reconfiguration after checking the hardware MAC. Missing/invalid MACs
  and different hardware at the stored address are rejected rather than falling
  back to address-based identity.
- The code expects the current MAC-based entry format. Earlier development entry
  formats have no migration path; recreate development state when needed.
- Polling is fixed at 30 seconds. Entities inherit `CoordinatorEntity`
  availability: failed polls make them unavailable; successful polls restore
  availability and missing/invalid readings become unknown. Startup of an
  existing entry with empty readings creates unknown entities; initial UI setup
  still requires at least one valid reading to validate the connection.
  Devices/entities are never automatically pruned. Manual device removal is
  supported; reload can rediscover a removed gateway device.
- Canonical units: Celsius, percent, and hPa. Parsing supports gateway temperature
  in Fahrenheit and pressure in hPa/mb, inHg, or mmHg. It rejects placeholders,
  malformed values, non-finite numbers, and unknown units instead of using zero.
- Diagnostics use an allowlist of gateway metadata, polling status, and parsed
  readings; no gateway URL, raw payload, config-entry data, or credentials.
  After unload or failed setup, diagnostics return the config-entry state and
  empty readings without requiring runtime data.
- Validation covers MAC normalization, address aliases/reconfiguration,
  hardware mismatch handling, coordinator availability, manual removal/rediscovery, and
  independent gateway reload/failure behaviour. Ruff and packaging checks pass. Official
  hassfest container reports one valid integration and zero invalid integrations.
- A real-gateway check through HA's config flow and registries created one device
  with four available sensor entities and completed a subsequent refresh. The
  user subsequently onboarded the persistent development instance and added the
  gateway. Its URL-based entry was then migrated to MAC identity in place, with
  the device ID, all four entity IDs, and registry preferences preserved; all four
  readings remained available. See local notes for private verification reports.
- `scripts/setup` prepares dependencies and a ready-to-login development HA
  instance. `scripts/develop` starts it, and `scripts/reset` recreates its
  disposable configuration. Initial owner/admin creation and onboarding use
  HA's own helpers in the pinned image. Existing accounts survive rerunning
  setup/develop; reset recreates them using the same private credential store.
- Credential values stay in a Git-ignored credential file, separate from notes.
  They are passed to the one-shot setup container over stdin, not command-line
  arguments or logs. See local infrastructure notes for the credential-store
  reference and `scripts/dev.py --help` for commands.
- Helper validation: initial setup, repeated develop, and reset were exercised
  against a separate fresh HA Container instance with real HTTP logins. Existing
  account identity survived rerun; reset produced a new owner with the same
  configured credentials. A subsequent user-requested rebuild of the main
  development instance also passed actual HTTP login and onboarding checks.
  All 86 tests and local lint/packaging consistency checks pass.
- `scripts/check`, `scripts/package.py`, and `scripts/smoke.py` provide checks,
  zip packaging, and optional real-gateway verification.

### Soil moisture implementation

- Each 30-second poll reads live data, version/page count, all registration
  pages and `/get_cli_soilad`. Responses without `sensorid_page` use the
  specification's two pages; malformed page counts or failed metadata requests
  fail the poll.
- Registration parsing retains valid identities independently of reading support.
  Soil moisture attribution joins `ch_soil[].channel` to `/get_cli_soilad[].ch`,
  then its radio `id` to the registered Ecowitt sensor. No type/channel catalogue,
  retail-model filter or capability inference from metadata is used in attribution.
- Devices are explicitly registered from valid registration identities, independently
  of readings and entities. The temporary `img: "wh51"` filter limits creation
  during development; an offline registration still creates a device without
  assuming any measurement entities. Device metadata is shared with entity setup and existing names retained.
- Only valid live `ch_soil[].humidity` percentages discover moisture entities;
  zero is valid. Calibration `soilVal` never supplies a live reading. Missing or
  ambiguous channel/radio links leave readings unattributed.
- Ecowitt sensor device identifiers are `<gateway_mac>::<type>` and moisture
  entity unique IDs are `<gateway_mac>::<type>::soil_moisture`. Devices link to
  the gateway through HA's `via_device_id`. Initial names use the live channel
  name or registration name; existing device names survive missing metadata.
- A diagnostic sensor named **Gateway name** exposes the registration-page `name`
  separately from the configured live-data name and HA's user name. It is created
  when a nonempty registration name is observed, including for offline Ecowitt
  sensors. Its unique ID is `<gateway_mac>::<type>::gateway_name`. Missing metadata
  yields unknown; failed polls yield unavailable. Registration metadata supplies
  diagnostic capabilities; measurement capabilities require observed readings.
- At the user's request, the device model is the registration-page name with a
  trailing `CH<number>` removed, for example `Soil moisture CH5` becomes
  `Soil moisture`. This is a gateway-provided descriptive model, not an inferred
  retail model number. Gateway name retains the full registration string. Missing
  names do not erase previously recorded model metadata.
- A diagnostic sensor named **Radio ID** exposes the registration's normalized
  hexadecimal radio ID, including for offline Ecowitt sensors. Its unique ID is
  `<gateway_mac>::<type>::radio_id`; a changed radio ID updates the value without
  changing device identity. Invalid/sentinel IDs do not create devices or entities.
  A retained entity reports unknown when its valid registration disappears.
  Downloadable diagnostics continue to exclude radio IDs.
- Setup restores moisture, Gateway name and Radio ID entities from this config
  entry's HA entity registry
  entries without a known-type filter. New readings can discover further
  moisture entities on later polls.
  There is no separate persisted capability catalogue and no automatic pruning.
- Successful polls with absent/invalid moisture readings yield unknown values;
  failed polls make the gateway's entities unavailable. No individual radio
  timeout or inferred battery/signal connectivity is introduced.
- Diagnostics include attributed soil readings by slot and exclude configured
  names, radio IDs, MAC addresses and connection addresses. The smoke script now
  checks discovered devices/entities, gateway links, refresh and reload.
- Validation: 176 tests, strict mypy, Ruff and metadata checks pass. Tests use
  unfamiliar registration types and synthetic HTTP responses with HA's real
  registries/lifecycle, including changed channel links and ambiguous radio IDs.
  A disposable HA instance passed the real-gateway smoke check. A second
  verification stopped HA,
  loaded its saved registries into a fresh HA runtime with an intentionally empty
  reading/registration snapshot, and retained device/entity IDs and device names
  with unknown values. Private reports are linked in local infrastructure notes.

## Remaining work

- After soil moisture, review testing, particularly integration testing, and
  establish the local development deployment workflow before adding further
  reading support (user priority, 2026-10-19). Build on the existing setup,
  develop, reset and smoke scripts. Review coverage of discovery, polling,
  reload/restart and registry retention through HA, and make deploying and
  verifying local changes repeatable. This is the next planned story, #6.
- HACS work is not part of the current board roadmap; revisit distribution
  planning when the user wants to pursue it.
- Battery-removal identity experiment started on 2026-10-18 for one soil moisture
  Ecowitt sensor, with its exact channel initially unknown. Compare every slot's
  `type` and radio `id`, channel mappings, signal status, and live readings through
  battery removal, gateway restart while absent, a multi-day absence, and return.
  Distinguish lost readings from lost registration. Ad hoc snapshots at known
  stages are sufficient; retain their timestamps and physical action times when
  known. Continuous recording is not required, and gaps cannot establish when
  an intermediate change occurred.
  Baseline has all seven soil moisture channels reporting. Raw captures and
  recorder details remain in local infrastructure notes.
  Initial observation: the target's signal field stepped down every three
  minutes, then signal and moisture became `--`, while the channel and registered
  type/radio ID remained present. Cached RSSI and battery fields remained populated
  after loss, so those alone do not establish connectivity. All slot type/radio-ID
  mappings still matched the baseline. A deliberate gateway restart while the
  target remained absent preserved every slot type/radio-ID mapping; the target
  remained registered but was absent from live and soil-channel metadata in the
  first response after restart. The target will remain continuously unpowered for
  a few days before return. Return and extended absence remain pending;
  do not generalize this timeout to other Ecowitt sensor families yet.
- When adding external Ecowitt sensor support, verify the gateway's status
  indicators before deciding individual device availability. Successful gateway
  polling does not establish an Ecowitt sensor's radio connectivity or reading age.
- Before HACS publication, add the issue URL and codeowners,
  add a project icon, and run full HACS validation against that repository. Local
  packaging consistency and hassfest pass; no HACS distribution is claimed yet.
- Further external readings follow the board roadmap after the testing and local
  development deployment review.

## Decision log

- **2026-10-21:** Removed the temporary WH51/WH31 filter from device and entity
  discovery at the user's request. All valid registrations now produce devices
  and mapped diagnostics, including unfamiliar or absent image markers.
  Measurement mappings are unchanged. Tests cover discovery, retention and
  ambiguous ownership with the newly included registrations; all 245 tests,
  Ruff, strict mypy and metadata checks pass. Restarted development HA at the
  user's request and verified readiness and four additional diagnostic entity
  registrations. Reviewed with no actionable findings; the user approved committing
  and pushing the discovery and temperature changes on 2026-10-21.

- **2026-10-15:** Selected Ecowitt's local HTTP/JSON LAN API for this project.
- **2026-10-15:** Started this file at the user's request; maintain it as work proceeds.
- **2026-10-15:** Added `AGENTS.md` and a Git-ignored `.local/INFRASTRUCTURE.md`
  for machine-specific infrastructure records.

- **2026-10-17:** Renamed the project folder to `ha-ecowitt-atomic`.
- **2026-10-17:** Agreed to use normalized gateway base URL + Ecowitt sensor `type` as
  the working device identifier, accepting that it can change later. This
  supersedes the earlier gateway/family/radio-ID recommendation. The gateway
  portion was subsequently changed to MAC address on the same day (see below).
- **2026-10-17:** Agreed that the initial integration will be read-only;
  configuration controls can follow later.
- **2026-10-17:** Selected HA-BoardOil as the reference for integration structure
  and development tooling.
- **2026-10-17:** Agreed to retain discovered devices and entities automatically;
  removal is manual, independent of missing readings or registrations.
- **2026-10-17:** Added multiple-gateway support to the initial scope, with
  separate config entries, polling, and gateway-scoped identities for Ecowitt sensors.

- **2026-10-17:** Moved the integration into the parent `ha/` workspace to leave
  room for a separate Home Assistant development setup alongside it.
- **2026-10-17:** Narrowed the first pass to gateway-internal readings, fixed
  30-second polling, simple timeout-based availability, and the latest stable HA.
  Manually removed devices may return if still reported; defer exclusion support.
- **2026-10-17:** Reserved unqualified device/entity/sensor terminology for HA;
  explicitly qualify Ecowitt sensors in code and communication.

- **2026-10-17:** Adopted the project name **Ecowitt Atomic** and confirmed
  the renamed board retains ID **16**. The MCP server key remains
  `boardoil_ecowittflux`.
- **2026-10-17:** Implemented the gateway-internal first pass, selected a
  90-second reading timeout, validated the real gateway through HA, and prepared
  a separate development instance. Publication remains a separate step.
- **2026-10-17:** Corrected gateway identity to its MAC address at the user's
  request. Base URL is connection data; future Ecowitt sensor device identities
  are gateway MAC + `type`. Added migration for existing URL-based entries and
  hardware-verified connection-address reconfiguration.
- **2026-10-17:** Clarified that HA development state is disposable. Removed the
  migration handler, legacy registry rewriting, and migration-specific tests;
  previous migration work was unnecessary for the current development stage.
  Current MAC identity, duplicate detection, and address reconfiguration remain.
- **2026-10-17:** Added scripted initial HA owner/admin creation and onboarding,
  plus extensionless develop/reset entry points for disposable development state.
- **2026-10-18:** Fixed the P1 integration loading failure by replacing the
  rejected manifest version `0.1.1dev` with `0.1.1.dev0`, matching project metadata
  and the regenerated lockfile. `scripts/check` passes all 86 tests, lint,
  formatting, and metadata checks. Rebuilt the zip and verified its manifest
  version matches the source, project metadata, and lockfile.
- **2026-10-18:** Fixed the P2 diagnostics crash by handling missing runtime data
  and returning setup state with empty readings. HTTP regression tests cover
  unload, connection failure, unsupported hardware, and missing initial readings;
  existing loaded diagnostics retain their detailed allowlisted data. All 90
  tests, lint, formatting, and metadata checks pass. Rebuilt the integration zip.
- **2026-10-18:** Reset the initial config-entry schema version to 1 and aligned
  test fixtures and the setup assertion. The earlier version 2 bump belonged to
  the discarded development migration approach. No migration or compatibility
  path was added; older development entries should be recreated. All 90 tests,
  lint, formatting, and metadata checks pass. Rebuilt the integration zip.
- **2026-10-18:** Adopted HA's
  [availability guidance](https://contributors.home-assistant.io/core/quality-scale/entity-unavailable/)
  for gateway-internal readings. Removed the custom 90-second expiry, timestamp
  wrapper, and accumulation of omitted readings. Entities inherit coordinator
  availability; missing values on successful responses are unknown. Diagnostics
  expose parsed readings and polling status without reading-age fields. Tests
  cover partial/empty responses, initially empty readings, first failed poll,
  recovery, retained registries, and independent gateways. All 91 tests, lint,
  formatting, and metadata checks pass.
- **2026-10-18:** Recreated the dedicated development HA configuration at the
  user's request after the config-entry version correction. Scripted admin
  creation, onboarding, frontend readiness, and actual credential-file login
  were verified; previous gateway entries were cleared. See local infrastructure
  notes for the timestamped verification report.
- **2026-10-18:** Final pre-commit review passed all 91 tests, lint, formatting,
  metadata checks, hassfest (one valid integration), zip inspection, and a fresh
  real-gateway smoke check (one device, four readings, subsequent refresh, MAC
  identity). Git dry-run lists 41 project files and excludes private local data,
  credentials, caches, and generated packages; credential scanning found no
  development password in the candidate files. A workflow-reference blocker was
  identified; the workflows were subsequently removed. The user's trimmed README
  was preserved.
- **2026-10-18:** Removed all three GitHub Actions workflows at the user's request.
  Automated GitHub checks, HACS validation, and release packaging are deferred;
  local validation and packaging scripts remain available.
- **2026-10-18:** Created the public GitHub repository under `dozigden` at the
  user's request and prepared the initial development snapshot for `main`.
  Private local notes, captures, credentials, development environments, and
  generated packages remain Git-ignored.
- **2026-10-18:** Reduced the README and removed or shortened redundant comments
  and docstrings. Python code is unchanged apart from docstrings; all 91 tests
  and local checks pass.
- **2026-10-18:** Adopted BoardOil's Ruff and mypy settings and pinned development
  Python to 3.14.5. Added required short docstrings, aligned naming/imports, and
  switched config forms to HA's Probatio schema after mypy exposed a type mismatch.
  Ruff, formatting, mypy, all 91 tests, and metadata checks pass.
- **2026-10-18:** Reviewed the linting and Python changes; no actionable findings.
  All local checks pass on Python 3.14.5. A temporary HTTP test also verified form
  serialization, invalid-address handling, setup, and reconfiguration with Probatio.
  Existing locked dependency versions are unchanged; only mypy and its dependencies
  were added.
- **2026-10-18:** Merged the upstream diagnostics typing change, retaining direct
  typed access with an attribute-existence guard. HA removes runtime data on
  unload and may never set it after setup failure; unguarded access failed all
  four existing diagnostics HTTP regression cases. All 91 tests, Ruff,
  formatting, mypy, and metadata checks pass after the merge.
- **2026-10-18:** Simplified gateway URL normalization with `yarl.URL`. Validate
  original components before normalization, retaining the HTTP(S)-origin-only
  input rules; delegate host encoding, IPv6 formatting, and default ports to yarl.
- **2026-10-18:** Use HA's `device_registry.format_mac` for MAC formatting,
  retaining validation of supported formats and nonzero unicast addresses.
- **2026-10-18:** Completed story #2's stronger typing scope. Strict mypy rejects
  explicit `Any`; JSON/config inputs remain `object` until validated, while
  config and diagnostics have concrete TypedDict structures. Device metadata
  uses the typed client's normalized address. All 103 tests and local checks
  pass. A temporary negative probe verified five expected typing failures;
  integration source has no explicit `Any`, casts, or type-ignore directives.
- **2026-10-18:** Reviewed the uncommitted stronger-typing changes; no actionable
  findings. Checked HA interface compatibility, JSON/config validation, diagnostics
  after setup failure/unload, and configuration URL updates after reload. All 103
  tests, strict mypy, Ruff, formatting, metadata, and whitespace checks pass.
- **2026-10-18:** Fetched upstream through `8778258` without merging. It adds
  yarl URL normalization, HA MAC formatting, HTTPStatus.OK, and .DS_Store exclusion.
  Commit `d611ac9` also removes the diagnostics runtime-data guard: an isolated
  upstream checkout passes 63 API cases but fails all four diagnostics lifecycle
  cases with HTTP 500. Preserve missing-runtime handling when reconciling it with
  the local stronger-typing changes.
- **2026-10-18:** Checked whether missing runtime data is reachable outside tests.
  HA 2026.10.2's diagnostics download view checks entry existence and registered
  handler, not LOADED state. Our startup can raise ConfigEntryNotReady before
  assigning runtime data; HA also deletes the attribute on successful unload.
  Existing HTTP tests use this real dispatch/lifecycle with mocked gateway calls.
  Missing-runtime handling remains justified for these entry states.
- **2026-10-18:** Integrated upstream through `e6b5053`, including its restored
  diagnostics guard, yarl normalization, HA MAC formatting, and API tests, with
  the local stronger-typing work. Resolved API import and notes conflicts while
  preserving both sets of changes. All 110 tests, strict mypy, Ruff, formatting,
  metadata, and whitespace checks pass.
- **2026-10-18:** Added GitHub CI for main pushes, pull requests, and manual runs.
  The Ubuntu job installs the pinned Python and locked dependencies, then runs
  `scripts/check`. Workflow validation with actionlint and all 110 local tests
  and checks pass. Release automation and HACS validation remain deferred.

- **2026-10-19:** Reset and started the dedicated development HA for user
  testing of the discovery rewrite. Verified admin login and integration setup
  form; previous gateway entries cleared. Local verification report is recorded
  in the infrastructure notes. Review and commit remain pending.

- **2026-10-19:** Checked frontend 20260930.4 used by the development HA:
  the integration page sorts devices by display name, without prioritising
  `via_device_id` gateways. The setup "Name and assign" dialog preserves
  registry order. Device headings show model/manufacturer, not integration name.
  Source: [integration page](https://github.com/home-assistant/frontend/blob/20260930.4/src/panels/config/integrations/ha-config-integration-page.ts#L999)
  and [setup dialog](https://github.com/home-assistant/frontend/blob/20260930.4/src/dialogs/config-flow/dialog-data-entry-flow.ts#L243).

- **2026-10-19:** Corrected device creation to follow registration discovery,
  independently of readings. The earlier absence of the offline device was an
  implementation error. At the user's request, temporarily limit creation to
  soil-moisture registrations (`img: "wh51"`); retain generic inventory parsing
  and API-provided ownership links. Tests cover devices with no entities, later
  readings attaching to the same device, later registration discovery, and
  retention through disappearance, reload and HA registry cleanup.
  Real-gateway smoke and fresh-runtime disk-registry restoration also pass.
  Restarted the development HA and verified that the offline device is present
  without entities. Review and commit remain pending.

- **2026-10-19:** Added the requested Gateway name diagnostic entity from the
  registration-page name, independent of moisture readings and configured names.
  Tests verify diagnostic category, name changes, missing registration/name,
  restoration on reload and recovery. The temporary soil filter still applies.
  Real-gateway and fresh-runtime restart checks pass. Restarted development HA
  and verified the new diagnostics, including the offline device. Review and
  commit remain pending; private reports are linked in local infrastructure notes.

- **2026-10-19:** Added the requested Radio ID diagnostic alongside Gateway name.
  It reads registration metadata, independent of moisture. Tests verify hex
  normalization, offline discovery, missing/invalid/sentinel IDs, restoration,
  and value changes without replacing the device. All 176 tests and checks pass.
  Real-gateway smoke and restarted development HA both verified the new
  diagnostics, including the offline device. Review and commit remain pending.

- **2026-10-19:** Use the registration name without its trailing channel suffix
  for device model metadata, as requested. Keep configured device names and the
  complete Gateway name diagnostic unchanged. All 176 tests and checks pass.
  Restarted development HA and verified the descriptive models in its live
  device registry. Review and commit remain pending.

- **2026-10-19:** Reviewed the full uncommitted implementation after the
  registration-driven device correction, diagnostics and descriptive model changes.
  No actionable findings against the current agreed scope. Checked separation of
  registration discovery, reading ownership, entity discovery and restoration;
  the temporary soil filter; metadata handling; and HA lifecycle cleanup. All
  176 tests, Ruff, strict mypy, metadata and whitespace checks pass. Three
  temporary probes also passed: polling stops on unload, and both diagnostics
  retain their device association when disabled/reloaded/re-enabled. Temporary
  probes removed. Story remains In Progress pending commit.
