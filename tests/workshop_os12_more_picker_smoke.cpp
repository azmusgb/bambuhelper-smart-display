// Host test for the More pages' Picker session (display-kit K9, rollout step 5): firmware/platform/ui/more_picker.hpp
// around the kit's ui::Picker, drawn on the in-memory panel of tests/kit_mem_canvas.hpp with the real Archivo faces.
//
// It checks the cases the settings use:
//  - a short list fits on one page, every row at least 48 px, nothing under the tab bar;
//  - a long list (the 42 time zones, the 96 clock times of 15-minute steps) scrolls, and opens on the page with the
//    current choice, which is below page one;
//  - colours show their swatch beside the name;
//  - a long label (a time zone's full name) wraps, in the 16 px face, and is never cut or shrunk;
//  - a tap applies the choice and closes; Back and Home change nothing (apply is never called);
//  - a failed save (apply gives a reason) or a setting that reads back as something else keeps the Picker open, says
//    "Not saved: why" on that row, and keeps the previous choice checked;
//  - an unreadable current value checks nothing and the title line says "Current setting unknown".
//
//   mkdir -p /tmp/kit-inc && ln -sfn "$PWD/assets/ui" /tmp/kit-inc/kit
//   g++ -std=c++17 -Wall -Wextra -Werror -pedantic -I/tmp/kit-inc tests/workshop_os12_more_picker_smoke.cpp -o /tmp/more-picker-smoke
//   /tmp/more-picker-smoke            (from the repository root)

#include "kit_mem_canvas.hpp"
#include "../firmware/platform/ui/more_picker.hpp"
#include "../firmware/platform/ui/more_layout.hpp"

#include <stdio.h>
#include <string.h>
#include <string>
#include <vector>

