# Workshop OS roadmap

This document is the persistent product/release roadmap. GitHub issues are reserved for bounded actionable work; long-lived direction lives here.

## Current release state

The repository deliberately separates **physically accepted hardware state**, **code present on `main`**, and **static distribution**.

- **Physically accepted hardware baseline:** Workshop OS **v11.19.1 Physical Fit RC2**.
- **Current code on `main`:** Workshop OS **v11.20 Portal Auth RC1** plus the merged **v11.21 Settings Parity Audit**. v11.21 adds registry/CI enforcement only; it does not replace the pending real-device v11.20 authentication acceptance gate.
- **Static installer:** Workshop OS **v11.19.1 Physical Fit RC2** Full + OTA.
- **Static rollback:** Smart Home **v7.2** Full + OTA.
- **Repository governance:** `main` is protected and requires the stable path-aware `merge-gate` status; force pushes and deletion are blocked.
- **Active development candidate:** **v11.22 Display Expert RC1** on `feature/v11-22-display-expert`. This is a hardware-facing UI/settings candidate and therefore requires real WS350 acceptance before promotion.

`releases/current.json` remains authoritative for accepted source, `main` state, and static download channel. A merge or green CI does not by itself replace the physically accepted hardware baseline.

## Priority 0 — physically accept or reject v11.20 Portal Auth

v11.20 is already present on `main`. Real-device authentication evidence remains a prerequisite for promoting any descendant firmware candidate.

Required checks:

- normal-LAN browser redirects to custom `/login`;
- wrong portal code rejected / current System-screen code accepted;
- portal code absent from ordinary Serial output;
- logout invalidates the session;
- reboot invalidates the prior boot-scoped session;
- authenticated Light / Pause / Resume / Stop / Power and OTA remain functional;
- signed-out normal-LAN `/recovery` requires authentication;
- authenticated normal-LAN Recovery works;
- ordinary setup/fallback AP exposes onboarding essentials without anonymous privileged controls;
- portal-code login works on AP where protected access is required;
- deliberate Recovery Safe Mode exposes only intended recovery/status/actions + OTA/reset surfaces;
- touch, printer settings, display fit, speaker/MIC ECHO, and accepted v11.19.1 behavior remain intact;
- retained framebuffer/capture artifacts redact the System credential line and retain no secrets.

If these pass, update release metadata so the inherited v11.20 security delta is physically accepted. If they fail materially, keep v11.19.1 accepted and fix/revert before any later candidate can promote.

## Priority 1 — v11.21 Settings Parity Audit — COMPLETE

Merged to `main`.

The repository now has:

- version-controlled WS350 capability registry under `docs/settings-capability-registry/`;
- every tracked writable browser setting classified as `PHYSICAL`, `PHYSICAL-EXPERT`, `PORTAL-INPUT`, or `BOARD-N/A`;
- explicit inventory of non-setting POST command/auth/recovery routes;
- static registry validation in normal `Validate`;
- reconstructed-source route/key/evidence validation in the firmware gate;
- browser route/key drift detection;
- physical-evidence checks for settings claimed as implemented physically.

v11.22 tightens this contract so implemented `PHYSICAL-EXPERT` entries also require source evidence and the reconstructed-source validator advances with v11.20+ candidates rather than being frozen to one version string.

## Priority 2 — v11.22 Display Expert RC1 — ACTIVE

Move the remaining safe, visually dense display configuration onto a deeper WS350 expert surface while preserving portal boundaries for text/secrets and preserving fixed safety-state colors.

Candidate scope:

- curated theme palettes and clock colors;
- gauge color editor for all existing gauge groups;
- gauge full-scale ranges;
- gauge smoothing / warning threshold / warning color;
- glow mode/style/duration/color;
- 8-slot / 9-slot layout modes and split presentation settings;
- clock-info toggle;
- AMS tray-type presentation;
- seven new deterministic capture views, expanding the physical visual catalog from 22 to 29.

Explicit boundaries:

- custom gauge labels remain `PORTAL-INPUT`;
- display rotation remains v11.23 because it changes touch mapping;
- no speculative speed/fan/temperature/AMS printer commands;
- no change to accepted-source/static-installer metadata until physical promotion criteria are met.

Promotion requires both inherited v11.20 authentication acceptance and v11.22 Display Expert real-device acceptance.

## Priority 3 — v11.23 Network / Locale / Layout Expert

- timezone;
- coordinated DHCP/static mode;
- segmented IP / gateway / subnet / DNS entry;
- guarded display rotation with touch-remap recovery semantics;
- deeper printer rotation policy;
- deeper network diagnostics where capability evidence exists.

Wi-Fi credentials and hostname remain portal input.

## Priority 4 — v11.24 Printer / Workshop / Power Configuration

- light start/finish/failure automation and off delay;
- printer connection mode and region;
- PSRAM multi-printer expert enablement;
- custom dashboard enable/refresh/return behavior;
- plug type/outlet selection;
- power currency/tariff.

Text/secrets such as printer identity/access credentials, dashboard URL/note, and plug IP remain portal input.

## Priority 5 — v11.25 Deeper Waveshare hardware use

Capability-gated opportunities:

- AXP2101 power telemetry;
- PCF85063 RTC fallback;
- QMI8658 motion/orientation behavior;
- richer ES8311 notification controls;
- microSD diagnostics/history/export;
- panel-life-aware backlight and sleep policies;
- wiring-sensitive buzzer/LED expert controls.

Peripheral failure must degrade gracefully and never block printer operation.

## Priority 6 — v11.26 Reliability / soak release

No major UX feature family. Focus on:

- 24/48/72-hour soak and memory trend testing;
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
- real-device acceptance whenever touch, display, audio, recovery, authentication, or control behavior can change.

Quality gates and physical evidence — not planned version numbers — determine promotion.
