# Workshop OS roadmap

This document is the persistent product/release roadmap. GitHub issues are reserved for bounded actionable work; long-lived direction lives here.

## Current release state

- **Physically accepted hardware/source baseline:** Workshop OS **v11.22 Display Expert RC1**.
- **Current code on `main`:** Workshop OS **v11.22 Display Expert RC1** — accepted.
- **Static installer:** Workshop OS **v11.19.1 Physical Fit RC2** Full + OTA (intentionally conservative until a separate binary-channel promotion).
- **Static rollback:** Smart Home **v7.2** Full + OTA.
- **Repository governance:** protected `main` with stable path-aware `merge-gate`; force pushes and deletion blocked.
- **Active firmware candidate:** none.

`releases/current.json` remains authoritative. Green CI alone is not physical acceptance.

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

The WS350 browser/device configuration contract is now machine-enforced:

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

Gauge Labels remain portal input because they are free text. Display Rotation remains deferred.

## Priority 1 — v11.23 Network / Locale / Layout Expert

Next recommended firmware evolution:

- timezone;
- coordinated DHCP/static mode;
- segmented IP / gateway / subnet / DNS entry;
- guarded display rotation;
- printer rotation/split policy;
- deeper network diagnostics where real capability evidence exists.

Wi-Fi credentials and hostname remain **PORTAL-INPUT**.

### v11.23 design constraints

- network configuration must remain atomic: no partially-applied static configuration;
- display rotation must be guarded and recoverable if the selected geometry breaks touch/display orientation;
- no secret/free-text keyboard work should be introduced just to satisfy parity;
- preserve v11.22's 29-view visual acceptance catalog and add new views only when they materially improve acceptance coverage.

## Priority 2 — v11.24 Printer / Workshop / Power Configuration

- light start/finish/failure automation and off delay;
- printer connection mode and region;
- PSRAM multi-printer expert enablement;
- custom dashboard enable/refresh/return behavior;
- plug type/outlet selection;
- power currency/tariff.

Printer identity/access credentials, custom dashboard URL, Workshop note, and plug IP/hostname remain portal input.

## Priority 3 — v11.25 Deeper Waveshare hardware use

Capability-gated opportunities:

1. AXP2101 power telemetry;
2. PCF85063 RTC fallback;
3. microSD diagnostics/history/export;
4. QMI8658 motion/orientation behavior;
5. richer ES8311 notification controls;
6. panel-life-aware backlight/sleep policies;
7. wiring-sensitive buzzer/LED expert controls.

Peripheral failure must degrade gracefully and never block printer operation.

## Priority 4 — v11.26 Reliability / soak release

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
