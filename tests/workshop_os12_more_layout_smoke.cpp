// Host test for firmware/platform/ui/more_layout.hpp (WS350 More area).
//
// Checks, in landscape 480x320 (the WS350's real orientation) and portrait
// 320x480, that every control on every page routes a tap at its centre and at
// all four inner edges to that control, that nothing overlaps the tab bar,
// that every target is at least 44 x 44, that Back is the same everywhere,
// and that the page tree is at most two levels deep and fully reachable.
//
//   g++ -std=c++11 -Wall -Wextra -Werror -pedantic tests/workshop_os12_more_layout_smoke.cpp -o /tmp/more-layout-smoke

#include "../firmware/platform/ui/more_layout.hpp"

#include <stdio.h>
#include <string.h>

using namespace workshop::ui::more;

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

// Centre plus the four inner edges of a rectangle.
void probePoints(const Rect& r, int xs[5], int ys[5]) {
  xs[0] = r.x + r.w / 2; ys[0] = r.y + r.h / 2;
  xs[1] = r.x;           ys[1] = r.y + r.h / 2;
  xs[2] = r.right() - 1; ys[2] = r.y + r.h / 2;
  xs[3] = r.x + r.w / 2; ys[3] = r.y;
  xs[4] = r.x + r.w / 2; ys[4] = r.bottom() - 1;
}

void expectRoutes(Screen s, PageId id, uint8_t scroll, bool dialog, const Rect& r, const Hit& want, const char* where) {
  int xs[5], ys[5];
  probePoints(r, xs, ys);
  for (int i = 0; i < 5; ++i) {
    const Hit got = hitTest(s, id, scroll, dialog, xs[i], ys[i]);
    check(sameHit(got, want), "tap routes to its control", where, xs[i], ys[i]);
  }
}

void checkChrome(Screen s, const char* o) {
  const Rect band = tabBand(s);
  const Rect header = headerBand(s);
  int covered = 0;
  for (uint8_t i = 0; i < kTabCount; ++i) {
    const Rect t = tabRect(s, i);
    check(bigEnough(t), "tab at least 44x44", o, t.w, t.h);
    check(inside(t, band), "tab inside tab band", o, i);
    covered += t.w;
    for (uint8_t j = static_cast<uint8_t>(i + 1); j < kTabCount; ++j)
      check(!intersects(t, tabRect(s, j)), "tabs do not overlap", o, i, j);
  }
  check(covered == s.w, "tab bar spans the screen", o, covered);
  check(band.bottom() == s.h, "tab bar at the bottom", o);

  const Rect back = backRect(s);
  check(bigEnough(back), "Back at least 44x44", o, back.w, back.h);
  check(back.x == 0 && back.y == 0, "Back at top-left", o);
  check(inside(back, header), "Back inside header", o);
  const Rect up = scrollUpRect(s), down = scrollDownRect(s);
  check(bigEnough(up) && bigEnough(down), "scroll buttons at least 44x44", o);
  check(inside(up, header) && inside(down, header), "scroll buttons inside header", o);
  check(!intersects(up, down) && !intersects(back, up), "header controls do not overlap", o);
  check(titleRect(s, false, true).w >= 96, "title has room next to the scroll buttons", o, titleRect(s, false, true).w);
  check(!intersects(header, band), "header and tab bar are apart", o);
  check(visibleRows(s) >= 4, "at least four rows fit", o, visibleRows(s));
  check(kRowH >= 52, "rows at least 52 px (8 mm) tall", o, kRowH);
  check(scrollStep(s) >= 1, "scroll step positive", o);

  const Rect card = dialogCard(s), cancel = dialogCancelRect(s), confirm = dialogConfirmRect(s);
  check(inside(card, contentBand(s)), "dialog inside content", o);
  check(bigEnough(cancel) && bigEnough(confirm), "dialog buttons at least 44x44", o);
  check(inside(cancel, card) && inside(confirm, card), "dialog buttons inside card", o);
  check(!intersects(cancel, confirm), "dialog buttons apart", o);
}

