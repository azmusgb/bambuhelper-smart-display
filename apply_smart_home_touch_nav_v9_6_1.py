#!/usr/bin/env python3
from pathlib import Path
import argparse
import re


class PatchError(RuntimeError):
    pass


def replace_once(text: str, old: str, new: str, label: str) -> str:
    n = text.count(old)
    if n != 1:
        raise PatchError(f"{label}: expected exactly 1 match, found {n}")
    return text.replace(old, new, 1)


def patch_touch_backend(repo: Path) -> None:
    p = repo / "src" / "button_touch_backend.h"
    t = p.read_text(encoding="utf-8")
    old = '''struct TouchPoll {
  TouchEvent ev;
  bool isDown;  // meaningful for level backends (ev == None); raw finger-down
};'''
    new = '''struct TouchPoll {
  TouchEvent ev;
  bool isDown;  // meaningful for level backends (ev == None); raw finger-down
  // Optional controller-native contact point. Existing backends that initialize
  // only ev/isDown remain source-compatible; aggregate initialization zeros the
  // trailing fields. Coordinate-aware backends set hasPoint=true while touched.
  int16_t x;
  int16_t y;
  bool hasPoint;
};'''
    t = replace_once(t, old, new, "TouchPoll coordinates")
    p.write_text(t, encoding="utf-8")


def patch_focaltech(repo: Path) -> None:
    p = repo / "src" / "button_touch_focaltech.cpp"
    t = p.read_text(encoding="utf-8")

    reg_anchor = '#define FT5X06_TOUCH_POINTS_REG 0x02  // TD_STATUS register\n'
    reg_new = reg_anchor + '''#define FT5X06_P1_XH_REG 0x03
#define FT5X06_P1_XL_REG 0x04
#define FT5X06_P1_YH_REG 0x05
#define FT5X06_P1_YL_REG 0x06
'''
    t = replace_once(t, reg_anchor, reg_new, "FocalTech coordinate registers")

    read_anchor = '''static bool ft5x06ReadReg(uint8_t reg, uint8_t& value) {
  Wire.beginTransmission(TOUCH_SLAVE_ADDRESS);
  Wire.write(reg);
  if (Wire.endTransmission(false) != 0) return false;
  if (Wire.requestFrom((uint8_t)TOUCH_SLAVE_ADDRESS, (uint8_t)1) != 1) return false;
  value = Wire.read();
  return true;
}
'''
    read_new = read_anchor + '''
static bool ft5x06ReadPoint(int16_t& x, int16_t& y) {
  // First contact point: XH/XL/YH/YL. The upper nibble of XH/YH contains
  // event/touch metadata; the coordinate itself is the low 12 bits.
  Wire.beginTransmission(TOUCH_SLAVE_ADDRESS);
  Wire.write((uint8_t)FT5X06_P1_XH_REG);
  if (Wire.endTransmission(false) != 0) return false;
  if (Wire.requestFrom((uint8_t)TOUCH_SLAVE_ADDRESS, (uint8_t)4) != 4) return false;
  uint8_t xh = Wire.read();
  uint8_t xl = Wire.read();
  uint8_t yh = Wire.read();
  uint8_t yl = Wire.read();
  x = (int16_t)(((uint16_t)(xh & 0x0F) << 8) | xl);
  y = (int16_t)(((uint16_t)(yh & 0x0F) << 8) | yl);
  return true;
}
'''
    t = replace_once(t, read_anchor, read_new, "FocalTech point reader")

    old_return = '''  // TD_STATUS low nibble = active touch points; mask off the reserved high bits so
  // a stray high bit can't be misread as a permanent touch.
  return {TouchEvent::None, (bool)((touchPoints & 0x0F) > 0)};'''
    new_return = '''  // TD_STATUS low nibble = active touch points; mask off the reserved high bits so
  // a stray high bit can't be misread as a permanent touch.
  const bool down = (touchPoints & 0x0F) > 0;
  if (!down) return {TouchEvent::None, false, 0, 0, false};
  int16_t x = 0, y = 0;
  if (!ft5x06ReadPoint(x, y)) {
    // Preserve the down level even if this optional coordinate read fails.
    return {TouchEvent::None, true, 0, 0, false};
  }
  return {TouchEvent::None, true, x, y, true};'''
    t = replace_once(t, old_return, new_return, "FocalTech point return")
    p.write_text(t, encoding="utf-8")


