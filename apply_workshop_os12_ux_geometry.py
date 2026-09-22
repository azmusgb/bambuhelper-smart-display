#!/usr/bin/env python3
"""Apply the Workshop OS 12 480x320 geometry/polish pass.

This pass intentionally does not alter navigation authority or device/inventory
semantics. It normalizes margins, row heights, action geometry, text columns,
and root-screen vertical rhythm after the hierarchical UX architecture pass.
"""
from __future__ import annotations

import argparse
from pathlib import Path


class PatchError(RuntimeError):
    pass


def load(path: Path) -> str:
    if not path.is_file():
        raise PatchError(f"missing reconstructed source: {path}")
    return path.read_text(encoding="utf-8")


def block_end(text: str, start: int, label: str) -> int:
    brace = text.find("{", start)
    if brace < 0:
        raise PatchError(f"{label}: opening brace missing")
    depth = 0
    string = None
    escape = False
    line = False
    block = False
    i = brace
    while i < len(text):
        c = text[i]
        n = text[i + 1] if i + 1 < len(text) else ""
        if line:
            if c == "\n": line = False
        elif block:
            if c == "*" and n == "/": block = False; i += 1
        elif string:
            if escape: escape = False
            elif c == "\\": escape = True
            elif c == string: string = None
        elif c == "/" and n == "/": line = True; i += 1
        elif c == "/" and n == "*": block = True; i += 1
        elif c in ('"', "'"): string = c
        elif c == "{": depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0: return i + 1
        i += 1
    raise PatchError(f"{label}: closing brace missing")


def function_block(text: str, signature: str) -> tuple[int, int, str]:
    start = text.find(signature)
    if start < 0 or text.find(signature, start + 1) >= 0:
        raise PatchError(f"function missing/non-unique: {signature}")
    end = block_end(text, start, signature)
    return start, end, text[start:end]


def replace_function(text: str, signature: str, replacement: str) -> str:
    start, end, _ = function_block(text, signature)
    return text[:start] + replacement.strip() + text[end:]


TOKENS = r'''
static constexpr int16_t OS12_MARGIN_X = 12;
static constexpr int16_t OS12_HEADER_H = 44;
static constexpr int16_t OS12_CONTENT_TOP = 48;
static constexpr int16_t OS12_ROW_H = 52;
static constexpr int16_t OS12_ROW_INSET_X = 14;
static constexpr int16_t OS12_SECTION_GAP = 8;
static constexpr int16_t OS12_ACTION_H = 52;
static constexpr int16_t OS12_ACTION_GAP = 8;
static constexpr int16_t OS12_BOTTOM_SAFE = 12;
static constexpr int16_t OS12_TRAILING_COL_W = 148;
'''

ROW_SURFACE = r'''
static void hubOs12RowSurface(const HubRect& r) {
  tft.fillRect(r.x,r.y,r.w,r.h,C10_BG);
  tft.drawFastHLine(r.x+OS12_ROW_INSET_X,r.y+r.h-1,r.w-(OS12_ROW_INSET_X*2),C10_SEPARATOR);
}
'''

NAV_ROW = r'''
static void hubOs12NavRow(const HubRect& r,const char* title,const char* detail,uint16_t valueColor=C10_MUTED) {
  hubOs12RowSurface(r);
  const int16_t rightPad=42;
  uiDrawFit(title,r.x+OS12_ROW_INSET_X,r.y+9,r.w-OS12_ROW_INSET_X-rightPad,FONT_BODY,TL_DATUM,C10_TEXT,C10_BG);
  uiDrawFit(detail,r.x+OS12_ROW_INSET_X,r.y+r.h-9,r.w-OS12_ROW_INSET_X-rightPad,FONT_SMALL,BL_DATUM,valueColor,C10_BG);
  uiDrawFit(">",r.x+r.w-OS12_ROW_INSET_X,r.y+r.h/2,20,FONT_BODY,MR_DATUM,C10_ACCENT,C10_BG);
}
'''

