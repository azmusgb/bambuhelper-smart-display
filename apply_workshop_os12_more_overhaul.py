#!/usr/bin/env python3
"""WS350 More/System overhaul (Workshop OS 12.1.x).

Owning patch for the More area. It runs last in the recipe, after
apply_workshop_os12_status_lite.py and apply_workshop_os12_code_token.py
(the More pages read both consent prompts and the Local Portal page shows
whether the sign-in code key is set up), and owns whole functions rather than
editing lines inside them, so earlier layers cannot silently undo it.

- ``firmware/platform/ui/more_layout.hpp`` (page table and geometry) is
  installed as ``include/workshop_more_layout.hpp``; the host test
  tests/workshop_os12_more_layout_smoke.cpp checks it in both orientations.
- ``firmware/platform/ui/more_pages.cppfrag`` (the More pages: drawing, live
  values, actions, touch) is inserted at the end of smart_hub.cpp's anonymous
  namespace. Drawing and touch both go through the layout functions.
- drawMore/drawSystem and the start of smartHubHandleTouch hand every More
  and System page to the new code. Tools and Custom are gone (their ids open
  the More root); the 12.0 More/System renderers, touch branches and
  /hub/show handlers they used are deleted.
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
    # 12.1.4 clean-up: Tools, Custom and every helper only they or the 12.0
    # More/System pages used.
    "static void drawTools(bool full)",
    "static void drawCustom(bool full)",
    "static void drawUi12Experience()",
    "static void drawUi12PrinterConnection()",
    "static void drawUi12SoftwareUpdate()",
    "static void hubUi12SettingsCard(const HubRect& r,const char* title,const char* detail,uint16_t rail=C10_SEPARATOR,bool wide=false)",
    "static HubRect hubUi12SettingsRect(uint8_t i)",
    "static HubRect hubUi12BackRect()",
    "static HubRect hubUi12SubActionRect()",
    "static HubRect hubUi12ExperienceRect(uint8_t i)",
    "static HubRect hubUi12SystemBackRect()",
    "static HubRect hubUi12SystemPortalRect()",
    "static HubRect hubUi13SystemCardRect(uint8_t i)",
    "static void hubUi13StepperRow(const HubRect& r,const char* label,const char* value,const char* detail,uint16_t accent=C10_ACCENT)",
    "static void hubUi13ToggleRow(const HubRect& r,const char* label,const char* detail,bool on,uint16_t accent=C10_ACCENT)",
    "static void hubUi13InfoRow(const HubRect& r,const char* label,const char* value,const char* detail,uint16_t accent=C10_ACCENT)",
    "static HubRect hubUi13ToggleRect(uint8_t i)",
    "static HubRect hubUi13PlusRect(uint8_t i)",
    "static HubRect hubUi13MinusRect(uint8_t i)",
    "static HubRect hubUi13StepperTouch(const HubRect& button,const HubRect& row)",
    "static HubRect hubUi13StepperPlusButton(const HubRect& r)",
    "static HubRect hubUi13StepperMinusButton(const HubRect& r)",
    "static HubRect hubUi13ActionRect()",
    "static HubRect hubUi13BackRect()",
    "static HubRect hubUi13RowRect(uint8_t i)",
    "static HubRect hubSystemActionRect(uint8_t i)",
    "static HubRect hubSystemAudioSettingsEntryRect()",
    "static HubRect hubSystemSubBackRect()",
    "static HubRect hubSystemSubNextRect()",
    "static HubRect hubSystemNetworkCardRect()",
    "static HubRect hubDisplayPagerRect()",
    "static void uiDisplaySettingCard(const HubRect& r, const char* label,",
    "static const char* hubDisplayPageLabel(uint8_t page)",
    "static const char* hubDisplayPageNextLabel(uint8_t page)",
    "static const char* hubDisplayPageFooterTitle(uint8_t page)",
    "static const char* hubDisplayPageFooterDetail(uint8_t page)",
    "static void uiHealthDot(int16_t x,int16_t y,const char* label,bool ok,uint16_t goodColor=UI_GREEN)",
    "static void uiMoreIcon(const HubRect& r,uint8_t i,uint16_t c)",
    "static HubRect hubToolsPresetRect(uint8_t i)",
    "static HubRect hubToolsActionRect(uint8_t i)",
    "static HubRect hubMoreRect(uint8_t i)",
    "static HubRect hubV1125MoreRect(uint8_t i)",
    "static void hubOs12NavRow(const HubRect& r,const char* title,const char* detail,uint16_t valueColor=C10_MUTED)",
    "static const char* hubOs12CompactTimezoneLabel()",
    "static const char* hubDateFormatLabel(uint8_t fmt)",
    "static const char* hubQuietHourLabel(uint8_t hour,char* out,size_t outLen,bool allowOff)",
    "static uint8_t hubStepCooldownThreshold(uint8_t current,bool reverse)",
    "static const char* hubLedFinishModeLabel()",
    "static const char* hubLedDriverLabel()",
    "static uint16_t hubStepLedSeconds(uint16_t current, bool reverse, bool allowZero)",
    "static const char* hubPowerDisplayModeLabel(uint8_t mode)",
    "static const char* hubPowerTypeLabel(uint8_t type)",
    "static uint8_t hubStepPowerPoll(uint8_t current,bool reverse)",
    "static uint8_t hubStepAutoOffDelay(uint8_t current,bool reverse)",
    "static const char* hubAfterPrintLabel()",
    "static const char* hubTimeDisplayLabel()",
    "static const char* hubClockSizeLabel(uint8_t v)",
    "static const char* hubHmsAutoLabel()",
    "static const char* hubGaugeSmoothingLabel()",
    "static const char* hubGlowModeLabel()",
    "static const char* hubGlowStyleLabel()",
    "static const char* hubGlowDurationLabel()",
    "static void hubFormatPresetPct(uint8_t level, bool allowZero, char* out, size_t outLen)",
    "static bool hubQuarterPreset(uint8_t level, bool allowZero)",
    "static uint8_t hubStepPreset(uint8_t current, const uint8_t* values,",
    "static uint16_t hubStepPreset16(uint16_t current, const uint16_t* values,",
    "static void hubCommitNetworkAndRestart()",
    "static bool hubStaticNetworkValid()",
    "static void hubNetworkDiscardEdit()",
    "static void hubLoadNetworkEdit()",
    "static const char* hubNetworkFieldLabel(uint8_t field)",
    "static void hubRc2PageIndicator(uint8_t page, uint8_t count)",
    "static void drawWidgetCard(uint8_t slot,const HubRect&r,bool selected=false)",
    "static void hubWidgetValue(uint8_t kind,char* value,size_t valueLen,char* sub,size_t subLen)",
    "static const char* hubWidgetLabel(uint8_t kind)",
    "static HubRect hubCustomRect(uint8_t i)",
    "static void uiActionButton(const HubRect& r, const char* label, uint16_t accent, bool filled=false)",
    "static void hubOs12StatePanel(const HubRect& r,const char* eyebrow,const char* title,const char* detail,uint16_t color,bool strong=false)",
    "static bool hubIpv4AllZero(const uint8_t v[4])",
    "static bool hubParseIpv4(const char* text, uint8_t out[4])",
    "static void hubIpv4FromAddress(const IPAddress& ip, uint8_t out[4])",
    "static void hubFormatIpv4(const uint8_t v[4], char* out, size_t len)",
)

TOUCH_TABS_OLD = "  if(hubTabBarLive(cur))for(uint8_t i=0;i<4;i++)if(hubNavRect(i).contains(x,y))"
TOUCH_TABS_NEW = ("  // The More pages own all of their touch, tab bar included.\n"
                  "  if(cur==SCREEN_HUB_MORE||cur==SCREEN_HUB_SYSTEM||cur==SCREEN_HUB_CUSTOM)return wsMoreTouch(x,y,longPress);\n"
                  + TOUCH_TABS_OLD)

CUSTOM_LONG_PRESS = "  if(longPress&&cur==SCREEN_HUB_CUSTOM){g_widgetEditMode=!g_widgetEditMode;g_widgetSelected=0;g_dirty=true;return true;}\n"
CUSTOM_EDIT = ("  if(cur==SCREEN_HUB_CUSTOM&&g_widgetEditMode){for(uint8_t i=0;i<4;i++)if(hubCustomRect(i).contains(x,y)){g_widgetSelected=i;"
               "g_widgets[i]=(uint8_t)((g_widgets[i]+1)%HUB_W_COUNT);prefsSave();g_dirty=true;return true;}return true;}\n")
CUSTOM_DRAW_OLD = "    case SCREEN_HUB_CUSTOM:   drawCustom(effectiveForce);   break;"
CUSTOM_DRAW_NEW = "    case SCREEN_HUB_CUSTOM:   drawMore(effectiveForce);     break;"

TAB_LIVE_SIGNATURE = "static bool hubTabBarLive(ScreenState cur)"
TAB_LIVE = """static bool hubTabBarLive(ScreenState cur) {
  // Every hub screen draws the tab bar. (More, System and Custom hand their
  // touch to the More pages before this is consulted.)
  (void)cur;
  return true;
}
"""

HOLD_NETWORK_OLD = ("  if(g_networkSettingsView && (g_networkSettingsPage%HUB_NETWORK_PAGE_COUNT)==6 && hubStaticNetworkValid() && hubRc2HitRef(x,y,240,252,230,56)){\n"
                    "    kind=1;bx=240;by=252;bw=230;bh=56;label=\"Keep Holding\";\n"
                    "  }else if(")
HOLD_NETWORK_NEW = "  if("

SHOW_PAGE_SIGNATURE = "bool smartHubShowPage(const char* pageName)"
SHOW_PAGE = """bool smartHubShowPage(const char* pageName) {
  if (!pageName) return false;
  if (strcmp(pageName, "legacy-printer") == 0) { smartHubReturnToPrinter(); return true; }
  if (!g_cfg.enabled) return false;

  if (strcmp(pageName, "home") == 0) { setPage(SCREEN_HUB_HOME); return true; }
  if (strcmp(pageName, "printer") == 0) { setPage(SCREEN_HUB_PRINTER); return true; }
  if (strcmp(pageName, "workshop") == 0) { setPage(SCREEN_HUB_WORKSHOP); return true; }
  // Every More page, plus the ids of pages that were merged into them.
  return wsMoreShowPage(pageName);
}
"""

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
MORE_TOUCH_END = "    }return true;}\n  if(cur==SCREEN_HUB_PRINTER){"
SYSTEM_TOUCH_START = "  if(cur==SCREEN_HUB_SYSTEM){\n"
SYSTEM_TOUCH_END = ("      if(buzzerSettings.enabled) buzzerPlay(BUZZ_CONNECTED);\n      return true;\n    }\n"
                    "    return true;\n  }\n")

HOLD_ROTATION_OLD = "if(g_displayExperienceView && g_rotationPreviewMode && hubRc2HitRef(x,y,160,258,310,52)){"
HOLD_ROTATION_NEW = "if(g_rotationPreviewMode && getScreenState()==SCREEN_HUB_MORE && hubRc2HitRef(x,y,160,258,310,52)){"

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
CATALOG_LEGACY: tuple[tuple[str, str, str], ...] = ()


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
    text = replace_cpp_function(text, SHOW_PAGE_SIGNATURE, SHOW_PAGE, "/hub/show")
    text = remove_span(text, MORE_TOUCH_START, MORE_TOUCH_END, False, "  if(cur==SCREEN_HUB_PRINTER){", "old More touch")
    text = replace_once(text, CUSTOM_LONG_PRESS, "", "Custom long press")
    text = replace_once(text, CUSTOM_EDIT, "", "Custom widget editing")
    text = replace_once(text, CUSTOM_DRAW_OLD, CUSTOM_DRAW_NEW, "Custom screen")
    text = replace_cpp_function(text, TAB_LIVE_SIGNATURE, TAB_LIVE, "tab bar predicate")
    text = replace_once(text, HOLD_NETWORK_OLD, HOLD_NETWORK_NEW, "Network Expert hold progress")
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
    if "#define WORKSHOP_OS_CODE_TOKEN 1" not in build:
        raise PatchError("the More overhaul runs after apply_workshop_os12_code_token.py")
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
