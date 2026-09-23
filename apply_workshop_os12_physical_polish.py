#!/usr/bin/env python3
"""Focused product-polish pass from physical WS350 review.

This layer intentionally runs after the Workshop runtime fix. It does not
change authority, transport, placement, quantity, or release-state semantics.
It tightens the appliance presentation observed on the physical 480x320 panel:
- no irrelevant implicit ONLINE badges;
- consistent status vocabulary;
- secondary navigation no longer masquerades as a primary orange action;
- distinct navigation pictograms instead of duplicated initial letters;
- quieter OFF toggles;
- user-facing Software Update hierarchy;
- Home consumes the same authoritative inventory snapshot as Workshop.
"""
from __future__ import annotations

import argparse
from pathlib import Path


class PatchError(RuntimeError):
    pass


def load(path: Path) -> str:
    if not path.is_file():
        raise PatchError(f"missing {path}")
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


def replace_function(text: str, signature: str, replacement: str) -> str:
    start = text.find(signature)
    if start < 0 or text.find(signature, start + 1) >= 0:
        raise PatchError(f"missing/non-unique function: {signature}")
    end = braced_end(text, start, signature)
    return text[:start] + replacement.strip() + text[end:]


HEADER = r'''
static uint16_t hubOs12HeaderStatusColor(const char* state) {
  if(!state||!state[0])return OS12V_BLUE;
  if(strstr(state,"HEALTHY")||strstr(state,"CONNECTED")||strstr(state,"CURRENT")||
     strstr(state,"READY")||strstr(state,"ONLINE"))return OS12V_GREEN;
  if(strstr(state,"CONFLICT")||strstr(state,"ERROR")||strstr(state,"FAILED"))return OS12V_RED;
  if(strstr(state,"STALE")||strstr(state,"CHECK")||strstr(state,"SETUP")||
     strstr(state,"ATTENTION"))return OS12V_AMBER;
  if(strstr(state,"PRINTING")||strstr(state,"CANDIDATE")||strstr(state,"SYNCING"))return OS12V_BLUE;
  return OS12V_BLUE;
}

static void drawHeader(const char* title,const char* right,uint8_t page) {
  const int16_t W=tft.width(),HH=hubHeaderH();
  const bool explicitState=right&&right[0];
  tft.fillRect(0,0,W,HH,OS12V_BG);
  tft.fillRoundRect(OS12V_INSET,9,4,19,2,OS12V_ACCENT);
  uiDrawFit(title?title:"Home",OS12V_INSET+11,7,272,FONT_BODY,TL_DATUM,OS12V_TEXT,OS12V_BG);
  if(explicitState){
    const uint16_t stateColor=hubOs12HeaderStatusColor(right);
    tft.fillRoundRect(W-108,8,96,21,10,OS12V_SURFACE);
    tft.drawRoundRect(W-108,8,96,21,10,OS12V_LINE);
    tft.fillCircle(W-98,18,4,stateColor);
    uiDrawFit(right,W-17,18,72,FONT_SMALL,MR_DATUM,stateColor,OS12V_SURFACE);
  }
  tft.drawFastHLine(OS12V_INSET,HH-1,W-OS12V_INSET*2,OS12V_LINE);
  (void)hubV1125UiFingerprint(page);
}
'''


