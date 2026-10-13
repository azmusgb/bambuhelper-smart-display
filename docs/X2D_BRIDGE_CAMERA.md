# X2D bridge camera for WS350

Status: **experimental / physical validation required**

This path is a fallback for Bambu X2D camera viewing on the Waveshare ESP32-S3-Touch-LCD-3.5 (`ws_lcd_350`). It keeps the printer camera session and Bambu-specific transport on a Mac running Bambu Studio components, then exposes only a downscaled JPEG frame to the WS350 over the trusted LAN.

It does **not** send video over the WS350 USB cable. USB remains appropriate for power, flashing, and serial diagnostics. Runtime camera frames use Wi-Fi.

## Architecture

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
WS350 firmware
   |
   | JPEG decode in PSRAM
   v
480x270 camera viewport + existing 50 px controls
```

The bridge never returns Bambu `url.txt`, printer UID, access code, credentials, or the raw Bambu camera URI.

## Preconditions

On the Mac:

- Bambu Studio camera works for the X2D.
- The following Bambu Studio components exist:
  - `~/Library/Application Support/BambuStudio/cameratools/bambu_source`
  - `~/Library/Application Support/BambuStudio/cameratools/url.txt`
  - `~/Library/Application Support/BambuStudio/plugins/libBambuSource.dylib`
- `ffmpeg` is installed and on `PATH`.
- Mac and WS350 are on the same trusted LAN, or are connected by an explicitly trusted routed VPN.

Do not publish the bridge port on the public Internet.

## 1. Start the Mac bridge

From the repository root:

```bash
python3 tools/x2d_camera_bridge.py
```

Defaults:

- bind: `0.0.0.0`
- port: `8091`
- JPEG rate: `5 fps`
- JPEG width: `480 px` (height resolves to `270 px` for the X2D 16:9 stream)

Lower-load example:

```bash
python3 tools/x2d_camera_bridge.py --fps 3 --width 480
```

The process owns one Bambu camera session. Stop another manually launched `bambu_source` camera test before starting the bridge.

## 2. Validate the bridge on the Mac

```bash
curl -fsS http://127.0.0.1:8091/x2d/health.json
```

Expected shape:

```json
{"ok":true,"frameSequence":42,"frameAgeMs":120,"frameBytes":48321,"sourceRunning":true,"ffmpegRunning":true,"uptimeSeconds":12,"lastError":null}
```

Open one current frame:

```bash
open http://127.0.0.1:8091/x2d/frame.jpg
```

Find the Mac LAN address:

```bash
MAC_IP="$(ipconfig getifaddr en0)"
printf '%s\n' "$MAC_IP"
```

If the Mac uses a different active interface, substitute that interface rather than guessing an address.

Validate from another LAN device before flashing the WS350:

```text
http://<MAC_IP>:8091/x2d/frame.jpg
```

## 3. Apply the firmware bridge configuration

The existing OS12 media runtime and authenticated media API must already be reconstructed. Apply the bridge after those patches:

```bash
python3 apply_workshop_os12_x2d_bridge_camera.py \
  --repo /path/to/reconstructed/BambuHelper \
  --bridge-url "http://${MAC_IP}:8091/x2d/frame.jpg" \
  --apply
```

The patch accepts only:

- plain `http://`
- a literal private IP address
- an explicit port
- the exact path `/x2d/frame.jpg`
- no username/password
- no query string or fragment

The firmware does not accept a camera URL from an HTTP request. The endpoint is fixed at build time.

## 4. Build and flash the WS350

Use the repository's existing `ws_lcd_350` build/flash flow. Keep USB connected for power, flashing, and serial diagnostics.

A bridge-enabled image must be built from the patched reconstructed source; existing published binaries do not contain the private bridge URL.

## 5. Start the viewer

The bridge viewer has a dedicated authenticated OS12 endpoint:

```text
POST /os12/media/video/start-x2d-bridge
```

It is intentionally separate from the existing fixed demo video route and does not accept arbitrary source parameters.

Existing media controls remain in force:

```text
POST /os12/media/video/pause
POST /os12/media/video/resume
POST /os12/media/stop
GET  /os12/media/status
```

Use the same authenticated session mechanism already required by the OS12 diagnostics API.

## Device-side limits

The WS350 path is intentionally conservative:

- maximum polling cadence: 5 fps
- JPEG maximum: 384 KiB
- frame buffer allocated from PSRAM
- expected frame size: 480x270
- frame must have valid JPEG SOI/EOI markers
- no arbitrary remote media URL
- no public Internet dependency
- current implementation requires `Content-Length`

On any malformed, oversized, unavailable, or stale source frame, the firmware rejects the frame and increments existing video diagnostics rather than rendering untrusted bytes.

## Physical acceptance

This feature is **not accepted** until tested on the real WS350. Record at least the following:

1. Camera view starts from a normal connected state.
2. Frames visibly update; they are not a repeated still image.
3. Device remains touch-responsive while video is running.
4. Pause and resume work without rebooting.
5. Stop returns to normal UI cleanly.
6. Disconnect Mac Wi-Fi while viewing; device remains responsive and recovers when the bridge returns.
7. Stop the Mac bridge process; device remains responsive and status diagnostics record failed/no-frame polls.
8. Restart the bridge and confirm viewing can be started again without rebooting the WS350.
9. Run for at least 30 minutes and check for PSRAM exhaustion, reboot, watchdog reset, or progressive UI slowdown.
10. Confirm normal printer MQTT/control functions remain usable while the camera viewer runs.
11. Confirm no Bambu credential, UID, access code, raw IP, or camera session URI appears in serial logs or exported diagnostics.

If touch stalls materially during bridge failure/recovery, do not promote this implementation. Move HTTP frame acquisition off the foreground media poll path before release.

## Security and privacy

The Mac bridge has no authentication of its own in this experimental version. That is acceptable only on a trusted private LAN/VPN during development. Do not port-forward TCP 8091.

For a persistent deployment, prefer host firewall restrictions to the WS350/VPN subnets and add bridge authentication before treating the service as generally deployable.

The `url.txt` file remains local to the Mac and should never be committed, logged, uploaded, or returned by the bridge.
