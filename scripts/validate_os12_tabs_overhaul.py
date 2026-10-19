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
import re
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
    need(block(hub, "static void wtTextOn("), "if (!wsm::drawsValueText(text)) return;", "empty card text draws nothing")
    need(block(hub, "static void wtText("), "wtTextOn(", "card text goes through the empty-value guard")
    forbid(fragment, '"—"', "em dash drawn on the tabs")
    # Cross-links from Home come back to Home.
    need(hub, "wsOpenFrom(wsm::PageId::LocalPortal, 0);", "Home -> Local Portal returns to Home")
    need(block(hub, "static bool wsMoreTouch(int16_t x, int16_t y, bool longPress)"),
         "else if (g_wsReturnTab >= 0 && p.level == 1) wsTab((uint8_t)g_wsReturnTab);", "Back returns to the tab")


def validate_printer(hub: str, fragment: str) -> None:
    need(block(hub, "static void drawPrinter(bool full)"), "wtDrawPrinter(full);", "drawPrinter hands Printer to the tabs")
    for gone in ("hubPrinterActionRect", "hubV1125PrinterModeRect", "hubV1125ModeTabs(", "hubV1125TelemetryColumn", "hubV1125AmsSlot"):
        forbid(hub, gone, "12.0 Printer geometry or widget")
    draw = block(hub, "static void wtDrawPrinter(bool full)")
    ordered(draw, ["wtDrawHeader(", "wtDrawSegments(", "wtl::itemRect(", "uiBottomNav(1, nullptr);"], "Printer draws header, segments, items, tab bar")
    # Plain words on AMS (no 12.0 jargon footer); AMS and Status are read-only.
    for jargon in ("TELEMETRY", "authoritative in Filament Inventory"):
        forbid(fragment, jargon, "jargon on Printer")
    touch = block(hub, "static bool wtPrinterTouch(int16_t x, int16_t y, bool longPress)")
    need(touch, "if (id != wtl::View::PrinterControl) return true;  // Status and AMS are read-only", "read-only Status and AMS")
    # The only printer commands the tabs send: light, pause/resume, and the
    # hold-guarded Stop. Power goes through the existing confirm screen.
    commands = set(re.findall(r"workshop::platform::PrinterCommand::(\w+)", fragment))
    if commands != {"Pause", "Resume", "ChamberLightOn", "ChamberLightOff", "Stop"}:
        raise ValidationError(f"unexpected printer commands on the tabs: {sorted(commands)}")
    if hub.count("workshop::platform::PrinterCommand::Stop") != 1:
        raise ValidationError("Stop must be dispatched from exactly one place")
    stop_case = touch[touch.find("case wtl::ItemId::ControlStop:"):]
    stop_case = stop_case[:stop_case.find("default:")]
    ordered(stop_case, ["if (!c.stopEnabled)", "if (longPress && stopHeld) {",
                        "workshopPlatformDispatchPrinterCommand(slot, workshop::platform::PrinterCommand::Stop, true)"],
            "Stop needs a long press that started and stayed on the Stop button, with the confirm flag")
    need(touch, "const bool stopHeld = wtStopHoldConsume();", "Stop hold state read for every press")
    track = block(hub, "static bool wtStopHoldTrack(int16_t x, int16_t y, wsm::Rect& drawn)")
    need(track, "if (!g_wtStopHoldStarted) { g_wtStopHoldStarted = true; g_wtStopHoldValid = on; }", "hold must start on Stop")
    need(track, "else if (!on) g_wtStopHoldValid = false;", "hold must stay on Stop")
    need(track, "wtControls(w).stopEnabled", "hold only counts while Stop is live")
    hold = block(hub, "void smartHubUpdateHoldProgress(uint16_t rawX, uint16_t rawY, uint32_t holdMs)")
    need(hold, "if(wtStopHoldTrack(x,y,stop))", "hold progress follows the Stop tracker")
    need(hold, "wtDrawStopHold(", "hold progress drawn over the Stop button")
    need(fragment, "if (powerConfirmOpenForSlot(slot)) wsClick();", "printer power asks first (existing confirm screen)")
    forbid(fragment, "tasmotaSetPower", "direct plug switching from the tabs")
    # Pause/Resume is the primary action; Stop is outlined, never filled red.
    stop_draw = block(hub, "static void wtDrawStop(const wsm::Screen& s, const wsm::Rect& row, const WtControls& c)")
    forbid(stop_draw, "fillRoundRect(b.x, b.y, b.w, b.h, 10, OS12V_RED)", "Stop drawn as a filled red button")
    need(block(hub, "static void wtDrawPrimary(const wsm::Rect& row, const WtControls& c)"), "OS12V_ACCENT", "Pause is the filled primary")


