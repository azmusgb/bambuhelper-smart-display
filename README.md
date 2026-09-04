# BambuHelper Smart Display — Waveshare Workshop OS

Local-first Workshop OS for the **Waveshare ESP32-S3-Touch-LCD-3.5 (`ws_lcd_350`)**, built on the BambuHelper v3.8.1 core.

## Release model

The repository deliberately separates the **physically accepted source baseline** from the conservative static download channel.

| Surface | Current state | Purpose |
| --- | --- | --- |
| accepted source baseline | **Workshop OS v11.22 Display Expert RC1 — physically accepted** | Current source baseline accepted on real WS350 hardware. |
| `main` | **Workshop OS v11.22 Display Expert RC1 — accepted** | PR #74 merged after exact-head CI and real-device acceptance. |
| `release.json` / Netlify | **Workshop OS v11.19.1 Physical Fit RC2** | Conservative static installer retained until its binary-channel promotion is performed separately. |
| static rollback download | **Smart Home v7.2** | Current static-channel rollback while v11.19.1 remains the published installer. |
| active candidate | **Workshop OS v11.23 Network Locale Layout RC2 — PR #76** | Touch-UX / network candidate; exact-head CI and physical WS350 acceptance are required before promotion. |

A merge is not physical acceptance by itself. `releases/current.json` is authoritative for accepted source, candidate state, `main` state, and the static download channel.

## Active candidate — Workshop OS v11.23 Network Locale Layout RC2

PR **#76** now carries the RC2 interaction redesign after RC1 proved technically healthy but exposed unnecessary friction during real WS350 touch testing.

### RC2 touch experience

The physical interface is being elevated around **discoverability, target size, explicit direction, and safe staging**:

- Network Expert uses large finger-sized controls instead of dense card-only gestures;
- every network page has explicit **Back / Next** navigation;
- Time & Locale exposes dedicated **Prev / Next** timezone controls;
- Address Editor exposes a visible **STAGED — NOT APPLIED** state;
- IPv4 editing uses selectable octets plus explicit **-10 / -1 / +1 / +10** controls;
- Address Review separates **Back**, **Discard**, and guarded **Hold Apply + Restart**;
- normal short taps can no longer accidentally apply a network configuration;
- Display Expert removes hidden “hold to go backward” behavior — left-side / right-side card interaction becomes the explicit previous/next model;
- display rotation remains intentionally **hold-guarded** because it changes orientation and touch mapping;
- page position is shown explicitly on the Network Expert flow;
- the existing 32-view deterministic framebuffer catalog is retained.

### Temporary portal-code policy

For **v11.23 RC2 only**, the normal-Wi-Fi portal-code challenge is temporarily bypassed to reduce development friction while touch behavior is iterated on real hardware.

This is intentionally narrower than deleting the security subsystem:

- `SECURE_GET` / `SECURE_POST` route wrappers stay in place;
- mutating requests still enforce same-origin protection;
- ordinary AP mode does **not** become a blanket admin bypass;
- setup/recovery AP exceptions remain route-scoped;
- the session/token implementation remains in source so the temporary bypass can be removed cleanly in one later delta;
- the browser shows a visible **TEMPORARY TRUSTED-LAN MODE** warning.

The LAN-open mode is a temporary candidate-development decision, **not** the accepted long-term security policy.

### Network / Locale / Layout scope retained from RC1

- physical timezone selection using the existing supported timezone database;
- coordinated DHCP/static mode;
- segmented IP / gateway / subnet / DNS editing staged on-device;
- no network mutation until the Review page is deliberately held to apply;
- restart after an accepted network commit so addressing changes are applied coherently;
- guarded display rotation;
- Time & Locale, Address Editor, and Network Review framebuffer acceptance views;
- Wi-Fi credentials and hostname remain browser-only inputs;
- no speculative speed, fan, temperature, or AMS printer commands.

The candidate is **not accepted** until exact-head RC2 CI and real-device touch/display/network acceptance pass. v11.22 remains the authoritative physically accepted source baseline.

## Accepted source — Workshop OS v11.22 Display Expert RC1

