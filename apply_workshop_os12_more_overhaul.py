#!/usr/bin/env python3
"""WS350 More/System overhaul (Workshop OS 12.1.x).

Owning patch for the More area. It runs last in the recipe, after
apply_workshop_os12_status_lite.py, and owns whole functions rather than
editing lines inside them, so earlier layers cannot silently undo it.

- ``firmware/platform/ui/more_layout.hpp`` (page table and geometry) is
  installed as ``include/workshop_more_layout.hpp``; the host test
  tests/workshop_os12_more_layout_smoke.cpp checks it in both orientations.
- ``firmware/platform/ui/more_pages.cppfrag`` (the More pages: drawing, live
  values, actions, touch) is inserted at the end of smart_hub.cpp's anonymous
  namespace. Drawing and touch both go through the layout functions.
- drawMore/drawSystem and the start of smartHubHandleTouch hand every page
  that has moved to the new code. Pages that have not moved yet keep their
  12.0 screens (wsPageLive in the fragment says which).
- The tab bar's rectangles come from the layout (hubNavRect), the More tab
  always opens the More root, and the /hub/views catalog lists the new pages.
"""
from __future__ import annotations

import argparse
import re
import shutil
import sys as _sys
from pathlib import Path

_here = Path(__file__).resolve().parent
if str(_here) not in _sys.path:
    _sys.path.insert(0, str(_here))
from scripts.smart_home_patch_utils import PatchError, replace_cpp_function  # noqa: E402

BUILD_MARKER = "#define WORKSHOP_OS12_MORE_OVERHAUL 1"
LAYOUT_SOURCE = Path("firmware") / "platform" / "ui" / "more_layout.hpp"
LAYOUT_TARGET = Path("include") / "workshop_more_layout.hpp"

PAGES_SOURCE = Path("firmware") / "platform" / "ui" / "more_pages.cppfrag"

OLD_INCLUDE = '#include "smart_hub.h"\n'
NEW_INCLUDE = '#include "smart_hub.h"\n#include "workshop_more_layout.hpp"\n'

NAV_RECT_SIGNATURE = "static HubRect hubNavRect(uint8_t i)"
NAV_RECT = """static HubRect hubNavRect(uint8_t i) {
  // One tab-bar geometry for drawing and touch on every hub screen.
  const workshop::ui::more::Rect r=workshop::ui::more::tabRect(workshop::ui::more::makeScreen(tft.width(),tft.height()),i);
  return hr(r.x,r.y,r.w,r.h);
}
"""

NAMESPACE_END = "\n} // namespace\n"

DRAW_MORE_SIGNATURE = "static void drawMore(bool full)"
DRAW_MORE = """static void wsMoreDraw(bool full);
static void drawMore(bool full) {
  // 12.0 screens that have not moved to the new More pages yet.
  if(g_displayExperienceView){drawDisplayExperience(full);return;}if(g_toolsView){drawTools(full);return;}
  if(g_ui12SettingsView==1){drawUi13Display();return;}if(g_ui12SettingsView==2){drawUi13Sound();return;}if(g_ui12SettingsView==5){drawUi13AfterPrint();return;}if(g_ui12SettingsView==6){drawUi13PrinterAlerts();return;}if(g_ui12SettingsView==7){drawUi13AlertSignals();return;}if(g_ui12SettingsView==10){drawOs12Media();return;}if(g_ui12SettingsView==11){drawOs12Recorder();return;}if(g_ui12SettingsView==12){drawOs12VideoViewer();return;}
  g_ui12SettingsView=0;
  wsMoreDraw(full);
}
"""

DRAW_SYSTEM_SIGNATURE = "static void drawSystem(bool full)"
DRAW_SYSTEM = """static void drawSystem(bool full) {
  // Hidden Hardware pages (capture only) until Sound & Alerts moves over.
  if(g_audioSettingsView){drawAudioSettings(full);return;}
  wsMoreDraw(full);
}
"""

