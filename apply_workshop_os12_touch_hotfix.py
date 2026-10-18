#!/usr/bin/env python3
"""Touch hotfix for the WS350 More/System pages (candidate 12.0.2).

Fixes found while mapping the More area (no layout change):

* The bottom tab bar is drawn only on the More root (and a few hidden expert
  pages), but its touch zones were hit-tested first on every hub screen. In
  landscape they cover y 266-319, which is most of every sub-page's Back and
  action button (y 256-307): a tap on the middle of Back went Home, and a tap on
  "Local Portal" went to Workshop or the More root. The tab-bar hit test now
  runs only where the tab bar is drawn (``hubTabBarLive``).
* The stepper "-" touch zone (x 232-283 of a 456 px row) did not line up with
  the drawn button (x 264-307). Drawing and touch now share one rectangle per
  button; the touch zone is the drawn button widened by 4 px each side over
  the full row height, as "+" already was.
* Software Update's right-hand button said "Local Portal" but checks for an
  update or opens the install confirmation. It now says "Check for update" or
  "Install", and is greyed while an update job is busy (touch already ignored
  it then).
* The install confirmation (System view 5) had lost its draw case, so after a
  check found an update the screen kept showing the System root while touch
  acted as the install dialog. With the tab bar no longer covering it, a tap on
  the System root's "Local Portal" button would have started an install. The
  draw case is restored; the dialog no longer draws a tab bar, matching every
  other System page.

Runs last in the recipe, after apply_workshop_os12_portal_signin_restore.py.
"""
from __future__ import annotations

import argparse
import sys as _sys
from pathlib import Path

_here = Path(__file__).resolve().parent
if str(_here) not in _sys.path:
    _sys.path.insert(0, str(_here))
from scripts.smart_home_patch_utils import PatchError, replace_cpp_function  # noqa: E402

BUILD_MARKER = "#define WORKSHOP_OS12_TOUCH_HOTFIX 1"

OLD_MINUS_RECT = '''static HubRect hubUi13MinusRect(uint8_t i) {
  const HubRect r=hubUi13RowRect(i);
  return hr(r.x+r.w-236,r.y,52,r.h);
}

static HubRect hubUi13PlusRect(uint8_t i) {
  const HubRect r=hubUi13RowRect(i);
  return hr(r.x+r.w-60,r.y,52,r.h);
}
'''

NEW_MINUS_RECT = '''// One rectangle per stepper button, used by both drawing and touch.
static HubRect hubUi13StepperMinusButton(const HubRect& r) {
  return hr(r.x+r.w-204,r.y+(r.h-44)/2,44,44);
}

static HubRect hubUi13StepperPlusButton(const HubRect& r) {
  return hr(r.x+r.w-44-OS12V_INSET,r.y+(r.h-44)/2,44,44);
}

// Touch zone: the drawn button widened by 4 px each side, over the full row.
static HubRect hubUi13StepperTouch(const HubRect& button,const HubRect& row) {
  return hr(button.x-4,row.y,button.w+8,row.h);
}

static HubRect hubUi13MinusRect(uint8_t i) {
  const HubRect r=hubUi13RowRect(i);
  return hubUi13StepperTouch(hubUi13StepperMinusButton(r),r);
}

static HubRect hubUi13PlusRect(uint8_t i) {
  const HubRect r=hubUi13RowRect(i);
  return hubUi13StepperTouch(hubUi13StepperPlusButton(r),r);
}
'''

# replace_cpp_function finds the body brace after the signature, so the
# signature stops before " {".
STEPPER_SIGNATURE = "static void hubUi13StepperRow(const HubRect& r,const char* label,const char* value,const char* detail,uint16_t accent=C10_ACCENT)"

NEW_STEPPER = STEPPER_SIGNATURE + ''' {
  (void)accent;hubOs12RowSurface(r);
  const HubRect minus=hubUi13StepperMinusButton(r);
  const HubRect plus=hubUi13StepperPlusButton(r);
  const int16_t controlStart=minus.x;
  uiDrawFit(label,r.x+OS12V_INSET,r.y+7,controlStart-r.x-OS12V_INSET*2,FONT_SMALL,TL_DATUM,OS12V_MUTED,OS12V_SURFACE);
  uiDrawFit(detail,r.x+OS12V_INSET,r.y+r.h-9,controlStart-r.x-OS12V_INSET*2,FONT_SMALL,BL_DATUM,OS12V_MUTED,OS12V_SURFACE);
  for(HubRect b:{minus,plus}){tft.fillRoundRect(b.x,b.y,b.w,b.h,10,OS12V_SURFACE2);tft.drawRoundRect(b.x,b.y,b.w,b.h,10,OS12V_LINE);}
  uiDrawFit("-",minus.x+minus.w/2,minus.y+minus.h/2,minus.w-8,FONT_LARGE,MC_DATUM,OS12V_ACCENT,OS12V_SURFACE2);
  uiDrawFit("+",plus.x+plus.w/2,plus.y+plus.h/2,plus.w-8,FONT_LARGE,MC_DATUM,OS12V_ACCENT,OS12V_SURFACE2);
  const int16_t valueX=minus.x+minus.w+6;
  const int16_t valueW=plus.x-valueX-6;
  uiDrawFit(value,valueX,r.y+r.h/2,valueW,FONT_SMALL,MC_DATUM,OS12V_TEXT,OS12V_SURFACE);
}
'''

