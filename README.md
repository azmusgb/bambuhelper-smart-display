# BambuHelper Smart Display

Production installer for **Waveshare ESP32-S3-Touch-LCD-3.5 (`ws_lcd_350`) + Bambu X2D**.

## Production firmware

- Profile: Smart Display v6
- Base: BambuHelper v3.8.1
- Full image: `BambuHelper-ws_lcd_350-v3.8.1-Full-smart-display-v6-validated.bin`
- Size: 2,207,040 bytes
- SHA-256: `82265502dac6b93356ee2ab3d7c4edcaad47bdd7584be85d24ddef348166d5ac`
- Source baseline: `8cb1cbbb6d3c175af91989e8ebe1bbdcbe848ac4`

The repository stores the compressed firmware as Base64 chunks under `firmware-parts/`. Netlify runs `python3 build.py`, reconstructs the XZ payload, verifies SHA-256 against `release.json`, then publishes the Full `.bin` with the installer.

## Installer workflow

Hardware → Firmware integrity → Flash → Wi-Fi → Device → X2D → Commission

The browser independently fetches the published Full image and verifies its byte length and SHA-256 with Web Crypto before enabling the ESP Web Tools install control.

## Deployment

The existing Netlify project `bambuhelper-smart-display` publishes `dist/` using `netlify.toml`.
