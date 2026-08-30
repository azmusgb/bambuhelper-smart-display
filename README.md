# BambuHelper Smart Display

Production evolution for **Waveshare ESP32-S3-Touch-LCD-3.5 (`ws_lcd_350`)** on the BambuHelper v3.8.1 core.

## Smart Home v8.3 RC3 — physical-test candidate

RC3 is the current candidate after physical WS350 testing exposed two release-blocking defects in earlier v8.3 builds:

- the System page still performed visible full-frame redraws;
- browser-native Digest authentication produced repeated Safari/iOS sign-in prompts and interfered with the final response of manual OTA uploads.

RC3 keeps the v8 security work but changes the browser interaction model:

- **Portal-code session login:** browse to the device, enter the current 10-character portal code shown on System, then use a random RAM-only `BHSESSION` cookie for the rest of that boot.
- No `WWW-Authenticate` / native Digest browser prompt in station mode.
- Session cookie is `HttpOnly`, `SameSite=Strict`, RAM-only, and invalidated on reboot/logout.
- Same-origin enforcement remains for mutating requests.
- Manual OTA pauses background polling while the ESP32 single-client WebServer owns the upload connection.
- OTA retains browser + device SHA-256 verification and now reports useful HTTP failure details instead of a generic `unexpected response`.
- System full-screen clearing occurs only on page entry; normal telemetry refreshes update in place.

Existing v8 hardening remains:

- insecure OTA `setInsecure()` fallback removed;
- device auto-OTA disabled for `ws_lcd_350` pending publisher-authenticity work;
- Bambu cloud authentication is email-code-only in the local portal;
- Bambu account passwords are not persisted;
- settings backups redact Wi-Fi password, printer LAN access code and cloud identity;
- min-heap, max-block and PSRAM diagnostics are exposed on System.

### Validated RC3 assets

GitHub Actions run: `33302810825`

- **OTA:** `BambuHelper-ws_lcd_350-v3.8.1-Smart-Home-v8.3-RC3-OTA.bin`
  - Size: `2,140,592 bytes`
  - SHA-256: `499a73a43dc27b0ccfea3688115bda11b0ef3d972a80ed6e9e0b0a90d97d67fc`
- **Full / USB recovery:** `BambuHelper-ws_lcd_350-v3.8.1-Smart-Home-v8.3-RC3-Full.bin`
  - Size: `2,206,128 bytes`
  - SHA-256: `21adbffad9854271acb2a93b05fe6e0df7d6e24113276f1bbad7a17e46d8c737`
- Actions artifact ZIP SHA-256: `f10a617bd9cf2628aa6f90d76e7048128fade9cb0c5f25fa23fc582dca758bca`

Validation gates passed:

- patch composition / RC3 invariants;
- browser SHA-256 known-answer test;
- exact `ws_lcd_350` PlatformIO build;
- shared `jc3248w535` 320×480 regression build;
- Full-image merge and packaging.

The artifact was independently unpacked and re-hashed after CI; both firmware hashes match `validation-report-v8.3-rc3.txt`.

**Do not merge/promote yet.** RC3 still requires physical retesting for session login, no repeated Safari prompts, System stability, successful 100% OTA + automatic reboot, printer/AMS telemetry and runtime memory stability. See [`PHYSICAL_ACCEPTANCE_V8_3.md`](PHYSICAL_ACCEPTANCE_V8_3.md).

Production site remains on the currently accepted release until RC3 passes hardware acceptance:

<https://bambuhelper-smart-display.netlify.app/>
