#!/usr/bin/env python3
"""Overlay the experimental Mac X2D JPEG bridge onto reconstructed WS350 OS12 source.

The canonical Workshop OS 12 media backend deliberately remains transport-agnostic.
This patch is applied only to a reconstructed firmware tree for physical testing.
It installs one fixed private-LAN JPEG endpoint at build time, acquires frames on
a dedicated FreeRTOS worker (never in the foreground media poll), exposes a single
authenticated start route, and wires the existing on-device Video row to the
fixed X2D source. Arbitrary media URLs are never accepted.

Since Workshop OS 12.1.3 the on-device entry is Sound & Alerts > Video test,
and frames are drawn inside that page's video area (between its header and
control row) so the header and tab bar stay on screen.

Starting the viewer from the authenticated web route also moves the physical
display to the video viewer, whatever page or screen it was showing.
"""
from __future__ import annotations

import argparse
import ipaddress
from pathlib import Path
import sys as _sys
from pathlib import Path as _Path
from urllib.parse import urlparse

_here = _Path(__file__).resolve().parent
if str(_here) not in _sys.path:
    _sys.path.insert(0, str(_here))

from scripts.smart_home_patch_utils import PatchError


HANDLER = r'''
static void handleWorkshopMediaVideoStartX2dBridge() {
  workshop::media::MediaService& media = workshopMediaService();
  // Fixed build-time bridge source only. No request URL/path is accepted.
  const bool started = media.playMjpeg("x2d-bridge", millis());
  if (started) {
    // Give the existing OS12 video viewer physical display ownership too.
    smartHubShowPage("media-video");
  }
  sendWorkshopMediaStatus(started ? 202 : 409);
}

'''

ROUTE = '  SECURE_POST("/os12/media/video/start-x2d-bridge", handleWorkshopMediaVideoStartX2dBridge);\n'

CPP_INCLUDE_ANCHOR = "#if defined(ESP32)\n#include <esp_heap_caps.h>\n#endif\n"
CPP_INCLUDE_REPLACEMENT = (
    "#if defined(ESP32)\n#include <HTTPClient.h>\n#include <WiFi.h>\n#include <esp_heap_caps.h>\n"
    "#include <freertos/FreeRTOS.h>\n#include <freertos/semphr.h>\n#include <freertos/task.h>\n#endif\n"
)
CPP_SOURCE_ANCHOR = 'static const char kPrinterCameraSource[] = "printer-camera";\n'
CPP_SOURCE_ADDITION = 'static const char kX2dBridgeSource[] = "x2d-bridge";\n'
CPP_CONSTANT_ANCHOR = "static const uint32_t kVideoFrameIntervalMs = 200U;  // 5 fps diagnostic ceiling; preserve touch/main-loop headroom.\n"
CPP_CONSTANT_ADDITION = (
    "static const uint32_t kBridgeConnectTimeoutMs = 350U;\n"
    "static const uint32_t kBridgeReadTimeoutMs = 900U;\n"
    "static const size_t kBridgeMaxFrameBytes = 384U * 1024U;\n"
)
CPP_DIMENSION_ANCHOR = "static const float kBambuCameraHeight = 720.0f;\n"
CPP_DIMENSION_ADDITION = (
    "static const int16_t kBridgeCameraWidth = 480;\n"
    "static const int16_t kBridgeCameraHeight = 270;\n"
)
CPP_BEGIN_MJPEG_ANCHOR = """  } else if (std::strcmp(source, kPrinterCameraSource) == 0) {
    if (!cameraCanStreamDisplayedPrinter()) return false;
    cameraSetMediaOwned(true);
    cameraBegin();
    if (!cameraActive()) {
      cameraSetMediaOwned(false);
      return false;
    }
    next = VideoSource::PrinterCamera;
  } else {
    return false;
  }
"""
CPP_BEGIN_MJPEG_REPLACEMENT = """  } else if (std::strcmp(source, kPrinterCameraSource) == 0) {
    if (!cameraCanStreamDisplayedPrinter()) return false;
    cameraSetMediaOwned(true);
    cameraBegin();
    if (!cameraActive()) {
      cameraSetMediaOwned(false);
      return false;
    }
    next = VideoSource::PrinterCamera;
  } else if (std::strcmp(source, kX2dBridgeSource) == 0) {
#if defined(ESP32)
    if (WORKSHOP_X2D_BRIDGE_URL[0] == '\\0' || WiFi.status() != WL_CONNECTED) return false;
    if (!x2dBeginFetchSession()) return false;
    next = VideoSource::X2dBridge;
#else
    return false;
#endif
  } else {
    return false;
  }
"""
CPP_RENDER_INSERT_ANCHOR = "\nbool Ws350MediaBackend::stopMedia() {\n"
CPP_POLL_ANCHOR = """    } else if (videoSource_ == VideoSource::Demo) {
      renderDemoFrame(millis());
    }
"""
CPP_POLL_REPLACEMENT = """    } else if (videoSource_ == VideoSource::X2dBridge) {
      renderX2dBridgeFrame(millis());
    } else if (videoSource_ == VideoSource::Demo) {
      renderDemoFrame(millis());
    }
"""
HEADER_ENUM_ANCHOR = "  enum class VideoSource : uint8_t { None = 0, Demo, PrinterCamera };\n"
HEADER_ENUM_REPLACEMENT = "  enum class VideoSource : uint8_t { None = 0, Demo, PrinterCamera, X2dBridge };\n"
HEADER_METHOD_ANCHOR = "  void renderLatestCameraFrame(uint32_t nowMs);\n"
HEADER_METHOD_ADDITION = "  void renderX2dBridgeFrame(uint32_t nowMs);\n"

