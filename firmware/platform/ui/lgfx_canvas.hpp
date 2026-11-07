// The LovyanGFX adapter for the appliance-ui display kit (display-kit K5): UiCanvas drawn on a LovyanGFX panel or sprite.
// This is the one place in the repository that implements the kit's drawing surface; the kit itself depends on no
// graphics library, so its parts are rendered and tested on a Mac. Installed as include/workshop_lgfx_canvas.hpp,
// next to the kit's headers in include/kit/ (apply_workshop_os12_display_kit_palette.py).
//
// Gfx is the LovyanGFX type drawn on (lgfx::LovyanGFX for the panel, or an LGFX_Sprite); it is a template parameter
// only so that tests/workshop_os12_lgfx_canvas_smoke.cpp can drive the adapter with a recording stand-in on a host. The
// firmware instantiates it with lgfx::LovyanGFX, so every member is compiled against the real library.
//
// Fonts: the kit's five faces are Archivo VLW files (appliance-ui display/fonts/*.vlw, 225,129 bytes in all). The
// caller links them in as byte arrays, the way fonts.cpp links the Figtree ones, and passes them in UiLgfxFonts. A face
// with no data draws nothing and measures 0: the adapter never substitutes another size. Until a screen is ported
// (rollout steps 4 and 5) nothing instantiates this class and no font is linked.
//
// State it changes on the target: the current VLW font, the text datum (baseline_left), the text colours and the text
// size (1). The older screen code selects fonts through setFont(), which caches its choice: call release() when a
// canvas draw is done, or pass a hook that does `setFont(tft, FONT_NONE)`, so the next setFont() loads its own font.
#pragma once

#include <stddef.h>
#include <stdint.h>

#include "kit/display/canvas.h"

// One VLW blob per UiFont, indexed by the enum: Fs3 (14 px), Fs4 (16), Fs5 (20), Fs6 (26) and Readout (34, 75% width).
struct UiLgfxFonts {
  const uint8_t* vlw[5];
};

template <class Gfx>
class UiLgfxCanvas : public UiCanvas {
 public:
  // lgfx::baseline_left: text is placed by its baseline, not the top of the line (checked against the library where
  // the firmware instantiates this class).
  static constexpr uint8_t kBaselineLeft = 16;
  using ReleaseHook = void (*)();

  UiLgfxCanvas(Gfx& gfx, const UiLgfxFonts& fonts, ReleaseHook onRelease = nullptr)
      : gfx_(gfx), fonts_(fonts), onRelease_(onRelease) {}

  void fillRect(int x, int y, int w, int h, uint16_t color) override {
    if (w <= 0 || h <= 0) return;
    gfx_.fillRect(x, y, w, h, color);
  }

  void fillRoundRect(int x, int y, int w, int h, int r, uint16_t color) override {
    if (w <= 0 || h <= 0) return;
    // The parts never ask for more than half a side; a corner that would not fit is squared, never inverted.
    const int maxR = (w < h ? w : h) / 2;
    if (r > maxR) r = maxR;
    if (r <= 0) gfx_.fillRect(x, y, w, h, color);
    else gfx_.fillRoundRect(x, y, w, h, r, color);
  }

  void line(int x0, int y0, int x1, int y1, uint16_t color) override { gfx_.drawLine(x0, y0, x1, y1, color); }

  void text(int x, int baseline, const char* utf8, UiFont font, uint16_t fg, uint16_t bg) override {
    if (!utf8 || !*utf8 || !use(font)) return;
    gfx_.setTextDatum(kBaselineLeft);
    gfx_.setTextColor(fg, bg);
    gfx_.drawString(utf8, x, baseline);
  }

  int textWidth(const char* utf8, UiFont font) override {
    if (!utf8 || !*utf8 || !use(font)) return 0;
    return (int)gfx_.textWidth(utf8);
  }

  // True when the face is linked in and loads: what a screen checks before it trusts a layout built on the metrics.
  bool hasFont(UiFont font) { return use(font); }

  // Unloads the VLW font this canvas loaded and tells the older font cache (the hook) that nothing is loaded.
  void release() {
    if (loaded_ >= 0) gfx_.unloadFont();
    loaded_ = -1;
    if (onRelease_) onRelease_();
  }

 private:
  // Loads the face once and keeps it until another is asked for: a VLW load parses the glyph table.
  bool use(UiFont font) {
    const unsigned idx = (unsigned)font;
    if (idx >= sizeof(fonts_.vlw) / sizeof(fonts_.vlw[0]) || !fonts_.vlw[idx]) return false;
    if (loaded_ == (int)idx) return true;
    if (!gfx_.loadFont(fonts_.vlw[idx])) {
      loaded_ = -1;
      return false;
    }
    loaded_ = (int)idx;
    gfx_.setTextSize(1);
    return true;
  }

  Gfx& gfx_;
  UiLgfxFonts fonts_;
  ReleaseHook onRelease_;
  int loaded_ = -1;
};
