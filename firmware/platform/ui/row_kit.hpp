// The text and the stepper of a More row (display-kit rollout step 5), drawn through the kit's UiCanvas so a host checks
// them (tests/workshop_os12_home_idle_kit_smoke.cpp, rowParts). Header-only C++17, no graphics library; installed as
// include/workshop_kit/row_kit.hpp (apply_workshop_os12_display_kit_home.py).
//
// Three rules the rows keep:
//  - A setting's value is the row's value size (Fs4, 16 px). It is never shrunk to fit: a value too long for its slot is
//    cut at a word and ends in an ellipsis (fitWords).
//  - The kit's Stepper draws its value in the 26 px face between the keys; a row's value is a word or a percentage, so the
//    keys are drawn with no value and the value is drawn here in Fs4, centred between them, never closer than the kit's
//    8 px gap to a key.
//  - A switch says On or Off itself (ui::Switch), so a row value that only repeats that word is not drawn twice.
#pragma once

#include "kit_screen.hpp"

namespace wkit {

constexpr UiFont kRowValueFont = UiFont::Fs4;

// True for a row value that only says what the switch beside it already says.
inline bool repeatsSwitchWord(const char* value) { return value && (!strcmp(value, "On") || !strcmp(value, "Off")); }

// A value in `slot` (the row's value slot, as tall as the row), right-aligned: Fs4, cut at a word to fit.
inline void rowValue(UiCanvas& c, const ::ui::Rect& slot, const char* value, uint16_t fg, uint16_t bg) {
  if (!value || !*value || slot.w <= 0) return;
  char shown[::ui::kTextMax + 1];
  fitWords(c, value, kRowValueFont, slot.w, shown, sizeof shown);
  ::ui::drawTextRight(c, slot.right(), ::ui::baselineIn(slot, kRowValueFont), shown, kRowValueFont, fg, bg);
}

// The Stepper's keys, and its value between them. `cells` runs from the left edge of the "-" key's 48 px cell to the
// right edge of the "+" key's.
inline void rowStepper(UiCanvas& c, const ::ui::Rect& cells, const char* value, uint16_t fg, uint16_t bg) {
  ::ui::Stepper::draw(c, cells, "", nullptr, true, true, bg);  // the keys; an empty value draws no text
  const ::ui::Rect mid{cells.x + ::ui::kTarget + ::ui::kGap, cells.y, cells.w - 2 * (::ui::kTarget + ::ui::kGap), cells.h};
  if (!value || !*value || mid.w <= 0) return;
  char shown[::ui::kTextMax + 1];
  fitWords(c, value, kRowValueFont, mid.w, shown, sizeof shown);
  ::ui::drawTextCentered(c, mid, shown, kRowValueFont, fg, bg);
}

}  // namespace wkit
