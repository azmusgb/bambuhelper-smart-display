#pragma once

// Workshop OS 12.1: page table and geometry for the WS350 "More" area.
//
// Plain C++11, no Arduino. The firmware draws and hit-tests every More page
// from these functions, and tests/workshop_os12_more_layout_smoke.cpp checks
// them on the host in both orientations. One rectangle function per control
// is used for both drawing and touch, so the two cannot drift apart again.
//
// Rules this file encodes:
// - at most two levels below More;
// - one 44 px header on every page, Back at top-left going to the parent;
// - the tab bar is drawn and live on every page and nothing else sits on it;
// - single-line rows, 55 px tall (about 8.5 mm on the WS350's 3.5" panel,
//   four to a landscape screen), every touch target at least 44 x 44;
// - long pages scroll a row at a time with visible up/down buttons in the
//   header (no gestures, no hidden zones).

#include <stddef.h>
#include <stdint.h>

namespace workshop {
namespace ui {
namespace more {

struct Rect {
  int16_t x;
  int16_t y;
  int16_t w;
  int16_t h;
  bool contains(int px, int py) const { return px >= x && py >= y && px < x + w && py < y + h; }
  bool empty() const { return w <= 0 || h <= 0; }
  int right() const { return x + w; }
  int bottom() const { return y + h; }
};

inline Rect makeRect(int x, int y, int w, int h) {
  Rect r;
  r.x = static_cast<int16_t>(x);
  r.y = static_cast<int16_t>(y);
  r.w = static_cast<int16_t>(w);
  r.h = static_cast<int16_t>(h);
  return r;
}

inline bool intersects(const Rect& a, const Rect& b) {
  return !a.empty() && !b.empty() && a.x < b.right() && b.x < a.right() && a.y < b.bottom() && b.y < a.bottom();
}

inline bool inside(const Rect& inner, const Rect& outer) {
  return inner.x >= outer.x && inner.y >= outer.y && inner.right() <= outer.right() && inner.bottom() <= outer.bottom();
}

struct Screen {
  int16_t w;
  int16_t h;
  bool landscape() const { return w > h; }
};

inline Screen makeScreen(int w, int h) {
  Screen s;
  s.w = static_cast<int16_t>(w);
  s.h = static_cast<int16_t>(h);
  return s;
}

static const int16_t kHeaderH = 44;
static const int16_t kTabH = 54;      // same as hubNavH()
static const int16_t kRowH = 55;
static const int16_t kRowTop = 45;
static const int16_t kMarginX = 8;
static const int16_t kMinTouch = 44;
static const uint8_t kTabCount = 4;

// ---------------------------------------------------------------------------
// Page table
// ---------------------------------------------------------------------------

enum class PageId : uint8_t {
  Root = 0,
  PrinterPower,
  AutoOff,
  Network,
  TimeLocale,
  Display,
  ClockSchedule,
  Gauges,
  SoundAlerts,
  Alerts,
  StatusLight,
  VideoTest,
  LocalPortal,
  UpdatesAbout,
  DeviceHealth,
  Count
};

static const uint8_t kPageCount = static_cast<uint8_t>(PageId::Count);

enum class PageLayout : uint8_t {
  Tiles,   // the More root: six tiles
  List,    // rows from the top, scrolls when longer than the screen
  Video,   // video area with one control row at the bottom
};

enum class RowKind : uint8_t {
  Info,     // read-only; a tap shows the row's reason, if it has one
  Nav,      // opens a sub-page
  Toggle,   // whole row toggles
  Stepper,  // "-" and "+" buttons, value centred between them
  Action,   // whole row runs one action; a button is drawn on the right
  Action2,  // two buttons on the right, each its own target
  Code,     // read-only, large text (the Local Portal access code)
};

enum class Part : uint8_t { Whole = 0, Minus, Plus, ActionA, ActionB };

enum class RowId : uint8_t {
  None = 0,
  // Printer & Power
  PrinterStatus, PlugEnabled, AutoOffNav, CooldownAlert, CooldownTemp, PlugPoll, PlugReadout, ButtonPower,
  // Auto power-off
  AutoOffEnabled, AutoOffDelay, AutoOffDoor,
  // Network
  WifiStatus, WifiSignal, AddressMode, MdnsEnabled, ShowIpAtBoot, TimeLocaleNav,
  // Time & locale
  TimeZone, Clock24h, DateFormat,
  // Display
  Brightness, StandbyBrightness, ClockScheduleNav, GaugesNav, AfterPrint, FinishTimeout, DoorAck,
  KeepPrintScreen, FinishTime, TimeReadout, AnimatedBar, SmallLabels, FanReadout, StatusReadout,
  Theme, AmbientHome, Rotation,
  // Clock & schedule
  NightMode, NightBrightness, NightStart, NightEnd, PongClock, ClockTimeSize, ClockDateSize,
  ClockShowDate, ClockInfo, ClockTimeColor, ClockDateColor,
  // Gauges
  GaugeSelect, GaugeArc, GaugeLabel, GaugeValue, NozzleScale, BedScale, ChamberScale, PowerScale,
  Smoothing, WarnAt, WarnColor, GaugeDefaults, Ams8Slot, Ams9Slot, SplitView, SplitForce, AmsTrayTypes,
  // Sound & Alerts
  EventSounds, TouchSounds, Volume, QuietStart, QuietEnd, AlertsNav, StatusLightNav, SpeakerTest,
  MicTest, Recorder, VideoTestNav,
  // Printer alerts
  HmsEnabled, HmsSeverity, HmsPresent, HmsLookup, AlertGlow, AlertSound, AlertLight, AlertWake,
  GlowMode, GlowStyle, GlowDuration, GlowColor,
  // Status light
  LedEnabled, LedBrightness, LedWhilePrinting, LedPauseBreath, LedFinishEffect, LedFinishTime,
  LedFinishPeak, LedErrorStrobe, LedErrorTime,
  // Video test
  VideoPause,
  // Local Portal
  PortalAddress, PortalName, PortalCode, PortalSignIn, PortalCodeKey,
  // Updates & About
  Version, UpdateAction, UpdateChannel, DateTimeNow, HealthNav,
  // Device health
  HealthTouch, HealthRecovery, HealthPrinter, HealthUptime,
  Count
};

struct RowSpec {
  RowId id;
  RowKind kind;
  const char* label;
  PageId target;  // Nav rows only
};

struct PageSpec {
  PageId id;
  PageId parent;
  uint8_t level;          // 0 = More, 1 = page, 2 = sub-page
  PageLayout layout;
  const char* title;
  const char* backLabel;  // short name of the parent, shown as "< More"
  const char* viewId;     // /hub/views and /hub/show id
  const RowSpec* rows;
  uint8_t rowCount;
};

#define WS_ROWS(name) name, static_cast<uint8_t>(sizeof(name) / sizeof(name[0]))

static const RowSpec kPrinterPowerRows[] = {
  {RowId::PrinterStatus, RowKind::Info, "Printer", PageId::Root},
  {RowId::PlugEnabled, RowKind::Toggle, "Smart plug", PageId::Root},
  {RowId::AutoOffNav, RowKind::Nav, "Auto power-off", PageId::AutoOff},
  {RowId::CooldownAlert, RowKind::Toggle, "Bed cooldown alert", PageId::Root},
  {RowId::CooldownTemp, RowKind::Stepper, "Cooldown at", PageId::Root},
  {RowId::PlugPoll, RowKind::Stepper, "Check plug every", PageId::Root},
  {RowId::PlugReadout, RowKind::Stepper, "Plug readout", PageId::Root},
  {RowId::ButtonPower, RowKind::Toggle, "Button controls power", PageId::Root},
};

static const RowSpec kAutoOffRows[] = {
  {RowId::AutoOffEnabled, RowKind::Toggle, "Auto power-off", PageId::Root},
  {RowId::AutoOffDelay, RowKind::Stepper, "Turn off after", PageId::Root},
  {RowId::AutoOffDoor, RowKind::Toggle, "Keep on if door opens", PageId::Root},
};

static const RowSpec kNetworkRows[] = {
  {RowId::WifiStatus, RowKind::Info, "Wi-Fi", PageId::Root},
  {RowId::AddressMode, RowKind::Info, "Address", PageId::Root},
  {RowId::MdnsEnabled, RowKind::Toggle, "Name on network", PageId::Root},
  {RowId::ShowIpAtBoot, RowKind::Toggle, "Show address at start", PageId::Root},
  {RowId::TimeLocaleNav, RowKind::Nav, "Time & locale", PageId::TimeLocale},
};

static const RowSpec kTimeLocaleRows[] = {
  {RowId::TimeZone, RowKind::Stepper, "Time zone", PageId::Root},
  {RowId::Clock24h, RowKind::Toggle, "24-hour clock", PageId::Root},
  {RowId::DateFormat, RowKind::Stepper, "Date format", PageId::Root},
};

static const RowSpec kDisplayRows[] = {
  {RowId::Brightness, RowKind::Stepper, "Brightness", PageId::Root},
  {RowId::StandbyBrightness, RowKind::Stepper, "Standby", PageId::Root},
  {RowId::ClockScheduleNav, RowKind::Nav, "Clock & schedule", PageId::ClockSchedule},
  {RowId::GaugesNav, RowKind::Nav, "Gauges", PageId::Gauges},
  {RowId::AfterPrint, RowKind::Stepper, "After a print", PageId::Root},
  {RowId::FinishTimeout, RowKind::Stepper, "Finish screen", PageId::Root},
  {RowId::DoorAck, RowKind::Toggle, "Wait for door", PageId::Root},
  {RowId::KeepPrintScreen, RowKind::Toggle, "Stay on printer", PageId::Root},
  {RowId::FinishTime, RowKind::Toggle, "Show finish time", PageId::Root},
  {RowId::TimeReadout, RowKind::Stepper, "Time shown", PageId::Root},
  {RowId::AnimatedBar, RowKind::Toggle, "Animated progress", PageId::Root},
  {RowId::SmallLabels, RowKind::Toggle, "Small labels", PageId::Root},
  {RowId::FanReadout, RowKind::Stepper, "Fan readout", PageId::Root},
  {RowId::StatusReadout, RowKind::Toggle, "Status readout", PageId::Root},
  {RowId::Theme, RowKind::Stepper, "Colour theme", PageId::Root},
  {RowId::AmbientHome, RowKind::Toggle, "Calm idle screen", PageId::Root},
  {RowId::Rotation, RowKind::Action, "Rotation", PageId::Root},
};

static const RowSpec kClockScheduleRows[] = {
  {RowId::NightMode, RowKind::Toggle, "Night mode", PageId::Root},
  {RowId::NightBrightness, RowKind::Stepper, "Night brightness", PageId::Root},
  {RowId::NightStart, RowKind::Stepper, "Night starts", PageId::Root},
  {RowId::NightEnd, RowKind::Stepper, "Night ends", PageId::Root},
  {RowId::PongClock, RowKind::Toggle, "Animated clock", PageId::Root},
  {RowId::ClockTimeSize, RowKind::Stepper, "Time size", PageId::Root},
  {RowId::ClockDateSize, RowKind::Stepper, "Date size", PageId::Root},
  {RowId::ClockShowDate, RowKind::Toggle, "Show date", PageId::Root},
  {RowId::ClockInfo, RowKind::Toggle, "Name and address", PageId::Root},
  {RowId::ClockTimeColor, RowKind::Stepper, "Time colour", PageId::Root},
  {RowId::ClockDateColor, RowKind::Stepper, "Date colour", PageId::Root},
};

static const RowSpec kGaugesRows[] = {
  {RowId::GaugeSelect, RowKind::Stepper, "Gauge", PageId::Root},
  {RowId::GaugeArc, RowKind::Stepper, "Arc colour", PageId::Root},
  {RowId::GaugeLabel, RowKind::Stepper, "Label colour", PageId::Root},
  {RowId::GaugeValue, RowKind::Stepper, "Value colour", PageId::Root},
  {RowId::NozzleScale, RowKind::Stepper, "Nozzle scale", PageId::Root},
  {RowId::BedScale, RowKind::Stepper, "Bed scale", PageId::Root},
  {RowId::ChamberScale, RowKind::Stepper, "Chamber scale", PageId::Root},
  {RowId::PowerScale, RowKind::Stepper, "Power scale", PageId::Root},
  {RowId::Smoothing, RowKind::Stepper, "Smoothing", PageId::Root},
  {RowId::WarnAt, RowKind::Stepper, "Warn at", PageId::Root},
  {RowId::WarnColor, RowKind::Stepper, "Warning colour", PageId::Root},
  {RowId::GaugeDefaults, RowKind::Action, "Gauge defaults", PageId::Root},
  {RowId::Ams8Slot, RowKind::Toggle, "8-slot AMS (wide)", PageId::Root},
  {RowId::Ams9Slot, RowKind::Toggle, "9-slot AMS (tall)", PageId::Root},
  {RowId::SplitView, RowKind::Toggle, "Split view", PageId::Root},
  {RowId::SplitForce, RowKind::Toggle, "Always split", PageId::Root},
  {RowId::AmsTrayTypes, RowKind::Toggle, "AMS tray types", PageId::Root},
};

static const RowSpec kSoundAlertsRows[] = {
  {RowId::EventSounds, RowKind::Toggle, "Event sounds", PageId::Root},
  {RowId::TouchSounds, RowKind::Toggle, "Touch sounds", PageId::Root},
  {RowId::Volume, RowKind::Stepper, "Volume", PageId::Root},
  {RowId::AlertsNav, RowKind::Nav, "Printer alerts", PageId::Alerts},
  {RowId::StatusLightNav, RowKind::Nav, "Status light", PageId::StatusLight},
  {RowId::QuietStart, RowKind::Stepper, "Quiet from", PageId::Root},
  {RowId::QuietEnd, RowKind::Stepper, "Quiet until", PageId::Root},
  {RowId::SpeakerTest, RowKind::Action, "Speaker test", PageId::Root},
  {RowId::MicTest, RowKind::Action, "Microphone", PageId::Root},
  {RowId::Recorder, RowKind::Action2, "Recorder", PageId::Root},
  {RowId::VideoTestNav, RowKind::Nav, "Video test", PageId::VideoTest},
};

static const RowSpec kAlertsRows[] = {
  {RowId::HmsEnabled, RowKind::Toggle, "Printer errors", PageId::Root},
  {RowId::HmsSeverity, RowKind::Stepper, "Which errors", PageId::Root},
  {RowId::HmsPresent, RowKind::Stepper, "How shown", PageId::Root},
  {RowId::HmsLookup, RowKind::Toggle, "Look up details", PageId::Root},
  {RowId::AlertSound, RowKind::Toggle, "Error sound", PageId::Root},
  {RowId::AlertLight, RowKind::Toggle, "Error light", PageId::Root},
  {RowId::AlertWake, RowKind::Toggle, "Wake screen", PageId::Root},
  {RowId::AlertGlow, RowKind::Toggle, "Error glow", PageId::Root},
  {RowId::GlowMode, RowKind::Stepper, "Edge glow", PageId::Root},
  {RowId::GlowStyle, RowKind::Stepper, "Glow style", PageId::Root},
  {RowId::GlowDuration, RowKind::Stepper, "Glow length", PageId::Root},
  {RowId::GlowColor, RowKind::Stepper, "Glow colour", PageId::Root},
};

static const RowSpec kStatusLightRows[] = {
  {RowId::LedEnabled, RowKind::Toggle, "Status light", PageId::Root},
  {RowId::LedBrightness, RowKind::Stepper, "Brightness", PageId::Root},
  {RowId::LedWhilePrinting, RowKind::Toggle, "On while printing", PageId::Root},
  {RowId::LedPauseBreath, RowKind::Toggle, "Breathe when paused", PageId::Root},
  {RowId::LedFinishEffect, RowKind::Stepper, "Finish effect", PageId::Root},
  {RowId::LedFinishTime, RowKind::Stepper, "Finish effect for", PageId::Root},
  {RowId::LedFinishPeak, RowKind::Stepper, "Finish brightness", PageId::Root},
  {RowId::LedErrorStrobe, RowKind::Toggle, "Error strobe", PageId::Root},
  {RowId::LedErrorTime, RowKind::Stepper, "Strobe for", PageId::Root},
};

static const RowSpec kVideoRows[] = {
  {RowId::VideoPause, RowKind::Action, "Video", PageId::Root},
};

static const RowSpec kLocalPortalRows[] = {
  {RowId::PortalAddress, RowKind::Info, "Address", PageId::Root},
  {RowId::PortalCode, RowKind::Code, "Access code", PageId::Root},
  {RowId::PortalSignIn, RowKind::Info, "Require access code", PageId::Root},
  {RowId::PortalCodeKey, RowKind::Info, "Local AI code access", PageId::Root},
};

static const RowSpec kUpdatesAboutRows[] = {
  {RowId::Version, RowKind::Info, "Version", PageId::Root},
  {RowId::UpdateAction, RowKind::Action, "Software update", PageId::Root},
  {RowId::UpdateChannel, RowKind::Toggle, "Test builds", PageId::Root},
  {RowId::DateTimeNow, RowKind::Info, "Date & time", PageId::Root},
  {RowId::HealthNav, RowKind::Nav, "Device health", PageId::DeviceHealth},
};

static const RowSpec kDeviceHealthRows[] = {
  {RowId::HealthTouch, RowKind::Info, "Touch", PageId::Root},
  {RowId::HealthRecovery, RowKind::Info, "Recovery", PageId::Root},
  {RowId::WifiSignal, RowKind::Info, "Wi-Fi signal", PageId::Root},
  {RowId::HealthPrinter, RowKind::Info, "Printer link", PageId::Root},
  {RowId::HealthUptime, RowKind::Info, "Uptime", PageId::Root},
};

// Tile order on the More root.
static const PageId kRootTiles[] = {
  PageId::PrinterPower, PageId::Network, PageId::Display,
  PageId::SoundAlerts, PageId::LocalPortal, PageId::UpdatesAbout,
};
static const uint8_t kRootTileCount = static_cast<uint8_t>(sizeof(kRootTiles) / sizeof(kRootTiles[0]));

static const PageSpec kPages[] = {
  {PageId::Root, PageId::Root, 0, PageLayout::Tiles, "More", "", "more", nullptr, 0},
  {PageId::PrinterPower, PageId::Root, 1, PageLayout::List, "Printer & Power", "More", "settings-printer-power", WS_ROWS(kPrinterPowerRows)},
  {PageId::AutoOff, PageId::PrinterPower, 2, PageLayout::List, "Auto power-off", "Power", "hardware-auto-off", WS_ROWS(kAutoOffRows)},
  {PageId::Network, PageId::Root, 1, PageLayout::List, "Network", "More", "settings-network", WS_ROWS(kNetworkRows)},
  {PageId::TimeLocale, PageId::Network, 2, PageLayout::List, "Time & locale", "Network", "system-date-time", WS_ROWS(kTimeLocaleRows)},
  {PageId::Display, PageId::Root, 1, PageLayout::List, "Display", "More", "settings-display", WS_ROWS(kDisplayRows)},
  {PageId::ClockSchedule, PageId::Display, 2, PageLayout::List, "Clock & schedule", "Display", "display-clock", WS_ROWS(kClockScheduleRows)},
  {PageId::Gauges, PageId::Display, 2, PageLayout::List, "Gauges", "Display", "display-gauges", WS_ROWS(kGaugesRows)},
  {PageId::SoundAlerts, PageId::Root, 1, PageLayout::List, "Sound & Alerts", "More", "settings-sounds", WS_ROWS(kSoundAlertsRows)},
  {PageId::Alerts, PageId::SoundAlerts, 2, PageLayout::List, "Printer alerts", "Sound", "display-alerts", WS_ROWS(kAlertsRows)},
  {PageId::StatusLight, PageId::SoundAlerts, 2, PageLayout::List, "Status light", "Sound", "hardware-led", WS_ROWS(kStatusLightRows)},
  {PageId::VideoTest, PageId::SoundAlerts, 2, PageLayout::Video, "Video test", "Sound", "media-video", WS_ROWS(kVideoRows)},
  {PageId::LocalPortal, PageId::Root, 1, PageLayout::List, "Local Portal", "More", "system-portal", WS_ROWS(kLocalPortalRows)},
  {PageId::UpdatesAbout, PageId::Root, 1, PageLayout::List, "Updates & About", "More", "system-update", WS_ROWS(kUpdatesAboutRows)},
  {PageId::DeviceHealth, PageId::UpdatesAbout, 2, PageLayout::List, "Device health", "About", "system-diagnostics", WS_ROWS(kDeviceHealthRows)},
};

#undef WS_ROWS

inline const PageSpec& page(PageId id) {
  const uint8_t i = static_cast<uint8_t>(id);
  return kPages[i < kPageCount ? i : 0];
}

inline bool pageFromViewId(const char* viewId, PageId& out) {
  if (!viewId) return false;
  for (uint8_t i = 0; i < kPageCount; ++i) {
    const char* a = kPages[i].viewId;
    const char* b = viewId;
    while (*a && *a == *b) { ++a; ++b; }
    if (*a == 0 && *b == 0) { out = kPages[i].id; return true; }
  }
  return false;
}

// Pages whose content must never be stored by the framebuffer capture tools.
inline bool pageSensitive(PageId id) { return id == PageId::LocalPortal; }

// ---------------------------------------------------------------------------
// Shared chrome
// ---------------------------------------------------------------------------

inline Rect tabRect(Screen s, uint8_t i) {
  const int cell = s.w / kTabCount;
  const int x = i * cell;
  return makeRect(x, s.h - kTabH, i == kTabCount - 1 ? s.w - x : cell, kTabH);
}

inline Rect tabBand(Screen s) { return makeRect(0, s.h - kTabH, s.w, kTabH); }
inline Rect headerBand(Screen s) { return makeRect(0, 0, s.w, kHeaderH); }
inline Rect contentBand(Screen s) { return makeRect(0, kHeaderH, s.w, s.h - kTabH - kHeaderH); }

// Back is the same rectangle on every page.
inline Rect backRect(Screen s) { return makeRect(0, 0, s.landscape() ? 112 : 96, kHeaderH); }
inline Rect scrollUpRect(Screen s) { return makeRect(s.w - 112, 0, 52, kHeaderH); }
inline Rect scrollDownRect(Screen s) { return makeRect(s.w - 56, 0, 52, kHeaderH); }

// Title area: between Back and the right-hand header controls. The right side
// holds the scroll buttons when the page scrolls, otherwise a status chip.
inline Rect titleRect(Screen s, bool rootPage, bool scrollButtons) {
  const int left = rootPage ? 12 : backRect(s).right() + 4;
  const int right = scrollButtons ? scrollUpRect(s).x - 4 : s.w - 8;
  return makeRect(left, 0, right - left, kHeaderH);
}
inline Rect chipRect(Screen s) { return makeRect(s.w - 116, 9, 108, 26); }

// ---------------------------------------------------------------------------
// Rows
// ---------------------------------------------------------------------------

inline uint8_t visibleRows(Screen s) {
  const int n = (s.h - kTabH - kRowTop) / kRowH;
  return static_cast<uint8_t>(n > 0 ? n : 0);
}

inline uint8_t rowCount(PageId id) { return page(id).rowCount; }

// Rows of a Video page sit in the bottom slots under the video area.
inline uint8_t firstSlot(Screen s, PageId id) {
  const PageSpec& p = page(id);
  if (p.layout != PageLayout::Video) return 0;
  const uint8_t vis = visibleRows(s);
  return static_cast<uint8_t>(vis > p.rowCount ? vis - p.rowCount : 0);
}

inline uint8_t maxScroll(Screen s, PageId id) {
  const PageSpec& p = page(id);
  if (p.layout != PageLayout::List) return 0;
  const uint8_t vis = visibleRows(s);
  return static_cast<uint8_t>(p.rowCount > vis ? p.rowCount - vis : 0);
}

inline bool pageScrolls(Screen s, PageId id) { return maxScroll(s, id) > 0; }

// Scrolling moves a screen at a time and keeps one row of context.
inline uint8_t scrollStep(Screen s) {
  const uint8_t vis = visibleRows(s);
  return static_cast<uint8_t>(vis > 1 ? vis - 1 : 1);
}

inline uint8_t clampScroll(Screen s, PageId id, int scroll) {
  const int m = maxScroll(s, id);
  if (scroll < 0) return 0;
  return static_cast<uint8_t>(scroll > m ? m : scroll);
}

inline Rect slotRect(Screen s, uint8_t slot) {
  return makeRect(kMarginX, kRowTop + slot * kRowH, s.w - 2 * kMarginX, kRowH);
}

// Rectangle of row `row` when the list is scrolled by `scroll`; empty if the
// row is not on screen.
inline Rect rowRect(Screen s, PageId id, uint8_t scroll, uint8_t row) {
  const PageSpec& p = page(id);
  if (p.layout == PageLayout::Tiles || row >= p.rowCount || row < scroll) return makeRect(0, 0, 0, 0);
  const int slot = firstSlot(s, id) + (row - scroll);
  if (slot >= visibleRows(s)) return makeRect(0, 0, 0, 0);
  return slotRect(s, static_cast<uint8_t>(slot));
}

// Drawn surface of a row: inset 1 px top and bottom so neighbours separate.
inline Rect rowSurface(const Rect& row) { return makeRect(row.x, row.y + 1, row.w, row.h - 2); }

inline int stepperValueWidth(Screen s) { return s.landscape() ? 140 : 76; }
inline int actionButtonWidth(Screen s) { return s.landscape() ? 112 : 84; }
inline int action2ButtonWidth(Screen s) { return s.landscape() ? 96 : 70; }

// Drawn button for a row part (the thing the user sees).
inline Rect partDrawRect(Screen s, const Rect& row, RowKind kind, Part part) {
  switch (kind) {
    case RowKind::Stepper: {
      const Rect plus = makeRect(row.right() - 6 - 52, row.y + 5, 52, row.h - 10);
      if (part == Part::Plus) return plus;
      if (part == Part::Minus) return makeRect(plus.x - stepperValueWidth(s) - 52, row.y + 5, 52, row.h - 10);
      return makeRect(0, 0, 0, 0);
    }
    case RowKind::Toggle:
      return part == Part::Whole ? makeRect(row.right() - 12 - 60, row.y + (row.h - 34) / 2, 60, 34) : makeRect(0, 0, 0, 0);
    case RowKind::Action:
      return part == Part::Whole ? makeRect(row.right() - 8 - actionButtonWidth(s), row.y + 6, actionButtonWidth(s), row.h - 12)
                                 : makeRect(0, 0, 0, 0);
    case RowKind::Action2: {
      const int bw = action2ButtonWidth(s);
      const Rect b = makeRect(row.right() - 8 - bw, row.y + 6, bw, row.h - 12);
      if (part == Part::ActionB) return b;
      if (part == Part::ActionA) return makeRect(b.x - 8 - bw, row.y + 6, bw, row.h - 12);
      return makeRect(0, 0, 0, 0);
    }
    default:
      return makeRect(0, 0, 0, 0);
  }
}

// Touch rectangle for a row part. Buttons span the full row height and are
// widened sideways: stepper buttons by 6 px, Action2 buttons by 4 px (half
// the 8 px gap between them). Whole-row controls use the row.
inline Rect partTouchRect(Screen s, const Rect& row, RowKind kind, Part part) {
  switch (kind) {
    case RowKind::Stepper:
    case RowKind::Action2: {
      const Rect d = partDrawRect(s, row, kind, part);
      if (d.empty()) return d;
      const int widen = kind == RowKind::Stepper ? 6 : 4;
      return makeRect(d.x - widen, row.y, d.w + 2 * widen, row.h);
    }
    default:
      return part == Part::Whole ? row : makeRect(0, 0, 0, 0);
  }
}

// Value text slot of a stepper: centred between "-" and "+".
inline Rect stepperValueRect(Screen s, const Rect& row) {
  const Rect minus = partDrawRect(s, row, RowKind::Stepper, Part::Minus);
  const Rect plus = partDrawRect(s, row, RowKind::Stepper, Part::Plus);
  return makeRect(minus.right() + 2, row.y, plus.x - minus.right() - 4, row.h);
}

// Label slot: left of the first control.
inline Rect labelRect(Screen s, const Rect& row, RowKind kind) {
  int right = row.right() - 12;
  switch (kind) {
    case RowKind::Stepper: right = partDrawRect(s, row, kind, Part::Minus).x - 8; break;
    case RowKind::Toggle: right = partDrawRect(s, row, kind, Part::Whole).x - 8; break;
    case RowKind::Action: right = partDrawRect(s, row, kind, Part::Whole).x - 8; break;
    case RowKind::Action2: right = partDrawRect(s, row, kind, Part::ActionA).x - 8; break;
    default: break;
  }
  return makeRect(row.x + 12, row.y, right - row.x - 12, row.h);
}

// Whether a row draws its value text at all. An empty value draws nothing:
// the firmware's text fitter turns "" into an em dash, which the WS350 font
// has no glyph for, so 12.2.0 showed a stray "|" left of every toggle switch.
inline bool drawsValueText(const char* value) { return value != nullptr && value[0] != '\0'; }

// Value slot for Info / Nav / Code / Toggle rows (right-aligned text).
inline Rect valueRect(Screen s, const Rect& row, RowKind kind) {
  const int labelShare = s.landscape() ? 200 : 116;
  int right = row.right() - 12;
  if (kind == RowKind::Nav) right = row.right() - 28;           // room for the chevron
  if (kind == RowKind::Toggle) right = partDrawRect(s, row, kind, Part::Whole).x - 8;
  if (kind == RowKind::Action) right = partDrawRect(s, row, kind, Part::Whole).x - 8;
  if (kind == RowKind::Action2) right = partDrawRect(s, row, kind, Part::ActionA).x - 8;
  const int left = row.x + 12 + labelShare;
  return makeRect(left, row.y, right - left, row.h);
}

// ---------------------------------------------------------------------------
// More root tiles
// ---------------------------------------------------------------------------

inline Rect tileRect(Screen s, uint8_t i) {
  if (i >= kRootTileCount) return makeRect(0, 0, 0, 0);
  if (s.landscape()) {
    const int w = (s.w - 2 * kMarginX - 8) / 2;
    return makeRect(kMarginX + (i % 2) * (w + 8), 48 + (i / 2) * (68 + 6), w, 68);
  }
  return makeRect(kMarginX, 48 + i * (56 + 6), s.w - 2 * kMarginX, 56);
}

// ---------------------------------------------------------------------------
// Confirmation dialog (modal inside the content area; the tab bar stays live)
// ---------------------------------------------------------------------------

inline Rect dialogCard(Screen s) {
  return makeRect(kMarginX, kHeaderH + 6, s.w - 2 * kMarginX, s.h - kTabH - kHeaderH - 10);
}

inline Rect dialogCancelRect(Screen s) {
  const Rect c = dialogCard(s);
  const int bw = (c.w - 36) / 2;
  return makeRect(c.x + 12, c.bottom() - 8 - 48, bw, 48);
}

inline Rect dialogConfirmRect(Screen s) {
  const Rect cancel = dialogCancelRect(s);
  return makeRect(cancel.right() + 12, cancel.y, cancel.w, cancel.h);
}

// Video area of a Video page: between the header and its control row.
inline Rect videoRect(Screen s, PageId id) {
  const Rect first = slotRect(s, firstSlot(s, id));
  return makeRect(0, kHeaderH, s.w, first.y - kHeaderH);
}

// ---------------------------------------------------------------------------
// Hit testing
// ---------------------------------------------------------------------------

enum class HitKind : uint8_t { None = 0, Tab, Back, ScrollUp, ScrollDown, Tile, Row, DialogCancel, DialogConfirm };

struct Hit {
  HitKind kind;
  uint8_t index;  // tab, tile or row index
  Part part;
};

inline Hit makeHit(HitKind kind, uint8_t index, Part part) {
  Hit h;
  h.kind = kind;
  h.index = index;
  h.part = part;
  return h;
}

inline Hit hitTest(Screen s, PageId id, uint8_t scroll, bool dialogOpen, int x, int y) {
  // The tab bar is drawn on every page, so it is always live.
  for (uint8_t i = 0; i < kTabCount; ++i)
    if (tabRect(s, i).contains(x, y)) return makeHit(HitKind::Tab, i, Part::Whole);
  const PageSpec& p = page(id);
  if (p.level > 0 && backRect(s).contains(x, y)) return makeHit(HitKind::Back, 0, Part::Whole);
  if (dialogOpen) {
    if (dialogCancelRect(s).contains(x, y)) return makeHit(HitKind::DialogCancel, 0, Part::Whole);
    if (dialogConfirmRect(s).contains(x, y)) return makeHit(HitKind::DialogConfirm, 0, Part::Whole);
    return makeHit(HitKind::None, 0, Part::Whole);
  }
  if (pageScrolls(s, id)) {
    if (scrollUpRect(s).contains(x, y)) return makeHit(HitKind::ScrollUp, 0, Part::Whole);
    if (scrollDownRect(s).contains(x, y)) return makeHit(HitKind::ScrollDown, 0, Part::Whole);
  }
  if (p.layout == PageLayout::Tiles) {
    for (uint8_t i = 0; i < kRootTileCount; ++i)
      if (tileRect(s, i).contains(x, y)) return makeHit(HitKind::Tile, i, Part::Whole);
    return makeHit(HitKind::None, 0, Part::Whole);
  }
  for (uint8_t r = 0; r < p.rowCount; ++r) {
    const Rect row = rowRect(s, id, scroll, r);
    if (!row.contains(x, y)) continue;
    const RowKind kind = p.rows[r].kind;
    if (kind == RowKind::Stepper) {
      if (partTouchRect(s, row, kind, Part::Minus).contains(x, y)) return makeHit(HitKind::Row, r, Part::Minus);
      if (partTouchRect(s, row, kind, Part::Plus).contains(x, y)) return makeHit(HitKind::Row, r, Part::Plus);
      return makeHit(HitKind::None, r, Part::Whole);
    }
    if (kind == RowKind::Action2) {
      if (partTouchRect(s, row, kind, Part::ActionA).contains(x, y)) return makeHit(HitKind::Row, r, Part::ActionA);
      if (partTouchRect(s, row, kind, Part::ActionB).contains(x, y)) return makeHit(HitKind::Row, r, Part::ActionB);
      return makeHit(HitKind::None, r, Part::Whole);
    }
    return makeHit(HitKind::Row, r, Part::Whole);
  }
  return makeHit(HitKind::None, 0, Part::Whole);
}

}  // namespace more
}  // namespace ui
}  // namespace workshop
