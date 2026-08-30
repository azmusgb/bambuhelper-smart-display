# BambuHelper Smart Display

Production installer for **Waveshare ESP32-S3-Touch-LCD-3.5 (`ws_lcd_350`) + Bambu X2D**.

## Smart Home v7.2 — recommended

v7 fixed the legacy-clock navigation defect. v7.1 redesigned Workshop from physical-display feedback. **v7.2 is the display-stability pass driven by the physical-device video.**

The video confirms the v7.1 layout is physically running: progress hierarchy, detailed AMS cards, X2D thermal cards, and bottom safe area. It also captures a repeating rolling redraw/pulse near 5 Hz. Inspection found Workshop was clearing the entire TFT every time the hub render loop requested a frame.

v7.2 changes:
- Full-screen clear only when entering Workshop.
- Dynamic Workshop repaint minimum interval: 750 ms.
- Clean/unchanged Workshop refresh: 5 seconds.
- Only the dynamic body is cleared between updates; header and bottom navigation remain stable.
- Smart Home identity advances to v7.2.
- v7.1 layout, tap cycle, printer preemption, HMS/error priority, and print-finish priority are preserved.

**Tap cycle:** Home → Workshop → Custom → System → Printer → Home

### Validated v7.2 assets
- Full/USB: 2,208,288 bytes · SHA-256 `ed72f08e4977edd14dc7590a129469405d81e0f565f327402ea5e5190543233a`
- Wi-Fi OTA/app: 2,142,752 bytes · SHA-256 `3eb17d01fb980dbea82e07242bb385ea35b6035b3b57038616b0579f846a95fc`
- Validation run: `33297286792`
- `ws_lcd_350`: PASS
- shared `jc3248w535` regression build: PASS

v7.1, v7, and v6 remain available as rollback profiles.

Production: <https://bambuhelper-smart-display.netlify.app/>

The next release gate is physical comparison of v7.2 against the v7.1 video, specifically whether the visible rolling redraw/pulse is eliminated or materially reduced.
