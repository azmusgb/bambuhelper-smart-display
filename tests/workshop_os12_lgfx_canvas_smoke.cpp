// Host test for firmware/platform/ui/lgfx_canvas.hpp (display-kit K5) and for the generated palette header
// firmware/platform/ui/display_palette.h (display-kit K1).
//
// The adapter is driven with a recording stand-in for LovyanGFX: every UiCanvas call must reach the right Gfx call
// with the right arguments, text must be placed by its baseline, a font must load once and again only when it
// changes, a missing face must draw nothing and measure 0, and release() must unload and run the hook. The palette
// header is compiled against the kit's tokens: every tint must equal the kit's own blend565, and every constant must
// be a kit token or such a tint.
//
// The kit is C++17 and is found as kit/ (a copy or link of assets/ui; the firmware build installs it as include/kit/):
//   mkdir -p /tmp/kit-inc && ln -sfn "$PWD/assets/ui" /tmp/kit-inc/kit
//   g++ -std=c++17 -Wall -Wextra -Werror -pedantic -I/tmp/kit-inc tests/workshop_os12_lgfx_canvas_smoke.cpp -o /tmp/lgfx-canvas-smoke

#include "../firmware/platform/ui/lgfx_canvas.hpp"
#include "../firmware/platform/ui/display_palette.h"

#include <stdio.h>
#include <string.h>
#include <string>
#include <vector>

namespace {

int g_failures = 0;
long g_checks = 0;

void check(bool ok, const char* what, long a = 0, long b = 0) {
  ++g_checks;
  if (ok) return;
  ++g_failures;
  if (g_failures <= 40) printf("FAIL %s (%ld, %ld)\n", what, a, b);
}

// Records what the adapter asks LovyanGFX for, with the same method shapes.
struct FakeGfx {
  std::vector<std::string> calls;
  bool loadOk = true;
  int loads = 0, unloads = 0;
  const uint8_t* font = nullptr;
  uint8_t datum = 0;
  uint16_t fg = 0, bg = 0;
  float size = 0;