# Renderers replaced by the new pages in this step.
REPLACED_RENDERERS = (
    "static void drawUi13Network()",
    "static void drawUi13PrinterPower()",
    "static void drawUi13PowerOptions()",
    "static void drawUi13AutoOffConfirm()",
    "static void drawUi12PortalAccess()",
    "static void drawUi13DateTime()",
    "static void drawUi13SoftwareUpdate()",
    "static void drawUi13UpdateConfirm()",
    "static void drawUi13Diagnostics()",
    "static void drawNetworkEssentials(bool full)",
)

TOUCH_TABS_OLD = "  if(hubTabBarLive(cur))for(uint8_t i=0;i<4;i++)if(hubNavRect(i).contains(x,y))"
TOUCH_TABS_NEW = ("  // Moved More pages own all of their touch, tab bar included.\n"
                  "  if((cur==SCREEN_HUB_MORE||cur==SCREEN_HUB_SYSTEM)&&!wsLegacyActive(cur))return wsMoreTouch(x,y,longPress);\n"
                  + TOUCH_TABS_OLD)

MORE_TAB_OLD = ("else{if(cur==SCREEN_HUB_MORE&&(g_toolsView||g_displayExperienceView)){g_toolsView=false;g_displayExperienceView=false;"
                "g_displayExperiencePage=0;g_dirty=true;}else g_ui12SettingsView=0;g_ui12SystemView=0;setPage(SCREEN_HUB_MORE);}return true;}")
MORE_TAB_NEW = "else wsOpen(wsm::PageId::Root);return true;}"

WORKSHOP_PORTAL_OLD = """        g_ui12SettingsView=0;
        g_ui12SystemView=1;
        g_networkSettingsView=false;
        g_audioSettingsView=false;
        setPage(SCREEN_HUB_SYSTEM);
"""
WORKSHOP_PORTAL_NEW = """        wsOpen(wsm::PageId::LocalPortal);
"""

HOME_SYSTEM_OLD = "if(hubHomeRect(2).contains(x,y)||hubHomeRect(3).contains(x,y)||hubHomeRect(4).contains(x,y)){setPage(SCREEN_HUB_SYSTEM);return true;}"
HOME_SYSTEM_NEW = "if(hubHomeRect(2).contains(x,y)||hubHomeRect(3).contains(x,y)||hubHomeRect(4).contains(x,y)){wsOpen(wsm::PageId::Root);return true;}"
HOME_HINT_OLD = '"More  >  System  >  Printer & Power"'
HOME_HINT_NEW = '"More  >  Printer & Power"'

ADVANCE_OLD = "case SCREEN_HUB_WORKSHOP: g_ui12SettingsView=0;g_ui12SystemView=0;setPage(SCREEN_HUB_MORE);     break;"
ADVANCE_NEW = "case SCREEN_HUB_WORKSHOP: wsOpen(wsm::PageId::Root);     break;"

SHOW_PAGE_OLD = '  if (strcmp(pageName, "workshop") == 0) { setPage(SCREEN_HUB_WORKSHOP); return true; }\n'
SHOW_PAGE_NEW = SHOW_PAGE_OLD + "  if (wsMoreShowPage(pageName)) return true;\n"

# The old System touch branch: everything except the hidden Hardware pages is
# now handled by the More pages. Removing it also removes the invisible
# update-channel flip on the Software Update version card.
SYSTEM_TOUCH_START = "  if(cur==SCREEN_HUB_SYSTEM){\n"
SYSTEM_TOUCH_AUDIO = "    if(g_audioSettingsView){\n      if(hubSystemSubBackRect().contains(x,y))"
SYSTEM_TOUCH_NETWORK = "    if(g_networkSettingsView){\n"
SYSTEM_TOUCH_TAIL = "      if(buzzerSettings.enabled) buzzerPlay(BUZZ_CONNECTED);\n      return true;\n    }\n"