ACTION = r'''
static bool hubOs12SecondaryActionLabel(const char* label) {
  if(!label)return false;
  return strcmp(label,"Back")==0||
         strcmp(label,"Cancel")==0||
         strcmp(label,"Discard")==0||
         strcmp(label,"Local Portal")==0||
         strcmp(label,"After Print")==0||
         strcmp(label,"Printer Alerts")==0||
         strcmp(label,"Power Options")==0||
         strcmp(label,"Recorder")==0;
}

static void hubV1125Action(const HubRect& r,const char* label,uint16_t c,bool enabled=true,bool destructive=false) {
  const bool secondary=!destructive&&hubOs12SecondaryActionLabel(label);
  const uint16_t semantic=destructive?OS12V_RED:((c==C10_GREEN||c==OS12V_GREEN)?OS12V_GREEN:((c==C10_ORANGE||c==OS12V_AMBER)?OS12V_AMBER:OS12V_ACCENT));
  const uint16_t bg=!enabled?OS12V_SURFACE:(destructive?OS12V_RED:(secondary?OS12V_SURFACE2:semantic));
  const uint16_t border=!enabled?OS12V_LINE:(destructive?OS12V_RED:(secondary?OS12V_LINE:semantic));
  const uint16_t fg=!enabled?OS12V_MUTED:((destructive||!secondary)?OS12V_BG:OS12V_TEXT);
  tft.fillRoundRect(r.x,r.y,r.w,r.h,OS12V_RADIUS,bg);
  tft.drawRoundRect(r.x,r.y,r.w,r.h,OS12V_RADIUS,border);
  if(enabled&&secondary)tft.fillCircle(r.x+17,r.y+r.h/2,4,semantic);
  uiDrawFit(label,r.x+r.w/2+(secondary?5:0),r.y+r.h/2,r.w-(secondary?44:22),FONT_BODY,MC_DATUM,fg,bg);
}
'''


