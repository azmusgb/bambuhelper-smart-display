# Workshop OS roadmap

This document is the persistent product/release roadmap. GitHub issues are reserved for bounded actionable work; long-lived direction lives here.

## Current release state

- **Physically accepted hardware/source baseline:** Workshop OS **v11.22 Display Expert RC1**.
- **Current code on `main`:** Workshop OS **v11.22 Display Expert RC1** — accepted.
- **Static installer:** Workshop OS **v11.19.1 Physical Fit RC2** Full + OTA (intentionally conservative until a separate binary-channel promotion).
- **Static rollback:** Smart Home **v7.2** Full + OTA.
- **Repository governance:** protected `main` with stable path-aware `merge-gate`; force pushes and deletion blocked.
- **Active direct firmware candidate:** Workshop OS **v11.23 Network / Locale / Layout Expert RC2**, PR **#76** — draft, physical acceptance required.
- **Stacked follow-on candidate:** Workshop OS **v11.24 Audio Console RC1**, PR **#77** — draft, based on #76.

`releases/current.json` remains authoritative for the accepted source and the direct-to-`main` hardware candidate. Green CI alone is not physical acceptance, and a stacked candidate cannot bypass acceptance of its base.

## Completed — v11.20 Portal Auth

Inherited into v11.22 and accepted as part of the current source line:

- rotating 10-character portal code;
- boot-scoped authenticated session;
- protected normal-LAN admin/recovery surfaces;
- independent recovery-safe-mode path;
- authenticated framebuffer capture;
- no development-auth bypass;
- credential-safe retained capture artifacts.

## Completed — v11.21 Settings Parity Audit

The WS350 browser/device configuration contract is machine-enforced:

- registry under `docs/settings-capability-registry/`;
- `PHYSICAL`, `PHYSICAL-EXPERT`, `PORTAL-INPUT`, and `BOARD-N/A` classifications;
- browser route/key drift detection;
- implementation evidence checks for physical settings;
- reusable reconstructed-source parity validation in CI.

## Completed — v11.22 Display Expert

Physically accepted on the WS350 with complete 29-view capture and healthy device interrogation.

Implemented:

- curated theme palettes and clock colors;
- gauge colors and full-scale ranges;
- gauge smoothing / warning threshold / warning color;
- glow mode/style/duration/color;
- extended gauge layout / split presentation;
- Clock Info toggle;
- AMS Tray Types presentation.

Gauge Labels remain portal input because they are free text.

## In validation — v11.23 Network / Locale / Layout Expert RC2

PR **#76** is the current direct-to-`main` hardware candidate.

Implemented candidate scope includes:

- explicit, larger finger-sized Network Expert controls;
- explicit Back / Next navigation rather than hidden tap/hold direction changes;
- physical timezone Prev / Next controls;
- coordinated DHCP/static mode;
- staged IP / gateway / subnet / DNS editing;
- selectable IPv4 octets with explicit `-10 / -1 / +1 / +10` controls;
- visible `STAGED — NOT APPLIED` state;
- separate Back / Discard / guarded Hold Apply + Restart review actions;
- guarded Display Rotation with Current / Preview / Prev / Next / Cancel / Hold Commit;
- preview-only rotation changes that do not persist until deliberate commit;
- retention of the deterministic 32-view candidate capture catalog.

Wi-Fi credentials and hostname remain **PORTAL-INPUT**.

### v11.23 security exception during hardware iteration

RC2 temporarily permits no-code access on normal trusted-LAN station Wi-Fi so touch/network UX can be iterated without portal-code friction. This is a **candidate-only development exception**, not accepted baseline policy. The inherited authenticated/session implementation is reconstructed and validated before the bypass delta, same-origin protection for mutating requests remains, and ordinary AP mode is not converted into a blanket privileged bypass.

Promotion requires exact-head CI plus new real-device acceptance of touch geometry, staged-network safety, rotation preview/commit behavior, and the intended security boundary.

## In validation — v11.24 Audio Console RC1

PR **#77** is stacked on v11.23 and therefore cannot be independently promoted ahead of its base candidate.

Implemented candidate scope includes:

- persistent ES8311 speaker volume, 0–100%, with explicit `-10 / +10` controls;
- Event Sounds toggle;
- direct Speaker Test;
- 250 ms onboard-microphone level sample with 0–100% feedback;
- explicit 1-second, 3-second, and 5-second local record/playback loops;
- Button Clicks control;
- Bed Cooldown control and explicit threshold adjustment;
- Quiet Start / Quiet End explicit hour controls;
- continued PSRAM-backed local-only mic capture → playback → release behavior.

The v11.24 interaction contract follows v11.23 RC2: ordinary adjustments use explicit directional controls rather than hidden long-press reverse semantics.

## Backlog — Printer / Workshop / Power configuration

Still useful after the current candidate stack is physically accepted:

- light start/finish/failure automation and off delay;
- printer connection mode and region;
- PSRAM multi-printer expert enablement;
- custom dashboard enable/refresh/return behavior;
- plug type/outlet selection;
- power currency/tariff.

Printer identity/access credentials, custom dashboard URL, Workshop note, and plug IP/hostname remain portal input unless a safe physical-input design is deliberately introduced.

## Deeper Waveshare hardware use

Capability-gated opportunities:

1. AXP2101 power telemetry;
2. PCF85063 RTC fallback;
3. microSD diagnostics/history/export;
4. QMI8658 motion/orientation behavior;
5. richer ES8311 notification behavior after Audio Console acceptance;
6. panel-life-aware backlight/sleep policies;
7. wiring-sensitive buzzer/LED expert controls.

Peripheral failure must degrade gracefully and never block printer operation.

## Reliability / soak release

No major UX feature family. Focus on:

- 24/48/72-hour soak and memory trends;
- Wi-Fi/printer reconnect behavior;
- malformed/slow payload handling;
- brownout/interrupted-save behavior;
- OTA interruption/recovery;
- settings migrations;
- artifact provenance and publisher-verifiable release metadata.

## v12 — Workshop OS 2

Only after parity and reliability are closed out:

- richer AMS/material workflow;
- HMS recovery assistant and state-driven quick actions;
- command lifecycle `REQUESTED → SENT → OBSERVED → CONFIRMED` where telemetry permits;
- real Filament Inventory integration through a configured API bridge;
- state-aware Home/Standby experiences;
- historical device/print telemetry when backed by real storage.

## Cross-release invariants

Every future release must preserve:

- local-first operation;
- explicit stale/offline/unsupported/failure state;
- fail-closed printer and power commands;
- guarded destructive actions;
- no speculative Bambu commands;
- no visible steady-state flicker regression;
- no secrets in source, logs, backups, captures, or artifacts;
- deterministic reconstruction from a pinned upstream baseline;
- native WS350 plus shared-target CI;
- real-device acceptance whenever touch, display, audio, recovery, authentication, network, or control behavior can change.

Quality gates and physical evidence — not planned version numbers — determine promotion.
