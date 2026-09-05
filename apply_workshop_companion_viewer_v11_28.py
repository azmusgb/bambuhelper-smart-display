#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

MARKER = "Workshop OS v11.28 Physical Companion Viewer RC1"


class PatchError(RuntimeError):
    pass


def load(root: Path, rel: str) -> str:
    p = root / rel
    if not p.exists():
        raise PatchError(f"missing reconstructed source: {rel}")
    return p.read_text(encoding="utf-8")


def save(root: Path, rel: str, text: str) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise PatchError(f"{label}: expected exactly one anchor, found {count}")
    return text.replace(old, new, 1)


def patch_build(root: Path) -> None:
    rel = "include/smart_home_build.h"
    text = load(root, rel)
    text = once(text, '#define SMART_HOME_VERSION "v11.27"', '#define SMART_HOME_VERSION "v11.28"', "version")
    text = once(text, '#define SMART_HOME_PROFILE "companion-link"', '#define SMART_HOME_PROFILE "companion-viewer"', "profile")
    text = once(text, 'Smart Home v11.27 Companion Link RC1', 'Smart Home v11.28 Physical Companion Viewer RC1', "build label")
    text += f"\n// {MARKER}\n"
    save(root, rel, text)


def patch_header(root: Path) -> None:
    rel = "src/companion_web.h"
    text = load(root, rel)
    text = once(
        text,
        'bool companionWebGetLatestCapture(const uint8_t** buf, size_t* len, uint32_t* captureId);\nvoid companionWebClearCapture();\n',
        'bool companionWebGetLatestCapture(const uint8_t** buf, size_t* len, uint32_t* captureId, uint16_t* width, uint16_t* height);\nvoid companionWebClearCapture();\nbool companionWebViewerActive();\nvoid companionWebViewerDeactivate();\n',
        "viewer capture API",
    )
    save(root, rel, text)


