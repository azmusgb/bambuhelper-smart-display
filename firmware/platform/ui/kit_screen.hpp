// Helpers shared by the screens that draw through the appliance-ui display kit (display-kit rollout steps 4 and 5).
// Header-only C++17, no graphics library: everything draws through the kit's UiCanvas, so it is compiled and checked on
// a host (tests/workshop_os12_home_idle_kit_smoke.cpp) and the firmware only supplies the LovyanGFX adapter. Installed
// as include/workshop_kit_screen.hpp (apply_workshop_os12_display_kit_home.py).
//
// The kit's parts are in the global namespace ::ui; the firmware has a workshop::ui of its own, so every name here
// is written ::ui::.
#pragma once

#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include "kit/display/ui.h"

namespace wkit {

// A line of text that must fit on one line, cut at a word, never in the middle of one: "Local AI isn't answering. The
// PC is on; Local AI itself isn't…" and not "…isn't a…". The kit's own ui::ellipsize cuts at a character, which is its
// last resort and ours when a single word is wider than the line. Returns true when the text was shortened (it ends in
// an ellipsis then, so a shortened line never reads as the whole line). The font is never shrunk.
inline bool fitWords(UiCanvas& c, const char* s, UiFont f, int maxW, char* out, size_t n) {
  if (n == 0) return false;
  out[0] = '\0';
  if (!s) return false;
  size_t len = strlen(s);
  if (len >= n) len = n - 1;
  while (len > 0 && (static_cast<unsigned char>(s[len]) & 0xC0) == 0x80) len--;  // not mid-character
  memcpy(out, s, len);
  out[len] = '\0';
  if (len == strlen(s) && c.textWidth(out, f) <= maxW) return false;
  static const char kEllipsis[] = "\xE2\x80\xA6";
  // Walk back over the spaces; the text before each one, less trailing punctuation that reads badly before an ellipsis.
  for (size_t cut = len; cut-- > 0;) {
    if (s[cut] != ' ') continue;
    size_t end = cut;
    while (end > 0 && (s[end - 1] == ' ' || s[end - 1] == ',' || s[end - 1] == ';' || s[end - 1] == ':' || s[end - 1] == '-')) end--;
    if (end == 0 || end + sizeof kEllipsis > n) continue;
    memcpy(out, s, end);
    memcpy(out + end, kEllipsis, sizeof kEllipsis);
    if (c.textWidth(out, f) <= maxW) return true;
  }
  return ::ui::ellipsize(c, s, f, maxW, out, n);  // one word wider than the line: the kit's cut
}

// The card behind a printer or a timer: the surface and the 4 px bar down its left edge, as the kit's NeedsRow draws
// its own, so a card of ours sits beside the kit's rows as one family.
inline void card(UiCanvas& c, const ::ui::Rect& r, uint16_t bar) {
  c.fillRoundRect(r.x, r.y, r.w, r.h, UI_R_2, UI_COLOR_SURFACE);
  if (bar != 0) c.fillRect(r.x, r.y + 6, 4, r.h - 12, bar);
}

// A right-pointing chevron 8 px wide, centred on (x, cy): a card that opens another screen when tapped.
inline void chevronRight(UiCanvas& c, int x, int cy, uint16_t color) {
  ::ui::strokeLine(c, x, cy - 6, x + 6, cy, 2, color);
  ::ui::strokeLine(c, x + 6, cy, x, cy + 6, 2, color);
}

// The kit's Button, as wide as its label needs and 48 px high, at the right of a card with 8 px to the card's edge and
// centred up and down. A card that holds a button is at least 56 px high.
inline ::ui::Rect buttonAtRight(UiCanvas& c, const ::ui::Rect& cardRect, const char* label) {
  const int w = ::ui::Button::width(c, label);
  return ::ui::Rect{cardRect.right() - 8 - w, cardRect.y + (cardRect.h - ::ui::kTarget) / 2, w, ::ui::kTarget};
}

}  // namespace wkit