# /hub/views: capture order. "sensitive" pages are never stored by captures.
CATALOG_LEGACY = (
    ("settings-display", "Display & Appearance", "Settings"),
    ("settings-sounds", "Sound & Media", "Settings"),
    ("media", "Media", "Sound & Media"),
    ("media-lab", "Recorder", "Sound & Media"),
    ("media-video", "Video Viewer", "Sound & Media"),
    ("custom", "Custom", "Primary"),
    ("tools", "Tools", "More"),
    ("display-quick", "Display - Quick", "Display"),
    ("display-schedule", "Display - Schedule", "Display"),
    ("display-behavior", "Display - Behavior", "Display"),
    ("display-visual", "Display - Visual", "Display"),
    ("display-clock", "Display - Clock", "Display"),
    ("display-alerts", "Display - Alerts", "Display"),
    ("display-signals", "Display - Signals", "Display"),
    ("display-theme", "Display - Theme", "Display Expert"),
    ("display-gauge-colors", "Display - Gauge Colors", "Display Expert"),
    ("display-gauge-scales", "Display - Gauge Scales", "Display Expert"),
    ("display-gauge-behavior", "Display - Gauge Behavior", "Display Expert"),
    ("display-glow", "Display - Glow", "Display Expert"),
    ("display-layout", "Display - Layout", "Display Expert"),
    ("display-extras", "Display - Extras", "Display Expert"),
    ("hardware-sound", "Hardware - Sound", "Hardware"),
    ("hardware-led", "Hardware - LED", "Hardware"),
    ("hardware-finish", "Hardware - Finish", "Hardware"),
    ("hardware-error", "Hardware - Error", "Hardware"),
)


def load(path: Path) -> str:
    if not path.is_file():
        raise PatchError(f"missing {path}")
    return path.read_text(encoding="utf-8")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise PatchError(f"{label}: expected exactly one anchor, found {count}")
    return text.replace(old, new, 1)


def remove_span(text: str, start: str, end: str, keep_end: bool, replacement: str, label: str) -> str:
    """Replace text from `start` up to `end` (kept or consumed) with `replacement`."""
    if text.count(start) != 1 or text.count(end) != 1:
        raise PatchError(f"{label}: anchors not unique ({text.count(start)}, {text.count(end)})")
    a = text.index(start)
    b = text.index(end, a)
    if not keep_end:
        b += len(end)
    return text[:a] + replacement + text[b:]


def install_layout(repo: Path, source_root: Path) -> None:
    source = source_root / LAYOUT_SOURCE
    if not source.is_file():
        raise PatchError(f"missing {source}")
    target = repo / LAYOUT_TARGET
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)


def layout_pages(source_root: Path) -> list[tuple[str, str, str, int]]:
    """(PageId name, title, view id, level) for every page in more_layout.hpp."""
    text = load(source_root / LAYOUT_SOURCE)
    pages = re.findall(
        r'\{PageId::(\w+), PageId::\w+, (\d), PageLayout::\w+, "([^"]*)", "[^"]*", "([^"]*)"', text)
    if len(pages) < 10:
        raise PatchError("could not read the page table from more_layout.hpp")
    return [(name, title, view, int(level)) for name, level, title, view in pages]


def pending_pages(fragment: str) -> set[str]:
    """Pages the fragment still sends to their 12.0 screens (wsPageLive false)."""
    start = fragment.find("static bool wsPageLive(wsm::PageId id)")
    end = fragment.find("return false;", start)
    if start < 0 or end < 0:
        raise PatchError("wsPageLive missing from more_pages.cppfrag")
    return set(re.findall(r"case wsm::PageId::(\w+):", fragment[start:end]))


def catalog_json(source_root: Path, fragment: str) -> str:
    pending = pending_pages(fragment)
    rows = [("home", "Home", "Primary", ""), ("printer", "Printer", "Primary", ""), ("workshop", "Workshop", "Primary", "")]
    for name, title, view, level in layout_pages(source_root):
        if name in pending:
            continue
        sensitive = ',"sensitive":"portal-code"' if name == "LocalPortal" else ""
        rows.append((view, title, "More" if level < 2 else "More - sub-page", sensitive))
    for view, label, group in CATALOG_LEGACY:
        rows.append((view, label, group, ""))
    ids = [r[0] for r in rows]
    if len(ids) != len(set(ids)):
        raise PatchError(f"duplicate view ids in catalog: {ids}")
    body = ",\n".join(f'    {{"id":"{v}","label":"{l}","group":"{g}"{s}}}' for v, l, g, s in rows)
    return '{"version":3,"views":[\n' + body + "\n  ]}"


