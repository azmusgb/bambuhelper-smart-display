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
   | 384x216 JPEG, default 5 fps
   v
tools/x2d_camera_bridge.py
   |
   | HTTP GET /x2d/frame.jpg on trusted LAN
   v
reconstructed WS350 image + experimental X2D overlay
   |
   | FreeRTOS fetch worker (core 0) -> PSRAM triple buffer
   v
foreground media poll decodes newest frame
   |
   v
Video test viewport (frame fitted to its JPEG size) + existing controls
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
- JPEG width: `384 px` (`216 px` high for the 16:9 X2D stream): it fills the 12.3.9+ Printer › Camera page, at the same frame rate as 320 px (3.7 fps measured)

Lower-load example:

```bash
python3 tools/x2d_camera_bridge.py --fps 3 --width 480
```

The process owns one Bambu camera session. Stop other manually launched `bambu_source` camera tests first.

### Keep it running (launchd)

To start the bridge at login and restart it whenever it exits, install a per-user launch agent:

```bash
bash tools/install_x2d_bridge_agent.sh              # install or update, then start
bash tools/install_x2d_bridge_agent.sh -- --fps 3   # same, passing arguments to the bridge
bash tools/install_x2d_bridge_agent.sh --status
bash tools/install_x2d_bridge_agent.sh --uninstall
```

- The agent is `com.bambuhelper.x2d-camera-bridge`. It logs to `~/Library/Logs/x2d-camera-bridge.log`, which grows by roughly 2 MB a day from the tunnel's stats lines (successful frame requests are not logged).
- It runs the bridge from this working copy, so checking out another branch changes the code it runs after the next restart.
- Bambu Studio's live view still has to be open for frames. The bridge reconnects by itself when it reopens.

## 2. Validate the bridge

```bash
curl -fsS http://127.0.0.1:8091/x2d/health.json
open http://127.0.0.1:8091/x2d/frame.jpg
```

A healthy response resembles:

```json
{"ok":true,"frameSequence":42,"frameAgeMs":120,"frameBytes":48321,"sourceRunning":true,"ffmpegRunning":true,"uptimeSeconds":12,"lastError":null,"pipelineRestarts":0}
```

The bridge restarts its camera pipeline by itself, with a back-off from 2 s up to 60 s, when:

- `bambu_source` or FFmpeg exits, for example because the live view in Bambu Studio was closed; or
- no new frame arrives for 15 s.

Each restart re-reads `url.txt`, so reopening the X2D live view in Studio is enough to bring frames back. `pipelineRestarts` counts the restarts.

Run the bridge in a terminal you keep open (or under `launchd`). A shell that ends sends it SIGTERM, which shuts it down cleanly. The supervisor does not survive that.

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

## 4. Apply the experimental X2D overlays

`scripts/run_x2d_local.sh` does steps 3-5 in one go. It copies the canonical
tree to a separate build directory, so the canonical candidate is never touched:

```bash
X2D_BRIDGE_URL="http://${MAC_IP}:8091/x2d/frame.jpg" bash scripts/run_x2d_local.sh --build
```

Or apply the two overlays by hand, in this order, after canonical reconstruction:

```bash
python3 apply_workshop_os12_x2d_bridge_camera.py \
  --repo /path/to/reconstructed/BambuHelper \
  --bridge-url "http://${MAC_IP}:8091/x2d/frame.jpg" \
  --apply
python3 apply_workshop_os12_x2d_viewer_polish.py --repo /path/to/reconstructed/BambuHelper --apply
```

Each overlay validates every anchor before writing anything, so a mismatch
leaves the tree untouched. The bridge overlay modifies only the reconstructed copy. It:

- adds the fixed `x2d-bridge` media source to that reconstructed image,
- acquires frames on a dedicated FreeRTOS worker pinned to core 0, so HTTP
  latency never blocks touch, the web server or MQTT on the Arduino loop,
- rotates three PSRAM frame buffers by pointer swap; the frame mutex is held
  only for swaps, and the foreground poll decodes outside the lock,
- tags each request with a session generation so a frame fetched before a
  pause/stop/reopen is never shown,
- validates JPEG SOI/EOI markers and the 384 KiB limit,
- adds authenticated `POST /os12/media/video/start-x2d-bridge`, which also moves
  the physical display to the video viewer,
