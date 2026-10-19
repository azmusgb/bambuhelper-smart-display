#!/usr/bin/env python3
"""Workshop OS 12.3.8: fixes from the 12.3.6 firmware review.

Runs after apply_workshop_os12_touch_audio_fit.py and changes whole
functions of that layer and of the sign-in layers before it.

Sign-in (web_server.cpp, security_manager.cpp/.h):
- POST /login checks the browser's Origin/Referer like every other mutation,
  so a cross-site form cannot submit codes (and so cannot run up the owner's
  sign-in lock-out from the owner's own browser). A refused request is not a
  failed sign-in. The sign-in page now uses Referrer-Policy: same-origin, so
  its own form sends its Origin (no-referrer made browsers send "null").
- The sign-in code key route keeps its own lock-out (in
  firmware/platform/code_token/workshop_code_token.cpp, installed by the code
  key layer); this layer only adds securitySameOrigin() for /login.

Touchscreen approval (smart_hub.cpp):
- Allow and Cancel on the Local AI prompts answer only a press that went down
  on that button at least 500 ms after the prompt was first drawn, and was
  released on it (include/workshop_press_gesture.hpp, host-tested).

Touch-down outline (smart_hub.cpp, smart_hub.h, main.cpp):
- A press acts only on the target it went down on: lifting the finger off
  that target cancels it, like a standard button. The outline follows the
  finger: it goes when the finger leaves the target and comes back with it.
- The outline is cleared on every path that ends a press: release, the HMS
  alert taking the release, a release without a point, and leaving the hub
  mid-press. smartHubDraw repaints it only for a live press on the same
  screen whose target is still under the press point.

Audio (buzzer_backend_es8311.cpp, web_server.cpp):
- POST /audio/mic/echo is removed. Nothing in the portal or the touchscreen
  used it, and it drove the codec around MediaService.
- The microphone meter removes a running DC estimate per slot before taking
  the peak (include/workshop_mic_meter.hpp, host-tested).
- The recording buffer is handed over through a gate: the audio task enters
  it before copying into or playing the clip, and the main loop closes it and
  waits for the task to leave before it frees or replaces the buffer.
"""
from __future__ import annotations

import argparse
import shutil
import sys as _sys
from pathlib import Path

_here = Path(__file__).resolve().parent
if str(_here) not in _sys.path:
    _sys.path.insert(0, str(_here))
from scripts.smart_home_patch_utils import PatchError, replace_cpp_function  # noqa: E402

BUILD_MARKER = "#define WORKSHOP_OS12_REVIEW_HARDENING 1"
TOUCH_AUDIO_MARKER = "#define WORKSHOP_OS12_TOUCH_AUDIO_FIT 1"

HEADERS = (
    (Path("firmware") / "platform" / "ui" / "press_gesture.hpp", Path("include") / "workshop_press_gesture.hpp"),
    (Path("firmware") / "platform" / "media" / "mic_meter.hpp", Path("include") / "workshop_mic_meter.hpp"),
)


def load(path: Path) -> str:
    if not path.is_file():
        raise PatchError(f"missing {path}")
    return path.read_text(encoding="utf-8")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise PatchError(f"{label}: expected exactly one anchor, found {count}")
    return text.replace(old, new, 1)


# ---------------------------------------------------------------------------
# security_manager / web_server: same-origin sign-in, no echo route
# ---------------------------------------------------------------------------

SEC_H_OLD = "bool securityAuthorize(WebServer& server, bool mutating);\n"
SEC_H_NEW = SEC_H_OLD + (
    "// 12.3.8: true when the request carries the browser's own same-origin\n"
    "// provenance (Origin, or Referer when Origin is absent). Used by POST /login.\n"
    "bool securitySameOrigin(WebServer& server);\n"
)

SEC_CPP_OLD = "bool securityAuthorize(WebServer& server, bool mutating) {\n"
SEC_CPP_NEW = (
    "bool securitySameOrigin(WebServer& server) {\n"
    "  return sameOrigin(server);\n"
    "}\n\n" + SEC_CPP_OLD
)