def patch_companion(root: Path) -> None:
    rel = "src/companion_web.cpp"
    text = load(root, rel)

    text = once(text, '#include "config.h"\n', '#include "config.h"\n#include "display_ui.h"\n', "display API include")

    text = once(
        text,
        'uint8_t* g_capturePublished = nullptr;\nsize_t g_capturePublishedLen = 0;\nuint32_t g_captureId = 0;\nuint32_t g_captureAtMs = 0;\n',
        'uint8_t* g_capturePublished = nullptr;\nsize_t g_capturePublishedLen = 0;\nuint16_t g_captureInflightWidth = 0;\nuint16_t g_captureInflightHeight = 0;\nuint16_t g_capturePublishedWidth = 0;\nuint16_t g_capturePublishedHeight = 0;\nuint32_t g_captureId = 0;\nuint32_t g_captureAtMs = 0;\nbool g_captureViewerActive = false;\nScreenState g_captureViewerReturnScreen = SCREEN_IDLE;\n',
        "capture dimensions + viewer state",
    )

    text = once(
        text,
        '  CAPTURE_UPLOAD_TYPE,\n  CAPTURE_UPLOAD_ALLOC,\n',
        '  CAPTURE_UPLOAD_TYPE,\n  CAPTURE_UPLOAD_DIMENSIONS,\n  CAPTURE_UPLOAD_ALLOC,\n',
        "dimension upload error",
    )

    text = once(
        text,
        '  g_captureInflightLen = 0;\n}\n\nvoid clearPublishedCapture() {',
        '  g_captureInflightLen = 0;\n  g_captureInflightWidth = 0;\n  g_captureInflightHeight = 0;\n}\n\nvoid clearPublishedCapture() {',
        "reset inflight dimensions",
    )
    text = once(
        text,
        '  g_capturePublishedLen = 0;\n  g_captureAtMs = 0;\n}\n',
        '  g_capturePublishedLen = 0;\n  g_capturePublishedWidth = 0;\n  g_capturePublishedHeight = 0;\n  g_captureAtMs = 0;\n}\n',
        "reset published dimensions",
    )

    text = once(
        text,
        '    if (upload.type != "image/jpeg") {\n      g_captureUploadError = CAPTURE_UPLOAD_TYPE;\n      return;\n    }\n#ifdef BOARD_HAS_PSRAM\n',
        '    if (upload.type != "image/jpeg") {\n      g_captureUploadError = CAPTURE_UPLOAD_TYPE;\n      return;\n    }\n    const int requestedWidth = server.hasArg("w") ? server.arg("w").toInt() : 0;\n    const int requestedHeight = server.hasArg("h") ? server.arg("h").toInt() : 0;\n    if (requestedWidth < 1 || requestedWidth > 480 || requestedHeight < 1 || requestedHeight > 480) {\n      g_captureUploadError = CAPTURE_UPLOAD_DIMENSIONS;\n      return;\n    }\n    g_captureInflightWidth = static_cast<uint16_t>(requestedWidth);\n    g_captureInflightHeight = static_cast<uint16_t>(requestedHeight);\n#ifdef BOARD_HAS_PSRAM\n',
        "validate capture dimensions",
    )

    text = once(
        text,
        '    g_capturePublished = g_captureInflight;\n    g_capturePublishedLen = g_captureInflightLen;\n    g_captureInflight = nullptr;\n    g_captureInflightLen = 0;\n',
        '    g_capturePublished = g_captureInflight;\n    g_capturePublishedLen = g_captureInflightLen;\n    g_capturePublishedWidth = g_captureInflightWidth;\n    g_capturePublishedHeight = g_captureInflightHeight;\n    g_captureInflight = nullptr;\n    g_captureInflightLen = 0;\n    g_captureInflightWidth = 0;\n    g_captureInflightHeight = 0;\n',
        "publish capture dimensions",
    )

    text = once(
        text,
        '    case CAPTURE_UPLOAD_TYPE: code = 415; message = "JPEG capture required"; break;\n    case CAPTURE_UPLOAD_ALLOC:',
        '    case CAPTURE_UPLOAD_TYPE: code = 415; message = "JPEG capture required"; break;\n    case CAPTURE_UPLOAD_DIMENSIONS: code = 422; message = "capture dimensions must be between 1 and 480 pixels"; break;\n    case CAPTURE_UPLOAD_ALLOC:',
        "dimension error response",
    )

    text = once(
        text,
        '  cap["bytes"] = g_capturePublishedLen;\n  cap["ageMs"] = g_captureAtMs ? static_cast<uint32_t>(millis() - g_captureAtMs) : 0;\n',
        '  cap["bytes"] = g_capturePublishedLen;\n  cap["width"] = g_capturePublishedWidth;\n  cap["height"] = g_capturePublishedHeight;\n  cap["viewer"] = g_captureViewerActive;\n  cap["ageMs"] = g_captureAtMs ? static_cast<uint32_t>(millis() - g_captureAtMs) : 0;\n',
        "capture viewer metadata",
    )

    text = once(
        text,
        'void handleCompanionCaptureClear() {\n  if (!securityAuthorize(server, true)) return;\n  clearPublishedCapture();\n',
        'void handleCompanionCaptureClear() {\n  if (!securityAuthorize(server, true)) return;\n  if (g_captureViewerActive) {\n    const ScreenState returnScreen = g_captureViewerReturnScreen;\n    g_captureViewerActive = false;\n    setScreenState(returnScreen);\n  }\n  clearPublishedCapture();\n',
        "clear active viewer",
    )

    show_handler = r'''

void handleCompanionCaptureShow() {
  if (!securityAuthorize(server, true)) return;
  if (!g_capturePublished || g_capturePublishedLen == 0 || g_capturePublishedWidth == 0 || g_capturePublishedHeight == 0) {
    server.send(409, "application/json", "{\"status\":\"error\",\"message\":\"no phone capture is available\"}");
    return;
  }
  const ScreenState current = getScreenState();
  g_captureViewerReturnScreen = current == SCREEN_CAMERA ? SCREEN_IDLE : current;
  g_captureViewerActive = true;
  notePhoneSeen(g_lastPhoneSlot);
  setScreenState(SCREEN_CAMERA);
  server.sendHeader("Cache-Control", "no-store");
  server.send(200, "application/json", "{\"status\":\"ok\",\"viewer\":true}");
}
'''
    text = once(text, '\n}  // namespace\n\nvoid registerCompanionWebRoutes() {', show_handler + '\n}  // namespace\n\nvoid registerCompanionWebRoutes() {', "capture show handler")

    text = once(
        text,
        '  server.on("/companion/capture/clear", HTTP_POST, handleCompanionCaptureClear);\n',
        '  server.on("/companion/capture/clear", HTTP_POST, handleCompanionCaptureClear);\n  server.on("/companion/capture/show", HTTP_POST, handleCompanionCaptureShow);\n',
        "capture show route",
    )

    old_api = '''bool companionWebGetLatestCapture(const uint8_t** buf, size_t* len, uint32_t* captureId) {\n  if (!buf || !len || !captureId || !g_capturePublished || g_capturePublishedLen == 0) return false;\n  *buf = g_capturePublished;\n  *len = g_capturePublishedLen;\n  *captureId = g_captureId;\n  return true;\n}\n\nvoid companionWebClearCapture() { clearPublishedCapture(); }\n'''
    new_api = '''bool companionWebGetLatestCapture(const uint8_t** buf, size_t* len, uint32_t* captureId, uint16_t* width, uint16_t* height) {\n  if (!buf || !len || !captureId || !width || !height || !g_capturePublished ||\n      g_capturePublishedLen == 0 || g_capturePublishedWidth == 0 || g_capturePublishedHeight == 0) return false;\n  *buf = g_capturePublished;\n  *len = g_capturePublishedLen;\n  *captureId = g_captureId;\n  *width = g_capturePublishedWidth;\n  *height = g_capturePublishedHeight;\n  return true;\n}\n\nvoid companionWebClearCapture() { clearPublishedCapture(); }\n\nbool companionWebViewerActive() { return g_captureViewerActive; }\n\nvoid companionWebViewerDeactivate() { g_captureViewerActive = false; }\n'''
    text = once(text, old_api, new_api, "viewer public API")

    # Mobile UI: four balanced phone actions, explicit physical display action.
    text = once(
        text,
        '<button id="clearCaptureBtn" class="btn" type="button" disabled>Clear photo</button>\n      <a class="btn linkBtn full" href="/">Full Workshop OS</a>',
        '<button id="showCaptureBtn" class="btn primary" type="button" disabled>Show on Waveshare</button>\n      <button id="clearCaptureBtn" class="btn" type="button" disabled>Clear photo</button>\n      <a class="btn linkBtn" href="/">Full Workshop OS</a>',
        "viewer phone action",
    )
    text = once(
        text,
        "('On Waveshare RAM · '+Math.round(num(capture.bytes,0)/1024)+' KB · capture #'+capture.id)",
        "('On Waveshare RAM · '+num(capture.width,0)+'×'+num(capture.height,0)+' · '+Math.round(num(capture.bytes,0)/1024)+' KB · capture #'+capture.id)",
        "capture dimensions copy",
    )
    text = once(
        text,
        "if($('clearCaptureBtn'))$('clearCaptureBtn').disabled=!(capture&&capture.available)||!!busy.capture;",
        "if($('showCaptureBtn')){$('showCaptureBtn').disabled=!(capture&&capture.available)||!!busy.capture;$('showCaptureBtn').textContent=capture&&capture.viewer?'Showing on Waveshare':'Show on Waveshare'}\n  if($('clearCaptureBtn'))$('clearCaptureBtn').disabled=!(capture&&capture.available)||!!busy.capture;",
        "viewer render state",
    )
    text = once(text, 'function uploadCaptureBlob(blob){', 'function uploadCaptureBlob(blob,width,height){', "capture upload dimensions signature")
    text = once(
        text,
        "return fetchJson('/companion/capture',{method:'POST',body:form},12000)",
        "return fetchJson('/companion/capture?w='+encodeURIComponent(width)+'&h='+encodeURIComponent(height),{method:'POST',body:form},12000)",
        "capture dimensions request",
    )
    text = once(text, 'uploadCaptureBlob(blob).catch(function(e)', 'uploadCaptureBlob(blob,canvas.width,canvas.height).catch(function(e)', "send canvas dimensions")
    text = once(
        text,
        "$('clearCaptureBtn').addEventListener('click',function(){",
        "$('showCaptureBtn').addEventListener('click',function(){if(!(capture&&capture.available)||busy.capture)return;busy.capture=true;render();post('/companion/capture/show',{}).then(function(){setFeedback('Phone photo is now on the Waveshare. Tap the display to exit.','ok');return refresh()}).catch(function(e){setFeedback(e.message||'Could not open photo on Waveshare','error')}).finally(function(){busy.capture=false;render()})});\n$('clearCaptureBtn').addEventListener('click',function(){",
        "viewer action handler",
    )
    text = once(text, 'Workshop Companion Link · v11.27 candidate', 'Physical Companion Viewer · v11.28 candidate', "viewer footer")

    save(root, rel, text)


