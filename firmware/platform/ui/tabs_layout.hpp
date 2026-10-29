#pragma once

// Workshop OS 12.4: Premium UI Overhaul
// Implements Bottom Navigation, Bento-style Home, and Semantic Visuals.

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

// Semantic Colors for Visual Language
enum class SemanticColor : uint8_t {
  Neutral = 0,
  Success = 1, // Green: Finished, All Clear
  Warning = 2, // Amber: Needs Attention, Low Filament
  Danger = 3,  // Red: Stop, Failure, Critical Alert
  Primary = 4  // Brand Color: Active state, Primary Action
};

// Tab bar index - Now positioned at the BOTTOM
enum class Tab : uint8_t { Home = 0, Printer = 1, Workshop = 2 };

enum class View : uint8_t {
  Home = 0,
  PrinterStatus,
  PrinterAms,
  PrinterControl,
  WorkshopSetup,
  WorkshopInventory,
  HomeIdle,
  Count
};

static const uint8_t kViewCount = static_cast<uint8_t>(View::Count);

enum class ItemKind : uint8_t {
  BentoCard,    // Multi-slot visual widget (Home)
  Temps,        // Compact temp readouts
  Row,          // Standard More row
  Primary,      // High-emphasis action
  Hold,        // Safety-guarded action (Stop)
};

enum class ItemId : uint8_t {
  None = 0,
  // Home (Bento)
  HomeMainCard, HomeTempWidget, HomeAiAlerts, HomeTimerWidget,
  // Printer
  PrinterCard, PrinterTemps, PrinterDetail,
  AmsTray,
  ControlPrimary, ControlLight, ControlPower, ControlStop,
  // Workshop (Organized)
  WsAiStatus, WsAiAsk, WsAiGallery, WsAiPair,
  WsToolTimer, WsToolLength, WsToolNote,
  WsInvManage, WsInvReadiness, WsInvLoaded, WsInvReview,
  Count
};

struct ItemSpec {
  ItemId id;
  ItemKind kind;
  RowKind rowKind;
  bool tappable;
  const char* label;
  SemanticColor color; // Semantic coloring for the item
};

struct ViewSpec {
  View id;
  Tab tab;
  bool segments;
  bool list;
  bool repeat;
  const char* title;
  const ItemSpec* items;
  uint8_t itemCount;
  bool headRepeat;
};

#define WT_ITEMS(name) name, static_cast<uint8_t>(sizeof(name) / sizeof(name[0]))

// Home: Now uses a Bento-style layout
static const ItemSpec kHomeItems[] = {
  {ItemId::HomeMainCard, ItemKind::BentoCard, RowKind::Info, true, "Print", SemanticColor::Neutral},
  {ItemId::HomeTempWidget, ItemKind::Temps, RowKind::Info, false, "Temps", SemanticColor::Neutral},
  {ItemId::HomeAiAlerts, ItemKind::Row, RowKind::Nav, true, "Needs you", SemanticColor::Warning},
  {ItemId::HomeTimerWidget, ItemKind::Row, RowKind::Action, true, "Timer", SemanticColor::Primary},
};

static const ItemSpec kPrinterStatusItems[] = {
  {ItemId::PrinterCard, ItemKind::BentoCard, RowKind::Info, false, "Status", SemanticColor::Neutral},
  {ItemId::PrinterTemps, ItemKind::Temps, RowKind::Info, false, "Temps", SemanticColor::Neutral},
  {ItemId::PrinterDetail, ItemKind::Row, RowKind::Info, false, "Layer", SemanticColor::Neutral},
};

static const ItemSpec kPrinterAmsItems[] = {
  {ItemId::AmsTray, ItemKind::Row, RowKind::Info, false, "Slot", SemanticColor::Neutral},
};

static const ItemSpec kPrinterControlItems[] = {
  {ItemId::ControlPrimary, ItemKind::Primary, RowKind::Action, false, "Pause", SemanticColor::Primary},
  {ItemId::ControlLight, ItemKind::Row, RowKind::Toggle, false, "Light", SemanticColor::Neutral},
  {ItemId::ControlPower, ItemKind::Row, RowKind::Action, false, "Power", SemanticColor::Neutral},
  {ItemId::ControlStop, ItemKind::Hold, RowKind::Action, false, "Stop", SemanticColor::Danger},
};

