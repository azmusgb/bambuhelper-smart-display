# Workshop OS 12 — Device Platform Foundation

Workshop OS 12 evolves the WS350 firmware from a collection of feature screens into a resource-managed workshop appliance. This document defines the platform boundary; it does not promote a firmware release and does not alter the frozen UI13 physical-acceptance evidence.

## Source and release boundary

Foundation work begins from exact UI13 source head:

`3672a6f0947af0c890a4f7a79c28b140c901425b`

UI13 remains subject to its own physical-acceptance gate. OS12 source, builds, CI artifacts, or successful host tests must not be used to claim that UI13, OS12, an OTA path, or recovery has been physically accepted.

The OS12 reconstruction has a release identity distinct from the frozen UI implementation identity. Current development builds use numeric release version `12.0.0` plus the exact source SHA embedded at build time. Once a version is published in the device manifest, different bytes/source must use a new version; published release identities are immutable.

## Authority

### Filament Inventory

Authoritative for spool identity/QR resolution, household/member scope, ownership/sharing, quantity evidence, locations, printer/AMS inventory relationships, print requirements/readiness, usage/forecasting, grounded AI, and device-facing inventory data.

### Workshop OS / WS350

Authoritative for firmware runtime, touchscreen UX/navigation, Bambu printer telemetry/control, local hardware state, audio/microphone/BLE, networking, OTA/recovery UX, and physical-device acceptance.

Workshop OS consumes inventory state; it does not manufacture inventory truth.

## Platform model

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

Screens render normalized `WorkshopState` and request actions. Screens must not become independent authorities for printer, power, inventory, network, media, or update state.

`Unknown` is a valid state. Where applicable each domain preserves `fresh`, `stale`, `unknown`, and `conflicting` rather than guessing.

## Service boundaries

### PrinterService

Owns Bambu LAN/session integration, normalized telemetry, command dispatch/acknowledgement, reconnect behavior, and printer-specific fault reporting. Printer commands have higher runtime priority than decorative work.

### NetworkService

Owns Wi-Fi/local connectivity, reconnect, signal quality, and service reachability. Network loss must not make healthy local hardware appear failed.

### InventoryService

Consumes the versioned Filament Inventory device contract. It rejects unsupported schema versions, cross-profile payloads, malformed authoritative placement, and any attempt to substitute color/material matching for placement evidence.

### AudioService / MediaService

Audio owns speaker/microphone resources and semantic event sound policy. Media owns optional static/sprite/MJPEG playback. Both are subordinate to touch, printer control, network integrity, recovery, and critical alerts.

### PowerService

Owns normalized mapped-plug state and guarded printer-power operations. Power Off remains safety relevant; stale/unknown printer state requires stronger handling rather than optimistic inference.

### UpdateService

Owns normal Workshop OS device-native online update state and artifact validation. It is the only active device-initiated online-update authority in OS12.

The service:

- reads `releases/device-update.json` from canonical raw `main` over certificate-validated HTTPS;
- supports explicit Stable and Candidate channels, with Stable as default;
- validates schema, firmware authority, WS350 board identity, artifact base, version, source SHA, relative artifact path, size, and SHA-256 metadata;
- refuses automatic downgrade;
- refuses install when any configured printer is active or has stale/unknown operational state;
- downloads only an OTA/application image to the inactive application partition;
- verifies exact content length, downloaded byte count, and SHA-256 before selecting the new boot partition;
- leaves the currently bootable firmware authoritative on failure and restores printer connectivity when no reboot is coming;
- reboots only after successful stage/verification/boot-partition selection.

The legacy arbitrary-URL `/ota/auto` route is not registered in the OS12 reconstruction. The local authenticated manual OTA path remains a bootstrap/maintenance fallback, not a parallel online-update authority.

Full-image cross-line migration/recovery is separate. A Full image at offset `0x0` must never be presented as routine OTA.

### HealthService

Owns runtime observability such as uptime, free heap/largest block, PSRAM reserve, service responsiveness, reconnect/error counters, UI/media timing, and reboot reason. Exact physical budgets remain subject to hardware measurement.

## Device contract

The first Filament Inventory projection contract is:

`contracts/workshop-device-state-v1.schema.json`

It is minimal, redacted, versioned, and profile-scoped. It excludes provider credentials, broad user secrets, raw household data, and any field that would authorize Workshop OS to infer authoritative spool identity/placement from printer telemetry.