LOGIN_SIGNATURE = "static void handlePortalLoginSubmit()"
LOGIN_NEW = """static void handlePortalLoginSubmit() {
  // 12.3.8: sign-in is a mutation too. A form on another site must not be
  // able to submit codes from the owner's browser (each wrong one would count
  // toward this address's lock-out). A refused request is not a failed
  // sign-in and does not touch the lock-out.
  if (!securitySameOrigin(server)) {
    server.sendHeader("Cache-Control", "no-store");
    server.send(403, "application/json",
        "{\\"status\\":\\"error\\",\\"message\\":\\"Rejected by Workshop OS same-origin protection.\\"}");
    return;
  }
  if (!server.hasArg("code")) {
    sendPortalLoginPage(PortalLoginPageState::InvalidCode);
    return;
  }

  uint32_t retryAfterSeconds = 0;
  const SecurityLoginResult result = securityLogin(server, server.arg("code"), retryAfterSeconds);
  if (result == SecurityLoginResult::RateLimited) {
    sendPortalLoginPage(PortalLoginPageState::RateLimited, retryAfterSeconds);
    return;
  }
  if (result != SecurityLoginResult::Success) {
    sendPortalLoginPage(PortalLoginPageState::InvalidCode);
    return;
  }

  server.sendHeader("Location", "/");
  server.send(303, "text/plain", "Signed in");
}
"""

# Browsers send "Origin: null" (and no Referer) on a form POST from a page
# served with Referrer-Policy: no-referrer, which the same-origin check must
# refuse. "same-origin" sends the page's own origin to the device itself and
# still nothing to any other site.
LOGIN_POLICY_OLD = '  server.sendHeader("Referrer-Policy", "no-referrer");\n'
LOGIN_POLICY_NEW = (
    '  // 12.3.8: same-origin, so the sign-in form\'s POST carries this page\'s\n'
    '  // Origin (no-referrer makes browsers send "Origin: null").\n'
    '  server.sendHeader("Referrer-Policy", "same-origin");\n'
)

ECHO_SIGNATURE = "static void handleAudioMicEcho()"
ECHO_ROUTE = '  SECURE_POST("/audio/mic/echo", handleAudioMicEcho);\n'


def patch_web(repo: Path) -> None:
    sec_h = repo / "include" / "security_manager.h"
    sec_h.write_text(replace_once(load(sec_h), SEC_H_OLD, SEC_H_NEW, "securitySameOrigin declaration"),
                     encoding="utf-8")
    sec = repo / "src" / "security_manager.cpp"
    sec.write_text(replace_once(load(sec), SEC_CPP_OLD, SEC_CPP_NEW, "securitySameOrigin"), encoding="utf-8")

    web = repo / "src" / "web_server.cpp"
    text = load(web)
    if "PortalLoginPageState::RateLimited" not in text:
        raise PatchError("web_server.cpp lacks the hardened sign-in page (portal login layer)")
    text = replace_cpp_function(text, LOGIN_SIGNATURE, LOGIN_NEW, "POST /login")
    text = replace_once(text, LOGIN_POLICY_OLD, LOGIN_POLICY_NEW, "sign-in page referrer policy")
    # The echo test is unused (no portal or touchscreen caller) and drives the
    # codec outside MediaService. Remove the route and its handler.
    text = replace_once(text, ECHO_ROUTE, "", "/audio/mic/echo route")
    text = replace_cpp_function(text, ECHO_SIGNATURE, "", "echo handler")
    web.write_text(text, encoding="utf-8")


# ---------------------------------------------------------------------------
# smart_hub.cpp: press tracking, prompt arming, outline
# ---------------------------------------------------------------------------

HUB_INCLUDE_OLD = '#include "workshop_frame_diff.hpp"\n'
HUB_INCLUDE_NEW = HUB_INCLUDE_OLD + '#include "workshop_press_gesture.hpp"\n'

HUB_STATE_OLD = "static bool g_hubPressShown = false;\n"
HUB_STATE_NEW = HUB_STATE_OLD + """// 12.3.8: the press in progress (touch-down to release) and the arming of
// the two Local AI prompts (workshop_press_gesture.hpp).
namespace wpress = workshop::ui::press;
static wpress::Tracker g_hubPress;
static wpress::PromptArm g_statusPromptArm;
static wpress::PromptArm g_codePromptArm;
template <class R> static wpress::Box hubBox(const R& r) { return wpress::makeBox(r.x, r.y, r.w, r.h); }
"""

STATUS_SERVICE_OLD = """static void hubStatusTokenPromptService() {
  const bool visible=workshopStatusTokenPromptVisible();
"""
STATUS_SERVICE_NEW = STATUS_SERVICE_OLD + "  if(!visible)g_statusPromptArm.hidden();  // 12.3.8: the next prompt arms afresh\n"
CODE_SERVICE_OLD = """static void hubCodeTokenPromptService() {
  const bool visible=workshopCodeTokenPromptVisible();
"""
CODE_SERVICE_NEW = CODE_SERVICE_OLD + "  if(!visible)g_codePromptArm.hidden();  // 12.3.8: the next prompt arms afresh\n"

