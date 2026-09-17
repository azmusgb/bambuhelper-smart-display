# Workshop OS 12 — Device Platform Foundation

Workshop OS 12 evolves the WS350 firmware from a collection of feature screens into a resource-managed workshop appliance. This document defines the platform boundary; it does not promote a new firmware release and does not alter the frozen UI13 physical-acceptance evidence.

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

## Local portal authentication boundary

Workshop OS 12 keeps the rotating physical portal code as the local browser authentication factor and hardens the implementation without pretending that the raw-IP HTTP portal provides TLS transport security.

The current OS12 portal contract is:

- the canonical code alphabet is exactly `ABCDEFGHJKLMNPQRSTUVWXYZ23456789` on the server;
- browser validation accepts the same letters in either case plus digits `2-9`, while the submitted value is normalized to uppercase before the authoritative server comparison;
- `I`, `O`, `0`, and `1` are rejected on both sides;
- failed login attempts are tracked per client address with bounded exponential backoff after two unsuccessful attempts, capped at 60 seconds;
- successful authentication issues a unique RAM-only 128-bit session token rather than sharing one token across every browser;
- at most six active session slots are retained, each with an eight-hour server-side lifetime and matching cookie `Max-Age`;
- the cookie remains `HttpOnly` and `SameSite=Strict`; it deliberately does not claim the `Secure` attribute while the direct device portal is served over HTTP;
- logout revokes only the presenting session instead of silently logging out every other client;
- a reboot invalidates all sessions naturally because session state is RAM-only and also rotates the physical portal code;
- same-origin protection for authenticated mutating browser requests remains authoritative;
- ordinary setup/recovery authorization boundaries from the existing portal security design remain unchanged.

The login surface must expose explicit Ready, Invalid, Rate-limited, and Submitting states. It uses semantic headings/text, `lang`/UTF-8 metadata, associated help/error descriptions, `role="alert"`, `aria-invalid`, an `aria-live` submitting status, disabled/busy controls, keyboard focus treatment, reduced-motion/forced-colors support, and pointer-capability-gated hover polish. `autocomplete="one-time-code"` is not used because this code is read from the WS350 rather than delivered by SMS or email.

Copy describes this as **local device access**, not "secure LAN" or "secure sign-in" while the direct device URL is HTTP. No Bambu account, printer access code, provider credential, or cloud password belongs in this login flow.

Static/compile validation of these contracts is necessary but is not physical acceptance. Actual WS350 testing must still demonstrate wrong-code handling, lowercase entry, rate-limit recovery, multiple independent browser sessions, logout isolation, reboot invalidation, touch/recovery continuity, and normal controls after authentication.

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

## Current implementation slice

The current OS12 branch contains no physical-release claim. It establishes:

1. the architecture contract and versioned device-state schema;
2. deterministic validation of the device truth boundary;
3. normalized Printer/Network state and service interfaces;
4. UI/System read migration through the OS12 facade;
5. Light, Pause, Resume, and guarded Stop routing through OS12 command validation;
6. local portal validation/session/rate-limit/accessibility hardening;
7. CI reconstruction and compile gates for the resulting source.

Power/update/health expansion remains a later coherent slice and must not introduce parallel authorities.

## Acceptance rule

The release-state chain remains:

`implemented -> built -> tested -> runtime validated -> production validated -> physically validated -> accepted -> stable`

No later state is inferred from an earlier one.