def patch_catalog(repo: Path, source_root: Path, fragment: str) -> None:
    path = repo / "src" / "web_server.cpp"
    text = load(path)
    start_marker = 'static const char kCatalog[] = R"json('
    start = text.find(start_marker)
    end = text.find(')json";', start)
    if start < 0 or end < 0 or text.count(start_marker) != 1:
        raise PatchError("/hub/views catalog not found")
    text = text[: start + len(start_marker)] + catalog_json(source_root, fragment) + text[end:]
    path.write_text(text, encoding="utf-8")


def patch_smart_hub(repo: Path, source_root: Path) -> str:
    path = repo / "src" / "smart_hub.cpp"
    text = load(path)
    fragment = load(source_root / PAGES_SOURCE)
    text = replace_once(text, OLD_INCLUDE, NEW_INCLUDE, "layout include")
    text = replace_cpp_function(text, NAV_RECT_SIGNATURE, NAV_RECT, "tab bar rectangles")
    for signature in REPLACED_RENDERERS:
        text = replace_cpp_function(text, signature, "", f"replaced renderer {signature}")
    text = replace_cpp_function(text, DRAW_MORE_SIGNATURE, DRAW_MORE, "drawMore")
    text = replace_cpp_function(text, DRAW_SYSTEM_SIGNATURE, DRAW_SYSTEM, "drawSystem")
    text = replace_once(text, NAMESPACE_END, "\n" + fragment.rstrip() + "\n" + NAMESPACE_END, "More pages")
    text = replace_once(text, TOUCH_TABS_OLD, TOUCH_TABS_NEW, "More touch hand-off")
    text = replace_once(text, MORE_TAB_OLD, MORE_TAB_NEW, "More tab opens the More root")
    if text.count(WORKSHOP_PORTAL_OLD) != 2:
        raise PatchError("Workshop Local Portal links: expected two")
    text = text.replace(WORKSHOP_PORTAL_OLD, WORKSHOP_PORTAL_NEW)
    text = replace_once(text, HOME_SYSTEM_OLD, HOME_SYSTEM_NEW, "Home system card")
    text = replace_once(text, HOME_HINT_OLD, HOME_HINT_NEW, "Home setup hint")
    text = replace_once(text, ADVANCE_OLD, ADVANCE_NEW, "board-button advance")
    text = replace_once(text, SHOW_PAGE_OLD, SHOW_PAGE_NEW, "/hub/show")
    text = remove_span(text, SYSTEM_TOUCH_START, SYSTEM_TOUCH_AUDIO, True,
                       SYSTEM_TOUCH_START + "    // Only the hidden Hardware pages still reach here.\n", "old System touch")
    text = remove_span(text, SYSTEM_TOUCH_NETWORK, SYSTEM_TOUCH_TAIL, False, "", "old Network Expert and System actions")
    path.write_text(text, encoding="utf-8")
    return fragment


def apply(repo: Path, source_root: Path) -> None:
    build_path = repo / "include" / "smart_home_build.h"
    build = load(build_path)
    if "#define WORKSHOP_OS_STATUS_LITE_TOKEN 1" not in build:
        raise PatchError("the More overhaul runs after apply_workshop_os12_status_lite.py")
    if BUILD_MARKER in build:
        raise PatchError("the More overhaul is already applied")
    install_layout(repo, source_root)
    fragment = patch_smart_hub(repo, source_root)
    patch_catalog(repo, source_root, fragment)
    build_path.write_text(build.rstrip() + "\n" + BUILD_MARKER + "\n", encoding="utf-8")
    print("Workshop OS 12.1 More pages installed")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    ap.add_argument("--source-root", default=str(_here))
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    if not args.apply:
        raise SystemExit("refusing to modify source without --apply")
    try:
        apply(Path(args.repo).resolve(), Path(args.source_root).resolve())
    except PatchError as exc:
        raise SystemExit(f"FAIL: {exc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