void checkTree(const char* o) {
  check(kPageCount <= 15, "at most 15 pages", o, kPageCount);
  bool reachable[32] = {false};
  reachable[0] = true;
  for (uint8_t i = 0; i < kPageCount; ++i) {
    const PageSpec& p = kPages[i];
    check(static_cast<uint8_t>(p.id) == i, "page table in id order", p.title, i);
    check(p.level <= 2, "at most two levels below More", p.title, p.level);
    if (i == 0) {
      check(p.layout == PageLayout::Tiles && p.level == 0, "root is the tile page", p.title);
    } else {
      const PageSpec& parent = page(p.parent);
      check(parent.level + 1 == p.level, "parent is one level up", p.title, parent.level);
      check(p.backLabel && p.backLabel[0], "Back names the parent", p.title);
    }
    check(p.viewId && p.viewId[0], "view id present", p.title);
    PageId round = PageId::Root;
    check(pageFromViewId(p.viewId, round) && round == p.id, "view id round trip", p.viewId);
    for (uint8_t j = static_cast<uint8_t>(i + 1); j < kPageCount; ++j)
      check(strcmp(p.viewId, kPages[j].viewId) != 0, "view ids unique", p.viewId);
    if (p.layout != PageLayout::Tiles) check(p.rowCount > 0, "page has rows", p.title);
  }
  for (uint8_t t = 0; t < kRootTileCount; ++t) {
    const PageSpec& p = page(kRootTiles[t]);
    check(p.level == 1 && p.parent == PageId::Root, "tiles open level-1 pages", p.title);
    reachable[static_cast<uint8_t>(p.id)] = true;
  }
  for (uint8_t i = 0; i < kPageCount; ++i) {
    const PageSpec& p = kPages[i];
    for (uint8_t r = 0; r < p.rowCount; ++r) {
      if (p.rows[r].kind != RowKind::Nav) continue;
      const PageSpec& target = page(p.rows[r].target);
      check(target.parent == p.id, "Nav row opens a child of its page", p.rows[r].label);
      reachable[static_cast<uint8_t>(target.id)] = true;
    }
  }
  for (uint8_t i = 0; i < kPageCount; ++i) check(reachable[i], "page reachable from More", kPages[i].title);
  const PageSpec& portal = page(PageId::LocalPortal);
  check(portal.level == 1 && portal.parent == PageId::Root, "Local Portal is one tap below More", o);
  check(pageSensitive(PageId::LocalPortal), "Local Portal is capture-sensitive", o);
  int codeRows = 0;
  for (uint8_t r = 0; r < portal.rowCount; ++r) if (portal.rows[r].kind == RowKind::Code) ++codeRows;
  check(codeRows == 1, "Local Portal shows the access code", o, codeRows);
  // scripts/capture-ws350-views.zsh redacts (8, 89)-(472, 155) on catalog v3:
  // the access-code row must be inside it in 480x320 and never scroll.
  const Screen land = makeScreen(480, 320);
  check(maxScroll(land, PageId::LocalPortal) == 0, "Local Portal does not scroll", o);
  for (uint8_t r = 0; r < portal.rowCount; ++r) {
    if (portal.rows[r].kind != RowKind::Code) continue;
    const Rect code = rowRect(land, PageId::LocalPortal, 0, r);
    check(code.x == 8 && code.y >= 89 && code.right() == 472 && code.bottom() <= 155,
          "access-code row matches the capture redaction", o, code.y, code.bottom());
  }
}