STATUS_HIDE_OLD = "    if(g_statusTokenPromptShown){g_statusTokenPromptShown=false;g_dirty=true;}\n"
STATUS_HIDE_NEW = "    g_statusPromptArm.hidden();\n" + STATUS_HIDE_OLD
CODE_HIDE_OLD = "    if(g_codeTokenPromptShown){g_codeTokenPromptShown=false;g_dirty=true;}\n"
CODE_HIDE_NEW = "    g_codePromptArm.hidden();\n" + CODE_HIDE_OLD

STATUS_SHOWN_OLD = "g_statusTokenPromptShown=true;g_statusTokenPromptSecond=second;"
STATUS_SHOWN_NEW = STATUS_SHOWN_OLD + "g_statusPromptArm.shown(millis());"
CODE_SHOWN_OLD = "g_codeTokenPromptShown=true;g_codeTokenPromptSecond=second;"
CODE_SHOWN_NEW = CODE_SHOWN_OLD + "g_codePromptArm.shown(millis());"

STATUS_TOUCH_SIGNATURE = "static bool hubStatusTokenPromptTouch(int16_t x,int16_t y)"
STATUS_TOUCH_NEW = """static bool hubStatusTokenPromptTouch(int16_t x,int16_t y) {
  if(!workshopStatusTokenPromptVisible())return false;
  // 12.3.8: only a press that went down on the button at least
  // wpress::kPromptArmMs after the prompt was drawn, and was released on it.
  // A finger already on the panel when the prompt appeared answers nothing.
  if(g_statusPromptArm.tapAccepted(g_hubPress,hubBox(hubStatusTokenAllowRect()),x,y)){workshopStatusTokenAllow();g_dirty=true;return true;}
  if(g_statusPromptArm.tapAccepted(g_hubPress,hubBox(hubStatusTokenCancelRect()),x,y)){workshopStatusTokenDeny();g_dirty=true;return true;}
  return true;
}
"""
CODE_TOUCH_SIGNATURE = "static bool hubCodeTokenPromptTouch(int16_t x,int16_t y)"
CODE_TOUCH_NEW = """static bool hubCodeTokenPromptTouch(int16_t x,int16_t y) {
  if(!workshopCodeTokenPromptVisible())return false;
  // 12.3.8: same arming as the status prompt (workshop_press_gesture.hpp).
  if(g_codePromptArm.tapAccepted(g_hubPress,hubBox(hubCodeTokenAllowRect()),x,y)){workshopCodeTokenAllow();g_dirty=true;return true;}
  if(g_codePromptArm.tapAccepted(g_hubPress,hubBox(hubCodeTokenCancelRect()),x,y)){workshopCodeTokenDeny();g_dirty=true;return true;}
  return true;
}
"""

PRESS_RECT_SIGNATURE = "static bool hubPressRect(int16_t x, int16_t y, wsm::Rect& out)"
PRESS_VALID = """
// 12.3.8: whether the outline in g_hubPressRect still shows what a release
// at the press point would do: a live press, on the screen it went down on,
// no prompt up, and the same target still under the point.
static bool hubPressStillValid(ScreenState screen) {
  if (!g_hubPress.active() || (uint8_t)screen != g_hubPress.screen()) return false;
  if (workshopStatusTokenPromptVisible() || workshopCodeTokenPromptVisible()) return false;
  wsm::Rect r = wsm::makeRect(0, 0, 0, 0);
  if (!hubPressRect(g_hubPress.downX(), g_hubPress.downY(), r)) return false;
  return wpress::sameBox(hubBox(r), g_hubPress.target()) && wpress::sameBox(hubBox(r), hubBox(g_hubPressRect));
}
"""

DRAW_OUTLINE_OLD = "      if (g_hubPressShown) hubPaintPressed(g_hubFrame);\n"
DRAW_OUTLINE_NEW = (
    "      // 12.3.8: never repaint an outline that no longer matches the press.\n"
    "      if (g_hubPressShown && !hubPressStillValid(screen)) g_hubPressShown = false;\n"
    + DRAW_OUTLINE_OLD
)