PR **#74** completed the v11.22 Display Expert evolution and was physically accepted on a real WS350 on **2026-09-04**.

Acceptance evidence includes:

- exact-head `Validate`, `Release Gate`, stable `merge-gate`, and **Workshop OS Firmware Gate — v11.22 Display Expert RC1** success;
- native `ws_lcd_350` build success;
- shared `jc3248w535` 320×480 regression success;
- inherited v11.20 portal-auth contract validation;
- v11.22 Display Expert contract and settings-parity validation;
- healthy read-only device interrogation reporting `Smart Home v11.22 Display Expert RC1`, `safeMode=false`, responsive FT6336 touch, connected Wi-Fi, healthy memory, and connected printer telemetry;
- complete **29-view** authenticated framebuffer capture with the System credential line redacted before retained PNG/PPM output.

### v11.22 Display Expert

The physical Display Experience includes 14 pages, with expert surfaces for curated theme palettes, clock colors, gauge colors/scales/behavior, glow, layout, Clock Info, and AMS Tray Types.

Free-text Gauge Labels remain browser-only.

### Inherited safety

Printer control remains selected-printer scoped and fail-closed. Chamber Light, Pause/Resume, guarded Stop, and mapped Printer Power retain their established safeguards.

Speed, fan, temperature, AMS, or other printer commands are not added without a proven backend path and explicit safety semantics.

## Static installer

The static installer intentionally remains **Workshop OS v11.19.1 Physical Fit RC2**, with **Smart Home v7.2** as rollback. Accepted source and static distribution are independent release surfaces.

For a normal existing-device update, use the application/OTA image. A Full image belongs only at flash offset `0x0` during intentional USB recovery/full flash.

## Validation model

Firmware is reconstructed deterministically from pinned upstream BambuHelper commit `8cb1cbbb6d3c175af91989e8ebe1bbdcbe848ac4` plus the versioned `apply_smart_home_*.py` evolution stack. The reusable firmware gate validates deterministic reconstruction, inherited safety/security, candidate-specific contracts, settings parity, browser JavaScript, native `ws_lcd_350`, shared `jc3248w535`, and Full/OTA artifact provenance.

For v11.23 RC2, the gate reconstructs and validates the authenticated v11.20 baseline first, then applies the explicit RC2 temporary LAN-open delta. This keeps the accepted auth implementation testable and makes the development bypass obvious and reversible.

`docs/settings-capability-registry/` is the machine-authoritative WS350 browser/device settings parity inventory.

## Repository layout

- `apply_smart_home_*.py` — deterministic firmware evolution inputs.
- `.bambuhelper-validation/` — verified patch payloads required by selected loaders.
- `.github/workflows/firmware-candidate.yml` — single reusable firmware/hardware gate.
- `.github/workflows/validate.yml` — repository validation.
- `.github/workflows/release-gate.yml` — source/release metadata gate and stable `merge-gate` coordination.
- `.github/workflows/release-main.yml` — accepted static installer integrity gate.
- `docs/` — architecture, safety, parity, acceptance, and roadmap documentation.
- `docs/archive/` and `releases/archive/` — historical provenance.
- `releases/current.json` — accepted-source / candidate / `main` / static-channel state.
- `scripts/capture-ws350-views.zsh` — credential-safe physical framebuffer capture helper; RC2 supports temporary trusted-LAN access without requiring a code prompt.

## Governance and safety

- `main` is protected by the stable path-aware `merge-gate`.
- Hardware-facing changes require exact-head CI and real-device acceptance before source promotion.
- Generated PlatformIO output, local capture ZIPs, credentials, and ad-hoc reports stay out of source control.
- Captures redact the System credential region before retained output and exclude printer configuration/settings exports.
- Static firmware retention remains bounded to the published pair plus one rollback pair.
- Upstream synchronization is its own candidate; the accepted source line is never silently repinned.
- Temporary trusted-LAN mode must be explicitly removed or intentionally re-approved before a security-hardened production promotion.

## License and attribution

Original Workshop OS contributions are provided under the **MIT License** in `LICENSE`. Workshop OS is derived from **Keralots/BambuHelper**; exact attribution and third-party boundaries are recorded in `NOTICE.md`.
