#!/usr/bin/env python3
"""Validate the WS350 More/System overhaul (Workshop OS 12.1.x).

String and behaviour contracts on the rebuilt src/smart_hub.cpp, plus the
host-compiled geometry and touch-routing test
tests/workshop_os12_more_layout_smoke.cpp (both orientations, every control
on every page, centre and edges).
"""
from __future__ import annotations

import argparse
import subprocess
import tempfile
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LAYOUT = ROOT / "firmware/platform/ui/more_layout.hpp"
PAGES = ROOT / "firmware/platform/ui/more_pages.cppfrag"
TEST = ROOT / "tests/workshop_os12_more_layout_smoke.cpp"

# Catalog ids of pages that no longer exist. /hub/show may still accept some
# of them as aliases, but captures must not list them.
REMOVED_VIEW_IDS = (
    "system", "system-network", "system-time-locale", "system-network-address",
    "system-network-review", "hardware-power", "hardware-cooldown",
    "media", "media-lab", "display-quick", "display-schedule", "display-behavior", "display-visual",
    "display-signals", "display-theme", "display-gauge-colors", "display-gauge-scales",
    "display-gauge-behavior", "display-glow", "display-layout", "display-extras",
    "hardware-sound", "hardware-finish", "hardware-error", "tools", "custom",
)

# Renderers the More pages replaced.
REPLACED_RENDERERS = (
    "drawUi13Network", "drawUi13PrinterPower", "drawUi13PowerOptions", "drawUi13AutoOffConfirm",
    "drawUi12PortalAccess", "drawUi13DateTime", "drawUi13SoftwareUpdate", "drawUi13UpdateConfirm",
    "drawUi13Diagnostics", "drawNetworkEssentials", "drawUi13Display", "drawUi13AfterPrint", "drawUi13Sound",
    "drawOs12Media", "drawOs12VideoViewer", "drawOs12Recorder", "drawUi13PrinterAlerts", "drawUi13AlertSignals",
    "drawDisplayExperience", "drawAudioSettings", "drawTools", "drawCustom", "drawUi12Experience",
    "drawUi12PrinterConnection", "drawUi12SoftwareUpdate", "drawWidgetCard",
)


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


def layout_rows(layout: str) -> dict[str, list[tuple[str, str]]]:
    """Row (id, kind) lists per row-table name, e.g. kNetworkRows."""
    tables: dict[str, list[tuple[str, str]]] = {}
    for name, body in re.findall(r"static const RowSpec (k\w+Rows)\[\] = \{(.*?)\n\};", layout, re.S):
        tables[name] = re.findall(r"\{RowId::(\w+), RowKind::(\w+),", body)
    return tables


def live_page_rows(layout: str, fragment: str) -> list[tuple[str, str, str]]:
    """(page, row id, kind) for every row of every page the fragment draws."""
    start = fragment.find("static bool wsPageLive(wsm::PageId id)")
    pending = set(re.findall(r"case wsm::PageId::(\w+):", fragment[start:fragment.find("\n}\n", start)]))
    tables = layout_rows(layout)
    rows = []
    for page, table in re.findall(r"\{PageId::(\w+), PageId::\w+, \d, PageLayout::\w+, \"[^\"]*\", \"[^\"]*\", \"[^\"]*\", WS_ROWS\((\w+)\)\}", layout):
        if page in pending:
            continue
        for row, kind in tables[table]:
            rows.append((page, row, kind))
    if not rows:
        raise ValidationError("could not read live page rows")
    return rows


def run_host_test() -> str:
    with tempfile.TemporaryDirectory(prefix="os12-more-layout-") as td:
        binary = Path(td) / "more-layout-smoke"
        subprocess.run(["c++", "-std=c++11", "-Wall", "-Wextra", "-Werror", "-pedantic",
                        str(TEST), "-o", str(binary)], check=True, cwd=ROOT)
        result = subprocess.run([str(binary)], check=True, cwd=ROOT, capture_output=True, text=True)
        return result.stdout.strip()


