// Host test for firmware/platform/ui/tabs_layout.hpp (WS350 Home, Printer
// and Workshop tabs).
//
// Checks, in landscape 480x320 (the WS350's real orientation) and portrait
// 320x480, for every view and every state the firmware can show (AMS with
// 0-17 rows, every scroll position):
// - every control routes a tap at its centre and all four inner edges to
//   itself, every target is at least 44 x 44, and nothing overlaps the header,
//   the tab bar or another item;
// - every pixel of the content area that reacts to a tap lies inside a drawn
//   control (no invisible zones);
// - Stop is only its drawn button, is never next to Pause, and its label and
//   the rest of its row do nothing;
// - the Local AI prompts keep their buttons inside the dialog card, clear of
//   the tab bar.
//
//   g++ -std=c++11 -Wall -Wextra -Werror -pedantic tests/workshop_os12_tabs_layout_smoke.cpp -o /tmp/tabs-layout-smoke

#include "../firmware/platform/ui/more_layout.hpp"
#include "../firmware/platform/ui/tabs_layout.hpp"

#include <stdio.h>
#include <string.h>

using namespace workshop::ui;
using namespace workshop::ui::tabs;

namespace {

int g_failures = 0;
int g_checks = 0;

void check(bool ok, const char* what, const char* where, int a = 0, int b = 0) {
  ++g_checks;
  if (ok) return;
  ++g_failures;
  if (g_failures <= 60) printf("FAIL %s [%s] (%d, %d)\n", what, where, a, b);
}

bool bigEnough(const Rect& r) { return r.w >= kMinTouch && r.h >= kMinTouch; }
bool sameHit(const Hit& a, const Hit& b) { return a.kind == b.kind && a.index == b.index && a.part == b.part; }

void probePoints(const Rect& r, int xs[5], int ys[5]) {
  xs[0] = r.x + r.w / 2; ys[0] = r.y + r.h / 2;
  xs[1] = r.x;           ys[1] = r.y + r.h / 2;
  xs[2] = r.right() - 1; ys[2] = r.y + r.h / 2;
  xs[3] = r.x + r.w / 2; ys[3] = r.y;
  xs[4] = r.x + r.w / 2; ys[4] = r.bottom() - 1;
}

void expectRoutes(Screen s, View id, uint8_t n, uint8_t scroll, const Rect& r, const Hit& want, const char* where) {
  int xs[5], ys[5];
  probePoints(r, xs, ys);
  for (int i = 0; i < 5; ++i) {
    const Hit got = hitTest(s, id, n, scroll, xs[i], ys[i]);
    check(sameHit(got, want), "tap routes to its control", where, xs[i], ys[i]);
  }
}

// The drawn target a hit lands on (what the user sees as the control).
Rect drawnTarget(Screen s, const ViewSpec& v, uint8_t n, uint8_t scroll, const Hit& h) {
  if (h.kind == HitKind::Segment) return segmentRect(s, h.index);
  if (h.kind == HitKind::Tab) return more::tabRect(s, h.index);
  if (h.kind == HitKind::ScrollUp) return more::scrollUpRect(s);
  if (h.kind == HitKind::ScrollDown) return more::scrollDownRect(s);
  if (h.kind != HitKind::Item) return makeRect(0, 0, 0, 0);
  const Rect r = itemRect(s, v, n, scroll, h.index);
  const ItemSpec& it = item(v, h.index);
  if (it.kind == ItemKind::Hold) return holdTouchRect(s, r);
  if (it.kind == ItemKind::Row && it.rowKind == RowKind::Stepper) return more::partTouchRect(s, r, it.rowKind, h.part);
  return r;  // cards, primary buttons and rows are drawn over their whole rect
}

void checkChrome(Screen s, const char* o) {
  const Rect band = more::tabBand(s), header = more::headerBand(s), content = more::contentBand(s);
  check(!intersects(segmentBand(s), header) && !intersects(segmentBand(s), band), "segments between header and tabs", o);
  for (uint8_t i = 0; i < kSegmentCount; ++i) {
    const Rect r = segmentRect(s, i);
    check(bigEnough(r), "segment at least 44x44", o, r.w, r.h);
    check(inside(r, content), "segment inside content", o, i);
    for (uint8_t j = static_cast<uint8_t>(i + 1); j < kSegmentCount; ++j)
      check(!intersects(r, segmentRect(s, j)), "segments do not overlap", o, i, j);
    check(segmentOf(segmentView(i)) == i, "segment <-> view round trip", o, i);
  }
  // Local AI prompts: buttons in the dialog card, never on the tab bar.
  const Rect card = more::dialogCard(s);
  const Rect cancel = promptCancelRect(s), allow = promptAllowRect(s);
  check(bigEnough(cancel) && bigEnough(allow), "prompt buttons at least 44x44", o);
  check(inside(cancel, card) && inside(allow, card), "prompt buttons inside the card", o);
  check(!intersects(cancel, band) && !intersects(allow, band), "prompt buttons clear of the tab bar", o);
  check(!intersects(cancel, allow), "prompt buttons apart", o);
}

void checkTree(const char* o) {
  for (uint8_t i = 0; i < kViewCount; ++i) {
    const ViewSpec& v = kViews[i];
    check(static_cast<uint8_t>(v.id) == i, "view table in id order", v.title, i);
    check(v.itemCount > 0, "view has items", v.title);
    check(!v.repeat || v.list, "repeating views are lists", v.title);
    check(v.segments == (v.tab == Tab::Printer), "only Printer has segments", v.title);
    for (uint8_t j = 0; j < v.itemCount; ++j) {
      const ItemSpec& it = v.items[j];
      check(it.label && it.label[0], "item has a label", v.title, j);
      if (v.list) check(it.kind == ItemKind::Row, "lists hold rows only", it.label);
      if (it.kind == ItemKind::Card && it.tappable) check(v.id == View::Home, "only the Home card is a button", it.label);
    }
  }
  // Stop exists exactly once, as the hold item on Control, after Pause.
  int holds = 0, primaries = 0;
  for (uint8_t i = 0; i < kViewCount; ++i)
    for (uint8_t j = 0; j < kViews[i].itemCount; ++j) {
      if (kViews[i].items[j].kind == ItemKind::Hold) ++holds;
      if (kViews[i].items[j].kind == ItemKind::Primary) ++primaries;
    }
  check(holds == 1 && primaries == 1, "one hold (Stop) and one primary (Pause/Resume)", o, holds, primaries);
  const ViewSpec& c = view(View::PrinterControl);
  check(c.items[0].id == ItemId::ControlPrimary && c.items[c.itemCount - 1].id == ItemId::ControlStop,
        "Pause first, Stop last on Control", o);
  // The clock text used for "done at".
  char t[16];
  check(strcmp(clockText(t, sizeof(t), 18, 42, false), "6:42 PM") == 0, "12-hour clock", t);
  check(strcmp(clockText(t, sizeof(t), 0, 5, false), "12:05 AM") == 0, "midnight", t);
  check(strcmp(clockText(t, sizeof(t), 12, 0, false), "12:00 PM") == 0, "noon", t);
  check(strcmp(clockText(t, sizeof(t), 7, 9, true), "07:09") == 0, "24-hour clock", t);
  check(strcmp(clockText(t, sizeof(t), 23, 59, true), "23:59") == 0, "24-hour late", t);
}

void checkItem(Screen s, const ViewSpec& v, uint8_t n, uint8_t scroll, uint8_t i, const Rect& r, const char* o, int& controls) {
  const ItemSpec& it = item(v, i);
  char where[112];
  snprintf(where, sizeof(where), "%s / %s / %s / n=%u scroll=%u", o, v.title, it.label, (unsigned)n, (unsigned)scroll);
  check(r.h >= kMinTouch && r.h % more::kRowH == 0, "item is whole 44 px slots", where, r.h);
  check(inside(r, more::contentBand(s)), "item inside the content area", where, r.y, r.bottom());
  check(!intersects(r, more::tabBand(s)) && !intersects(r, more::headerBand(s)), "item clear of header and tab bar", where);
  if (v.segments) check(!intersects(r, segmentBand(s)), "item clear of the segments", where);

  switch (it.kind) {
    case ItemKind::Card:
      if (it.tappable) {
        expectRoutes(s, v.id, n, scroll, r, makeHit(HitKind::Item, i, Part::Whole), where);
        ++controls;
      } else {
        expectRoutes(s, v.id, n, scroll, r, makeHit(HitKind::None, i, Part::Whole), where);
      }
      break;
    case ItemKind::Temps:
      expectRoutes(s, v.id, n, scroll, r, makeHit(HitKind::None, i, Part::Whole), where);
      for (uint8_t c = 0; c < 3; ++c) {
        const Rect cell = tempCellRect(s, r, c);
        check(inside(cell, r) && cell.w >= 96, "temperature cell fits", where, cell.w);
      }
      check(s.landscape() ? r.h == more::kRowH : r.h == 3 * more::kRowH, "strip in landscape, rows in portrait", where, r.h);
      break;
    case ItemKind::Primary:
      check(bigEnough(r), "primary at least 44x44", where);
      check(inside(primaryDrawRect(r), r), "primary drawn inside its row", where);
      expectRoutes(s, v.id, n, scroll, r, makeHit(HitKind::Item, i, Part::Whole), where);
      ++controls;
      break;
    case ItemKind::Hold: {
      const Rect touch = holdTouchRect(s, r), drawn = holdDrawRect(s, r);
      check(bigEnough(touch), "hold button at least 44x44", where, touch.w, touch.h);
      check(inside(drawn, touch) && inside(touch, r), "hold button inside its row", where);
      check(touch.w <= r.w / 2, "hold button is not the whole row", where, touch.w);
      expectRoutes(s, v.id, n, scroll, touch, makeHit(HitKind::Item, i, Part::Whole), where);
      // The label side of the row does nothing.
      const Rect label = makeRect(r.x, r.y, touch.x - r.x, r.h);
      expectRoutes(s, v.id, n, scroll, label, makeHit(HitKind::None, i, Part::Whole), where);
      ++controls;
      break;
    }
    case ItemKind::Row:
    default: {
      check(more::labelRect(s, r, it.rowKind).w > 40, "label has room", where);
      if (it.rowKind == RowKind::Stepper) {
        const Part parts[2] = {Part::Minus, Part::Plus};
        for (int p = 0; p < 2; ++p) {
          const Rect touch = more::partTouchRect(s, r, it.rowKind, parts[p]);
          check(bigEnough(touch) && inside(touch, r), "stepper button at least 44x44 in its row", where);
          expectRoutes(s, v.id, n, scroll, touch, makeHit(HitKind::Item, i, parts[p]), where);
          ++controls;
        }
        check(more::stepperValueRect(s, r).w >= 60, "stepper value has room", where);
      } else {
        expectRoutes(s, v.id, n, scroll, r, makeHit(HitKind::Item, i, Part::Whole), where);
        ++controls;
        if (it.rowKind != RowKind::Action) check(more::valueRect(s, r, it.rowKind).w > 40, "value slot has room", where);
      }
      break;
    }
  }
}

// Every reacting pixel of the content area is inside the drawn control it
// routes to.
void checkNoHiddenZones(Screen s, const ViewSpec& v, uint8_t n, uint8_t scroll, const char* where) {
  int stray = 0, sx = 0, sy = 0;
  for (int y = 0; y < s.h; ++y)
    for (int x = 0; x < s.w; ++x) {
      const Hit h = hitTest(s, v.id, n, scroll, x, y);
      if (h.kind == HitKind::None) continue;
      if (!drawnTarget(s, v, n, scroll, h).contains(x, y)) { if (!stray) { sx = x; sy = y; } ++stray; }
    }
  check(stray == 0, "every tap lands on a drawn control", where, sx, sy);
}

void checkView(Screen s, const ViewSpec& v, uint8_t n, const char* o, int& controls) {
  char where[96];
  snprintf(where, sizeof(where), "%s / %s / n=%u", o, v.title, (unsigned)n);
  const uint8_t count = itemCount(v, n);
  const uint8_t maxS = maxScroll(s, v, n);
  check(clampScroll(s, v, n, 1000) == maxS && clampScroll(s, v, n, -2) == 0, "scroll clamps", where);
  if (!v.list) check(maxS == 0, "cards views never scroll", where);

  for (uint8_t t = 0; t < kTabCount; ++t) {
    expectRoutes(s, v.id, n, 0, more::tabRect(s, t), makeHit(HitKind::Tab, t, Part::Whole), where);
    ++controls;
  }
  if (v.segments)
    for (uint8_t i = 0; i < kSegmentCount; ++i) {
      expectRoutes(s, v.id, n, 0, segmentRect(s, i), makeHit(HitKind::Segment, i, Part::Whole), where);
      ++controls;
    }
  if (maxS > 0) {
    expectRoutes(s, v.id, n, 0, more::scrollUpRect(s), makeHit(HitKind::ScrollUp, 0, Part::Whole), where);
    expectRoutes(s, v.id, n, 0, more::scrollDownRect(s), makeHit(HitKind::ScrollDown, 0, Part::Whole), where);
    controls += 2;
  } else {
    // No scroll buttons: the header's right side is the status chip, not a target.
    const Hit h = hitTest(s, v.id, n, 0, more::scrollDownRect(s).x + 10, 20);
    check(h.kind == HitKind::None, "header is not a target without scroll buttons", where);
  }

  bool seen[kMaxAmsRows + 1] = {false};
  for (int scroll = 0; scroll <= maxS; ++scroll) {
    for (uint8_t i = 0; i < count; ++i) {
      const Rect r = itemRect(s, v, n, static_cast<uint8_t>(scroll), i);
      if (r.empty()) continue;
      seen[i] = true;
      checkItem(s, v, n, static_cast<uint8_t>(scroll), i, r, o, controls);
      for (uint8_t j = static_cast<uint8_t>(i + 1); j < count; ++j)
        check(!intersects(r, itemRect(s, v, n, static_cast<uint8_t>(scroll), j)), "items do not overlap", where, i, j);
    }
    checkNoHiddenZones(s, v, n, static_cast<uint8_t>(scroll), where);
  }
  for (uint8_t i = 0; i < count; ++i) check(seen[i], v.list ? "every row can be scrolled into view" : "every item fits", where, i);
  int pos = 0, guard = 0;
  while (pos < maxS && guard++ < 64) pos = clampScroll(s, v, n, pos + more::scrollStep(s));
  check(pos == maxS, "scroll down reaches the last row", where, pos);
}

void checkStop(Screen s, const char* o) {
  const ViewSpec& c = view(View::PrinterControl);
  const Rect primary = itemRect(s, c, 0, 0, 0);
  const Rect stopRow = itemRect(s, c, 0, 0, static_cast<uint8_t>(c.itemCount - 1));
  const Rect stop = holdItemTouch(s, View::PrinterControl, 0, 0, ItemId::ControlStop);
  check(!stop.empty() && stop.x == holdTouchRect(s, stopRow).x, "Stop target found by id", o);
  check(stop.y - primary.bottom() >= 2 * more::kRowH, "two rows between Pause and Stop", o, stop.y - primary.bottom());
  check(!intersects(stop, more::tabBand(s)), "Stop clear of the tab bar", o);
  check(stop.w * stop.h < primary.w * primary.h / 2, "Stop is a smaller target than Pause", o);
  // No other view has a Stop target.
  for (uint8_t i = 0; i < kViewCount; ++i) {
    if (kViews[i].id == View::PrinterControl) continue;
    check(holdItemTouch(s, kViews[i].id, kMaxAmsRows, 0, ItemId::ControlStop).empty(), "Stop only on Control", kViews[i].title);
  }
}

}  // namespace

int main() {
  const Screen screens[2] = {more::makeScreen(480, 320), more::makeScreen(320, 480)};
  const char* names[2] = {"landscape 480x320", "portrait 320x480"};
  checkTree("tree");
  int controls[2] = {0, 0};
  for (int k = 0; k < 2; ++k) {
    checkChrome(screens[k], names[k]);
    checkStop(screens[k], names[k]);
    for (uint8_t i = 0; i < kViewCount; ++i) {
      const ViewSpec& v = kViews[i];
      if (v.repeat) {
        for (uint8_t n = 0; n <= kMaxAmsRows; ++n) checkView(screens[k], v, n, names[k], controls[k]);
      } else {
        checkView(screens[k], v, 0, names[k], controls[k]);
      }
    }
  }
  if (g_failures) {
    printf("tabs-layout smoke: %d of %d checks failed\n", g_failures, g_checks);
    return 1;
  }
  printf("tabs-layout smoke: PASS (%d checks; %d views; %d / %d control routes probed in landscape / portrait)\n",
         g_checks, static_cast<int>(kViewCount), controls[0], controls[1]);
  return 0;
}