NAVROW = r'''
static void hubOs12NavIcon(const HubRect& badge,const char* title,uint16_t c) {
  const int16_t cx=badge.x+badge.w/2,cy=badge.y+badge.h/2;
  if(strstr(title,"Display")){
    tft.drawRect(cx-8,cy-7,16,11,c);
    tft.drawFastHLine(cx-4,cy+7,8,c);
    tft.drawFastVLine(cx,cy+4,4,c);
    return;
  }
  if(strstr(title,"Sound")||strstr(title,"Media")){
    tft.drawRect(cx-8,cy-4,5,8,c);
    tft.drawLine(cx-3,cy-4,cx+3,cy-9,c);
    tft.drawLine(cx-3,cy+4,cx+3,cy+9,c);
    tft.drawFastVLine(cx+3,cy-9,18,c);
    tft.drawLine(cx+6,cy-5,cx+9,cy,c);
    tft.drawLine(cx+9,cy,cx+6,cy+5,c);
    return;
  }
  if(strstr(title,"Network")){
    tft.fillCircle(cx,cy+7,2,c);
    tft.drawLine(cx,cy+4,cx-6,cy-2,c);
    tft.drawLine(cx,cy+4,cx+6,cy-2,c);
    tft.drawLine(cx-6,cy-2,cx-10,cy-6,c);
    tft.drawLine(cx+6,cy-2,cx+10,cy-6,c);
    return;
  }
  if(strstr(title,"Date")||strstr(title,"Time")){
    tft.drawRect(cx-8,cy-7,16,15,c);
    tft.drawFastHLine(cx-8,cy-3,16,c);
    tft.drawFastVLine(cx-4,cy-9,4,c);
    tft.drawFastVLine(cx+4,cy-9,4,c);
    return;
  }
  if(strstr(title,"Update")){
    tft.drawFastVLine(cx,cy-9,12,c);
    tft.drawLine(cx,cy+3,cx-5,cy-2,c);
    tft.drawLine(cx,cy+3,cx+5,cy-2,c);
    tft.drawFastHLine(cx-8,cy+8,16,c);
    return;
  }
  if(strstr(title,"Printer")||strstr(title,"Power")){
    tft.drawRect(cx-8,cy-4,16,9,c);
    tft.drawRect(cx-5,cy-9,10,5,c);
    tft.drawFastHLine(cx-5,cy+8,10,c);
    tft.fillCircle(cx+5,cy,1,c);
    return;
  }
  if(strstr(title,"System")||strstr(title,"Device")||strstr(title,"Diagnostics")){
    tft.drawCircle(cx,cy,6,c);
    tft.fillCircle(cx,cy,2,c);
    tft.drawFastHLine(cx-10,cy,4,c);tft.drawFastHLine(cx+7,cy,4,c);
    tft.drawFastVLine(cx,cy-10,4,c);tft.drawFastVLine(cx,cy+7,4,c);
    return;
  }
  char glyph[2]={title&&title[0]?title[0]:'?',0};
  uiDrawFit(glyph,cx,cy,badge.w-8,FONT_BODY,MC_DATUM,c,OS12V_SURFACE2);
}

static void hubOs12NavRow(const HubRect& r,const char* title,const char* detail,uint16_t valueColor=C10_MUTED) {
  hubOs12RowSurface(r);
  uint16_t detailColor=OS12V_MUTED;
  if(valueColor==C10_GREEN||valueColor==OS12V_GREEN)detailColor=OS12V_GREEN;
  else if(valueColor==C10_ORANGE||valueColor==OS12V_AMBER)detailColor=OS12V_AMBER;
  else if(valueColor==C10_RED||valueColor==OS12V_RED)detailColor=OS12V_RED;

  uint16_t iconColor=OS12V_BLUE;
  if(strstr(title,"Display"))iconColor=OS12V_ACCENT;
  else if(strstr(title,"Sound")||strstr(title,"Media"))iconColor=OS12V_BLUE;
  else if(strstr(title,"Network"))iconColor=OS12V_BLUE;
  else if(strstr(title,"System")||strstr(title,"Device")||strstr(title,"Diagnostics"))iconColor=OS12V_AMBER;
  else if(strstr(title,"Printer")||strstr(title,"Power"))iconColor=OS12V_GREEN;
  else if(strstr(title,"Date")||strstr(title,"Update"))iconColor=OS12V_BLUE;

  HubRect badge=hr(r.x+9,r.y+(r.h-30)/2,30,30);
  tft.fillRoundRect(badge.x,badge.y,badge.w,badge.h,8,OS12V_SURFACE2);
  tft.drawRoundRect(badge.x,badge.y,badge.w,badge.h,8,iconColor);
  hubOs12NavIcon(badge,title,iconColor);

  const int16_t textX=r.x+48;
  uiDrawFit(title,textX,r.y+7,r.w-96,FONT_BODY,TL_DATUM,OS12V_TEXT,OS12V_SURFACE);
  uiDrawFit(detail,textX,r.y+r.h-9,r.w-96,FONT_SMALL,BL_DATUM,detailColor,OS12V_SURFACE);
  const int16_t cx=r.x+r.w-18,cy=r.y+r.h/2;
  tft.drawLine(cx-4,cy-5,cx+1,cy,OS12V_MUTED);
  tft.drawLine(cx+1,cy,cx-4,cy+5,OS12V_MUTED);
}
'''


TOGGLE = r'''
static void hubUi13ToggleRow(const HubRect& r,const char* label,const char* detail,bool on,uint16_t accent=C10_ACCENT) {
  (void)accent;hubOs12RowSurface(r);
  const int16_t controlW=62;
  uiDrawFit(label,r.x+OS12V_INSET,r.y+8,r.w-controlW-OS12V_INSET*3,FONT_BODY,TL_DATUM,OS12V_TEXT,OS12V_SURFACE);
  uiDrawFit(detail,r.x+OS12V_INSET,r.y+r.h-9,r.w-controlW-OS12V_INSET*3,FONT_SMALL,BL_DATUM,OS12V_MUTED,OS12V_SURFACE);
  HubRect sw=hr(r.x+r.w-controlW-OS12V_INSET,r.y+(r.h-34)/2,controlW,34);
  const uint16_t track=on?OS12V_ACCENT:OS12V_SURFACE2;
  const uint16_t edge=on?OS12V_ACCENT:OS12V_LINE;
  tft.fillRoundRect(sw.x,sw.y,sw.w,sw.h,17,track);
  tft.drawRoundRect(sw.x,sw.y,sw.w,sw.h,17,edge);
  const int16_t d=on?24:20;
  const int16_t cx=on?(sw.x+sw.w-5-d/2):(sw.x+5+d/2);
  tft.fillCircle(cx,sw.y+sw.h/2,d/2,on?OS12V_BG:OS12V_MUTED);
}
'''


