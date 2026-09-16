# Workshop OS 12 — Printer + Network Migration Seam

This note records the first runtime migration target for Workshop OS 12 without changing the frozen UI13 physical-acceptance candidate.

## Source baseline inspected

The reconstruction chain pins upstream BambuHelper commit:

`8cb1cbbb6d3c175af91989e8ebe1bbdcbe848ac4`

Relevant existing runtime authorities at that source baseline:

- `include/bambu_state.h`
  - `BambuState`
  - `PrinterGcodeState`
  - `printers[slot].state` via the existing settings/runtime model
- `src/bambu_mqtt.h/.cpp`
  - `isPrinterConfigured(slot)`
  - `isAnyPrinterConfigured()`
  - `getActiveConnCount()`
  - `getMqttDiag(slot)`
  - `requestLightCommand(slot, on)`
  - existing MQTT reconnect and pushall recovery behavior
- `src/wifi_manager.h/.cpp`
  - `isWiFiConnected()`
  - `isAPMode()`
  - existing Wi-Fi reconnect/fallback behavior
- `src/main.cpp`
  - existing display/touch path remains ahead of MQTT work so blocking TLS reconnect does not starve UI responsiveness
  - current printer freshness logic already distinguishes connected state from recently observed stale/disconnected state

Workshop OS 12 does not replace those mechanisms in the first migration step. It normalizes their outputs behind a stable platform boundary.

## Target flow

```text
existing Bambu MQTT / Wi-Fi runtime
            |
            v
legacy observation adapters
            |
            v
PrinterService + NetworkService
            |
            v
         StateStore
            |
      +-----+------+----------------+
      |            |                |
      v            v                v
     UI        Health/diag      Media policy
```

The first runtime adapter must be observational before it becomes authoritative for command routing. Existing printer commands and reconnect behavior remain in place until parity tests prove the adapter path.

## Printer normalization

For each configured printer slot, normalize only facts already present in authoritative device runtime state:

- configured
- connection state
- normalized activity state
- telemetry freshness
- progress
- nozzle temperature
- bed temperature
- command-channel readiness
- observation timestamp

Do not map AMS tray color/material telemetry into Filament Inventory spool identity or canonical placement. Printer telemetry remains printer telemetry.

### Activity mapping

The existing `PrinterGcodeState` values map to the platform state as follows:

| Existing state | Workshop OS 12 |
| --- | --- |
| `GCODE_UNKNOWN` | `Unknown` |
| `GCODE_IDLE` | `Idle` |
| `GCODE_PREPARE` | `Preparing` |
| `GCODE_RUNNING` | `Printing` |
| `GCODE_PAUSE` | `Paused` |
| `GCODE_FINISH` | `Finished` |
| `GCODE_FAILED` | `Error` |
| `GCODE_OTHER` | `Unknown` unless a later explicit mapping is defined |

Unknown is preserved rather than inferred.

## Network normalization

Normalize existing Wi-Fi runtime state into:

- `Offline`
- `Connecting`
- `Online`
- `Degraded`
- `Unknown`

Access-point mode is represented separately from ordinary station connectivity. Local portal reachability and cloud reachability remain independent facts so loss of one service does not make the whole appliance appear failed.

## Multi-printer capacity

The current pinned upstream supports four configured printer slots and, on PSRAM boards such as the WS350, up to four active MQTT sessions. The platform state therefore reserves four printer slots rather than collapsing the device to a single printer.

## Command migration order

1. **Observation only** — publish normalized Printer/Network snapshots while existing code remains authoritative.
2. **Read-path migration** — Home/Printer/System views read normalized snapshots.
3. **Non-destructive commands** — chamber light, pause, resume route through `IPrinterService` after parity validation.
4. **Destructive Stop** — migrate last; retain explicit guard confirmation and fail closed on stale/conflicting/unavailable state.
5. Remove direct UI access to legacy globals only after physical parity is demonstrated.

## Runtime invariants

- Touch/render work remains higher priority than blocking MQTT reconnect work.
- Stale or conflicting printer state must not be presented as fresh.
- Invalid printer slot requests fail closed.
- Stop remains guarded.
- Decorative media yields to printer activity, touch responsiveness, and service-health degradation.
- Network, printer, cloud, and inventory failures degrade independently.
- No inventory identity, quantity, ownership, location, or AMS placement is invented by the adapter.

## Physical acceptance requirement

A compiled adapter is not physical acceptance. Before the normalized runtime becomes authoritative on the WS350, validate:

- touch latency during printer reconnect
- pause/resume/stop behavior
- chamber light control
- multi-printer switching
- Wi-Fi reconnect and AP fallback
- stale printer state behavior
- no regression to OTA/recovery
- no inventory-placement inference
- no memory growth or unacceptable heap fragmentation

Until that occurs, UI13's accepted/pending release state remains independent of this Workshop OS 12 branch.