def patch_button(repo: Path) -> None:
    p = repo / "src" / "button.cpp"
    t = p.read_text(encoding="utf-8")

    anchor = 'static const unsigned long DEBOUNCE_MS = 50;\n'
    injected = anchor + '''// Most recent touchscreen contact point. Kept separate from debounce/hold state
// so delayed tap dispatch (LED hold/tap disambiguation) can still resolve the
// coordinate on release without changing the proven button state machine.
static int16_t lastTouchX = 0;
static int16_t lastTouchY = 0;
static uint32_t lastTouchPointMs = 0;
'''
    t = replace_once(t, anchor, injected, "button touch-point cache")

    poll = '''    TouchPoll tp = touchPoll();
    // A failed bus/read must NOT disturb debounce or hold state - it is not a'''
    poll_new = '''    TouchPoll tp = touchPoll();
    if (tp.hasPoint) {
      lastTouchX = tp.x;
      lastTouchY = tp.y;
      lastTouchPointMs = millis();
    }
    // A failed bus/read must NOT disturb debounce or hold state - it is not a'''
    t = replace_once(t, poll, poll_new, "cache reported touch point")

    marker = '// Smart Home v9.6 RC2 coordinate-aware touch accessor\n'
    if marker not in t:
        t += '''

// Smart Home v9.6 RC2 coordinate-aware touch accessor
bool buttonLastTouchPoint(int16_t* x, int16_t* y) {
  if (buttonType != BTN_TOUCHSCREEN || lastTouchPointMs == 0) return false;
  // Deferred release-edge tap dispatch is normally tens of milliseconds later.
  // A short freshness window prevents a board-button press from reusing a stale
  // touchscreen coordinate after the user has moved on.
  if ((uint32_t)(millis() - lastTouchPointMs) > 750u) return false;
  if (x) *x = lastTouchX;
  if (y) *y = lastTouchY;
  return true;
}
'''
    p.write_text(t, encoding="utf-8")

    h = repo / "src" / "button.h"
    ht = h.read_text(encoding="utf-8")
    h_anchor = 'uint32_t buttonHoldDurationMs();  // 0 if not held, else millis() - press start\n'
    h_new = h_anchor + '''// Fresh controller-native coordinate for the most recent touchscreen contact.
// Returns false for physical buttons, stale points, or coordinate-less backends.
bool buttonLastTouchPoint(int16_t* x, int16_t* y);
'''
    ht = replace_once(ht, h_anchor, h_new, "button touch-point declaration")
    h.write_text(ht, encoding="utf-8")