def patch_display(root: Path) -> None:
    rel = "src/display_ui.cpp"
    text = load(root, rel)
    text = once(text, '#include "camera_client.h"\n', '#include "camera_client.h"\n#include "companion_web.h"\n', "Companion Viewer include")

    text = once(
        text,
        '''void setScreenState(ScreenState state) {\n  currentScreen = state;\n}\n''',
        '''void setScreenState(ScreenState state) {\n  // PHONE PHOTO is an explicit override of the existing fullscreen camera\n  // surface. Leaving that surface always releases the override so the normal\n  // P1/A1 chamber-camera path can never inherit a stale phone image.\n  if (currentScreen == SCREEN_CAMERA && state != SCREEN_CAMERA && companionWebViewerActive())\n    companionWebViewerDeactivate();\n  currentScreen = state;\n}\n''',
        "viewer exit cleanup",
    )

    start = '''static void drawCameraFullscreen() {\n  static uint32_t lastFid = 0xFFFFFFFFu;\n  const uint8_t* buf; size_t len; uint32_t fid;\n'''
    replacement = '''static void drawCameraFullscreen() {\n  // v11.28 reuses the proven fullscreen JPEG surface for an explicitly opened\n  // iPhone capture. Upload alone never changes screens; only the authenticated\n  // /companion/capture/show action activates this branch.\n  if (companionWebViewerActive()) {\n    static uint32_t lastCompanionCaptureId = 0xFFFFFFFFu;\n    const uint8_t* phoneBuf = nullptr;\n    size_t phoneLen = 0;\n    uint32_t captureId = 0;\n    uint16_t srcW = 0, srcH = 0;\n    if (!companionWebGetLatestCapture(&phoneBuf, &phoneLen, &captureId, &srcW, &srcH)) {\n      tft.fillScreen(TFT_BLACK);\n      markFrameDirty();\n      return;\n    }\n    if (captureId == lastCompanionCaptureId && !forceRedraw) return;\n    lastCompanionCaptureId = captureId;\n    const float sw = tft.width(), sh = tft.height();\n    float sc = sw / srcW;\n    if (sh / srcH < sc) sc = sh / srcH;\n    const int dw = (int)(srcW * sc), dh = (int)(srcH * sc);\n    tft.fillScreen(TFT_BLACK);\n    tft.drawJpg(phoneBuf, (uint32_t)phoneLen, ((int)sw - dw) / 2, ((int)sh - dh) / 2, 0, 0, 0, 0, sc, sc);\n    const int16_t footerH = 24;\n    tft.fillRect(0, tft.height() - footerH, tft.width(), footerH, TFT_BLACK);\n    tft.setTextDatum(MC_DATUM);\n    setFont(tft, FONT_SMALL);\n    tft.setTextColor(TFT_WHITE, TFT_BLACK);\n    tft.drawString("PHONE PHOTO  |  TAP TO EXIT", tft.width() / 2, tft.height() - footerH / 2);\n    markFrameDirty();\n    return;\n  }\n\n  static uint32_t lastFid = 0xFFFFFFFFu;\n  const uint8_t* buf; size_t len; uint32_t fid;\n'''
    text = once(text, start, replacement, "fullscreen Companion photo renderer")
    save(root, rel, text)