TOUCH_DOWN_SIGNATURE = "void smartHubTouchDown(uint16_t rawX, uint16_t rawY)"
TOUCH_DOWN_NEW = """void smartHubTouchDown(uint16_t rawX, uint16_t rawY) {
  // 12.3.8: every touch-down starts a new press, prompt or not, so the
  // prompts can tell a fresh press from a finger that was already down.
  g_hubPress.cancel();
  if (!g_cfg.enabled || !smartHubIsScreen(getScreenState())) return;
  int16_t x = 0, y = 0;
  mapHubTouch(rawX, rawY, x, y);
  const bool prompt = workshopStatusTokenPromptVisible() || workshopCodeTokenPromptVisible();
  wsm::Rect r = wsm::makeRect(0, 0, 0, 0);
  const bool target = !prompt && hubPressRect(x, y, r);
  g_hubPress.down(x, y, millis(), (uint8_t)getScreenState(), target ? hubBox(r) : wpress::noBox());
  if (target) hubDrawPressed(r);
}

// 12.3.8: the finger moved while down. The outline shows only while it is on
// the target the press went down on (and so would fire on release).
void smartHubTouchMove(uint16_t rawX, uint16_t rawY) {
  if (!g_hubPress.active() || !g_cfg.enabled || !smartHubIsScreen(getScreenState())) return;
  int16_t x = 0, y = 0;
  mapHubTouch(rawX, rawY, x, y);
  const bool on = g_hubPress.outlineVisible((uint8_t)getScreenState(), x, y);
  if (on && !g_hubPressShown) {
    // Back on the target: outline it again if it is still the same target.
    const wpress::Box& b = g_hubPress.target();
    const wsm::Rect r = wsm::makeRect(b.x, b.y, b.w, b.h);
    wsm::Rect now = wsm::makeRect(0, 0, 0, 0);
    if (!workshopStatusTokenPromptVisible() && !workshopCodeTokenPromptVisible() &&
        hubPressRect(g_hubPress.downX(), g_hubPress.downY(), now) && wpress::sameBox(hubBox(now), b)) {
      hubDrawPressed(r);
    }
  } else if (!on && g_hubPressShown) {
    // Redraw the page without it (hubDrawPressed already marked its rows).
    g_hubPressShown = false;
    g_dirty = true;
  }
}

// 12.3.8: a press ended without reaching smartHubHandleTouch (the HMS alert
// took the release, no point was read, or the screen left the hub).
void smartHubTouchCancel() {
  g_hubPress.cancel();
  smartHubUpdateHoldProgress(0, 0, 0);
  if (g_hubPressShown) { g_hubPressShown = false; g_dirty = true; }
}
"""

HANDLE_TOUCH_SIGNATURE = "bool smartHubHandleTouch(uint16_t rawX, uint16_t rawY, bool longPress)"
HANDLE_TOUCH_NEW = """// 12.3.8: the press ends with smartHubHandleTouch, whichever way it returns.
struct HubPressEnd { ~HubPressEnd() { g_hubPress.cancel(); } };

bool smartHubHandleTouch(uint16_t rawX, uint16_t rawY, bool longPress) {
  HubPressEnd pressEnds;
  smartHubUpdateHoldProgress(rawX,rawY,0);
  if (g_hubPressShown) { g_hubPressShown = false; g_dirty = true; }
  if (!g_cfg.enabled || !smartHubIsScreen(getScreenState())) return false;
  int16_t x=0,y=0;mapHubTouch(rawX,rawY,x,y);ScreenState cur=getScreenState();
  if(hubStatusTokenPromptTouch(x,y))return true;
  if(hubCodeTokenPromptTouch(x,y))return true;
  // 12.3.8: a press acts only on the target it went down on, on the screen it
  // went down on. Lifting the finger anywhere else cancels it.
  {
    wsm::Rect r = wsm::makeRect(0, 0, 0, 0);
    const bool hit = hubPressRect(x, y, r);
    if (!g_hubPress.releaseFires((uint8_t)cur, hit ? hubBox(r) : wpress::noBox())) return true;
  }
  // The More pages own all of their touch, tab bar included.
  if(cur==SCREEN_HUB_MORE||cur==SCREEN_HUB_SYSTEM||cur==SCREEN_HUB_CUSTOM)return wsMoreTouch(x,y,longPress);
  // Home, Printer and Workshop own their touch too (tab bar included).
  if(cur==SCREEN_HUB_HOME)return wtHomeTouch(x,y);
  if(cur==SCREEN_HUB_PRINTER)return wtPrinterTouch(x,y,longPress);
  if(cur==SCREEN_HUB_WORKSHOP)return wtWorkshopTouch(x,y);
  if(hubTabBarLive(cur))for(uint8_t i=0;i<4;i++)if(hubNavRect(i).contains(x,y)){if(i==0)setPage(SCREEN_HUB_HOME);else if(i==1)setPage(SCREEN_HUB_PRINTER);else if(i==2)setPage(SCREEN_HUB_WORKSHOP);else wsOpen(wsm::PageId::Root);return true;}
  return true;
}
"""
HANDLE_TOUCH_BODY_OLD = """  if(hubStatusTokenPromptTouch(x,y))return true;
  if(hubCodeTokenPromptTouch(x,y))return true;
  // The More pages own all of their touch, tab bar included.
  if(cur==SCREEN_HUB_MORE||cur==SCREEN_HUB_SYSTEM||cur==SCREEN_HUB_CUSTOM)return wsMoreTouch(x,y,longPress);
  // Home, Printer and Workshop own their touch too (tab bar included).
  if(cur==SCREEN_HUB_HOME)return wtHomeTouch(x,y);
  if(cur==SCREEN_HUB_PRINTER)return wtPrinterTouch(x,y,longPress);
  if(cur==SCREEN_HUB_WORKSHOP)return wtWorkshopTouch(x,y);
"""

