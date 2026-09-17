#!/usr/bin/env python3
"""Apply Workshop OS 12 UX v3 physical-fit/navigation corrections.

This pass is intentionally narrow and runs after the hierarchy and geometry
passes. It corrects defects proven on the physical 480x320 WS350 without
changing printer-control, recovery, update, media, or inventory authority.
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path


class PatchError(RuntimeError):
    pass


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


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise PatchError(f"{label}: expected one anchor, found {count}")
    return text.replace(old, new, 1)


EVIDENCE_ROW = r'''
static void hubOs12EvidenceRow(const HubRect& r,const char* title,const char* value,const char* detail,uint16_t valueColor=C10_MUTED) {
  hubOs12RowSurface(r);
  const int16_t inset=OS12_ROW_INSET_X;
  const int16_t valueW=176;
  const int16_t detailX=r.x+inset+valueW+8;
  const int16_t detailW=r.x+r.w-inset-detailX;
  uiDrawFit(title,r.x+inset,r.y+7,r.w-inset*2,FONT_SMALL,TL_DATUM,C10_MUTED,C10_BG);
  uiDrawFit(value,r.x+inset,r.y+r.h-10,valueW,FONT_BODY,BL_DATUM,valueColor,C10_BG);
  uiDrawFit(detail,detailX,r.y+r.h-10,detailW,FONT_SMALL,BR_DATUM,C10_MUTED,C10_BG);
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
    hubOs12EvidenceRow(printer,p&&p->config.name[0]?p->config.name:"Printer",state,online?"Live":"Connection",stateColor);
    if(printing||paused){char meta[32],rem[20];formatDuration(s->remainingMinutes,rem,sizeof(rem));snprintf(meta,sizeof(meta),"%u%% · %s left",(unsigned)s->progress,rem);hubOs12EvidenceRow(job,"Current Print",jobDisplayName(*s),meta,C10_TEXT);}
    else hubOs12EvidenceRow(job,"Current Print",online?"None":"Unknown",online?"Printer idle":"Printer unavailable",online?C10_TEXT:C10_MUTED);
    hubOs12EvidenceRow(inventory,"Filament Inventory","Unknown","No authoritative inventory evidence",C10_MUTED);
  } else {
    HubRect printer=hr(OS12_MARGIN_X,54,W-OS12_MARGIN_X*2,88),job=hr(OS12_MARGIN_X,150,W-OS12_MARGIN_X*2,96),inventory=hr(OS12_MARGIN_X,254,W-OS12_MARGIN_X*2,96);
    hubOs12EvidenceRow(printer,p&&p->config.name[0]?p->config.name:"Printer",state,online?"Live":"Connection",stateColor);
    hubOs12EvidenceRow(job,"Current Print",printing||paused?jobDisplayName(*s):(online?"None":"Unknown"),printing||paused?"Active job":"Printer state",C10_TEXT);
    hubOs12EvidenceRow(inventory,"Filament Inventory","Unknown","No authoritative inventory evidence",C10_MUTED);
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
    hubOs12EvidenceRow(attention,"Needs Attention",printerAlert?"Printer alert":"Unknown",printerAlert?"Printer evidence":"No inventory attention evidence",printerAlert?C10_ORANGE:C10_MUTED);
    hubOs12EvidenceRow(readiness,"Print Readiness","Undetermined","Requirements unknown",C10_MUTED);
    hubOs12EvidenceRow(loaded,"Loaded Spools","Unknown","Canonical placement unknown",C10_MUTED);
    hubOs12EvidenceRow(inventory,"Inventory","Unknown","Authoritative inventory unavailable",C10_MUTED);
  } else {
    HubRect attention=hr(OS12_MARGIN_X,56,W-OS12_MARGIN_X*2,78),readiness=hr(OS12_MARGIN_X,142,W-OS12_MARGIN_X*2,78),loaded=hr(OS12_MARGIN_X,228,W-OS12_MARGIN_X*2,78),inventory=hr(OS12_MARGIN_X,314,W-OS12_MARGIN_X*2,78);
    hubOs12EvidenceRow(attention,"Needs Attention",printerAlert?"Printer alert":"Unknown",printerAlert?"Printer evidence":"No inventory attention evidence",printerAlert?C10_ORANGE:C10_MUTED);
    hubOs12EvidenceRow(readiness,"Print Readiness","Undetermined","Requirements unknown",C10_MUTED);
    hubOs12EvidenceRow(loaded,"Loaded Spools","Unknown","Canonical placement unknown",C10_MUTED);
    hubOs12EvidenceRow(inventory,"Inventory","Unknown","Authoritative inventory unavailable",C10_MUTED);
  }
  hubMarkFrameDirty();g_dirty=false;
}
'''


def patch_bottom_nav(text: str) -> str:
    start, end, block = function_block(text, "static void uiBottomNav(")
    pattern = re.compile(r'static const char\* labels\[4\]=\{[^\n;]+\};')
    matches = pattern.findall(block)
    if len(matches) != 1:
        raise PatchError(f"bottom nav labels: expected one array, found {len(matches)}")
    block = pattern.sub('static const char* labels[4]={"Home","Printer","Workshop","More"};', block, count=1)
    return text[:start] + block + text[end:]


def patch_portal_routes(text: str) -> str:
    marker = "static uint8_t gOs12PortalParent = 0;"
    if marker not in text:
        anchor = "static constexpr int16_t OS12_MARGIN_X = 12;"
        if text.count(anchor) != 1:
            raise PatchError("geometry token anchor missing/non-unique")
        text = text.replace(anchor, marker + " // 0=System, 1=Network\n" + anchor, 1)

    network_old = 'if(hubUi13ActionRect().contains(x,y)){g_ui12SettingsView=0;g_ui12SystemView=1;g_networkSettingsView=false;g_audioSettingsView=false;setPage(SCREEN_HUB_SYSTEM);buzzerPlay(BUZZ_CLICK);g_dirty=true;return true;}'
    network_new = 'if(hubUi13ActionRect().contains(x,y)){setPage(SCREEN_HUB_SYSTEM);g_ui12SettingsView=0;g_networkSettingsView=false;g_audioSettingsView=false;gOs12PortalParent=1;g_ui12SystemView=1;buzzerPlay(BUZZ_CLICK);g_dirty=true;return true;}'
    text = replace_once(text, network_old, network_new, "Network -> Local Portal route")

    portal_back_old = 'if(g_ui12SystemView==1){if(hubUi12SystemBackRect().contains(x,y)){g_ui12SystemView=0;buzzerPlay(BUZZ_CLICK);g_dirty=true;}return true;}'
    portal_back_new = 'if(g_ui12SystemView==1){if(hubUi12SystemBackRect().contains(x,y)){g_ui12SystemView=0;if(gOs12PortalParent==1){setPage(SCREEN_HUB_MORE);g_ui12SettingsView=3;}gOs12PortalParent=0;buzzerPlay(BUZZ_CLICK);g_dirty=true;}return true;}'
    text = replace_once(text, portal_back_old, portal_back_new, "Local Portal Back route")

    system_action_old = 'if(hubUi13ActionRect().contains(x,y)){g_ui12SystemView=1;buzzerPlay(BUZZ_CLICK);g_dirty=true;return true;}'
    system_action_new = 'if(hubUi13ActionRect().contains(x,y)){gOs12PortalParent=0;g_ui12SystemView=1;buzzerPlay(BUZZ_CLICK);g_dirty=true;return true;}'
    text = replace_once(text, system_action_old, system_action_new, "System -> Local Portal route")
    return text


def patch_capture_catalog(web: str) -> str:
    aliases = ("settings-experience", "settings-printer", "settings-update")
    for view_id in aliases:
        pattern = re.compile(r'\s*\{\\?"id\\?":\\?"' + re.escape(view_id) + r'\\?"[^\n]*\n?')
        web, count = pattern.subn("", web, count=1)
        if count != 1:
            raise PatchError(f"capture catalog alias missing/non-unique: {view_id}")
    web = web.replace('{\\"id\\":\\"more\\",\\"label\\":\\"Settings\\"', '{\\"id\\":\\"more\\",\\"label\\":\\"More\\"')
    web = web.replace('{"id":"more","label":"Settings"', '{"id":"more","label":"More"')
    return web


def apply(repo: Path) -> None:
    hub_path = repo / "src" / "smart_hub.cpp"
    text = load(hub_path)
    text = patch_bottom_nav(text)
    text = replace_function(text, "static void hubOs12EvidenceRow(", EVIDENCE_ROW)
    text = replace_function(text, "static void drawHome(bool full)", HOME)
    text = replace_function(text, "static void drawWorkshop(bool full)", WORKSHOP)
    text = patch_portal_routes(text)
    hub_path.write_text(text, encoding="utf-8")

    web_path = repo / "src" / "web_server.cpp"
    web = patch_capture_catalog(load(web_path))
    web_path.write_text(web, encoding="utf-8")

    print("Workshop OS 12 UX v3 physical-fit/navigation corrections installed")


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
