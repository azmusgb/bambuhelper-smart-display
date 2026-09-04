# Workshop OS roadmap

This document replaces GitHub issue #3 as the persistent roadmap. GitHub issues should represent bounded, actionable work; long-lived product direction belongs in version-controlled documentation.

## Current release state

The repository deliberately separates **physically accepted hardware state**, **code present on `main`**, and **static distribution**.

- **Physically accepted hardware baseline:** Workshop OS **v11.19.1 Physical Fit RC2**. Physical acceptance passed on the WS350 using the complete 22-view framebuffer capture and exact-final-head CI.
- **Current code on `main`:** Workshop OS **v11.20 Portal Auth RC1**. Exact-head CI, WS350 build, shared 320×480 regression, browser JavaScript, and portal-auth contracts pass, but real-device authentication acceptance is still pending.
- **Static installer:** **Workshop OS v11.19.1 Physical Fit RC2** Full + OTA.
- **Static rollback:** **Smart Home v7.2** Full + OTA.
- **Active firmware candidate:** none.

`releases/current.json` is authoritative for accepted source, current `main`, candidate state, and static download channel. A merge or green CI does not by itself replace the physically accepted hardware baseline.

## Priority 0 — physically accept or reject v11.20 Portal Auth

v11.20 is already present on `main`. The next action is real-device validation, not another merge.

Required checks:

- normal-LAN browser redirects to the custom `/login` page;
- wrong portal code is rejected and the current System-screen code is accepted;
- portal code is absent from ordinary Serial output;
- logout invalidates the session;
- reboot invalidates the previous boot-scoped session;
- authenticated Light / Pause / Resume / Stop / Power and OTA remain functional;
- signed-out normal-LAN `/recovery` requires authentication;
- authenticated normal-LAN Recovery works;
- ordinary setup/fallback AP exposes onboarding essentials without anonymous privileged controls;
- portal-code login works on AP where protected access is required;
- deliberate Recovery Safe Mode independently exposes the intended recovery/status/actions and application OTA/reset surface;
- touch, printer settings, display fit, speaker/MIC ECHO, and accepted v11.19.1 behavior remain intact;
- retained framebuffer/capture artifacts redact the System credential line and do not retain secrets.

If these checks pass, update release metadata so v11.20 becomes the accepted source baseline. If they fail materially, keep v11.19.1 as accepted and fix or revert the v11.20 delta.

## Priority 1 — repository governance

Issue #60 remains the only repository-administration item: protect `main` using a GitHub ruleset or branch protection.

Desired policy:

- require a pull request before merging;
- require successful `Validate`;
- require successful `Release Gate`;
- require the Workshop OS firmware gate when firmware-facing code changes;
- require the accepted-static-installer gate when `release.json`, tracked firmware binaries, installer assets, or release validation change;
- require up-to-date branches where practical;
- block force pushes;
- block branch deletion;
- no routine bypass;
- any administrator bypass reserved for documented emergency/recovery use.

A future CI refinement should expose one always-present stable **Merge Gate** status that internally decides which deeper checks are required for the changed paths. This makes GitHub protection simpler and avoids depending on conditional status names.

Physical acceptance remains separate from GitHub branch protection; no repository rule can prove real WS350 behavior.

## Priority 2 — dependency policy

The upstream BambuHelper repin evaluation is complete. Proposed upstream `f86555c4e050ccee73d8005ac5dfc77baa101b5c` is nine commits ahead of the accepted pin `8cb1cbbb6d3c175af91989e8ebe1bbdcbe848ac4` and overlaps display, touch, MQTT, settings, browser, and smart-plug code.

Decision: retain the accepted pin until a dedicated upstream-sync candidate performs deterministic reconstruction, overlap review, dual-target CI, safety checks, and physical acceptance.

## Priority 3 — complete daily-operation parity

Continue toward touchscreen-complete normal workshop operation while keeping the browser as the power-user/admin surface.

- maintain a capability registry for every portal/device setting;
- classify every setting as touchscreen-editable, read-only with reason, browser-only by reviewed exception, or unsupported;
- improve command acknowledgement from requested → sent → observed/confirmed where telemetry permits;
- enrich HMS recovery guidance and state-driven quick actions;
- deepen AMS/material presentation;
- connect Filament Inventory only through a real configured API bridge—never fabricate external inventory state.

Only add printer controls when the backend protocol is demonstrated and safety semantics are explicit. Do not guess speed, fan, temperature, or AMS command payloads.

## Priority 4 — deeper Waveshare hardware use

Capability-gated opportunities include:

- AXP2101 power telemetry;
- PCF85063 RTC fallback;
- QMI8658 motion/orientation behavior;
- richer ES8311 notification controls;
- microSD diagnostics/history/export;
- panel-life-aware backlight and sleep policies.

Peripheral failure must degrade gracefully and never block printer operation.

## Priority 5 — reliability and release engineering

Continue strengthening:

- soak and memory testing;
- network/printer reconnect behavior;
- malformed and slow payload handling;
- brownout/interrupted-save behavior;
- OTA interruption/recovery;
- settings migrations;
- artifact provenance;
- publisher-verifiable release metadata.

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

## Immediate next actions

1. Physically accept or reject the **v11.20 Portal Auth RC1** delta already on `main`.
2. Complete **#60** by configuring `main` branch protection/ruleset in GitHub repository administration.
3. Keep the accepted upstream pin until a dedicated upstream-sync candidate is intentionally opened.
4. Resume feature evolution from the then-current **physically accepted** baseline, not merely the newest merged commit.

Quality gates and physical evidence—not planned version numbers—determine promotion.