STUB_OLD = "void smartHubTouchDown(uint16_t, uint16_t) {}\n"
STUB_NEW = STUB_OLD + "void smartHubTouchMove(uint16_t, uint16_t) {}\nvoid smartHubTouchCancel() {}\n"

HEADER_OLD = "void smartHubTouchDown(uint16_t rawX, uint16_t rawY);\n"
HEADER_NEW = HEADER_OLD + """// 12.3.8: the finger moved while down (the outline follows it on and off the
// pressed target), and a press that ended without smartHubHandleTouch.
void smartHubTouchMove(uint16_t rawX, uint16_t rawY);
void smartHubTouchCancel();
"""

MAIN_DOWN_OLD = """      hubTouchHasPoint = buttonGetTouchPosition(&hubTouchX, &hubTouchY);
      // 12.3.6: show which control the finger is on before anything else.
      if (hubTouchHasPoint) smartHubTouchDown(hubTouchX, hubTouchY);
"""
MAIN_DOWN_NEW = """      hubTouchHasPoint = buttonGetTouchPosition(&hubTouchX, &hubTouchY);
      // 12.3.6: show which control the finger is on before anything else.
      if (hubTouchHasPoint) smartHubTouchDown(hubTouchX, hubTouchY);
      hubTouchDownSent = hubTouchHasPoint;
"""
MAIN_STATE_OLD = "  static uint32_t hubTouchMaxHoldMs = 0;\n"
MAIN_STATE_NEW = MAIN_STATE_OLD + "  static bool hubTouchDownSent = false;  // 12.3.8: the hub knows where this press went down\n"
MAIN_MOVE_OLD = """      if (buttonGetTouchPosition(&x, &y)) {
        hubTouchX = x; hubTouchY = y; hubTouchHasPoint = true;
      }
"""
MAIN_MOVE_NEW = """      if (buttonGetTouchPosition(&x, &y)) {
        hubTouchX = x; hubTouchY = y; hubTouchHasPoint = true;
        // 12.3.8: the first point of a press is its touch-down; later points
        // move the finger (the outline follows what a release would do).
        if (!hubTouchDownSent) { smartHubTouchDown(x, y); hubTouchDownSent = true; }
        else smartHubTouchMove(x, y);
      }
"""
MAIN_RELEASE_OLD = """      if (hmsScreenAlerting() && openHmsScreen(HMS_SCREEN_MS)) {
        // Error detail retains priority over navigation.
      } else if (hubTouchHasPoint) {
        smartHubHandleTouch(hubTouchX, hubTouchY, hubTouchMaxHoldMs >= 650);
      } else {
        smartHubAdvance();
      }
      hubTouchTracking = false;
"""
MAIN_RELEASE_NEW = """      if (hmsScreenAlerting() && openHmsScreen(HMS_SCREEN_MS)) {
        // Error detail retains priority over navigation.
        smartHubTouchCancel();  // 12.3.8: the press ends here; clear its outline
      } else if (hubTouchHasPoint) {
        smartHubHandleTouch(hubTouchX, hubTouchY, hubTouchMaxHoldMs >= 650);
      } else {
        smartHubTouchCancel();
        smartHubAdvance();
      }
      hubTouchTracking = false;
      hubTouchDownSent = false;
"""
MAIN_LEAVE_OLD = """  } else {
    hubTouchTracking = false;
    hubTouchWasHeld = false;
"""
MAIN_LEAVE_NEW = """  } else {
    // 12.3.8: the screen left the hub mid-press; drop the press and its outline.
    if (hubTouchTracking) smartHubTouchCancel();
    hubTouchDownSent = false;
    hubTouchTracking = false;
    hubTouchWasHeld = false;
"""


