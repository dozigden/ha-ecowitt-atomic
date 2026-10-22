# Ecowitt Atomic agent instructions

## Project context

- Read `PROJECT_NOTES.md` before starting project work.
- Target Ecowitt's local HTTP/JSON LAN API. The initial reference is the official
  v1.0.6 HTTP specification linked from the project notes.
- Confirm device support before relying on an endpoint or field.

## Development stage

- This integration is unreleased and in active development. Keep implementation
  focused on the current design; do not add migrations or compatibility paths
  for earlier development versions.
- The project's dedicated HA development instance is disposable. Breaking changes
  can be tested with a fresh instance instead of preserving config entries,
  registry IDs, names, or other development state.
- Revisit upgrade compatibility when preparing a supported release.

## Data model

- Use capability-based discovery: model each Ecowitt sensor as an identity,
  metadata, recognised capabilities, and current typed readings. Identity maps to
  a device, capabilities to entities, and readings to entity values.
- Recognise understood reading formats across Ecowitt sensor records, including
  new combinations of capabilities; do not require a retail-model whitelist.
  Keep discovery/identity separate from reading ownership and meaning.
- Reuse reading parsers and entity definitions across Ecowitt sensor families.
  Express support through verified API mappings; do not build fixed entity bundles
  or a separate implementation for every retail model.
- Preserve API context when interpreting fields and attributing readings. A field
  name or unit alone is insufficient; do not guess ownership of aggregated readings.
- Prefer explicit API links for reading ownership; for soil moisture, join live
  channel to channel metadata to registered radio ID. Where those links are
  absent, documented registration-type mappings may establish ownership once
  verified for the supported gateway. Type does not prescribe capabilities.
  Shared/aggregated weather observations belong to the gateway device, with stable
  entity identities across physical-source changes. Keep conventional and piezo
  rain streams distinct. Do not infer physical ownership from registration
  presence, model, image or name.
- Create devices directly from registered Ecowitt sensor identities, even before
  any recognised readings arrive. Entity discovery must not gate device creation.
- Discover all valid registered Ecowitt sensors, regardless of `img` or model.
  Create entities only for recognised mapped readings and registration diagnostics.
- Missing readings do not remove devices/entities or establish lost capabilities.

## Coding conventions: terminology

- Use unqualified `device`, `entity`, and `sensor` with their Home Assistant
  meanings. A sensor is an HA sensor entity; a device groups HA entities.
- When referring to Ecowitt hardware or its API representation, explicitly say
  **Ecowitt sensor**. Carry that distinction into identifiers, for example
  `ecowitt_sensor`, `ecowitt_sensors`, and `EcowittSensorData`.
- Call measurements supplied by an Ecowitt sensor its **readings**. One Ecowitt
  sensor can map to one HA device with several entities, including several
  sensors. A gateway can also supply its own internal readings.
- Apply this vocabulary in code, comments, docstrings, tests, documentation, and
  discussions. Preserve literal upstream API field names and endpoint names;
  clarify their meaning when describing them.

## Maintain the notes

- Keep `PROJECT_NOTES.md` current with useful decisions, verified findings,
  references, constraints, and unresolved questions as work progresses.
- Keep machine-specific infrastructure details in `.local/INFRASTRUCTURE.md`.
  Read it when working on local connectivity, devices, or development setup.
- Distinguish confirmed facts from assumptions, and revise stale entries.
- Keep infrastructure addresses and configuration out of tracked project notes.
  Link to the local file when needed instead of copying its contents.
- Do not store passwords, tokens, private keys, or OAuth callback URLs in either
  notes file. Record references to the appropriate credential store instead.

## Local files and Git

- `.local/` is excluded by the project `.gitignore`; preserve that exclusion.
- Include the capture date and time in saved JSON response filenames, using UTC
  in `YYYYMMDDTHHMMSSZ` format. Preserve previous snapshots rather than overwriting
  them, and keep the capture timestamp inside the JSON too.
- Never force-add `.local/` or include its contents in commits or external task
  descriptions without an explicit user instruction.
- If local notes are absent on another checkout, recreate the template or ask for
  needed details rather than inventing infrastructure values.

## Task tracking

- Move implementation stories to **Done** only after the changes have been
  reviewed and committed. Passing tests alone does not complete a story; keep it
  **In Progress** while review or commit is pending.
- BoardOil MCP server: `boardoil_ecowittflux`.
- Project board: **Ecowitt Atomic**, board ID **16**.
- Use authenticated MCP tools for requested board work; do not record credentials
  in this repository.
