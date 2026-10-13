# X2D bridge camera for WS350

Status: **experimental / physical validation required**

This path is a fallback for Bambu X2D camera viewing on the Waveshare ESP32-S3-Touch-LCD-3.5 (`ws_lcd_350`). It keeps the Bambu/TUTK camera session on a Mac and sends only a small JPEG frame to the WS350 over the trusted LAN.

USB remains the power, flashing, and serial-diagnostics connection. Runtime camera frames use Wi-Fi.

## Architectural boundary

The canonical Workshop OS 12 media backend under `firmware/platform/media/` remains unchanged and transport-agnostic. In particular, the canonical `Ws350MediaBackend` does **not** own `HTTPClient`/`WiFiClient` networking.

X2D networking is installed only by `apply_workshop_os12_x2d_bridge_camera.py` into a **reconstructed firmware tree** for this hardware experiment. That keeps the accepted OS12 media contract intact while allowing the real WS350 to be tested before deciding whether the transport deserves a permanent service abstraction.

```text
Bambu X2D
   |
   | Bambu/TUTK camera session on LAN
   v
Bambu Studio bambu_source + libBambuSource.dylib (Mac)
   |
   | raw H.264 1920x1080 ~30 fps
   v
FFmpeg (Mac)
   |
   | 480x270 JPEG, default 5 fps
   v
tools/x2d_camera_bridge.py
   |
   | HTTP GET /x2d/frame.jpg on trusted LAN
   v
reconstructed WS350 image + experimental X2D overlay
   |
   | JPEG in PSRAM
   v
480x270 camera viewport + existing controls
```

The bridge never returns Bambu `url.txt`, printer UID, access code, credentials, or the raw Bambu camera URI.

## Preconditions

On the Mac:

- Bambu Studio camera works for the X2D.
- These Bambu Studio components exist:
  - `~/Library/Application Support/BambuStudio/cameratools/bambu_source`
  - `~/Library/Application Support/BambuStudio/cameratools/url.txt`
  - `~/Library/Application Support/BambuStudio/plugins/libBambuSource.dylib`
- `ffmpeg` is installed and on `PATH`.
- Mac and WS350 are on the same trusted LAN, or on an explicitly trusted routed VPN.

Do not expose the bridge port to the public Internet.

## 1. Start the Mac bridge

From the repository root:

```bash
python3 tools/x2d_camera_bridge.py
```

Defaults:

- bind: `0.0.0.0`
- port: `8091`
- JPEG rate: `5 fps`
- JPEG width: `480 px` (`270 px` high for the 16:9 X2D stream)

Lower-load example:

```bash
python3 tools/x2d_camera_bridge.py --fps 3 --width 480
```

The process owns one Bambu camera session. Stop other manually launched `bambu_source` camera tests first.

## 2. Validate the bridge

```bash
curl -fsS http://127.0.0.1:8091/x2d/health.json
open http://127.0.0.1:8091/x2d/frame.jpg
```

A healthy response resembles:

```json
{"ok":true,"frameSequence":42,"frameAgeMs":120,"frameBytes":48321,"sourceRunning":true,"ffmpegRunning":true,"uptimeSeconds":12,"lastError":null}
```

Find the active Mac LAN address. For Wi-Fi this is commonly:

```bash
MAC_IP="$(ipconfig getifaddr en0)"
printf '%s\n' "$MAC_IP"
```

If `en0` is not the active interface, identify the correct interface rather than guessing an address.

Validate from another LAN device:

```text
http://<MAC_IP>:8091/x2d/frame.jpg
```

## 3. Reconstruct canonical OS12 first

Run the repository's normal OS12 reconstruction sequence, including the canonical media runtime and authenticated media API. At this point the reconstructed `src/ws350_media_backend.cpp` should still match the accepted transport-agnostic design.

Do **not** edit `firmware/platform/media/ws350_media_backend.*` to add the bridge.

## 4. Apply the experimental X2D overlay

After canonical reconstruction:

```bash
python3 apply_workshop_os12_x2d_bridge_camera.py \
  --repo /path/to/reconstructed/BambuHelper \
  --bridge-url "http://${MAC_IP}:8091/x2d/frame.jpg" \
  --apply
```

The overlay modifies only the reconstructed copy. It:

- adds the fixed `x2d-bridge` media source to that reconstructed image,
- adds bounded HTTP/JPEG acquisition there,
- allocates the frame in PSRAM,
- validates JPEG SOI/EOI markers and the 384 KiB limit,
- adds authenticated `POST /os12/media/video/start-x2d-bridge`.

The supplied bridge URL must be:

- plain `http://`,
- a literal private IP address,
- an explicit port,
- exactly `/x2d/frame.jpg`,
- without username, password, query string, or fragment.

The firmware does not accept a camera URL from an HTTP request.

## 5. Build and flash the WS350

Use the repository's normal `ws_lcd_350` build/flash flow. Keep USB attached for power, flashing, and serial diagnostics.

An already-published firmware image will not contain this experimental overlay or its private bridge endpoint.

## 6. Start and control the viewer

Use the existing authenticated OS12 session mechanism.

```text
POST /os12/media/video/start-x2d-bridge
POST /os12/media/video/pause
POST /os12/media/video/resume
POST /os12/media/stop
GET  /os12/media/status
```

The X2D start route is fixed-source only and accepts no arbitrary URL/path argument.

## Device-side limits

The experimental overlay is deliberately conservative:

- maximum polling cadence: 5 fps,
- JPEG maximum: 384 KiB,
- PSRAM frame allocation,
- expected frame dimensions: 480x270,
- JPEG SOI/EOI validation,
- bounded connect/read timeouts,
- no public Internet dependency,
- current implementation requires `Content-Length`.

Malformed, oversized, unavailable, or incomplete frames are rejected and counted as no-frame polls.

## Physical acceptance

Do not promote this overlay into the canonical media architecture until the real WS350 passes all of the following:

1. Camera view starts from a normal connected state.
2. Frames visibly update and are not a repeated still image.
3. Touch remains responsive while the viewer runs.
4. Pause and resume work without rebooting.
5. Stop returns to the normal UI cleanly.
6. Disconnect Mac Wi-Fi while viewing; the WS350 remains responsive.
7. Stop the Mac bridge; failed/no-frame diagnostics advance without watchdog/reset behavior.
8. Restart the bridge and start viewing again without rebooting the WS350.
9. Run for at least 30 minutes with no PSRAM exhaustion, reboot, watchdog reset, or progressive UI slowdown.
10. Normal printer MQTT/control functions remain usable while viewing.
11. No Bambu credential, UID, access code, raw camera URI, or sensitive session data appears in serial logs or exported diagnostics.

If touch materially stalls during bridge failure or recovery, this overlay is not acceptable. The next design must move frame acquisition out of the foreground media poll into a dedicated asynchronous transport/service boundary.

## Security and privacy

The development bridge has no HTTP authentication of its own. Use it only on a trusted private LAN/VPN and do not port-forward TCP 8091.

For persistent deployment, restrict the host firewall to the WS350/VPN subnet and add bridge authentication before treating the service as generally deployable.

`url.txt` remains local to the Mac and must never be committed, logged, uploaded, or returned by the bridge.