namespace {

using kittest::MemCanvas;
using kittest::TextOp;
using wkit::PickerSession;

int g_failures = 0;
long g_checks = 0;

void check(bool ok, const char* what, const char* detail = "") {
  ++g_checks;
  if (ok) return;
  ++g_failures;
  if (g_failures <= 40) printf("FAIL %s %s\n", what, detail);
}

const char* g_dir = "assets/ui/display/fonts";

// The setting the Picker edits, as the firmware's setter and reader would: a value, a reason it is refused, a read-back.
int g_value = 0;
const char* g_refuse = nullptr;
int g_driftTo = -1;  // when set, the setting reads back as this instead of what was chosen
int g_applied = 0;
const char* applyValue(int index) {
  ++g_applied;
  if (g_refuse) return g_refuse;
  g_value = index;
  return nullptr;
}
int readValue() { return g_driftTo >= 0 ? g_driftTo : g_value; }

void reset(int value) { g_value = value; g_refuse = nullptr; g_driftTo = -1; g_applied = 0; }

bool shown(const MemCanvas& c, const char* needle) {
  for (const TextOp& t : c.texts) if (t.s.find(needle) != std::string::npos) return true;
  return false;
}

struct List {
  std::vector<::ui::PickerOption> opt;
  std::vector<std::string> text;
  void add(const std::string& label, bool swatch = false, uint16_t colour = 0) {
    text.push_back(label);
    ::ui::PickerOption o;
    o.hasSwatch = swatch;
    o.swatch = colour;
    opt.push_back(o);
  }
  void fix() { for (size_t i = 0; i < opt.size(); i++) opt[i].label = text[i].c_str(); }
};

List namedList(int n) {
  List l;
  for (int i = 0; i < n; i++) l.add("Choice " + std::to_string(i + 1));
  l.fix();
  return l;
}

List clockTimes() {  // 15-minute steps, the 96 options of the K9 clock-time Picker
  List l;
  for (int m = 0; m < 24 * 60; m += 15) {
    char b[8];
    snprintf(b, sizeof b, "%02d:%02d", m / 60, m % 60);
    l.add(b);
  }
  l.fix();
  return l;
}

List timeZones() {
  const char* names[] = {"(UTC-10:00) Hawaii", "(UTC-09:00) Alaska", "(UTC-08:00) Pacific Time (US & Canada), Tijuana, Baja California",
                         "(UTC-07:00) Mountain Time (US & Canada)", "(UTC-06:00) Central Time (US & Canada), Guadalajara, Mexico City, Monterrey",
                         "(UTC-05:00) Eastern Time (New York, Toronto)", "(UTC-04:00) Atlantic Time (Canada)", "(UTC+00:00) Dublin, Edinburgh, Lisbon, London"};
  List l;
  for (int i = 0; i < 42; i++) l.add(i < 8 ? names[i] : "(UTC+01:00) Amsterdam, Berlin, Bern, Rome, Stockholm, Vienna " + std::to_string(i));
  l.fix();
  return l;
}

List colours() {
  const struct { const char* n; uint16_t v; } c[] = {{"Green", UI_COLOR_OK}, {"Cyan", UI_COLOR_ACCENT}, {"Blue", UI_COLOR_ACCENT_TEXT}, {"Orange", UI_COLOR_WARN},
                                                      {"Gold", UI_COLOR_WARN}, {"Yellow", UI_COLOR_WARN}, {"Red", UI_COLOR_BAD}, {"White", UI_COLOR_TEXT}};
  List l;
  for (const auto& x : c) l.add(x.n, true, x.v);
  l.fix();
  return l;
}

bool tapOption(PickerSession& s, MemCanvas& c, int index, PickerSession::Outcome& out) {
  const ::ui::Rect r = s.picker().rowRect(c, index);
  if (r.w <= 0) return false;
  out = s.tap(c, r.x + r.w / 2, r.y + r.h / 2, applyValue, readValue);
  return true;
}

void fits() {
  MemCanvas c(g_dir);
  List l = namedList(3);
  PickerSession s;
  check(s.open("After a print", l.opt.data(), 3, 1), "opens");
  s.draw(c);
  check(!s.picker().scrolls(c), "three options fit on one page");
  for (int i = 0; i < 3; i++) {
    const ::ui::Rect r = s.picker().rowRect(c, i);
    check(r.h >= ::ui::kTarget, "a row is at least 48 px", l.text[i].c_str());
    check(r.bottom() <= ::ui::kScreenH - ::ui::kTabBarH, "a row is above the tab bar");
  }
  check(shown(c, "After a print"), "the title is the setting's name");
  check(!shown(c, "Current setting unknown"), "a known setting says nothing about unknown");
  bool bottom = true;
  for (int y = ::ui::kScreenH - ::ui::kTabBarH; y < ::ui::kScreenH && bottom; y++)
    for (int x = 0; x < ::ui::kScreenW; x++)
      if (c.px[static_cast<size_t>(y) * ::ui::kScreenW + static_cast<size_t>(x)] != 0) { bottom = false; break; }
  check(bottom, "nothing is drawn where the tab bar goes");
  {  // the device's tab bar is 54 px, not the kit's 48
    MemCanvas d(g_dir);
    PickerSession deviceBar;
    List m = namedList(12);
    deviceBar.open("Time zone", m.opt.data(), 12, 0, 54);
    deviceBar.draw(d);
    bool above = true;
    for (int i = deviceBar.picker().firstVisible(d); i < deviceBar.picker().endVisible(d); i++)
      above = above && deviceBar.picker().rowRect(d, i).bottom() <= ::ui::kScreenH - 54;
    check(above, "with the device's 54 px tab bar every row is above it");
  }
}

void scrolling() {
  {
    MemCanvas c(g_dir);
    List l = clockTimes();
    check(l.opt.size() == 96, "96 clock times in 15-minute steps");
    PickerSession s;
    s.open("Night starts", l.opt.data(), 96, 88);  // 22:00
    s.draw(c);
    check(s.picker().scrolls(c), "96 options scroll");
    check(s.picker().firstVisible(c) > 0, "it opens below page one");
    check(s.picker().firstVisible(c) <= 88 && 88 < s.picker().endVisible(c), "the current time is in view");
    const ::ui::Rect next = s.picker().nextRect(c), prev = s.picker().previousRect(c);
    check(next.h >= ::ui::kTarget && prev.h >= ::ui::kTarget, "Previous and Next are 48 px keys");
    const int before = s.picker().firstVisible(c);
    PickerSession::Outcome o = s.tap(c, prev.x + prev.w / 2, prev.y + prev.h / 2, applyValue, readValue);
    check(o == PickerSession::Outcome::Redraw && s.picker().firstVisible(c) < before, "Previous turns the page and asks for a redraw");
    check(g_applied == 0, "turning a page saves nothing");
  }
  {
    MemCanvas c(g_dir);
    List l = timeZones();
    PickerSession s;
    s.open("Time zone", l.opt.data(), 42, 40);
    s.draw(c);
    check(s.picker().scrolls(c) && s.picker().firstVisible(c) > 0, "42 zones scroll and open on the current one's page");
    check(s.picker().firstVisible(c) <= 40 && 40 < s.picker().endVisible(c), "the current zone is in view");
  }
}

void swatches() {
  MemCanvas c(g_dir);
  List l = colours();
  PickerSession s;
  s.open("Arc colour", l.opt.data(), 8, 1);
  s.draw(c);
  for (int i = s.picker().firstVisible(c); i < s.picker().endVisible(c); i++) {
    const ::ui::Rect r = s.picker().rowRect(c, i);
    bool swatch = false;  // the colour appears in the row's left part, beside the name
    for (int y = r.y; y < r.bottom() && !swatch; y++)
      for (int x = r.x; x < r.x + 60; x++)
        if (c.px[static_cast<size_t>(y) * ::ui::kScreenW + static_cast<size_t>(x)] == l.opt[i].swatch) { swatch = true; break; }
    check(swatch, "a colour option shows its swatch", l.text[i].c_str());
  }
}

void longLabel() {
  MemCanvas c(g_dir);
  List l = timeZones();
  PickerSession s;
  s.open("Time zone", l.opt.data(), 42, 4);  // the Central Time zone's full name
  s.draw(c);
  const std::string whole = l.text[4];
  std::string seen;
  bool onlyKitFace = true, ellipsis = false;
  for (const TextOp& t : c.texts) {
    if (whole.find(t.s) == std::string::npos || t.s.size() < 4) continue;
    seen += t.s;
    if (t.font != ::ui::Picker::kFont) onlyKitFace = false;
    if (t.s.find("\xE2\x80\xA6") != std::string::npos) ellipsis = true;
  }
  std::string squeezed, wholeSqueezed;
  for (char ch : seen) if (ch != ' ') squeezed += ch;
  for (char ch : whole) if (ch != ' ') wholeSqueezed += ch;
  check(onlyKitFace, "a long label stays in the 16 px face");
  check(!ellipsis && squeezed == wholeSqueezed, "a long label wraps and is shown in full", seen.c_str());
  check(s.picker().rowRect(c, 4).h > ::ui::kTarget, "its row grew to hold the lines");
}

void applyAndBack() {
  using O = PickerSession::Outcome;
  {  // a tap applies and closes
    reset(1);
    MemCanvas c(g_dir);
    List l = namedList(3);
    PickerSession s;
    s.open("After a print", l.opt.data(), 3, 1);
    s.draw(c);
    O o = O::None;
    check(tapOption(s, c, 2, o), "option 2 is on screen");
    check(o == O::Closed && !s.isOpen() && g_value == 2 && g_applied == 1, "a tap applies the choice and closes");
  }
  {  // Back changes nothing
    reset(1);
    MemCanvas c(g_dir);
    List l = namedList(3);
    PickerSession s;
    s.open("After a print", l.opt.data(), 3, 1);
    s.draw(c);
    const O o = s.tap(c, 20, 24, applyValue, readValue);  // the header's Back
    check(o == O::Closed && !s.isOpen() && g_applied == 0 && g_value == 1, "Back closes and changes nothing");
  }
  {  // Home
    reset(1);
    MemCanvas c(g_dir);
    List l = namedList(3);
    PickerSession s;
    s.open("After a print", l.opt.data(), 3, 1);
    s.draw(c);
    const O o = s.tap(c, ::ui::kScreenW - 40, 24, applyValue, readValue);  // the header's Home
    check(o == O::Home && !s.isOpen() && g_applied == 0, "Home closes and changes nothing");
  }
  {  // a tap outside every row does nothing
    reset(1);
    MemCanvas c(g_dir);
    List l = namedList(3);
    PickerSession s;
    s.open("After a print", l.opt.data(), 3, 1);
    s.draw(c);
    const O o = s.tap(c, ::ui::kScreenW / 2, ::ui::kScreenH - 8, applyValue, readValue);  // where the tab bar is
    check(o == O::None && s.isOpen() && g_applied == 0, "a tap below the list does nothing");
  }
  {  // an empty list does not open
    PickerSession s;
    check(!s.open("Nothing", nullptr, 0, -1) && !s.isOpen(), "an empty list does not open");
  }
}

void failedSave() {
  using O = PickerSession::Outcome;
  for (int mode = 0; mode < 2; mode++) {  // 0: the setter refuses with a reason; 1: it reads back as another value
    reset(1);
    if (mode == 0) g_refuse = "No connection to the Pi";
    else g_driftTo = 1;
    MemCanvas c(g_dir);
    List l = namedList(3);
    PickerSession s;
    s.open("After a print", l.opt.data(), 3, 1);
    s.draw(c);
    O o = O::None;
    check(tapOption(s, c, 2, o), "option 2 is on screen");
    check(o == O::Redraw && s.isOpen() && s.picker().hasFailure(), "a failed save keeps the Picker open", mode ? "read-back" : "refused");
    check(s.picker().current() == 1 && g_value == (mode ? 2 : 1), "the previous choice keeps its check", mode ? "read-back" : "refused");
    MemCanvas again(g_dir);
    s.draw(again);
    check(shown(again, "Not saved"), "the row says it was not saved", mode ? "read-back" : "refused");
    check(mode == 1 || shown(again, "No connection to the Pi"), "and why");
    // the next tap clears the message
    const ::ui::Rect r = s.picker().rowRect(again, 0);
    s.tap(again, r.x + r.w / 2, r.y + r.h / 2, applyValue, readValue);
  }
}

void unknown() {
  reset(0);
  MemCanvas c(g_dir);
  List l = namedList(4);
  PickerSession s;
  s.open("Colour theme", l.opt.data(), 4, -1);
  s.draw(c);
  check(shown(c, "Current setting unknown"), "an unreadable setting says so in the title line");
  check(s.picker().current() == -1, "nothing is checked, the first option is not pre-selected");
}

}  // namespace

int main(int argc, char** argv) {
  if (argc > 1) g_dir = argv[1];
  namespace more = workshop::ui::more;
  check(more::pickerKit(more::makeScreen(480, 320)) && !more::pickerKit(more::makeScreen(320, 480)), "the Picker is for the 480 x 320 panel");
  fits();
  scrolling();
  swatches();
  longLabel();
  applyAndBack();
  failedSave();
  unknown();
  printf("more picker smoke: %ld checks, %d failures\n", g_checks, g_failures);
  return g_failures ? 1 : 0;
}
