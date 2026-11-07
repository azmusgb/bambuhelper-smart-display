// An in-memory RGB565 panel for the display kit's host tests: UiCanvas over a 480 x 320 buffer that lays text out with
// the real Archivo VLW files (assets/ui/display/fonts), so a width measured here is the device's. It records every text
// draw (TextOp) so a test can ask what was written, where and in which face. Shared by the screens' smoke tests
// (tests/workshop_os12_more_picker_smoke.cpp); copied from tests/workshop_os12_home_idle_kit_smoke.cpp, which keeps its own.
#pragma once

#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string>
#include <vector>

#include "../firmware/platform/ui/kit_screen.hpp"

namespace kittest {

// ---- Archivo VLW, as LovyanGFX reads it -------------------------------------------------------------------------------

struct Glyph { uint32_t cp; int h, w, adv, dY, dX; size_t bitmap; };
struct Face {
  std::vector<uint8_t> data;
  std::vector<Glyph> glyphs;
  int ascent = 0, descent = 0;
  const Glyph* find(uint32_t cp) const {
    for (const Glyph& g : glyphs) if (g.cp == cp) return &g;
    return nullptr;
  }
};

int32_t be32(const std::vector<uint8_t>& d, size_t at) {
  return static_cast<int32_t>((uint32_t(d[at]) << 24) | (uint32_t(d[at + 1]) << 16) | (uint32_t(d[at + 2]) << 8) | d[at + 3]);
}

bool loadFace(const char* path, Face& f) {
  FILE* fp = fopen(path, "rb");
  if (!fp) return false;
  fseek(fp, 0, SEEK_END);
  const long n = ftell(fp);
  fseek(fp, 0, SEEK_SET);
  f.data.resize(static_cast<size_t>(n));
  const size_t got = fread(f.data.data(), 1, f.data.size(), fp);
  fclose(fp);
  if (got != f.data.size() || n < 24) return false;
  const int count = be32(f.data, 0);
  f.ascent = be32(f.data, 16);
  f.descent = be32(f.data, 20);
  size_t bitmap = 24 + static_cast<size_t>(count) * 28;
  for (int i = 0; i < count; i++) {
    const size_t at = 24 + static_cast<size_t>(i) * 28;
    Glyph g{static_cast<uint32_t>(be32(f.data, at)), be32(f.data, at + 4), be32(f.data, at + 8), be32(f.data, at + 12),
            be32(f.data, at + 16), be32(f.data, at + 20), bitmap};
    bitmap += static_cast<size_t>(g.w) * static_cast<size_t>(g.h);
    f.glyphs.push_back(g);
  }
  return bitmap <= f.data.size();
}

uint32_t nextCodepoint(const char*& p) {
  const unsigned char c = static_cast<unsigned char>(*p);
  int len = c < 0x80 ? 1 : (c >> 5) == 6 ? 2 : (c >> 4) == 14 ? 3 : (c >> 3) == 30 ? 4 : 1;
  uint32_t cp = len == 1 ? c : len == 2 ? (c & 0x1F) : len == 3 ? (c & 0x0F) : (c & 0x07);
  p++;
  for (int i = 1; i < len && *p; i++, p++) cp = (cp << 6) | (static_cast<unsigned char>(*p) & 0x3F);
  return cp;
}

// ---- The panel ---------------------------------------------------------------------------------------------------------

struct TextOp { int x, baseline, w; UiFont font; std::string s; };

class MemCanvas : public UiCanvas {
 public:
  std::vector<uint16_t> px = std::vector<uint16_t>(::ui::kScreenW * ::ui::kScreenH, 0);
  std::vector<TextOp> texts;
  Face face[5];
  bool ok = true;

  explicit MemCanvas(const char* dir) {
    const char* names[5] = {"archivo-14.vlw", "archivo-16.vlw", "archivo-20.vlw", "archivo-26.vlw", "archivo-readout-34.vlw"};
    for (int i = 0; i < 5; i++) {
      const std::string path = std::string(dir) + "/" + names[i];
      if (!loadFace(path.c_str(), face[i])) { printf("cannot read %s\n", path.c_str()); ok = false; }
    }
  }
  void set(int x, int y, uint16_t c) {
    if (x >= 0 && y >= 0 && x < ::ui::kScreenW && y < ::ui::kScreenH) px[static_cast<size_t>(y) * ::ui::kScreenW + static_cast<size_t>(x)] = c;
  }
  void fillRect(int x, int y, int w, int h, uint16_t c) override {
    for (int j = 0; j < h; j++) for (int i = 0; i < w; i++) set(x + i, y + j, c);
  }
  void fillRoundRect(int x, int y, int w, int h, int r, uint16_t c) override {
    if (r > w / 2) r = w / 2;
    if (r > h / 2) r = h / 2;
    for (int j = 0; j < h; j++) for (int i = 0; i < w; i++) {
      const int cx = i < r ? r - 1 - i : i >= w - r ? i - (w - r) : -1;
      const int cy = j < r ? r - 1 - j : j >= h - r ? j - (h - r) : -1;
      if (cx >= 0 && cy >= 0 && cx * cx + cy * cy >= r * r + r) continue;  // outside the corner's circle
      set(x + i, y + j, c);
    }
  }
  void line(int x0, int y0, int x1, int y1, uint16_t c) override {
    const int dx = abs(x1 - x0), dy = -abs(y1 - y0), sx = x0 < x1 ? 1 : -1, sy = y0 < y1 ? 1 : -1;
    int err = dx + dy;
    for (;;) {
      set(x0, y0, c);
      if (x0 == x1 && y0 == y1) break;
      const int e2 = 2 * err;
      if (e2 >= dy) { err += dy; x0 += sx; }
      if (e2 <= dx) { err += dx; y0 += sy; }
    }
  }
  int textWidth(const char* s, UiFont f) override {
    const Face& fc = face[static_cast<int>(f)];
    int w = 0;
    for (const char* p = s; *p;) {
      const Glyph* g = fc.find(nextCodepoint(p));
      if (g) w += g->adv;
    }
    return w;
  }
  void text(int x, int baseline, const char* s, UiFont f, uint16_t fg, uint16_t bg) override {
    texts.push_back(TextOp{x, baseline, textWidth(s, f), f, s});
    const Face& fc = face[static_cast<int>(f)];
    int pen = x;
    for (const char* p = s; *p;) {
      const Glyph* g = fc.find(nextCodepoint(p));
      if (!g) continue;
      for (int j = 0; j < g->h; j++) for (int i = 0; i < g->w; i++) {
        const int a = fc.data[g->bitmap + static_cast<size_t>(j) * static_cast<size_t>(g->w) + static_cast<size_t>(i)];
        if (a) set(pen + g->dX + i, baseline - g->dY + j, ::ui::blend565(fg, bg, a * 100 / 255));
      }
      pen += g->adv;
    }
  }
  void writePpm(const std::string& path) const {
    FILE* fp = fopen(path.c_str(), "wb");
    if (!fp) return;
    fprintf(fp, "P6\n%d %d\n255\n", ::ui::kScreenW, ::ui::kScreenH);
    for (uint16_t v : px) {
      const unsigned char rgb[3] = {static_cast<unsigned char>(::ui::expand5(v >> 11)), static_cast<unsigned char>(::ui::expand6((v >> 5) & 63)),
                                    static_cast<unsigned char>(::ui::expand5(v & 31))};
      fwrite(rgb, 1, 3, fp);
    }
    fclose(fp);
  }
};


}  // namespace kittest