EVIDENCE_ROW = r'''
static void hubOs12EvidenceRow(const HubRect& r,const char* title,const char* value,const char* detail,uint16_t valueColor=C10_MUTED) {
  hubOs12RowSurface(r);
  const int16_t leftW=r.w-OS12_TRAILING_COL_W-OS12_ROW_INSET_X*2;
  const int16_t trailingX=r.x+r.w-OS12_TRAILING_COL_W-OS12_ROW_INSET_X;
  uiDrawFit(title,r.x+OS12_ROW_INSET_X,r.y+7,leftW,FONT_SMALL,TL_DATUM,C10_MUTED,C10_BG);
  uiDrawFit(value,r.x+OS12_ROW_INSET_X,r.y+26,leftW,FONT_BODY,TL_DATUM,valueColor,C10_BG);
  uiDrawFit(detail,trailingX,r.y+r.h/2,OS12_TRAILING_COL_W,FONT_SMALL,MR_DATUM,C10_MUTED,C10_BG);
}
'''

TOGGLE_ROW = r'''
static void hubUi13ToggleRow(const HubRect& r,const char* label,const char* detail,bool on,uint16_t accent=C10_ACCENT) {
  hubOs12RowSurface(r);
  const int16_t controlW=66;
  uiDrawFit(label,r.x+OS12_ROW_INSET_X,r.y+8,r.w-controlW-OS12_ROW_INSET_X*3,FONT_BODY,TL_DATUM,C10_TEXT,C10_BG);
  uiDrawFit(detail,r.x+OS12_ROW_INSET_X,r.y+r.h-9,r.w-controlW-OS12_ROW_INSET_X*3,FONT_SMALL,BL_DATUM,C10_MUTED,C10_BG);
  HubRect sw=hr(r.x+r.w-controlW-OS12_ROW_INSET_X,r.y+(r.h-36)/2,controlW,36);
  tft.fillRoundRect(sw.x,sw.y,sw.w,sw.h,18,on?accent:C10_SURFACE_2);
  tft.drawRoundRect(sw.x,sw.y,sw.w,sw.h,18,on?accent:C10_SEPARATOR);
  const int16_t d=28;
  const int16_t cx=on?(sw.x+sw.w-4-d/2):(sw.x+4+d/2);
  tft.fillCircle(cx,sw.y+sw.h/2,d/2,C10_TEXT);
}
'''

STEPPER_ROW = r'''
static void hubUi13StepperRow(const HubRect& r,const char* label,const char* value,const char* detail,uint16_t accent=C10_ACCENT) {
  hubOs12RowSurface(r);
  const int16_t buttonW=46;
  const int16_t buttonH=44;
  const int16_t plusX=r.x+r.w-OS12_ROW_INSET_X-buttonW;
  const int16_t minusX=plusX-OS12_ACTION_GAP-buttonW-92;
  uiDrawFit(label,r.x+OS12_ROW_INSET_X,r.y+7,minusX-r.x-OS12_ROW_INSET_X-8,FONT_SMALL,TL_DATUM,C10_MUTED,C10_BG);
  uiDrawFit(detail,r.x+OS12_ROW_INSET_X,r.y+r.h-8,minusX-r.x-OS12_ROW_INSET_X-8,FONT_SMALL,BL_DATUM,C10_MUTED,C10_BG);
  HubRect minus=hr(minusX,r.y+(r.h-buttonH)/2,buttonW,buttonH);
  HubRect plus=hr(plusX,r.y+(r.h-buttonH)/2,buttonW,buttonH);
  tft.fillRoundRect(minus.x,minus.y,minus.w,minus.h,10,C10_SURFACE_2);
  tft.fillRoundRect(plus.x,plus.y,plus.w,plus.h,10,C10_SURFACE_2);
  uiDrawFit("-",minus.x+minus.w/2,minus.y+minus.h/2,minus.w-8,FONT_LARGE,MC_DATUM,accent,C10_SURFACE_2);
  uiDrawFit("+",plus.x+plus.w/2,plus.y+plus.h/2,plus.w-8,FONT_LARGE,MC_DATUM,accent,C10_SURFACE_2);
  uiDrawFit(value,minus.x+buttonW+OS12_ACTION_GAP,r.y+r.h/2,84,FONT_BODY,MC_DATUM,C10_TEXT,C10_BG);
}
'''

