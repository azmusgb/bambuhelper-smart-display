#!/usr/bin/env python3
"""Validate the WS350 Home, Printer and Workshop tabs (Workshop OS 12.3.x).

String and behaviour contracts on the rebuilt src/smart_hub.cpp, plus the
host-compiled geometry and touch-routing test
tests/workshop_os12_tabs_layout_smoke.cpp (both orientations, every view and
state, every control at its centre and edges, and a full-screen scan for taps
that land outside a drawn control).
"""
from __future__ import annotations

import argparse
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LAYOUT = ROOT / "firmware/platform/ui/tabs_layout.hpp"
PAGES = ROOT / "firmware/platform/ui/tabs_pages.cppfrag"
TEST = ROOT / "tests/workshop_os12_tabs_layout_smoke.cpp"


class ValidationError(RuntimeError):
    pass


def read(path: Path) -> str:
    if not path.is_file():
        raise ValidationError(f"missing file: {path}")
    return path.read_text(encoding="utf-8")


def need(text: str, needle: str, label: str) -> None:
    if needle not in text:
        raise ValidationError(f"missing {label}: {needle}")


def forbid(text: str, needle: str, label: str) -> None:
    if needle in text:
        raise ValidationError(f"forbidden {label}: {needle}")


def ordered(text: str, needles: list[str], label: str) -> None:
    at = -1
    for needle in needles:
        i = text.find(needle)
        if i < 0 or i < at:
            raise ValidationError(f"{label}: {needle!r} out of order or missing")
        at = i