HOME = r'''
static void drawHome(bool full) {
  (void)full;
  const int16_t W=tft.width();
  const bool configured=workshopPlatformState().configuredPrinterCount>0;
  const PrinterSlot* p=configured?&displayedPrinter():nullptr;
  const BambuState* s=p?&p->state:nullptr;
  if(g_ambientEnabled&&g_ambientActive){drawAmbientHome(p,s);return;}
  const uint8_t slot=rotState.displayIndex<MAX_PRINTERS?rotState.displayIndex:0;
  const bool paused=configured&&workshopPlatformPrinterPaused(slot);
  const bool printing=configured&&workshopPlatformPrinterPrinting(slot);
  const bool online=configured&&workshopPlatformPrinterOnline(slot);
  const bool alert=s&&uiHmsCount(*s)>0;
  const uint16_t sc=!configured?C10_MUTED:(!online?C10_ORANGE:(alert?C10_RED:(paused?C10_ORANGE:(printing?C10_ACCENT:C10_GREEN))));
  const char* state=!configured?"SETUP":(!online?"OFFLINE":(alert?"ATTENTION":(paused?"PAUSED":(printing?"PRINTING":"READY"))));

  tft.fillScreen(OS12V_BG);drawHeader("Home",nullptr,0);uiBottomNav(0,nullptr);

  HubRect hero=hr(OS12V_INSET,46,W-OS12V_INSET*2,76);
  hubV1125Card(hero,sc,true);
  uiDrawFit(p&&p->config.name[0]?p->config.name:"Printer",hero.x+14,hero.y+11,hero.w-28,FONT_SMALL,TL_DATUM,OS12V_MUTED,OS12V_SURFACE2);
  uiDrawFit(state,hero.x+14,hero.y+31,hero.w-28,FONT_LARGE,TL_DATUM,
      !configured?OS12V_MUTED:(!online?OS12V_AMBER:(alert?OS12V_RED:(printing?OS12V_ACCENT:OS12V_GREEN))),OS12V_SURFACE2);
  uiDrawFit(printing||paused?"Print in progress":(online?"Ready for work":"Check connection"),hero.x+14,hero.y+65,hero.w-28,FONT_SMALL,BL_DATUM,OS12V_MUTED,OS12V_SURFACE2);

  HubRect job=hr(OS12V_INSET,128,W-OS12V_INSET*2,54);
  if(printing||paused){
    char meta[36],rem[20];
    formatDuration(s->remainingMinutes,rem,sizeof(rem));
    snprintf(meta,sizeof(meta),"%u%% · %s left",(unsigned)s->progress,rem);
    hubOs12EvidenceRow(job,"CURRENT PRINT",jobDisplayName(*s),meta,C10_TEXT);
  }else{
    hubOs12EvidenceRow(job,"CURRENT PRINT",online?"None":"Unknown",online?"Printer idle":"No fresh printer evidence",online?C10_TEXT:C10_MUTED);
  }

  const WorkshopInventoryRuntimeSnapshot inv=workshopInventorySnapshot();
  const auto& inventoryState=inv.state;
  HubRect inventory=hr(OS12V_INSET,188,W-OS12V_INSET*2,62);
  char invValue[48];
  char invDetail[96];
  uint16_t invColor=C10_MUTED;
  if(!inv.credentialConfigured){
    strlcpy(invValue,"Not configured",sizeof(invValue));
    strlcpy(invDetail,"Open Workshop to set up inventory access",sizeof(invDetail));
    invColor=C10_ORANGE;
  }else if(inv.busy){
    strlcpy(invValue,"Refreshing",sizeof(invValue));
    strlcpy(invDetail,"Waiting for profile-scoped inventory evidence",sizeof(invDetail));
    invColor=C10_ACCENT;
  }else if(!inventoryState.available){
    strlcpy(invValue,"Unknown",sizeof(invValue));
    strlcpy(invDetail,inv.statusMessage[0]?inv.statusMessage:"Authoritative inventory unavailable",sizeof(invDetail));
  }else if(inventoryState.freshness==workshop::platform::Freshness::Conflicting){
    strlcpy(invValue,"Evidence conflict",sizeof(invValue));
    strlcpy(invDetail,"Open Workshop to review inventory evidence",sizeof(invDetail));
    invColor=C10_RED;
  }else if(inventoryState.freshness!=workshop::platform::Freshness::Fresh){
    strlcpy(invValue,"Evidence stale",sizeof(invValue));
    strlcpy(invDetail,"Refresh or verify inventory evidence",sizeof(invDetail));
    invColor=C10_ORANGE;
  }else{
    snprintf(invValue,sizeof(invValue),"%u spools · %u loaded",
        (unsigned)inventoryState.spoolCount,(unsigned)inventoryState.loadedCount);
    snprintf(invDetail,sizeof(invDetail),"Current · %s",
        hubOs12WorkshopReadinessLabel(inventoryState.readiness));
    invColor=hubOs12WorkshopReadinessColor(inventoryState.readiness);
  }
  hubOs12EvidenceRow(inventory,"FILAMENT INVENTORY",invValue,invDetail,invColor);
  hubMarkFrameDirty();g_dirty=false;
}
'''


