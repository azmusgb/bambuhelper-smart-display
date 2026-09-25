#!/usr/bin/env python3
"""Apply the OS12 hierarchical UX architecture pass to reconstructed WS350 UI.

This is a composition/navigation refactor only. It preserves printer-control,
recovery, update, media, and inventory authority boundaries.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import sys as _sys
from pathlib import Path as _Path
_here = _Path(__file__).resolve().parent
if str(_here) not in _sys.path:
    _sys.path.insert(0, str(_here))
from scripts.smart_home_patch_utils import PatchError




def load(path: Path) -> str:
    if not path.is_file():
        raise PatchError(f"missing reconstructed source: {path}")
    return path.read_text(encoding="utf-8")


def braced_end(text: str, start: int, label: str) -> int:
    brace = text.find("{", start)
    if brace < 0:
        raise PatchError(f"{label}: opening brace missing")
    depth = 0
    string = None
    escape = False
    line_comment = False
    block_comment = False
    i = brace
    while i < len(text):
        c = text[i]
        n = text[i + 1] if i + 1 < len(text) else ""
        if line_comment:
            if c == "\n":
                line_comment = False
        elif block_comment:
            if c == "*" and n == "/":
                block_comment = False
                i += 1
        elif string:
            if escape:
                escape = False
            elif c == "\\":
                escape = True
            elif c == string:
                string = None
        elif c == "/" and n == "/":
            line_comment = True
            i += 1
        elif c == "/" and n == "*":
            block_comment = True
            i += 1
        elif c in ('"', "'"):
            string = c
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    raise PatchError(f"{label}: closing brace missing")


def function_block(text: str, signature: str) -> tuple[int, int, str]:
    start = text.find(signature)
    if start < 0 or text.find(signature, start + 1) >= 0:
        raise PatchError(f"function missing/non-unique: {signature}")
    end = braced_end(text, start, signature)
    return start, end, text[start:end]


def replace_function(text: str, signature: str, replacement: str) -> str:
    start, end, _ = function_block(text, signature)
    return text[:start] + replacement.strip() + text[end:]


def remove_bottom_nav(text: str, signature: str) -> str:
    start, end, block = function_block(text, signature)
    if "uiBottomNav(" not in block:
        return text
    import re
    block = re.sub(r"\s*uiBottomNav\([^;]+;", "", block)
    return text[:start] + block + text[end:]


BASE_HELPERS = r'''
static void hubOs12RowSurface(const HubRect& r) {
  tft.fillRect(r.x,r.y,r.w,r.h,C10_BG);
  tft.drawFastHLine(r.x+12,r.y+r.h-1,r.w-24,C10_SEPARATOR);
}

static void hubOs12NavRow(const HubRect& r,const char* title,const char* detail,uint16_t valueColor=C10_MUTED) {
  hubOs12RowSurface(r);
  uiDrawFit(title,r.x+14,r.y+9,r.w-68,FONT_BODY,TL_DATUM,C10_TEXT,C10_BG);
  uiDrawFit(detail,r.x+14,r.y+r.h-9,r.w-68,FONT_SMALL,BL_DATUM,valueColor,C10_BG);
  uiDrawFit(">",r.x+r.w-18,r.y+r.h/2,20,FONT_BODY,MR_DATUM,C10_ACCENT,C10_BG);
}

static void hubOs12EvidenceRow(const HubRect& r,const char* title,const char* value,const char* detail,uint16_t valueColor=C10_MUTED) {
  hubOs12RowSurface(r);
  uiDrawFit(title,r.x+14,r.y+8,r.w-160,FONT_SMALL,TL_DATUM,C10_MUTED,C10_BG);
  uiDrawFit(value,r.x+14,r.y+27,r.w-160,FONT_BODY,TL_DATUM,valueColor,C10_BG);
  uiDrawFit(detail,r.x+r.w-146,r.y+r.h/2,132,FONT_SMALL,MR_DATUM,C10_MUTED,C10_BG);
}
'''

INFO_ROW = r'''
static void hubUi13InfoRow(const HubRect& r,const char* label,const char* value,const char* detail,uint16_t accent=C10_ACCENT) {
  hubOs12EvidenceRow(r,label,value,detail,accent);
}
'''

TOGGLE_ROW = r'''
static void hubUi13ToggleRow(const HubRect& r,const char* label,const char* detail,bool on,uint16_t accent=C10_ACCENT) {
  hubOs12RowSurface(r);
  uiDrawFit(label,r.x+12,r.y+8,r.w-108,FONT_BODY,TL_DATUM,C10_TEXT,C10_BG);
  uiDrawFit(detail,r.x+12,r.y+r.h-9,r.w-108,FONT_SMALL,BL_DATUM,C10_MUTED,C10_BG);
  HubRect sw=hr(r.x+r.w-82,r.y+8,66,r.h-16);
  tft.fillRoundRect(sw.x,sw.y,sw.w,sw.h,sw.h/2,on?accent:C10_SURFACE_2);
  tft.drawRoundRect(sw.x,sw.y,sw.w,sw.h,sw.h/2,on?accent:C10_SEPARATOR);
  const int16_t d=sw.h-8;
  const int16_t cx=on?(sw.x+sw.w-4-d/2):(sw.x+4+d/2);
  tft.fillCircle(cx,sw.y+sw.h/2,d/2,C10_TEXT);
}
'''

STEPPER_ROW = r'''
static void hubUi13StepperRow(const HubRect& r,const char* label,const char* value,const char* detail,uint16_t accent=C10_ACCENT) {
  hubOs12RowSurface(r);
  uiDrawFit(label,r.x+12,r.y+8,r.w-248,FONT_SMALL,TL_DATUM,C10_MUTED,C10_BG);
  uiDrawFit(detail,r.x+12,r.y+r.h-9,r.w-248,FONT_SMALL,BL_DATUM,C10_MUTED,C10_BG);
  HubRect minus=hr(r.x+r.w-236,r.y+4,50,r.h-8),plus=hr(r.x+r.w-58,r.y+4,50,r.h-8);
  tft.fillRoundRect(minus.x,minus.y,minus.w,minus.h,10,C10_SURFACE_2);
  tft.fillRoundRect(plus.x,plus.y,plus.w,plus.h,10,C10_SURFACE_2);
  uiDrawFit("-",minus.x+minus.w/2,minus.y+minus.h/2,minus.w-8,FONT_LARGE,MC_DATUM,accent,C10_SURFACE_2);
  uiDrawFit("+",plus.x+plus.w/2,plus.y+plus.h/2,plus.w-8,FONT_LARGE,MC_DATUM,accent,C10_SURFACE_2);
  uiDrawFit(value,r.x+r.w-176,r.y+r.h/2,110,FONT_BODY,MC_DATUM,C10_TEXT,C10_BG);
}
'''

SETTINGS_RECTS = r'''
static HubRect hubUi12SettingsRect(uint8_t i) {
  const int16_t W=tft.width();
  if(i>=4)return hr(0,0,0,0);
  if(hubLandscape())return hr(8,48+i*50,W-16,48);
  return hr(8,58+i*76,W-16,70);
}
'''

HOME = r'''
static void drawHome(bool full) {
  (void)full;
  const int16_t W=tft.width();
  const bool configured=isAnyPrinterConfigured();
  const PrinterSlot* p=configured?&displayedPrinter():nullptr;
  const BambuState* s=p?&p->state:nullptr;
  if(g_ambientEnabled&&g_ambientActive){drawAmbientHome(p,s);return;}
  tft.fillScreen(C10_BG);drawHeader("Home",nullptr,0);uiBottomNav(0,nullptr);
  const bool paused=s&&s->gcodeStateId==GCODE_PAUSE;
  const bool printing=s&&s->printing;
  const bool online=s&&s->connected;
  const bool alert=s&&uiHmsCount(*s)>0;
  const uint16_t stateColor=!configured?C10_MUTED:(!online?C10_RED:(alert?C10_RED:(paused?C10_ORANGE:(printing?C10_ACCENT:C10_GREEN))));
  const char* state=!configured?"Set Up":(!online?"Offline":(alert?"Needs Attention":(paused?"Paused":(printing?"Printing":"Ready"))));
  if(hubLandscape()) {
    HubRect printer=hr(8,46,W-16,66),job=hr(8,112,W-16,70),inventory=hr(8,182,W-16,70);
    hubOs12EvidenceRow(printer,p&&p->config.name[0]?p->config.name:"Printer",state,online?"Live printer state":"Connection state",stateColor);
    if(printing||paused){char meta[40],rem[20];formatDuration(s->remainingMinutes,rem,sizeof(rem));snprintf(meta,sizeof(meta),"%u%% - %s left",(unsigned)s->progress,rem);hubOs12EvidenceRow(job,"Current Print",jobDisplayName(*s),meta,C10_TEXT);}
    else hubOs12EvidenceRow(job,"Current Print",online?"None":"Unknown",online?"Printer idle":"Printer unavailable",online?C10_TEXT:C10_MUTED);
    hubOs12EvidenceRow(inventory,"Filament Inventory","Unknown","Inventory evidence unavailable",C10_MUTED);
  } else {
    HubRect printer=hr(8,54,W-16,88),job=hr(8,142,W-16,100),inventory=hr(8,242,W-16,100);
    hubOs12EvidenceRow(printer,p&&p->config.name[0]?p->config.name:"Printer",state,online?"Live state":"Connection",stateColor);
    hubOs12EvidenceRow(job,"Current Print",printing||paused?jobDisplayName(*s):(online?"None":"Unknown"),printing||paused?"Active job":"Printer state",C10_TEXT);
    hubOs12EvidenceRow(inventory,"Filament Inventory","Unknown","Inventory evidence unavailable",C10_MUTED);
  }
  hubMarkFrameDirty();g_dirty=false;
}
'''

WORKSHOP = r'''
static void drawWorkshop(bool full) {
  (void)full;
  const int16_t W=tft.width();
  tft.fillScreen(C10_BG);drawHeader("Workshop",nullptr,2);uiBottomNav(2,nullptr);
  const BambuState* s=isAnyPrinterConfigured()?&displayedPrinter().state:nullptr;
  const bool printerAlert=s&&uiHmsCount(*s)>0;
  if(hubLandscape()) {
    HubRect attention=hr(8,48,W-16,50),readiness=hr(8,98,W-16,50),loaded=hr(8,148,W-16,50),inventory=hr(8,198,W-16,50);
    hubOs12EvidenceRow(attention,"Needs Attention",printerAlert?"Printer alert":"Unknown",printerAlert?"Printer evidence":"Inventory evidence unavailable",printerAlert?C10_ORANGE:C10_MUTED);
    hubOs12EvidenceRow(readiness,"Print Readiness","Undetermined","Requirements/evidence unavailable",C10_MUTED);
    hubOs12EvidenceRow(loaded,"Loaded Spools","Unknown","No canonical placement evidence",C10_MUTED);
    hubOs12EvidenceRow(inventory,"Inventory","Unknown","Awaiting authoritative inventory evidence",C10_MUTED);
  } else {
    HubRect attention=hr(8,56,W-16,78),readiness=hr(8,134,W-16,78),loaded=hr(8,212,W-16,78),inventory=hr(8,290,W-16,78);
    hubOs12EvidenceRow(attention,"Needs Attention",printerAlert?"Printer alert":"Unknown","Evidence status",printerAlert?C10_ORANGE:C10_MUTED);
    hubOs12EvidenceRow(readiness,"Print Readiness","Undetermined","Requirements unknown",C10_MUTED);
    hubOs12EvidenceRow(loaded,"Loaded Spools","Unknown","Placement evidence unavailable",C10_MUTED);
    hubOs12EvidenceRow(inventory,"Inventory","Unknown","Authoritative evidence unavailable",C10_MUTED);
  }
  hubMarkFrameDirty();g_dirty=false;
}
'''


def apply(repo: Path) -> None:
    path = repo / "src/smart_hub.cpp"
    text = load(path)

    if "static void hubOs12RowSurface(" not in text:
        pos = text.find("static void drawHome(bool full)")
        if pos < 0:
            raise PatchError("Home renderer anchor missing")
        text = text[:pos] + BASE_HELPERS + "\n" + text[pos:]

    text = replace_function(text,"static void hubUi13InfoRow(",INFO_ROW)
    text = replace_function(text,"static void hubUi13ToggleRow(",TOGGLE_ROW)
    text = replace_function(text,"static void hubUi13StepperRow(",STEPPER_ROW)
    text = replace_function(text,"static HubRect hubUi12SettingsRect(",SETTINGS_RECTS)

    child_functions = (
        "static void drawUi13Display()","static void drawUi13AfterPrint()","static void drawUi13Sound()",
        "static void drawUi13PrinterAlerts()","static void drawUi13AlertSignals()","static void drawUi13Network()",
        "static void drawUi13PrinterPower()","static void drawUi13PowerOptions()","static void drawUi13AutoOffConfirm()",
        "static void drawUi13DateTime()","static void drawUi13SoftwareUpdate()","static void drawUi13Diagnostics()",
        "static void drawUi12PortalAccess()","static void drawUi12Experience()","static void drawUi12PrinterConnection()",
        "static void drawUi12SoftwareUpdate()","static void drawOs12Media()","static void drawOs12MediaLab()",
        "static void drawSystem(bool full)",
    )
    for sig in child_functions:
        if text.find(sig) >= 0:
            text = remove_bottom_nav(text,sig)

    start,end,more=function_block(text,"static void drawMore(bool full)")
    replacements = (
        ('hubUi12SettingsCard(hubUi12SettingsRect(0),"Display & Appearance","Brightness, standby, after print",C10_ACCENT,false);','hubOs12NavRow(hubUi12SettingsRect(0),"Display & Appearance","Brightness, standby, after print",C10_MUTED);'),
        ('hubUi12SettingsCard(hubUi12SettingsRect(1),"Sounds & Alerts","Sounds, touch feedback, printer alerts",C10_ACCENT,false);','hubOs12NavRow(hubUi12SettingsRect(1),"Sound & Microphone","Volume, microphone, event sounds",C10_MUTED);'),
        ('hubUi12SettingsCard(hubUi12SettingsRect(2),"Network",wifi?"Connected":"Offline",wifi?C10_GREEN:C10_ORANGE,false);','hubOs12NavRow(hubUi12SettingsRect(2),"Network",wifi?"Connected":"Offline",wifi?C10_GREEN:C10_ORANGE);'),
        ('hubUi12SettingsCard(hubUi12SettingsRect(3),"Printer & Power",!configured?"Not configured":(printerConnected?"Connected":"Offline"),printerConnected?C10_GREEN:(configured?C10_ORANGE:C10_MUTED),false);','hubOs12NavRow(hubUi12SettingsRect(3),"System",deviceHealthy?"Ready":"Needs attention",deviceHealthy?C10_GREEN:C10_ORANGE);'),
        ('hubUi12SettingsCard(hubUi12SettingsRect(4),"System",deviceHealthy?"Ready":"Needs attention",deviceHealthy?C10_GREEN:C10_ORANGE,true);',''),
    )
    for old,new in replacements:
        if old not in more:
            raise PatchError(f"More flatten anchor missing: {old[:48]}")
        more=more.replace(old,new,1)
    text=text[:start]+more+text[end:]

    start,end,system=function_block(text,"static void drawSystem(bool full)")
    system_replacements = (
        ('hubUi12SettingsCard(hubUi13SystemCardRect(0),"Device Health",deviceHealthy?"Healthy":"Needs attention",deviceHealthy?C10_GREEN:C10_ORANGE,false);','hubOs12NavRow(hubUi13SystemCardRect(0),"Device Health",deviceHealthy?"Healthy":"Needs attention",deviceHealthy?C10_GREEN:C10_ORANGE);'),
        ('hubUi12SettingsCard(hubUi13SystemCardRect(1),"Connectivity",!wifi?"Offline":(printerOk?"Network + printer":"Network connected"),wifi?C10_GREEN:C10_ORANGE,false);','hubOs12NavRow(hubUi13SystemCardRect(1),"Printer & Power",!configured?"Not configured":(printerOk?"Connected":"Offline"),printerOk?C10_GREEN:(configured?C10_ORANGE:C10_MUTED));'),
        ('hubUi12SettingsCard(hubUi13SystemCardRect(2),"Date & Time",hubTimezoneLabel(),C10_ACCENT,false);','hubOs12NavRow(hubUi13SystemCardRect(2),"Date & Time",hubTimezoneLabel(),C10_MUTED);'),
        ('hubUi12SettingsCard(hubUi13SystemCardRect(3),"Software Update","Version and update options",C10_ACCENT,false);','hubOs12NavRow(hubUi13SystemCardRect(3),"Software Update","Version and update options",C10_MUTED);'),
    )
    for old,new in system_replacements:
        if old not in system:
            raise PatchError(f"System flatten anchor missing: {old[:48]}")
        system=system.replace(old,new,1)
    text=text[:start]+system+text[end:]

    root_old='for(uint8_t i=0;i<5;i++)if(hubUi12SettingsRect(i).contains(x,y)){' 
    root_new='for(uint8_t i=0;i<4;i++)if(hubUi12SettingsRect(i).contains(x,y)){' 
    if root_old not in text:
        raise PatchError("More root touch loop anchor missing")
    text=text.replace(root_old,root_new,1)
    old_route='if(i<4){g_ui12SettingsView=(uint8_t)(i+1U);buzzerPlay(BUZZ_CLICK);g_dirty=true;}\n      else{g_ui12SettingsView=0;setPage(SCREEN_HUB_SYSTEM);buzzerPlay(BUZZ_CLICK);g_dirty=true;}'
    new_route='if(i<3){g_ui12SettingsView=(uint8_t)(i+1U);buzzerPlay(BUZZ_CLICK);g_dirty=true;}\n      else{g_ui12SettingsView=0;setPage(SCREEN_HUB_SYSTEM);buzzerPlay(BUZZ_CLICK);g_dirty=true;}'
    if old_route not in text:
        raise PatchError("More root routing anchor missing")
    text=text.replace(old_route,new_route,1)

    old_system_route='else if(i==1){g_ui12SettingsView=3;setPage(SCREEN_HUB_MORE);}'
    new_system_route='else if(i==1){g_ui12SettingsView=4;setPage(SCREEN_HUB_MORE);}'
    if old_system_route not in text:
        raise PatchError("System Printer & Power routing anchor missing")
    text=text.replace(old_system_route,new_system_route,1)

    text=replace_function(text,"static void drawHome(bool full)",HOME)
    text=replace_function(text,"static void drawWorkshop(bool full)",WORKSHOP)

    path.write_text(text,encoding="utf-8")
    print("Workshop OS 12 UX architecture overhaul installed")


def main() -> int:
    ap=argparse.ArgumentParser();ap.add_argument("--repo",required=True);ap.add_argument("--apply",action="store_true");args=ap.parse_args()
    if not args.apply: raise SystemExit("refusing to modify source without --apply")
    try: apply(Path(args.repo).resolve())
    except PatchError as exc: raise SystemExit(f"FAIL: {exc}") from exc
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