def block(text: str, signature: str) -> str:
    """Body of the function defined (not just declared) at `signature`."""
    start = text.find(signature)
    while start >= 0 and text[start + len(signature):].lstrip().startswith(";"):
        start = text.find(signature, start + 1)
    if start < 0:
        raise ValidationError(f"missing function: {signature}")
    brace = text.find("{", start + len(signature))
    depth = 0
    for i in range(brace, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    raise ValidationError(f"unterminated function: {signature}")


def run_host_test() -> str:
    with tempfile.TemporaryDirectory(prefix="os12-tabs-layout-") as td:
        binary = Path(td) / "tabs-layout-smoke"
        subprocess.run(["c++", "-std=c++11", "-O1", "-Wall", "-Wextra", "-Werror", "-pedantic",
                        str(TEST), "-o", str(binary)], check=True, cwd=ROOT)
        result = subprocess.run([str(binary)], check=True, cwd=ROOT, capture_output=True, text=True)
        return result.stdout.strip()


def validate_home(hub: str, fragment: str) -> None:
    # drawHome hands Home to the new page; the calm idle screen is kept.
    need(block(hub, "static void drawHome(bool full)"), "wtDrawHome(full);", "drawHome hands Home to the tabs")
    home = block(hub, "static void wtDrawHome(bool full)")
    ordered(home, ["drawAmbientHome(", "wtDrawHeader(", "wtl::itemRect(", "uiBottomNav(0, nullptr);"],
            "Home draws header, items and tab bar")
    # No invisible zones: the 12.0 Home rectangles are gone, Home touch goes
    # through the shared hit test, and only drawn items react.
    forbid(hub, "hubHomeRect", "12.0 Home zones")
    touch_fn = block(hub, "static bool wtHomeTouch(int16_t x, int16_t y)")
    ordered(touch_fn, ["if (g_ambientActive)", "wtl::hitTest(s, wtl::View::Home"], "calm screen wakes before any hit test")
    need(touch_fn, "if (h.kind != wtl::HitKind::Item) return true;", "untargeted Home taps do nothing")
    # Plain words, Title Case: no ALL-CAPS card labels.
    for caps in ('"PRINTER"', '"FILAMENT"', '"PRINTING"', '"READY"', '"OFFLINE"', '"ATTENTION"', '"SETUP"'):
        forbid(fragment, caps, "ALL-CAPS label on the tabs")
    # Big status: percent, time left, done-at clock time and file name.
    card = block(hub, "static void wtDrawHomeCard(const wsm::Screen& s, const wsm::Rect& r, const WtPrint& w)")
    for needle in ("jobDisplayName(st)", "FONT_XLARGE", "wtDurationText(", "wtClockIn(", '"Done %s"', "wtDrawProgress("):
        need(card, needle, "Home print status")
    need(block(hub, "static bool wtClockOf(char* out, size_t len, time_t at)"), "netSettings.use24h", "done-at follows the 12/24 h setting")
    need(block(hub, "static bool wtClockOf(char* out, size_t len, time_t at)"), "localtime_r(", "done-at in local time")
    # Honest empty states.
    need(card, '"No printer set up"', "no-printer state")
    need(card, '"Printer offline"', "offline state")
    need(block(hub, "static const char* wtHomeExtra(WsRowView& v)"), '"Not connected · set up in Workshop"', "inventory empty state")
    # Empty values draw nothing (the WS350 font shows the fitter's em dash as "|").
    need(block(hub, "static void wtText("), "if (!wsm::drawsValueText(text)) return;", "empty card text draws nothing")
    forbid(fragment, '"—"', "em dash drawn on the tabs")
    # Cross-links from Home come back to Home.
    need(hub, "wsOpenFrom(wsm::PageId::LocalPortal, 0);", "Home -> Local Portal returns to Home")
    need(block(hub, "static bool wsMoreTouch(int16_t x, int16_t y, bool longPress)"),
         "else if (g_wsReturnTab >= 0 && p.level == 1) wsTab((uint8_t)g_wsReturnTab);", "Back returns to the tab")


def validate(repo: Path) -> str:
    build = read(repo / "include/smart_home_build.h")
    hub = read(repo / "src/smart_hub.cpp")
    need(build, "#define WORKSHOP_OS12_TABS_OVERHAUL 1", "build marker")
    if read(repo / "include/workshop_tabs_layout.hpp") != read(LAYOUT):
        raise ValidationError("installed include/workshop_tabs_layout.hpp differs from firmware/platform/ui/tabs_layout.hpp")
    ordered(hub, ['#include "workshop_more_layout.hpp"', '#include "workshop_tabs_layout.hpp"'], "layout includes")
    fragment = read(PAGES)
    need(hub, fragment.strip().splitlines()[-1], "tab pages fragment")

    # Touch: the Local AI prompts first, then the More pages, then the tabs,
    # each through its own shared hit test; all before the 12.0 tab-bar code.
    touch = block(hub, "bool smartHubHandleTouch(uint16_t rawX, uint16_t rawY, bool longPress)")
    ordered(touch, ["if(hubStatusTokenPromptTouch(x,y))return true;", "if(hubCodeTokenPromptTouch(x,y))return true;",
                    "return wsMoreTouch(x,y,longPress);", "if(cur==SCREEN_HUB_HOME)return wtHomeTouch(x,y);",
                    "hubNavRect(i).contains(x,y)"], "touch hand-off order")
    # Geometry only from the shared layout in the new code.
    for needle in ("hubRc2HitRef", "hubHomeRect", "hubPrinterActionRect", "hubV1125PrinterModeRect", " hr(", "(hr(", "=hr("):
        forbid(fragment, needle, "hand-placed geometry in the tab pages")
    need(block(hub, "static void wtTab(uint8_t i)"), "wsOpen(wsm::PageId::Root);", "More tab opens the More root")
    validate_home(hub, fragment)
    return run_host_test()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    args = ap.parse_args()
    try:
        summary = validate(Path(args.repo).resolve())
    except (ValidationError, subprocess.CalledProcessError) as exc:
        raise SystemExit(f"FAIL: {exc}")
    print(summary)
    print("PASS: Home, Printer and Workshop tabs on the shared layout; geometry and touch routing hold in 480x320 and 320x480")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