  void note(const char* name, long a = 0, long b = 0, long c = 0, long d = 0, long e = 0, long f = 0) {
    char buf[96];
    snprintf(buf, sizeof buf, "%s %ld %ld %ld %ld %ld %ld", name, a, b, c, d, e, f);
    calls.push_back(buf);
  }
  void fillRect(int32_t x, int32_t y, int32_t w, int32_t h, uint16_t c) { note("fillRect", x, y, w, h, c); }
  void fillRoundRect(int32_t x, int32_t y, int32_t w, int32_t h, int32_t r, uint16_t c) { note("fillRoundRect", x, y, w, h, r, c); }
  void drawLine(int32_t x0, int32_t y0, int32_t x1, int32_t y1, uint16_t c) { note("drawLine", x0, y0, x1, y1, c); }
  bool loadFont(const uint8_t* data) {
    loads++;
    if (!loadOk) return false;
    font = data;
    return true;
  }
  void unloadFont() { unloads++; font = nullptr; }
  void setTextDatum(uint8_t d) { datum = d; }
  void setTextColor(uint16_t f, uint16_t b) { fg = f; bg = b; }
  void setTextSize(float s) { size = s; }
  size_t drawString(const char* s, int32_t x, int32_t y) {
    note("drawString", x, y, font ? font[0] : -1, datum, fg, bg);
    calls.back() += std::string(" ") + s;
    return strlen(s);
  }
  int32_t textWidth(const char* s) { return font ? (int32_t)strlen(s) * (font[0] + 1) : 0; }
};

const uint8_t kFace14[] = {14}, kFace16[] = {16}, kFace20[] = {20}, kFace26[] = {26}, kFace34[] = {34};
const UiLgfxFonts kFonts = {{kFace14, kFace16, kFace20, kFace26, kFace34}};

int g_hooked = 0;
void hook() { g_hooked++; }

void shapes() {
  FakeGfx g;
  UiLgfxCanvas<FakeGfx> c(g, kFonts);
  c.fillRect(1, 2, 3, 4, 0x1234);
  check(g.calls.back() == "fillRect 1 2 3 4 4660 0", "fillRect forwarded");
  c.fillRect(1, 2, 0, 4, 0x1234);
  c.fillRect(1, 2, 3, -1, 0x1234);
  check(g.calls.size() == 1, "an empty rect draws nothing", (long)g.calls.size());
  c.fillRoundRect(10, 20, 40, 30, 6, 0xABCD);
  check(g.calls.back() == "fillRoundRect 10 20 40 30 6 43981", "fillRoundRect forwarded");
  c.fillRoundRect(10, 20, 18, 18, 9, 0x0001);
  check(g.calls.back() == "fillRoundRect 10 20 18 18 9 1", "a disc keeps r = w/2");
  c.fillRoundRect(0, 0, 10, 20, 50, 7);
  check(g.calls.back() == "fillRoundRect 0 0 10 20 5 7", "a corner larger than half a side is clamped");
  c.fillRoundRect(0, 0, 10, 20, 0, 7);
  check(g.calls.back() == "fillRect 0 0 10 20 7 0", "r = 0 is a plain rect");
  c.line(5, 6, 7, 8, 0x00FF);
  check(g.calls.back() == "drawLine 5 6 7 8 255 0", "line forwarded, both ends");
}

void text() {
  FakeGfx g;
  UiLgfxCanvas<FakeGfx> c(g, kFonts);
  c.text(12, 40, "Up", UiFont::Fs4, 0xFFFF, 0x0841);
  check(g.calls.size() == 1 && g.calls[0] == "drawString 12 40 16 16 65535 2113 Up", "text is placed by its baseline in the face");
  check(g.size == 1.0f, "the text size is 1");
  check(g.loads == 1, "the face loaded once", g.loads);
  c.text(30, 40, "Down", UiFont::Fs4, 0x1111, 0x2222);
  check(g.loads == 1, "the same face is not loaded again", g.loads);
  c.text(0, 0, "x", UiFont::Readout, 1, 2);
  check(g.loads == 2 && g.font == kFace34, "a new face loads when asked for", g.loads);
  check(c.textWidth("abc", UiFont::Readout) == 3 * 35, "textWidth measures in the face", c.textWidth("abc", UiFont::Readout));
  check(c.textWidth("abc", UiFont::Fs3) == 3 * 15 && g.font == kFace14, "textWidth selects the face", c.textWidth("abc", UiFont::Fs3));
  const size_t before = g.calls.size();
  c.text(0, 0, "", UiFont::Fs3, 1, 2);
  c.text(0, 0, nullptr, UiFont::Fs3, 1, 2);
  check(g.calls.size() == before, "empty and null text draw nothing");
  check(c.textWidth("", UiFont::Fs3) == 0 && c.textWidth(nullptr, UiFont::Fs3) == 0, "empty and null text measure 0");
  const uint8_t* faces[] = {kFace14, kFace16, kFace20, kFace26, kFace34};
  const UiFont fonts[] = {UiFont::Fs3, UiFont::Fs4, UiFont::Fs5, UiFont::Fs6, UiFont::Readout};
  for (int i = 0; i < 5; i++) {
    c.text(0, 0, "a", fonts[i], 1, 2);
    check(g.font == faces[i], "each UiFont maps to its own face", i);
  }
}

void missingAndFailing() {
  FakeGfx g;
  const UiLgfxFonts partial = {{kFace14, nullptr, kFace20, nullptr, nullptr}};
  UiLgfxCanvas<FakeGfx> c(g, partial);
  check(c.hasFont(UiFont::Fs3) && !c.hasFont(UiFont::Fs4), "hasFont tells a linked face from a missing one");
  g.calls.clear();
  c.text(0, 0, "Hi", UiFont::Fs4, 1, 2);
  check(g.calls.empty(), "a missing face draws nothing (no other size is substituted)");
  check(c.textWidth("Hi", UiFont::Fs4) == 0, "a missing face measures 0");
  g.loadOk = false;
  g.calls.clear();
  c.text(0, 0, "Hi", UiFont::Fs5, 1, 2);
  check(g.calls.empty() && !c.hasFont(UiFont::Fs5), "a face that fails to load draws nothing");
  g.loadOk = true;
  c.text(0, 0, "Hi", UiFont::Fs5, 1, 2);
  check(g.calls.size() == 1, "and loads again on the next draw");
  check(!c.hasFont(static_cast<UiFont>(9)), "an out-of-range font is a missing face");
}

void release() {
  FakeGfx g;
  g_hooked = 0;
  UiLgfxCanvas<FakeGfx> c(g, kFonts, hook);
  c.release();
  check(g.unloads == 0 && g_hooked == 1, "release with nothing loaded does not unload, and runs the hook", g.unloads, g_hooked);
  c.text(0, 0, "a", UiFont::Fs3, 1, 2);
  c.release();
  check(g.unloads == 1 && g.font == nullptr && g_hooked == 2, "release unloads the face and runs the hook", g.unloads, g_hooked);
  c.text(0, 0, "a", UiFont::Fs3, 1, 2);
  check(g.loads == 2, "a face loads again after release", g.loads);
}

// Every palette constant is a kit token or a tint of two, and a tint is the kit's own blend565.
static_assert(OS12V_ACCENT == UI_COLOR_ACCENT && UI_ORANGE == UI_COLOR_ACCENT && C10_ACCENT == UI_COLOR_ACCENT &&
                  W25_ACCENT == UI_COLOR_ACCENT,
              "every accent is the kit's accent");
static_assert(OS12V_GREEN == UI_COLOR_OK && OS12V_AMBER == UI_COLOR_WARN && OS12V_RED == UI_COLOR_BAD, "lamps are the kit's lamps");
static_assert(OS12V_BG == UI_COLOR_BG && UI_PANEL == UI_COLOR_SURFACE && OS12V_SURFACE2 == UI_COLOR_SURFACE_2 &&
                  OS12V_LINE == UI_COLOR_LINE && OS12V_TEXT == UI_COLOR_TEXT && OS12V_MUTED == UI_COLOR_MUTED,
              "greys are the kit's graphite");
// The classes the screens tell apart by comparing colours must stay four different colours.
static_assert(OS12V_ACCENT != OS12V_GREEN && OS12V_ACCENT != OS12V_AMBER && OS12V_ACCENT != OS12V_RED &&
                  OS12V_GREEN != OS12V_AMBER && OS12V_GREEN != OS12V_RED && OS12V_AMBER != OS12V_RED &&
                  OS12V_TEXT != OS12V_MUTED,
              "accent, ok, warn, bad, text and muted stay distinct");
static_assert(UI_GLOW == ui::blend565(UI_COLOR_ACCENT, UI_COLOR_BG, 14), "glow is the kit's accentSoft");
static_assert(UI_GREEN_BG == ui::blend565(UI_COLOR_OK, UI_COLOR_SURFACE, 18), "ok tint is the kit's chip tint");
static_assert(UI_WARN_BG == ui::blend565(UI_COLOR_WARN, UI_COLOR_SURFACE, 18), "warn tint is the kit's chip tint");
static_assert(UI_CYAN_BG == ui::blend565(UI_COLOR_ACCENT, UI_COLOR_SURFACE, 18), "accent tint is the kit's chip tint");
static_assert(UI_PURP_BG == ui::blend565(UI_COLOR_ACCENT_TEXT, UI_COLOR_SURFACE, 18), "accent text tint is the kit's chip tint");
static_assert(uiTint565(0xFFFF, 0x0000, 50) == ui::blend565(0xFFFF, 0x0000, 50), "the header's blend is the kit's blend");

}  // namespace

int main() {
  shapes();
  text();
  missingAndFailing();
  release();
  printf("lgfx canvas smoke: %ld checks, %d failures\n", g_checks, g_failures);
  return g_failures ? 1 : 0;
}
