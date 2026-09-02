# BambuHelper Smart Display

Production evolution for **Waveshare ESP32-S3-Touch-LCD-3.5 (`ws_lcd_350`)** on the BambuHelper v3.8.1 core.

## Current line: Smart Home v9.7 Interaction & Layout RC1

Smart Home v9.7 is the canonical merged firmware line. It combines:

- **v9.4 RC3 recovery foundation** — Safe Mode, recovery AP, rollback and anti-lockout;
- **v9.6 Printer Workspace** — Overview / Connection / Display / Automation / Advanced;
- **v9.6.1 zero-blip compositor** — PSRAM-backed complete-frame Smart Home page transitions;
- **v9.7 Interaction & Layout** — direct coordinate touch navigation, native Printer/More screens, on-device widget editing and the revised physical/browser layout.

PR **#17** was merged after exact-head CI passed. Superseded PRs **#11** and **#18** were closed without merging duplicate/conflicting history. The useful ambient/preset ideas from #18 are preserved in **#19** for v9.8.

## Physical interaction model

The WS350 now uses real FT6336 touch coordinates rather than treating the whole display as a single “next page” button.

Primary navigation is a persistent 48 px direct-touch footer:

**Home · Printer · Workshop · More**

### Home
Glanceable operational state:

- selected printer and job;
- progress / ETA / layer;
- nozzle, bed, chamber and fan telemetry;
- AMS / filament state;
- Wi-Fi and attention state.

### Printer
Native Smart Home printer workspace:

- job and progress;
- printer-family-aware illustration;
- live thermal telemetry;
- AMS state;
- chamber-light action;
- bridge to the full classic BambuHelper printer detail surface.

### Workshop
Action-oriented workshop view:

- print summary;
- environment;
- material / AMS;
- quick actions.

The redundant Workshop hero/title treatment from older builds is removed.

### More
Secondary destinations and configuration:

- Custom dashboard;
- System;
- Edit Widgets;
- Classic Printer;
- device / recovery status.

## Custom widgets

The physical device has a persistent four-widget fallback deck stored in Smart Hub NVS. Available built-in widgets include:

- Progress
- Nozzle
- Bed
- Chamber
- Wi-Fi
- AMS
- Layer
- ETA
- Fan
- Uptime

Long-press **Custom** to enter on-device edit mode, then tap a tile to cycle its widget. The fallback remains useful when an external Custom feed is unavailable.

## Display stability / zero-blip architecture

Smart Home pages render into a 16-bit PSRAM `LGFX_Sprite` before being committed to the physical ST7796 panel.

- The previous page remains visible while the next page is composed.
- The upstream physical `fillScreen()` pre-clear is suppressed for Smart Home transitions.
- Completed frames are pushed only after composition.
- Live telemetry retains dirty/incremental updates so unchanged regions do not repaint unnecessarily.

This foundation from v9.6.1 remains underneath v9.7.

## Browser Printer Workspace

Printer configuration is organized as:

- **Overview** — printer hero, connection, progress, temperatures, layer, Wi-Fi and actionable health;
- **Connection** — LAN / Cloud identity and setup;
- **Display** — true 320:480 touchscreen preview, presets and Widget Library;
- **Automation** — chamber-light behavior as readable event rules;
- **Advanced** — original low-level controls remain available.

The browser preview now enforces the physical display's **320:480 (2:3)** aspect ratio. Original Remote Monitor Profile / Gauge Layout controls are retained under **Advanced display configuration** rather than competing with the visual editor. Legacy Setup Health is hidden when the modern workspace is active.

Printer imagery adapts for enclosed X/P-style machines, A1 / A1 mini, and H2 / dual-nozzle-style configurations.

## Recovery and anti-lockout

v9.7 preserves the v9.4 RC3 recovery foundation:

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

Portal-code authentication remains intentionally disabled in this development line so the previous portal-lockout failure is not reintroduced.

### Settings-backup security

The final composed v9.7 source verifies that `/settings/export` is safe to expose from recovery:

- `_secretsIncluded=false`;
- Wi-Fi password is omitted/redacted;
- printer LAN access code is omitted/redacted;
- cloud identity is omitted/redacted;
- restoring a redacted backup preserves credentials already provisioned on the device.

## Mac USB auto-detection