def patch_smart_hub(repo: Path) -> None:
    p = repo / "src" / "smart_hub.cpp"
    t = p.read_text(encoding="utf-8")

    anchor = '''void smartHubAdvance() {
'''
    handler = r'''// Direct coordinate navigation for the WS350 Smart Home footer. Only the nav
// strip consumes coordinates; taps everywhere else deliberately fall through to
// the existing smartHubAdvance() gesture, preserving the proven interaction.
static bool mapSmartHubNavPoint(int16_t rawX, int16_t rawY,
                                int16_t& screenX, int16_t& screenY) {
#if defined(BOARD_IS_WS350)
  // Physical acceptance of this Waveshare/FT6336 combination established that
  // controller coordinates are 180 degrees from the portrait framebuffer.
  // Keep the transform local to WS350 so shared 320x480 targets are unaffected.
  screenX = (int16_t)(tft.width() - 1 - rawX);
  screenY = (int16_t)(tft.height() - 1 - rawY);
#else
  screenX = rawX;
  screenY = rawY;
#endif
  return screenX >= 0 && screenX < tft.width() &&
         screenY >= 0 && screenY < tft.height();
}

bool smartHubHandleTouch(int16_t rawX, int16_t rawY) {
  if (!g_cfg.enabled || !smartHubIsScreen(getScreenState())) return false;
  // Ambient has intentionally no navigation chrome. Its first touch remains the
  // established tap-to-wake gesture rather than turning into a hidden nav tap.
  if (g_ambientHome && getScreenState() == SCREEN_HUB_HOME) return false;

  int16_t x = 0, y = 0;
  if (!mapSmartHubNavPoint(rawX, rawY, x, y)) return false;
  const int16_t navTop = tft.height() - 42;
  if (y < navTop) return false;

  int16_t cell = tft.width() / 4;
  uint8_t item = (uint8_t)(x / cell);
  if (item > 3) item = 3;
  Serial.printf("SmartHub nav touch raw=(%d,%d) mapped=(%d,%d) item=%u\n",
                rawX, rawY, x, y, (unsigned)item);
  switch (item) {
    case 0: return smartHubShowPage("home");
    case 1: return smartHubShowPage("workshop");
    case 2: return smartHubShowPage("custom");
    case 3: return smartHubShowPage("system");
    default: return false;
  }
}

'''
    t = replace_once(t, anchor, handler + anchor, "Smart Hub direct-nav handler")
    t = replace_once(
        t,
        '// existing tap gesture advances pages; the nav itself is visual in RC1.',
        '// direct footer taps select pages; taps elsewhere still advance pages.',
        "bottom-nav interaction comment",
    )
    p.write_text(t, encoding="utf-8")

    h = repo / "src" / "smart_hub.h"
    ht = h.read_text(encoding="utf-8")
    if 'bool smartHubHandleTouch(int16_t rawX, int16_t rawY);' not in ht:
        # Place next to the existing public page-selection API without depending
        # on historical header ordering.
        needle = 'bool smartHubShowPage(const char* pageName);'
        if needle not in ht:
            raise PatchError("smart_hub.h: smartHubShowPage declaration not found")
        ht = ht.replace(
            needle,
            needle + '\n// Consume a coordinate tap only when it lands on Smart Home navigation.\nbool smartHubHandleTouch(int16_t rawX, int16_t rawY);',
            1,
        )
    h.write_text(ht, encoding="utf-8")


def patch_main(repo: Path) -> None:
    p = repo / "src" / "main.cpp"
    t = p.read_text(encoding="utf-8")
    pattern = re.compile(
        r'''  if \(smartHubIsScreen\(cur\)\) \{\n'''
        r'''\s*smartHubAdvance\(\);\n'''
        r'''\s*return;\n'''
        r'''\s*\}'''
    )
    matches = list(pattern.finditer(t))
    if len(matches) != 1:
        raise PatchError(f"main Smart Hub tap dispatch: expected 1 match, found {len(matches)}")
    repl = '''  if (smartHubIsScreen(cur)) {
    int16_t touchX = 0, touchY = 0;
    if (buttonLastTouchPoint(&touchX, &touchY) &&
        smartHubHandleTouch(touchX, touchY)) {
      return;
    }
    smartHubAdvance();
    return;
  }'''
    t = pattern.sub(repl, t, count=1)
    p.write_text(t, encoding="utf-8")


def apply(repo: Path) -> None:
    patch_touch_backend(repo)
    patch_focaltech(repo)
    patch_button(repo)
    patch_smart_hub(repo)
    patch_main(repo)

    contracts = {
        repo / "src" / "button_touch_backend.h": ["int16_t x;", "bool hasPoint;"],
        repo / "src" / "button_touch_focaltech.cpp": ["ft5x06ReadPoint", "FT5X06_P1_XH_REG"],
        repo / "src" / "button.cpp": ["buttonLastTouchPoint", "lastTouchPointMs"],
        repo / "src" / "smart_hub.cpp": ["smartHubHandleTouch", "SmartHub nav touch raw="],
        repo / "src" / "main.cpp": ["buttonLastTouchPoint(&touchX, &touchY)", "smartHubHandleTouch(touchX, touchY)"],
    }
    for path, needles in contracts.items():
        body = path.read_text(encoding="utf-8")
        for needle in needles:
            if needle not in body:
                raise PatchError(f"contract missing in {path.name}: {needle}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Smart Home v9.6 RC2 direct touch navigation")
    ap.add_argument("--repo", required=True)
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    if not args.apply:
        raise SystemExit("Pass --apply")
    apply(Path(args.repo))
    print("Smart Home v9.6 RC2 direct touch navigation applied")
