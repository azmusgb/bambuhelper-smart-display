# BambuHelper Smart Display

Production installer for **Waveshare ESP32-S3-Touch-LCD-3.5 (`ws_lcd_350`) + Bambu X2D**.

## Production firmware

- Profile: **Smart Display v6**
- Base: BambuHelper v3.8.1
- Full image: `firmware/BambuHelper-ws_lcd_350-v3.8.1-Full-smart-display-v6-validated.bin`
- Size: **2,207,040 bytes**
- SHA-256: `82265502dac6b93356ee2ab3d7c4edcaad47bdd7584be85d24ddef348166d5ac`
- Source baseline: `8cb1cbbb6d3c175af91989e8ebe1bbdcbe848ac4`

The release binary is stored directly in this repository. It was recovered from the successful Smart Display v6 validation artifact and verified again for exact size and SHA-256 before being committed to `main`.

`release.json` is the production integrity contract. Netlify runs `python3 build.py`, verifies the committed release asset against that manifest, and publishes it with the installer. The browser then independently downloads the published Full image and verifies its size and SHA-256 with Web Crypto before enabling ESP Web Tools installation.

## Installer workflow

**Hardware → Firmware integrity → Flash → Wi-Fi → Device → X2D → Commission**

The installer includes:

- exact `ws_lcd_350` hardware confirmation
- browser-side firmware integrity verification
- optional USB preflight
- ESP Web Tools flashing
- Improv Serial Wi-Fi guidance
- serial diagnostics and LAN-IP discovery
- fallback-AP and crash/brownout classification
- conservative recovery guidance
- Bambu X2D Cloud + Email-code onboarding
- commissioning receipt and redacted support bundle

## Validation policy

The preserved release binary is the deployment source of truth. A later rebuild from the same source stack may compile successfully yet differ byte-for-byte because embedded/toolchain inputs can drift. For that reason, production does **not** replace the validated release asset merely because a fresh compile succeeds.

The original v6 validation evidence is retained as `validation-report-v6-original.txt`. A manual GitHub workflow validates release metadata and the preserved binary when needed.

## Deployment

The existing Netlify project **`bambuhelper-smart-display`** deploys `main` using `netlify.toml` and publishes `dist/`.

Production URL: <https://bambuhelper-smart-display.netlify.app/>

## Remaining acceptance step

Software, build, integrity, GitHub, and hosted deployment validation are complete. Final acceptance still requires a real desktop Chrome/Edge flash against the physical Waveshare board, followed by Wi-Fi, X2D telemetry, touch/page-cycle, recovery-access, and enclosure checks.
