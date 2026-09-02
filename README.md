# BambuHelper Smart Display

Production evolution for **Waveshare ESP32-S3-Touch-LCD-3.5 (`ws_lcd_350`)** on the BambuHelper v3.8.1 core.

## Current candidate: Smart Home v9.6.1 Zero-Blip RC2

The current development candidate combines the **v9.4 RC3 recovery foundation**, the **v9.6 Printer Workspace**, and a new **v9.6.1 PSRAM framebuffer compositor** for Smart Home page transitions.

### Why RC2 exists

v9.6 RC1 passed automated validation but **failed physical acceptance**: the WS350 still showed visible blank/repaint blipping when changing Smart Home pages.

The root cause was below the v9.5 page-level partial-render code. BambuHelper's global display loop cleared the physical panel on every screen change before the Smart Home renderer ran. Reducing periodic redraw frequency could not eliminate a blank frame that had already been exposed by the upstream transition path.

RC2 changes that architecture:

- Smart Home pages render into a 16-bit **PSRAM `LGFX_Sprite`** first.
- The existing page stays visible while the replacement page is composed off-screen.
- The completed frame is pushed to the ST7796 only after composition finishes.
- The upstream physical `fillScreen()` pre-clear is suppressed when entering Smart Home pages.
- Live Smart Home updates retain dirty/incremental behavior so unchanged data does not force an unnecessary commit.

The primary RC2 physical test is therefore **Home → Workshop → Custom → System → Home** with no blank/intermediate frame.

### Printer Workspace

The v9.6 Printer experience remains organized around:

- **Overview** — printer hero, connection state, progress, temperatures, layer, Wi-Fi and health actions.
- **Connection** — LAN / Cloud identity and setup.
- **Display** — touchscreen preview, presets and Widget Library.
- **Automation** — chamber-light behavior as readable event rules.
- **Advanced** — original low-level controls remain available.

The Widget Library edits the same physical gauge-slot configuration used by the Waveshare display, keeping browser preview and physical layout on one model.

### Recovery and anti-lockout foundation

v9.6.1 preserves the validated v9.4 RC3 recovery work:

- Safe Mode `/` lands on `/recovery`;
- captive-portal recovery routing;
- triple-reset Safe Mode entry;
- sticky `Waveshare-Recovery-*` access point;
- candidate health watchdog and web-ready promotion gate;
- automatic candidate rollback;
- previous-slot boot;
- selective reset controls;
- application-only recovery OTA;
- WS350 touchscreen lockout guard.

Portal-code authentication remains intentionally disabled in this development candidate so the previous portal lockout failure is not reintroduced.

## Validation

GitHub Actions run: **33641404096**

Validated build head: `1ec8d190be91705f7f0d4bcdfc03ba30b13219eb`

Passed gates:

- complete patch composition;
- inherited printer / OTA contracts;
- v9.4 RC3 recovery invariants;
- PSRAM Smart Home compositor invariant;
- Smart Home physical pre-clear suppression invariant;
- dirty-only frame commit invariant;
- browser JavaScript syntax;
- exact `ws_lcd_350` PlatformIO build;
- shared `jc3248w535` 320×480 regression build;
- Full-image merge;
- artifact packaging and upload.

### Validated artifacts

- **OTA:** `BambuHelper-ws_lcd_350-v3.8.1-Smart-Home-v9.6.1-Zero-Blip-RC2-OTA.bin`
  - SHA-256: `c290bb942662023de00cd622b90a85945af3c08a6d3bf31976ecebb25eefe760`
- **Full / USB recovery:** `BambuHelper-ws_lcd_350-v3.8.1-Smart-Home-v9.6.1-Zero-Blip-RC2-Full.bin`
  - SHA-256: `c19f6e7f144d4ee9b172ee84d56f4a2beed8587148cde6e7fcb5ce446fba6dd0`
- **Recovery OTA alias:** `WaveshareHome-firmware.bin`
  - SHA-256: `c290bb942662023de00cd622b90a85945af3c08a6d3bf31976ecebb25eefe760`

Persistent provenance is stored in [`releases/v9.6.1-zero-blip-rc2/`](releases/v9.6.1-zero-blip-rc2/).

## Release status

**Do not merge/promote yet.** RC1 is rejected for visible blipping. RC2 is the current physical-test candidate.

First verify repeated Smart Home-to-Smart Home transitions. A blip that occurs only when crossing into or out of the legacy Printer renderer should be recorded separately because that boundary is not yet fully framebuffer-composited.

See [`PHYSICAL_ACCEPTANCE_V9_6_1.md`](PHYSICAL_ACCEPTANCE_V9_6_1.md).

Production site remains on the currently accepted release until the candidate passes hardware acceptance:

<https://bambuhelper-smart-display.netlify.app/>