def validate(repo: Path) -> str:
    build = read(repo / "include/smart_home_build.h")
    hub = read(repo / "src/smart_hub.cpp")
    installed = read(repo / "include/workshop_more_layout.hpp")

    need(build, "#define WORKSHOP_OS12_MORE_OVERHAUL 1", "build marker")
    if installed != read(LAYOUT):
        raise ValidationError("installed include/workshop_more_layout.hpp differs from firmware/platform/ui/more_layout.hpp")
    need(hub, '#include "workshop_more_layout.hpp"', "layout include")
    layout = read(LAYOUT)
    fragment = read(PAGES)
    web = read(repo / "src/web_server.cpp")

    # The More pages are inserted whole and own drawing and touch.
    need(hub, fragment.strip().splitlines()[-1], "More pages fragment")
    more = block(hub, "static void drawMore(bool full)")
    system = block(hub, "static void drawSystem(bool full)")
    need(more, "wsMoreDraw(full);", "drawMore hands moved pages to the More pages")
    need(system, "wsMoreDraw(full);", "drawSystem hands System to the More pages")
    touch = block(hub, "bool smartHubHandleTouch(uint16_t rawX, uint16_t rawY, bool longPress)")
    handoff = touch.find("return wsMoreTouch(x,y,longPress);")
    if handoff < 0 or handoff > touch.find("hubNavRect(i).contains(x,y)"):
        raise ValidationError("More pages must take their touch before the 12.0 tab-bar hit test")
    nav = block(hub, "static HubRect hubNavRect(uint8_t i)")
    need(nav, "workshop::ui::more::tabRect(", "tab bar rectangles come from the shared layout")

    # Tab bar drawn on every More page and hit-tested first on every page.
    draw = block(hub, "static void wsMoreDraw(bool full)")
    need(draw, "uiBottomNav(3, nullptr);", "tab bar drawn on every More page")
    if "if" in draw[draw.find("wsDrawScrollbar(s, p);"):draw.find("uiBottomNav(3, nullptr);")].split("}")[-1]:
        raise ValidationError("the tab bar must be drawn unconditionally")
    need(layout, "// The tab bar is drawn on every page, so it is always live.", "tab bar hit first")
    need(block(hub, "static bool wsMoreTouch(int16_t x, int16_t y, bool longPress)"), "wsm::hitTest(", "touch uses the shared hit test")

    # Old geometry and parent hacks are gone from the new code.
    # (The guarded rotation preview keeps its 12.0 hold-to-commit geometry.)
    rotation = block(fragment, "static bool wsRotationPreviewTouch(int16_t x, int16_t y, bool longPress)")
    pages_only = fragment.replace(rotation, "")
    for needle in ("hubUi13BackRect", "hubUi12SystemBackRect", "hubUi13ActionRect", "gOs12PortalParent",
                   "gOs12SettingsParent", "hubRc2HitRef", "hubUi13RowRect", "hubMoreRect"):
        forbid(pages_only, needle, "12.0 geometry in the More pages")
    need(block(hub, "static bool wsMoreTouch(int16_t x, int16_t y, bool longPress)"),
         "if (g_rotationPreviewMode) return wsRotationPreviewTouch(x, y, longPress);", "rotation preview is modal")

    # Video test: the backend draws inside the page's video area, and the
    # full-screen sprite is never pushed over a running video.
    backend = read(repo / "src/ws350_media_backend.cpp")
    need(backend, "workshop::ui::more::videoRect(", "video drawn inside the Video test area")
    forbid(backend, "controlBarH", "video drawn over the page chrome")
    draw_hub = block(hub, "void smartHubDraw(ScreenState screen, bool forceRedraw)")
    need(draw_hub, "screen == SCREEN_HUB_MORE && wsVideoDirect();", "direct video drawing")
    need(draw_hub, "const bool buffered = !directVideoViewer && hubEnsureFrame();", "no sprite over running video")
    need(block(hub, "static void wsMoreDraw(bool full)"), "uiBottomNav(3, nullptr);", "video page tab bar")
    for name in REPLACED_RENDERERS:
        forbid(hub, f"static void {name}(", "replaced renderer still present")
    # No hard-coded channel labels; the channel is read from the update service.
    # (The header colour helper still recognises the word; it is never drawn.)
    for match in re.finditer(r'"CANDIDATE"', hub):
        if not hub[max(0, match.start() - 13):match.start()].endswith("strstr(state,"):
            raise ValidationError("hard-coded CANDIDATE label drawn on screen")
    forbid(hub, "Candidate channel", "hard-coded candidate channel text")
    need(fragment, "u.channel == workshop::platform::UpdateChannel::Candidate", "real update channel")
    # The only way to change the channel is the visible row, through a dialog.
    forbid(hub, "workshopUpdateSetChannel(next)", "invisible channel flip")
    if fragment.count("workshopUpdateSetChannel(") != 1 or "WsDialog::Channel" not in block(hub, "static void wsDialogConfirm()"):
        raise ValidationError("the update channel must change only after the confirmation dialog")

    # Every row of every page drawn by this build has a value case, and every
    # control has an action. (A view set in touch but never drawn is how the
    # 12.0 install dialog went missing.)
    view = block(hub, "static void wsRowView(wsm::RowId id, WsRowView& v)")
    tap = block(hub, "static void wsRowTap(wsm::RowId id, wsm::Part part)")
    for page, row, kind in live_page_rows(layout, fragment):
        if f"case R::{row}:" not in view:
            raise ValidationError(f"{page}/{row}: no value case in wsRowView")
        if kind in ("Toggle", "Stepper", "Action", "Action2") and f"case R::{row}:" not in tap:
            raise ValidationError(f"{page}/{row}: {kind} row has no action in wsRowTap")

    # Disabled controls say why: a disabled row always carries a reason.
    for line in view.splitlines():
        if "v.enabled = false;" in line and "v.reason" not in line:
            raise ValidationError(f"disabled row without a reason: {line.strip()}")

    # 12.2.1: no stray "|" beside a toggle. Every value slot goes through
    # wsDrawRowValue, which draws nothing for an empty value (uiDrawFit would
    # draw an em dash, which the WS350 font shows as "|"). The row label is
    # the only direct text draw left in wsDrawRow.
    # (12.3: the row body is shared with the Home, Printer and Workshop tabs.)
    need(block(hub, "static void wsDrawRow(const wsm::Screen& s, const wsm::RowSpec& spec, const wsm::Rect& row)"),
         "wsDrawRowBody(s, spec.kind, spec.label, v, row);", "More rows drawn by the shared row body")
    row = block(hub, "static void wsDrawRowBody(const wsm::Screen& s, wsm::RowKind kind, const char* labelText, const WsRowView& v,")
    forbid(row, "uiDrawFit(value", "value text drawn without the empty-value guard")
    if row.count("uiDrawFit(") != 1:
        raise ValidationError("wsDrawRowBody may draw text directly only for the label")
    toggle = row[row.find("case wsm::RowKind::Toggle:"):row.find("case wsm::RowKind::Stepper:")]
    for needle in ("drawFastVLine", "drawLine", "fillRect(", "drawRect(", "drawString(", "drawChar("):
        forbid(toggle, needle, "extra drawing between a toggle's label and switch")
    value_draw = block(hub, "static void wsDrawRowValue(")
    need(value_draw, "if (!wsm::drawsValueText(text)) return;", "empty values draw nothing")
    need(layout, "inline bool drawsValueText(const char* value) { return value != nullptr && value[0] != '\\0'; }",
         "empty-value predicate")

    # 12.2.1: the Local Portal tile fits its status line (no "Open ... code in...").
    tiles = block(hub, "static void wsTileStatus(")
    forbid(tiles, "Open %s", "Local Portal tile status that does not fit")
    need(tiles, 'snprintf(out, len, "%s · code inside", ip);', "Local Portal tile status")
    need(tiles, "if (tft.textWidth(out) > maxW) strlcpy(out, ip, len);", "Local Portal tile falls back to the address")
    need(block(hub, "static void wsDrawRoot(const wsm::Screen& s)"),
         "wsTileStatus(id, status, sizeof(status), textW, statusColor);", "tile status sized to the tile text")

    # 12.2.1: a date format that was never saved defaults to MM/DD/YYYY; a
    # saved one is read unchanged (only the NVS fallback differs).
    settings = read(repo / "src/settings.cpp")
    need(settings, 'netSettings.dateFormat = prefs.getUChar("net_datefmt", 2);', "MM/DD/YYYY default for an unsaved date format")
    if settings.count('"net_datefmt"') != 2 or 'prefs.putUChar("net_datefmt", netSettings.dateFormat);' not in settings:
        raise ValidationError("the saved date format must be read and written unchanged")

    # Local Portal still shows the access code, and its capture is sensitive.
    need(view, "securityPortalCode()", "Local Portal access code")
    forbid(fragment, "securitySetPortalCodeRequired", "touch control that turns off the access code")
    catalog = web[web.find('static const char kCatalog[] = R"json('):web.find(')json";')]
    need(catalog, '{"id":"system-portal","label":"Local Portal","group":"More","sensitive":"portal-code"}', "sensitive Local Portal view")
    for view_id in REMOVED_VIEW_IDS:
        forbid(catalog, f'"id":"{view_id}"', "removed view id in /hub/views")
    need(catalog, '"id":"more"', "More root view")
    # Home, Printer, Workshop and the 15 More pages; nothing else.
    view_ids = re.findall(r'\{"id":"([a-z0-9-]+)"', catalog)
    page_views = re.findall(r'PageLayout::\w+, "[^"]*", "[^"]*", "([a-z0-9-]+)"', layout)
    if view_ids != ["home", "printer", "workshop"] + page_views:
        raise ValidationError(f"/hub/views must list Home, Printer, Workshop and the More pages in order: {view_ids}")
    show = block(hub, "bool smartHubShowPage(const char* pageName)")
    need(show, "return wsMoreShowPage(pageName);", "/hub/show routes every More page through the page table")
    for needle in ("g_toolsView=true", "g_displayExperienceView=true", "g_audioSettingsView=true", "g_networkSettingsView=true"):
        forbid(hub, needle, "12.0 page state set anywhere")
    need(catalog, '{"version":3,', "catalog v3 (12.1 Local Portal redaction geometry)")
    need(read(ROOT / "scripts/capture-ws350-views.zsh"), "redaction = (8, 89, 472, 155)", "capture redaction of the access-code row")
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
    print("PASS: More overhaul layout installed; geometry and touch routing hold in 480x320 and 320x480")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
