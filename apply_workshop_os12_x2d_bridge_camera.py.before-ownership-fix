#!/usr/bin/env python3
"""Overlay the experimental Mac X2D JPEG bridge onto reconstructed WS350 OS12 source.

The canonical Workshop OS 12 media backend deliberately remains transport-agnostic.
This patch is applied only to a reconstructed firmware tree for physical testing.
It installs one fixed private-LAN JPEG endpoint at build time and exposes a
single authenticated start route. Arbitrary media URLs are never accepted.
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
  sendWorkshopMediaStatus(started ? 202 : 409);
}

'''

ROUTE = '  SECURE_POST("/os12/media/video/start-x2d-bridge", handleWorkshopMediaVideoStartX2dBridge);\n'

CPP_INCLUDE_ANCHOR = "#if defined(ESP32)\n#include <esp_heap_caps.h>\n#endif\n"
CPP_INCLUDE_REPLACEMENT = "#if defined(ESP32)\n#include <HTTPClient.h>\n#include <WiFi.h>\n#include <esp_heap_caps.h>\n#endif\n"
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
    cameraBegin();
    if (!cameraActive()) return false;
    next = VideoSource::PrinterCamera;
  } else {
    return false;
  }
"""
CPP_BEGIN_MJPEG_REPLACEMENT = """  } else if (std::strcmp(source, kPrinterCameraSource) == 0) {
    if (!cameraCanStreamDisplayedPrinter()) return false;
    cameraBegin();
    if (!cameraActive()) return false;
    next = VideoSource::PrinterCamera;
  } else if (std::strcmp(source, kX2dBridgeSource) == 0) {
#if defined(ESP32)
    if (WORKSHOP_X2D_BRIDGE_URL[0] == '\\0' || WiFi.status() != WL_CONNECTED) return false;
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

RENDER_X2D = r'''
void Ws350MediaBackend::renderX2dBridgeFrame(uint32_t nowMs) {
#if defined(BOARD_IS_WS350) && defined(BOARD_HAS_PSRAM) && defined(ESP32)
  if (!videoRequested_ || videoPaused_ || videoSource_ != VideoSource::X2dBridge) return;
  if (videoLastRenderAtMs_ != 0 && nowMs - videoLastRenderAtMs_ < kVideoFrameIntervalMs) return;

  // Set the deadline before network I/O so failures stay bounded to the same
  // 5 fps ceiling rather than spinning the foreground media poll.
  videoLastRenderAtMs_ = nowMs;
  ++videoDiagnostics_.polls;

  if (WORKSHOP_X2D_BRIDGE_URL[0] == '\0' || WiFi.status() != WL_CONNECTED) {
    ++videoDiagnostics_.noFramePolls;
    return;
  }

  HTTPClient http;
  http.setConnectTimeout(kBridgeConnectTimeoutMs);
  http.setTimeout(kBridgeReadTimeoutMs);
  http.setReuse(false);
  if (!http.begin(WORKSHOP_X2D_BRIDGE_URL)) {
    ++videoDiagnostics_.noFramePolls;
    return;
  }
  http.addHeader("Cache-Control", "no-cache");

  const int status = http.GET();
  const int contentLength = http.getSize();
  if (status != HTTP_CODE_OK || contentLength <= 4 ||
      static_cast<size_t>(contentLength) > kBridgeMaxFrameBytes) {
    http.end();
    ++videoDiagnostics_.noFramePolls;
    return;
  }

  uint8_t* frame = static_cast<uint8_t*>(
      heap_caps_malloc(static_cast<size_t>(contentLength), MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT));
  if (!frame) {
    http.end();
    ++videoDiagnostics_.noFramePolls;
    return;
  }

  WiFiClient* stream = http.getStreamPtr();
  size_t received = 0;
  const uint32_t readStartedAt = millis();
  while (received < static_cast<size_t>(contentLength) &&
         millis() - readStartedAt < kBridgeReadTimeoutMs) {
    const int available = stream->available();
    if (available > 0) {
      size_t request = static_cast<size_t>(available);
      const size_t remaining = static_cast<size_t>(contentLength) - received;
      if (request > remaining) request = remaining;
      const int got = stream->read(frame + received, request);
      if (got > 0) received += static_cast<size_t>(got);
    } else if (!stream->connected()) {
      break;
    } else {
      delay(1);
    }
    yield();  // Cooperative handoff during bounded bridge reads.
  }
  http.end();

  const bool jpegValid =
      received == static_cast<size_t>(contentLength) && received >= 4U &&
      frame[0] == 0xFFU && frame[1] == 0xD8U &&
      frame[received - 2U] == 0xFFU && frame[received - 1U] == 0xD9U;
  if (!jpegValid) {
    heap_caps_free(frame);
    ++videoDiagnostics_.noFramePolls;
    return;
  }

  ++videoDiagnostics_.frameObservations;
  const int16_t controlBarH = 50;
  const int16_t viewportH = tft.height() > controlBarH ? tft.height() - controlBarH : tft.height();
  const int16_t x = (tft.width() - kBridgeCameraWidth) / 2;
  const int16_t y = (viewportH - kBridgeCameraHeight) / 2;
  tft.fillRect(0, 0, tft.width(), viewportH, TFT_BLACK);
  tft.drawJpg(frame, static_cast<uint32_t>(received), x, y);
  heap_caps_free(frame);

  markFrameDirty();
  ++videoLastFrameId_;
  ++videoDiagnostics_.framesRendered;
  videoDiagnostics_.lastFrameId = videoLastFrameId_;
  videoDiagnostics_.lastFrameBytes = static_cast<uint32_t>(received);
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


def apply(repo: Path, bridge_url: str) -> None:
    backend = repo / "src/ws350_media_backend.cpp"
    backend_h = repo / "include/ws350_media_backend.h"
    web = repo / "src/web_server.cpp"
    for path in (backend, backend_h, web):
        if not path.is_file():
            raise PatchError(f"X2D bridge requires reconstructed OS12 source: missing {path}")

    # Preserve the canonical repository backend. Networking is introduced only
    # in this reconstructed-source overlay for physical X2D/WS350 validation.
    cpp = backend.read_text(encoding="utf-8")
    header = backend_h.read_text(encoding="utf-8")
    if "HTTPClient" in cpp or "kX2dBridgeSource" in cpp or "X2dBridge" in header:
        raise PatchError("X2D bridge overlay already applied or reconstructed backend is not canonical")

    cpp = replace_once(cpp, CPP_INCLUDE_ANCHOR, CPP_INCLUDE_REPLACEMENT, "ESP32 include block")
    define = f'#define WORKSHOP_X2D_BRIDGE_URL "{bridge_url}"\n\n'
    namespace_anchor = "namespace workshop {\nnamespace media {\n"
    cpp = replace_once(cpp, namespace_anchor, define + namespace_anchor, "bridge URL define")
    cpp = insert_after_once(cpp, CPP_SOURCE_ANCHOR, CPP_SOURCE_ADDITION, "X2D source constant")
    cpp = insert_after_once(cpp, CPP_CONSTANT_ANCHOR, CPP_CONSTANT_ADDITION, "X2D bridge limits")
    cpp = insert_after_once(cpp, CPP_DIMENSION_ANCHOR, CPP_DIMENSION_ADDITION, "X2D viewport dimensions")
    cpp = replace_once(cpp, CPP_BEGIN_MJPEG_ANCHOR, CPP_BEGIN_MJPEG_REPLACEMENT, "beginMjpeg X2D branch")
    cpp = replace_once(cpp, CPP_RENDER_INSERT_ANCHOR, "\n" + RENDER_X2D + CPP_RENDER_INSERT_ANCHOR, "X2D renderer insertion")
    cpp = replace_once(cpp, CPP_POLL_ANCHOR, CPP_POLL_REPLACEMENT, "X2D poll branch")

    header = replace_once(header, HEADER_ENUM_ANCHOR, HEADER_ENUM_REPLACEMENT, "X2D video source enum")
    header = insert_after_once(header, HEADER_METHOD_ANCHOR, HEADER_METHOD_ADDITION, "X2D renderer declaration")

    backend.write_text(cpp, encoding="utf-8")
    backend_h.write_text(header, encoding="utf-8")

    web_text = web.read_text(encoding="utf-8")
    if "sendWorkshopMediaStatus" not in web_text or "/os12/media/video/start" not in web_text:
        raise PatchError("authenticated OS12 media API must be installed before X2D bridge route")

    if "handleWorkshopMediaVideoStartX2dBridge" not in web_text:
        # Anchor on the function name rather than brace/newline formatting so the
        # overlay remains compatible with both reconstructed source formatting
        # and compact test fixtures while still requiring one unique insertion point.
        anchor = "static void handleWorkshopMediaVideoPause()"
        if web_text.count(anchor) != 1:
            raise PatchError("media video pause handler anchor missing/non-unique")
        web_text = web_text.replace(anchor, HANDLER + anchor, 1)

    if "/os12/media/video/start-x2d-bridge" not in web_text:
        route_anchor = '  SECURE_POST("/os12/media/video/start", handleWorkshopMediaVideoStart);\n'
        if web_text.count(route_anchor) != 1:
            raise PatchError("media video start route anchor missing/non-unique")
        web_text = web_text.replace(route_anchor, route_anchor + ROUTE, 1)

    if web_text.count("/os12/media/video/start-x2d-bridge") != 1:
        raise PatchError("X2D bridge route missing/non-unique after patch")
    if 'server.on("/os12/media/video/start-x2d-bridge"' in web_text:
        raise PatchError("X2D bridge route must remain authenticated")
    if 'media.playMjpeg("x2d-bridge", millis())' not in web_text:
        raise PatchError("X2D bridge handler is not fixed to x2d-bridge source")

    web.write_text(web_text, encoding="utf-8")
    print(f"Experimental Workshop OS 12 X2D bridge overlay enabled at {bridge_url}")


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
