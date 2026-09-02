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

    old_nav = r'''static void uiNavIcon(int16_t cx, int16_t cy, uint8_t item, uint16_t c) {
  if (item == 0) {
    tft.drawLine(cx - 6, cy, cx, cy - 6, c);
    tft.drawLine(cx, cy - 6, cx + 6, cy, c);
    tft.drawRect(cx - 5, cy, 10, 7, c);
  } else if (item == 1) {
    tft.drawRect(cx - 6, cy - 5, 12, 10, c);
    tft.drawFastHLine(cx - 3, cy - 8, 6, c);
    tft.fillCircle(cx, cy, 2, c);
  } else if (item == 2) {
    tft.drawRect(cx - 6, cy - 6, 12, 12, c);
    tft.drawLine(cx - 6, cy - 6, cx + 6, cy + 6, c);
    tft.drawLine(cx + 6, cy - 6, cx - 6, cy + 6, c);
  } else {
    tft.drawCircle(cx, cy, 6, c);
    tft.fillCircle(cx, cy, 2, c);
  }
}

static void uiBottomNav(uint8_t active, const char* nextPage) {
  const int16_t y = tft.height() - 42;
  const int16_t W = tft.width();
  tft.fillRect(0, y, W, 42, UI_BG);
  tft.drawFastHLine(8, y, W - 16, UI_BORDER);
  static const char* labels[] = {"HOME", "WORK", "CUSTOM", "SYSTEM"};
  const int16_t cell = W / 4;
  for (uint8_t i = 0; i < 4; i++) {
    int16_t x = i * cell;
    uint16_t c = i == active ? UI_ORANGE : UI_MUTED;
    if (i == active) {
      tft.fillRoundRect(x + 4, y + 5, cell - 8, 32, 9, UI_WARN_BG);
      tft.drawRoundRect(x + 4, y + 5, cell - 8, 32, 9, UI_ORANGE);
    }
    uiNavIcon(x + 16, y + 17, i, c);
    setFont(tft, FONT_SMALL);
    tft.setTextDatum(ML_DATUM);
    tft.setTextColor(c, i == active ? UI_WARN_BG : UI_BG);
    tft.drawString(labels[i], x + 27, y + 18);
  }
  if (nextPage && *nextPage) {
    setFont(tft, FONT_SMALL);
    tft.setTextDatum(BR_DATUM);
    tft.setTextColor(UI_MUTED, UI_BG);
    // Small corner chevron is a subtle reminder that the physical screen's
    // existing tap gesture advances pages; the nav itself is visual in RC1.
    tft.drawString(">", W - 3, y - 3);
  }
}
'''
    new_nav = r'''static void uiNavIcon(int16_t cx, int16_t cy, uint8_t item, uint16_t c) {
  if (item == 0) { // Home
    tft.drawLine(cx - 6, cy, cx, cy - 6, c);
    tft.drawLine(cx, cy - 6, cx + 6, cy, c);
    tft.drawRect(cx - 5, cy, 10, 7, c);
  } else if (item == 1) { // Printer
    tft.drawRoundRect(cx - 7, cy - 6, 14, 12, 3, c);
    tft.drawFastHLine(cx - 4, cy - 9, 8, c);
    tft.drawFastHLine(cx - 4, cy + 9, 8, c);
    tft.fillCircle(cx + 4, cy + 3, 2, c);
  } else if (item == 2) { // Workshop
    tft.drawRect(cx - 7, cy - 7, 6, 6, c);
    tft.drawRect(cx + 1, cy - 7, 6, 6, c);
    tft.drawRect(cx - 7, cy + 1, 6, 6, c);
    tft.drawRect(cx + 1, cy + 1, 6, 6, c);
  } else if (item == 3) { // Widgets
    tft.drawRoundRect(cx - 8, cy - 7, 7, 14, 2, c);
    tft.drawRoundRect(cx + 1, cy - 7, 7, 6, 2, c);
    tft.drawRoundRect(cx + 1, cy + 1, 7, 6, 2, c);
  } else { // System
    tft.drawCircle(cx, cy, 7, c);
    tft.fillCircle(cx, cy, 2, c);
    tft.drawFastHLine(cx - 10, cy, 3, c);
    tft.drawFastHLine(cx + 7, cy, 3, c);
    tft.drawFastVLine(cx, cy - 10, 3, c);
    tft.drawFastVLine(cx, cy + 7, 3, c);
  }
}

static void uiBottomNav(uint8_t active, const char* nextPage) {
  (void)nextPage;
  const int16_t navH = 44;
  const int16_t y = tft.height() - navH;
  const int16_t W = tft.width();
  tft.fillRect(0, y, W, navH, UI_BG);
  tft.drawFastHLine(8, y, W - 16, UI_BORDER);
  static const char* labels[] = {"HOME", "PRINT", "WORK", "WIDGET", "SYSTEM"};
  // Existing page IDs are Home=0, Workshop=1, Custom=2, System=3. Translate
  // them into the persistent five-destination footer, which inserts Printer.
  const uint8_t activeTab = active == 0 ? 0 : (active == 1 ? 2 : (active == 2 ? 3 : 4));
  const int16_t cell = W / 5; // 64px on WS350: generous one-finger hit targets.
  for (uint8_t i = 0; i < 5; i++) {
    int16_t x = i * cell;
    uint16_t c = i == activeTab ? UI_ORANGE : UI_MUTED;
    uint16_t bg = i == activeTab ? UI_WARN_BG : UI_BG;
    if (i == activeTab) {
      tft.fillRoundRect(x + 4, y + 3, cell - 8, navH - 7, 9, UI_WARN_BG);
      tft.drawRoundRect(x + 4, y + 3, cell - 8, navH - 7, 9, UI_ORANGE);
    }
    uiNavIcon(x + cell / 2, y + 14, i, c);
    setFont(tft, FONT_SMALL);
    tft.setTextDatum(TC_DATUM);
    tft.setTextColor(c, bg);
    tft.drawString(labels[i], x + cell / 2, y + 25);
  }
}
'''
    t = replace_once(t, old_nav, new_nav, "five-destination Smart Hub footer")

    anchor = '''void smartHubAdvance() {
'''
    handler = r'''// Direct coordinate navigation for the WS350 Smart Home footer. Only the nav
// strip consumes coordinates; direct footer taps select pages while taps elsewhere
// deliberately fall through to smartHubAdvance(), preserving the proven gesture.
static bool mapSmartHubNavPoint(int16_t rawX, int16_t rawY,
                                int16_t& screenX, int16_t& screenY) {
#if defined(BOARD_IS_WS350)
  // Current WS350 calibration expects controller coordinates 180 degrees from
  // the portrait framebuffer. Serial diagnostics expose raw/mapped points so
  // physical acceptance can verify this mapping without hiding assumptions.
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
  const int16_t navTop = tft.height() - 44;
  if (y < navTop) return false;

  int16_t cell = tft.width() / 5;
  uint8_t item = (uint8_t)(x / cell);
  if (item > 4) item = 4;
  Serial.printf("SmartHub nav touch raw=(%d,%d) mapped=(%d,%d) item=%u\n",
                rawX, rawY, x, y, (unsigned)item);
  switch (item) {
    case 0: return smartHubShowPage("home");
    case 1: return smartHubShowPage("printer");
    case 2: return smartHubShowPage("workshop");
    case 3: return smartHubShowPage("custom");
    case 4: return smartHubShowPage("system");
    default: return false;
  }
}

'''
    t = replace_once(t, anchor, handler + anchor, "Smart Hub direct-nav handler")
    p.write_text(t, encoding="utf-8")

    h = repo / "src" / "smart_hub.h"
    ht = h.read_text(encoding="utf-8")
    if 'bool smartHubHandleTouch(int16_t rawX, int16_t rawY);' not in ht:
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
        repo / "src" / "smart_hub.cpp": [
            "smartHubHandleTouch", "SmartHub nav touch raw=", "direct footer taps select pages",
            'static const char* labels[] = {"HOME", "PRINT", "WORK", "WIDGET", "SYSTEM"}',
            'case 1: return smartHubShowPage("printer")',
        ],
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