OLD_STEPPER_GEOMETRY = (
    "const int16_t buttonW=44,buttonH=44,controlStart=r.x+r.w-204;",
    "HubRect minus=hr(controlStart,r.y+(r.h-buttonH)/2,buttonW,buttonH);",
    "HubRect plus=hr(r.x+r.w-buttonW-OS12V_INSET,r.y+(r.h-buttonH)/2,buttonW,buttonH);",
)

OLD_UPDATE_ACTION = '''  hubUi13InfoRow(hr(OS12V_INSET,190,W-OS12V_INSET*2,54),"Build Details","Local Portal","Source · artifact · recovery identity",C10_MUTED);
  hubV1125Action(hubUi13BackRect(),"Back",C10_ACCENT,true,false);
  hubV1125Action(hubUi13ActionRect(),"Local Portal",C10_ACCENT,true,false);
'''

NEW_UPDATE_ACTION = '''  hubUi13InfoRow(hr(OS12V_INSET,190,W-OS12V_INSET*2,54),"Build Details","Local Portal","Source · artifact · recovery identity",C10_MUTED);
  hubV1125Action(hubUi13BackRect(),"Back",C10_ACCENT,true,false);
  {const workshop::platform::UpdateState& u=workshopPlatformUpdateState();hubV1125Action(hubUi13ActionRect(),(u.phase==workshop::platform::UpdatePhase::Available&&u.updateAvailable)?"Install":"Check for update",C10_ACCENT,!u.busy,false);}
'''

OLD_CONFIRM_NAV = 'tft.fillScreen(C10_BG);drawHeader("Install Workshop OS?",nullptr,3);uiBottomNav(3,nullptr);'
NEW_CONFIRM_NAV = 'tft.fillScreen(C10_BG);drawHeader("Install Workshop OS?",nullptr,3);'

OLD_SYSTEM_DISPATCH = "if(g_ui12SystemView==4){drawUi13Diagnostics();return;}\n  (void)full;"
NEW_SYSTEM_DISPATCH = "if(g_ui12SystemView==4){drawUi13Diagnostics();return;}if(g_ui12SystemView==5){drawUi13UpdateConfirm();return;}\n  (void)full;"

# drawSystem is defined after drawUi13UpdateConfirm, so no forward declaration is needed.

TAB_BAR_LIVE = '''// The tab bar's touch zones are live only where the tab bar is drawn. Mirrors
// drawMore (root, Tools and Display Expert except the rotation preview draw it;
// More views 1-12 do not) and drawSystem (only the hidden Hardware pages draw
// it). Every other hub screen draws it.
static bool hubTabBarLive(ScreenState cur) {
  if(cur==SCREEN_HUB_MORE){
    if(g_displayExperienceView)return !g_rotationPreviewMode;
    if(g_toolsView)return true;
    return g_ui12SettingsView<1||g_ui12SettingsView>12;
  }
  if(cur==SCREEN_HUB_SYSTEM)return g_audioSettingsView;
  return true;
}

bool smartHubHandleTouch(uint16_t rawX, uint16_t rawY, bool longPress) {'''

OLD_NAV_TOUCH = "  for(uint8_t i=0;i<4;i++)if(hubNavRect(i).contains(x,y)){if(i==0)setPage(SCREEN_HUB_HOME);"
NEW_NAV_TOUCH = "  if(hubTabBarLive(cur))for(uint8_t i=0;i<4;i++)if(hubNavRect(i).contains(x,y)){if(i==0)setPage(SCREEN_HUB_HOME);"


def load(path: Path) -> str:
    if not path.exists():
        raise PatchError(f"missing {path}")
    return path.read_text(encoding="utf-8")


def save(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise PatchError(f"{label}: expected exactly one anchor, found {count}")
    return text.replace(old, new, 1)


def patch_smart_hub(repo: Path) -> None:
    path = repo / "src" / "smart_hub.cpp"
    text = load(path)
    text = replace_once(text, OLD_MINUS_RECT, NEW_MINUS_RECT, "stepper touch rectangles")
    for needle in OLD_STEPPER_GEOMETRY:
        if needle not in text:
            raise PatchError(f"stepper row geometry changed upstream of the hotfix: {needle}")
    text = replace_cpp_function(text, STEPPER_SIGNATURE, NEW_STEPPER, "stepper row")
    text = replace_once(text, OLD_UPDATE_ACTION, NEW_UPDATE_ACTION, "Software Update action label")
    text = replace_once(text, OLD_CONFIRM_NAV, NEW_CONFIRM_NAV, "install confirmation tab bar")
    text = replace_once(text, OLD_SYSTEM_DISPATCH, NEW_SYSTEM_DISPATCH, "install confirmation draw case")
    text = replace_once(text, "bool smartHubHandleTouch(uint16_t rawX, uint16_t rawY, bool longPress) {", TAB_BAR_LIVE, "tab bar predicate")
    text = replace_once(text, OLD_NAV_TOUCH, NEW_NAV_TOUCH, "tab bar hit test")
    save(path, text)


def apply(repo: Path) -> None:
    build_path = repo / "include" / "smart_home_build.h"
    build = load(build_path)
    if "WORKSHOP_OS_PORTAL_SIGNIN_RESTORED" not in build:
        raise PatchError("touch hotfix runs after apply_workshop_os12_portal_signin_restore.py")
    if BUILD_MARKER in build:
        raise PatchError("touch hotfix is already applied")
    patch_smart_hub(repo)
    save(build_path, build.rstrip() + "\n" + BUILD_MARKER + "\n")
    print("Workshop OS 12 More/System touch hotfix applied")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    if not args.apply:
        raise SystemExit("refusing to modify source without --apply")
    try:
        apply(Path(args.repo).resolve())
    except PatchError as exc:
        raise SystemExit(f"FAIL: {exc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