SMART_HUB_MEDIA_HINT_ANCHOR = 'strlcpy(v.value, "Motion check", sizeof(v.value));'
SMART_HUB_MEDIA_HINT_REPLACEMENT = 'strlcpy(v.value, "X2D camera", sizeof(v.value));'
SMART_HUB_DEMO_START_ANCHOR = 'if(!media.playMjpeg("demo-video",millis()))g_wsVideoStartFailed=true;'
SMART_HUB_X2D_START_REPLACEMENT = 'if(!media.playMjpeg("x2d-bridge",millis()))g_wsVideoStartFailed=true;'
SMART_HUB_IDLE_HINT_ANCHOR = '"Go back and open Video test again to retry."'
SMART_HUB_IDLE_HINT_REPLACEMENT = '"Check Wi-Fi and the Mac bridge, then try again."'
SMART_HUB_ACTIVE_HINT_ANCHOR = '"Moving shapes check the screen refresh."'
# Drawn once under the camera viewport; the first decoded frame covers it.
SMART_HUB_ACTIVE_HINT_REPLACEMENT = '"Waiting for X2D camera frames"'
# The canonical build (apply_workshop_os12_more_overhaul.py) already keeps the
# full-screen sprite off a running video; the overlay only requires it.
SMART_HUB_COMPOSITOR_ANCHOR = "const bool buffered = !directVideoViewer && hubEnsureFrame();"

ASYNC_MARKER = "static TaskHandle_t gX2dFetchTask = nullptr;"

