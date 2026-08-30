# BambuHelper Smart Display

Firmware evolution and installer project for **Waveshare ESP32-S3-Touch-LCD-3.5 (`ws_lcd_350`)** built on BambuHelper v3.8.1.

## Release channels

### Smart Home v8.3 — software-validated release candidate

v8.3 keeps the mature BambuHelper printer / MQTT / AMS / HMS core and hardens the management, credential, backup, OTA, and diagnostics surfaces.

Key changes:

- Station-mode management portal protected with **Digest authentication**.
- Per-boot **10-character admin code** displayed on the physical System screen.
- Same-origin enforcement for browser mutations and POST semantics for destructive actions.
- Automatic OTA no longer retries with `setInsecure()` after certificate validation failure.
- `ws_lcd_350` device-initiated automatic OTA is disabled pending a stronger publisher-authenticity scheme.
- Manual OTA requires browser + device **SHA-256 transfer-integrity verification**.
- Bambu account passwords are not persisted; legacy stored password material is erased.
- Local Bambu cloud sign-in is **email-code only**; the portal does not serialize the account password or remember-password field.
- Settings backups are **secret-safe**: Wi-Fi password, printer LAN access code, and cloud identity are redacted, while restore preserves already-provisioned secrets.
- System diagnostics add minimum free heap, maximum allocatable heap block, PSRAM visibility, and explicit **Smart Home v8.3** provenance.
- v7.2 display-stability behavior and Home → Workshop → Custom → System → Printer navigation are preserved.

The candidate is gated by GitHub Actions for patch-stack composition, security contracts, browser SHA-256, exact `ws_lcd_350` compilation, a shared 320×480 regression build, and Full-image generation.

**Release state:** `SOFTWARE-VALIDATED / PHYSICAL-ACCEPTANCE-PENDING`

See [`PHYSICAL_ACCEPTANCE_V8_3.md`](PHYSICAL_ACCEPTANCE_V8_3.md) before promotion or production deployment.

### Smart Home v7.2 — current physically safer rollback baseline

v7 fixed the legacy-clock navigation defect. v7.1 redesigned Workshop from physical-display feedback. v7.2 is the display-stability pass intended to reduce the repeating rolling redraw/pulse seen on the physical screen.

v7.2 changes:

- Full-screen clear only when entering Workshop.
- Dynamic Workshop repaint minimum interval: 750 ms.
- Clean/unchanged Workshop refresh: 5 seconds.
- Only the dynamic body is cleared between updates; header and bottom navigation remain stable.
- Smart Home identity advances to v7.2.
- v7.1 layout, tap cycle, printer preemption, HMS/error priority, and print-finish priority are preserved.

**Tap cycle:** Home → Workshop → Custom → System → Printer → Home

Validated v7.2 assets:

- Full/USB: 2,208,288 bytes · SHA-256 `ed72f08e4977edd14dc7590a129469405d81e0f565f327402ea5e5190543233a`
- Wi-Fi OTA/app: 2,142,752 bytes · SHA-256 `3eb17d01fb980dbea82e07242bb385ea35b6035b3b57038616b0579f846a95fc`
- Validation run: `33297286792`
- `ws_lcd_350`: PASS
- shared `jc3248w535` regression build: PASS

v7.1, v7, and v6 remain available as rollback profiles.

Production installer: <https://bambuhelper-smart-display.netlify.app/>

## Promotion policy

A green firmware build is necessary but not sufficient. New candidates remain off the production installer until the physical Waveshare board passes boot/display/touch, printer/AMS telemetry, portal security, backup/restore, OTA integrity, rollback readiness, and sustained heap/PSRAM checks.
