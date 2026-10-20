#pragma once

// Workshop OS 12.3: geometry for the WS350 Home, Printer and Workshop tabs.
//
// Plain C++11, no Arduino. Built on the More layout (more_layout.hpp, which
// must be included first): the same 44 px header, the same tab bar, the same
// 44 px slots and row controls. The firmware draws and hit-tests the three
// tabs from these functions only, and tests/workshop_os12_tabs_layout_smoke.cpp
// checks them on the host in both orientations, for every state the firmware
// can show.
//
// Rules this file encodes (on top of the More rules):
// - a view is a stack of items in 44 px slots between the header and the tab
//   bar: status cards (several slots), a temperature strip (one slot in
//   landscape, three plain rows in portrait) and More-style rows;
// - nothing is tappable unless it is drawn as tappable (a card with a chevron,
//   a row control, a button). There are no invisible zones;
// - Stop is a hold-guarded button on its own row, never next to Pause, and
//   only the drawn button routes to it;
// - the calm idle screen (12.3.3) has no controls at all: the whole screen is
//   one wake target, and a wake tap never reaches a control below it;
// - (12.3.6) the tab bar touch zone keeps the More guard band (tabTouchRect),
//   only interactive items are drawn raised (itemInteractive), and hitRect()
//   gives the rectangle the pressed highlight outlines.
// - (12.3.9) while a print runs, the Home and Printer status cards share one
//   layout (printCardLayout): the percentage in the 48 px numeric font, time
//   left and the done-at time beside it, the progress bar, one detail line.
//   The done-at time is fixed when the printer's estimate changes (DoneAt),
//   so every screen shows the same time and it does not tick.

#include <stdio.h>