MORE = r'''
static void drawMore(bool full) {
  if(g_displayExperienceView){drawDisplayExperience(full);return;}if(g_toolsView){drawTools(full);return;}
  if(g_ui12SettingsView==1){drawUi13Display();return;}if(g_ui12SettingsView==2){drawUi13Sound();return;}if(g_ui12SettingsView==3){drawUi13Network();return;}if(g_ui12SettingsView==4){drawUi13PrinterPower();return;}if(g_ui12SettingsView==5){drawUi13AfterPrint();return;}if(g_ui12SettingsView==6){drawUi13PrinterAlerts();return;}if(g_ui12SettingsView==7){drawUi13AlertSignals();return;}if(g_ui12SettingsView==8){drawUi13PowerOptions();return;}if(g_ui12SettingsView==9){drawUi13AutoOffConfirm();return;}if(g_ui12SettingsView==10){drawOs12Media();return;}if(g_ui12SettingsView==11){drawOs12Recorder();return;}if(g_ui12SettingsView==12){drawOs12VideoViewer();return;}
  (void)full;
  const bool wifi=workshopPlatformWifiOnline();
  const bool healthy=hubTouchHealthy()&&recoveryWebReady();
  tft.fillScreen(OS12V_BG);drawHeader("More",nullptr,3);uiBottomNav(3,nullptr);
  hubOs12NavRow(hubUi12SettingsRect(0),"Display & Appearance","Brightness · standby · after print",C10_MUTED);
  hubOs12NavRow(hubUi12SettingsRect(1),"Sound & Media","Sounds · microphone · recorder · video",C10_MUTED);
  hubOs12NavRow(hubUi12SettingsRect(2),"Network",wifi?"Connected":"Offline",wifi?C10_GREEN:C10_ORANGE);
  hubOs12NavRow(hubUi12SettingsRect(3),"System",healthy?"Device health OK · power · time · updates":"Needs attention · open diagnostics",healthy?C10_MUTED:C10_ORANGE);
  hubMarkFrameDirty();g_dirty=false;
}
'''