void checkRow(Screen s, PageId id, uint8_t scroll, uint8_t r, const Rect& row, const char* o, int& controls) {
  const PageSpec& p = page(id);
  const RowSpec& spec = p.rows[r];
  char where[96];
  snprintf(where, sizeof(where), "%s / %s / %s", o, p.title, spec.label);
  check(row.h >= kMinTouch, "row at least 44 tall", where, row.h);
  check(inside(row, contentBand(s)), "row inside the content area", where, row.y, row.bottom());
  check(!intersects(row, tabBand(s)), "row clear of the tab bar", where);
  check(!intersects(row, headerBand(s)), "row clear of the header", where);
  check(labelRect(s, row, spec.kind).w > 40, "label has room", where, labelRect(s, row, spec.kind).w);

  Part parts[2];
  int n = 0;
  if (spec.kind == RowKind::Stepper) { parts[0] = Part::Minus; parts[1] = Part::Plus; n = 2; }
  else if (spec.kind == RowKind::Action2) { parts[0] = Part::ActionA; parts[1] = Part::ActionB; n = 2; }
  else { parts[0] = Part::Whole; n = 1; }

  for (int i = 0; i < n; ++i) {
    const Rect touch = partTouchRect(s, row, spec.kind, parts[i]);
    check(bigEnough(touch), "control at least 44x44", where, touch.w, touch.h);
    check(inside(touch, row), "control inside its row", where);
    const Rect drawn = partDrawRect(s, row, spec.kind, parts[i]);
    if (!drawn.empty()) check(inside(drawn, touch), "drawn button inside its touch area", where);
    expectRoutes(s, id, scroll, false, touch, makeHit(HitKind::Row, r, parts[i]), where);
    ++controls;
  }
  if (n == 2) {
    check(!intersects(partTouchRect(s, row, spec.kind, parts[0]), partTouchRect(s, row, spec.kind, parts[1])),
          "two buttons do not overlap", where);
  }
  if (spec.kind == RowKind::Stepper) {
    const Rect value = stepperValueRect(s, row);
    check(value.w >= 60, "stepper value has room", where, value.w);
    check(!intersects(value, partDrawRect(s, row, spec.kind, Part::Minus)), "value clear of '-'", where);
    check(!intersects(value, partDrawRect(s, row, spec.kind, Part::Plus)), "value clear of '+'", where);
    check(!intersects(labelRect(s, row, spec.kind), partDrawRect(s, row, spec.kind, Part::Minus)), "label clear of '-'", where);
  }
  if (spec.kind != RowKind::Stepper && spec.kind != RowKind::Action2) {
    check(valueRect(s, row, spec.kind).w > 40 || spec.kind == RowKind::Action, "value slot has room", where);
  }
  if (spec.kind == RowKind::Toggle) {
    // 12.2.1: the only thing between a toggle's label and its switch is the
    // optional value text, and an empty value draws nothing (12.2.0 drew an
    // em dash there, shown as a stray "|").
    const Rect sw = partDrawRect(s, row, spec.kind, Part::Whole);
    const Rect value = valueRect(s, row, spec.kind);
    check(value.right() <= sw.x - 8, "toggle value text clear of the switch", where, value.right(), sw.x);
    check(labelRect(s, row, spec.kind).right() <= sw.x - 8, "toggle label clear of the switch", where);
    check(!drawsValueText("") && !drawsValueText(nullptr), "toggle with no value draws nothing beside the switch", where);
  }
}

