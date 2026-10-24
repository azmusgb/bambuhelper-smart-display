# BambuHelper Smart Display — Workshop OS

Local-first Workshop OS for the **Waveshare ESP32-S3-Touch-LCD-3.5 (`ws_lcd_350`)**, built on the BambuHelper v3.8.1 core.

Workshop OS owns the WS350 firmware, touchscreen UX, printer/device controls, hardware integrations, audio/microphone/BLE, networking, OTA/recovery behavior, and physical acceptance. **Bambuddy (on the household Pi) holds the filament inventory: spools, quantities, AMS placement and projects.** Filament Inventory (`azmusgb/filamentinventory`) was retired on 24 Oct 2026; see `docs/REPOSITORY_BOUNDARIES.md`.

## Current release state

Workshop OS deliberately keeps accepted source, merged-but-unaccepted source, static distribution, device OTA publication, and hardware candidates separate. A green build is not physical acceptance, and physical acceptance is not automatically stable promotion.

| Surface | Current state | Meaning |
| --- | --- | --- |
| accepted source baseline | **Workshop OS v11.22 Display Expert RC1** | Last physically accepted source baseline; remains authoritative for accepted/stable state. |
| `main` | **Workshop OS 12.3.8 Review Fixes — merged, physical acceptance pending** | `main` at `ffebf46263b367932e479024dca94564c39f3717`: 12.3.7 (`fba92a7`: 12.3.6 WS350 touch and audio fit #194, Printer > Camera #195, `/hub/show printer-camera` #196) plus #197, the fixes from the 12.3.6 review: same-origin sign-in and a separate code-key lock-out, armed Local AI prompts, a press acts only on the control it went down on, no `/audio/mic/echo`, a DC-free microphone meter and a gated recording buffer. 12.3.8 has passed exact-head CI. Its exact CI image is not recorded as installed here; the 19 Oct 2026 captures show a 12.3.8 build on the WS350. |
| active candidate | **Workshop OS 12.3.9 Glance and Legibility** | Candidate PR #198, branch `fix/ws350-glance-legibility-12-3-9`. Touchscreen fixes from a UX critique of the 12.3.8 captures, judged at arm's length: a 48 px print percentage with time left and the done-at time beside it on Home and Printer, one done-at time on every screen, 14 px row values, button labels and toasts (10 px before), a 19 px calm status line, grey not amber for not-set-up reasons, a visible off-switch outline, and Printer > Camera without its control row (the picture runs to the tab bar, Pause in the header). Re-test with `scripts/accept_os12_retest_12_3_9.py`. Exact-head CI and physical WS350 acceptance required. |
| tested OS12 candidate | **50123320544fcf690d11a9e7ba82af00e836f138** | Exact PR #194 CI firmware (12.3.6, same source tree as main `d24347a`; SHA-256 `1d0145ae…10c7fad5`) installed on the WS350 by signed-in OTA. The owner's re-test of the 12.3.5 failures (`scripts/accept_os12_retest_12_3_6.py`) passed on it. Whole-device sensory acceptance and a recovery round-trip are not recorded. The unattended acceptance script last passed on 12.3.5 main `17108d1`. Since then the WS350 has been USB-flashed for testing with a 12.3.7 development build (`5a206a0` plus #196 and the X2D overlays); that build is not a recorded candidate. |
| main source commit | **ffebf46263b367932e479024dca94564c39f3717** | Merged `main` (12.3.8). Its CI image is `os12-ux-ws350-ffebf46…` (run 39340041154, SHA-256 `b2e74b60…e098e8e1`). The 12.3.7 main image `os12-ux-ws350-fba92a7…` (run 39338893230, SHA-256 `584a1b1f…67c6d583`) and the 12.3.6 main image `os12-ux-ws350-d24347a…` (run 39328584313, SHA-256 `e4a053e0…3aa7fdfc3`) are earlier mains; the 12.3.6 one differs from the installed `5012332` image only in the embedded source SHA and image checksum (102 bytes, same size). |
| static installer and device Stable | **Workshop OS 12.7.1** | Full + OTA (`firmware/Workshop-OS-12.7.1-*`). The OTA image is the exact CI build of main `06a49e1`, installed on the WS350 and passed by `accept_os12_unattended.py` on 20 Oct 2026; the owner waived the interactive re-test. |
| static rollback | **Workshop OS 12.4.4**, then **v11.19.1** and **Smart Home v7.2** | Previous installer release first; the older pairs stay for recovery. |
| published device OTA candidate | **Workshop OS v11.26 UI11 Cupertino** | Existing published, unaccepted OTA candidate in `releases/device-update.json`; unchanged by PR #122. |

`releases/current.json` is authoritative for the accepted source baseline, any active source candidate, merged-but-unaccepted `main` state, and the conservative static download channel. `releases/device-update.json` is the versioned device-facing OTA discovery contract and is not automatically advanced by a source merge.

## Workshop OS v11.28 UI13 Appliance Settings

PR **#109** is the frozen UI13 hardware-facing source candidate underneath the OS12 platform branch. Its goal is not another settings menu; it is a coherent appliance UI for a 480×320 touch device.

Primary navigation is:

`Home · Printer · Tools · Settings`

Settings is reduced to five user-facing destinations:

- **Display & Appearance** — brightness, standby, night behavior, and after-print display behavior.
- **Sounds & Alerts** — event/touch sounds, cooled-bed notification, printer-error policy, and alert signals.
- **Network** — everyday connectivity, local discovery, startup address visibility, and Local Portal handoff.
- **Printer & Power** — printer availability, smart-plug readiness, and guarded automatic power-off.
- **System** — device health, connectivity summary, Date & Time, Software Update, Diagnostics, and Local Portal.

Advanced network configuration, credentials, wiring, drivers, polling, raw diagnostics, and recovery/service mechanics do not belong in normal touchscreen Settings.

### Product-finish rules

UI13 uses a restrained dark system palette and semantic state treatment:

- blue = normal interaction;
- green = healthy / available;
- orange = offline / degraded / setup required;
- red = true fault / destructive meaning;
- muted = unknown / unavailable information.

Routine landscape controls expose at least a **48 px** touch target. Back and primary actions are explicit. Numeric/preset values use visible decrement/increment controls. Routine Settings navigation does not depend on hidden tap/hold gestures.

Copy is written as product language rather than implementation language. The touchscreen presents what a person needs while standing at the printer; advanced administration stays in the authenticated Local Portal.

## Workshop OS 12 merged source state

Workshop OS 12.0.0 is present on `main` under the documented merged-but-unaccepted exception. The exact tested firmware source is `48ddd5819e578bc85a391d9607653e71ca5c6aa2`, produced by the OS12 UX Architecture candidate build from merged `main`. Guarded installation, exact runtime identity, 15/15 unattended native-view acceptance, unattended media lifecycle checks, and automatic evidence validation passed on the current exact candidate. The Network status-fit and Video Viewer visible-state corrections are included. This is **not** yet an accepted/stable promotion; the prior physically accepted v11.22 source remains the accepted baseline until the remaining physical sensory checks and an exact-candidate full-image recovery round-trip are explicitly completed.

For a WS350 that is physically attached to a Mac but still running pre-OS12 firmware, the guarded bootstrap helper is:

```bash
bash scripts/bootstrap_ws350_os12_usb_macos.sh
```

The default invocation is non-mutating: it builds exact local source, resolves the ESP32-S3 USB port, captures recovery metadata, and byte-compares the live partition table with the expected Workshop OS 16 MB layout. After confirming the actual printer is idle, the guarded mutation form is:

```bash
bash scripts/bootstrap_ws350_os12_usb_macos.sh --flash --confirm-printer-idle
```

A partition mismatch stops the operation and must be handled through the approved recovery/full-image migration path rather than forced.

Once OS12 is running, ordinary device-native online updates are manifest-bound GitHub OTA application updates. The authenticated update status API reports both the running release version and exact embedded source SHA so post-reboot acceptance can verify identity, not merely a version label.

## Safety, truth, and security boundaries

Workshop OS must not invent physical or inventory facts.

- Unknown inventory state remains **Unknown**.
- AMS color/material telemetry does not identify a Filament Inventory spool by similarity.
- Workshop OS does not fabricate spool identity, owner, quantity, location, printer assignment, feeder/AMS placement, or measured weight.
- Printer controls fail closed when required printer connectivity/state is unavailable.
- Stop and other destructive actions retain deliberate guards and visible feedback.
- Automatic printer power-off requires explicit enable confirmation and a valid mapped smart plug.
- The rotating Local Portal access code is shown only in the deliberate Local Portal view, not on normal System status screens.
- Session validation and same-origin mutation protection remain authoritative. Same-origin is proven only by the browser `Origin`/`Referer` headers; no client-chosen marker header counts. (12.0.0 `main` ships a code-free portal; 12.0.1 restores sign-in.)

## Update and recovery model

For a normal existing-device update, use the **application/OTA image** on a compatible Workshop OS partition layout.

A **Full** image is a recovery/service artifact and belongs at flash offset `0x0`. Waveshare Home and Workshop OS use incompatible partition layouts; cross-line migration is therefore a deliberate full-image recovery procedure, never an OTA shortcut.

OS12 implements device-native GitHub OTA through one normalized `UpdateService`: certificate-validated manifest fetch, stable/candidate selection, board/authority/path validation, exact byte-count and SHA-256 verification, inactive application partition staging, and guarded activation/reboot. The historical arbitrary-URL `/ota/auto` path is not an active OS12 update authority.

## Validation and acceptance

Firmware is reconstructed deterministically from pinned upstream BambuHelper commit `8cb1cbbb6d3c175af91989e8ebe1bbdcbe848ac4` plus the versioned Workshop OS patch stack.

Hardware-facing source changes are expected to pass repository validation, deterministic reconstruction, product/interaction contracts, native/shared-target builds, release coordination, exact artifact identity capture, and applicable unattended runtime/hardware checks before merge. Routine merge testing must not depend on operator `y/n/u` prompts.

A merge is not an acceptance promotion. Sensory evidence that cannot be established honestly by automation—real LCD appearance, finger touch feel/responsiveness, speaker quality, microphone intelligibility—and recovery/rollback exercises when due remain explicit physical-promotion evidence.

The lifecycle is kept explicit:

`implemented → built → tested → runtime validated → merged-unaccepted → physically validated → accepted → stable`

Automation may establish objective machine-observable behavior, but it must not manufacture sensory physical truth.

## Repository map

- `apply_smart_home_*.py` — inherited deterministic firmware evolution inputs.
- `apply_workshop_os_*.py` — Workshop OS source evolution and product-finish layers.
- `apply_workshop_os12_*.py` — OS12 platform/control/security/update reconstruction layers.
- `.bambuhelper-validation/` — verified patch payloads required by selected loaders.
- `.github/workflows/firmware-candidate.yml` — reusable firmware/hardware gate.
- `.github/workflows/ui13-appliance-settings.yml` — UI13 reconstruction, product-finish, native build, and exact artifact gate.
- `.github/workflows/os12-platform-bridge.yml` — OS12 reconstruction/build and exact-head OTA candidate artifact.
- `.github/workflows/validate.yml` — repository validation.
- `.github/workflows/release-gate.yml` — release metadata validation and conditional merge-gate coordination.
- `.github/workflows/release-main.yml` — accepted static-installer integrity gate.
- `releases/current.json` — accepted-source / active-source-candidate / `main` / static-channel state.
- `releases/device-update.json` — minimal versioned device-facing OTA discovery contract.
- `release.json` — conservative static download/rollback catalog.
- `scripts/bootstrap_ws350_os12_usb_macos.sh` — guarded same-layout Mac USB bootstrap.
- `scripts/accept_os12_portal_runtime.py` — real-device portal runtime acceptance helper.
- `scripts/accept_os12_update_runtime.py` — real-device GitHub update/runtime identity acceptance helper.
- `scripts/capture-ws350-views.zsh` — authenticated credential-safe physical framebuffer capture.
- `docs/` — architecture, safety, UX, acceptance, and release documentation.
- `docs/archive/` and `releases/archive/` — historical provenance only.

## Repository discipline

- The last physically accepted source remains authoritative for accepted/stable state until a later source earns promotion.
- Hardware-facing changes require exact-head CI and applicable unattended objective hardware evidence before merge; a merged candidate remains `merged-unaccepted` until physical promotion evidence is completed.
- Generated PlatformIO output, local capture bundles, credentials, and ad-hoc reports stay out of source control.
- Physical framebuffer evidence redacts the Local Portal credential before retained output is written.
- Printer configuration/settings exports are excluded from credential-safe capture bundles.
- Static firmware retention remains bounded to the published pair plus one rollback pair.
- Upstream synchronization is a deliberate candidate; the accepted source line is never silently repinned.

## License and attribution

Original Workshop OS contributions are provided under the **MIT License** in `LICENSE`.

Workshop OS is derived from **Keralots/BambuHelper**; exact attribution and third-party boundaries are recorded in `NOTICE.md`.