static const ItemSpec kWorkshopItems[] = {
  {ItemId::WsAiStatus, ItemKind::BentoCard, RowKind::Info, true, "AI Status", SemanticColor::Primary},
  {ItemId::WsAiAsk, ItemKind::Row, RowKind::Nav, true, "Ask AI", SemanticColor::Neutral},
  {ItemId::WsAiGallery, ItemKind::Row, RowKind::Nav, true, "Latest Image", SemanticColor::Neutral},
  {ItemId::WsAiPair, ItemKind::Row, RowKind::Nav, true, "Connection", SemanticColor::Neutral},
  {ItemId::WsToolTimer, ItemKind::Row, RowKind::Action, true, "Timer", SemanticColor::Neutral},
  {ItemId::WsToolLength, ItemKind::Row, RowKind::Stepper, true, "Length", SemanticColor::Neutral},
  {ItemId::WsToolNote, ItemKind::Row, RowKind::Info, false, "Note", SemanticColor::Neutral},
  {ItemId::WsInvManage, ItemKind::Row, RowKind::Nav, true, "Manage Portal", SemanticColor::Neutral},
  {ItemId::WsInvReadiness, ItemKind::Row, RowKind::Info, false, "Readiness", SemanticColor::Neutral},
  {ItemId::WsInvLoaded, ItemKind::Row, RowKind::Info, false, "Loaded", SemanticColor::Neutral},
  {ItemId::WsInvReview, ItemKind::Row, RowKind::Info, false, "Review", SemanticColor::Warning},
};

static const ViewSpec kViews[] = {
  {View::Home, Tab::Home, false, false, false, "Home", WT_ITEMS(kHomeItems), false},
  {View::PrinterStatus, Tab::Printer, true, false, false, "Printer", WT_ITEMS(kPrinterStatusItems), false},
  {View::PrinterAms, Tab::Printer, true, true, true, "Printer", WT_ITEMS(kPrinterAmsItems), false},
  {View::PrinterControl, Tab::Printer, true, false, false, "Printer", WT_ITEMS(kPrinterControlItems), false},
  {View::WorkshopSetup, Tab::Workshop, false, true, false, "AI Hub", WT_ITEMS(kWorkshopItems), true},
  {View::WorkshopInventory, Tab::Workshop, false, true, false, "AI Hub", WT_ITEMS(kWorkshopItems), true},
  {View::HomeIdle, Tab::Home, false, false, false, "Home", WT_ITEMS(kHomeItems), false},
};

#undef WT_ITEMS

inline const ViewSpec& view(View id) {
  const uint8_t i = static_cast<uint8_t>(id);
  return kViews[i < kViewCount ? i : 0];
}

// ---------------------------------------------------------------------------
// Bottom Navigation Geometry
// ---------------------------------------------------------------------------

inline Rect bottomTabBand(Screen s) { 
  return makeRect(0, s.h - 56, s.w, 56); 
}

inline Rect bottomTabRect(Screen s, uint8_t i) {
  const Rect band = bottomTabBand(s);
  const int cell = band.w / kTabCount;
  return makeRect(band.x + i * cell, band.y, cell, band.h);
}

// ---------------------------------------------------------------------------
// Bento Slotting
// ---------------------------------------------------------------------------

inline uint8_t itemSlots(Screen s, const ItemSpec& it) {
  switch (it.kind) {
    case ItemKind::BentoCard: return s.landscape() ? 2 : 3;
    case ItemKind::Temps: return 1;
    default: return 1;
  }
}

inline Rect itemRect(Screen s, const ViewSpec& v, uint8_t runtimeCount, uint8_t scroll, uint8_t i) {
  const uint8_t n = (v.repeat) ? runtimeCount : v.itemCount;
  if (i >= n) return makeRect(0, 0, 0, 0);
  
  int slot = v.segments ? 1 : 0;
  for (uint8_t j = 0; j < i; ++j) slot += itemSlots(s, v.items[j]);
  
  const int span = itemSlots(s, v.items[i]);
  const Rect top = more::slotRect(s, static_cast<uint8_t>(slot));
  return makeRect(top.x, top.y, top.w, span * more::kRowH);
}

// ---------------------------------------------------------------------------
// Hold-to-Stop Radial Feedback
// ---------------------------------------------------------------------------
struct RadialProgress {
  float percent; // 0.0 to 1.0
  Rect center;
};

inline RadialProgress calculateStopProgress(long now, long start, long duration) {
  RadialProgress p;
  p.percent = (float)(now - start) / (float)duration;
  if (p.percent > 1.0f) p.percent = 1.0f;
  return p;
}

} // namespace tabs
} // namespace ui
} // namespace workshop