def apply(root: Path) -> None:
    build = load(root, "include/smart_home_build.h")
    if MARKER in build:
        print(f"{MARKER} already applied")
        return
    if 'SMART_HOME_VERSION "v11.27"' not in build:
        raise PatchError("v11.27 Companion Link base is required")

    patch_header(root)
    patch_companion(root)
    patch_display(root)
    patch_build(root)

    checks = {
        "include/smart_home_build.h": ['SMART_HOME_VERSION "v11.28"', 'SMART_HOME_PROFILE "companion-viewer"', MARKER],
        "src/companion_web.h": ['companionWebViewerActive', 'companionWebViewerDeactivate', 'uint16_t* width', 'uint16_t* height'],
        "src/companion_web.cpp": [
            'server.on("/companion/capture/show", HTTP_POST',
            'g_capturePublishedWidth', 'g_capturePublishedHeight',
            'requestedWidth < 1 || requestedWidth > 480',
            'requestedHeight < 1 || requestedHeight > 480',
            'cap["viewer"] = g_captureViewerActive',
            'Show on Waveshare',
            "post('/companion/capture/show',{})",
            "'/companion/capture?w='+encodeURIComponent(width)+'&h='+encodeURIComponent(height)",
            'Physical Companion Viewer · v11.28 candidate',
        ],
        "src/display_ui.cpp": [
            '#include "companion_web.h"',
            'if (companionWebViewerActive())',
            'companionWebGetLatestCapture(&phoneBuf, &phoneLen, &captureId, &srcW, &srcH)',
            'tft.drawJpg(phoneBuf',
            'PHONE PHOTO  |  TAP TO EXIT',
            'cameraGetLatestFrame(&buf, &len, &fid)',
            'companionWebViewerDeactivate()',
        ],
    }
    for rel, needles in checks.items():
        body = load(root, rel)
        for needle in needles:
            if needle not in body:
                raise PatchError(f"{rel}: missing {needle}")

    print(f"{MARKER} applied")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    if not args.apply:
        raise SystemExit("refusing to mutate without --apply")
    apply(Path(args.repo))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
