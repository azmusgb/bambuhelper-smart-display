#!/usr/bin/env python3
"""Touch ergonomics for the WS350 touchscreen (12.3.6).

Physical acceptance of 12.3.5 failed on touch: "not responsive" and "controls
not comfortable" on ten screens. The bigger rows (55 px, about 8.5 mm) live in
firmware/platform/ui/more_layout.hpp and tabs_layout.hpp. This overlay adds the
interaction half on top of the tabs overhaul:

- press feedback: the target under the finger is outlined while it is down,
  so a tap is visibly received before the action runs on release;
- swipe to scroll: a vertical drag scrolls the More pages, the Printer AMS and
  Control lists and Workshop, instead of only the small header arrows;
- Pause/Resume is hold-guarded like Stop: hold progress is drawn over the
  button and only a hold that started and stayed on it pauses the print.

Run after apply_workshop_os12_tabs_overhaul.py. Every change is staged in
memory and written only after every anchor validates.
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

MARKER = "smartHubHandleSwipe"

# ---- smart_hub.cpp: hold progress feeds the Pause tracker too ----
HOLD_OLD = """    wsm::Rect stop;
    if(wtStopHoldTrack(x,y,stop)){kind=3;bx=stop.x;by=stop.y;bw=stop.w;bh=stop.h;label="Keep holding";}else{lastKind=0;lastSegments=255;return;}"""
HOLD_NEW = """    // Pause/Resume is hold-guarded the same way (12.3.6); both trackers see
    // every sample.
    wsm::Rect stop,pause;
    const bool pauseHeld=wtPauseHoldTrack(x,y,pause);
    if(wtStopHoldTrack(x,y,stop)){kind=3;bx=stop.x;by=stop.y;bw=stop.w;bh=stop.h;label="Keep holding";}
    else if(pauseHeld){kind=4;bx=pause.x;by=pause.y;bw=pause.w;bh=pause.h;label="Keep holding";}
    else{lastKind=0;lastSegments=255;return;}"""
HOLD_DRAW_OLD = "  if(kind==3){wtDrawStopHold(wsm::makeRect(bx,by,bw,bh),segments);hubMarkFrameDirty();return;}\n"
HOLD_DRAW_NEW = (HOLD_DRAW_OLD +
                 "  if(kind==4){wtDrawPauseHold(wsm::makeRect(bx,by,bw,bh),segments);hubMarkFrameDirty();return;}\n")

# ---- smart_hub.cpp: press feedback at the first sample of every press ----
FEEDBACK_OLD = "  int16_t x=0,y=0;mapHubTouch(rawX,rawY,x,y);\n  uint8_t kind=0;"
FEEDBACK_NEW = ("  int16_t x=0,y=0;mapHubTouch(rawX,rawY,x,y);\n"
                "  // Outline what the finger is on, once per press (12.3.6).\n"
                "  if(!g_pressFeedbackShown){g_pressFeedbackShown=true;wsPressFeedback(x,y);}\n"
                "  uint8_t kind=0;")
RESET_OLD = "  if(holdMs==0){lastKind=0;lastSegments=255;return;}"
RESET_NEW = "  if(holdMs==0){lastKind=0;lastSegments=255;g_pressFeedbackShown=false;return;}"

# ---- smart_hub.cpp: a touch repaints the page (clears the outline) ----
TOUCH_OLD = """bool smartHubHandleTouch(uint16_t rawX, uint16_t rawY, bool longPress) {
  smartHubUpdateHoldProgress(rawX,rawY,0);
  if (!g_cfg.enabled || !smartHubIsScreen(getScreenState())) return false;"""
TOUCH_NEW = """bool smartHubHandleTouch(uint16_t rawX, uint16_t rawY, bool longPress) {
  smartHubUpdateHoldProgress(rawX,rawY,0);
  if (!g_cfg.enabled || !smartHubIsScreen(getScreenState())) return false;
  g_dirty = true;  // repaint: clears the press outline even when nothing changes"""

HOLD_SIGNATURE = "void smartHubUpdateHoldProgress(uint16_t rawX, uint16_t rawY, uint32_t holdMs) {"
HELPERS = r"""// ---------------------------------------------------------------------------
// Touch ergonomics (12.3.6): press feedback and swipe to scroll
// ---------------------------------------------------------------------------

static bool g_pressFeedbackShown = false;

static void wsOutline(const wsm::Rect& r) {
  if (r.empty()) return;
  tft.drawRoundRect(r.x, r.y, r.w, r.h, 10, OS12V_ACCENT);
  tft.drawRoundRect(r.x + 1, r.y + 1, r.w - 2, r.h - 2, 9, OS12V_ACCENT);
  hubMarkFrameDirty();
}

// The drawn target under (x, y) on the More pages, or an empty rect.
static wsm::Rect wsMoreTarget(int16_t x, int16_t y) {
  const wsm::Screen s = wsScreen();
  const wsm::Hit h = wsm::hitTest(s, g_wsPage, g_wsScroll, g_wsDialog != WsDialog::None, x, y);
  switch (h.kind) {
    case wsm::HitKind::Tab: return wsm::tabRect(s, h.index);
    case wsm::HitKind::Back: return wsm::backRect(s);
    case wsm::HitKind::ScrollUp: return wsm::scrollUpRect(s);
    case wsm::HitKind::ScrollDown: return wsm::scrollDownRect(s);
    case wsm::HitKind::Tile: return wsm::tileRect(s, h.index);
    case wsm::HitKind::DialogCancel: return wsm::dialogCancelRect(s);
    case wsm::HitKind::DialogConfirm: return wsm::dialogConfirmRect(s);
    case wsm::HitKind::Row: {
      const wsm::Rect row = wsm::rowRect(s, g_wsPage, g_wsScroll, h.index);
      const wsm::RowKind kind = wsm::page(g_wsPage).rows[h.index].kind;
      if (h.part == wsm::Part::Whole) return wsm::rowSurface(row);
      return wsm::partDrawRect(s, row, kind, h.part);
    }
    default: return wsm::makeRect(0, 0, 0, 0);
  }
}

// The Printer / Workshop / Home view on screen, its runtime count and scroll.
static bool wtCurrentView(wtl::View& id, uint8_t& count, uint8_t& scroll) {
  count = 0;
  scroll = 0;
  const ScreenState cur = getScreenState();
  if (cur == SCREEN_HUB_HOME) { id = wtl::View::Home; return true; }
  if (cur == SCREEN_HUB_PRINTER) {
    id = wtPrinterView();
    if (id == wtl::View::PrinterAms) {
      WtTray trays[wtl::kMaxAmsRows];
      const uint8_t n = wtAmsRows(wtPrint(), trays, wtl::kMaxAmsRows);
      count = n ? n : 1;
    }
    scroll = wtl::view(id).list ? g_wtPrinterScroll : 0;
    return true;
  }
  if (cur == SCREEN_HUB_WORKSHOP) {
    id = workshopInventorySnapshot().credentialConfigured ? wtl::View::WorkshopInventory : wtl::View::WorkshopSetup;
    scroll = g_wtWorkshopScroll;
    return true;
  }
  return false;
}

static wsm::Rect wtTarget(int16_t x, int16_t y) {
  wtl::View id = wtl::View::Home;
  uint8_t count = 0, scroll = 0;
  if (!wtCurrentView(id, count, scroll)) return wsm::makeRect(0, 0, 0, 0);
  const wsm::Screen s = wsScreen();
  const wtl::ViewSpec& v = wtl::view(id);
  const wtl::Hit h = wtl::hitTest(s, id, count, scroll, x, y);
  switch (h.kind) {
    case wtl::HitKind::Tab: return wsm::tabRect(s, h.index);
    case wtl::HitKind::ScrollUp: return wsm::scrollUpRect(s);
    case wtl::HitKind::ScrollDown: return wsm::scrollDownRect(s);
    case wtl::HitKind::Segment: return wtl::segmentRect(s, h.index);
    case wtl::HitKind::Item: {
      if (id == wtl::View::PrinterAms) return wsm::makeRect(0, 0, 0, 0);  // read-only rows
      const wtl::ItemSpec& it = wtl::item(v, h.index);
      const wsm::Rect r = wtl::itemRect(s, v, count, scroll, h.index);
      if (it.kind == wtl::ItemKind::Hold) return wtl::holdDrawRect(s, r);
      if (it.kind == wtl::ItemKind::Primary) return wtl::primaryDrawRect(r);
      if (it.kind == wtl::ItemKind::Row && h.part != wsm::Part::Whole) return wsm::partDrawRect(s, r, it.rowKind, h.part);
      return wsm::rowSurface(r);
    }
    default: return wsm::makeRect(0, 0, 0, 0);
  }
}

// Outline the control under the finger so a press is visibly received; the
// action itself still runs on release.
static void wsPressFeedback(int16_t x, int16_t y) {
  if (workshopStatusTokenPromptVisible() || workshopCodeTokenPromptVisible()) return;
  const ScreenState cur = getScreenState();
  if (cur == SCREEN_HUB_MORE || cur == SCREEN_HUB_SYSTEM || cur == SCREEN_HUB_CUSTOM) {
    if (g_rotationPreviewMode) return;
    wsOutline(wsMoreTarget(x, y));
    return;
  }
  if (wtCalmShown()) return;
  wsOutline(wtTarget(x, y));
}

// A vertical drag scrolls the page instead of tapping. True when the press was
// a drag (whether or not the page could scroll), so main.cpp skips the tap.
bool smartHubHandleSwipe(uint16_t rawX0, uint16_t rawY0, uint16_t rawX1, uint16_t rawY1) {
  if (!g_cfg.enabled || !smartHubIsScreen(getScreenState())) return false;
  if (workshopStatusTokenPromptVisible() || workshopCodeTokenPromptVisible()) return false;
  int16_t x0 = 0, y0 = 0, x1 = 0, y1 = 0;
  mapHubTouch(rawX0, rawY0, x0, y0);
  mapHubTouch(rawX1, rawY1, x1, y1);
  const int dx = x1 - x0, dy = y1 - y0;
  const int ady = dy < 0 ? -dy : dy, adx = dx < 0 ? -dx : dx;
  if (ady < 32 || ady <= adx) return false;
  // A drag never sends Pause or Stop, wherever it started or ended.
  wtStopHoldConsume();
  wtPauseHoldConsume();
  smartHubUpdateHoldProgress(rawX1, rawY1, 0);
  g_dirty = true;
  if (wtCalmShown()) return false;  // the calm screen wakes on any touch
  // Finger up = later rows; one row per 55 px of travel, at least one.
  const int rows = ady / wsm::kRowH > 0 ? ady / wsm::kRowH : 1;
  const int delta = dy < 0 ? rows : -rows;
  const wsm::Screen s = wsScreen();
  const ScreenState cur = getScreenState();
  if (cur == SCREEN_HUB_MORE || cur == SCREEN_HUB_SYSTEM || cur == SCREEN_HUB_CUSTOM) {
    if (g_rotationPreviewMode || g_wsDialog != WsDialog::None) return true;
    g_wsScroll = wsm::clampScroll(s, g_wsPage, (int)g_wsScroll + delta);
    return true;
  }
  wtl::View id = wtl::View::Home;
  uint8_t count = 0, scroll = 0;
  if (!wtCurrentView(id, count, scroll)) return true;
  const wtl::ViewSpec& v = wtl::view(id);
  if (!wtl::scrolls(s, v, count)) return true;
  const uint8_t next = wtl::clampScroll(s, v, count, (int)scroll + delta);
  if (cur == SCREEN_HUB_PRINTER) g_wtPrinterScroll = next;
  else if (cur == SCREEN_HUB_WORKSHOP) g_wtWorkshopScroll = next;
  return true;
}

"""

STUB_OLD = "bool smartHubHandleTouch(uint16_t, uint16_t, bool) { return false; }\n"
STUB_NEW = STUB_OLD + "bool smartHubHandleSwipe(uint16_t, uint16_t, uint16_t, uint16_t) { return false; }\n"

HEADER_OLD = "bool smartHubHandleTouch(uint16_t rawX, uint16_t rawY, bool longPress);\n"
HEADER_NEW = HEADER_OLD + (
    "// A vertical drag from (x0, y0) to (x1, y1), raw panel coordinates: scrolls\n"
    "// the page and returns true, so the caller skips the tap. False for a tap.\n"
    "bool smartHubHandleSwipe(uint16_t rawX0, uint16_t rawY0, uint16_t rawX1, uint16_t rawY1);\n")

# ---- main.cpp: remember where the press started; drags scroll ----
MAIN_STATICS_OLD = "  static uint16_t hubTouchX = 0, hubTouchY = 0;\n"
MAIN_STATICS_NEW = MAIN_STATICS_OLD + (
    "  static uint16_t hubTouchStartX = 0, hubTouchStartY = 0;\n"
    "  static bool hubTouchStartValid = false;\n")
MAIN_PRESS_OLD = "      hubTouchHasPoint = buttonGetTouchPosition(&hubTouchX, &hubTouchY);\n"
MAIN_PRESS_NEW = MAIN_PRESS_OLD + (
    "      hubTouchStartValid = hubTouchHasPoint;\n"
    "      hubTouchStartX = hubTouchX; hubTouchStartY = hubTouchY;\n")
MAIN_RELEASE_OLD = """      } else if (hubTouchHasPoint) {
        smartHubHandleTouch(hubTouchX, hubTouchY, hubTouchMaxHoldMs >= 650);"""
MAIN_RELEASE_NEW = """      } else if (hubTouchHasPoint && hubTouchStartValid &&
                 smartHubHandleSwipe(hubTouchStartX, hubTouchStartY, hubTouchX, hubTouchY)) {
        // A vertical drag scrolled the page; it is not a tap.
      } else if (hubTouchHasPoint) {
        smartHubHandleTouch(hubTouchX, hubTouchY, hubTouchMaxHoldMs >= 650);"""


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise PatchError(f"{label}: expected one anchor, found {count}")
    return text.replace(old, new, 1)


def patch_smart_hub(hub: str) -> str:
    if "wtStopHoldTrack(x,y,stop)" not in hub or "static bool wtPauseHoldTrack(" not in hub:
        raise PatchError("the tabs overhaul (with the hold-guarded Pause) must be applied first")
    hub = replace_once(hub, HOLD_OLD, HOLD_NEW, "Pause hold tracking")
    hub = replace_once(hub, HOLD_DRAW_OLD, HOLD_DRAW_NEW, "Pause hold drawing")
    hub = replace_once(hub, RESET_OLD, RESET_NEW, "press feedback reset")
    hub = replace_once(hub, FEEDBACK_OLD, FEEDBACK_NEW, "press feedback")
    hub = replace_once(hub, TOUCH_OLD, TOUCH_NEW, "repaint after touch")
    hub = replace_once(hub, HOLD_SIGNATURE, HELPERS + HOLD_SIGNATURE, "touch ergonomics helpers")
    hub = replace_once(hub, STUB_OLD, STUB_NEW, "disabled-hub swipe stub")
    return hub


def apply(repo: Path) -> None:
    hub_path, header_path, main_path = repo / "src/smart_hub.cpp", repo / "src/smart_hub.h", repo / "src/main.cpp"
    for path in (hub_path, header_path, main_path):
        if not path.is_file():
            raise PatchError(f"missing reconstructed source: {path}")
    hub = hub_path.read_text(encoding="utf-8")
    if MARKER in hub:
        print("Workshop OS 12 touch ergonomics already installed")
        return
    hub = patch_smart_hub(hub)
    header = replace_once(header_path.read_text(encoding="utf-8"), HEADER_OLD, HEADER_NEW, "swipe declaration")
    main = main_path.read_text(encoding="utf-8")
    main = replace_once(main, MAIN_STATICS_OLD, MAIN_STATICS_NEW, "press start statics")
    main = replace_once(main, MAIN_PRESS_OLD, MAIN_PRESS_NEW, "press start point")
    main = replace_once(main, MAIN_RELEASE_OLD, MAIN_RELEASE_NEW, "swipe on release")
    hub_path.write_text(hub, encoding="utf-8")
    header_path.write_text(header, encoding="utf-8")
    main_path.write_text(main, encoding="utf-8")
    print("Workshop OS 12 touch ergonomics installed: press outline, swipe to scroll, hold-guarded Pause")


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
