# Workshop OS v11.27 Companion Link RC1

## Purpose

v11.27 evolves the first device-hosted Companion Web build into a lower-churn, bidirectional local link between iPhone and Workshop OS.

## One state envelope

The phone no longer needs separate `/status`, `/printer/power/status`, and heartbeat traffic on every refresh. `GET /companion/state?slot=N` is authenticated and returns one compact envelope containing:

- phone presence and selected printer slot;
- device uptime, free heap, free/total PSRAM, Wi-Fi RSSI and local IP;
- printer configured/connected state, g-code state, progress, remaining minutes, temperatures, layer count, job name, chamber-light state and door state;
- mapped smart-plug availability, reachability, relay inference and live watts;
- latest phone-capture metadata.

Receiving a valid authenticated state request also refreshes Web Companion phone presence. The older heartbeat route remains for compatibility, but the v11.27 page does not need it.

## Phone photo transfer

The iPhone Companion can now take/select an image and send a display-scale copy to the Waveshare over the existing authenticated LAN session.

The browser:

1. previews the selected image locally;
2. decodes it on the iPhone;
3. resizes the longest dimension to at most 480 px;
4. JPEG-encodes it with adaptive quality;
5. refuses to send more than 250 KiB;
6. uploads the JPEG as multipart form data to `/companion/capture`.

Workshop OS:

- requires the normal portal/session cookie and same-origin mutation check;
- accepts JPEG only;
- hard-limits a capture to 256 KiB;
- allocates the upload buffer from PSRAM;
- checks JPEG SOI/EOI markers before publishing;
- keeps only the latest successful capture;
- exposes the published pointer through `companionWebGetLatestCapture()` for a later physical viewer;
- never writes captures to flash/NVS/filesystem;
- clears the capture on request or automatically on reboot.

This creates the phone → Waveshare image/data path without adding cloud storage or flash wear.

## Existing command authority

Printer and power actions still use the existing Workshop OS endpoints and their existing deferred/state-guarded backends:

- `POST /light/set`
- `POST /printer/control`
- `POST /printer/power`

v11.27 does not add BLE printer authority. BLE remains orchestration/presence only.

## Interaction hardening

The Companion page also prevents a completed hold-to-power-off gesture from falling through into a second synthetic click action on mobile Safari.

## Physical acceptance additions

In addition to the v11.26 acceptance matrix, verify on a real WS350 + iPhone:

- `/companion/state` stays responsive while printing;
- visible polling does not disturb MQTT, audio, BLE, touch, or smart-plug polling;
- device heap/PSRAM remain healthy over an extended session;
- iPhone capture resize + JPEG upload works from Safari and Home Screen launch;
- oversize/non-JPEG uploads fail closed;
- upload cancellation leaves the previous successful image intact;
- clear removes the volatile image;
- image disappears after reboot;
- session expiry and cross-origin upload attempts are rejected;
- active-print power-off still requires the stronger confirmation token.

## Promotion boundary

This remains a stacked hardware candidate. CI proves deterministic reconstruction, contracts, JavaScript syntax and native firmware builds; real-device acceptance is still required before promotion.