Do **not** hard-code macOS device names such as `/dev/cu.usbmodem101`. macOS may renumber the same board after reconnects, resets, hub changes, or reboots.

The repo includes [`scripts/waveshare-usb.sh`](scripts/waveshare-usb.sh), which identifies the board from the USB JTAG/serial VID:PID (`303A:1001`) and then returns the current `/dev/cu.*` path.

Detect the current port:

```bash
PORT="$(bash scripts/waveshare-usb.sh port)"
echo "$PORT"
```

Open the serial monitor without knowing the port number:

```bash
bash scripts/waveshare-usb.sh monitor
```

Inspect all serial devices when diagnosing USB problems:

```bash
bash scripts/waveshare-usb.sh list
```

If more than one matching Espressif USB device is attached, the helper refuses to guess. Select the intended board using its serial from `platformio device list`:

```bash
WAVESHARE_USB_SERIAL='<board-serial>' \
  bash scripts/waveshare-usb.sh monitor
```

The same resolved port can be reused for a deliberate USB flash:

```bash
PORT="$(bash scripts/waveshare-usb.sh port)"
python -m esptool \
  --chip esp32s3 \
  --port "$PORT" \
  --baud 460800 \
  write-flash 0x0 <Full-firmware.bin>
```

Only a **Full** firmware image belongs at flash offset `0x0`. Recovery-page uploads must continue to use the application firmware (`WaveshareHome-firmware.bin`), never `Full.bin`.

## Automated validation

Exact pre-merge head: `5825602f6a56c7b274df6744e3c87c23ccc9be6e`

Merge commit: `239b2ea26b57e456cb7ef4c424b361de3d8d55e3`

GitHub Actions v9.7 run: **33647474577**

Passed:

- full v1 → v9.7 patch composition;
- inherited OTA / printer contracts;
- secret-safe recovery-export verification;
- v9.4 RC3 recovery invariants;
- v9.6.1 zero-blip compositor invariants;
- FT6336 coordinate-navigation contracts;
- Home / Printer / Workshop / More interaction contracts;
- native Printer / More views;
- Custom fallback and on-device widget editing;
- AMS spacing and printer-family imagery checks;
- browser 320:480 preview / legacy-control disclosure / control semantics;
- browser JavaScript syntax;
- exact `ws_lcd_350` PlatformIO build;
- shared `jc3248w535` 320×480 regression build;
- Full-image merge;
- artifact packaging and upload.

The v9.4 RC3 and v9.6.1 compatibility workflows also passed on the final pre-merge head.

## Validated artifacts

- **OTA:** `BambuHelper-ws_lcd_350-v3.8.1-Smart-Home-v9.7-Interaction-Layout-RC1-OTA.bin`
  - SHA-256: `c27c6c1407fcb18d47394b1f1fa87d86b4881c8541b2a5266d1b0a271fc4d673`
- **Full / USB recovery:** `BambuHelper-ws_lcd_350-v3.8.1-Smart-Home-v9.7-Interaction-Layout-RC1-Full.bin`
  - SHA-256: `0c6152c476961b7f40f84409b60224e434e00983d485d3fc23b3f4b653649173`
- **Recovery OTA alias:** `WaveshareHome-firmware.bin`
  - SHA-256: `c27c6c1407fcb18d47394b1f1fa87d86b4881c8541b2a5266d1b0a271fc4d673`

Persistent provenance is stored in [`releases/v9.7-interaction-layout-rc1/`](releases/v9.7-interaction-layout-rc1/).

## Release status

**Merged to `main`; physical acceptance still required before broad OTA promotion.**

The highest-priority physical checks are:

1. FT6336 coordinate orientation and direct footer targets;
2. repeated Home ↔ Printer ↔ Workshop ↔ More transitions with no visible blank/intermediate frame;
3. Custom long-press edit mode and persistence after reboot;
4. native Printer telemetry / light action;
5. recovery page / rollback / settings persistence;
6. 30+ minute soak without freezes, spontaneous reboot or worsening visual corruption.

See [`PHYSICAL_ACCEPTANCE_V9_7.md`](PHYSICAL_ACCEPTANCE_V9_7.md).

Production site remains on the currently accepted firmware until v9.7 completes physical acceptance:

<https://bambuhelper-smart-display.netlify.app/>