def validate_workshop(hub: str, fragment: str) -> None:
    need(block(hub, "static void drawWorkshop(bool full)"), "wtDrawWorkshop(full);", "drawWorkshop hands Workshop to the tabs")
    for gone in ("hubOs12WorkshopActionRect", "hubOs12WorkshopSetupRect", "Set Up Inventory"):
        forbid(hub, gone, "12.0 Workshop geometry or giant set-up button")
    draw = block(hub, "static void wtDrawWorkshop(bool full)")
    ordered(draw, ["wtDrawHeader(", "wtl::itemRect(", "wsDrawRowBody(", "uiBottomNav(2, nullptr);"], "Workshop draws header, rows, tab bar")
    # Useful without inventory: the timer and the note live on Workshop, and
    # set-up is one row that says where to go.
    rows = block(hub, "static void wtWorkshopRow(wtl::ItemId id, const WorkshopInventoryRuntimeSnapshot& inv, WsRowView& v)")
    for needle in ('"Not connected · set up"', '"Local Portal > More > Filament Inventory"', '"Start"', '"Cancel"',
                   "g_workshopNote", "wtTimerLength()"):
        need(rows, needle, "Workshop rows")
    touch = block(hub, "static bool wtWorkshopTouch(int16_t x, int16_t y)")
    need(touch, "wsOpenFrom(wsm::PageId::LocalPortal, 2);", "Workshop -> Local Portal returns to Workshop")
    need(touch, "startWorkshopTimer(wtTimerLength());", "start the workshop timer on the device")
    need(touch, "clearWorkshopTimer();", "cancel the workshop timer on the device")
    need(touch, "if (row.reason) wsToast(row.reason);", "disabled rows say why")
    need(block(hub, "static void wtStepTimer(int dir)"), "g_timerPresets[i]", "timer lengths are the portal presets")
    for prompt in ("hubStatusTokenPromptDraw", "hubCodeTokenPromptDraw"):
        body = block(hub, f"static bool {prompt}(bool force)")
        need(body, "wsm::dialogCard(s)", f"{prompt} on the More dialog card")
        forbid(body, "drawHeader(", f"{prompt} uses the 12.0 header")
        forbid(body, "uiBottomNav(", f"{prompt} draws the tab bar under a modal prompt")
    need(hub, "static HubRect hubStatusTokenCancelRect() { return wsHub(wsm::dialogCancelRect(wsScreen())); }",
         "status prompt Cancel inside the card")
    need(hub, "static HubRect hubStatusTokenAllowRect() { return wsHub(wsm::dialogConfirmRect(wsScreen())); }",
         "status prompt Allow inside the card")
    forbid(hub, "(int16_t)(H-68)", "status prompt buttons on the tab-bar strip")


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
                    "if(cur==SCREEN_HUB_PRINTER)return wtPrinterTouch(x,y,longPress);",
                    "if(cur==SCREEN_HUB_WORKSHOP)return wtWorkshopTouch(x,y);",
                    "hubNavRect(i).contains(x,y)"], "touch hand-off order")
    # Geometry only from the shared layout in the new code.
    for needle in ("hubRc2HitRef", "hubHomeRect", "hubPrinterActionRect", "hubV1125PrinterModeRect", " hr(", "(hr(", "=hr("):
        forbid(fragment, needle, "hand-placed geometry in the tab pages")
    need(block(hub, "static void wtTab(uint8_t i)"), "wsOpen(wsm::PageId::Root);", "More tab opens the More root")
    validate_home(hub, fragment)
    validate_printer(hub, fragment)
    validate_workshop(hub, fragment)
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
