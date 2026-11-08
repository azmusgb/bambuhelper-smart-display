// Host test for idle Home on the appliance-ui display kit (display-kit rollout step 4):
// firmware/platform/ui/home_idle_kit.hpp, kit_screen.hpp and the layout in tabs_layout.hpp (homeIdleRect).
//
// The screen is drawn through the kit's UiCanvas on an in-memory RGB565 panel that lays text out with the real Archivo
// VLW files (assets/ui/display/fonts), so the widths are the device's. It checks that
//  - the layout is the kit's own geometry (NeedsRow 72 px, Button 48 px, the 48 px header) and what is drawn is what
//    is tappable: no overlap, nothing under the tab bar, each rect is its own hit;
//  - every line of text is inside the part that owns it, in a kit font (none under 14 px), and a line that had to be
//    shortened was cut at a word and ends in an ellipsis, never mid-word, unless one word is wider than the line;
//  - a need with a long reason, a long title, no clock, no weather, a long printer line, a quiet printer, a running
//    timer and an empty string all draw without leaving the panel.
// With WORKSHOP_HOME_IDLE_PPM_DIR set it also writes each case as a PPM, for a person to look at.
//
// The kit is C++17 and is found as kit/ (a link to assets/ui; the firmware build installs it as include/kit/). Run it
// from the repository root:
//   mkdir -p /tmp/kit-inc && ln -sfn "$PWD/assets/ui" /tmp/kit-inc/kit
//   g++ -std=c++17 -Wall -Wextra -Werror -pedantic -I/tmp/kit-inc tests/workshop_os12_home_idle_kit_smoke.cpp -o /tmp/home-idle-kit-smoke

#include "../firmware/platform/localai/workshop_localai_feed_core.hpp"
#include "../firmware/platform/ui/home_idle_kit.hpp"
#include "../firmware/platform/ui/more_layout.hpp"
#include "../firmware/platform/ui/tabs_layout.hpp"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <string>
#include <vector>