SETTINGS_RECTS = r'''
static HubRect hubUi12SettingsRect(uint8_t i) {
  const int16_t W=tft.width();
  if(i>=4)return hr(0,0,0,0);
  if(hubLandscape())return hr(OS12_MARGIN_X,OS12_CONTENT_TOP+i*OS12_ROW_H,W-OS12_MARGIN_X*2,OS12_ROW_H);
  return hr(OS12_MARGIN_X,58+i*76,W-OS12_MARGIN_X*2,70);
}
'''

UI13_ROW_RECTS = r'''
static HubRect hubUi13RowRect(uint8_t i) {
  const int16_t W=tft.width();
  if(hubLandscape())return i<3?hr(OS12_MARGIN_X,OS12_CONTENT_TOP+i*56,W-OS12_MARGIN_X*2,54):hr(0,0,0,0);
  return i<3?hr(OS12_MARGIN_X,58+i*82,W-OS12_MARGIN_X*2,72):hr(0,0,0,0);
}
'''

BACK_RECT = r'''
static HubRect hubUi13BackRect() {
  const int16_t W=tft.width();
  return hubLandscape()?hr(OS12_MARGIN_X,320-OS12_BOTTOM_SAFE-OS12_ACTION_H,116,OS12_ACTION_H):hr(OS12_MARGIN_X,366,116,48);
}
'''

ACTION_RECT = r'''
static HubRect hubUi13ActionRect() {
  const int16_t W=tft.width();
  return hubLandscape()?hr(W-OS12_MARGIN_X-184,320-OS12_BOTTOM_SAFE-OS12_ACTION_H,184,OS12_ACTION_H):hr(W-188,366,176,48);
}
'''

SYSTEM_RECTS = r'''
static HubRect hubUi13SystemCardRect(uint8_t i) {
  const int16_t W=tft.width();
  if(i>=4)return hr(0,0,0,0);
  if(hubLandscape())return hr(OS12_MARGIN_X,OS12_CONTENT_TOP+i*OS12_ROW_H,W-OS12_MARGIN_X*2,OS12_ROW_H);
  return hr(OS12_MARGIN_X,52+i*74,W-OS12_MARGIN_X*2,66);
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
    HubRect printer=hr(OS12_MARGIN_X,48,W-OS12_MARGIN_X*2,58);
    HubRect job=hr(OS12_MARGIN_X,114,W-OS12_MARGIN_X*2,70);
    HubRect inventory=hr(OS12_MARGIN_X,192,W-OS12_MARGIN_X*2,60);
    hubOs12EvidenceRow(printer,p&&p->config.name[0]?p->config.name:"Printer",state,online?"Live printer state":"Connection state",stateColor);
    if(printing||paused){char meta[40],rem[20];formatDuration(s->remainingMinutes,rem,sizeof(rem));snprintf(meta,sizeof(meta),"%u%% - %s left",(unsigned)s->progress,rem);hubOs12EvidenceRow(job,"Current Print",jobDisplayName(*s),meta,C10_TEXT);}
    else hubOs12EvidenceRow(job,"Current Print",online?"None":"Unknown",online?"Printer idle":"Printer unavailable",online?C10_TEXT:C10_MUTED);
    hubOs12EvidenceRow(inventory,"Filament Inventory","Unknown","Authoritative evidence unavailable",C10_MUTED);
  } else {
    HubRect printer=hr(OS12_MARGIN_X,54,W-OS12_MARGIN_X*2,88),job=hr(OS12_MARGIN_X,150,W-OS12_MARGIN_X*2,96),inventory=hr(OS12_MARGIN_X,254,W-OS12_MARGIN_X*2,96);
    hubOs12EvidenceRow(printer,p&&p->config.name[0]?p->config.name:"Printer",state,online?"Live state":"Connection",stateColor);
    hubOs12EvidenceRow(job,"Current Print",printing||paused?jobDisplayName(*s):(online?"None":"Unknown"),printing||paused?"Active job":"Printer state",C10_TEXT);
    hubOs12EvidenceRow(inventory,"Filament Inventory","Unknown","Authoritative evidence unavailable",C10_MUTED);
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
    HubRect attention=hr(OS12_MARGIN_X,OS12_CONTENT_TOP,W-OS12_MARGIN_X*2,OS12_ROW_H);
    HubRect readiness=hr(OS12_MARGIN_X,OS12_CONTENT_TOP+OS12_ROW_H,W-OS12_MARGIN_X*2,OS12_ROW_H);
    HubRect loaded=hr(OS12_MARGIN_X,OS12_CONTENT_TOP+OS12_ROW_H*2,W-OS12_MARGIN_X*2,OS12_ROW_H);
    HubRect inventory=hr(OS12_MARGIN_X,OS12_CONTENT_TOP+OS12_ROW_H*3,W-OS12_MARGIN_X*2,OS12_ROW_H);
    hubOs12EvidenceRow(attention,"Needs Attention",printerAlert?"Printer alert":"Unknown",printerAlert?"Printer evidence":"Inventory evidence unavailable",printerAlert?C10_ORANGE:C10_MUTED);
    hubOs12EvidenceRow(readiness,"Print Readiness","Undetermined","Requirements/evidence unavailable",C10_MUTED);
    hubOs12EvidenceRow(loaded,"Loaded Spools","Unknown","No canonical placement evidence",C10_MUTED);
    hubOs12EvidenceRow(inventory,"Inventory","Unknown","Awaiting authoritative evidence",C10_MUTED);
  } else {
    HubRect attention=hr(OS12_MARGIN_X,56,W-OS12_MARGIN_X*2,78),readiness=hr(OS12_MARGIN_X,142,W-OS12_MARGIN_X*2,78),loaded=hr(OS12_MARGIN_X,228,W-OS12_MARGIN_X*2,78),inventory=hr(OS12_MARGIN_X,314,W-OS12_MARGIN_X*2,78);
    hubOs12EvidenceRow(attention,"Needs Attention",printerAlert?"Printer alert":"Unknown","Evidence status",printerAlert?C10_ORANGE:C10_MUTED);
    hubOs12EvidenceRow(readiness,"Print Readiness","Undetermined","Requirements unknown",C10_MUTED);
    hubOs12EvidenceRow(loaded,"Loaded Spools","Unknown","Placement evidence unavailable",C10_MUTED);
    hubOs12EvidenceRow(inventory,"Inventory","Unknown","Authoritative evidence unavailable",C10_MUTED);
  }
  hubMarkFrameDirty();g_dirty=false;
}
'''


