#!/usr/bin/env python3
"""Validate the 12.3.8 review fixes on the reconstructed tree (need/forbid).

The host tests prove the rules (tests/workshop_os12_press_gesture_smoke.cpp,
tests/workshop_os12_mic_meter_smoke.cpp, tests/workshop_os12_code_token_smoke.cpp).
This validator proves the device is wired to them:

* POST /login refuses a request without same-origin browser provenance
  before it reads the code, and the sign-in page sends its own Origin;
* the sign-in code key route has its own lock-out and never touches the
  portal sign-in one, and counts only a well-formed wsc_ key that does not
  match;
* each Local AI create refuses while the other prompt is up;
* Allow/Cancel answer only an armed press (PromptArm) that went down on the
  button; every touch-down starts a new press;
* a release acts only on the target it went down on; the outline follows the
  finger and is cleared on every path that ends a press; smartHubDraw
  repaints it only for a live press;
* /audio/mic/echo is gone; the meter removes DC; the audio task touches the
  recording only inside the gate, and the free waits for it.

It fails on the 12.3.7 tree.
"""
from __future__ import annotations

import argparse
from pathlib import Path


class ValidationError(RuntimeError):
    pass


def read(path: Path) -> str:
    if not path.is_file():
        raise ValidationError(f"missing file: {path}")
    return path.read_text(encoding="utf-8")


def need(text: str, needle: str, label: str) -> None:
    if needle not in text:
        raise ValidationError(f"missing {label}: {needle}")


def forbid(text: str, needle: str, label: str) -> None:
    if needle in text:
        raise ValidationError(f"forbidden {label}: {needle}")


