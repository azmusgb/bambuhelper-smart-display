# BambuHelper Smart Display — Waveshare Workshop OS

Local-first Workshop OS for the **Waveshare ESP32-S3-Touch-LCD-3.5 (`ws_lcd_350`)**, built on the BambuHelper v3.8.1 core.

## Release model

This repository deliberately separates the accepted download channel from firmware still awaiting physical-device acceptance:

| Line | Status | Purpose |
| --- | --- | --- |
| `release.json` / Netlify | **Accepted download channel: Smart Home v7.2** | Integrity-checked production/rollback firmware currently served by the static installer. |
| `main` | **Accepted source line: Smart Home v10** | Latest promoted source baseline. |
| PR #39 / `evolve/v11-5-printer-power` | **Current candidate: Smart Home v11.5 Printer Power RC1** | Complete v11 Workshop OS evolution; CI-green and awaiting final physical acceptance before promotion. |

Do not infer that the oldest number is the newest code. The static download channel is intentionally conservative until a candidate has passed physical acceptance.

## Current candidate — Smart Home v11.5

v11.5 turns the display into a guarded workshop control surface while preserving the local-first design.

### Physical experience

- calm Workshop Home with adaptive state hero;
- materials-first AMS / filament rail with color, type and remaining percentage;
- dedicated Printer, Workshop, Tools, More and ambient/standby experiences;
- Workshop note and configurable timers;
- ES8311 speaker self-test, event sounds and onboard microphone **MIC ECHO**;
- chamber-light control;
- state-aware **Pause / Resume**;
- long-press guarded **Stop**;
- mapped smart-plug **Printer Power** with the existing hold-to-confirm safety modal;
- stronger warning before power-off during an active print.

### Browser control plane

The browser UI mirrors the physical-device model and includes printer-scoped Light, Pause/Resume, Stop and mapped Power controls. Destructive actions require explicit confirmation, and v11.4+ commands fail closed if connectivity disappears before publish.

### Safety and reliability preserved

The current stack retains:

- FT6336 touch recovery and coordinate navigation;
- printer-screen retention while printing;
- OTA candidate/rollback protections;
- Safari-safe recovery hashing;
- settings persistence;
- secret-safe settings export;
- WS350 ES8311 audio + microphone support;
- `jc3248w535` shared 320×480 regression compatibility.

Speed/fan command controls remain intentionally deferred until the pinned BambuHelper backend has an equally proven command path.

## Validation

The current candidate is reconstructed from the pinned upstream BambuHelper baseline and every evolution patch. Its exact-head workflow verifies device contracts, browser JavaScript, the native `ws_lcd_350` PlatformIO build, the shared 320×480 regression build, Full-image merge and OTA packaging.

Current candidate PR: **#39** (`evolve/v11-5-printer-power`).

The final promotion gate is **physical acceptance** on the real WS350: display/touch behavior, Speaker, MIC ECHO, Light, Pause/Resume, guarded Stop, mapped Power, recovery and configuration retention.

## Repository layout

- `apply_smart_home_*.py` — deterministic evolution patches used by CI. These are source inputs, not generated artifacts.
- `.bambuhelper-validation/` — verified compressed patch payloads required by selected loaders. Keep these under source control.
- `.github/workflows/bambuhelper-v11-5-printer-power.yml` — current candidate hardware/release gate.
- `.github/workflows/validate.yml` — repository syntax/hygiene validation.
- `.github/workflows/release-gate.yml` — main-branch release metadata gate.
- `.github/workflows/release-main.yml` — accepted static OTA portal integrity validation.
- `docs/archive/` — historical physical-acceptance and roadmap documents.
- `releases/` — persistent release provenance/metadata.
- `firmware/` — binaries still required by the accepted Netlify download channel. New candidate binaries should normally remain GitHub Actions artifacts until promoted.
- `scripts/waveshare-usb.sh` — safe Mac USB/JTAG serial auto-detection helper.

## Firmware installation rule

For a normal device OTA/recovery-page update, use the **application image** (`WaveshareHome-firmware.bin` / named OTA image).

Only a **Full** image belongs at flash offset `0x0` during an intentional USB recovery/full flash.

## Development policy

1. One current release-candidate PR targets `main`.
2. Superseded RC PRs are closed rather than left as competing active releases.
3. Generated build output belongs in Actions artifacts, not the repository root.
4. Historical validation/acceptance material is archived under `docs/` or `releases/`.
5. A candidate is not promoted to `main` solely because CI is green when a physical acceptance gate is still outstanding.
6. Do not add speculative Bambu commands. Control features must have a proven backend path and explicit safety semantics.