# Bridge HTTP acquisition runs on a dedicated FreeRTOS worker. Physical testing
# showed that HTTPClient work inside workshopMediaPoll() starves the WS350's own
# web/control plane once playback starts, so the foreground poll only claims and
# decodes frames the worker has already published.
ASYNC_BLOCK = r'''
#if defined(ESP32)
// The worker task and its three PSRAM frame buffers are created on the first
// X2D start and intentionally persist for the rest of the boot; stop and pause
// only gate acquisition.
static const uint32_t kBridgeWorkerStackBytes = 8192U;
static const TickType_t kBridgeWorkerIdleTicks = pdMS_TO_TICKS(25U);
static const TickType_t kBridgeWorkerCycleTicks = pdMS_TO_TICKS(kVideoFrameIntervalMs);

static TaskHandle_t gX2dFetchTask = nullptr;
static SemaphoreHandle_t gX2dFrameMutex = nullptr;
// Three buffers rotate by pointer swap so the mutex is only ever held for a
// swap: the worker fills gX2dFetchBuffer and publishes it by swapping with
// gX2dPublishedFrame; the renderer claims a published frame by swapping it
// with gX2dDisplayFrame and decodes outside the lock.
static uint8_t* gX2dFetchBuffer = nullptr;
static uint8_t* gX2dPublishedFrame = nullptr;
static uint8_t* gX2dDisplayFrame = nullptr;
static size_t gX2dDisplayBytes = 0U;  // Foreground-owned; last decoded frame.
static size_t gX2dPublishedBytes = 0U;
static uint32_t gX2dPublishedSequence = 0U;
// Written only while holding gX2dFrameMutex. The worker reads the enable flag
// unlocked as an idle hint and re-validates both fields under the lock before
// publishing, so a pause/stop/reopen can never surface an older session's frame.
static volatile bool gX2dFetchEnabled = false;
static volatile uint32_t gX2dFetchGeneration = 0U;

static void x2dSetFetchEnabled(bool enabled, bool clearPublished) {
  if (!gX2dFrameMutex) return;
  xSemaphoreTake(gX2dFrameMutex, portMAX_DELAY);
  ++gX2dFetchGeneration;
  gX2dFetchEnabled = enabled;
  if (clearPublished) gX2dPublishedBytes = 0U;
  xSemaphoreGive(gX2dFrameMutex);
}

// Fetch one complete JPEG into dest. Returns its size, or 0 on any failure.
static size_t x2dFetchOnce(uint8_t* dest) {
  if (WORKSHOP_X2D_BRIDGE_URL[0] == '\0' || WiFi.status() != WL_CONNECTED) return 0U;

  HTTPClient http;
  http.setConnectTimeout(kBridgeConnectTimeoutMs);
  http.setTimeout(kBridgeReadTimeoutMs);
  http.setReuse(false);
  if (!http.begin(WORKSHOP_X2D_BRIDGE_URL)) return 0U;
  http.addHeader("Cache-Control", "no-cache");

  const int status = http.GET();
  const int contentLength = http.getSize();
  size_t received = 0U;
  if (status == HTTP_CODE_OK && contentLength > 4 &&
      static_cast<size_t>(contentLength) <= kBridgeMaxFrameBytes) {
    const size_t expected = static_cast<size_t>(contentLength);
    WiFiClient* stream = http.getStreamPtr();
    const uint32_t readStartedAt = millis();
    while (received < expected && millis() - readStartedAt < kBridgeReadTimeoutMs) {
      const int available = stream->available();
      if (available > 0) {
        size_t request = static_cast<size_t>(available);
        if (request > expected - received) request = expected - received;
        const int got = stream->read(dest + received, request);
        if (got > 0) received += static_cast<size_t>(got);
      } else if (!stream->connected()) {
        break;
      } else {
        vTaskDelay(pdMS_TO_TICKS(1U));
      }
    }
    if (received != expected) received = 0U;
  }
  http.end();

  if (received < 4U || dest[0] != 0xFFU || dest[1] != 0xD8U ||
      dest[received - 2U] != 0xFFU || dest[received - 1U] != 0xD9U) {
    return 0U;
  }
  return received;
}

static void x2dFetchWorker(void*) {
  for (;;) {
    if (!gX2dFetchEnabled) {
      vTaskDelay(kBridgeWorkerIdleTicks);
      continue;
    }

    const TickType_t cycleStart = xTaskGetTickCount();
    const uint32_t generation = gX2dFetchGeneration;
    const size_t received = x2dFetchOnce(gX2dFetchBuffer);
    if (received > 0U) {
      xSemaphoreTake(gX2dFrameMutex, portMAX_DELAY);
      if (gX2dFetchEnabled && generation == gX2dFetchGeneration) {
        uint8_t* const previous = gX2dPublishedFrame;
        gX2dPublishedFrame = gX2dFetchBuffer;
        gX2dFetchBuffer = previous;
        gX2dPublishedBytes = received;
        ++gX2dPublishedSequence;
      }
      xSemaphoreGive(gX2dFrameMutex);
    }

    // Hold acquisition at the existing 5 fps ceiling including HTTP latency.
    const TickType_t elapsed = xTaskGetTickCount() - cycleStart;
    vTaskDelay(elapsed < kBridgeWorkerCycleTicks ? kBridgeWorkerCycleTicks - elapsed : 1);
  }
}

static bool x2dEnsureFetchWorker() {
  if (!gX2dFrameMutex) {
    gX2dFrameMutex = xSemaphoreCreateMutex();
    if (!gX2dFrameMutex) return false;
  }
  uint8_t** const buffers[] = {&gX2dFetchBuffer, &gX2dPublishedFrame, &gX2dDisplayFrame};
  for (uint8_t** buffer : buffers) {
    if (!*buffer) {
      *buffer = static_cast<uint8_t*>(
          heap_caps_malloc(kBridgeMaxFrameBytes, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT));
      if (!*buffer) return false;
    }
  }
  if (!gX2dFetchTask) {
    // Core 0, away from the Arduino loop task on core 1.
    if (xTaskCreatePinnedToCore(x2dFetchWorker, "x2d-fetch", kBridgeWorkerStackBytes,
                                nullptr, 1, &gX2dFetchTask, 0) != pdPASS) {
      gX2dFetchTask = nullptr;
      return false;
    }
  }
  return true;
}

static bool x2dBeginFetchSession() {
  if (!x2dEnsureFetchWorker()) return false;
  x2dSetFetchEnabled(true, true);
  return true;
}

static void x2dStopFetchSession() {
  x2dSetFetchEnabled(false, true);
}
#endif
'''