SYSTEM = r'''
static void drawSystem(bool full) {
  if(g_audioSettingsView){drawAudioSettings(full);return;}if(g_networkSettingsView){drawNetworkEssentials(full);return;}if(g_ui12SystemView==1){drawUi12PortalAccess();return;}if(g_ui12SystemView==2){drawUi13DateTime();return;}if(g_ui12SystemView==3){drawUi13SoftwareUpdate();return;}if(g_ui12SystemView==4){drawUi13Diagnostics();return;}
  (void)full;
  const bool healthy=hubTouchHealthy()&&recoveryWebReady();
  const bool configured=workshopPlatformState().configuredPrinterCount>0;
  const uint8_t slot=rotState.displayIndex<MAX_PRINTERS?rotState.displayIndex:0;
  const bool printerOk=configured&&workshopPlatformPrinterOnline(slot);
  tft.fillScreen(OS12V_BG);drawHeader("System",healthy?"HEALTHY":"CHECK",3);
  hubOs12NavRow(hubUi13SystemCardRect(0),"Device Health",healthy?"Healthy":"Needs attention",healthy?C10_GREEN:C10_ORANGE);
  hubOs12NavRow(hubUi13SystemCardRect(1),"Printer & Power",!configured?"Not configured":(printerOk?"Connected":"Unavailable"),printerOk?C10_GREEN:(configured?C10_ORANGE:C10_MUTED));
  hubOs12NavRow(hubUi13SystemCardRect(2),"Date & Time",hubOs12CompactTimezoneLabel(),C10_MUTED);
  hubOs12NavRow(hubUi13SystemCardRect(3),"Software Update","Candidate channel · physical validation pending",C10_MUTED);
  hubV1125Action(hubUi13BackRect(),"Back",C10_ACCENT,true,false);
  hubV1125Action(hubUi13ActionRect(),"Local Portal",C10_ACCENT,workshopPlatformWifiOnline(),false);
  hubMarkFrameDirty();g_dirty=false;
}
'''


DISPLAY = r'''
static void drawUi13Display() {
  tft.fillScreen(OS12V_BG);drawHeader("Display & Appearance",nullptr,3);
  char mainValue[16],standbyValue[16];
  snprintf(mainValue,sizeof(mainValue),"%u%%",(unsigned)hubLevelPct(brightness));
  snprintf(standbyValue,sizeof(standbyValue),"%u%%",(unsigned)hubLevelPct(dpSettings.screensaverBrightness));
  hubUi13StepperRow(hubUi13RowRect(0),"Brightness",mainValue,"Active display",C10_ACCENT);
  hubUi13StepperRow(hubUi13RowRect(1),"Standby Brightness",standbyValue,"Idle display",C10_ACCENT);
  hubUi13ToggleRow(hubUi13RowRect(2),"Night Mode","Follow configured night schedule",dpSettings.nightModeEnabled,C10_ACCENT);
  hubV1125Action(hubUi13BackRect(),"Back",C10_ACCENT,true,false);
  hubV1125Action(hubUi13ActionRect(),"After Print",C10_ACCENT,true,false);
  hubMarkFrameDirty();g_dirty=false;
}
'''


SOUND = r'''
static void drawUi13Sound() {
  tft.fillScreen(OS12V_BG);drawHeader("Sound & Media",nullptr,3);
  hubUi13ToggleRow(hubUi13RowRect(0),"Event Sounds","Print and device events",buzzerSettings.enabled,C10_ACCENT);
  hubUi13ToggleRow(hubUi13RowRect(1),"Touch Sounds","Immediate tap feedback",buzzerSettings.buttonClick,C10_ACCENT);
  hubOs12NavRow(hubUi13RowRect(2),"Media","Speaker · microphone · recorder · video",C10_MUTED);
  hubV1125Action(hubUi13BackRect(),"Back",C10_ACCENT,true,false);
  hubV1125Action(hubUi13ActionRect(),"Printer Alerts",C10_ACCENT,true,false);
  hubMarkFrameDirty();g_dirty=false;
}
'''