def patch_hub(repo: Path) -> None:
    path = repo / "src" / "smart_hub.cpp"
    text = load(path)
    for needle in ("static void hubDrawPressed(const wsm::Rect& r)", "hubCodeTokenPromptDraw(effectiveForce)"):
        if needle not in text:
            raise PatchError(f"smart_hub.cpp lacks {needle} (12.3.6 touch layer or code key layer missing)")
    if HANDLE_TOUCH_BODY_OLD not in text:
        raise PatchError("smartHubHandleTouch differs from the 12.3.6 layer's version")
    text = replace_once(text, HUB_INCLUDE_OLD, HUB_INCLUDE_NEW, "press gesture include")
    text = replace_once(text, HUB_STATE_OLD, HUB_STATE_NEW, "press state")
    text = replace_once(text, STATUS_SERVICE_OLD, STATUS_SERVICE_NEW, "status prompt service")
    text = replace_once(text, CODE_SERVICE_OLD, CODE_SERVICE_NEW, "code prompt service")
    text = replace_once(text, STATUS_HIDE_OLD, STATUS_HIDE_NEW, "status prompt hidden")
    text = replace_once(text, CODE_HIDE_OLD, CODE_HIDE_NEW, "code prompt hidden")
    text = replace_once(text, STATUS_SHOWN_OLD, STATUS_SHOWN_NEW, "status prompt shown")
    text = replace_once(text, CODE_SHOWN_OLD, CODE_SHOWN_NEW, "code prompt shown")
    text = replace_cpp_function(text, STATUS_TOUCH_SIGNATURE, STATUS_TOUCH_NEW, "status prompt touch")
    text = replace_cpp_function(text, CODE_TOUCH_SIGNATURE, CODE_TOUCH_NEW, "code prompt touch")
    # hubPressStillValid goes right after hubPressRect.
    start = text.find(PRESS_RECT_SIGNATURE)
    if start < 0 or text.count(PRESS_RECT_SIGNATURE) != 1:
        raise PatchError("hubPressRect not found once")
    end = text.find("\n}\n", start)
    if end < 0:
        raise PatchError("hubPressRect end not found")
    end += 3
    text = text[:end] + PRESS_VALID + text[end:]
    text = replace_once(text, DRAW_OUTLINE_OLD, DRAW_OUTLINE_NEW, "smartHubDraw outline")
    text = replace_cpp_function(text, TOUCH_DOWN_SIGNATURE, TOUCH_DOWN_NEW, "touch-down")
    text = replace_cpp_function(text, HANDLE_TOUCH_SIGNATURE, HANDLE_TOUCH_NEW, "smartHubHandleTouch")
    text = replace_once(text, STUB_OLD, STUB_NEW, "non-hub stubs")
    path.write_text(text, encoding="utf-8")

    header = repo / "src" / "smart_hub.h"
    header.write_text(replace_once(load(header), HEADER_OLD, HEADER_NEW, "smart_hub.h declarations"),
                      encoding="utf-8")

    main = repo / "src" / "main.cpp"
    mtext = load(main)
    mtext = replace_once(mtext, MAIN_STATE_OLD, MAIN_STATE_NEW, "press-down state")
    mtext = replace_once(mtext, MAIN_DOWN_OLD, MAIN_DOWN_NEW, "touch-down")
    mtext = replace_once(mtext, MAIN_MOVE_OLD, MAIN_MOVE_NEW, "touch move")
    mtext = replace_once(mtext, MAIN_RELEASE_OLD, MAIN_RELEASE_NEW, "release paths")
    mtext = replace_once(mtext, MAIN_LEAVE_OLD, MAIN_LEAVE_NEW, "leaving the hub mid-press")
    main.write_text(mtext, encoding="utf-8")


# ---------------------------------------------------------------------------
# buzzer_backend_es8311.cpp: DC-free meter, recording buffer gate
# ---------------------------------------------------------------------------

ES_INCLUDE_OLD = '#include "workshop_recording_dsp.hpp"\n'
ES_INCLUDE_NEW = ES_INCLUDE_OLD + '#include "workshop_mic_meter.hpp"\n'