PAUSE_OLD = """bool Ws350MediaBackend::pauseVideo(bool paused) {
  if (!videoRequested_) return false;
  videoPaused_ = paused;
  return true;
}
"""
PAUSE_NEW = """bool Ws350MediaBackend::pauseVideo(bool paused) {
  if (!videoRequested_) return false;
  videoPaused_ = paused;
#if defined(ESP32)
  if (videoSource_ == VideoSource::X2dBridge) x2dSetFetchEnabled(!paused, true);
#endif
  return true;
}
"""

# The camera-ownership overlay expands the legacy one-line PrinterCamera stop
# into a block. Accept either form; exactly one must be present.
STOP_ANCHORS = (
    "  if (videoRequested_ && videoSource_ == VideoSource::PrinterCamera) {\n"
    "    cameraStop();\n"
    "    cameraSetMediaOwned(false);\n"
    "  }\n",
    "  if (videoRequested_ && videoSource_ == VideoSource::PrinterCamera) cameraStop();\n",
)
STOP_ADDITION = (
    "#if defined(ESP32)\n"
    "  if (videoRequested_ && videoSource_ == VideoSource::X2dBridge) x2dStopFetchSession();\n"
    "#endif\n"
)

RENDER_X2D = r'''
#if defined(BOARD_IS_WS350) && defined(BOARD_HAS_PSRAM) && defined(ESP32)
// Frame size from the JPEG's start-of-frame marker, so the bridge can send
// frames at the size the viewer shows (smaller over Wi-Fi, no scaling).
static bool x2dJpegSize(const uint8_t* d, size_t n, int16_t* w, int16_t* h) {
  size_t i = 2;
  while (i + 9 < n) {
    if (d[i] != 0xFFU) return false;
    const uint8_t marker = d[i + 1];
    const size_t len = (static_cast<size_t>(d[i + 2]) << 8) | d[i + 3];
    const bool sof = marker >= 0xC0U && marker <= 0xCFU &&
                     marker != 0xC4U && marker != 0xC8U && marker != 0xCCU;
    if (sof) {
      *h = static_cast<int16_t>((d[i + 5] << 8) | d[i + 6]);
      *w = static_cast<int16_t>((d[i + 7] << 8) | d[i + 8]);
      return *w > 0 && *h > 0;
    }
    i += 2 + len;
  }
  return false;
}

// Fit the frame inside the Video test page's video area, never scaling up.
static float x2dViewportOrigin(const uint8_t* frame, size_t bytes, int16_t* x, int16_t* y) {
  int16_t fw = kBridgeCameraWidth, fh = kBridgeCameraHeight;
  if (!x2dJpegSize(frame, bytes, &fw, &fh)) {
    fw = kBridgeCameraWidth;
    fh = kBridgeCameraHeight;
  }
  int16_t ax = 0, ay = 0, aw = 0, ah = 0;
  ws350VideoArea(ax, ay, aw, ah);
  float scale = static_cast<float>(aw) / fw;
  const float heightScale = static_cast<float>(ah) / fh;
  if (heightScale < scale) scale = heightScale;
  if (scale > 1.0f) scale = 1.0f;
  *x = static_cast<int16_t>(ax + (aw - static_cast<int16_t>(fw * scale)) / 2);
  *y = static_cast<int16_t>(ay + (ah - static_cast<int16_t>(fh * scale)) / 2);
  return scale;
}
#endif

// Redraw the last decoded camera frame into the current tft target. The WS350
// panel is not readable, so framebuffer evidence recomposes the viewer into an
// offscreen sprite with this. Foreground-only, like the renderer.
bool x2dRedrawLastFrame() {
#if defined(BOARD_IS_WS350) && defined(BOARD_HAS_PSRAM) && defined(ESP32)
  if (!gX2dDisplayFrame || gX2dDisplayBytes < 4U) return false;
  int16_t x = 0;
  int16_t y = 0;
  const float scale = x2dViewportOrigin(gX2dDisplayFrame, gX2dDisplayBytes, &x, &y);
  return tft.drawJpg(gX2dDisplayFrame, static_cast<uint32_t>(gX2dDisplayBytes), x, y, 0, 0, 0, 0, scale, scale);
#else
  return false;
#endif
}

void Ws350MediaBackend::renderX2dBridgeFrame(uint32_t nowMs) {
#if defined(BOARD_IS_WS350) && defined(BOARD_HAS_PSRAM) && defined(ESP32)
  if (!videoRequested_ || videoPaused_ || videoSource_ != VideoSource::X2dBridge) return;
  if (videoLastRenderAtMs_ != 0 && nowMs - videoLastRenderAtMs_ < kVideoFrameIntervalMs) return;

  videoLastRenderAtMs_ = nowMs;
  ++videoDiagnostics_.polls;
  if (!gX2dFrameMutex) {
    ++videoDiagnostics_.noFramePolls;
    return;
  }

  // Claim the newest published frame by pointer swap; never decode under the lock.
  size_t frameBytes = 0U;
  uint32_t frameSequence = 0U;
  xSemaphoreTake(gX2dFrameMutex, portMAX_DELAY);
  if (gX2dPublishedBytes >= 4U) {
    uint8_t* const previous = gX2dDisplayFrame;
    gX2dDisplayFrame = gX2dPublishedFrame;
    gX2dPublishedFrame = previous;
    frameBytes = gX2dPublishedBytes;
    frameSequence = gX2dPublishedSequence;
    gX2dPublishedBytes = 0U;
  }
  xSemaphoreGive(gX2dFrameMutex);
  if (frameBytes == 0U) {
    ++videoDiagnostics_.noFramePolls;
    return;
  }

  ++videoDiagnostics_.frameObservations;
  gX2dDisplayBytes = frameBytes;
  int16_t x = 0;
  int16_t y = 0;
  const float scale = x2dViewportOrigin(gX2dDisplayFrame, frameBytes, &x, &y);
  // Same size and place every frame, so no black clear here (a panel flush
  // between clear and decode would show a black frame). The Video test page
  // clears the area once when the session starts.
  tft.drawJpg(gX2dDisplayFrame, static_cast<uint32_t>(frameBytes), x, y, 0, 0, 0, 0, scale, scale);

  markFrameDirty();
  videoLastFrameId_ = frameSequence;
  ++videoDiagnostics_.framesRendered;
  videoDiagnostics_.lastFrameId = frameSequence;
  videoDiagnostics_.lastFrameBytes = static_cast<uint32_t>(frameBytes);
  videoDiagnostics_.lastFrameAtMs = nowMs;
#else
  (void)nowMs;
#endif
}
'''


