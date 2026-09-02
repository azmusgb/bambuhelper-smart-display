# BambuHelper Smart Display

Production evolution for **Waveshare ESP32-S3-Touch-LCD-3.5 (`ws_lcd_350`)** on the BambuHelper v3.8.1 core.

## Current candidate: Smart Home v9.6 Printer Workspace RC1

The current development candidate combines the **v9.4 RC3 recovery foundation**, the **v9.5 smooth-render device experience**, and the **v9.6 Printer Workspace** browser redesign.

### What v9.6 changes

The Printer experience is now organized around the jobs users actually perform:

- **Overview** — printer hero, connection state, progress, temperatures, layer, Wi-Fi and health actions.
- **Connection** — LAN / Cloud identity and connection setup without unrelated display controls mixed in.
- **Display** — touchscreen preview, display presets and the Widget Library.
- **Automation** — chamber-light behavior expressed as readable event rules.
- **Advanced** — original low-level controls remain available so capability is not lost.

The **Widget Library** edits the same physical gauge-slot configuration used by the Waveshare display. Browser preview and device layout therefore use one configuration model instead of diverging into separate systems.

Other v9.6 UX improvements include:

- visual printer and AMS presentation;
- actionable disconnected / setup states;
- one-tap Remote Status, Thermal & Fans, AMS Overview and X2D display presets;
- sticky **Unsaved changes / Save / Discard** behavior;
- clearer separation between everyday controls and advanced configuration.

### Smooth-render device experience

The v9.5 layer reduces visible redraws and screen blipping by updating live regions incrementally instead of repainting entire pages whenever possible.

Home, Workshop, Custom and System retain live printer, AMS, Wi-Fi and system telemetry while avoiding unnecessary full-frame refreshes.

### Recovery and anti-lockout foundation

v9.6 preserves the validated v9.4 RC3 recovery work:

- Safe Mode `/` automatically lands on `/recovery`;
- captive-portal recovery routing;
- triple-reset Safe Mode entry;
- sticky `Waveshare-Recovery-*` access point;
- candidate health watchdog and web-ready promotion gate;
- automatic candidate rollback;
- previous-slot boot;
- selective reset controls;
- application-only recovery OTA;
- WS350 touchscreen lockout guard.

Portal-code authentication remains intentionally disabled in this development candidate so the previous portal lockout failure is not reintroduced before a replacement authentication design is physically validated.

## Validation

GitHub Actions run: **33638721743**

Validated code head: `574bbd5cbc4ad30648e5af03af893da37976ff4e`

Passed gates:

- inherited printer / OTA contracts;
- v9.4 RC3 recovery invariants;
- v9.6 Printer Workspace invariants;
- browser JavaScript syntax;
- exact `ws_lcd_350` PlatformIO build;
- shared `jc3248w535` 320×480 regression build;
- Full-image merge;
- artifact packaging and upload.

### Validated artifacts

- **OTA:** `BambuHelper-ws_lcd_350-v3.8.1-Smart-Home-v9.6-Printer-Workspace-RC1-OTA.bin`
  - SHA-256: `2acd8c73b0d9f76fa4a78a4dc6ea47a361cd022eb2906eb449b61ca813c397f4`
- **Full / USB recovery:** `BambuHelper-ws_lcd_350-v3.8.1-Smart-Home-v9.6-Printer-Workspace-RC1-Full.bin`
  - SHA-256: `fee08462c80d4c10a5fd748a2ba2a1f274106b44b36415265bbbc88c441246f3`
- **Recovery OTA alias:** `WaveshareHome-firmware.bin`
  - SHA-256: `2acd8c73b0d9f76fa4a78a4dc6ea47a361cd022eb2906eb449b61ca813c397f4`

## Release status

**Do not merge/promote yet.** Automated validation is green, but v9.6 RC1 still requires physical WS350 acceptance.

Verify normal boot, touchscreen operation, Printer Workspace behavior, touchscreen-preview/widget synchronization, browser control plane, recovery console, OTA/reboot behavior and absence of portal-code lockout or critical regressions.

See [`PHYSICAL_ACCEPTANCE_V9_6.md`](PHYSICAL_ACCEPTANCE_V9_6.md).

Production site remains on the currently accepted release until the candidate passes hardware acceptance:

<https://bambuhelper-smart-display.netlify.app/>