ES_STATE_OLD = "volatile uint32_t gOs12MicSampleCount = 0;\n"
ES_STATE_NEW = ES_STATE_OLD + """// 12.3.8: the meter's running DC estimate (audio task only), and the gate
// that hands the recording buffer between the main loop and the audio task
// (workshop_mic_meter.hpp).
workshop::media::meter::DcMeter gOs12DcMeter;
workshop::media::meter::BufferGate gOs12RecGate;
volatile uint32_t gOs12RecGateTimeouts = 0;
"""

METER_SIGNATURE = "void os12MeterChunk(const int16_t* s, size_t count)"
METER_NEW = """void os12MeterChunk(const int16_t* s, size_t count) {
  Os12MicChunk c;
  c.minSample = INT16_MAX;
  c.maxSample = INT16_MIN;
  uint32_t nz = 0;
  for (size_t i = 0; i < count; ++i) {
    const int16_t v = s[i];
    if (v) ++nz;
    if (v < c.minSample) c.minSample = v;
    if (v > c.maxSample) c.maxSample = v;
  }
  if (!count) { c.minSample = 0; c.maxSample = 0; }
  // 12.3.8: the level is the peak with each slot's running DC estimate
  // removed, so a silent room reads near zero instead of the ADC offset.
  // min/max stay raw (diagnostic evidence).
  c.peak = gOs12DcMeter.chunkPeak(s, count);
  c.nonZero = (uint16_t)nz;
  c.samples = (uint16_t)count;
  gOs12MicRingBuf[gOs12MicRingHead % kOs12MicRing] = c;
  gOs12MicRingHead = gOs12MicRingHead + 1;
}
"""

READ_STORE_OLD = "    if (gOs12RecordingActive) os12StoreChunk(reinterpret_cast<const uint8_t*>(rx), got);\n"
READ_STORE_NEW = """    // 12.3.8: touch the recording only inside the gate; the main loop closes
    // it and waits for this before it frees or replaces the buffer.
    if (gOs12RecordingActive && gOs12RecGate.enter()) {
      if (gOs12RecordingActive) os12StoreChunk(reinterpret_cast<const uint8_t*>(rx), got);
      gOs12RecGate.leave();
    }
"""

TASK_PLAY_OLD = """    if (gOs12PlaybackActive && gOs12RecordingData && gOs12PlaybackPosition < gOs12RecordingBytes) {
      gIdleStartMs = millis();"""
TASK_PLAY_NEW = """    // 12.3.8: play the clip only inside the recording gate.
    bool os12InGate = gOs12PlaybackActive && gOs12RecGate.enter();
    if (os12InGate && gOs12PlaybackActive && gOs12RecordingData && gOs12PlaybackPosition < gOs12RecordingBytes) {
      gIdleStartMs = millis();"""
TASK_FILL_OLD = """    } else {
      fillChunk(chunk);
    }
    size_t written = 0;"""
TASK_FILL_NEW = """      gOs12RecGate.leave();
      os12InGate = false;
    } else {
      if (os12InGate) { gOs12RecGate.leave(); os12InGate = false; }
      fillChunk(chunk);
    }
    size_t written = 0;"""

FREE_SIGNATURE = "void os12FreeRecording()"
FREE_NEW = """// 12.3.8: stop the audio task from touching the recording, wait until it
// has left the gate, then free the buffer. Leaves the gate closed: the caller
// opens it once the replacement (or nothing) is in place. False when the task
// did not leave in time; the buffer is then kept, not freed under it.
bool os12FreeRecording() {
  gOs12RecordingActive = false;
  gOs12PlaybackActive = false;
  gOs12CaptureKeepAlive = false;
  gOs12RecGate.close();
  const uint32_t waitStart = millis();
  while (!gOs12RecGate.idle() && millis() - waitStart < 250U) delay(1);
  if (!gOs12RecGate.idle() && gAudioTask != nullptr) {
    gOs12RecGateTimeouts = gOs12RecGateTimeouts + 1;
    gOs12RecGate.open();
    return false;
  }
  if (gOs12RecordingData) {
    free(gOs12RecordingData);
    gOs12RecordingData = nullptr;
  }
  gOs12RecordingCapacity = 0;
  gOs12RecordingBytes = 0;
  gOs12PlaybackPosition = 0;
  gOs12PlaybackGainQ8 = 256U;
  gOs12PlaybackSourcePeak = 0U;
  return true;
}
"""