namespace workshop {
namespace ui {
namespace tabs {

using more::Part;
using more::Rect;
using more::RowKind;
using more::Screen;
using more::kMinTouch;
using more::kTabCount;
using more::makeRect;

// Tab bar index of each tab (the same tab bar as More).
enum class Tab : uint8_t { Home = 0, Printer = 1, Workshop = 2 };

enum class View : uint8_t {
  Home = 0,
  PrinterStatus,
  PrinterAms,
  PrinterControl,
  WorkshopSetup,      // Filament Inventory not connected
  WorkshopInventory,  // Filament Inventory connected
  Count
};

static const uint8_t kViewCount = static_cast<uint8_t>(View::Count);

enum class ItemKind : uint8_t {
  Card,     // status card over several slots; one target when tappable
  Temps,    // read-only temperatures: a strip in landscape, rows in portrait
  Row,      // a More row (Info, Nav, Toggle, Stepper, Action)
  Primary,  // the view's main action: a filled button across the row
  Hold,     // a hold-guarded action; only its button is a target
};

enum class ItemId : uint8_t {
  None = 0,
  // Home
  HomeCard, HomeTemps, HomeExtra,
  // Printer > Status
  PrinterCard, PrinterTemps, PrinterDetail,
  // Printer > AMS (one row per tray, repeated)
  AmsTray,
  // Printer > Control
  ControlPrimary, ControlLight, ControlPower, ControlStop,
  // Workshop
  WsInventorySetup, WsHowTo, WsInventory, WsReadiness, WsLoaded, WsReview, WsManage,
  WsTimer, WsTimerLength, WsNote,
  Count
};

struct ItemSpec {
  ItemId id;
  ItemKind kind;
  RowKind rowKind;  // Row items: the More row kind
  bool tappable;    // Card items: the whole card opens something
  const char* label;
};

struct ViewSpec {
  View id;
  Tab tab;
  bool segments;    // Printer's Status / AMS / Control control in the first slot
  bool list;        // one-slot rows only; scrolls when longer than the screen
  bool repeat;      // items[0] repeated for a runtime count (AMS trays)
  const char* title;
  const ItemSpec* items;
  uint8_t itemCount;
};

#define WT_ITEMS(name) name, static_cast<uint8_t>(sizeof(name) / sizeof(name[0]))

static const ItemSpec kHomeItems[] = {
  {ItemId::HomeCard, ItemKind::Card, RowKind::Info, true, "Print"},
  {ItemId::HomeTemps, ItemKind::Temps, RowKind::Info, false, "Temperatures"},
  {ItemId::HomeExtra, ItemKind::Row, RowKind::Nav, false, "Filament"},
};

static const ItemSpec kPrinterStatusItems[] = {
  {ItemId::PrinterCard, ItemKind::Card, RowKind::Info, false, "Status"},
  {ItemId::PrinterTemps, ItemKind::Temps, RowKind::Info, false, "Temperatures"},
  {ItemId::PrinterDetail, ItemKind::Row, RowKind::Info, false, "Layer"},
};

static const ItemSpec kPrinterAmsItems[] = {
  {ItemId::AmsTray, ItemKind::Row, RowKind::Info, false, "Slot"},
};

static const ItemSpec kPrinterControlItems[] = {
  {ItemId::ControlPrimary, ItemKind::Primary, RowKind::Action, false, "Pause print"},
  {ItemId::ControlLight, ItemKind::Row, RowKind::Toggle, false, "Chamber light"},
  {ItemId::ControlPower, ItemKind::Row, RowKind::Action, false, "Printer power"},
  {ItemId::ControlStop, ItemKind::Hold, RowKind::Action, false, "Stop print"},
};

static const ItemSpec kWorkshopSetupItems[] = {
  {ItemId::WsInventorySetup, ItemKind::Row, RowKind::Nav, false, "Filament inventory"},
  {ItemId::WsHowTo, ItemKind::Row, RowKind::Info, false, "How to connect"},
  {ItemId::WsTimer, ItemKind::Row, RowKind::Action, false, "Timer"},
  {ItemId::WsTimerLength, ItemKind::Row, RowKind::Stepper, false, "Timer length"},
  {ItemId::WsNote, ItemKind::Row, RowKind::Info, false, "Note"},
};

static const ItemSpec kWorkshopInventoryItems[] = {
  {ItemId::WsInventory, ItemKind::Row, RowKind::Action, false, "Filament inventory"},
  {ItemId::WsReadiness, ItemKind::Row, RowKind::Info, false, "Print readiness"},
  {ItemId::WsLoaded, ItemKind::Row, RowKind::Info, false, "Loaded spools"},
  {ItemId::WsReview, ItemKind::Row, RowKind::Info, false, "Needs review"},
  {ItemId::WsTimer, ItemKind::Row, RowKind::Action, false, "Timer"},
  {ItemId::WsTimerLength, ItemKind::Row, RowKind::Stepper, false, "Timer length"},
  {ItemId::WsManage, ItemKind::Row, RowKind::Nav, false, "Manage in Local Portal"},
  {ItemId::WsNote, ItemKind::Row, RowKind::Info, false, "Note"},
};

static const ViewSpec kViews[] = {
  {View::Home, Tab::Home, false, false, false, "Home", WT_ITEMS(kHomeItems)},
  {View::PrinterStatus, Tab::Printer, true, false, false, "Printer", WT_ITEMS(kPrinterStatusItems)},
  {View::PrinterAms, Tab::Printer, true, true, true, "Printer", WT_ITEMS(kPrinterAmsItems)},
  {View::PrinterControl, Tab::Printer, true, false, false, "Printer", WT_ITEMS(kPrinterControlItems)},
  {View::WorkshopSetup, Tab::Workshop, false, true, false, "Workshop", WT_ITEMS(kWorkshopSetupItems)},
  {View::WorkshopInventory, Tab::Workshop, false, true, false, "Workshop", WT_ITEMS(kWorkshopInventoryItems)},
};

#undef WT_ITEMS

// The most AMS rows the firmware lists: 4 units x 4 trays + the external spool.
static const uint8_t kMaxAmsRows = 17;

inline const ViewSpec& view(View id) {
  const uint8_t i = static_cast<uint8_t>(id);
  return kViews[i < kViewCount ? i : 0];
}

// Number of items shown. Repeating views take the runtime count.
inline uint8_t itemCount(const ViewSpec& v, uint8_t runtimeCount) {
  if (!v.repeat) return v.itemCount;
  return runtimeCount > kMaxAmsRows ? kMaxAmsRows : runtimeCount;
}

inline const ItemSpec& item(const ViewSpec& v, uint8_t i) {
  if (v.repeat || i >= v.itemCount) return v.items[0];
  return v.items[i];
}

// ---------------------------------------------------------------------------
// Slots
// ---------------------------------------------------------------------------

inline uint8_t firstSlot(const ViewSpec& v) { return v.segments ? 1 : 0; }

inline uint8_t itemSlots(Screen s, const ViewSpec& v, const ItemSpec& it) {
  (void)v;
  switch (it.kind) {
    case ItemKind::Card:
      if (it.id == ItemId::HomeCard) return 3;
      return s.landscape() ? 2 : 3;
    case ItemKind::Temps:
      return s.landscape() ? 1 : 3;
    default:
      return 1;
  }
}

inline uint8_t listCapacity(Screen s, const ViewSpec& v) {
  const int n = more::visibleRows(s) - firstSlot(v);
  return static_cast<uint8_t>(n > 0 ? n : 0);
}

inline uint8_t maxScroll(Screen s, const ViewSpec& v, uint8_t runtimeCount) {
  if (!v.list) return 0;
  const uint8_t n = itemCount(v, runtimeCount), cap = listCapacity(s, v);
  return static_cast<uint8_t>(n > cap ? n - cap : 0);
}

inline bool scrolls(Screen s, const ViewSpec& v, uint8_t runtimeCount) { return maxScroll(s, v, runtimeCount) > 0; }

inline uint8_t clampScroll(Screen s, const ViewSpec& v, uint8_t runtimeCount, int scroll) {
  const int m = maxScroll(s, v, runtimeCount);
  if (scroll < 0) return 0;
  return static_cast<uint8_t>(scroll > m ? m : scroll);
}

// Rectangle of item `i`, or empty when it is scrolled out of view or does
// not fit.
inline Rect itemRect(Screen s, const ViewSpec& v, uint8_t runtimeCount, uint8_t scroll, uint8_t i) {
  const uint8_t n = itemCount(v, runtimeCount);
  if (i >= n) return makeRect(0, 0, 0, 0);
  if (!v.list) scroll = 0;
  if (i < scroll) return makeRect(0, 0, 0, 0);
  int slot = firstSlot(v);
  for (uint8_t j = scroll; j < i; ++j) slot += itemSlots(s, v, item(v, j));
  const int span = itemSlots(s, v, item(v, i));
  if (slot + span > more::visibleRows(s)) return makeRect(0, 0, 0, 0);
  const Rect top = more::slotRect(s, static_cast<uint8_t>(slot));
  return makeRect(top.x, top.y, top.w, span * more::kRowH);
}

// ---------------------------------------------------------------------------
// Printer segments (Status / AMS / Control)
// ---------------------------------------------------------------------------

// Four buttons: Status, AMS and Control select a view; Camera (12.3.7) opens
// the camera page, whose Back returns to Printer.
static const uint8_t kSegmentCount = 4;
static const uint8_t kViewSegments = 3;
static const uint8_t kCameraSegment = 3;

inline Rect segmentBand(Screen s) { return more::slotRect(s, 0); }

inline Rect segmentRect(Screen s, uint8_t i) {
  const Rect band = segmentBand(s);
  const int cell = band.w / kSegmentCount;
  const int x = band.x + i * cell;
  return makeRect(x, band.y, i == kSegmentCount - 1 ? band.right() - x : cell, band.h);
}

inline View segmentView(uint8_t i) {
  return i == 1 ? View::PrinterAms : (i == 2 ? View::PrinterControl : View::PrinterStatus);
}

inline uint8_t segmentOf(View v) {
  return v == View::PrinterAms ? 1 : (v == View::PrinterControl ? 2 : 0);
}

// /hub/views and /hub/show ids of the three Printer segments (catalog v3,
// 12.3.3): "printer" opens Status, "printer-ams" AMS, "printer-control"
// Control.
inline const char* printerViewId(View v) {
  return v == View::PrinterAms ? "printer-ams" : (v == View::PrinterControl ? "printer-control" : "printer");
}

inline bool printerViewFromId(const char* id, View& out) {
  if (!id) return false;
  for (uint8_t i = 0; i < kViewSegments; ++i) {
    const View v = segmentView(i);
    const char* a = printerViewId(v);
    const char* b = id;
    while (*a && *a == *b) { ++a; ++b; }
    if (*a == 0 && *b == 0) { out = v; return true; }
  }
  return false;
}

// ---------------------------------------------------------------------------
// Inside items
// ---------------------------------------------------------------------------

// Temperature cells: three side by side in landscape, three rows in portrait.
inline Rect tempCellRect(Screen s, const Rect& area, uint8_t i) {
  if (s.landscape()) {
    const int cell = area.w / 3;
    const int x = area.x + i * cell;
    return makeRect(x, area.y, i == 2 ? area.right() - x : cell, area.h);
  }
  return makeRect(area.x, area.y + i * more::kRowH, area.w, more::kRowH);
}

// Primary button: drawn across the row; the whole row is the target.
inline Rect primaryDrawRect(const Rect& row) { return makeRect(row.x, row.y + 2, row.w, row.h - 4); }

// Hold button (Stop): right-aligned, smaller than a primary button and
// outlined. The touch area is the button widened by 4 px and the full row
// height; the rest of the row is not a target.
inline Rect holdDrawRect(Screen s, const Rect& row) {
  const int w = s.landscape() ? 136 : 116;
  return makeRect(row.right() - 8 - w, row.y + 5, w, 34);
}

inline Rect holdTouchRect(Screen s, const Rect& row) {
  const Rect d = holdDrawRect(s, row);
  return makeRect(d.x - 4, row.y, d.w + 8, row.h);
}

// Card chevron (drawn on tappable cards so the target is visible).
inline int cardChevronX(const Rect& card) { return card.right() - 16; }

// Print status card while a print runs (12.3.9). Home's card (three slots,
// tappable, with a chevron) also has the printer and job names on top;
// Printer > Status (two slots in landscape) has the job name as its detail
// line. The parts are laid out in an 88 px block (Printer) or a 132 px block
// (Home), centred in taller cards.
struct PrintCardLayout {
  Rect names;    // Home only: printer name (10 px) over the job name (14 px)
  Rect percent;  // the digits in the 48 px numeric font, then "%"
  Rect left;     // "12h 53m left" (19 px), or "Paused"
  Rect doneAt;   // "Done 9:09 AM" (14 px)
  Rect bar;      // progress bar
  Rect detail;   // Home: layer, or the first error; Printer: the job name
};

static const int16_t kPercentW = 116;  // "100" in font 6 (3 x 27 px) and "%" in 19 px
static const int16_t kPercentH = 40;   // font 6 digits are 36 px above the baseline
static const int16_t kProgressH = 10;

inline PrintCardLayout printCardLayout(Screen s, const Rect& card, bool home) {
  (void)s;
  PrintCardLayout c;
  const int x = card.x + 18;
  const int w = card.w - 18 - (home ? 34 : 18);  // Home leaves room for the chevron
  const int block = home ? 132 : 88;
  const int y = card.y + (card.h > block ? (card.h - block) / 2 : 0);
  const int top = home ? 42 : 4;
  const int colX = x + kPercentW + 8, colW = x + w - colX;
  c.names = home ? makeRect(x, y + 5, w, 34) : makeRect(0, 0, 0, 0);
  c.percent = makeRect(x, y + top, kPercentW, kPercentH + 6);
  c.left = makeRect(colX, y + top + 2, colW, 22);
  c.doneAt = makeRect(colX, y + top + 26, colW, 18);
  c.bar = makeRect(x, y + top + kPercentH + 12, w, kProgressH);
  c.detail = makeRect(x, c.bar.bottom() + 4, w, 16);
  return c;
}

// One done-at time for every screen (12.3.9). The printer reports whole
// minutes left; recomputing now + minutes on every frame made the time jump
// by a minute whenever the seconds wrapped, and Home and Printer could show
// different times. The time is fixed when the estimate changes, and again
// only if it falls more than two minutes behind (a stalled estimate).
struct DoneAt {
  uint16_t minutes;  // the estimate the time was fixed for; 0 = none
  long epoch;        // the fixed done-at time (seconds)
};

inline long doneAtEpoch(DoneAt& d, uint16_t minutesLeft, long now) {
  if (!minutesLeft) { d.minutes = 0; d.epoch = 0; return 0; }
  const long fresh = now + static_cast<long>(minutesLeft) * 60L;
  if (d.minutes != minutesLeft || d.epoch <= 0 || fresh - d.epoch > 120L || d.epoch - fresh > 120L) {
    d.minutes = minutesLeft;
    d.epoch = fresh;
  }
  return d.epoch;
}

// Header: title on the left, chip or scroll buttons on the right (as More).
inline Rect titleRect(Screen s, bool scrollButtons) { return more::titleRect(s, true, scrollButtons); }

// ---------------------------------------------------------------------------
// Hit testing
// ---------------------------------------------------------------------------

enum class HitKind : uint8_t { None = 0, Tab, ScrollUp, ScrollDown, Segment, Item, Wake };

struct Hit {
  HitKind kind;
  uint8_t index;  // tab, segment or item index
  Part part;
};

inline Hit makeHit(HitKind kind, uint8_t index, Part part) {
  Hit h;
  h.kind = kind;
  h.index = index;
  h.part = part;
  return h;
}

inline Hit hitTest(Screen s, View id, uint8_t runtimeCount, uint8_t scroll, int x, int y) {
  // The tab bar is drawn on every tab, so it is always live.
  for (uint8_t i = 0; i < kTabCount; ++i)
    if (more::tabTouchRect(s, i).contains(x, y)) return makeHit(HitKind::Tab, i, Part::Whole);
  if (more::tabBand(s).contains(x, y)) return makeHit(HitKind::None, 0, Part::Whole);  // the guard band
  const ViewSpec& v = view(id);
  if (scrolls(s, v, runtimeCount)) {
    if (more::scrollUpRect(s).contains(x, y)) return makeHit(HitKind::ScrollUp, 0, Part::Whole);
    if (more::scrollDownRect(s).contains(x, y)) return makeHit(HitKind::ScrollDown, 0, Part::Whole);
  }
  if (v.segments) {
    for (uint8_t i = 0; i < kSegmentCount; ++i)
      if (segmentRect(s, i).contains(x, y)) return makeHit(HitKind::Segment, i, Part::Whole);
  }
  const uint8_t n = itemCount(v, runtimeCount);
  for (uint8_t i = 0; i < n; ++i) {
    const Rect r = itemRect(s, v, runtimeCount, scroll, i);
    if (!r.contains(x, y)) continue;
    const ItemSpec& it = item(v, i);
    switch (it.kind) {
      case ItemKind::Card:
        return it.tappable ? makeHit(HitKind::Item, i, Part::Whole) : makeHit(HitKind::None, i, Part::Whole);
      case ItemKind::Temps:
        return makeHit(HitKind::None, i, Part::Whole);
      case ItemKind::Primary:
        return makeHit(HitKind::Item, i, Part::Whole);
      case ItemKind::Hold:
        return holdTouchRect(s, r).contains(x, y) ? makeHit(HitKind::Item, i, Part::Whole)
                                                   : makeHit(HitKind::None, i, Part::Whole);
      case ItemKind::Row:
      default: {
        if (it.rowKind == RowKind::Stepper) {
          if (more::partTouchRect(s, r, it.rowKind, Part::Minus).contains(x, y)) return makeHit(HitKind::Item, i, Part::Minus);
          if (more::partTouchRect(s, r, it.rowKind, Part::Plus).contains(x, y)) return makeHit(HitKind::Item, i, Part::Plus);
          return makeHit(HitKind::None, i, Part::Whole);
        }
        return makeHit(HitKind::Item, i, Part::Whole);
      }
    }
  }
  return makeHit(HitKind::None, 0, Part::Whole);
}

// Whether an item does something when tapped. Read-only items (temperature
// strip, Info rows, non-tappable cards) are drawn flat and get no pressed
// highlight (12.3.6).
inline bool itemInteractive(const ItemSpec& it) {
  switch (it.kind) {
    case ItemKind::Card: return it.tappable;
    case ItemKind::Temps: return false;
    case ItemKind::Primary:
    case ItemKind::Hold: return true;
    case ItemKind::Row:
    default: return more::rowInteractive(it.rowKind);
  }
}

// Rectangle a hit refers to (the pressed highlight). Empty for None and
// Wake. Every point hitTest routes to a hit lies inside hitRect of that hit.
inline Rect hitRect(Screen s, View id, uint8_t runtimeCount, uint8_t scroll, const Hit& h) {
  const ViewSpec& v = view(id);
  switch (h.kind) {
    case HitKind::Tab: return more::tabTouchRect(s, h.index);
    case HitKind::ScrollUp: return more::scrollUpRect(s);
    case HitKind::ScrollDown: return more::scrollDownRect(s);
    case HitKind::Segment: return segmentRect(s, h.index);
    case HitKind::Item: {
      const Rect r = itemRect(s, v, runtimeCount, scroll, h.index);
      if (r.empty()) return r;
      const ItemSpec& it = item(v, h.index);
      if (it.kind == ItemKind::Hold) return holdTouchRect(s, r);
      if (it.kind == ItemKind::Row && it.rowKind == RowKind::Stepper) return more::partTouchRect(s, r, it.rowKind, h.part);
      return r;
    }
    default:
      return makeRect(0, 0, 0, 0);
  }
}

// Rectangle the hold-progress bar is drawn over for a hold item (empty when
// the item is not on screen).
inline Rect holdItemTouch(Screen s, View id, uint8_t runtimeCount, uint8_t scroll, ItemId which) {
  const ViewSpec& v = view(id);
  const uint8_t n = itemCount(v, runtimeCount);
  for (uint8_t i = 0; i < n; ++i) {
    const ItemSpec& it = item(v, i);
    if (it.id != which || it.kind != ItemKind::Hold) continue;
    const Rect r = itemRect(s, v, runtimeCount, scroll, i);
    if (r.empty()) return r;
    return holdTouchRect(s, r);
  }
  return makeRect(0, 0, 0, 0);
}

// ---------------------------------------------------------------------------
// Consent prompts (Local AI): the More dialog card and buttons, no tab bar.
// ---------------------------------------------------------------------------

inline Rect promptCancelRect(Screen s) { return more::dialogCancelRect(s); }
inline Rect promptAllowRect(Screen s) { return more::dialogConfirmRect(s); }

// ---------------------------------------------------------------------------
// Clock text for "done at" (ETA): minutes from now in local time.
// ---------------------------------------------------------------------------

// Formats hour/minute as "6:42 PM" or "18:42". Returns `out`.
inline char* clockText(char* out, size_t len, int hour, int minute, bool use24h) {
  if (!out || len < 6) return out;
  hour = ((hour % 24) + 24) % 24;
  minute = ((minute % 60) + 60) % 60;
  int h = hour;
  const char* suffix = "";
  if (!use24h) {
    suffix = hour < 12 ? " AM" : " PM";
    h = hour % 12;
    if (h == 0) h = 12;
  }
  size_t o = 0;
  if (use24h || h >= 10) out[o++] = static_cast<char>('0' + h / 10);
  out[o++] = static_cast<char>('0' + h % 10);
  out[o++] = ':';
  out[o++] = static_cast<char>('0' + minute / 10);
  out[o++] = static_cast<char>('0' + minute % 10);
  for (const char* p = suffix; *p && o + 1 < len; ++p) out[o++] = *p;
  out[o < len ? o : len - 1] = '\0';
  return out;
}

// ---------------------------------------------------------------------------
// Calm idle screen (12.3.3): a large clock, the date, one status line and
// "Tap anywhere to wake". No header, no tab bar, nothing else to tap.
// ---------------------------------------------------------------------------

struct CalmLayout {
  Rect clock;   // the time, centred
  Rect date;    // the date in the saved format
  Rect status;  // one status line on a card surface
  Rect hint;    // "Tap anywhere to wake", where the tab bar would be
};

static const int16_t kCalmClockH = 96;
static const int16_t kCalmDateH = 32;
static const int16_t kCalmGap = 20;

inline CalmLayout calmLayout(Screen s) {
  CalmLayout c;
  c.hint = more::tabBand(s);
  const int total = kCalmClockH + kCalmDateH + kCalmGap + more::kRowH;
  const int top = (c.hint.y - total) / 2;
  const int margin = 16;
  c.clock = makeRect(margin, top, s.w - 2 * margin, kCalmClockH);
  c.date = makeRect(margin, top + kCalmClockH, s.w - 2 * margin, kCalmDateH);
  const int statusW = s.landscape() ? 384 : s.w - 2 * margin;
  c.status = makeRect((s.w - statusW) / 2, c.date.bottom() + kCalmGap, statusW, more::kRowH);
  return c;
}

// The calm screen's only target is the whole screen, and a tap on it only
// wakes the display: it never reaches the tab bar or a Home control.
inline Hit calmHitTest(Screen s, int x, int y) {
  if (x < 0 || y < 0 || x >= s.w || y >= s.h) return makeHit(HitKind::None, 0, Part::Whole);
  return makeHit(HitKind::Wake, 0, Part::Whole);
}

// Date in the saved format (netSettings.dateFormat, 0-5), after the weekday:
// "Sunday · 10/18/2026". `month` is 1-12, `wday` 0 (Sunday) - 6.
inline char* dateText(char* out, size_t len, int year, int month, int day, int wday, uint8_t format) {
  static const char* kDays[] = {"Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"};
  static const char* kMonths[] = {"Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"};
  if (!out || !len) return out;
  const char* wd = kDays[((wday % 7) + 7) % 7];
  const char* mon = kMonths[((month - 1) % 12 + 12) % 12];
  switch (format % 6U) {
    case 1: snprintf(out, len, "%s · %02d-%02d-%04d", wd, day, month, year); break;
    case 2: snprintf(out, len, "%s · %02d/%02d/%04d", wd, month, day, year); break;
    case 3: snprintf(out, len, "%s · %04d-%02d-%02d", wd, year, month, day); break;
    case 4: snprintf(out, len, "%s · %d %s %04d", wd, day, mon, year); break;
    case 5: snprintf(out, len, "%s · %s %d, %04d", wd, mon, day, year); break;
    default: snprintf(out, len, "%s · %02d.%02d.%04d", wd, day, month, year); break;
  }
  return out;
}

// What the calm status line says. A print comes first, then the workshop
// timer, then the printer.
enum class CalmState : uint8_t { NoPrinter, Offline, Attention, Idle, Finished, Printing, Paused, TimerRunning, TimerDone };

struct CalmStatus {
  CalmState state;
  uint8_t percent;        // Printing, Paused
  const char* doneAt;     // Printing: clock time ("6:42 PM"), or empty when unknown
  uint32_t timerSeconds;  // TimerRunning
};

inline char* calmStatusText(char* out, size_t len, const CalmStatus& c) {
  if (!out || !len) return out;
  const unsigned pct = c.percent > 100 ? 100U : c.percent;
  switch (c.state) {
    case CalmState::Printing:
      if (c.doneAt && c.doneAt[0]) snprintf(out, len, "Printing %u%% · done %s", pct, c.doneAt);
      else snprintf(out, len, "Printing %u%%", pct);
      break;
    case CalmState::Paused: snprintf(out, len, "Paused at %u%%", pct); break;
    case CalmState::TimerRunning: {
      const unsigned long t = c.timerSeconds, h = t / 3600UL, m = (t % 3600UL) / 60UL, sec = t % 60UL;
      if (h) snprintf(out, len, "Timer %lu:%02lu:%02lu left", h, m, sec);
      else snprintf(out, len, "Timer %lu:%02lu left", m, sec);
      break;
    }
    case CalmState::TimerDone: snprintf(out, len, "Timer done"); break;
    case CalmState::Attention: snprintf(out, len, "Printer needs attention"); break;
    case CalmState::Offline: snprintf(out, len, "Printer offline"); break;
    case CalmState::NoPrinter: snprintf(out, len, "No printer set up"); break;
    case CalmState::Finished: snprintf(out, len, "Print finished"); break;
    case CalmState::Idle:
    default: snprintf(out, len, "Printer idle"); break;
  }
  return out;
}

}  // namespace tabs
}  // namespace ui
}  // namespace workshop
