# BambuHelper Smart Display

Production installer for **Waveshare ESP32-S3-Touch-LCD-3.5 (`ws_lcd_350`) + Bambu X2D**.

## Smart Home v7.1 — recommended

v7 fixed the physical navigation defect where legacy `SCREEN_CLOCK` consumed the first touch. v7.1 is the first visual/UX pass driven by a real photo of the Waveshare running the evolved firmware.

**Tap cycle:** Home → Workshop → Custom → System → Printer → Home

v7.1 improvements:
- Workshop uses the full 320×480 canvas instead of leaving a large dead zone.
- Progress is promoted to a dedicated status band with layer and remaining time.
- AMS tray cards show tray number, remaining percentage, filament type, and active-tray emphasis.
- X2D left/right nozzle, bed, and chamber temperatures are separate readable cards.
- Bottom telemetry clipping is removed by moving data into a safe-area card grid.
- System explicitly identifies `Smart Home v7.1`, `ws_lcd_350`, and UX build `ux71` while retaining upstream BambuHelper `3.8.1` as the base-version axis.
- v7 navigation, printer preemption, HMS/error priority, and print-finish priority remain intact.

### Validated assets
- Full/USB: 2,208,400 bytes · SHA-256 `9f1cd4c103caad2378e2ff35e9562047030a8830ac2985e3ff9ab75f162b73fb`
- Wi-Fi OTA/app: 2,142,864 bytes · SHA-256 `938e0764453b875f5770fa74c64805ea82f721581da0c84dce56db736050037c`
- Validation run: `33295355598`
- `ws_lcd_350`: PASS
- shared `jc3248w535` 320×480 regression build: PASS

v7 and v6 remain available as rollback profiles.

Production: <https://bambuhelper-smart-display.netlify.app/>

The next release gate is physical acceptance of the v7.1 visual layout on the actual Waveshare display.
