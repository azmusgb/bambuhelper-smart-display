# Smart Home v8.3 Physical Acceptance Runbook

Target hardware: **Waveshare ESP32-S3-Touch-LCD-3.5 (`ws_lcd_350`)**  
Firmware base: **BambuHelper v3.8.1**  
Candidate: **Smart Home v8.3 Hardening RC**

This runbook is the final gate between software validation and promotion to production. Do not merge/promote v8.3 solely because CI is green; the real display, touch controller, Wi-Fi path, printer telemetry, and OTA rollback behavior must be exercised on the physical board.

## 1. Select the correct image

Use the binaries from the **latest successful `BambuHelper ws_lcd_350 Smart Home v8 hardening` GitHub Actions run** and verify the SHA-256 values against `validation-report-v8.3.txt` in the same artifact.

- **Existing BambuHelper / Smart Home installation:** use the `...Smart-Home-v8.3-RC-OTA.bin` application image through the device's manual OTA page.
- **First install or recovery only:** use the `...Full-smart-home-v8.3-rc.bin` merged image with the established full-flash/recovery procedure.

Never substitute a binary for another board target.

## 2. Capture pre-upgrade evidence

Before flashing:

- Record the currently installed Smart Home/BambuHelper version.
- Export settings if desired. Treat older exports as potentially secret-bearing; v8.3 exports are intentionally redacted.
- Record printer connection mode (LAN or Cloud), configured printer(s), and AMS visibility.
- Photograph or record the current Home / Workshop / System screens for visual comparison.

## 3. OTA upgrade acceptance

For an already-running device:

1. Open the device portal on the trusted LAN.
2. Confirm the station-mode portal requires Digest authentication.
3. Read the current per-boot admin code from the physical **System** screen and authenticate as `admin`.
4. Select the v8.3 OTA image.
5. Confirm the browser computes and submits SHA-256 before upload.
6. Start the update and allow the device to reboot normally.
7. Do not power-cycle during image write or first reboot.

**PASS:** update completes, device reboots, display initializes, touch works, and System screen reports **Smart Home v8.3**.

## 4. Display and touch acceptance

Verify on the actual 320×480 panel:

- No boot loop, white screen, inverted display, or persistent corruption.
- Touch coordinates map correctly across all screen regions.
- Home → Workshop → Custom → System → Printer navigation remains usable.
- Workshop no longer exhibits the prior rapid full-screen rolling redraw/pulse behavior.
- Text remains inside the bezel-safe area.
- AMS cards, progress, temperatures, ETA, and page/footer elements do not overlap.
- A print-state/HMS priority screen can still preempt Smart Home when applicable.

**PASS:** no visible regression from v7.2 display-stability behavior and no touch dead zones.

## 5. Portal security acceptance

While connected in normal station mode:

- Unauthenticated access to management/configuration routes is rejected.
- Correct `admin` + current on-device code grants access.
- Reboot the device and verify the admin code changes.
- Mutating requests from the normal portal succeed after authentication.
- A mutation without accepted same-origin provenance is rejected.
- Captive-portal/AP onboarding remains usable when intentionally placed into onboarding mode.

**PASS:** management is protected in station mode without breaking first-boot recovery/onboarding.

## 6. Bambu connectivity acceptance

### LAN mode

- Connect to the P1/X/A-series printer using the configured LAN credentials.
- Confirm printer state, progress, nozzle/bed/chamber telemetry, current layer, ETA, and AMS data populate.
- Observe at least one reconnect/recovery cycle if practical (for example, briefly remove Wi-Fi and restore it).

### Cloud mode, if used

- Confirm the portal offers **email-code sign-in only**.
- Verify the portal does not request or transmit the long-lived Bambu account password.
- Complete Bambu email-code authentication.
- Verify cloud token operation after a normal reboot.

**PASS:** required printer telemetry works and cloud authentication does not regress to password mode.

## 7. Secret-safe backup acceptance

Export settings from v8.3 and inspect the JSON.

The export must:

- retain non-secret configuration such as Wi-Fi SSID and printer metadata;
- report `_secretsIncluded=false`;
- mark Wi-Fi password, printer LAN access code, and cloud identity as redacted;
- contain no usable Wi-Fi password, LAN access code, or Bambu account password.

Then import that redacted backup onto the already provisioned device.

**PASS:** existing secrets remain intact and the printer reconnects without requiring them to be re-entered.

A restore onto a fresh/unprovisioned device is expected to require Wi-Fi and printer credentials again.

## 8. Runtime health acceptance

Leave the device running for a meaningful observation window, ideally including an active print.

Record from the System/diagnostics surface:

- free heap;
- minimum free heap;
- maximum allocatable heap block;
- free PSRAM;
- Wi-Fi RSSI;
- reconnect behavior.

Watch for:

- steady heap decline;
- repeated TLS/MQTT allocation failures;
- spontaneous reboot/watchdog reset;
- touch/display lock-up;
- AMS state disappearing after partial updates.

**PASS:** memory remains bounded/stable and no unexplained reset or UI lockup occurs.

## 9. OTA failure and rollback acceptance

Where practical, validate recovery behavior without intentionally corrupting the device:

- Confirm an upload with an incorrect/missing SHA-256 is rejected before activation.
- Confirm the updater does **not** downgrade to insecure TLS (`setInsecure()` fallback is removed by contract).
- Confirm the normal rollback/recovery path remains available if the new slot fails boot health checks.
- Keep the last physically accepted Full image available before testing.

## 10. Promotion decision

Promote v8.3 only when all required categories are PASS:

| Gate | Result |
|---|---|
| Boot / display / touch | PENDING |
| Smart Home navigation / redraw stability | PENDING |
| Digest-auth portal / rotating admin code | PENDING |
| Same-origin mutation protection | PENDING |
| Local printer + AMS telemetry | PENDING |
| Email-code cloud auth, if used | PENDING / N/A |
| Secret-safe export / restore | PENDING |
| Manual OTA SHA-256 | PENDING |
| Runtime heap / PSRAM stability | PENDING |
| Rollback / recovery readiness | PENDING |

### Acceptance evidence

For each failed item, capture the screen/page, exact action, expected result, actual result, and whether the device recovered without reflashing. Attach that evidence to PR #2 before changing the promotion status.

**Release state until this checklist is complete: `SOFTWARE-VALIDATED / PHYSICAL-ACCEPTANCE-PENDING`.**
