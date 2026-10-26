#!/usr/bin/env python3
"""Validate Workshop OS 12.3.9 WS350 glanceability and legibility.

String and behaviour contracts on the finished touchscreen tree (after
apply_workshop_os12_glance_legibility.py), plus the two host-compiled layout
tests that hold the new geometry:

- tests/workshop_os12_tabs_layout_smoke.cpp: the running-print card layout
  (tabs::printCardLayout) in both orientations, and the done-at anchor
  (tabs::doneAtEpoch);
- tests/workshop_os12_more_layout_smoke.cpp: Printer > Camera without a
  control row (more::cameraVideoRect, cameraPauseRect and the camera hit
  test), with a full-screen scan in both orientations.

It also checks that what 12.3.9 must not change is still there: Stop's hold
guard, the changed-row frame push, the touch-down outline and slide-off
cancel, the capture catalog and the X2D overlay anchors.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UI = ROOT / "firmware" / "platform" / "ui"
TESTS = (ROOT / "tests" / "workshop_os12_tabs_layout_smoke.cpp", ROOT / "tests" / "workshop_os12_more_layout_smoke.cpp")


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


def run_host_tests() -> list[str]:
    out = []
    with tempfile.TemporaryDirectory(prefix="os12-glance-") as td:
        for test in TESTS:
            binary = Path(td) / test.stem
            subprocess.run(["c++", "-std=c++11", "-O1", "-Wall", "-Wextra", "-Werror", "-pedantic", str(test), "-o", str(binary)],
                           check=True, cwd=ROOT)
            result = subprocess.run([str(binary)], check=True, cwd=ROOT, capture_output=True, text=True)
            out.append(result.stdout.strip().splitlines()[-1])
    return out


def validate_rows(hub: str) -> None:
    """Values, reasons, button labels and toasts are 14 px when they fit."""
    need(block(hub, "static FontID wsValueFont(const char* text, int16_t w)"), "wsFitFont(text, w, FONT_BODY, FONT_SMALL)",
         "14 px value font with a 10 px fallback")
    body = block(hub, "static void wsDrawRowBody(const wsm::Screen& s, wsm::RowKind kind, const char* labelText, const WsRowView& v,")
    if len(re.findall(r"wsDrawRowValue\([^;]*wsValueFont\(", body, re.S)) < 7:
        raise ValidationError("every row value slot must pick its font with wsValueFont")
    for old in ("FONT_SMALL, MR_DATUM, valueColor", "FONT_SMALL, MC_DATUM, valueColor"):
        forbid(body, old, "a row value fixed at 10 px")
    need(body, "const uint16_t valueColor = v.enabled ? v.valueColor : OS12V_MUTED;", "disabled reasons muted, not amber")
    forbid(body, "v.enabled ? v.valueColor : OS12V_AMBER", "disabled reasons in amber")
    need(body, "on ? OS12V_ACCENT : OS12V_MUTED", "an off switch keeps a visible track")
    need(block(hub, "static void wsDrawButton(const wsm::Rect& r, const char* label, bool enabled, bool primary, uint16_t rowBg)"),
         "wsValueFont(label, r.w - 12)", "14 px button labels")
    need(block(hub, "static void wsDrawHeader(const wsm::Screen& s, const wsm::PageSpec& p)"),
         "wsFitFont(g_wsToast, toastW, FONT_BODY, FONT_SMALL)", "14 px toasts on More pages")
    need(block(hub, "static void wtDrawHeader("), "wsFitFont(g_wsToast, t.right() - titleX, FONT_BODY, FONT_SMALL)", "14 px toasts on the tabs")
    tray = block(hub, "static void wtDrawTray(const wsm::Screen& s, const wsm::Rect& row, const WtTray& t)")
    need(tray, 'uiDrawFit("In use", right, mid, 60, FONT_BODY,', "14 px In use")
    need(tray, "wsValueFont(t.value,", "14 px tray values")
    for gone, label in (('"No smart plug for this printer"', "a reason that did not fit"), ('"%u C"', "a temperature without a degree sign")):
        forbid(hub, gone, label)
    need(hub, '"No smart plug"', "short smart-plug reason")
    if hub.count('"%u°C"') < 4:
        raise ValidationError("cooldown and gauge scales must say °C")
    extra = block(hub, "static const char* wtHomeExtra(WsRowView& v)")
    # 12.4.0: Home's bottom row is Local AI's top card (filament moved to the Local AI tab).
    need(extra, "wtHomeSummary(others)", "Home's Local AI row shows the card that matters most")
    forbid(extra, "Not connected · set up in Workshop", "the 12.3.8 amber set-up line")
    stop = block(hub, "static void wtDrawStop(const wsm::Screen& s, const wsm::Rect& row, const WtControls& c)")
    forbid(stop, "OS12V_AMBER", "the Stop hint in amber")


def validate_print_status(hub: str) -> None:
    """Home and Printer: 48 px percentage, time left and one done-at time."""
    big = block(hub, "static void wtDrawBigPercent(const wsm::Rect& r, uint8_t pct, uint16_t color, uint16_t bg)")
    for needle in ("setFont(tft, FONT_NONE);", "tft.setTextFont(6);", 'uiDrawFit("%",'):
        need(big, needle, "48 px percentage")
    run = block(hub, "static void wtDrawRunningPrint(const wtl::PrintCardLayout& L, const WtPrint& w)")
    for needle in ("wtDrawBigPercent(L.percent,", '"%s left"', '"Paused"', "wtDoneAtText(w, done, sizeof(done))",
                   'snprintf(line, sizeof(line), "Done %s", done);', "wtDrawProgress(L.bar.x, L.bar.y, L.bar.w,",
                   "wsFitFont(left, L.left.w, FONT_LARGE, FONT_BODY)"):
        need(run, needle, "running-print card")
    home = block(hub, "static void wtDrawHomeCard(const wsm::Screen& s, const wsm::Rect& r, const WtPrint& w)")
    need(home, "wtl::printCardLayout(s, r, true)", "Home card on the shared layout")
    need(home, "wtDrawRunningPrint(L, w);", "Home card draws the running print")
    need(home, '"Layer %u of %u"', "Home detail line")
    printer = block(hub, "static void wtDrawPrinterCard(const wsm::Screen& s, const wsm::Rect& r, const WtPrint& w)")
    need(printer, "wtl::printCardLayout(s, r, false)", "Printer card on the shared layout")
    need(printer, "wtDrawRunningPrint(L, w);", "Printer card draws the running print")
    forbid(printer, 'w.paused ? "Paused" : "Printing"', "the Printing headline the chip already shows")
    done = block(hub, "static bool wtDoneAtText(const WtPrint& w, char* out, size_t len)")
    need(done, "wtl::doneAtEpoch(g_wtDoneAt, w.s->remainingMinutes, (long)now)", "one done-at anchor")
    need(done, "wtClockOf(out, len, (time_t)at)", "done-at in local time, 12/24 h")
    forbid(hub, "wtClockIn(", "a per-frame done-at time")
    need(block(hub, "static wtl::CalmStatus wtCalmStatus(const WtPrint& w, char* doneAt, size_t doneLen, uint16_t& color)"),
         "wtDoneAtText(w, doneAt, doneLen)", "the calm screen shares the done-at time")
    need(block(hub, "static void wtDrawCalm(const WtPrint& w)"), "wsFitFont(status, maxW, FONT_LARGE, FONT_BODY)", "19 px calm status")


def validate_camera(hub: str, backend: str) -> None:
    need(block(hub, "static bool wsCameraView(wsm::PageId id)"), "g_wsCameraMode && id == wsm::PageId::VideoTest", "camera view predicate")
    need(block(hub, "static void wsDrawVideoControls(const wsm::Screen& s, const wsm::PageSpec& p)"), "if (wsCameraView(p.id)) return;",
         "no control row on the camera page")
    header = block(hub, "static void wsDrawHeader(const wsm::Screen& s, const wsm::PageSpec& p)")
    need(header, "wsm::cameraTitleRect(s)", "camera title beside Pause")
    need(header, "wsDrawButton(wsm::cameraPauseDrawRect(s),", "camera Pause in the header")
    touch = block(hub, "static bool wsMoreTouch(int16_t x, int16_t y, bool longPress)")
    need(touch, "wsm::hitTest(s, p.id, g_wsScroll, g_wsDialog != WsDialog::None, x, y, wsCameraView(p.id))", "camera hit test")
    need(touch, "wsRowTap(wsm::RowId::VideoPause, wsm::Part::Whole);", "header Pause runs the pause row's action")
    need(block(hub, "static bool wsMorePressRect(int16_t x, int16_t y, wsm::Rect& out)"),
         "wsm::hitTest(s, p.id, g_wsScroll, g_wsDialog != WsDialog::None, x, y, wsCameraView(p.id))", "camera pressed outline")
    need(block(hub, "static void wsDrawVideoIdle(const wsm::Screen& s)"),
         "wsm::videoRect(s, wsm::PageId::VideoTest, g_wsCameraMode)", "capture placeholder in the camera area")
    need(block(hub, "static void wsMoreDraw(bool full)"), "wsm::videoRect(s, p.id, wsCameraView(p.id))", "direct-video chrome around the camera area")
    need(block(hub, "bool smartHubCameraViewActive()"), "return wsCameraView(g_wsPage);", "camera mode for the media backend")
    area = block(backend, "static void ws350VideoArea(int16_t& x, int16_t& y, int16_t& w, int16_t& h)")
    need(area, "::smartHubCameraViewActive()", "the backend sizes frames to the camera area")
    need(backend, "extern bool smartHubCameraViewActive();", "backend declaration")


def validate_kept(hub: str, web: str, layout: str) -> None:
    """What 12.3.9 must not change."""
    if hub.count("workshop::platform::PrinterCommand::Stop") != 1:
        raise ValidationError("Stop must be dispatched from exactly one place")
    need(block(hub, "static bool wtPrinterTouch(int16_t x, int16_t y, bool longPress)"), "if (longPress && stopHeld) {", "Stop's hold guard")
    need(block(hub, "static void hubCommitFrame()"), "workshop::ui::frame::diffBands(", "changed-row frame push")
    need(hub, "static void hubPaintPressed(lgfx::LovyanGFX* dst)", "touch-down outline")
    need(hub, "wpress::sameBox(", "a press acts only on the target it went down on")
    catalog = web[web.find('static const char kCatalog[] = R"json('):web.find(')json";')]
    ids = re.findall(r'\{"id":"([a-z0-9-]+)"', catalog)
    want = ["home", "printer", "printer-ams", "printer-control", "workshop", "lab-judge", "lab-judge-send", "more", "settings-printer-power", "hardware-auto-off",
            "settings-network", "system-date-time", "settings-display", "display-clock", "display-gauges", "settings-sounds",
            "display-alerts", "hardware-led", "media-video", "system-portal", "system-update", "system-diagnostics"]
    if ids != want:
        raise ValidationError(f"capture view ids changed: {ids}")
    need(catalog, '{"id":"system-portal","label":"Local Portal","group":"More","sensitive":"portal-code"}', "portal capture redaction flag")
    # The X2D development overlays anchor on these (apply_workshop_os12_x2d_viewer_polish.py).
    need(hub, 'static const char kWsCameraSource[] = "printer-camera";', "X2D camera source anchor")
    need(hub, '"The printer needs LAN mode and its access code."', "X2D camera hint anchor")
    need(layout, '{RowId::VideoTestNav, RowKind::Nav, "Video test", PageId::VideoTest}', "X2D row label anchor")
    need(layout, 'PageLayout::Video, "Video test",', "X2D page title anchor")


def validate(repo: Path) -> list[str]:
    need(read(repo / "include" / "smart_home_build.h"), "#define WORKSHOP_OS12_GLANCE_LEGIBILITY 1", "build marker")
    for name in ("more_layout.hpp", "tabs_layout.hpp"):
        if read(repo / "include" / f"workshop_{name}") != read(UI / name):
            raise ValidationError(f"installed include/workshop_{name} differs from firmware/platform/ui/{name}")
    hub = read(repo / "src" / "smart_hub.cpp")
    for frag in ("more_pages.cppfrag", "tabs_pages.cppfrag"):
        need(hub, read(UI / frag).strip().splitlines()[-1], f"{frag} installed")
    validate_rows(hub)
    validate_print_status(hub)
    validate_camera(hub, read(repo / "src" / "ws350_media_backend.cpp"))
    validate_kept(hub, read(repo / "src" / "web_server.cpp"), read(repo / "include" / "workshop_more_layout.hpp"))
    return run_host_tests()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    args = ap.parse_args()
    try:
        summary = validate(Path(args.repo).resolve())
    except (ValidationError, subprocess.CalledProcessError) as exc:
        raise SystemExit(f"FAIL: {exc}")
    for line in summary:
        print(line)
    print("PASS: 12.3.9 glance and legibility: 48 px print percentage with time left and one done-at time, 14 px values and "
          "toasts, muted not-set-up reasons, camera picture to the tab bar; Stop guard, frame push, outline, capture ids kept")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