def validate_bridge_url(raw: str) -> str:
    parsed = urlparse(raw)
    if parsed.scheme != "http" or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise PatchError("bridge URL must be plain HTTP with no credentials/query/fragment")
    if parsed.path != "/x2d/frame.jpg":
        raise PatchError("bridge URL path must be exactly /x2d/frame.jpg")
    if parsed.port is None:
        raise PatchError("bridge URL must include an explicit port")
    try:
        address = ipaddress.ip_address(parsed.hostname or "")
    except ValueError as exc:
        raise PatchError("bridge host must be a literal private LAN IP address") from exc
    if not address.is_private:
        raise PatchError("bridge host must be a private LAN IP address")
    return f"http://{address}:{parsed.port}/x2d/frame.jpg"


def replace_once(text: str, anchor: str, replacement: str, label: str) -> str:
    count = text.count(anchor)
    if count != 1:
        raise PatchError(f"{label}: expected one anchor, found {count}")
    return text.replace(anchor, replacement, 1)


def insert_after_once(text: str, anchor: str, addition: str, label: str) -> str:
    if addition.strip() in text:
        return text
    count = text.count(anchor)
    if count != 1:
        raise PatchError(f"{label}: expected one anchor, found {count}")
    return text.replace(anchor, anchor + addition, 1)