void checkPages(Screen s, const char* o, int& controls) {
  const Rect back = backRect(s);
  for (uint8_t i = 0; i < kPageCount; ++i) {
    const PageId id = kPages[i].id;
    const PageSpec& p = kPages[i];
    char where[96];
    snprintf(where, sizeof(where), "%s / %s", o, p.title);

    // Tabs are live on every page, even with a dialog open.
    for (uint8_t t = 0; t < kTabCount; ++t) {
      expectRoutes(s, id, 0, false, tabRect(s, t), makeHit(HitKind::Tab, t, Part::Whole), where);
      expectRoutes(s, id, 0, true, tabRect(s, t), makeHit(HitKind::Tab, t, Part::Whole), where);
      controls += 2;
    }
    if (p.level > 0) {
      expectRoutes(s, id, 0, false, back, makeHit(HitKind::Back, 0, Part::Whole), where);
      expectRoutes(s, id, 0, true, back, makeHit(HitKind::Back, 0, Part::Whole), where);
      controls += 2;
      if (p.layout == PageLayout::List && p.rowCount > 0) {
        expectRoutes(s, id, 0, true, dialogCancelRect(s), makeHit(HitKind::DialogCancel, 0, Part::Whole), where);
        expectRoutes(s, id, 0, true, dialogConfirmRect(s), makeHit(HitKind::DialogConfirm, 0, Part::Whole), where);
        controls += 2;
      }
    }

    if (p.layout == PageLayout::Tiles) {
      for (uint8_t t = 0; t < kRootTileCount; ++t) {
        const Rect tile = tileRect(s, t);
        check(bigEnough(tile), "tile at least 44x44", where, tile.w, tile.h);
        check(inside(tile, contentBand(s)), "tile inside content", where, tile.y, tile.bottom());
        for (uint8_t u = static_cast<uint8_t>(t + 1); u < kRootTileCount; ++u)
          check(!intersects(tile, tileRect(s, u)), "tiles do not overlap", where, t, u);
        expectRoutes(s, id, 0, false, tile, makeHit(HitKind::Tile, t, Part::Whole), where);
        ++controls;
      }
      continue;
    }

    if (p.layout == PageLayout::Video) {
      const Rect video = videoRect(s, id);
      check(video.h >= 120, "video area is usable", where, video.h);
      check(inside(video, contentBand(s)), "video inside content", where);
    }

    const uint8_t maxS = maxScroll(s, id);
    check(clampScroll(s, id, 1000) == maxS && clampScroll(s, id, -3) == 0, "scroll clamps", where);
    if (maxS > 0) {
      expectRoutes(s, id, 0, false, scrollUpRect(s), makeHit(HitKind::ScrollUp, 0, Part::Whole), where);
      expectRoutes(s, id, 0, false, scrollDownRect(s), makeHit(HitKind::ScrollDown, 0, Part::Whole), where);
      controls += 2;
    }
    bool seen[64] = {false};
    for (int scroll = 0; scroll <= maxS; ++scroll) {
      for (uint8_t r = 0; r < p.rowCount; ++r) {
        const Rect row = rowRect(s, id, static_cast<uint8_t>(scroll), r);
        if (row.empty()) continue;
        seen[r] = true;
        checkRow(s, id, static_cast<uint8_t>(scroll), r, row, o, controls);
      }
    }
    for (uint8_t r = 0; r < p.rowCount; ++r) check(seen[r], "every row can be scrolled into view", where, r);
    // Paging by scrollStep from the top reaches the end.
    int pos = 0, guard = 0;
    while (pos < maxS && guard++ < 64) pos = clampScroll(s, id, pos + scrollStep(s));
    check(pos == maxS, "scroll down reaches the last row", where, pos);
  }
}

}  // namespace

void checkValueText() {
  check(!drawsValueText(nullptr), "null value draws nothing", "value text");
  check(!drawsValueText(""), "empty value draws nothing", "value text");
  check(drawsValueText("Off (stable)"), "a value is drawn", "value text");
}

int main() {
  checkValueText();
  const Screen screens[2] = {makeScreen(480, 320), makeScreen(320, 480)};
  const char* names[2] = {"landscape 480x320", "portrait 320x480"};
  checkTree("tree");
  int controls[2] = {0, 0};
  for (int i = 0; i < 2; ++i) {
    checkChrome(screens[i], names[i]);
    checkPages(screens[i], names[i], controls[i]);
  }
  if (g_failures) {
    printf("more-layout smoke: %d of %d checks failed\n", g_failures, g_checks);
    return 1;
  }
  printf("more-layout smoke: PASS (%d checks; %d pages; %d / %d control routes probed in landscape / portrait)\n",
         g_checks, static_cast<int>(kPageCount), controls[0], controls[1]);
  return 0;
}