NETWORK = r'''
static void drawUi13Network() {
  const bool wifi=workshopPlatformWifiOnline();
  String ip=wifi?WiFi.localIP().toString():String("Unknown");
  tft.fillScreen(OS12V_BG);drawHeader("Network",wifi?"CONNECTED":"OFFLINE",3);
  hubUi13InfoRow(hubUi13RowRect(0),"Wi-Fi",wifi?"Connected":"Unavailable",wifi?ip.c_str():"No active network connection",wifi?C10_GREEN:C10_ORANGE);
  hubUi13ToggleRow(hubUi13RowRect(1),"Local Hostname","Advertise the device on the LAN",netSettings.mdnsEnabled,C10_ACCENT);
  hubUi13ToggleRow(hubUi13RowRect(2),"Show IP at Startup","Show address after connection",netSettings.showIPAtStartup,C10_ACCENT);
  hubV1125Action(hubUi13BackRect(),"Back",C10_ACCENT,true,false);
  hubV1125Action(hubUi13ActionRect(),"Local Portal",C10_ACCENT,wifi,false);
  hubMarkFrameDirty();g_dirty=false;
}
'''


UPDATE = r'''
static void drawUi13SoftwareUpdate() {
  const int16_t W=tft.width();
  tft.fillScreen(OS12V_BG);drawHeader("Software Update","CANDIDATE",3);
  HubRect hero=hr(OS12V_INSET,48,W-OS12V_INSET*2,76);
  hubV1125Card(hero,C10_ACCENT,true);
  char runtimeVer[48];
  snprintf(runtimeVer,sizeof(runtimeVer),"Workshop OS %s",WORKSHOP_OS_RELEASE_VERSION);
  uiDrawFit("CURRENT VERSION",hero.x+14,hero.y+10,hero.w-28,FONT_SMALL,TL_DATUM,OS12V_MUTED,OS12V_SURFACE2);
  uiDrawFit(runtimeVer,hero.x+14,hero.y+31,hero.w-28,FONT_LARGE,TL_DATUM,OS12V_TEXT,OS12V_SURFACE2);
  hubUi13InfoRow(hr(OS12V_INSET,130,W-OS12V_INSET*2,54),"Update Channel","Candidate","Physical validation pending",C10_ORANGE);
  hubUi13InfoRow(hr(OS12V_INSET,190,W-OS12V_INSET*2,54),"Build Details","Local Portal","Source · artifact · recovery identity",C10_MUTED);
  hubV1125Action(hubUi13BackRect(),"Back",C10_ACCENT,true,false);
  hubV1125Action(hubUi13ActionRect(),"Local Portal",C10_ACCENT,true,false);
  hubMarkFrameDirty();g_dirty=false;
}
'''


def apply(repo: Path) -> None:
    path = repo / "src" / "smart_hub.cpp"
    text = load(path)

    for signature, replacement in (
        ("static void drawHeader(const char* title,const char* right,uint8_t page)", HEADER),
        ("static void hubV1125Action(const HubRect& r,const char* label,uint16_t c,bool enabled=true,bool destructive=false)", ACTION),
        ("static void hubOs12NavRow(const HubRect& r,const char* title,const char* detail,uint16_t valueColor=C10_MUTED)", NAVROW),
        ("static void hubUi13ToggleRow(const HubRect& r,const char* label,const char* detail,bool on,uint16_t accent=C10_ACCENT)", TOGGLE),
        ("static void drawHome(bool full)", HOME),
        ("static void drawMore(bool full)", MORE),
        ("static void drawSystem(bool full)", SYSTEM),
        ("static void drawUi13Display()", DISPLAY),
        ("static void drawUi13Sound()", SOUND),
        ("static void drawUi13Network()", NETWORK),
        ("static void drawUi13SoftwareUpdate()", UPDATE),
    ):
        text = replace_function(text, signature, replacement)

    path.write_text(text, encoding="utf-8")
    print("Workshop OS 12 physical product-polish pass applied")


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
