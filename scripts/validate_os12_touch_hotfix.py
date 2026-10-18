#!/usr/bin/env python3
"""Validate the Workshop OS 12 More/System touch hotfix (reconstructed source).

Two layers:

* need/forbid checks on the rebuilt ``src/smart_hub.cpp``, in the style of the
  other OS12 validators;
* a host-compiled routing check. The real rectangle functions (and the real
  ``hubTabBarLive`` predicate) are extracted from the rebuilt source and
  compiled with a stand-in display of 480x320 (landscape WS350) and 320x480
  (portrait / jc3248w535). For every sub-page under More and System, the
  centre and the four inner edge points of each bottom button must route to
  that button, not to the tab bar; and every stepper "-" / "+" drawn button
  must sit inside its own touch zone at the same five points.

Touch routing is modelled the way ``smartHubHandleTouch`` runs it: the tab bar
is hit-tested first (only where ``hubTabBarLive`` says so), then the page.
On sources without ``hubTabBarLive`` the tab bar is modelled as always live,
which is what the firmware did before this hotfix.
"""
from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import tempfile
from pathlib import Path


class ValidationError(RuntimeError):
    pass


def need(text: str, needle: str, label: str) -> None:
    if needle not in text:
        raise ValidationError(f"missing {label}: {needle}")


def forbid(text: str, needle: str, label: str) -> None:
    if needle in text:
        raise ValidationError(f"forbidden {label}: {needle}")


def read(path: Path) -> str:
    if not path.is_file():
        raise ValidationError(f"missing file: {path}")
    return path.read_text(encoding="utf-8")


