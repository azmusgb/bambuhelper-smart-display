#!/usr/bin/env python3
"""Apply targeted 480x320 refinements from WS350 physical acceptance evidence.

Scope is presentation only: Home hierarchy, Workshop density/labeling,
Date & Time clarity, and Software Update clarity. No inventory, printer,
update, recovery, or command authority is changed.
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path




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
    line = False
    block = False
    i = brace
    while i < len(text):
        c = text[i]
        n = text[i + 1] if i + 1 < len(text) else ""
        if line:
            if c == "\n":
                line = False
        elif block:
            if c == "*" and n == "/":
                block = False
                i += 1
        elif string:
            if escape:
                escape = False
            elif c == "\\":
                escape = True
            elif c == string:
                string = None
        elif c == "/" and n == "/":
            line = True
            i += 1
        elif c == "/" and n == "*":
            block = True
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


def replace_function(text: str, signature: str, replacement: str) -> str:
    start = text.find(signature)
    if start < 0 or text.find(signature, start + 1) >= 0:
        raise PatchError(f"function missing/non-unique: {signature}")
    end = braced_end(text, start, signature)
    return text[:start] + replacement.strip() + text[end:]


HOME = r'''
static void drawHome(bool full) {
  (void)full;
  const int16_t W=tft.width();
  const bool configured=workshopPlatformState().configuredPrinterCount>0;
  const PrinterSlot* p=configured?&displayedPrinter():nullptr;
  const BambuState* s=p?&p->state:nullptr;
  if(g_ambientEnabled&&g_ambientActive){drawAmbientHome(p,s);return;}

  const uint8_t os12Slot=rotState.displayIndex<MAX_PRINTERS?rotState.displayIndex:0;
  const bool paused=configured&&workshopPlatformPrinterPaused(os12Slot);
  const bool printing=configured&&workshopPlatformPrinterPrinting(os12Slot);
  const bool online=configured&&workshopPlatformPrinterOnline(os12Slot);
  const bool alert=s&&uiHmsCount(*s)>0;
  const uint16_t stateColor=!configured?C10_MUTED:(!online?C10_RED:(alert?C10_RED:(paused?C10_ORANGE:(printing?C10_ACCENT:C10_GREEN))));
  const char* state=!configured?"Set Up":(!online?"Offline":(alert?"Needs Attention":(paused?"Paused":(printing?"Printing":"Ready"))));

  tft.fillScreen(C10_BG);
  drawHeader("Home",nullptr,0);
  uiBottomNav(0,nullptr);

  HubRect printer=hr(OS12_MARGIN_X,48,W-OS12_MARGIN_X*2,64);
  HubRect job=hr(OS12_MARGIN_X,118,W-OS12_MARGIN_X*2,68);
  HubRect inventory=hr(OS12_MARGIN_X,192,W-OS12_MARGIN_X*2,60);

  const char* printerName=p&&p->config.name[0]?p->config.name:"Printer";
  hubOs12EvidenceRow(
      printer,
      "PRINTER STATUS",
      state,
      configured?printerName:"No printer configured",
      stateColor);

  if(printing||paused){
    char meta[40],rem[20];
    formatDuration(s->remainingMinutes,rem,sizeof(rem));
    snprintf(meta,sizeof(meta),"%u%% - %s left",(unsigned)s->progress,rem);
    hubOs12EvidenceRow(job,"PRINT JOB",jobDisplayName(*s),meta,C10_TEXT);
  }else{
    hubOs12EvidenceRow(
        job,
        "PRINT JOB",
        online?"No active print":"Unknown",
        online?"Printer is idle":"No fresh printer evidence",
        online?C10_TEXT:C10_MUTED);
  }

  hubOs12EvidenceRow(
      inventory,
      "Filament Inventory",
      "Unknown",
      "No authoritative inventory evidence",
      C10_MUTED);

  hubMarkFrameDirty();
  g_dirty=false;
}
'''

WORKSHOP = r'''
static void drawWorkshop(bool full) {
  (void)full;
  const int16_t W=tft.width();
  tft.fillScreen(C10_BG);
  drawHeader("Workshop",nullptr,2);
  uiBottomNav(2,nullptr);

  const BambuState* s=isAnyPrinterConfigured()?&displayedPrinter().state:nullptr;
  const bool printerAlert=s&&uiHmsCount(*s)>0;

  HubRect attention=hr(OS12_MARGIN_X,48,W-OS12_MARGIN_X*2,60);
  HubRect readiness=hr(OS12_MARGIN_X,112,W-OS12_MARGIN_X*2,60);
  HubRect inventory=hr(OS12_MARGIN_X,176,W-OS12_MARGIN_X*2,72);

  hubOs12EvidenceRow(
      attention,
      "ATTENTION",
      printerAlert?"Printer alert":"Inventory unknown",
      printerAlert?"Review printer diagnostics":"No authoritative inventory attention evidence",
      printerAlert?C10_ORANGE:C10_MUTED);

  hubOs12EvidenceRow(
      readiness,
      "Print Readiness",
      "Undetermined",
      "Print requirements or inventory evidence missing",
      C10_MUTED);

  hubOs12EvidenceRow(
      inventory,
      "Loaded Spools",
      "Unknown",
      "Canonical placement unknown",
      C10_MUTED);

  hubMarkFrameDirty();
  g_dirty=false;
}
'''

DATE_TIME = r'''
static void drawUi13DateTime() {
  tft.fillScreen(C10_BG);
  drawHeader("Date & Time",nullptr,3);

  hubUi13StepperRow(
      hubUi13RowRect(0),
      "Time Zone",
      hubTimezoneLabel(),
      "Use - / + to change",
      C10_ACCENT);

  hubUi13ToggleRow(
      hubUi13RowRect(1),
      "24-Hour Clock",
      netSettings.use24h?"Showing 24-hour time":"Showing 12-hour time",
      netSettings.use24h,
      C10_ACCENT);

  hubUi13StepperRow(
      hubUi13RowRect(2),
      "Date Format",
      hubDateFormatLabel(netSettings.dateFormat),
      "Use - / + to change",
      C10_ACCENT);

  hubV1125Action(hubUi13BackRect(),"Back",C10_ACCENT,true,false);
  hubV1125Action(hubUi13ActionRect(),"Done",C10_ACCENT,true,false);
  hubMarkFrameDirty();
  g_dirty=false;
}
'''

UPDATE = r'''
static void drawUi13SoftwareUpdate() {
  const int16_t W=tft.width();
  tft.fillScreen(C10_BG);
  drawHeader("Software Update",nullptr,3);

  HubRect hero=hr(OS12_MARGIN_X,48,W-OS12_MARGIN_X*2,76);
  hubV1125Card(hero,C10_ACCENT,true);
  char ver[40];
  snprintf(ver,sizeof(ver),"Workshop OS %s",SMART_HOME_VERSION);
  uiDrawFit("CURRENT VERSION",hero.x+16,hero.y+10,hero.w-32,FONT_SMALL,TL_DATUM,C10_MUTED,C10_SURFACE_2);
  uiDrawFit(ver,hero.x+16,hero.y+31,hero.w-32,FONT_LARGE,TL_DATUM,C10_TEXT,C10_SURFACE_2);

  HubRect stateRow=hr(OS12_MARGIN_X,132,W-OS12_MARGIN_X*2,54);
  HubRect methodRow=hr(OS12_MARGIN_X,190,W-OS12_MARGIN_X*2,54);
  hubUi13InfoRow(stateRow,"Release State","Candidate","Physical acceptance required",C10_ORANGE);
  hubUi13InfoRow(methodRow,"Update Method","Local Portal","Only exact validated artifacts",C10_ACCENT);

  hubV1125Action(hubUi13BackRect(),"Back",C10_ACCENT,true,false);
  hubV1125Action(hubUi13ActionRect(),"Local Portal",C10_ACCENT,true,false);
  hubMarkFrameDirty();
  g_dirty=false;
}
'''


def patch_workshop_catalog(web: str) -> str:
    lines = web.splitlines(keepends=True)
    hits = []
    for i, line in enumerate(lines):
        normalized = line.replace('\\\"', '"')
        if '"id":"workshop"' in normalized:
            hits.append(i)
    if len(hits) != 1:
        raise PatchError(f"Workshop capture catalog entry expected once, found {len(hits)}")

    i = hits[0]
    line = lines[i]
    updated, count = re.subn(r'("label"\s*:\s*")Tools(")', r'\1Workshop\2', line, count=1)
    if count == 0:
        updated, count = re.subn(r'(\\\"label\\\"\s*:\s*\\\")Tools(\\\")', r'\1Workshop\2', line, count=1)
    if count == 0 and "Workshop" not in line:
        raise PatchError("Workshop catalog entry did not contain the expected Tools label")
    lines[i] = updated
    return "".join(lines)


def apply(repo: Path) -> None:
    hub_path = repo / "src" / "smart_hub.cpp"
    hub = load(hub_path)
    for signature, replacement in (
        ("static void drawHome(bool full)", HOME),
        ("static void drawWorkshop(bool full)", WORKSHOP),
        ("static void drawUi13DateTime()", DATE_TIME),
        ("static void drawUi13SoftwareUpdate()", UPDATE),
    ):
        hub = replace_function(hub, signature, replacement)
    hub_path.write_text(hub, encoding="utf-8")

    web_path = repo / "src" / "web_server.cpp"
    web = patch_workshop_catalog(load(web_path))
    web_path.write_text(web, encoding="utf-8")

    print("Workshop OS 12 physical acceptance UI refinements applied")


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
