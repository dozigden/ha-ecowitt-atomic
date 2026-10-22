# Ecowitt Atomic

Under development. Do not use.

## Soil moisture data flow

Example values; unrelated response fields are omitted.

```mermaid
flowchart TD
    live["GET /get_livedata_info<br/>ch_soil[]<br/><br/>channel: 1<br/>name: CH1_Soil<br/>humidity: 30%<br/>battery: 2<br/>voltage: 1.30"]
    soil["GET /get_cli_soilad<br/>response array<br/><br/>ch: 1<br/>id: 0xABC123<br/>name: CH1_Soil"]
    registration["GET /get_sensors_info?page=N<br/>response array<br/><br/>type: 14<br/>id: ABC123<br/>name: Soil moisture CH1<br/>img: wh51"]

    live -->|"channel matches ch"| soil
    soil -->|"normalized radio ID matches id"| registration

    device["HA device<br/><br/>Identifier: gateway MAC + type 14<br/>Initial name: CH1_Soil<br/>Model: Soil moisture"]
    moisture["Soil moisture entity<br/>Value: 30%"]
    diagnostics["Diagnostic entities<br/><br/>Gateway name: Soil moisture CH1<br/>Radio ID: ABC123"]

    registration -->|"registered identity creates device"| device
    live -.->|"live name preferred when available"| device
    device -->|"groups entities"| moisture
    device -->|"groups entities"| diagnostics
    live -->|"ch_soil humidity supplies reading"| moisture
    registration -->|"name and id supply metadata"| diagnostics
```

Devices are created from registrations, even without live readings. Moisture
entities are created only after an understood reading is observed. New devices
and entities are temporarily restricted to registrations with `img: wh51`.
Battery and voltage are not exposed yet.