def block(text: str, signature: str, required: bool = True) -> str:
    start = text.find(signature)
    if start < 0:
        if required:
            raise ValidationError(f"missing function: {signature}")
        return ""
    if text.find(signature, start + 1) >= 0:
        raise ValidationError(f"function defined more than once: {signature}")
    brace = text.find("{", start)
    depth = 0
    for i in range(brace, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    raise ValidationError(f"unterminated function: {signature}")


# Sub-pages whose bottom buttons are hubUi13BackRect / hubUi13ActionRect.
# (screen, g_ui12SettingsView, g_ui12SystemView, name)
SUB_PAGES = [
    ("SCREEN_HUB_MORE", 1, 0, "Display & Appearance"),
    ("SCREEN_HUB_MORE", 2, 0, "Sound & Media"),
    ("SCREEN_HUB_MORE", 3, 0, "Network"),
    ("SCREEN_HUB_MORE", 4, 0, "Printer & Power"),
    ("SCREEN_HUB_MORE", 5, 0, "After Print"),
    ("SCREEN_HUB_MORE", 6, 0, "Printer Alerts"),
    ("SCREEN_HUB_MORE", 7, 0, "Alert Signals"),
    ("SCREEN_HUB_MORE", 8, 0, "Power Options"),
    ("SCREEN_HUB_MORE", 9, 0, "Enable Auto-Off?"),
    ("SCREEN_HUB_MORE", 10, 0, "Media"),
    ("SCREEN_HUB_MORE", 11, 0, "Recorder"),
    ("SCREEN_HUB_MORE", 12, 0, "Video Viewer"),
    ("SCREEN_HUB_SYSTEM", 0, 0, "System"),
    ("SCREEN_HUB_SYSTEM", 0, 2, "Date & Time"),
    ("SCREEN_HUB_SYSTEM", 0, 3, "Software Update"),
    ("SCREEN_HUB_SYSTEM", 0, 4, "Diagnostics"),
    ("SCREEN_HUB_SYSTEM", 0, 5, "Install Workshop OS?"),
]

# Local Portal uses its own Back rectangle and has no action button.
PORTAL_PAGE = ("SCREEN_HUB_SYSTEM", 0, 1, "Local Portal")

# Stepper rows: (screen, settings view, system view, name, row)
STEPPERS = [
    ("SCREEN_HUB_MORE", 1, 0, "Display: Brightness", 0),
    ("SCREEN_HUB_MORE", 1, 0, "Display: Standby Brightness", 1),
    ("SCREEN_HUB_MORE", 5, 0, "After Print: Display Behavior", 0),
    ("SCREEN_HUB_MORE", 5, 0, "After Print: Finish Timeout", 1),
    ("SCREEN_HUB_MORE", 10, 0, "Media: Speaker", 0),
    ("SCREEN_HUB_MORE", 6, 0, "Printer Alerts: Severity", 1),
    ("SCREEN_HUB_MORE", 6, 0, "Printer Alerts: Presentation", 2),
    ("SCREEN_HUB_MORE", 8, 0, "Power Options: Auto-Off Delay", 0),
    ("SCREEN_HUB_SYSTEM", 0, 2, "Date & Time: Time Zone", 0),
    ("SCREEN_HUB_SYSTEM", 0, 2, "Date & Time: Date Format", 2),
]

# Pages that draw the tab bar, so its touch zones must stay live there.
TAB_BAR_PAGES = [
    ("SCREEN_HUB_HOME", 0, 0, "Home"),
    ("SCREEN_HUB_PRINTER", 0, 0, "Printer"),
    ("SCREEN_HUB_WORKSHOP", 0, 0, "Workshop"),
    ("SCREEN_HUB_MORE", 0, 0, "More"),
]

# Draw functions of pages that hide the tab bar.
NO_TAB_BAR_DRAWS = [
    "static void drawUi13Display()",
    "static void drawUi13AfterPrint()",
    "static void drawUi13Sound()",
    "static void drawOs12Media()",
    "static void drawOs12Recorder()",
    "static void drawOs12VideoViewer()",
    "static void drawUi13PrinterAlerts()",
    "static void drawUi13AlertSignals()",
    "static void drawUi13Network()",
    "static void drawUi13PrinterPower()",
    "static void drawUi13PowerOptions()",
    "static void drawUi13AutoOffConfirm()",
    "static void drawUi12PortalAccess()",
    "static void drawUi13DateTime()",
    "static void drawUi13SoftwareUpdate()",
    "static void drawUi13UpdateConfirm()",
    "static void drawUi13Diagnostics()",
]

EXTRACT = [
    "static HubRect hr(",
    "static bool hubLandscape()",
    "static int16_t hubNavH()",
    "static HubRect hubNavRect(uint8_t i)",
    "static HubRect hubUi13RowRect(uint8_t i)",
    "static HubRect hubUi13BackRect()",
    "static HubRect hubUi13ActionRect()",
    "static HubRect hubUi12SystemBackRect()",
]

OPTIONAL_STEPPER = [
    "static HubRect hubUi13StepperMinusButton(const HubRect& r)",
    "static HubRect hubUi13StepperPlusButton(const HubRect& r)",
    "static HubRect hubUi13StepperTouch(const HubRect& button,const HubRect& row)",
]

TOUCH_RECTS = [
    "static HubRect hubUi13MinusRect(uint8_t i)",
    "static HubRect hubUi13PlusRect(uint8_t i)",
]

# Pre-hotfix drawing geometry, used only when the shared helpers are absent so
# that the routing check reports the real mismatch on old sources.
LEGACY_STEPPER = """
static HubRect hubUi13StepperMinusButton(const HubRect& r){return hr(r.x+r.w-204,r.y+(r.h-44)/2,44,44);}
static HubRect hubUi13StepperPlusButton(const HubRect& r){return hr(r.x+r.w-44-OS12V_INSET,r.y+(r.h-44)/2,44,44);}
"""

LEGACY_TAB_BAR = "static bool hubTabBarLive(ScreenState){return true;}\n"

HARNESS_HEAD = """
#include <cstdint>
#include <cstdio>

enum ScreenState { SCREEN_HUB_HOME, SCREEN_HUB_PRINTER, SCREEN_HUB_WORKSHOP, SCREEN_HUB_MORE, SCREEN_HUB_SYSTEM, SCREEN_HUB_CUSTOM };

struct FakeTft {
  int16_t w, h;
  int16_t width() const { return w; }
  int16_t height() const { return h; }
};
static FakeTft tft = {480, 320};

static uint8_t g_ui12SettingsView = 0;
static uint8_t g_ui12SystemView = 0;
static bool g_toolsView = false;
static bool g_displayExperienceView = false;
static bool g_rotationPreviewMode = false;
static bool g_audioSettingsView = false;
static bool g_networkSettingsView = false;
"""

HARNESS_BODY = r"""
static int failures = 0;

static void setPage(uint8_t settings, uint8_t system) {
  g_ui12SettingsView = settings; g_ui12SystemView = system;
  g_toolsView = false; g_displayExperienceView = false; g_rotationPreviewMode = false;
  g_audioSettingsView = false; g_networkSettingsView = false;
}

static int tabAt(ScreenState s, int16_t x, int16_t y) {
  if (!hubTabBarLive(s)) return -1;
  for (uint8_t i = 0; i < 4; i++) if (hubNavRect(i).contains(x, y)) return i;
  return -1;
}

struct Pt { int16_t x, y; const char* where; };

static void points(const HubRect& r, Pt out[5]) {
  const int16_t cx = (int16_t)(r.x + r.w / 2), cy = (int16_t)(r.y + r.h / 2);
  out[0] = {cx, cy, "centre"};
  out[1] = {r.x, cy, "left edge"};
  out[2] = {(int16_t)(r.x + r.w - 1), cy, "right edge"};
  out[3] = {cx, r.y, "top edge"};
  out[4] = {cx, (int16_t)(r.y + r.h - 1), "bottom edge"};
}

static const char* kTabs[4] = {"Home", "Printer", "Workshop", "More"};

static void checkButton(const char* orient, ScreenState s, const char* page, const char* button,
                        const HubRect& drawn, const HubRect& touch, const HubRect* other) {
  if (drawn.w <= 0 || drawn.h <= 0) {
    std::printf("FAIL %s %s: %s has no rectangle\n", orient, page, button); failures++; return;
  }
  Pt p[5]; points(drawn, p);
  for (int i = 0; i < 5; i++) {
    const int tab = tabAt(s, p[i].x, p[i].y);
    if (tab >= 0) {
      std::printf("FAIL %s %s: %s %s (%d,%d) routes to the %s tab\n", orient, page, button, p[i].where, p[i].x, p[i].y, kTabs[tab]);
      failures++; continue;
    }
    if (!touch.contains(p[i].x, p[i].y)) {
      std::printf("FAIL %s %s: %s %s (%d,%d) is outside its touch zone [%d,%d %dx%d]\n", orient, page, button, p[i].where, p[i].x, p[i].y, touch.x, touch.y, touch.w, touch.h);
      failures++; continue;
    }
    if (other && other->contains(p[i].x, p[i].y)) {
      std::printf("FAIL %s %s: %s %s (%d,%d) is also inside the neighbouring control\n", orient, page, button, p[i].where, p[i].x, p[i].y);
      failures++;
    }
  }
}

static void checkStepperTouch(const char* orient, const char* page, const char* button,
                              const HubRect& drawn, const HubRect& touch) {
  // The touch zone lines up with the drawn button: it covers all of it and
  // extends at most 8 px past either side.
  if (touch.x > drawn.x || touch.x + touch.w < drawn.x + drawn.w ||
      drawn.x - touch.x > 8 || (touch.x + touch.w) - (drawn.x + drawn.w) > 8) {
    std::printf("FAIL %s %s: %s drawn x %d-%d, touch x %d-%d\n", orient, page, button,
                drawn.x, drawn.x + drawn.w - 1, touch.x, touch.x + touch.w - 1);
    failures++;
  }
}

int main() {
  const struct { int16_t w, h; const char* name; } orients[2] = {{480, 320, "landscape"}, {320, 480, "portrait"}};
  for (int o = 0; o < 2; o++) {
    tft.w = orients[o].w; tft.h = orients[o].h;
    const char* orient = orients[o].name;
    for (unsigned i = 0; i < sizeof(kTabBarPages) / sizeof(kTabBarPages[0]); i++) {
      setPage(kTabBarPages[i].settings, kTabBarPages[i].system);
      if (!hubTabBarLive(kTabBarPages[i].s)) {
        std::printf("FAIL %s %s: draws the tab bar but its touch zones are off\n", orient, kTabBarPages[i].name); failures++;
      }
    }
    for (unsigned i = 0; i < sizeof(kSubPages) / sizeof(kSubPages[0]); i++) {
      const PageSpec& pg = kSubPages[i];
      setPage(pg.settings, pg.system);
      const HubRect back = hubUi13BackRect(), action = hubUi13ActionRect();
      checkButton(orient, pg.s, pg.name, "Back", back, back, &action);
      checkButton(orient, pg.s, pg.name, "action button", action, action, &back);
    }
    {
      setPage(kPortal.settings, kPortal.system);
      const HubRect back = hubUi12SystemBackRect();
      checkButton(orient, kPortal.s, kPortal.name, "Back", back, back, nullptr);
    }
    for (unsigned i = 0; i < sizeof(kSteppers) / sizeof(kSteppers[0]); i++) {
      const StepperSpec& st = kSteppers[i];
      setPage(st.settings, st.system);
      const HubRect row = hubUi13RowRect(st.row);
      const HubRect minus = hubUi13StepperMinusButton(row), plus = hubUi13StepperPlusButton(row);
      const HubRect minusTouch = hubUi13MinusRect(st.row), plusTouch = hubUi13PlusRect(st.row);
      checkStepperTouch(orient, st.name, "\"-\"", minus, minusTouch);
      checkStepperTouch(orient, st.name, "\"+\"", plus, plusTouch);
      checkButton(orient, st.s, st.name, "\"-\"", minus, minusTouch, &plusTouch);
      checkButton(orient, st.s, st.name, "\"+\"", plus, plusTouch, &minusTouch);
    }
  }
  if (failures) { std::printf("%d touch routing failure(s)\n", failures); return 1; }
  std::printf("touch routing: all bottom buttons and steppers route to themselves in both orientations\n");
  return 0;
}
"""


def harness_tables() -> str:
    def page(spec) -> str:
        s, settings, system, name = spec
        return f'  {{{s}, {settings}, {system}, "{name}"}},\n'

    out = "struct PageSpec { ScreenState s; uint8_t settings; uint8_t system; const char* name; };\n"
    out += "struct StepperSpec { ScreenState s; uint8_t settings; uint8_t system; const char* name; uint8_t row; };\n"
    out += "static const PageSpec kSubPages[] = {\n" + "".join(page(p) for p in SUB_PAGES) + "};\n"
    out += "static const PageSpec kTabBarPages[] = {\n" + "".join(page(p) for p in TAB_BAR_PAGES) + "};\n"
    s, settings, system, name = PORTAL_PAGE
    out += f'static const PageSpec kPortal = {{{s}, {settings}, {system}, "{name}"}};\n'
    out += "static const StepperSpec kSteppers[] = {\n"
    for s, settings, system, name, row in STEPPERS:
        out += f'  {{{s}, {settings}, {system}, "{name}", {row}}},\n'
    out += "};\n"
    return out


def build_harness(hub: str, problems: list[str]) -> str:
    consts = re.findall(r"^static constexpr int16_t OS12\w*\s*=\s*[^;]+;", hub, re.M)
    if not any("OS12V_INSET" in c for c in consts):
        raise ValidationError("missing OS12 layout constants")
    parts = [HARNESS_HEAD, "\n".join(consts), "\n"]
    parts.append(block(hub, "struct HubRect {") + ";\n")
    for sig in EXTRACT:
        parts.append(block(hub, sig) + "\n")
    helpers = [block(hub, sig, required=False) for sig in OPTIONAL_STEPPER]
    if all(helpers):
        parts.extend(h + "\n" for h in helpers)
    else:
        problems.append("stepper buttons are not drawn and hit-tested from one shared rectangle")
        parts.append(LEGACY_STEPPER)
    for sig in TOUCH_RECTS:
        parts.append(block(hub, sig) + "\n")
    live = block(hub, "static bool hubTabBarLive(ScreenState cur)", required=False)
    if live:
        parts.append(live + "\n")
    else:
        problems.append("tab bar touch zones are live on pages that do not draw the tab bar (no hubTabBarLive)")
        parts.append(LEGACY_TAB_BAR)
    parts.append(harness_tables())
    parts.append(HARNESS_BODY)
    return "".join(parts)


def compiler() -> str:
    for name in ("g++", "c++", "clang++"):
        path = shutil.which(name)
        if path:
            return path
    raise ValidationError("no host C++ compiler (g++/c++/clang++) for the touch routing check")


def run_harness(source: str) -> tuple[bool, str]:
    with tempfile.TemporaryDirectory(prefix="os12-touch-") as tmp:
        src = Path(tmp) / "touch_routing.cpp"
        exe = Path(tmp) / "touch_routing"
        src.write_text(source, encoding="utf-8")
        cc = subprocess.run(
            [compiler(), "-std=c++11", "-Wall", "-Wextra", "-Werror",
             "-Wno-unused-variable", "-Wno-unused-function", str(src), "-o", str(exe)],
            text=True, capture_output=True)
        if cc.returncode != 0:
            raise ValidationError("touch routing harness failed to compile:\n" + cc.stderr + cc.stdout)
        run = subprocess.run([str(exe)], text=True, capture_output=True)
        return run.returncode == 0, run.stdout + run.stderr


def source_checks(hub: str, build: str, problems: list[str]) -> None:
    touch = block(hub, "bool smartHubHandleTouch(uint16_t rawX, uint16_t rawY, bool longPress)")
    if touch.count("hubNavRect(i).contains(x,y)") != 1:
        problems.append("smartHubHandleTouch must hit-test the tab bar exactly once")
    if "if(hubTabBarLive(cur))for(uint8_t i=0;i<4;i++)if(hubNavRect(i).contains(x,y))" not in touch:
        problems.append("tab bar hit test is not gated by hubTabBarLive(cur)")

    for sig in NO_TAB_BAR_DRAWS:
        if "uiBottomNav(" in block(hub, sig):
            problems.append(f"{sig} draws the tab bar, but hubTabBarLive treats it as hidden")
    more = block(hub, "static void drawMore(bool full)")
    if "uiBottomNav(3,nullptr)" not in more:
        problems.append("More root no longer draws the tab bar")
    for v in range(1, 13):
        if f"if(g_ui12SettingsView=={v})" not in more:
            problems.append(f"drawMore has no draw case for More view {v}")

    system = block(hub, "static void drawSystem(bool full)")
    for v, fn in ((1, "drawUi12PortalAccess"), (2, "drawUi13DateTime"), (3, "drawUi13SoftwareUpdate"),
                  (4, "drawUi13Diagnostics"), (5, "drawUi13UpdateConfirm")):
        if f"if(g_ui12SystemView=={v}){{{fn}();return;}}" not in system:
            problems.append(f"drawSystem has no draw case for System view {v} ({fn})")

    stepper = block(hub, "static void hubUi13StepperRow(")
    for needle in ("hubUi13StepperMinusButton(r)", "hubUi13StepperPlusButton(r)"):
        if needle not in stepper:
            problems.append(f"stepper row is not drawn from the shared rectangle: {needle}")

    update = block(hub, "static void drawUi13SoftwareUpdate()")
    if 'hubV1125Action(hubUi13ActionRect(),"Local Portal"' in update:
        problems.append('Software Update action button is labelled "Local Portal"')
    for label in ('"Check for update"', '"Install"'):
        if label not in update:
            problems.append(f"Software Update action button never says {label}")

    # The portal page must keep showing the access code.
    portal = block(hub, "static void drawUi12PortalAccess()")
    if "securityPortalCode()" not in portal:
        problems.append("Local Portal page no longer shows the access code")

    if "#define WORKSHOP_OS12_TOUCH_HOTFIX 1" not in build:
        problems.append("missing build marker WORKSHOP_OS12_TOUCH_HOTFIX")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True, help="reconstructed firmware tree")
    args = ap.parse_args()
    repo = Path(args.repo).resolve()
    try:
        hub = read(repo / "src" / "smart_hub.cpp")
        build = read(repo / "include" / "smart_home_build.h")
        problems: list[str] = []
        source_checks(hub, build, problems)
        ok, output = run_harness(build_harness(hub, problems))
        print(output.rstrip())
        if not ok:
            problems.append("touch routing check failed (see above)")
        if problems:
            raise ValidationError("\n  - " + "\n  - ".join(problems))
    except ValidationError as exc:
        print(f"FAIL: OS12 touch hotfix validation: {exc}")
        return 1
    print("OS12 touch hotfix validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
