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
- drawMore/drawSystem and the start of smartHubHandleTouch hand every More
  and System page to the new code. Only the hidden, capture-only Tools page
  keeps its 12.0 screen until the clean-up step.
- Video test: smartHubDraw leaves the panel to the media backend while a
  video runs (wsVideoDirect), and the backend draws inside the layout's
  video area instead of over the header and tab bar.
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
  // The hidden, capture-only Tools page keeps its 12.0 screen for now.
  if(g_toolsView){drawTools(full);return;}
  wsMoreDraw(full);
}
"""

DRAW_SYSTEM_SIGNATURE = "static void drawSystem(bool full)"
DRAW_SYSTEM = """static void drawSystem(bool full) {
  // System is part of More now (Updates & About and its sub-pages).
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
    "static void drawUi13Display()",
    "static void drawUi13AfterPrint()",
    "static void drawUi13Sound()",
    "static void drawOs12Media()",
    "static void drawOs12VideoViewer()",
    "static void drawOs12Recorder()",
    "static void drawUi13PrinterAlerts()",
    "static void drawUi13AlertSignals()",
    "static void drawDisplayExperience(bool full)",
    "static void drawAudioSettings(bool full)",
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

# Media backend: draw video inside the Video test page's video area so the
# header, control row and tab bar stay on screen.
BACKEND_INCLUDE_OLD = '#include "display_ui.h"\n'
BACKEND_INCLUDE_NEW = '#include "display_ui.h"\n#include "workshop_more_layout.hpp"\n'
BACKEND_AREA = """
#if defined(BOARD_IS_WS350) && defined(BOARD_HAS_PSRAM)
// Video area of the More "Video test" page (between its header and controls).
static void ws350VideoArea(int16_t& x, int16_t& y, int16_t& w, int16_t& h) {
  const workshop::ui::more::Rect r = workshop::ui::more::videoRect(
      workshop::ui::more::makeScreen(tft.width(), tft.height()), workshop::ui::more::PageId::VideoTest);
  x = r.x; y = r.y; w = r.w; h = r.h;
}
#endif
"""
DEMO_SIGNATURE = "void Ws350MediaBackend::renderDemoFrame(uint32_t nowMs)"
DEMO = """void Ws350MediaBackend::renderDemoFrame(uint32_t nowMs) {
#if defined(BOARD_IS_WS350) && defined(BOARD_HAS_PSRAM)
  if (!videoRequested_ || videoPaused_ || videoSource_ != VideoSource::Demo) return;
  if (videoLastRenderAtMs_ != 0 && nowMs - videoLastRenderAtMs_ < kVideoFrameIntervalMs) return;

  int16_t ax = 0, ay = 0, aw = 0, ah = 0;
  ws350VideoArea(ax, ay, aw, ah);
  if (aw < 80 || ah < 80) return;
  const uint32_t frame = videoLastFrameId_ + 1U;
  const int16_t sprite = 48;
  const int16_t motionWidth = aw - sprite - 16 > 1 ? aw - sprite - 16 : 1;
  const int16_t motionHeight = ah - sprite - 24 > 1 ? ah - sprite - 24 : 1;
  const int16_t x = static_cast<int16_t>(ax + 8 + (frame * 11U) % motionWidth);
  const int16_t y = static_cast<int16_t>(ay + 8 + (frame * 7U) % motionHeight);
  const int16_t barY = static_cast<int16_t>(ay + ah - 8);

  // The first frame clears the area; later frames repaint only the previous
  // and current shape and the progress strip, to leave SPI and CPU headroom
  // for touch and printer telemetry.
  if (videoLastFrameId_ == 0U) {
    tft.fillRect(ax, ay, aw, ah, TFT_BLACK);
    tft.drawRect(ax + 6, barY - 2, aw - 12, 6, TFT_DARKGREY);
  } else {
    const uint32_t previousFrame = frame - 1U;
    const int16_t previousX = static_cast<int16_t>(ax + 8 + (previousFrame * 11U) % motionWidth);
    const int16_t previousY = static_cast<int16_t>(ay + 8 + (previousFrame * 7U) % motionHeight);
    tft.fillRect(previousX, previousY, sprite, sprite, TFT_BLACK);
  }

  tft.fillCircle(x + sprite / 2, y + sprite / 2, sprite / 2, TFT_CYAN);
  tft.fillRect(x + sprite / 2 - 9, y + sprite / 2 - 9, 18, 18, TFT_BLACK);
  tft.fillRect(ax + 8, barY, aw - 16, 2, TFT_BLACK);
  const int16_t progress = static_cast<int16_t>((frame * 5U) % (aw > 16 ? aw - 16 : 1));
  tft.fillRect(ax + 8, barY, progress, 2, TFT_GREEN);

  markFrameDirty();
  videoLastFrameId_ = frame;
  videoLastRenderAtMs_ = nowMs;
  ++videoDiagnostics_.polls;
  ++videoDiagnostics_.frameObservations;
  ++videoDiagnostics_.framesRendered;
  yield();  // Cooperative handoff: demo rendering must not starve touch/network tasks.
  videoDiagnostics_.lastFrameId = frame;
  videoDiagnostics_.lastFrameBytes = 0;
  videoDiagnostics_.lastFrameAtMs = nowMs;
#else
  (void)nowMs;
#endif
}
"""
CAMERA_GEOMETRY_OLD = """  const int16_t controlBarH = 50;
  const int16_t viewportH = tft.height() > controlBarH ? tft.height() - controlBarH : tft.height();
  const float sw = static_cast<float>(tft.width());
  const float sh = static_cast<float>(viewportH);"""
CAMERA_GEOMETRY_NEW = """  int16_t ax = 0, ay = 0, aw = 0, ah = 0;
  ws350VideoArea(ax, ay, aw, ah);
  const float sw = static_cast<float>(aw);
  const float sh = static_cast<float>(ah);"""
CAMERA_DRAW_OLD = """  const int x = (tft.width() - drawW) / 2;
  const int y = (viewportH - drawH) / 2;
  tft.fillRect(0, 0, tft.width(), viewportH, TFT_BLACK);"""
CAMERA_DRAW_NEW = """  const int x = ax + (aw - drawW) / 2;
  const int y = ay + (ah - drawH) / 2;
  tft.fillRect(ax, ay, aw, ah, TFT_BLACK);"""

# The 12.0 More and System touch branches. The More pages handle all of it now
# (only the hidden Tools page keeps its branch until clean-up). Removing the
# System branch also removes the invisible update-channel flip on the old
# Software Update version card.
MORE_TOUCH_START = "  if(cur==SCREEN_HUB_MORE){\n    if(g_displayExperienceView){\n      if(g_rotationPreviewMode){"
MORE_TOUCH_TOOLS = "    if(g_toolsView){\n"
MORE_TOUCH_SETTINGS = "    if(g_ui12SettingsView){\n      if(g_ui12SettingsView==1){"
MORE_TOUCH_END = "    }return true;}\n  if(cur==SCREEN_HUB_PRINTER){"
SYSTEM_TOUCH_START = "  if(cur==SCREEN_HUB_SYSTEM){\n"
SYSTEM_TOUCH_END = ("      if(buzzerSettings.enabled) buzzerPlay(BUZZ_CONNECTED);\n      return true;\n    }\n"
                    "    return true;\n  }\n")

HOLD_ROTATION_OLD = "}else if(g_displayExperienceView && g_rotationPreviewMode && hubRc2HitRef(x,y,160,258,310,52)){"
HOLD_ROTATION_NEW = "}else if(g_rotationPreviewMode && getScreenState()==SCREEN_HUB_MORE && hubRc2HitRef(x,y,160,258,310,52)){"

COMPOSITOR_OLD = """  lgfx::LovyanGFX* panel = tft_ptr;
  const bool buffered = hubEnsureFrame();
  if (buffered) {
    panel = g_hubPanelCanvas;
    tft_ptr = g_hubFrame;
    g_hubFrameDirty = false;
  }
"""
COMPOSITOR_NEW = """  lgfx::LovyanGFX* panel = tft_ptr;

  // Leaving the More screen stops the video test.
  wsVideoGuard(screen);

  // While the video test runs, the media backend draws its frames straight
  // to the panel inside the video area. Draw the page chrome around it
  // directly too, and never push the full-screen sprite over the video.
  const bool directVideoViewer =
      screen == SCREEN_HUB_MORE && wsVideoDirect();

  const bool buffered = !directVideoViewer && hubEnsureFrame();

  if (directVideoViewer) {
    // Force a complete buffered redraw after leaving the video viewer.
    g_hubFramePrimed = false;
  }

  if (buffered) {
    panel = g_hubPanelCanvas;
    tft_ptr = g_hubFrame;
    g_hubFrameDirty = false;
  }
"""

CAPTURE_SIGNATURE = "bool smartHubCapturePrepare(uint16_t* width, uint16_t* height)"
CAPTURE = """bool smartHubCapturePrepare(uint16_t* width, uint16_t* height) {
  if (!g_cfg.enabled) return false;
  // The video test draws straight to the panel, which cannot be read back.
  // Compose the page into the sprite for the capture instead (the video
  // area shows a placeholder); the panel's chrome is redrawn afterwards.
  g_wsCaptureCompose = true;
  smartHubDraw(getScreenState(), true);
  g_wsCaptureCompose = false;
  g_wsVideoChromeDrawn = false;
  if (!g_hubFrame || !g_hubFrame->getBuffer() || g_hubFrameW <= 0 || g_hubFrameH <= 0)
    return false;
  if (width) *width = (uint16_t)g_hubFrameW;
  if (height) *height = (uint16_t)g_hubFrameH;
  return true;
}
"""

# /hub/views: capture order. "sensitive" pages are never stored by captures.
CATALOG_LEGACY = (
    ("custom", "Custom", "Primary"),
    ("tools", "Tools", "More"),
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
    end = fragment.find("\n}\n", start)
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
    text = remove_span(text, MORE_TOUCH_START, MORE_TOUCH_TOOLS, True,
                       "  if(cur==SCREEN_HUB_MORE){\n    // Only the hidden Tools page still reaches here.\n", "old More touch")
    text = remove_span(text, MORE_TOUCH_SETTINGS, MORE_TOUCH_END, False,
                       "    return true;\n  }\n  if(cur==SCREEN_HUB_PRINTER){", "old More settings touch")
    text = remove_span(text, SYSTEM_TOUCH_START, SYSTEM_TOUCH_END, False, "", "old System touch")
    text = replace_once(text, HOLD_ROTATION_OLD, HOLD_ROTATION_NEW, "rotation hold progress")
    text = replace_once(text, COMPOSITOR_OLD, COMPOSITOR_NEW, "video compositor")
    text = replace_cpp_function(text, CAPTURE_SIGNATURE, CAPTURE, "framebuffer capture")
    path.write_text(text, encoding="utf-8")
    return fragment


def patch_media_backend(repo: Path) -> None:
    path = repo / "src" / "ws350_media_backend.cpp"
    text = load(path)
    text = replace_once(text, BACKEND_INCLUDE_OLD, BACKEND_INCLUDE_NEW, "backend layout include")
    text = replace_once(text, "\n" + DEMO_SIGNATURE, BACKEND_AREA + "\n" + DEMO_SIGNATURE, "backend video area helper")
    text = replace_cpp_function(text, DEMO_SIGNATURE, DEMO, "demo video frame")
    text = replace_once(text, CAMERA_GEOMETRY_OLD, CAMERA_GEOMETRY_NEW, "camera frame geometry")
    text = replace_once(text, CAMERA_DRAW_OLD, CAMERA_DRAW_NEW, "camera frame placement")
    path.write_text(text, encoding="utf-8")


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
    patch_media_backend(repo)
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