namespace {

namespace wtl = workshop::ui::tabs;

int g_failures = 0;
long g_checks = 0;

void check(bool ok, const char* what, const char* detail = "") {
  ++g_checks;
  if (ok) return;
  ++g_failures;
  if (g_failures <= 40) printf("FAIL %s %s\n", what, detail);
}

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

// ---- Cases -------------------------------------------------------------------------------------------------------------

wkit::HomeIdleModel baseModel() {
  wkit::HomeIdleModel m;
  for (uint8_t i = 0; i < 4; i++) m.rect[i] = [&] { const wtl::Rect r = wtl::homeIdleRect(i); return ::ui::Rect{r.x, r.y, r.w, r.h}; }();
  m.now = ::ui::Clock{1794000000u, 3600 * -8};
  m.title = "2:12 PM";
  m.subtitle = "68\xC2\xB0 Clear";
  m.need[0].tone = ::ui::NeedTone::Bad;
  m.need[0].title = "Local AI";
  m.need[0].detail = "Local AI isn't answering. The PC is on; Local AI itself isn't answering.";
  m.need[0].asOf = m.now.epoch - 5400;
  m.need[1].tone = ::ui::NeedTone::Attention;
  m.need[1].title = "Ad blocking";
  m.need[1].detail = "Ad blocking is off. AdGuard's protection is switched off on the Pi.";
  m.need[1].area = "+3 more";
  m.printerKind = ::ui::ChipKind::Ok;
  m.printerHeadline = "Ready";
  m.printerLine = "X2D \xC2\xB7 Nozzle 24\xC2\xB0 \xC2\xB7 Bed 23\xC2\xB0";
  m.printerLineAlt = "Nozzle 24\xC2\xB0 \xC2\xB7 Bed 23\xC2\xB0";
  m.timerValue = "Not running";
  return m;
}

struct Case { const char* name; wkit::HomeIdleModel model; };

bool endsWithEllipsis(const std::string& s) { return s.size() >= 3 && s.compare(s.size() - 3, 3, "\xE2\x80\xA6") == 0; }

// Which of the model's rects holds a text op's ink, or -1: -2 is the header.
int owner(const wkit::HomeIdleModel& m, const TextOp& t, int fontAscent, int fontDescent) {
  const int top = t.baseline - fontAscent, bottom = t.baseline + fontDescent;
  if (top >= 0 && bottom <= ::ui::kHeaderH && t.x >= 0 && t.x + t.w <= ::ui::kScreenW) return -2;
  for (int i = 0; i < 4; i++) {
    const ::ui::Rect& r = m.rect[i];
    if (t.x >= r.x && t.x + t.w <= r.right() && top >= r.y && bottom <= r.bottom()) return i;
  }
  return -1;
}

void runCase(const char* dir, const char* ppmDir, const Case& c) {
  MemCanvas canvas(dir);
  if (!canvas.ok) { check(false, "the Archivo VLW files load"); return; }
  wkit::drawHomeIdle(canvas, c.model);
  for (const TextOp& t : canvas.texts) {
    const int fi = static_cast<int>(t.font);
    const std::string label = std::string(c.name) + ": \"" + t.s + "\"";
    check(owner(c.model, t, canvas.face[fi].ascent, canvas.face[fi].descent) != -1, "text stays inside its part", label.c_str());
    check(::ui::fontPx(t.font) >= 14, "no text under 14 px", label.c_str());
  }
  // The printer card's muted line is never reduced to a prefix and an ellipsis ("X2D \xC2\xB7\xE2\x80\xA6"): it is whole, or it is
  // cut at a word after something worth reading, and it never ends on the separator.
  for (const TextOp& t : canvas.texts) {
    if (t.font != UiFont::Fs3 || t.baseline < c.model.rect[2].y + c.model.rect[2].h / 2 || t.baseline > c.model.rect[2].bottom() ||
        t.x < c.model.rect[2].x || t.x + t.w > c.model.rect[2].right())
      continue;
    const std::string label = std::string(c.name) + ": \"" + t.s + "\"";
    if (!endsWithEllipsis(t.s)) continue;
    const std::string head = t.s.substr(0, t.s.size() - 3);
    check(head.size() >= 8, "a cut printer line keeps more than a prefix", label.c_str());
    check(head.find_last_not_of(' ') != std::string::npos && head.substr(head.find_last_not_of(' ')).compare(0, 2, "\xC2\xB7") != 0,
          "a cut printer line does not end on the separator", label.c_str());
  }
  // Nothing is drawn over the tab bar's guard band (the 54 px at the bottom).
  const int tabTop = ::ui::kScreenH - 54;
  bool clean = true;
  for (int y = tabTop; y < ::ui::kScreenH && clean; y++)
    for (int x = 0; x < ::ui::kScreenW; x++)
      if (canvas.px[static_cast<size_t>(y) * ::ui::kScreenW + static_cast<size_t>(x)] != UI_COLOR_BG) { clean = false; break; }
  check(clean, "nothing under the tab bar", c.name);
  if (ppmDir && *ppmDir) canvas.writePpm(std::string(ppmDir) + "/home-idle-" + c.name + ".ppm");
}

// fitWords on the real face: fits, or ends in an ellipsis after a whole word.
void fitting(const char* dir) {
  MemCanvas canvas(dir);
  if (!canvas.ok) { check(false, "the Archivo VLW files load"); return; }
  const char* texts[] = {"Local AI isn't answering. The PC is on; Local AI itself isn't answering.",
                         "Short", "", "A reason, with commas, that runs on and on and on and on and on and on and on",
                         "Supercalifragilisticexpialidocious_and_more_and_more_and_more_and_more_and_more_and_more"};
  for (const char* s : texts) {
    for (int w : {60, 120, 200, 300, 452}) {
      char out[wkit::kHomeIdleTextMax];
      const bool cut = wkit::fitWords(canvas, s, UiFont::Fs3, w, out, sizeof out);
      const std::string o = out, label = std::string("\"") + s + "\" in " + std::to_string(w);
      check(canvas.textWidth(out, UiFont::Fs3) <= w || w < 20, "fitWords fits", label.c_str());
      check(cut == (o != s), "fitWords says whether it shortened", label.c_str());
      if (!cut) continue;
      check(endsWithEllipsis(o), "a shortened line ends in an ellipsis", label.c_str());
      const std::string head = o.substr(0, o.size() - 3);
      const bool whole = strlen(s) > head.size() && (s[head.size()] == ' ' || head.size() == 0 ||
                                                       strchr(" ,;:-", s[head.size()]) != nullptr);
      const bool oneWord = strchr(s, ' ') == nullptr || canvas.textWidth("Supercalifragilisticexpialidocious_and", UiFont::Fs3) > w;
      check(whole || oneWord, "cut at a word, not inside one", label.c_str());
    }
  }
  char out[8];
  check(!wkit::fitWords(canvas, nullptr, UiFont::Fs3, 100, out, sizeof out) && out[0] == '\0', "a null line is empty");
}

void layout() {
  namespace more = workshop::ui::more;
  const wtl::Screen s = more::makeScreen(480, 320);
  const wtl::Screen portrait = more::makeScreen(320, 480);
  check(wtl::homeIdleKit(s) && !wtl::homeIdleKit(portrait), "the kit's layout is for the 480 x 320 panel only");
  check(wtl::kHomeIdleNeedH == ::ui::NeedsRow::kHeight, "a need is the kit's 72 px");
  check(wtl::kHomeIdleHeaderH == ::ui::kHeaderH && wtl::kHomeIdleKitW == ::ui::kScreenW && wtl::kHomeIdleKitH == ::ui::kScreenH,
        "the header and the panel are the kit's");
  check(wtl::kHomeIdleBandH >= ::ui::kTarget + 8, "the band holds the kit's 48 px button");
  check(wtl::kHomeIdleMargin >= 4 && wtl::kHomeIdleGap >= 4, "gaps");
  const wtl::ViewSpec& v = wtl::view(wtl::View::HomeIdle);
  check(v.itemCount == 4, "idle Home has four items");
  const int tabTop = s.h - more::kTabH;
  for (uint8_t i = 0; i < 4; i++) {
    const wtl::Rect r = wtl::itemRect(s, v, 0, 0, i);
    check(!r.empty() && r.x >= 0 && r.right() <= s.w && r.y >= ::ui::kHeaderH && r.bottom() <= tabTop, "an item sits between the header and the tab bar");
    check(r.x == wtl::homeIdleRect(i).x && r.y == wtl::homeIdleRect(i).y, "itemRect is the kit's rect");
    for (uint8_t j = 0; j < i; j++) {
      const wtl::Rect o = wtl::itemRect(s, v, 0, 0, j);
      const bool apart = r.right() <= o.x || o.right() <= r.x || r.bottom() <= o.y || o.bottom() <= r.y;
      check(apart, "two items do not overlap");
    }
    const wtl::Hit h = wtl::hitTest(s, wtl::View::HomeIdle, 0, 0, r.x + r.w / 2, r.y + r.h / 2);
    check(h.kind == wtl::HitKind::Item && h.index == i, "each card is its own target");
    check(r.h >= ::ui::kTarget && r.w >= ::ui::kTarget, "every target is at least 48 px");
  }
  // The timer's button is inside its card: a tap on it is the timer item.
  wkit::HomeIdleModel m = baseModel();
  MemCanvas canvas("assets/ui/display/fonts");
  const char* labels[] = {"Start", "Cancel", "Clear"};
  for (const char* label : labels) {
    const ::ui::Rect b = wkit::buttonAtRight(canvas, m.rect[3], label);
    check(b.h == ::ui::kTarget && b.x >= m.rect[3].x && b.right() <= m.rect[3].right() && b.y >= m.rect[3].y && b.bottom() <= m.rect[3].bottom(),
          "the timer button is 48 px and inside its card", label);
    const wtl::Hit h = wtl::hitTest(s, wtl::View::HomeIdle, 0, 0, b.x + b.w / 2, b.y + b.h / 2);
    check(h.kind == wtl::HitKind::Item && h.index == 3, "the button is the timer's target", label);
  }
  // The portrait panel keeps the slot grid: four slot-sized items.
  for (uint8_t i = 0; i < 4; i++) check(!wtl::itemRect(portrait, v, 0, 0, i).empty(), "portrait panel keeps its own layout");
}

// The printer card holds a half-width line (about 190 px at 14 px): the readings of a healthy printer are shown whole
// ("Nozzle 27\xC2\xB0 \xC2\xB7 Bed 26\xC2\xB0"), whichever of the fuller wording fits, and never as the name and an ellipsis.
bool drawnLine(const MemCanvas& canvas, const wkit::HomeIdleModel& m, const char* needle) {
  for (const TextOp& t : canvas.texts)
    if (t.font == UiFont::Fs3 && t.baseline > m.rect[2].y + m.rect[2].h / 2 && t.baseline <= m.rect[2].bottom() && t.s.find(needle) != std::string::npos &&
        !endsWithEllipsis(t.s))
      return true;
  return false;
}

// Kit 2.13: a level-one header has no Back and no Home (Home is the tab bar's). Idle Home draws only its title and the
// subtitle line: the header's 88 px at each end hold no button glyph, so no pixel there but the bar colour.
void headerHasNoButtons(const char* dir) {
  wkit::HomeIdleModel m = baseModel();
  MemCanvas canvas(dir);
  wkit::drawHomeIdle(canvas, m);
  int odd = 0;
  for (int y = 4; y < ::ui::kHeaderH - 4; y++)
    for (int x = ::ui::kScreenW - 80; x < ::ui::kScreenW - 4; x++)
      if (canvas.px[static_cast<size_t>(y) * ::ui::kScreenW + static_cast<size_t>(x)] != UI_COLOR_BAR) odd++;
  check(odd == 0, "the header's right end holds no Home button", std::to_string(odd).c_str());
}

// The bar down a need's left edge is the colour of the item's own severity, whatever its place in the list.
void needTones(const char* dir) {
  namespace lai = workshop::localai;
  struct Row { const char* feed; lai::Tone tone; uint16_t bar; const char* what; };
  const Row rows[] = {
      {"bad", lai::toneFrom("bad"), UI_COLOR_BAD, "a failed item is the bad colour"},
      {"warn", lai::toneFrom("warn"), UI_COLOR_WARN, "Pi Hub's warn is amber, not grey"},
      {"warning", lai::toneFrom("warning"), UI_COLOR_WARN, "a warning is amber"},
      {"attention", lai::toneFrom("attention"), UI_COLOR_WARN, "attention is amber"},
      {"info", lai::toneFrom("info"), UI_COLOR_MUTED, "information is the quiet bar"},
      {"ok", lai::toneFrom("ok"), UI_COLOR_MUTED, "good news is the quiet bar"},
      {"busy", lai::toneFrom("busy"), UI_COLOR_MUTED, "busy is the quiet bar"},
      {"unknown word", lai::toneFrom("surprise"), UI_COLOR_MUTED, "an unrecognised tone is information, not an alarm"},
  };
  for (const Row& r : rows) {
    for (int place = 0; place < 2; place++) {  // the same severity in either row
      wkit::HomeIdleModel m = baseModel();
      m.need[place].tone = wkit::needToneOf(r.tone);
      m.need[1 - place].tone = wkit::needToneOf(lai::Tone::Info);  // the other row is the quiet tier
      MemCanvas canvas(dir);
      wkit::drawHomeIdle(canvas, m);
      const ::ui::Rect& rc = m.rect[place];
      const uint16_t drawn = canvas.px[static_cast<size_t>(rc.y + rc.h / 2) * ::ui::kScreenW + static_cast<size_t>(rc.x + 1)];
      const std::string label = std::string(r.feed) + " in row " + std::to_string(place);
      check(drawn == r.bar, r.what, label.c_str());
    }
  }
}

// Printer's Status / AMS / Control / Camera is the kit's Tabs part: the layout's rectangles are the kit's, every label
// fits whole, a tap lands on the tab drawn there, and the strip paints inside its band.
void printerStrip(const char* dir) {
  namespace more = workshop::ui::more;
  static const ::ui::TabItem kTabs[wtl::kSegmentCount] = {{"Status", true}, {"AMS", true}, {"Control", true}, {"Camera", true}};
  check(wtl::kSegmentH == ::ui::Tabs::kHeight, "the Printer strip is the kit's 48 px");
  const wtl::Screen sizes[2] = {more::makeScreen(480, 320), more::makeScreen(320, 480)};
  for (const wtl::Screen& s : sizes) {
    const workshop::ui::more::Rect band = wtl::segmentBand(s);
    const ::ui::Rect kb{band.x, band.y, band.w, band.h};
    for (uint8_t i = 0; i < wtl::kSegmentCount; ++i) {
      const workshop::ui::more::Rect r = wtl::segmentRect(s, i);
      const ::ui::Rect k = ::ui::Tabs::tabRect(kb, wtl::kSegmentCount, i);
      check(r.x == k.x && r.y == k.y && r.w == k.w && r.h == k.h, "segmentRect is the kit's tabRect");
      check(::ui::Tabs::hit(kb, kTabs, wtl::kSegmentCount, r.x + r.w / 2, r.y + r.h / 2) == i, "the kit hits the tab the layout hits");
    }
    if (!s.landscape()) continue;  // the only panel is 480 x 320; 320 wide holds the layout tests, not the words
    MemCanvas canvas(dir);
    if (!canvas.ok) { check(false, "the Archivo VLW files load"); return; }
    check(::ui::Tabs::fits(canvas, kb, kTabs, wtl::kSegmentCount), "every Printer tab label fits whole");
  }
}

void printerLines(const char* dir) {
  {  // healthy idle: the readings, whole, on the one line
    wkit::HomeIdleModel m = baseModel();
    MemCanvas canvas(dir);
    wkit::drawHomeIdle(canvas, m);
    check(drawnLine(canvas, m, "Nozzle 24\xC2\xB0") && drawnLine(canvas, m, "Bed 23\xC2\xB0"), "healthy idle shows nozzle and bed whole");
  }
  {  // a failure's reason keeps its words when the name does not fit with it
    wkit::HomeIdleModel m = baseModel();
    m.printerKind = ::ui::ChipKind::Bad;
    m.printerHeadline = "Needs attention";
    m.printerLine = "X2D \xC2\xB7 The nozzle is clogged";
    m.printerLineAlt = "The nozzle is clogged";
    MemCanvas canvas(dir);
    wkit::drawHomeIdle(canvas, m);
    check(drawnLine(canvas, m, "The nozzle is clogged"), "a failure reason is shown whole");
  }
}

}  // namespace