def block(text: str, signature: str) -> str:
    start = text.find(signature)
    if start < 0:
        raise ValidationError(f"missing function: {signature}")
    brace = text.find("{", start + len(signature))
    depth = 0
    for i in range(brace, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    raise ValidationError(f"unterminated function: {signature}")


def ordered(text: str, needles: list[str], label: str) -> None:
    last = -1
    for needle in needles:
        at = text.find(needle, last + 1)
        if at < 0:
            raise ValidationError(f"missing or out of order {label}: {needle}")
        last = at


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    ap.add_argument("--source-root", default=str(Path(__file__).resolve().parents[1]))
    args = ap.parse_args()
    root = Path(args.repo).resolve()
    source_root = Path(args.source_root).resolve()

    build = read(root / "include/smart_home_build.h")
    web = read(root / "src/web_server.cpp")
    sec = read(root / "src/security_manager.cpp")
    sec_h = read(root / "include/security_manager.h")
    hub = read(root / "src/smart_hub.cpp")
    hub_h = read(root / "src/smart_hub.h")
    main_cpp = read(root / "src/main.cpp")
    es = read(root / "src/buzzer_backend_es8311.cpp")
    code_glue = read(root / "src/workshop_code_token.cpp")
    lite_glue = read(root / "src/workshop_status_lite.cpp")
    recipe = read(source_root / "scripts/run_os12_ux_local.sh")

    need(build, "#define WORKSHOP_OS12_REVIEW_HARDENING 1", "12.3.8 build identity")
    need(recipe, "apply_workshop_os12_review_hardening.py", "12.3.8 layer in the recipe")
    for installed, source in (
        ("include/workshop_press_gesture.hpp", "firmware/platform/ui/press_gesture.hpp"),
        ("include/workshop_mic_meter.hpp", "firmware/platform/media/mic_meter.hpp"),
    ):
        if read(root / installed) != read(source_root / source):
            raise ValidationError(f"installed {installed} differs from {source}")

    # ---- sign-in ---------------------------------------------------------
    need(sec_h, "bool securitySameOrigin(WebServer& server);", "same-origin API")
    need(block(sec, "bool securitySameOrigin(WebServer& server)"), "return sameOrigin(server);",
         "same-origin API uses the mutation check")
    login = block(web, "static void handlePortalLoginSubmit()")
    ordered(login, ["if (!securitySameOrigin(server))", "server.send(403,", "return;",
                    'server.hasArg("code")', "securityLogin("], "cross-site sign-in refused before the code is read")
    refused = login.split("if (!securitySameOrigin(server))", 1)[1].split("return;", 1)[0]
    for counted in ("securityLogin", "NoteLoginFailure", "noteLoginFailure"):
        forbid(refused, counted, "refused sign-in counted as a failure")
    page = block(web, "static void sendPortalLoginPage(")
    need(page, 'server.sendHeader("Referrer-Policy", "same-origin");', "sign-in page sends its own Origin")
    forbid(page, '"Referrer-Policy", "no-referrer"', "sign-in page policy that makes browsers send Origin: null")

    read_handler = block(code_glue, "void workshopPortalCodeHandleRead(WebServer& server)")
    for shared in ("securityLoginRetryAfter", "securityNoteLoginFailure"):
        forbid(code_glue, shared, "code key route sharing the portal sign-in lock-out")
    ordered(read_handler, [
        "if (isAPMode())",
        "g_limiter.admit(client, now)",
        'server.header("Authorization")',
        "presentedCodeKey(header.c_str(), presented)",
        "digestEqual(digest, g_digest)",
        "if (keyFailureCounts(kind, valid)) g_limiter.noteFailure(client, now);",
        "sendJson(server, 401,",
        "g_limiter.noteSuccess(client, now);",
    ], "code key route (own rate limit, only a wrong wsc_ key counts)")
    if read_handler.count("g_limiter.noteFailure(") != 1:
        raise ValidationError("code key route must count failures in exactly one place")

    code_create = block(code_glue, "void workshopCodeTokenHandleCreate(WebServer& server)")
    ordered(code_create, ["workshopStatusTokenPromptVisible()", "sendJson(server, 409,", "g_flow.start("],
            "code key create refuses while the status prompt is up")
    lite_create = block(lite_glue, "void workshopStatusTokenHandleCreate(WebServer& server)")
    ordered(lite_create, ["workshopCodeTokenPromptVisible()", "sendJson(server, 409,", "g_flow.start("],
            "status token create refuses while the code key prompt is up")
    need(lite_glue, '#if __has_include("workshop_code_token.h")', "status token sees the code key prompt")

    # ---- touchscreen approval -------------------------------------------
    need(hub, '#include "workshop_press_gesture.hpp"', "press gesture header")
    for prefix, arm, allow, deny in (
        ("Status", "g_statusPromptArm", "workshopStatusTokenAllow();", "workshopStatusTokenDeny();"),
        ("Code", "g_codePromptArm", "workshopCodeTokenAllow();", "workshopCodeTokenDeny();"),
    ):
        touch = block(hub, f"static bool hub{prefix}TokenPromptTouch(int16_t x,int16_t y)")
        need(touch, f"{arm}.tapAccepted(g_hubPress,hubBox(hub{prefix}TokenAllowRect()),x,y)){{{allow}",
             f"{prefix} Allow only for an armed press on Allow")
        need(touch, f"{arm}.tapAccepted(g_hubPress,hubBox(hub{prefix}TokenCancelRect()),x,y)){{{deny}",
             f"{prefix} Cancel only for an armed press on Cancel")
        forbid(touch, f"hub{prefix}TokenAllowRect().contains(x,y)", f"{prefix} Allow on the release point alone")
        draw = block(hub, f"static bool hub{prefix}TokenPromptDraw(bool force)")
        need(draw, f"{arm}.shown(millis());", f"{prefix} prompt arms when drawn")
        need(draw, f"{arm}.hidden();", f"{prefix} prompt disarms when gone")
        need(block(hub, f"static void hub{prefix}TokenPromptService()"), f"if(!visible){arm}.hidden();",
             f"{prefix} prompt disarms even off the hub")
    down = block(hub, "void smartHubTouchDown(uint16_t rawX, uint16_t rawY)")
    ordered(down, ["g_hubPress.cancel();", "g_hubPress.down(x, y, millis(),"], "every touch-down starts a new press")
    forbid(down, "PromptVisible()) return;", "touch-down skipped while a prompt is up")

    # ---- outline and release --------------------------------------------
    handle = block(hub, "bool smartHubHandleTouch(uint16_t rawX, uint16_t rawY, bool longPress)")
    ordered(handle, [
        "HubPressEnd pressEnds;",
        "if (g_hubPressShown) { g_hubPressShown = false; g_dirty = true; }",
        "if(hubStatusTokenPromptTouch(x,y))return true;",
        "if(hubCodeTokenPromptTouch(x,y))return true;",
        "g_hubPress.releaseFires((uint8_t)cur,",
        "wsMoreTouch(x,y,longPress)",
        "hubNavRect(i).contains(x,y)",
    ], "release acts only on the pressed target")
    need(hub, "struct HubPressEnd { ~HubPressEnd() { g_hubPress.cancel(); } };", "press ends with the release")
    move = block(hub, "void smartHubTouchMove(uint16_t rawX, uint16_t rawY)")
    need(move, "g_hubPress.outlineVisible(", "outline follows the finger")
    need(move, "g_hubPressShown = false;", "outline removed when the finger leaves")
    cancel = block(hub, "void smartHubTouchCancel()")
    need(cancel, "g_hubPress.cancel();", "cancel ends the press")
    need(cancel, "if (g_hubPressShown) { g_hubPressShown = false; g_dirty = true; }", "cancel clears the outline")
    draw = block(hub, "void smartHubDraw(ScreenState screen, bool forceRedraw)")
    ordered(draw, ["if (g_hubPressShown && !hubPressStillValid(screen)) g_hubPressShown = false;",
                   "if (g_hubPressShown) hubPaintPressed(g_hubFrame);"], "no stale outline repainted")
    valid = block(hub, "static bool hubPressStillValid(ScreenState screen)")
    need(valid, "g_hubPress.active()", "outline needs a live press")
    need(valid, "g_hubPress.screen()", "outline needs the same screen")
    need(valid, "hubPressRect(g_hubPress.downX(), g_hubPress.downY(), r)", "outline needs the same target")
    for decl in ("void smartHubTouchMove(uint16_t rawX, uint16_t rawY);", "void smartHubTouchCancel();"):
        need(hub_h, decl, "hub press API")
    need(hub, "void smartHubTouchMove(uint16_t, uint16_t) {}", "non-hub stub")
    need(hub, "void smartHubTouchCancel() {}", "non-hub stub")

    wake = block(main_cpp, "static void handleWakeButton()")
    ordered(wake, [
        "if (hubTouchHasPoint) smartHubTouchDown(hubTouchX, hubTouchY);",
        "else smartHubTouchMove(x, y);",
        "if (hmsScreenAlerting() && openHmsScreen(HMS_SCREEN_MS)) {",
        "smartHubTouchCancel();  // 12.3.8: the press ends here; clear its outline",
        "smartHubHandleTouch(hubTouchX, hubTouchY, hubTouchMaxHoldMs >= 650);",
        "smartHubTouchCancel();\n        smartHubAdvance();",
        "if (hubTouchTracking) smartHubTouchCancel();",
    ], "every path that ends a press clears it")

    # ---- audio -------------------------------------------------------------
    forbid(web, "/audio/mic/echo", "echo route outside MediaService")
    forbid(web, "handleAudioMicEcho", "echo handler")
    need(es, '#include "workshop_mic_meter.hpp"', "meter header")
    meter = block(es, "void os12MeterChunk(const int16_t* s, size_t count)")
    need(meter, "c.peak = gOs12DcMeter.chunkPeak(s, count);", "meter peak without DC")
    forbid(meter, "if (a > peak) peak = a;", "meter peak of raw samples")
    read_mic = block(es, "void os12ReadMic(int16_t* rx, size_t rxBytes)")
    ordered(read_mic, ["gOs12RecGate.enter()", "os12StoreChunk(", "gOs12RecGate.leave();"],
            "recording stored inside the gate")
    task = block(es, "void audioTask(void*)")
    ordered(task, ["gOs12RecGate.enter()", "renderChunk(", "gOs12RecGate.leave();"], "playback inside the gate")
    free_fn = block(es, "bool os12FreeRecording()")
    ordered(free_fn, ["gOs12RecordingActive = false;", "gOs12PlaybackActive = false;", "gOs12RecGate.close();",
                      "gOs12RecGate.idle()", "free(gOs12RecordingData);"], "free waits for the audio task")
    begin = block(es, "bool buzzerBackendMicRecordBegin(uint32_t maxDurationMs)")
    ordered(begin, ["if (!os12FreeRecording()) return false;", "heap_caps_malloc(",
                    "gOs12RecordingActive = true;", "gOs12RecGate.open();"], "gate reopens after the new clip is set up")

    print("PASS: 12.3.8 review fixes: same-origin sign-in, separate code key lock-out, one prompt at a time, "
          "armed prompts, press acts on its own target with a live outline, no echo route, DC-free meter, "
          "gated recording buffer")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ValidationError as exc:
        print(f"FAIL: {exc}")
        raise SystemExit(1)