Bambu-reported material/color is telemetry. Inventory placement becomes authoritative only when explicit placement evidence arrives through the Filament Inventory contract.

## Local portal authentication boundary

Workshop OS 12 keeps the rotating physical portal code as the local browser authentication factor without pretending the raw-IP HTTP portal provides TLS transport security.

The current contract is:

- exact server alphabet `ABCDEFGHJKLMNPQRSTUVWXYZ23456789`;
- case-insensitive browser entry normalized to uppercase before authoritative comparison;
- `I`, `O`, `0`, and `1` rejected;
- bounded per-client exponential login backoff after two failures, capped at 60 seconds;
- unique RAM-only 128-bit session tokens, at most six active slots, eight-hour server lifetime;
- cookie `HttpOnly; SameSite=Strict`, deliberately without a false `Secure` attribute on HTTP;
- logout revokes only the presenting session;
- reboot invalidates RAM sessions and rotates the portal code;
- same-origin protection remains required for authenticated browser mutations;
- setup/recovery authorization boundaries remain distinct.

The login UI exposes explicit Ready, Invalid, Rate-limited, and Submitting states with semantic headings, UTF-8/lang metadata, associated help/errors, alert/live regions, focus treatment, reduced-motion/forced-colors behavior, and pointer-gated hover polish. `autocomplete="one-time-code"` is not used because the code is read from the WS350 rather than sent by SMS/email.

Static/compile validation is necessary but not physical acceptance.

## Software Update UX

The touch path is intentionally shallow:

`System -> Software Update`

From there the user can select Stable/Candidate, check the authoritative manifest, review a discovered update, and explicitly confirm installation. The screen consumes normalized `UpdateState` for running/available version, manifest freshness, phase/progress, candidate label, and artifact-integrity status.

A confirmation screen explains that Workshop OS will download the exact GitHub OTA artifact, verify declared size and SHA-256, write only the inactive application partition, and restart. Routine update actions do not depend on hidden long-press behavior.

A pre-OS12 device needs one bootstrap installation through the existing authenticated local OTA path before it can use this new GitHub-native flow.

## Runtime priority and degraded mode

Priority classes remain:

1. **Critical** — printer command dispatch, guarded destructive actions, session/security integrity, recovery-critical work.
2. **High** — touch/navigation, printer telemetry, state-store updates, connectivity transitions.
3. **Normal** — inventory refresh, assistant/device-feed requests, routine audio, noncritical persistence/update checks.
4. **Low** — decorative animation/ambient media/nonessential visual effects.

Low-priority work must be cancellable. Update installation is explicit and guarded; it must not begin while a printer is active or operational state is uncertain.

Subsystem failures degrade by capability: cloud/device-feed loss does not remove local printer control; printer loss does not remove inventory/settings; stale inventory stays visibly stale; media/audio failure does not collapse the UI.

## Current implementation slice

The branch currently establishes:

1. architecture contract and versioned inventory device-state schema;
2. normalized Printer/Network/Power/Update state in `WorkshopState`;
3. UI/System read migration through the OS12 facade;
4. Light, Pause, Resume, and guarded Stop routing through OS12 printer-command validation;
5. guarded mapped-plug power command policy;
6. local portal validation/session/rate-limit/accessibility hardening;
7. manifest-bound GitHub `UpdateService` with Stable/Candidate channel selection, fail-closed printer-state guard, streamed inactive-partition write, exact size/SHA-256 verification, and deferred reboot;
8. WS350 Software Update touch UX and authenticated local update-service API;
9. retirement of the legacy registered `/ota/auto` URL authority in OS12;
10. exact OS12 release-version/source-SHA stamping plus candidate-publication preparation tooling;
11. deterministic validators, reconstruction checks, WS350 build, and cross-board compile gates.

This is an implementation/build/test state until exact-head CI completes. It is not runtime validated merely because the code compiles, and it is not physically validated merely because a candidate artifact exists.

Inventory expansion, richer health metrics, media benchmarking, and other device services remain later coherent slices and must not create competing authorities.

## Acceptance rule

The release-state chain remains:

`implemented -> built -> tested -> runtime validated -> production validated -> physically validated -> accepted -> stable`

No later state is inferred from an earlier one. Stable publication must preserve the exact physically accepted artifact identity rather than rebuilding an allegedly equivalent image.
