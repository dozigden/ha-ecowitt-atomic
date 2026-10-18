# Ecowitt Atomic agent instructions

## Project context

- Read `PROJECT_NOTES.md` before starting project work.
- Target Ecowitt's local HTTP/JSON LAN API. The initial reference is the official
  v1.0.6 HTTP specification linked from the project notes.
- Confirm device and firmware support before relying on an endpoint or field.

## Development stage

- This integration is unreleased and in active development. Keep implementation
  focused on the current design; do not add migrations or compatibility paths
  for earlier development versions.
- The project's dedicated HA development instance is disposable. Breaking changes
  can be tested with a fresh instance instead of preserving config entries,
  registry IDs, names, or other development state.
- Revisit upgrade compatibility when preparing a supported release.

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

- BoardOil MCP server: `boardoil_ecowittflux`.
- Project board: **Ecowitt Atomic**, board ID **16**.
- Use authenticated MCP tools for requested board work; do not record credentials
  in this repository.
