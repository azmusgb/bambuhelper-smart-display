#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

MARKER = "Workshop OS v11.30 Unified Web + Companion RC2 Viewer Reliability"


class PatchError(RuntimeError):
    pass


def load(root: Path, rel: str) -> str:
    p = root / rel
    if not p.exists():
        raise PatchError(f"missing reconstructed source: {rel}")
    return p.read_text(encoding="utf-8")


def save(root: Path, rel: str, text: str) -> None:
    (root / rel).write_text(text, encoding="utf-8")


def once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise PatchError(f"{label}: expected exactly one anchor, found {count}")
    return text.replace(old, new, 1)


def patch_build(root: Path) -> None:
    rel = "include/smart_home_build.h"
    text = load(root, rel)
    text = once(text, 'Smart Home v11.30 Unified Web + Companion RC1', 'Smart Home v11.30 Unified Web + Companion RC2', "build label")
    text += f"\n// {MARKER}\n"
    save(root, rel, text)


def patch_companion_api(root: Path) -> None:
    rel = "src/companion_web.h"
    text = load(root, rel)
    text = once(text, 'bool companionWebViewerActive();\nvoid companionWebViewerDeactivate();\n', 'bool companionWebViewerActive();\nvoid companionWebViewerDeactivate();\nvoid companionWebViewerExitToReturnScreen();\n', "viewer exit API declaration")
    save(root, rel, text)

    rel = "src/companion_web.cpp"
    text = load(root, rel)
    text = once(
        text,
        'bool companionWebViewerActive() { return g_captureViewerActive; }\n\nvoid companionWebViewerDeactivate() { g_captureViewerActive = false; }\n',
        '''bool companionWebViewerActive() { return g_captureViewerActive; }\n\nvoid companionWebViewerDeactivate() { g_captureViewerActive = false; }\n\nvoid companionWebViewerExitToReturnScreen() {\n  if (!g_captureViewerActive) return;\n  const ScreenState target = g_captureViewerReturnScreen == SCREEN_CAMERA\n      ? SCREEN_IDLE : g_captureViewerReturnScreen;\n  g_captureViewerActive = false;\n  setScreenState(target);\n}\n''',
        "viewer exit implementation",
    )

    old = "$('showCaptureBtn').addEventListener('click',function(){if(!(capture&&capture.available)||busy.capture)return;busy.capture=true;render();post('/companion/capture/show',{}).then(function(){setFeedback('Phone photo is now on the Waveshare. Tap the display to exit.','ok');return refresh()}).catch(function(e){setFeedback(e.message||'Could not open photo on Waveshare','error')}).finally(function(){busy.capture=false;render()})});"
    new = "$('showCaptureBtn').addEventListener('click',function(){if(!(capture&&capture.available)||busy.capture)return;busy.capture=true;render();setFeedback('Opening photo on Waveshare…');post('/companion/capture/show',{}).then(function(){return new Promise(function(resolve){setTimeout(resolve,180)})}).then(function(){return refresh()}).then(function(){if(!(capture&&capture.viewer))throw new Error('Waveshare did not enter phone-photo view');setFeedback('Photo is displaying on the Waveshare. Tap the display to exit.','ok')}).catch(function(e){setFeedback(e.message||'Could not open photo on Waveshare','error')}).finally(function(){busy.capture=false;render()})});"
    text = once(text, old, new, "confirmed physical viewer feedback")

    old = "$('photoState').textContent=capture&&capture.available?('On Waveshare RAM · '+num(capture.width,0)+'×'+num(capture.height,0)+' · '+Math.round(num(capture.bytes,0)/1024)+' KB · capture #'+capture.id):'No phone photo stored on the Waveshare.'"
    new = "$('photoState').textContent=capture&&capture.available?((capture.viewer?'Displaying now · ':'On Waveshare RAM · ')+num(capture.width,0)+'×'+num(capture.height,0)+' · '+Math.round(num(capture.bytes,0)/1024)+' KB · capture #'+capture.id):'No phone photo stored on the Waveshare.'"
    text = once(text, old, new, "physical viewer state copy")
    save(root, rel, text)


