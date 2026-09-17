#!/usr/bin/env python3
"""Apply the OS12 hierarchical UX architecture pass to reconstructed WS350 UI.

Goals:
- bottom navigation only on root destinations
- flattened list-style settings surfaces
- three interaction families: navigation row, command button, setting row
- materially reduced card/elevation nesting
- evidence-oriented Home and Workshop surfaces without inventing inventory facts
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


def braced_end(text: str, start: int, label: str) -> int:
    brace = text.find("{", start)
    if brace < 0:
        raise PatchError(f"{label}: opening brace missing")
    depth = 0
    in_string = False
    quote = ""
    escape = False
    for i in range(brace, len(text)):
        c = text[i]
        if in_string:
            if escape:
                escape = False
            elif c == "\\":
                escape = True
            elif c == quote:
                in_string = False
            continue
        if c in ("'", '"'):
            in_string = True
            quote = c
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return i + 1
    raise PatchError(f"{label}: closing brace missing")


def function_block(text: str, signature: str) -> tuple[int, int, str]:
    start = text.find(signature)
    if start < 0 or text.find(signature, start + 1) >= 0:
        raise PatchError(f"function missing/non-unique: {signature}")
    end = braced_end(text, start, signature)
    return start, end, text[start:end]


def replace_function(text: str, signature: str, replacement: str) -> str:
    start, end, _ = function_block(text, signature)
    return text[:start] + replacement + text[end:]


def remove_bottom_nav(text: str, signature: str) -> str:
    start, end, block = function_block(text, signature)
    count = block.count("uiBottomNav(3,nullptr);")
    if count == 0:
        return text
    block = block.replace("uiBottomNav(3,nullptr);", "")
    return text[:start] + block + text[end:]


FLAT_HELPERS = r'''
static void hubOs12RowSurface(const HubRect& r) {
  tft.fillRect(r.x,r.y,r.w,r.h,C10_BG);
  tft.drawFastHLine(r.x+12,r.y+r.h-1,r.w-24,C10_SEPARATOR);
}

static void hubOs12NavRow(const HubRect& r,const char* title,const char* detail,uint16_t valueColor=C10_MUTED) {
  hubOs12RowSurface(r);
  uiDrawFit(title,r.x+14,r.y+10,r.w-70,FONT_BODY,TL_DATUM,C10_TEXT,C10_BG);
  uiDrawFit(detail,r.x+14,r.y+r.h-10,r.w-70,FONT_SMALL,BL_DATUM,valueColor,C10_BG);
  uiDrawFit(">",r.x+r.w-18,r.y+r.h/2,20,FONT_BODY,MR_DATUM,C10_ACCENT,C10_BG);
}

static void hubUi13InfoRow(const HubRect& r,const char* label,const char* value,const char* detail,uint16_t accent=C10_ACCENT) {
  hubOs12RowSurface(r);
  uiDrawFit(label,r.x+12,r.y+8,r.w-150,FONT_SMALL,TL_DATUM,C10_MUTED,C10_BG);
  uiDrawFit(value,r.x+12,r.y+26,r.w-150,FONT_BODY,TL_DATUM,accent,C10_BG);
  uiDrawFit(detail,r.x+r.w-140,r.y+r.h/2,128,FONT_SMALL,MR_DATUM,C10_MUTED,C10_BG);
}

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

HOME = r'''static void drawHome(bool full) {
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
    HubRect printer=hr(8,46,W-16,70);
    HubRect job=hr(8,116,W-16,70);
    HubRect inventory=hr(8,186,W-16,66);
    hubOs12RowSurface(printer);hubOs12RowSurface(job);hubOs12RowSurface(inventory);
    uiDrawFit(p&&p->config.name[0]?p->config.name:"Printer",printer.x+14,printer.y+9,printer.w-28,FONT_SMALL,TL_DATUM,C10_MUTED,C10_BG);
    uiDrawFit(state,printer.x+14,printer.y+31,printer.w-28,FONT_LARGE,TL_DATUM,stateColor,C10_BG);

    if(printing||paused){
      uiDrawFit(jobDisplayName(*s),job.x+14,job.y+8,job.w-140,FONT_BODY,TL_DATUM,C10_TEXT,C10_BG);
      char meta[40],rem[20];formatDuration(s->remainingMinutes,rem,sizeof(rem));snprintf(meta,sizeof(meta),"%u%% - %s left",(unsigned)s->progress,rem);
      uiDrawFit(meta,job.x+14,job.y+37,job.w-28,FONT_SMALL,TL_DATUM,C10_MUTED,C10_BG);
    } else {
      uiDrawFit("Current print",job.x+14,job.y+8,job.w-28,FONT_SMALL,TL_DATUM,C10_MUTED,C10_BG);
      uiDrawFit(online?"None":"Unknown",job.x+14,job.y+31,job.w-28,FONT_BODY,TL_DATUM,online?C10_TEXT:C10_MUTED,C10_BG);
    }

    uiDrawFit("Filament Inventory",inventory.x+14,inventory.y+8,180,FONT_SMALL,TL_DATUM,C10_MUTED,C10_BG);
    uiDrawFit("Unknown",inventory.x+14,inventory.y+31,120,FONT_BODY,TL_DATUM,C10_MUTED,C10_BG);
    uiDrawFit("Authoritative device feed not available",inventory.x+150,inventory.y+33,inventory.w-164,FONT_SMALL,ML_DATUM,C10_MUTED,C10_BG);
  }
  hubMarkFrameDirty();g_dirty=false;
}'''

WORKSHOP = r'''static void drawWorkshop(bool full) {
  (void)full;
  const int16_t W=tft.width();
  tft.fillScreen(C10_BG);drawHeader("Workshop",nullptr,2);uiBottomNav(2,nullptr);
  const BambuState* s=isAnyPrinterConfigured()?&displayedPrinter().state:nullptr;
  if(hubLandscape()) {
    HubRect attention=hr(8,46,W-16,52);
    HubRect readiness=hr(8,98,W-16,52);
    HubRect loaded=hr(8,150,W-16,52);
    HubRect inventory=hr(8,202,W-16,50);
    hubOs12NavRow(attention,"Needs Attention",s&&uiHmsCount(*s)>0?"Printer alerts present":"No authoritative inventory alerts",s&&uiHmsCount(*s)>0?C10_ORANGE:C10_MUTED);
    hubOs12NavRow(readiness,"Print Readiness","Undetermined",C10_MUTED);
    hubOs12NavRow(loaded,"Loaded Spools","Unknown",C10_MUTED);
    hubOs12NavRow(inventory,"Inventory","Unknown - awaiting Filament Inventory device feed",C10_MUTED);
  }
  hubMarkFrameDirty();g_dirty=false;
}'''


def apply(repo: Path) -> None:
    path = repo / "src/smart_hub.cpp"
    text = load(path)

    # Install the flattened component vocabulary immediately before Home.
    if "static void hubOs12RowSurface(" not in text:
        anchor = "static void drawHome(bool full)"
        pos = text.find(anchor)
        if pos < 0:
            raise PatchError("Home renderer anchor missing")
        text = text[:pos] + FLAT_HELPERS + "\n" + text[pos:]

    # Replace the three UI13 setting-row implementations with the flat variants.
    for sig, replacement in (
        ("static void hubUi13InfoRow(", FLAT_HELPERS[FLAT_HELPERS.find("static void hubUi13InfoRow("):FLAT_HELPERS.find("static void hubUi13ToggleRow(")].strip()),
        ("static void hubUi13ToggleRow(", FLAT_HELPERS[FLAT_HELPERS.find("static void hubUi13ToggleRow("):FLAT_HELPERS.find("static void hubUi13StepperRow(")].strip()),
        ("static void hubUi13StepperRow(", FLAT_HELPERS[FLAT_HELPERS.find("static void hubUi13StepperRow("):].strip()),
    ):
        if text.find(sig) >= 0:
            text = replace_function(text, sig, replacement)

    # Child/configuration screens must not render the global bottom navigation.
    child_functions = (
        "static void drawUi13Display()",
        "static void drawUi13AfterPrint()",
        "static void drawUi13Sound()",
        "static void drawUi13PrinterAlerts()",
        "static void drawUi13AlertSignals()",
        "static void drawUi13Network()",
        "static void drawUi13PrinterPower()",
        "static void drawUi13PowerOptions()",
        "static void drawUi13AutoOffConfirm()",
        "static void drawUi13DateTime()",
        "static void drawUi13SoftwareUpdate()",
        "static void drawUi13Diagnostics()",
        "static void drawUi12PortalAccess()",
        "static void drawUi12Experience()",
        "static void drawUi12PrinterConnection()",
        "static void drawUi12SoftwareUpdate()",
        "static void drawOs12Media()",
        "static void drawOs12MediaLab()",
        "static void drawSystem(bool full)",
    )
    for sig in child_functions:
        if text.find(sig) >= 0:
            text = remove_bottom_nav(text, sig)

    # Flatten the More root without changing its existing touch-routing geometry.
    _, _, more = function_block(text, "static void drawMore(bool full)")
    more = more.replace("hubUi12SettingsCard(hubUi12SettingsRect(0),\"Display & Appearance\",\"Brightness, standby, after print\",C10_ACCENT,false);",
                        "hubOs12NavRow(hubUi12SettingsRect(0),\"Display & Appearance\",\"Brightness, standby, after print\",C10_MUTED);")
    more = more.replace("hubUi12SettingsCard(hubUi12SettingsRect(1),\"Sounds & Alerts\",\"Sounds, touch feedback, printer alerts\",C10_ACCENT,false);",
                        "hubOs12NavRow(hubUi12SettingsRect(1),\"Sound & Microphone\",\"Volume, microphone, event sounds\",C10_MUTED);")
    more = more.replace("hubUi12SettingsCard(hubUi12SettingsRect(2),\"Network\",wifi?\"Connected\":\"Offline\",wifi?C10_GREEN:C10_ORANGE,false);",
                        "hubOs12NavRow(hubUi12SettingsRect(2),\"Network\",wifi?\"Connected\":\"Offline\",wifi?C10_GREEN:C10_ORANGE);")
    more = more.replace("hubUi12SettingsCard(hubUi12SettingsRect(3),\"Printer & Power\",!configured?\"Not configured\":(printerConnected?\"Connected\":\"Offline\"),printerConnected?C10_GREEN:(configured?C10_ORANGE:C10_MUTED),false);",
                        "hubOs12NavRow(hubUi12SettingsRect(3),\"Printer & Power\",!configured?\"Not configured\":(printerConnected?\"Connected\":\"Offline\"),printerConnected?C10_GREEN:(configured?C10_ORANGE:C10_MUTED));")
    more = more.replace("hubUi12SettingsCard(hubUi12SettingsRect(4),\"System\",deviceHealthy?\"Ready\":\"Needs attention\",deviceHealthy?C10_GREEN:C10_ORANGE,true);",
                        "hubOs12NavRow(hubUi12SettingsRect(4),\"System\",deviceHealthy?\"Ready\":\"Needs attention\",deviceHealthy?C10_GREEN:C10_ORANGE);")
    start, end, _ = function_block(text, "static void drawMore(bool full)")
    text = text[:start] + more + text[end:]

    # Make System visually list-based while preserving existing touch rectangles.
    _, _, system = function_block(text, "static void drawSystem(bool full)")
    system = system.replace("hubUi12SettingsCard(hubUi13SystemCardRect(0),\"Device Health\",deviceHealthy?\"Healthy\":\"Needs attention\",deviceHealthy?C10_GREEN:C10_ORANGE,false);",
                            "hubOs12NavRow(hubUi13SystemCardRect(0),\"Device Health\",deviceHealthy?\"Healthy\":\"Needs attention\",deviceHealthy?C10_GREEN:C10_ORANGE);")
    system = system.replace("hubUi12SettingsCard(hubUi13SystemCardRect(1),\"Connectivity\",!wifi?\"Offline\":(printerOk?\"Network + printer\":\"Network connected\"),wifi?C10_GREEN:C10_ORANGE,false);",
                            "hubOs12NavRow(hubUi13SystemCardRect(1),\"Connectivity\",!wifi?\"Offline\":(printerOk?\"Network + printer\":\"Network connected\"),wifi?C10_GREEN:C10_ORANGE);")
    system = system.replace("hubUi12SettingsCard(hubUi13SystemCardRect(2),\"Date & Time\",hubTimezoneLabel(),C10_ACCENT,false);",
                            "hubOs12NavRow(hubUi13SystemCardRect(2),\"Date & Time\",hubTimezoneLabel(),C10_MUTED);")
    system = system.replace("hubUi12SettingsCard(hubUi13SystemCardRect(3),\"Software Update\",\"Version and update options\",C10_ACCENT,false);",
                            "hubOs12NavRow(hubUi13SystemCardRect(3),\"Software Update\",\"Version and update options\",C10_MUTED);")
    start, end, _ = function_block(text, "static void drawSystem(bool full)")
    text = text[:start] + system + text[end:]

    # Root operational screens become evidence-first. Unknown stays explicit.
    text = replace_function(text, "static void drawHome(bool full)", HOME)
    text = replace_function(text, "static void drawWorkshop(bool full)", WORKSHOP)

    path.write_text(text, encoding="utf-8")
    print("Workshop OS 12 UX architecture overhaul installed")


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
