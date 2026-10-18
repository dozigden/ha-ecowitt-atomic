# Ecowitt Atomic — project notes

Last updated: 2026-10-18

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

- This is an unreleased development project. Do not build migrations or backward
  compatibility for earlier development states. The dedicated HA development
  instance is disposable and can be recreated for breaking changes. Revisit
  compatibility when preparing a supported release; see `AGENTS.md`.
- GitHub Actions are deferred for now. Run validation locally with `scripts/check`
  and build packages with `scripts/package.py`.
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
- First implementation pass covers only the gateway's own internal readings.
  External Ecowitt sensor support follows later, prioritizing hardware readily available
  for verification rather than attempting every documented family at once.
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

## Integration structure reference

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

## API references

- [Ecowitt official documentation index](https://www.ecowitt.com/api/quickstart/product?id=281):
  lists the local HTTP and TCP specifications and the TCP maintenance notice.
  This index is for WN1980; it does not establish the user's gateway model.
- [HTTP API interface protocol v1.0.6](https://oss.ecowitt.net/uploads/20260114/HTTP%20API%20interface%20Protocol%20%28Generic%29-%28V1.0.6-2026-1-14%29%20.pdf):
  the current HTTP specification linked by that index when checked on 2026-10-15.
- A documented read endpoint is `GET http://<gateway-ip>/get_livedata_info`.
  See the local infrastructure notes for the gateway address and connectivity findings.

## Ecowitt sensor identity and reading mapping

- The HTTP specification documents `GET /get_sensors_info?page=1` and `page=2`.
  Ecowitt sensor records include `type`, hexadecimal `id`, a generic name, `img`,
  battery and signal fields. Use the documented type enum to map Ecowitt sensor families
  and channels; do not depend on array positions or display names.
- Firmware-dependent pagination is confirmed: captures contain either two pages
  of 32 slots or four pages of 16 slots. The newer version response includes
  `sensorid_page: "4"`. Discover the page count rather than hard-coding two;
  pagination changes alone do not mean devices have disappeared.
- `GET /get_cli_multiCh` provides temperature/humidity channel IDs and configured
  names. Its `temp` and `humi` fields are calibration offsets, not live readings.
- `GET /get_cli_soilad` provides soil channel IDs (`ch`), names, readings, and
  calibration fields.
- Current identity decision (2026-10-17): identify the gateway by its normalized
  MAC address from `GET /get_network_info`. Its normalized base URL is connection
  data only. This supersedes the earlier base-URL identity decision.
- Future devices representing Ecowitt sensors use the gateway MAC plus API `type`.
  The `type` decision remains unchanged. Normalize equivalent bare-address, HTTP,
  and trailing-slash connection-address forms consistently.
- Device identities for Ecowitt sensors are scoped to their gateway: the same `type` on two gateways
  produces separate devices. Do not merge Ecowitt sensors across gateways by radio ID,
  even if both gateways receive the same transmitter.
- Accept `type` as sufficiently stable for now; this identifies an Ecowitt sensor slot.
  All 64 slot types retained their meanings across the captured firmware update.
  Stability after deliberate removal or reassignment remains unverified, and the
  identity scheme may be revised later. A replacement using the same slot would
  retain its identity under this scheme.
- Radio IDs remain useful metadata for correlating responses, rather than part
  of the chosen device identifier. Normalize hexadecimal IDs across endpoints:
  some include `0x` and others omit it. Cross-family radio ID uniqueness remains
  an assumption, not a verified guarantee.
- The specification uses `FFFFFFFF` for an Ecowitt sensor not yet received and `FFFFFFFE`
  for a disabled Ecowitt sensor. Neither identifies a physical Ecowitt sensor.
- Keep actual device IDs, channel mappings, and response snapshots in `.local/`.
- Name JSON response snapshots with their capture timestamp in UTC:
  `<name>-YYYYMMDDTHHMMSSZ.json`. Retain previous snapshots.
- When presenting an inventory, list each gateway and physical Ecowitt sensor once with all of its
  readings together, including battery and signal information. Treat a standalone
  Ecowitt soil temperature sensor as a device alongside devices for other Ecowitt sensors.

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
- Accessible board: **Ecowitt Atomic**, board ID **16**, with **Contributor** access.
- Initial bootstrap story: **#1 — Bootstrap the HA integration with
  gateway-internal readings**, created in **Todo** on 2026-10-17. Covers the
  scaffold, latest stable HA baseline, multiple gateways, fixed 30-second polling,
  internal readings, simple availability, and development validation.
  Moved to **Done** after bootstrap validation on 2026-10-17; HACS publication
  prerequisites and the persistent development UI onboarding are documented.
- If BoardOil tools are unavailable, check authentication as well as configuration:
  the server was configured and enabled but initially required OAuth login.

## Initial implementation and validation

- Integration domain: `ecowitt_atomic`. UI setup creates one config entry and
  gateway device per normalized hardware MAC, with four sensor entities: indoor
  temperature, indoor humidity, absolute pressure, and relative pressure.
- Development baseline: **Home Assistant 2026.10.2**, **Python 3.14.2**, verified
  on 2026-10-17 against [official HA package metadata](https://pypi.org/project/homeassistant/2026.10.2/)
  and the [October release notes](https://www.home-assistant.io/blog/2026/10/07/release-202610/).
  Dependencies are locked in `uv.lock`.
- The first pass accepts only the verified gateway model. Model/firmware and the
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
- Diagnostics use an allowlist of model, firmware, polling status, and parsed
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
  reference, and `README.md` for commands.
- Helper validation: initial setup, repeated develop, and reset were exercised
  against a separate fresh HA Container instance with real HTTP logins. Existing
  account identity survived rerun; reset produced a new owner with the same
  configured credentials. A subsequent user-requested rebuild of the main
  development instance also passed actual HTTP login and onboarding checks.
  All 86 tests and local lint/packaging consistency checks pass.
- `scripts/check`, `scripts/package.py`, and `scripts/smoke.py` provide checks,
  zip packaging, and optional real-gateway verification.

## Remaining work

- When adding external Ecowitt sensor support, verify the gateway's status
  indicators before deciding individual device availability. Successful gateway
  polling does not establish an Ecowitt sensor's radio connectivity or reading age.
- Before HACS publication, add the issue URL and codeowners,
  add a project icon, and run full HACS validation against that repository. Local
  packaging consistency and hassfest pass; no HACS distribution is claimed yet.
- External Ecowitt sensor support remains a later implementation pass.

## Decision log

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
