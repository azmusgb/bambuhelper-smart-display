// Idle Home drawn with the appliance-ui display kit (display-kit rollout step 4): Frame for the header, the kit's
// NeedsRow for the top two Needs-you items, a printer card and a timer card with the kit's Button, all in Archivo. This
// file knows nothing about the printer, Pi Hub or LovyanGFX: the firmware fills a HomeIdleModel from its live state and
// draws it through a UiCanvas, and tests/workshop_os12_home_idle_kit_smoke.cpp draws the same model on a host. The
// rectangles come in the model, from the layout that also hit-tests the screen (tabs_layout.hpp homeIdleRect), so what
// is drawn and what is tappable cannot differ. Installed as include/workshop_home_idle_kit.hpp.
//
// What the screen shows is what idle Home showed before (clock and weather, the top two needs, the printer, the
// timer); only the look, the words the kit owns and the parts change. Three things the kit's parts decide:
//  - A need is as wide as the row and one line each for its title and its reason. A reason that does not fit is cut at a
//    word and ends in an ellipsis (wkit::fitWords); the row opens the Local AI tab, which holds the whole text.
//  - The "+N more" of the second row is the area on its meta line, the kit's place for a note that is not a time.
//  - A need's tone is the kit's three: bad, attention, warn. A need that is only information is the muted one.
#pragma once

#include "kit_screen.hpp"

