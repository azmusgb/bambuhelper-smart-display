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
    text = once(
        text,
        'Smart Home v11.30 Unified Web + Companion RC1',
        'Smart Home v11.30 Unified Web + Companion RC2',
        "build label",
    )
    text += f"\n// {MARKER}\n"
    save(root, rel, text)


def patch_companion_api(root: Path) -> None:
    rel = "src/companion_web.h"
    text = load(root, rel)
    text = once(
        text,
        'bool companionWebViewerActive();\nvoid companionWebViewerDeactivate();\n',
        'bool companionWebViewerActive();\nvoid companionWebViewerDeactivate();\nvoid companionWebViewerExitToReturnScreen();\n',
        "viewer exit API declaration",
    )
    save(root, rel, text)

    rel = "src/companion_web.cpp"
    text = load(root, rel)
    text = once(
        text,
        'bool companionWebViewerActive() { return g_captureViewerActive; }\n\nvoid companionWebViewerDeactivate() { g_captureViewerActive = false; }\n',
        '''bool companionWebViewerActive() { return g_captureViewerActive; }\n\nvoid companionWebViewerDeactivate() { g_captureViewerActive = false; }\n\nvoid companionWebViewerExitToReturnScreen() {\n  if (!g_captureViewerActive) return;\n  const ScreenState target = g_captureViewerReturnScreen == SCREEN_CAMERA\n      ? SCREEN_IDLE : g_captureViewerReturnScreen;\n  // Clear the override before changing screen so setScreenState() does not\n  // interpret this deliberate exit as an external viewer cancellation.\n  g_captureViewerActive = false;\n  setScreenState(target);\n}\n''',
        "viewer exit implementation",
    )

    # Make the phone surface report the *confirmed* physical state. A 200 from
    # /capture/show is not enough; the state envelope must still report viewer=true
    # after the main display state machine has had a chance to run.
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
        text = once(
            text,
            '#include "camera_client.h"\n',
            '#include "camera_client.h"\n#include "companion_web.h"\n',
            "Companion viewer state include",
        )

    # This is the physical defect found during acceptance. SCREEN_CAMERA was
    # originally sticky only while a Bambu chamber stream remained possible.
    # A phone JPEG is independent of printer camera capability, so keep the
    # screen sticky while the explicit Companion override is active. Auto-OTA
    # remains allowed to preempt the viewer.
    anchor = '''  ledSetActivity(LED_ACT_IDLE);\n\n  if (!isAnyPrinterConfigured()) {\n'''
    replacement = '''  ledSetActivity(LED_ACT_IDLE);\n\n#if BOARD_HAS_CAMERA\n  // Phone-photo viewer is a first-class display override, not a chamber-camera\n  // stream. Keep it up even when the printer has no camera tile, is offline, or\n  // no printer is configured. Auto-OTA is still allowed to take the display.\n  if (current == SCREEN_CAMERA && companionWebViewerActive() && !isOtaAutoInProgress()) {\n    return;\n  }\n#endif\n\n  if (!isAnyPrinterConfigured()) {\n'''
    if "Phone-photo viewer is a first-class display override" not in text:
        text = once(text, anchor, replacement, "sticky phone viewer before printer state derivation")

    old = '''  if (cur == SCREEN_CAMERA) {\n    // Keep the drying peek reachable on camera boards by making it the next\n    // stop in the cycle: printing -> camera -> drying -> printing (+ next).\n    if (openDryPeek()) return;\n    setScreenState(SCREEN_PRINTING);\n    if (getActiveConnCount() >= 2) cycleDisplayedPrinterFromButton();\n    return;\n  }\n'''
    new = '''  if (cur == SCREEN_CAMERA) {\n    // A phone photo has its own return target and must not enter the chamber\n    // camera / drying / printer-cycle tap behavior. One physical tap exits to\n    // exactly the screen that was active before Show on Waveshare.\n    if (companionWebViewerActive()) {\n      companionWebViewerExitToReturnScreen();\n      return;\n    }\n    // Keep the drying peek reachable on camera boards by making it the next\n    // stop in the cycle: printing -> camera -> drying -> printing (+ next).\n    if (openDryPeek()) return;\n    setScreenState(SCREEN_PRINTING);\n    if (getActiveConnCount() >= 2) cycleDisplayedPrinterFromButton();\n    return;\n  }\n'''
    if "A phone photo has its own return target" not in text:
        text = once(text, old, new, "physical tap exits phone viewer")
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
        "include/smart_home_build.h": [
            'SMART_HOME_VERSION "v11.30"',
            'Smart Home v11.30 Unified Web + Companion RC2',
            MARKER,
        ],
        "src/companion_web.h": [
            'companionWebViewerExitToReturnScreen();',
        ],
        "src/companion_web.cpp": [
            'void companionWebViewerExitToReturnScreen()',
            "Waveshare did not enter phone-photo view",
            "Displaying now · ",
        ],
        "src/main.cpp": [
            '#include "companion_web.h"',
            'current == SCREEN_CAMERA && companionWebViewerActive() && !isOtaAutoInProgress()',
            'companionWebViewerExitToReturnScreen();',
            'A phone photo has its own return target',
        ],
        "web/app.js": [
            "cap.viewer?'Displaying · ':'Photo ready · '",
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
    apply(Path(args.repo).resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