def patch_main_state_machine(root: Path) -> None:
    rel = "src/main.cpp"
    text = load(root, rel)
    if '#include "companion_web.h"' not in text:
        text = once(text, '#include "camera_client.h"\n', '#include "camera_client.h"\n#include "companion_web.h"\n', "Companion viewer state include")

    if "Phone-photo viewer is a first-class display override" not in text:
        fn = text.find("static void updateDisplayedPrinterScreenState() {")
        if fn < 0:
            raise PatchError("updateDisplayedPrinterScreenState not found")
        anchor = text.find("  if (!isAnyPrinterConfigured()) {", fn)
        if anchor < 0:
            raise PatchError("no-printer state derivation anchor not found")
        block = '''#if BOARD_HAS_CAMERA
  // Phone-photo viewer is a first-class display override, not a chamber-camera
  // stream. Keep it up even when the printer has no camera tile, is offline, or
  // no printer is configured. Auto-OTA is still allowed to take the display.
  if (current == SCREEN_CAMERA && companionWebViewerActive() && !isOtaAutoInProgress()) {
    return;
  }
#endif

'''
        text = text[:anchor] + block + text[anchor:]

    if "A phone photo has its own return target" not in text:
        fn = text.find("static void doTapActions() {")
        if fn < 0:
            raise PatchError("doTapActions not found")
        cam = text.find("  if (cur == SCREEN_CAMERA) {", fn)
        if cam < 0:
            raise PatchError("camera tap block not found")
        body = text.find("\n", cam) + 1
        block = '''    // A phone photo has its own return target and must not enter the chamber
    // camera / drying / printer-cycle tap behavior. One physical tap exits to
    // exactly the screen that was active before Show on Waveshare.
    if (companionWebViewerActive()) {
      companionWebViewerExitToReturnScreen();
      return;
    }
'''
        text = text[:body] + block + text[body:]

    save(root, rel, text)


def patch_standard_web(root: Path) -> None:
    rel = "web/app.js"
    text = load(root, rel)
    old = "q('v1130Phone').textContent=d.phone&&d.phone.connected?'Connected':'Available';q('v1130Photo').textContent=cap.available?('Photo ready · '+text(cap.width,'?')+'×'+text(cap.height,'?')):'No photo stored';classState(q('v1130PhoneChip'),cap.available?'good':'');"
    new = "q('v1130Phone').textContent=d.phone&&d.phone.connected?'Connected':'Available';q('v1130Photo').textContent=cap.available?((cap.viewer?'Displaying · ':'Photo ready · ')+text(cap.width,'?')+'×'+text(cap.height,'?')):'No photo stored';classState(q('v1130PhoneChip'),cap.viewer?'good':cap.available?'good':'');"
    text = once(text, old, new, "full web physical viewer visibility")
    save(root, rel, text)


def apply(root: Path) -> None:
    build = load(root, "include/smart_home_build.h")
    if MARKER in build:
        print(f"{MARKER} already applied")
        return
    if 'SMART_HOME_VERSION "v11.30"' not in build or 'Unified Web + Companion RC1' not in build:
        raise PatchError("v11.30 RC1 reconstructed source is required")
    patch_companion_api(root)
    patch_main_state_machine(root)
    patch_standard_web(root)
    patch_build(root)

    checks = {
        "include/smart_home_build.h": ['SMART_HOME_VERSION "v11.30"', 'Smart Home v11.30 Unified Web + Companion RC2', MARKER],
        "src/companion_web.h": ['companionWebViewerExitToReturnScreen();'],
        "src/companion_web.cpp": ['void companionWebViewerExitToReturnScreen()', "Waveshare did not enter phone-photo view", "Displaying now · "],
        "src/main.cpp": ['#include "companion_web.h"', 'current == SCREEN_CAMERA && companionWebViewerActive() && !isOtaAutoInProgress()', 'companionWebViewerExitToReturnScreen();', 'A phone photo has its own return target'],
        "web/app.js": ["cap.viewer?'Displaying · ':'Photo ready · '"],
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
    apply(Path(args.repo).resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
