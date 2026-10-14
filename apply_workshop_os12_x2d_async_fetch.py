#!/usr/bin/env python3
"""Move reconstructed WS350 X2D JPEG acquisition off the foreground media poll.

The original experimental X2D overlay performs HTTPClient GET/read work from
Ws350MediaBackend::renderX2dBridgeFrame(), which is called by workshopMediaPoll()
on the main firmware loop. Physical testing showed that once X2D playback starts,
the WS350 local HTTP control plane begins resetting/timing out while the Mac
bridge continues serving healthy JPEGs.

This reconstruction-only follow-up overlay moves bridge acquisition to one
bounded FreeRTOS worker pinned away from the Arduino foreground loop. The worker
owns all HTTP I/O and publishes the latest complete JPEG into a PSRAM buffer.
The foreground media poll only decodes a newly published JPEG into the display.

The canonical media backend remains transport-agnostic.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import sys as _sys
from pathlib import Path as _Path

_here = _Path(__file__).resolve().parent
if str(_here) not in _sys.path:
    _sys.path.insert(0, str(_here))

from scripts.smart_home_patch_utils import PatchError


ASYNC_MARKER = "static TaskHandle_t gX2dFetchTask = nullptr;"

ESP32_INCLUDE_OLD = """#if defined(ESP32)\n#include <HTTPClient.h>\n#include <WiFi.h>\n#include <esp_heap_caps.h>\n#endif\n"""
ESP32_INCLUDE_NEW = """#if defined(ESP32)\n#include <HTTPClient.h>\n#include <WiFi.h>\n#include <esp_heap_caps.h>\n#include <freertos/FreeRTOS.h>\n#include <freertos/semphr.h>\n#include <freertos/task.h>\n#endif\n"""

ASYNC_INSERT_ANCHOR = "static const int16_t kBridgeCameraHeight = 270;\n"

