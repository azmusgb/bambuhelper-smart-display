# BambuHelper Smart Display

Production installer for **Waveshare ESP32-S3-Touch-LCD-3.5 (`ws_lcd_350`) + Bambu X2D**.

## Smart Home v7 — recommended
Physical testing of v6 exposed a UX defect: the legacy `SCREEN_CLOCK` consumed the first touch as wake, hiding Smart Display navigation. v7 fixes the runtime integration.

**Tap cycle:** Home → Workshop → Custom → System → Printer → Home

- Smart Home replaces the legacy idle clock when Smart Display is enabled.
- Upgraded devices on the old clock wake directly to Smart Home.
- Idle Home yields immediately when printing starts.
- Home/Workshop/Custom/System show visible `TAP > ...` hints.
- HMS/error and print-finish priority are preserved.
- Explicit display-off behavior remains respected.

v7: 2,207,472 bytes · SHA-256 `c659d4acfd3c6642baa789d6d7b64a9b77173a2f92be90a90fa71b48d4dbbfc7` · validation run `33293416153` · `ws_lcd_350` PASS · `jc3248w535` regression PASS.

v6 rollback: 2,207,040 bytes · SHA-256 `82265502dac6b93356ee2ab3d7c4edcaad47bdd7584be85d24ddef348166d5ac`.

Production: <https://bambuhelper-smart-display.netlify.app/>

v7 still requires physical acceptance on the Waveshare board: idle Home, repeated tap cycle, print preemption, X2D telemetry, power cycling, and enclosure access.