namespace wkit {

struct HomeIdleModel {
  // Header (Frame, level one: the clock, and under it the weather or a toast).
  const char* title = "Home";
  const char* subtitle = nullptr;
  uint16_t subtitleColor = UI_COLOR_MUTED;
  // The top two Needs-you items (NeedsRow); the strings are the caller's.
  ::ui::NeedItem need[2];
  // The printer card: its lamp colour, the headline (Ready, Finished 9:45 AM, Offline), the muted line under it and,
  // for a printer that has gone quiet, how long ago it last reported (the kit's AgeLine, so it reads Unknown when it
  // cannot be told). printerAgeLead is the words in front of the age ("Last report").
  ::ui::ChipKind printerKind = ::ui::ChipKind::Unknown;
  const char* printerHeadline = "";
  const char* printerLine = "";
  const char* printerAgeLead = nullptr;
  const ::ui::Reading* printerAge = nullptr;
  // The timer card: its state in words, that state's colour, and the one button (Start, Cancel, Clear).
  const char* timerValue = "";
  uint16_t timerValueColor = UI_COLOR_MUTED;
  const char* timerButton = "Start";
  bool timerPrimary = true;
  // Where each part goes: need, need, printer, timer (tabs_layout.hpp homeIdleRect).
  ::ui::Rect rect[4];
  ::ui::Clock now;
};

constexpr int kHomeIdleTextMax = 128;  // bytes of one fitted line on the stack (the firmware's loop task has 8 KB)

// Each section is its own noinline function, so its line buffers (about 0.5 KB, and the kit's NeedsRow another 0.5 KB)
// are off the stack again before the next one is drawn.
#if defined(__GNUC__)
#define WKIT_NOINLINE __attribute__((noinline))
#else
#define WKIT_NOINLINE
#endif

// One need: a title and a reason fitted to one line each, cut at a word, then the kit's NeedsRow.
WKIT_NOINLINE inline void drawHomeIdleNeed(UiCanvas& c, const ::ui::Rect& r, const ::ui::NeedItem& need, const ::ui::Clock& now) {
  ::ui::NeedItem item = need;
  char title[kHomeIdleTextMax], detail[kHomeIdleTextMax];
  const int lineW = r.w - 28;  // the width NeedsRow gives a line: 16 px in, 12 px out
  fitWords(c, item.title, UiFont::Fs4, lineW, title, sizeof title);
  fitWords(c, item.detail, UiFont::Fs3, lineW, detail, sizeof detail);
  item.title = title;
  item.detail = detail;
  ::ui::NeedsRow::draw(c, r, item, now, nullptr);
}

// The printer card: lamp bar, headline in its colour, one muted line, and a chevron because a tap opens Printer.
WKIT_NOINLINE inline void drawHomeIdlePrinter(UiCanvas& c, const HomeIdleModel& m) {
  const ::ui::Rect& r = m.rect[2];
  const uint16_t tone = ::ui::Chip::color(m.printerKind);
  card(c, r, tone);
  const int x = r.x + 16, right = r.right() - 30;
  const int top = r.y + (r.h - (::ui::lineHeight(UiFont::Fs5) + ::ui::lineHeight(UiFont::Fs3))) / 2;
  char text[kHomeIdleTextMax];
  fitWords(c, m.printerHeadline, UiFont::Fs5, right - x, text, sizeof text);
  ::ui::drawText(c, x, top + ::ui::ascent(UiFont::Fs5), text, UiFont::Fs5, tone, UI_COLOR_SURFACE);
  const int b2 = top + ::ui::lineHeight(UiFont::Fs5) + ::ui::ascent(UiFont::Fs3);
  if (m.printerAge && m.printerAgeLead) {
    // "X2D \xC2\xB7 Last report 4 min ago": the age is the kit's, so it is in the unknown colour when it is not a live one.
    char ageText[32];
    ::ui::AgeLine::text(ageText, sizeof ageText, *m.printerAge, m.now);
    const int ageW = c.textWidth(ageText, UiFont::Fs3);
    snprintf(text, sizeof text, "%s%s%s ", m.printerLine, *m.printerLine ? " \xC2\xB7 " : "", m.printerAgeLead);
    char shown[kHomeIdleTextMax];
    fitWords(c, text, UiFont::Fs3, right - x - ageW, shown, sizeof shown);
    ::ui::drawText(c, x, b2, shown, UiFont::Fs3, UI_COLOR_MUTED, UI_COLOR_SURFACE);
    ::ui::AgeLine::draw(c, x + c.textWidth(shown, UiFont::Fs3), b2, *m.printerAge, m.now, UI_COLOR_SURFACE);
  } else {
    fitWords(c, m.printerLine, UiFont::Fs3, right - x, text, sizeof text);
    ::ui::drawText(c, x, b2, text, UiFont::Fs3, UI_COLOR_MUTED, UI_COLOR_SURFACE);
  }
  chevronRight(c, r.right() - 20, r.y + r.h / 2, UI_COLOR_MUTED);
}

// The timer card: its name and state on the left, the kit's Button on the right (48 px high, 8 px from the card's edge).
WKIT_NOINLINE inline void drawHomeIdleTimer(UiCanvas& c, const HomeIdleModel& m) {
  const ::ui::Rect& r = m.rect[3];
  card(c, r, 0);
  const int x = r.x + 12;
  const int top = r.y + (r.h - (::ui::lineHeight(UiFont::Fs4) + ::ui::lineHeight(UiFont::Fs3))) / 2;
  ::ui::drawText(c, x, top + ::ui::ascent(UiFont::Fs4), "Timer", UiFont::Fs4, UI_COLOR_TEXT, UI_COLOR_SURFACE);
  const int b2 = top + ::ui::lineHeight(UiFont::Fs4) + ::ui::ascent(UiFont::Fs3);
  ::ui::drawText(c, x, b2, m.timerValue, UiFont::Fs3, m.timerValueColor, UI_COLOR_SURFACE);
  const ::ui::Rect b = buttonAtRight(c, r, m.timerButton);
  ::ui::Button::draw(c, b, m.timerButton, m.timerPrimary ? ::ui::ButtonStyle::Primary : ::ui::ButtonStyle::Plain, true);
}

inline void drawHomeIdle(UiCanvas& c, const HomeIdleModel& m) {
  c.fillRect(0, 0, ::ui::kScreenW, ::ui::kScreenH, UI_COLOR_BG);
  ::ui::Frame::draw(c, m.title, ::ui::Level::One, m.subtitle, m.subtitleColor);
  drawHomeIdleNeed(c, m.rect[0], m.need[0], m.now);
  drawHomeIdleNeed(c, m.rect[1], m.need[1], m.now);
  drawHomeIdlePrinter(c, m);
  drawHomeIdleTimer(c, m);
}

}  // namespace wkit