- points the on-device Media > Video row at the X2D source (replacing the
  built-in motion test there).

The worker task and its three 384 KiB PSRAM buffers are created on the first
X2D start and persist until reboot; stop and pause only gate acquisition.

The viewer polish overlay makes Back plain navigation, removes redundant panel
refreshes, shows "Not started" on the Media row when an on-device start is
refused (no Wi-Fi or no bridge URL), and makes `/hub/frame.ppm` work while the
viewer is open. The WS350 panel cannot be read back, so captures redraw the
viewer chrome and the last decoded camera frame into an offscreen sprite.

The supplied bridge URL must be:

- plain `http://`,
- a literal private IP address,
- an explicit port,
- exactly `/x2d/frame.jpg`,
- without username, password, query string, or fragment.

The firmware does not accept a camera URL from an HTTP request.

## 5. Build and flash the WS350

```bash
X2D_BRIDGE_URL="http://${MAC_IP}:8091/x2d/frame.jpg" \
  bash scripts/run_x2d_local.sh --flash --confirm-printer-idle
```

Before uploading, the script checks the printer state through the WS350 portal,
saves the partition table, NVS and otadata, and stops if the partition layout
differs. NVS is not erased. Keep USB attached for power, flashing, and serial
diagnostics.

CI (`os12-ux-architecture.yml`) compiles this overlay candidate on every
relevant PR but does not package it.

An already-published firmware image will not contain this experimental overlay or its private bridge endpoint.

## 6. Start and control the viewer

On the touchscreen (12.3.7+), tap **Printer → Camera**. The camera page plays the bridge with a Pause/Resume row. **‹ Printer** (Back) or any tab stops it. On builds without the X2D overlay, the same button plays the printer's own camera stream, which needs LAN mode and the printer's access code. The motion test is still at More → Sound & Alerts.

From the portal or a script, use the existing authenticated OS12 session mechanism.

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

- maximum acquisition cadence: 5 fps, including HTTP latency,
- JPEG maximum: 384 KiB,
- PSRAM frame allocation,
- frame fitted to the size in its JPEG header (up to 480x270),
- JPEG SOI/EOI validation,
- bounded connect/read timeouts,
- no public Internet dependency,
- current implementation requires `Content-Length`.

Malformed, oversized, unavailable, or incomplete frames are rejected by the worker; the renderer counts polls with no new frame as no-frame polls.

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

If touch materially stalls during bridge failure or recovery, this overlay is not acceptable.

## Soak results (2026-10-19)

These runs used the WS350 on 12.3.x with X2D overlays, during a print, with the bridge at 320 px / 5 fps.

| Run | Result |
|---|---|
| 20 min, viewer only | No stop. 4,231 frames, about 4.2 fps steady. |
| 30 min, `scripts/soak_x2d_viewer.py` (status at 1 Hz, capture every 10 s, pause/resume every 60 s) | No reboot. 306/306 status OK (p50 125 ms, p95 532 ms). 108/108 captures OK. Pause/resume max 1.3 s / 0.4 s. PSRAM free flat at 6.82–6.83 MB. Ended at 18 min when someone tapped the Workshop tab, which leaves the viewer and stops the video by design. |

Notes:

- A framebuffer capture takes about 5 s and stalls drawing while it runs. With a capture every 10 s the viewer drops to about 0.8 fps, so measure frame rate with `--no-captures`.
- Keep hands off the display during a soak. The script records the touch counters when the session ends, so a tap shows up as a `touchPresses` increase.

## Framebuffer evidence

With the device on the LAN, these runners collect screenshots from `/hub/frame.ppm` unattended (set `WORKSHOP_OS_URL` if the device is not at `10.0.0.124`):

```bash
python3 scripts/capture_x2d_lifecycle_recover.py   # camera lifecycle only, retries logged
python3 scripts/capture_x2d_full_ui.py              # every catalog view + camera lifecycle
```

Framebuffer captures show what was sent to the LCD. They cannot prove the panel never showed a sub-frame flicker.

## Security and privacy

The development bridge has no HTTP authentication of its own. Use it only on a trusted private LAN/VPN and do not port-forward TCP 8091.

For persistent deployment, restrict the host firewall to the WS350/VPN subnet and add bridge authentication before treating the service as generally deployable.

`url.txt` remains local to the Mac and must never be committed, logged, uploaded, or returned by the bridge.