BEGIN_OLD = """  os12FreeRecording();
  const uint64_t bytes64 = ((uint64_t)kSampleRate * 2ULL * sizeof(int16_t) * maxDurationMs) / 1000ULL;
  if (bytes64 == 0 || bytes64 > 512000ULL) return false;
  const size_t capacity = (size_t)(bytes64 - bytes64 % (2U * sizeof(int16_t)));
  gOs12RecordingData = static_cast<uint8_t*>(
      heap_caps_malloc(capacity, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT));
  if (!gOs12RecordingData) return false;
"""
BEGIN_NEW = """  // 12.3.8: the gate stays closed from the free until the new clip's state
  // is complete, so the audio task never sees a half-set-up buffer.
  if (!os12FreeRecording()) return false;
  const uint64_t bytes64 = ((uint64_t)kSampleRate * 2ULL * sizeof(int16_t) * maxDurationMs) / 1000ULL;
  if (bytes64 == 0 || bytes64 > 512000ULL) { gOs12RecGate.open(); return false; }
  const size_t capacity = (size_t)(bytes64 - bytes64 % (2U * sizeof(int16_t)));
  gOs12RecordingData = static_cast<uint8_t*>(
      heap_caps_malloc(capacity, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT));
  if (!gOs12RecordingData) { gOs12RecGate.open(); return false; }
"""
BEGIN_ACTIVE_OLD = """  gOs12RecordingDeadlineMs = millis() + maxDurationMs + 1500U;
  gOs12RecordingActive = true;
  return true;
"""
BEGIN_ACTIVE_NEW = """  gOs12RecordingDeadlineMs = millis() + maxDurationMs + 1500U;
  gOs12RecordingActive = true;
  gOs12RecGate.open();
  return true;
"""


def patch_audio(repo: Path) -> None:
    path = repo / "src" / "buzzer_backend_es8311.cpp"
    text = load(path)
    if "void os12ReadMic(int16_t* rx, size_t rxBytes)" not in text:
        raise PatchError("ES8311 backend lacks the 12.3.6 task-side capture")
    text = replace_once(text, ES_INCLUDE_OLD, ES_INCLUDE_NEW, "ES8311 includes")
    text = replace_once(text, ES_STATE_OLD, ES_STATE_NEW, "ES8311 12.3.8 state")
    text = replace_cpp_function(text, METER_SIGNATURE, METER_NEW, "meter chunk")
    text = replace_once(text, READ_STORE_OLD, READ_STORE_NEW, "gated store")
    text = replace_once(text, TASK_PLAY_OLD, TASK_PLAY_NEW, "gated playback")
    text = replace_once(text, TASK_FILL_OLD, TASK_FILL_NEW, "gated playback end")
    text = replace_cpp_function(text, FREE_SIGNATURE, FREE_NEW, "free recording")
    text = replace_once(text, BEGIN_OLD, BEGIN_NEW, "record begin free")
    text = replace_once(text, BEGIN_ACTIVE_OLD, BEGIN_ACTIVE_NEW, "record begin open")
    path.write_text(text, encoding="utf-8")


def install_headers(repo: Path, source_root: Path) -> None:
    for source, target in HEADERS:
        src = source_root / source
        if not src.is_file():
            raise PatchError(f"missing {src}")
        dst = repo / target
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)


def apply(repo: Path, source_root: Path) -> None:
    build_path = repo / "include" / "smart_home_build.h"
    build = load(build_path)
    if TOUCH_AUDIO_MARKER not in build:
        raise PatchError("the 12.3.8 review layer runs after apply_workshop_os12_touch_audio_fit.py")
    if BUILD_MARKER in build:
        raise PatchError("the 12.3.8 review layer is already applied")
    install_headers(repo, source_root)
    patch_web(repo)
    patch_hub(repo)
    patch_audio(repo)
    build_path.write_text(build.rstrip() + "\n" + BUILD_MARKER + "\n", encoding="utf-8")
    print("Workshop OS 12.3.8 review fixes installed: same-origin sign-in, armed Local AI prompts, "
          "press acts only on its own target, outline follows the finger; no echo route, DC-free meter, "
          "gated recording buffer")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    ap.add_argument("--source-root", default=str(_here))
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    if not args.apply:
        raise SystemExit("refusing to modify source without --apply")
    try:
        apply(Path(args.repo).resolve(), Path(args.source_root).resolve())
    except PatchError as exc:
        raise SystemExit(f"FAIL: {exc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
