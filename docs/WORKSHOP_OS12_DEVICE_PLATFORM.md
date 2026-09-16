# Workshop OS 12 — Device Platform Foundation

Workshop OS 12 evolves the WS350 firmware from a collection of feature screens into a resource-managed workshop appliance. This document defines the first platform boundary only; it does not promote a new firmware release and does not alter the frozen UI13 physical-acceptance evidence.

## Source and release boundary

Foundation work begins from the exact UI13 source head:

`3672a6f0947af0c890a4f7a79c28b140c901425b`

The UI13 candidate remains subject to its own physical acceptance gate. OS12 platform work must not be used to claim that UI13, any later binary, or any recovery path has been physically accepted.

## Authority

### Filament Inventory

Authoritative for:

- spool identity and QR resolution
- household/member scope
- ownership and sharing
- quantity evidence
- locations
- printer/AMS inventory relationships
- print requirements/readiness
- usage and forecasting
- grounded AI
- device-facing inventory data

### Workshop OS / WS350

Authoritative for:

- firmware runtime
- touchscreen UX and navigation
- Bambu printer telemetry/control
- local hardware state
- audio/microphone/BLE
- networking
- OTA and recovery UX
- physical-device acceptance

Workshop OS consumes inventory state; it does not manufacture inventory truth.

## Platform model

The target runtime is organized around one state store fed by independently managed services.

```text
                    Workshop OS
                        |
              +---------+---------+
              |                   |
          UI / Touch          System Services
              |                   |
              v                   v
          WorkshopState <---- PrinterService
              ^             <---- NetworkService
              |             <---- InventoryService
              |             <---- AudioService
              |             <---- MediaService
              |             <---- PowerService
              |             <---- UpdateService
              |             <---- HealthService
```

Screens render `WorkshopState` and request actions. Screens must not directly become independent authorities for printer, inventory, network, media, or update state.

## WorkshopState responsibilities

`WorkshopState` is a normalized runtime view, not a persistence authority. It should eventually contain:

- printer connection and normalized operational state
- network connectivity
- device-feed freshness and profile scope
- inventory summary projected from Filament Inventory
- explicit placement evidence received from the device contract
- alert/attention summary
- audio/media runtime state
- update state
- device health metrics

Each state domain must distinguish, where applicable:

- `fresh`
- `stale`
- `unknown`
- `conflicting`

`Unknown` is a valid state and must not be replaced by a guess.

## Service boundaries

### PrinterService

Owns Bambu LAN/session integration, normalized telemetry, command dispatch, command acknowledgement, reconnect behavior, and printer-specific fault reporting.

Printer commands are higher priority than decorative work.

### NetworkService

Owns Wi-Fi state, local connectivity, reconnect, signal quality, and service reachability. Network loss must not make healthy local hardware appear failed.

### InventoryService

Consumes the versioned Filament Inventory device contract. It must reject unsupported schema versions, cross-profile payloads, malformed authoritative placement, and payloads that attempt to substitute appearance matching for placement evidence.

### AudioService

Owns speaker/microphone resources and event-driven sound policy. UI screens request semantic events rather than directly owning audio files.

### MediaService

Owns optional animation/video playback. Media is always subordinate to touch, printer control, networking integrity, recovery, and critical alerts.

Initial supported media should remain intentionally small: static images, sprite/frame animation, and bounded MJPEG only after runtime benchmarking.

### PowerService

Owns display power/standby behavior and printer smart-plug operations. Printer power-off remains guarded and safety-relevant.

### UpdateService

Owns normal Workshop OS update state and artifact validation. Full-image cross-line migration/recovery remains a separate service/recovery workflow and must not be presented as routine OTA.

### HealthService

Owns runtime observability: uptime, free heap, largest block, PSRAM, task/service heartbeats, reconnect counts, UI/media timing, last reboot reason, and relevant fault counters.

## Runtime priority classes

The runtime should enforce semantic priorities rather than letting features compete implicitly.

1. **Critical** — printer command dispatch, guarded destructive actions, session/security integrity, recovery-critical work.
2. **High** — touch input, navigation, printer telemetry, state-store updates, connectivity transitions.
3. **Normal** — inventory refresh, assistant/device-feed requests, routine audio, noncritical persistence.
4. **Low** — decorative animation, ambient media, nonessential visual effects.

Low-priority work must be cancellable. A decorative media task must never delay a printer command or make navigation unresponsive.

## Degraded-mode contract

Subsystem failures are independent:

- cloud/device feed unavailable -> local printer control remains available
- printer unavailable -> inventory/device settings remain available
- media failure -> UI remains usable
- audio failure -> visual operation remains usable
- stale inventory -> freshness is shown; stale values are not silently promoted to current truth

The product should degrade by capability, not collapse into a generic error screen.

## Device contract

The first version is defined by:

`contracts/workshop-device-state-v1.schema.json`

The contract is a minimal, redacted, profile-scoped projection. It deliberately excludes provider API keys, broad user secrets, raw household data, and any field that would authorize Workshop OS to infer authoritative spool identity or placement from printer color/material telemetry.

Important distinctions:

- Bambu-reported material/color is printer telemetry.
- Inventory placement is authoritative only when the device contract supplies explicit placement evidence.
- A telemetry match is not placement evidence.

## Media/video gate

Do not enable rich video merely because the ESP32-S3 can decode frames. Before media becomes a normal feature, physical benchmarking must demonstrate that playback does not materially degrade:

- touch latency
- printer command latency
- Bambu session stability
- Wi-Fi/device-feed stability
- heap/PSRAM reserve
- long-running memory behavior
- audio coexistence

A reasonable initial target is bounded MJPEG around 12–15 FPS with immediate cancellation, but the accepted target must come from actual WS350 measurements rather than assumption.

## Resource budgets

Exact limits must be measured on hardware before promotion. The platform should nevertheless track budgets for:

- maximum UI/touch service latency
- printer command dispatch latency
- minimum free internal heap
- largest free block
- PSRAM reserve
- sustained media CPU share
- missed-frame count
- reconnect/error count

A media feature that meets its own FPS target while degrading control latency fails acceptance.

## First implementation slice

The initial foundation slice contains no physical-release claim. It establishes:

1. this architecture contract
2. the versioned device-state JSON schema
3. deterministic validation of the contract/truth boundary
4. CI execution of that validation

The next code-bearing slice should introduce the firmware-side normalized state and service interfaces into the authoritative build recipe, followed by PrinterService/NetworkService migration before MediaService is enabled.

## Acceptance rule

The release-state chain remains:

`implemented -> built -> tested -> runtime validated -> production validated -> physically validated -> accepted -> stable`

No later state is inferred from an earlier one.