def apply(repo: Path) -> None:
    path = repo / "src" / "smart_hub.cpp"
    text = load(path)

    # Token declarations must precede every function that consumes them. Earlier
    # revisions only checked whether the token *name* existed anywhere, which
    # allowed a later declaration to satisfy the patch while earlier functions
    # failed to compile. Normalize the declarations to the top of the anonymous
    # namespace on every application so reconstruction is deterministic.
    token_lines = tuple(line.strip() for line in TOKENS.strip().splitlines() if line.strip())
    for token in token_lines:
        count = text.count(token)
        if count > 1:
            raise PatchError(f"duplicate UX geometry token: {token}")
        if count == 1:
            text = text.replace(token, "", 1)

    namespace_anchor = "namespace {\n"
    pos = text.find(namespace_anchor)
    if pos < 0:
        raise PatchError("anonymous namespace anchor missing for UX geometry tokens")
    pos += len(namespace_anchor)
    text = text[:pos] + "\n" + TOKENS.strip() + "\n\n" + text[pos:]

    replacements = (
        ("static void hubOs12RowSurface(", ROW_SURFACE),
        ("static void hubOs12NavRow(", NAV_ROW),
        ("static void hubOs12EvidenceRow(", EVIDENCE_ROW),
        ("static void hubUi13ToggleRow(", TOGGLE_ROW),
        ("static void hubUi13StepperRow(", STEPPER_ROW),
        ("static HubRect hubUi12SettingsRect(", SETTINGS_RECTS),
        ("static HubRect hubUi13RowRect(", UI13_ROW_RECTS),
        ("static HubRect hubUi13BackRect()", BACK_RECT),
        ("static HubRect hubUi13ActionRect()", ACTION_RECT),
        ("static HubRect hubUi13SystemCardRect(", SYSTEM_RECTS),
        ("static void drawHome(bool full)", HOME),
        ("static void drawWorkshop(bool full)", WORKSHOP),
    )
    for signature, replacement in replacements:
        text = replace_function(text, signature, replacement)

    path.write_text(text, encoding="utf-8")
    print("Workshop OS 12 UX geometry polish installed")


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
        raise SystemExit(f"FAIL: {exc}") from exc
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