int main(int argc, char** argv) {
  const char* dir = argc > 1 ? argv[1] : "assets/ui/display/fonts";
  const char* ppmDir = getenv("WORKSHOP_HOME_IDLE_PPM_DIR");
  layout();
  fitting(dir);

  std::vector<Case> cases;
  cases.push_back({"calm", baseModel()});
  {
    Case c{"all-clear", baseModel()};
    c.model.need[0] = ::ui::NeedItem{};
    c.model.need[0].tone = ::ui::NeedTone::Warn;
    c.model.need[0].title = "All clear";
    c.model.need[0].detail = "Nothing needs you right now.";
    c.model.need[1] = ::ui::NeedItem{};
    c.model.need[1].tone = ::ui::NeedTone::Warn;
    c.model.need[1].title = "Local AI";
    c.model.need[1].detail = "Every card is on the Local AI tab";
    cases.push_back(c);
  }
  {
    Case c{"no-clock", baseModel()};
    c.model.now = ::ui::Clock{0, 0};
    c.model.title = "Home";
    c.model.subtitle = nullptr;
    cases.push_back(c);
  }
  {
    Case c{"long-text", baseModel()};
    c.model.need[0].title = "Pi Hub is not answering and the household dashboard cannot be reached right now";
    c.model.need[1].detail = "Unbroken_unbroken_unbroken_unbroken_unbroken_unbroken_unbroken_unbroken_unbroken_unbroken";
    c.model.printerHeadline = "Finished Wed 9:45 AM and cleared the plate";
    c.model.printerLine = "X2D \xC2\xB7 hex-tile_E-027_BLD-027-02_with_a_very_long_job_name_that_will_not_fit";
    c.model.printerLineAlt = "hex-tile_E-027_BLD-027-02_with_a_very_long_job_name_that_will_not_fit";
    c.model.subtitle = "Alert cleared";
    c.model.subtitleColor = UI_COLOR_WARN;
    cases.push_back(c);
  }
  {
    Case c{"empty", baseModel()};
    c.model.need[0] = ::ui::NeedItem{};
    c.model.need[1] = ::ui::NeedItem{};
    c.model.printerHeadline = "";
    c.model.printerLine = "";
    c.model.timerValue = "";
    cases.push_back(c);
  }
  static const ::ui::Reading quiet = ::ui::Reading::stale("1", 1794000000u - 240);
  {  // the device's capture: Finished, with the job's name, in a half-width card
    Case c{"finished-job", baseModel()};
    c.model.printerHeadline = "Finished";
    c.model.printerLine = "X2D \xC2\xB7 hex-tile_E-027_BLD-027-02";
    c.model.printerLineAlt = "hex-tile_E-027_BLD-027-02";
    cases.push_back(c);
  }
  {
    Case c{"quiet-printer", baseModel()};
    c.model.printerKind = ::ui::ChipKind::Unknown;
    c.model.printerHeadline = "No readings";
    c.model.printerLine = "X2D";
    c.model.printerAgeLead = "Last report";
    c.model.printerAge = &quiet;
    cases.push_back(c);
  }
  {
    Case c{"never-read", baseModel()};
    c.model.printerKind = ::ui::ChipKind::Unknown;
    c.model.printerHeadline = "No readings";
    c.model.printerLine = "X2D";
    c.model.printerAgeLead = "Last report";
    static const ::ui::Reading never = ::ui::Reading::neverRead();
    c.model.printerAge = &never;
    cases.push_back(c);
  }
  {
    Case c{"timer-running", baseModel()};
    c.model.timerValue = "12:04 left";
    c.model.timerValueColor = UI_COLOR_ACCENT_TEXT;
    c.model.timerButton = "Cancel";
    c.model.timerPrimary = false;
    cases.push_back(c);
  }
  {
    Case c{"timer-done", baseModel()};
    c.model.timerValue = "Done";
    c.model.timerValueColor = UI_COLOR_WARN;
    c.model.timerButton = "Clear";
    c.model.timerPrimary = false;
    c.model.printerKind = ::ui::ChipKind::Bad;
    c.model.printerHeadline = "Needs attention";
    c.model.printerLine = "X2D \xC2\xB7 The nozzle is clogged";
    cases.push_back(c);
  }
  for (const Case& c : cases) runCase(dir, ppmDir, c);
  printerLines(dir);
  printerStrip(dir);
  needTones(dir);
  headerHasNoButtons(dir);

  printf("home idle kit smoke: %ld checks, %d failures\n", g_checks, g_failures);
  return g_failures ? 1 : 0;
}
