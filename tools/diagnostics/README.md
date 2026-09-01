# Waveshare / ESP32 Diagnostics Toolkit

Purpose: collect repeatable evidence when firmware boots, crashes, resets, or behaves unexpectedly.

## Quick capture

```bash
./tools/diagnostics/collect_diagnostics.sh
```

The toolkit captures:

- connected ESP32 serial ports
- macOS environment information
- ESP-IDF version
- git revision
- recent serial boot output
- build artifacts when available

Output is written to `diagnostics/runs/<timestamp>`.

## Current recovery workflow

1. Run diagnostics before flashing again.
2. Preserve the generated folder.
3. Review:
   - `serial.log`
   - `environment.txt`
   - `firmware.txt`

This prevents losing the evidence needed to diagnose boot loops.