ASYNC_BLOCK = r'''
#if defined(ESP32)
static const uint32_t kBridgeWorkerStackBytes = 8192U;
static const TickType_t kBridgeWorkerIdleTicks = pdMS_TO_TICKS(25U);
static const TickType_t kBridgeWorkerCycleTicks = pdMS_TO_TICKS(kVideoFrameIntervalMs);
static const TickType_t kBridgePublishMutexTicks = pdMS_TO_TICKS(50U);

static TaskHandle_t gX2dFetchTask = nullptr;
static SemaphoreHandle_t gX2dFrameMutex = nullptr;
static uint8_t* gX2dFetchBuffer = nullptr;
static uint8_t* gX2dPublishedFrame = nullptr;
static size_t gX2dPublishedBytes = 0U;
static uint32_t gX2dPublishedSequence = 0U;
static volatile bool gX2dFetchEnabled = false;
static volatile uint32_t gX2dFetchGeneration = 0U;

static void x2dSetFetchEnabled(bool enabled, bool clearPublished) {
  // Invalidate any request currently in flight before changing session state.
  gX2dFetchEnabled = false;
  ++gX2dFetchGeneration;

  if (clearPublished && gX2dFrameMutex &&
      xSemaphoreTake(gX2dFrameMutex, kBridgePublishMutexTicks) == pdTRUE) {
    gX2dPublishedBytes = 0U;
    xSemaphoreGive(gX2dFrameMutex);
  }

  gX2dFetchEnabled = enabled;
}

static void x2dFetchWorker(void*) {
  for (;;) {
    if (!gX2dFetchEnabled) {
      vTaskDelay(kBridgeWorkerIdleTicks);
      continue;
    }

    const uint32_t generation = gX2dFetchGeneration;
    bool published = false;

    if (WORKSHOP_X2D_BRIDGE_URL[0] != '\0' && WiFi.status() == WL_CONNECTED &&
        gX2dFetchBuffer && gX2dPublishedFrame && gX2dFrameMutex) {
      HTTPClient http;
      http.setConnectTimeout(kBridgeConnectTimeoutMs);
      http.setTimeout(kBridgeReadTimeoutMs);
      http.setReuse(false);

      if (http.begin(WORKSHOP_X2D_BRIDGE_URL)) {
        http.addHeader("Cache-Control", "no-cache");
        const int status = http.GET();
        const int contentLength = http.getSize();

        if (status == HTTP_CODE_OK && contentLength > 4 &&
            static_cast<size_t>(contentLength) <= kBridgeMaxFrameBytes) {
          WiFiClient* stream = http.getStreamPtr();
          size_t received = 0U;
          const uint32_t readStartedAt = millis();

          while (received < static_cast<size_t>(contentLength) &&
                 millis() - readStartedAt < kBridgeReadTimeoutMs) {
            const int available = stream->available();
            if (available > 0) {
              size_t request = static_cast<size_t>(available);
              const size_t remaining = static_cast<size_t>(contentLength) - received;
              if (request > remaining) request = remaining;
              const int got = stream->read(gX2dFetchBuffer + received, request);
              if (got > 0) received += static_cast<size_t>(got);
            } else if (!stream->connected()) {
              break;
            } else {
              vTaskDelay(pdMS_TO_TICKS(1U));
            }
          }

          const bool jpegValid =
              received == static_cast<size_t>(contentLength) && received >= 4U &&
              gX2dFetchBuffer[0] == 0xFFU && gX2dFetchBuffer[1] == 0xD8U &&
              gX2dFetchBuffer[received - 2U] == 0xFFU &&
              gX2dFetchBuffer[received - 1U] == 0xD9U;

          // A pause/stop/reopen invalidates an in-flight response. Never publish
          // a frame fetched for an older media-session generation.
          if (jpegValid && gX2dFetchEnabled && generation == gX2dFetchGeneration &&
              xSemaphoreTake(gX2dFrameMutex, kBridgePublishMutexTicks) == pdTRUE) {
            std::memcpy(gX2dPublishedFrame, gX2dFetchBuffer, received);
            gX2dPublishedBytes = received;
            ++gX2dPublishedSequence;
            xSemaphoreGive(gX2dFrameMutex);
            published = true;
          }
        }
        http.end();
      }
    }

    // Keep acquisition bounded near the existing 5 fps ceiling. HTTP latency
    // is paid only by this worker; the foreground UI/web loop remains free.
    (void)published;
    vTaskDelay(kBridgeWorkerCycleTicks);
  }
}

static bool x2dEnsureFetchWorker() {
  if (gX2dFetchTask && gX2dFrameMutex && gX2dFetchBuffer && gX2dPublishedFrame) {
    return true;
  }

  if (!gX2dFrameMutex) {
    gX2dFrameMutex = xSemaphoreCreateMutex();
    if (!gX2dFrameMutex) return false;
  }

  if (!gX2dFetchBuffer) {
    gX2dFetchBuffer = static_cast<uint8_t*>(
        heap_caps_malloc(kBridgeMaxFrameBytes, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT));
  }
  if (!gX2dPublishedFrame) {
    gX2dPublishedFrame = static_cast<uint8_t*>(
        heap_caps_malloc(kBridgeMaxFrameBytes, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT));
  }
  if (!gX2dFetchBuffer || !gX2dPublishedFrame) return false;

  if (!gX2dFetchTask) {
    const BaseType_t created = xTaskCreatePinnedToCore(
        x2dFetchWorker,
        "x2d-fetch",
        kBridgeWorkerStackBytes,
        nullptr,
        1,
        &gX2dFetchTask,
        0);
    if (created != pdPASS) {
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

BEGIN_X2D_OLD = r'''  } else if (std::strcmp(source, kX2dBridgeSource) == 0) {
#if defined(ESP32)
    if (WORKSHOP_X2D_BRIDGE_URL[0] == '\0' || WiFi.status() != WL_CONNECTED) return false;
    next = VideoSource::X2dBridge;
#else
    return false;
#endif
  } else {
'''

BEGIN_X2D_NEW = r'''  } else if (std::strcmp(source, kX2dBridgeSource) == 0) {
#if defined(ESP32)
    if (WORKSHOP_X2D_BRIDGE_URL[0] == '\0' || WiFi.status() != WL_CONNECTED) return false;
    if (!x2dBeginFetchSession()) return false;
    next = VideoSource::X2dBridge;
#else
    return false;
#endif
  } else {
'''

PAUSE_NEW = r'''bool Ws350MediaBackend::pauseVideo(bool paused) {
  if (!videoRequested_) return false;
  videoPaused_ = paused;
#if defined(ESP32)
  if (videoSource_ == VideoSource::X2dBridge) {
    x2dSetFetchEnabled(!paused, false);
  }
#endif
  return true;
}
'''

RENDER_NEW = r'''void Ws350MediaBackend::renderX2dBridgeFrame(uint32_t nowMs) {
#if defined(BOARD_IS_WS350) && defined(BOARD_HAS_PSRAM) && defined(ESP32)
  if (!videoRequested_ || videoPaused_ || videoSource_ != VideoSource::X2dBridge) return;
  if (videoLastRenderAtMs_ != 0 && nowMs - videoLastRenderAtMs_ < kVideoFrameIntervalMs) return;

  videoLastRenderAtMs_ = nowMs;
  ++videoDiagnostics_.polls;

  if (!gX2dFrameMutex || !gX2dPublishedFrame ||
      xSemaphoreTake(gX2dFrameMutex, kBridgePublishMutexTicks) != pdTRUE) {
    ++videoDiagnostics_.noFramePolls;
    return;
  }

  const size_t frameBytes = gX2dPublishedBytes;
  const uint32_t frameSequence = gX2dPublishedSequence;
  if (frameBytes < 4U || frameSequence == videoLastFrameId_) {
    xSemaphoreGive(gX2dFrameMutex);
    ++videoDiagnostics_.noFramePolls;
    return;
  }

  ++videoDiagnostics_.frameObservations;
  const int16_t controlBarH = 50;
  const int16_t viewportH = tft.height() > controlBarH ? tft.height() - controlBarH : tft.height();
  const int16_t x = (tft.width() - kBridgeCameraWidth) / 2;
  const int16_t y = (viewportH - kBridgeCameraHeight) / 2;

  // The published buffer cannot be overwritten while the display decoder reads
  // it. The worker may continue network acquisition into its independent PSRAM
  // staging buffer and waits only for this short publish/decode ownership window.
  tft.drawJpg(gX2dPublishedFrame, static_cast<uint32_t>(frameBytes), x, y);
  xSemaphoreGive(gX2dFrameMutex);

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


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise PatchError(f"{label}: expected one anchor, found {count}")
    return text.replace(old, new, 1)


def replace_cpp_function(text: str, signature: str, replacement: str, label: str) -> str:
    start = text.find(signature)
    if start < 0:
        raise PatchError(f"{label}: function signature missing")
    brace = text.find("{", start + len(signature))
    if brace < 0:
        raise PatchError(f"{label}: opening brace missing")
    depth = 0
    i = brace
    while i < len(text):
        ch = text[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                if end < len(text) and text[end] == "\r":
                    end += 1
                if end < len(text) and text[end] == "\n":
                    end += 1
                return text[:start] + replacement + text[end:]
        i += 1
    raise PatchError(f"{label}: closing brace missing")


def apply(repo: Path) -> None:
    backend = repo / "src/ws350_media_backend.cpp"
    if not backend.is_file():
        raise PatchError(f"missing reconstructed source: {backend}")

    text = backend.read_text(encoding="utf-8")
    if ASYNC_MARKER in text:
        print("Workshop OS 12 X2D async bridge fetch already installed")
        return

    required = (
        "kX2dBridgeSource",
        "renderX2dBridgeFrame",
        "WORKSHOP_X2D_BRIDGE_URL",
        "kBridgeMaxFrameBytes",
        "HTTPClient",
        "The bridge already produces the exact 480x270 viewport",
    )
    for needle in required:
        if needle not in text:
            raise PatchError(f"apply bridge + viewer polish before async fetch: missing {needle}")

    staged = replace_once(text, ESP32_INCLUDE_OLD, ESP32_INCLUDE_NEW, "FreeRTOS include block")
    staged = replace_once(
        staged,
        ASYNC_INSERT_ANCHOR,
        ASYNC_INSERT_ANCHOR + ASYNC_BLOCK,
        "async fetch worker insertion",
    )
    staged = replace_once(staged, BEGIN_X2D_OLD, BEGIN_X2D_NEW, "X2D begin worker startup")
    staged = replace_cpp_function(
        staged,
        "bool Ws350MediaBackend::pauseVideo(bool paused)",
        PAUSE_NEW,
        "X2D pause worker control",
    )
    staged = replace_cpp_function(
        staged,
        "void Ws350MediaBackend::renderX2dBridgeFrame(uint32_t nowMs)",
        RENDER_NEW,
        "X2D non-blocking renderer",
    )

    stop_anchor = "  if (videoRequested_ && videoSource_ == VideoSource::PrinterCamera) cameraStop();\n"
    stop_replacement = stop_anchor + "#if defined(ESP32)\n  if (videoRequested_ && videoSource_ == VideoSource::X2dBridge) x2dStopFetchSession();\n#endif\n"
    staged = replace_once(staged, stop_anchor, stop_replacement, "X2D worker stop")

    checks = (
        ASYNC_MARKER,
        'xTaskCreatePinnedToCore(',
        '"x2d-fetch"',
        "x2dBeginFetchSession()",
        "x2dStopFetchSession();",
        "x2dSetFetchEnabled(!paused, false);",
        "tft.drawJpg(gX2dPublishedFrame",
        "generation == gX2dFetchGeneration",
        "std::memcpy(gX2dPublishedFrame, gX2dFetchBuffer, received);",
    )
    for needle in checks:
        if needle not in staged:
            raise PatchError(f"async fetch invariant missing: {needle}")

    render_start = staged.find("void Ws350MediaBackend::renderX2dBridgeFrame(uint32_t nowMs)")
    stop_start = staged.find("bool Ws350MediaBackend::stopMedia()", render_start)
    if render_start < 0 or stop_start < 0:
        raise PatchError("unable to isolate async X2D renderer")
    renderer = staged[render_start:stop_start]
    if "HTTPClient" in renderer or "http.GET" in renderer or "getStreamPtr" in renderer:
        raise PatchError("foreground X2D renderer still contains network I/O")

    backend.write_text(staged, encoding="utf-8")
    print("Workshop OS 12 X2D async bridge fetch installed")
    print("Bridge HTTP acquisition now runs in a dedicated FreeRTOS worker; foreground poll only renders published JPEGs")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    if not args.apply:
        raise SystemExit("refusing to modify reconstructed source without --apply")
    try:
        apply(Path(args.repo).resolve())
    except PatchError as exc:
        raise SystemExit(f"FAIL: {exc}") from exc
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