def patch_smart_hub(text: str) -> str:
    text = replace_once(
        text,
        SMART_HUB_MEDIA_HINT_ANCHOR,
        SMART_HUB_MEDIA_HINT_REPLACEMENT,
        "Media X2D launch hint",
    )
    text = replace_once(
        text,
        SMART_HUB_DEMO_START_ANCHOR,
        SMART_HUB_X2D_START_REPLACEMENT,
        "Media X2D launch action",
    )
    text = replace_once(
        text,
        SMART_HUB_IDLE_HINT_ANCHOR,
        SMART_HUB_IDLE_HINT_REPLACEMENT,
        "Video viewer idle hint",
    )
    text = replace_once(
        text,
        SMART_HUB_ACTIVE_HINT_ANCHOR,
        SMART_HUB_ACTIVE_HINT_REPLACEMENT,
        "Video viewer active hint",
    )
    if text.count(SMART_HUB_COMPOSITOR_ANCHOR) != 1:
        raise PatchError("Video viewer compositor ownership: canonical direct-video drawing missing")
    return text


def patch_backend(cpp: str, bridge_url: str) -> str:
    cpp = replace_once(cpp, CPP_INCLUDE_ANCHOR, CPP_INCLUDE_REPLACEMENT, "ESP32 include block")
    define = f'#define WORKSHOP_X2D_BRIDGE_URL "{bridge_url}"\n\n'
    namespace_anchor = "namespace workshop {\nnamespace media {\n"
    cpp = replace_once(cpp, namespace_anchor, define + namespace_anchor, "bridge URL define")
    cpp = insert_after_once(cpp, CPP_SOURCE_ANCHOR, CPP_SOURCE_ADDITION, "X2D source constant")
    cpp = insert_after_once(cpp, CPP_CONSTANT_ANCHOR, CPP_CONSTANT_ADDITION, "X2D bridge limits")
    cpp = insert_after_once(
        cpp, CPP_DIMENSION_ANCHOR, CPP_DIMENSION_ADDITION + ASYNC_BLOCK, "X2D viewport + fetch worker"
    )
    cpp = replace_once(cpp, CPP_BEGIN_MJPEG_ANCHOR, CPP_BEGIN_MJPEG_REPLACEMENT, "beginMjpeg X2D branch")
    cpp = replace_once(cpp, PAUSE_OLD, PAUSE_NEW, "pauseVideo X2D worker gate")
    cpp = replace_once(cpp, CPP_RENDER_INSERT_ANCHOR, "\n" + RENDER_X2D + CPP_RENDER_INSERT_ANCHOR, "X2D renderer insertion")
    cpp = replace_once(cpp, CPP_POLL_ANCHOR, CPP_POLL_REPLACEMENT, "X2D poll branch")

    matches = [anchor for anchor in STOP_ANCHORS if cpp.count(anchor) == 1]
    if len(matches) != 1:
        raise PatchError("stopMedia X2D worker stop: expected exactly one PrinterCamera stop form")
    cpp = cpp.replace(matches[0], matches[0] + STOP_ADDITION, 1)

    # The foreground renderer must never perform network I/O.
    renderer = cpp[cpp.index("void Ws350MediaBackend::renderX2dBridgeFrame"):cpp.index(CPP_RENDER_INSERT_ANCHOR)]
    for forbidden in ("HTTPClient", "http.GET", "getStreamPtr"):
        if forbidden in renderer:
            raise PatchError(f"foreground X2D renderer contains network I/O: {forbidden}")
    return cpp


def patch_web(web_text: str) -> str:
    if "sendWorkshopMediaStatus" not in web_text or "/os12/media/video/start" not in web_text:
        raise PatchError("authenticated OS12 media API must be installed before X2D bridge route")

    # Anchor on the function name rather than brace/newline formatting so the
    # overlay remains compatible with both reconstructed source formatting
    # and compact test fixtures while still requiring one unique insertion point.
    anchor = "static void handleWorkshopMediaVideoPause()"
    if web_text.count(anchor) != 1:
        raise PatchError("media video pause handler anchor missing/non-unique")
    web_text = web_text.replace(anchor, HANDLER + anchor, 1)

    route_anchor = '  SECURE_POST("/os12/media/video/start", handleWorkshopMediaVideoStart);\n'
    if web_text.count(route_anchor) != 1:
        raise PatchError("media video start route anchor missing/non-unique")
    web_text = web_text.replace(route_anchor, route_anchor + ROUTE, 1)

    if web_text.count("/os12/media/video/start-x2d-bridge") != 1:
        raise PatchError("X2D bridge route missing/non-unique after patch")
    if 'server.on("/os12/media/video/start-x2d-bridge"' in web_text:
        raise PatchError("X2D bridge route must remain authenticated")
    return web_text


def apply(repo: Path, bridge_url: str) -> None:
    backend = repo / "src/ws350_media_backend.cpp"
    backend_h = repo / "include/ws350_media_backend.h"
    web = repo / "src/web_server.cpp"
    smart_hub = repo / "src/smart_hub.cpp"
    for path in (backend, backend_h, web, smart_hub):
        if not path.is_file():
            raise PatchError(f"X2D bridge requires reconstructed OS12 source: missing {path}")

    # Preserve the canonical repository backend. Networking is introduced only
    # in this reconstructed-source overlay for physical X2D/WS350 validation.
    cpp = backend.read_text(encoding="utf-8")
    header = backend_h.read_text(encoding="utf-8")
    web_text = web.read_text(encoding="utf-8")
    hub = smart_hub.read_text(encoding="utf-8")
    if ("HTTPClient" in cpp or "kX2dBridgeSource" in cpp or "X2dBridge" in header
            or "handleWorkshopMediaVideoStartX2dBridge" in web_text
            or SMART_HUB_X2D_START_REPLACEMENT in hub):
        raise PatchError("X2D bridge overlay already applied or reconstructed source is not canonical")

    # Stage every file in memory and write only after all anchors validate, so
    # a late mismatch cannot leave a half-patched physical candidate behind.
    cpp = patch_backend(cpp, bridge_url)
    header = replace_once(header, HEADER_ENUM_ANCHOR, HEADER_ENUM_REPLACEMENT, "X2D video source enum")
    header = insert_after_once(header, HEADER_METHOD_ANCHOR, HEADER_METHOD_ADDITION, "X2D renderer declaration")
    web_text = patch_web(web_text)
    hub = patch_smart_hub(hub)

    backend.write_text(cpp, encoding="utf-8")
    backend_h.write_text(header, encoding="utf-8")
    web.write_text(web_text, encoding="utf-8")
    smart_hub.write_text(hub, encoding="utf-8")

    print(f"Experimental Workshop OS 12 X2D bridge overlay enabled at {bridge_url}")
    print("Bridge HTTP acquisition runs on a dedicated FreeRTOS worker; the foreground poll only decodes published JPEGs")
    print("On-device launch enabled: Sound & Alerts > Video test opens the fixed X2D bridge source")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True)
    parser.add_argument("--bridge-url", required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    if not args.apply:
        raise SystemExit("refusing to modify source without --apply")
    try:
        bridge_url = validate_bridge_url(args.bridge_url)
        apply(Path(args.repo).resolve(), bridge_url)
    except PatchError as exc:
        raise SystemExit(str(exc)) from exc
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
