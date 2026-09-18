#!/usr/bin/env python3
"""Workshop OS 12 product-surface completion pass.

Completes the 480x320 appliance UI for Home, Workshop, More/System, and
everyday child settings while preserving printer/control/inventory authority.
"""
from __future__ import annotations
import argparse
from pathlib import Path

class PatchError(RuntimeError): pass

def load(path: Path) -> str:
    if not path.is_file(): raise PatchError(f"missing {path}")
    return path.read_text(encoding="utf-8")

def braced_end(text: str, start: int, label: str) -> int:
    brace=text.find("{",start)
    if brace<0: raise PatchError(f"{label}: opening brace missing")
    depth=0; string=None; escape=False; line=False; block=False; i=brace
    while i<len(text):
        c=text[i]; n=text[i+1] if i+1<len(text) else ""
        if line:
            if c=="\n": line=False
        elif block:
            if c=="*" and n=="/": block=False; i+=1
        elif string:
            if escape: escape=False
            elif c=="\\": escape=True
            elif c==string: string=None
        elif c=="/" and n=="/": line=True; i+=1
        elif c=="/" and n=="*": block=True; i+=1
        elif c in ('"',"'"): string=c
        elif c=="{": depth+=1
        elif c=="}":
            depth-=1
            if depth==0:return i+1
        i+=1
    raise PatchError(f"{label}: closing brace missing")

def replace_function(text:str,signature:str,replacement:str)->str:
    start=text.find(signature)
    if start<0 or text.find(signature,start+1)>=0: raise PatchError(f"function missing/non-unique: {signature}")
    return text[:start]+replacement.strip()+text[braced_end(text,start,signature):]

STATE_HELPER=r'''
static void hubOs12StatePanel(const HubRect& r,const char* eyebrow,const char* title,const char* detail,uint16_t color,bool strong=false) {
  hubV1125Card(r,color,strong);
  const uint16_t bg=strong?C10_SURFACE_2:C10_SURFACE;
  uiDrawFit(eyebrow,r.x+14,r.y+10,r.w-28,FONT_SMALL,TL_DATUM,C10_MUTED,bg);
  uiDrawFit(title,r.x+14,r.y+31,r.w-28,FONT_BODY,TL_DATUM,color,bg);
  uiDrawFit(detail,r.x+14,r.y+r.h-10,r.w-28,FONT_SMALL,BL_DATUM,C10_MUTED,bg);
}
'''

HOME=r'''
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
  const uint16_t stateColor=!configured?C10_MUTED:(!online?C10_ORANGE:(alert?C10_RED:(paused?C10_ORANGE:(printing?C10_ACCENT:C10_GREEN))));
  const char* state=!configured?"Not configured":(!online?"Unavailable":(alert?"Needs attention":(paused?"Paused":(printing?"Printing":"Ready"))));

  tft.fillScreen(C10_BG);drawHeader("Home",nullptr,0);uiBottomNav(0,nullptr);
  HubRect printer=hr(OS12_MARGIN_X,48,W-OS12_MARGIN_X*2,58);
  HubRect job=hr(OS12_MARGIN_X,114,W-OS12_MARGIN_X*2,70);
  HubRect inventory=hr(OS12_MARGIN_X,192,W-OS12_MARGIN_X*2,60);

  hubOs12EvidenceRow(printer,p&&p->config.name[0]?p->config.name:"Printer",state,online?"Fresh printer status":(configured?"No fresh connection":"Setup required"),stateColor);
  if(printing||paused){
    char meta[32],rem[20];formatDuration(s->remainingMinutes,rem,sizeof(rem));
    snprintf(meta,sizeof(meta),"%u%% · %s left",(unsigned)s->progress,rem);
    hubOs12EvidenceRow(job,"Current Print",jobDisplayName(*s),meta,C10_TEXT);
  } else {
    hubOs12EvidenceRow(job,"Current Print",online?"None":"Unknown",online?"Printer idle":"No fresh printer evidence",online?C10_TEXT:C10_MUTED);
  }
  hubOs12EvidenceRow(inventory,"Filament Inventory","Unknown","No authoritative inventory evidence",C10_MUTED);
  hubMarkFrameDirty();g_dirty=false;
}
'''

WORKSHOP=r'''
static void drawWorkshop(bool full) {
  (void)full;
  const int16_t W=tft.width();
  tft.fillScreen(C10_BG);drawHeader("Workshop",nullptr,2);uiBottomNav(2,nullptr);
  const BambuState* s=isAnyPrinterConfigured()?&displayedPrinter().state:nullptr;
  const bool printerAlert=s&&uiHmsCount(*s)>0;

  HubRect attention=hr(OS12_MARGIN_X,OS12_CONTENT_TOP,W-OS12_MARGIN_X*2,OS12_ROW_H);
  HubRect readiness=hr(OS12_MARGIN_X,OS12_CONTENT_TOP+OS12_ROW_H,W-OS12_MARGIN_X*2,OS12_ROW_H);
  HubRect loaded=hr(OS12_MARGIN_X,OS12_CONTENT_TOP+OS12_ROW_H*2,W-OS12_MARGIN_X*2,OS12_ROW_H);
  HubRect inventory=hr(OS12_MARGIN_X,OS12_CONTENT_TOP+OS12_ROW_H*3,W-OS12_MARGIN_X*2,OS12_ROW_H);

  hubOs12EvidenceRow(attention,"Needs Attention",printerAlert?"Printer alert":"Unknown",printerAlert?"Printer evidence available":"Inventory attention evidence unavailable",printerAlert?C10_ORANGE:C10_MUTED);
  hubOs12EvidenceRow(readiness,"Print Readiness","Undetermined","Requirements or inventory evidence unavailable",C10_MUTED);
  hubOs12EvidenceRow(loaded,"Loaded Spools","Unknown","Placement evidence unavailable",C10_MUTED);
  hubOs12EvidenceRow(inventory,"Inventory","Unknown","Filament Inventory device feed not authoritative here",C10_MUTED);
  hubMarkFrameDirty();g_dirty=false;
}
'''

MORE=r'''
static void drawMore(bool full) {
  if(g_displayExperienceView){drawDisplayExperience(full);return;}if(g_toolsView){drawTools(full);return;}
  if(g_ui12SettingsView==1){drawUi13Display();return;}if(g_ui12SettingsView==2){drawUi13Sound();return;}if(g_ui12SettingsView==3){drawUi13Network();return;}if(g_ui12SettingsView==4){drawUi13PrinterPower();return;}if(g_ui12SettingsView==5){drawUi13AfterPrint();return;}if(g_ui12SettingsView==6){drawUi13PrinterAlerts();return;}if(g_ui12SettingsView==7){drawUi13AlertSignals();return;}if(g_ui12SettingsView==8){drawUi13PowerOptions();return;}if(g_ui12SettingsView==9){drawUi13AutoOffConfirm();return;}if(g_ui12SettingsView==10){drawOs12Media();return;}if(g_ui12SettingsView==11){drawOs12Recorder();return;}if(g_ui12SettingsView==12){drawOs12VideoViewer();return;}

  (void)full;
  const bool wifi=workshopPlatformWifiOnline();
  const bool deviceHealthy=hubTouchHealthy()&&recoveryWebReady();

  tft.fillScreen(C10_BG);drawHeader("More",nullptr,3);uiBottomNav(3,nullptr);
  hubOs12NavRow(hubUi12SettingsRect(0),"Display & Appearance","Brightness, standby and after-print behavior",C10_MUTED);
  hubOs12NavRow(hubUi12SettingsRect(1),"Sound & Media","Sounds, microphone, recorder and video",C10_MUTED);
  hubOs12NavRow(hubUi12SettingsRect(2),"Network",wifi?"Connected":"Offline",wifi?C10_GREEN:C10_ORANGE);
  hubOs12NavRow(hubUi12SettingsRect(3),"System",deviceHealthy?"Healthy · power, date, update, diagnostics":"Needs attention · diagnostics available",deviceHealthy?C10_GREEN:C10_ORANGE);
  hubMarkFrameDirty();g_dirty=false;
}
'''

SYSTEM=r'''
static void drawSystem(bool full) {
  if(g_audioSettingsView){drawAudioSettings(full);return;}if(g_networkSettingsView){drawNetworkEssentials(full);return;}if(g_ui12SystemView==1){drawUi12PortalAccess();return;}if(g_ui12SystemView==2){drawUi13DateTime();return;}if(g_ui12SystemView==3){drawUi13SoftwareUpdate();return;}if(g_ui12SystemView==4){drawUi13Diagnostics();return;}
  (void)full;
  const bool touchOk=hubTouchHealthy(),recoveryOk=recoveryWebReady();
  const bool healthy=touchOk&&recoveryOk;
  const bool configured=workshopPlatformState().configuredPrinterCount>0;
  const uint8_t slot=rotState.displayIndex<MAX_PRINTERS?rotState.displayIndex:0;
  const bool printerOk=configured&&workshopPlatformPrinterOnline(slot);

  tft.fillScreen(C10_BG);drawHeader("System",healthy?"Healthy":"Check Device",3);
  hubOs12NavRow(hubUi13SystemCardRect(0),"Device Health",healthy?"Healthy":"Needs attention",healthy?C10_GREEN:C10_ORANGE);
  hubOs12NavRow(hubUi13SystemCardRect(1),"Printer & Power",!configured?"Not configured":(printerOk?"Connected":"Unavailable"),printerOk?C10_GREEN:(configured?C10_ORANGE:C10_MUTED));
  hubOs12NavRow(hubUi13SystemCardRect(2),"Date & Time",hubTimezoneLabel(),C10_MUTED);
  hubOs12NavRow(hubUi13SystemCardRect(3),"Software Update","Version and candidate update status",C10_MUTED);
  hubV1125Action(hubUi13BackRect(),"Back",C10_ACCENT,true,false);
  hubV1125Action(hubUi13ActionRect(),"Local Portal",C10_ACCENT,workshopPlatformWifiOnline(),false);
  hubMarkFrameDirty();g_dirty=false;
}
'''

DISPLAY=r'''
static void drawUi13Display() {
  tft.fillScreen(C10_BG);drawHeader("Display & Appearance",nullptr,3);
  char mainValue[16],standbyValue[16];snprintf(mainValue,sizeof(mainValue),"%u%%",(unsigned)hubLevelPct(brightness));snprintf(standbyValue,sizeof(standbyValue),"%u%%",(unsigned)hubLevelPct(dpSettings.screensaverBrightness));
  hubUi13StepperRow(hubUi13RowRect(0),"Brightness",mainValue,"Active display",C10_ACCENT);
  hubUi13StepperRow(hubUi13RowRect(1),"Standby Brightness",standbyValue,"Idle display",C10_ACCENT);
  hubUi13ToggleRow(hubUi13RowRect(2),"Night Mode","Follow configured night schedule",dpSettings.nightModeEnabled,C10_ACCENT);
  hubV1125Action(hubUi13BackRect(),"Back",C10_ACCENT,true,false);hubV1125Action(hubUi13ActionRect(),"After Print",C10_ACCENT,true,false);
  hubMarkFrameDirty();g_dirty=false;
}
'''

AFTER=r'''
static void drawUi13AfterPrint() {
  tft.fillScreen(C10_BG);drawHeader("After Print",nullptr,3);
  char timeout[20];if(dpSettings.finishDisplayMins==0)strlcpy(timeout,"Immediate",sizeof(timeout));else snprintf(timeout,sizeof(timeout),"%u min",(unsigned)dpSettings.finishDisplayMins);
  hubUi13StepperRow(hubUi13RowRect(0),"Display Behavior",hubAfterPrintLabel(),"Finished-print screen",C10_ACCENT);
  hubUi13StepperRow(hubUi13RowRect(1),"Finish Timeout",timeout,"Before standby",C10_ACCENT);
  hubUi13ToggleRow(hubUi13RowRect(2),"Animated Progress","Use bounded progress motion",dispSettings.animatedBar,C10_ACCENT);
  hubV1125Action(hubUi13BackRect(),"Back",C10_ACCENT,true,false);hubV1125Action(hubUi13ActionRect(),"Done",C10_ACCENT,true,false);
  hubMarkFrameDirty();g_dirty=false;
}
'''

SOUND=r'''
static void drawUi13Sound() {
  tft.fillScreen(C10_BG);drawHeader("Sound & Media",nullptr,3);
  hubUi13ToggleRow(hubUi13RowRect(0),"Event Sounds","Print and device events",buzzerSettings.enabled,C10_ACCENT);
  hubUi13ToggleRow(hubUi13RowRect(1),"Touch Sounds","Immediate tap feedback",buzzerSettings.buttonClick,C10_ACCENT);
  hubUi13InfoRow(hubUi13RowRect(2),"Media","Open","Speaker, microphone, recorder and video",C10_ACCENT);
  hubV1125Action(hubUi13BackRect(),"Back",C10_ACCENT,true,false);
  hubV1125Action(hubUi13ActionRect(),"Printer Alerts",C10_ACCENT,true,false);
  hubMarkFrameDirty();g_dirty=false;
}
'''

NETWORK=r'''
static void drawUi13Network() {
  const bool wifi=workshopPlatformWifiOnline();String ip=wifi?WiFi.localIP().toString():String("Unknown");
  tft.fillScreen(C10_BG);drawHeader("Network",wifi?"Connected":"Offline",3);
  hubUi13InfoRow(hubUi13RowRect(0),"Wi-Fi",wifi?"Connected":"Unavailable",wifi?ip.c_str():"No active network connection",wifi?C10_GREEN:C10_ORANGE);
  hubUi13ToggleRow(hubUi13RowRect(1),"Local Hostname","Advertise the device on the LAN",netSettings.mdnsEnabled,C10_ACCENT);
  hubUi13ToggleRow(hubUi13RowRect(2),"Show IP at Startup","Show address after connection",netSettings.showIPAtStartup,C10_ACCENT);
  hubV1125Action(hubUi13BackRect(),"Back",C10_ACCENT,true,false);hubV1125Action(hubUi13ActionRect(),"Local Portal",C10_ACCENT,wifi,false);
  hubMarkFrameDirty();g_dirty=false;
}
'''

PRINTER_POWER=r'''
static void drawUi13PrinterPower() {
  const bool configured=workshopPlatformState().configuredPrinterCount>0;
  const uint8_t slot=rotState.displayIndex<MAX_PRINTERS?rotState.displayIndex:0;
  const PrinterSlot* p=configured?&displayedPrinter():nullptr;
  const bool connected=configured&&workshopPlatformPrinterOnline(slot);
  const uint8_t plug=configured?hubPowerConfigPlug():0xFF;
  const bool mapped=plug!=0xFF;
  const bool plugReady=mapped&&tasmotaSettings[plug].enabled&&tasmotaSettings[plug].ip[0];
  tft.fillScreen(C10_BG);drawHeader("Printer & Power",connected?"Connected":(configured?"Unavailable":"Not Configured"),3);
  hubUi13InfoRow(hubUi13RowRect(0),"Printer",p&&p->config.name[0]?p->config.name:(configured?"Configured":"Not configured"),connected?"Fresh printer connection":(configured?"No fresh printer connection":"Setup required"),connected?C10_GREEN:(configured?C10_ORANGE:C10_MUTED));
  hubUi13InfoRow(hubUi13RowRect(1),"Smart Plug",plugReady?"Ready":(mapped?"Needs setup":"Not mapped"),mapped?"Power mapping exists":"No power mapping",plugReady?C10_GREEN:C10_MUTED);
  hubUi13ToggleRow(hubUi13RowRect(2),"Automatic Power Off",mapped&&tasmotaSettings[plug].autoOffEnabled?"Enabled after finished print":"Disabled or unavailable",mapped&&tasmotaSettings[plug].autoOffEnabled,C10_ACCENT);
  hubV1125Action(hubUi13BackRect(),"Back",C10_ACCENT,true,false);hubV1125Action(hubUi13ActionRect(),"Power Options",C10_ACCENT,mapped,false);
  hubMarkFrameDirty();g_dirty=false;
}
'''

POWER_OPTIONS=r'''
static void drawUi13PowerOptions() {
  const bool configured=workshopPlatformState().configuredPrinterCount>0;const uint8_t plug=configured?hubPowerConfigPlug():0xFF;const bool mapped=plug!=0xFF;
  tft.fillScreen(C10_BG);drawHeader("Power Options",mapped?"Ready":"Unavailable",3);
  if(mapped){
    TasmotaSettings& ps=tasmotaSettings[plug];char delay[20];snprintf(delay,sizeof(delay),"%u min",(unsigned)ps.autoOffDelayMin);
    hubUi13StepperRow(hubUi13RowRect(0),"Auto-Off Delay",delay,"After a finished print",C10_ACCENT);
    hubUi13ToggleRow(hubUi13RowRect(1),"Cancel on Door","Keep power on if the door opens",ps.autoOffCancelOnDoor,C10_ACCENT);
    hubUi13InfoRow(hubUi13RowRect(2),"Advanced Setup","Local Portal","Address and device details",C10_MUTED);
  } else {
    hubUi13InfoRow(hubUi13RowRect(0),"Smart Plug","Unavailable","No mapped power device",C10_MUTED);
    hubUi13InfoRow(hubUi13RowRect(1),"Automatic Power Off","Unavailable","Map a smart plug first",C10_MUTED);
    hubUi13InfoRow(hubUi13RowRect(2),"Advanced Setup","Local Portal","Configure power mapping there",C10_MUTED);
  }
  hubV1125Action(hubUi13BackRect(),"Back",C10_ACCENT,true,false);hubV1125Action(hubUi13ActionRect(),"Local Portal",C10_ACCENT,true,false);
  hubMarkFrameDirty();g_dirty=false;
}
'''

AUTO_OFF=r'''
static void drawUi13AutoOffConfirm() {
  const int16_t W=tft.width();tft.fillScreen(C10_BG);drawHeader("Enable Auto-Off?",nullptr,3);
  HubRect card=hr(OS12_MARGIN_X,52,W-OS12_MARGIN_X*2,146);hubOs12StatePanel(card,"Guarded automation","Automatic printer power-off","Turns off only the mapped plug after a finished print and configured delay.",C10_ORANGE,true);
  hubV1125Action(hubUi13BackRect(),"Cancel",C10_ACCENT,true,false);hubV1125Action(hubUi13ActionRect(),"Enable",C10_ORANGE,true,false);
  hubMarkFrameDirty();g_dirty=false;
}
'''

DATE_TIME=r'''
static void drawUi13DateTime() {
  tft.fillScreen(C10_BG);drawHeader("Date & Time",nullptr,3);
  hubUi13StepperRow(hubUi13RowRect(0),"Time Zone",hubTimezoneLabel(),"Local region",C10_ACCENT);
  hubUi13ToggleRow(hubUi13RowRect(1),"24-Hour Time","Use a 24-hour clock",netSettings.use24h,C10_ACCENT);
  hubUi13StepperRow(hubUi13RowRect(2),"Date Format",hubDateFormatLabel(netSettings.dateFormat),"Display format",C10_ACCENT);
  hubV1125Action(hubUi13BackRect(),"Back",C10_ACCENT,true,false);hubV1125Action(hubUi13ActionRect(),"Done",C10_ACCENT,true,false);hubMarkFrameDirty();g_dirty=false;
}
'''

UPDATE=r'''
static void drawUi13SoftwareUpdate() {
  const int16_t W=tft.width();tft.fillScreen(C10_BG);drawHeader("Software Update",nullptr,3);
  HubRect hero=hr(OS12_MARGIN_X,48,W-OS12_MARGIN_X*2,86);hubV1125Card(hero,C10_ACCENT,true);
  char ver[40];snprintf(ver,sizeof(ver),"Workshop OS %s",SMART_HOME_VERSION);
  uiDrawFit(ver,hero.x+16,hero.y+14,hero.w-32,FONT_LARGE,TL_DATUM,C10_TEXT,C10_SURFACE_2);
  uiDrawFit("Candidate build · acceptance required",hero.x+16,hero.y+56,hero.w-32,FONT_SMALL,TL_DATUM,C10_ORANGE,C10_SURFACE_2);
  hubUi13InfoRow(hubUi13RowRect(2),"Device Update","Local Portal","Install only exact validated candidate artifacts",C10_MUTED);
  hubV1125Action(hubUi13BackRect(),"Back",C10_ACCENT,true,false);hubV1125Action(hubUi13ActionRect(),"Local Portal",C10_ACCENT,true,false);hubMarkFrameDirty();g_dirty=false;
}
'''

DIAG=r'''
static void drawUi13Diagnostics() {
  const bool touchOk=hubTouchHealthy(),recoveryOk=recoveryWebReady(),wifi=workshopPlatformWifiOnline();
  const bool configured=workshopPlatformState().configuredPrinterCount>0;
  const uint8_t slot=rotState.displayIndex<MAX_PRINTERS?rotState.displayIndex:0;
  const bool printerOk=configured&&workshopPlatformPrinterOnline(slot);
  const bool healthy=touchOk&&recoveryOk;
  tft.fillScreen(C10_BG);drawHeader("Diagnostics",healthy?"Healthy":"Check Device",3);
  hubUi13InfoRow(hubUi13RowRect(0),"Touch",touchOk?"OK":"Check","Physical touchscreen input",touchOk?C10_GREEN:C10_ORANGE);
  hubUi13InfoRow(hubUi13RowRect(1),"Recovery",recoveryOk?"Ready":"Starting","Recovery service",recoveryOk?C10_GREEN:C10_ORANGE);
  hubUi13InfoRow(hubUi13RowRect(2),"Connectivity",!wifi?"Offline":(printerOk?"Network + printer":"Network only"),"Connectivity is not device-health proof",wifi?C10_GREEN:C10_ORANGE);
  hubV1125Action(hubUi13BackRect(),"Back",C10_ACCENT,true,false);hubV1125Action(hubUi13ActionRect(),"Local Portal",C10_ACCENT,wifi,false);hubMarkFrameDirty();g_dirty=false;
}
'''

PORTAL=r'''
static void drawUi12PortalAccess() {
  const int16_t W=tft.width();const bool wifi=workshopPlatformWifiOnline();String ip=wifi?WiFi.localIP().toString():String("Wi-Fi required");
  tft.fillScreen(C10_BG);drawHeader("Local Portal",wifi?"Ready":"Offline",3);
  HubRect card=hr(OS12_MARGIN_X,48,W-OS12_MARGIN_X*2,156);hubV1125Card(card,wifi?C10_ACCENT:C10_ORANGE,true);
  uiDrawFit("Authenticated local administration",card.x+16,card.y+14,card.w-32,FONT_LARGE,TL_DATUM,C10_TEXT,C10_SURFACE_2);
  uiDrawFit(wifi?"Open this device address from the same LAN.":"Connect the WS350 to Wi-Fi before using Local Portal.",card.x+16,card.y+55,card.w-32,FONT_SMALL,TL_DATUM,C10_MUTED,C10_SURFACE_2);
  uiDrawFit(ip.c_str(),card.x+16,card.y+82,card.w/2-24,FONT_BODY,TL_DATUM,wifi?C10_ACCENT:C10_ORANGE,C10_SURFACE_2);
  uiDrawFit("Access Code",card.x+card.w/2,card.y+82,100,FONT_SMALL,TL_DATUM,C10_MUTED,C10_SURFACE_2);
  uiDrawFit(securityPortalCode(),card.x+card.w/2,card.y+108,card.w/2-24,FONT_LARGE,TL_DATUM,C10_TEXT,C10_SURFACE_2);
  uiDrawFit("Code changes after every reboot.",card.x+16,card.y+143,card.w-32,FONT_SMALL,BL_DATUM,C10_MUTED,C10_SURFACE_2);
  hubV1125Action(hubUi12SystemBackRect(),"Back",C10_ACCENT,true,false);hubMarkFrameDirty();g_dirty=false;
}
'''

def apply(repo:Path)->None:
    p=repo/"src"/"smart_hub.cpp";text=load(p)
    if "static uint8_t gOs12SettingsParent = 0;" not in text:
        marker="static uint8_t gOs12PortalParent = 0;"
        if marker not in text:
            raise PatchError("OS12 parent-state insertion anchor missing")
        text=text.replace(marker,marker+"\nstatic uint8_t gOs12SettingsParent = 0; // 0=More, 1=System",1)
    if "static void hubOs12StatePanel(" not in text:
        anchor="static void drawHome(bool full)"
        if text.count(anchor)!=1: raise PatchError("state helper insertion anchor missing/non-unique")
        text=text.replace(anchor,STATE_HELPER+"\n"+anchor,1)
    for sig,repl in (
        ("static void drawHome(bool full)",HOME),
        ("static void drawWorkshop(bool full)",WORKSHOP),
        ("static void drawMore(bool full)",MORE),
        ("static void drawSystem(bool full)",SYSTEM),
        ("static void drawUi13Display()",DISPLAY),
        ("static void drawUi13AfterPrint()",AFTER),
        ("static void drawUi13Sound()",SOUND),
        ("static void drawUi13Network()",NETWORK),
        ("static void drawUi13PrinterPower()",PRINTER_POWER),
        ("static void drawUi13PowerOptions()",POWER_OPTIONS),
        ("static void drawUi13AutoOffConfirm()",AUTO_OFF),
        ("static void drawUi13DateTime()",DATE_TIME),
        ("static void drawUi13SoftwareUpdate()",UPDATE),
        ("static void drawUi13Diagnostics()",DIAG),
        ("static void drawUi12PortalAccess()",PORTAL),
    ):
        text=replace_function(text,sig,repl)
    sound_touch_old = '''      if(g_ui12SettingsView==2){
        if(hubUi13ToggleRect(0).contains(x,y)){buzzerSettings.enabled=!buzzerSettings.enabled;saveBuzzerSettings();initBuzzer();buzzerPlay(BUZZ_CLICK);g_dirty=true;return true;}
        if(hubUi13ToggleRect(1).contains(x,y)){buzzerSettings.buttonClick=!buzzerSettings.buttonClick;saveBuzzerSettings();buzzerPlay(BUZZ_CLICK);g_dirty=true;return true;}
        if(hubUi13ToggleRect(2).contains(x,y)){buzzerSettings.bedCooldownAlert=!buzzerSettings.bedCooldownAlert;saveBuzzerSettings();buzzerPlay(BUZZ_CLICK);g_dirty=true;return true;}
        if(hubUi13BackRect().contains(x,y)){g_ui12SettingsView=0;buzzerPlay(BUZZ_CLICK);g_dirty=true;return true;}
        if(hubUi13ActionRect().contains(x,y)){g_ui12SettingsView=10;buzzerPlay(BUZZ_CLICK);g_dirty=true;return true;}
        return true;
      }'''
    sound_touch_new = '''      if(g_ui12SettingsView==2){
        if(hubUi13ToggleRect(0).contains(x,y)){buzzerSettings.enabled=!buzzerSettings.enabled;saveBuzzerSettings();initBuzzer();buzzerPlay(BUZZ_CLICK);g_dirty=true;return true;}
        if(hubUi13ToggleRect(1).contains(x,y)){buzzerSettings.buttonClick=!buzzerSettings.buttonClick;saveBuzzerSettings();buzzerPlay(BUZZ_CLICK);g_dirty=true;return true;}
        if(hubUi13RowRect(2).contains(x,y)){g_ui12SettingsView=10;buzzerPlay(BUZZ_CLICK);g_dirty=true;return true;}
        if(hubUi13BackRect().contains(x,y)){g_ui12SettingsView=0;buzzerPlay(BUZZ_CLICK);g_dirty=true;return true;}
        if(hubUi13ActionRect().contains(x,y)){g_ui12SettingsView=6;buzzerPlay(BUZZ_CLICK);g_dirty=true;return true;}
        return true;
      }'''
    if sound_touch_old not in text:
        raise PatchError("Sound & Media touch routing anchor missing")
    text=text.replace(sound_touch_old,sound_touch_new,1)

    # Preserve deterministic parentage for Printer & Power, which is owned
    # by System even though the historical renderer uses SCREEN_HUB_MORE state.
    more_route_old='if(i<3){g_ui12SettingsView=(uint8_t)(i+1U);buzzerPlay(BUZZ_CLICK);g_dirty=true;}'
    more_route_new='if(i<3){gOs12SettingsParent=0;g_ui12SettingsView=(uint8_t)(i+1U);buzzerPlay(BUZZ_CLICK);g_dirty=true;}'
    if more_route_old not in text:
        raise PatchError("More child parent-routing anchor missing")
    text=text.replace(more_route_old,more_route_new,1)

    system_power_old='else if(i==1){g_ui12SettingsView=4;setPage(SCREEN_HUB_MORE);}'
    system_power_new='else if(i==1){gOs12SettingsParent=1;g_ui12SettingsView=4;setPage(SCREEN_HUB_MORE);}'
    if system_power_old not in text:
        raise PatchError("System -> Printer & Power parent-routing anchor missing")
    text=text.replace(system_power_old,system_power_new,1)

    power_back_old='if(hubUi13BackRect().contains(x,y)){g_ui12SettingsView=0;buzzerPlay(BUZZ_CLICK);g_dirty=true;return true;}'
    state4=text.find('if(g_ui12SettingsView==4){')
    state8=text.find('if(g_ui12SettingsView==8){',state4)
    if state4 < 0 or state8 < 0:
        raise PatchError("Printer & Power touch block missing")
    block=text[state4:state8]
    if power_back_old not in block:
        raise PatchError("Printer & Power Back anchor missing")
    power_back_new='if(hubUi13BackRect().contains(x,y)){g_ui12SettingsView=0;if(gOs12SettingsParent==1){gOs12SettingsParent=0;g_ui12SystemView=0;setPage(SCREEN_HUB_SYSTEM);}buzzerPlay(BUZZ_CLICK);g_dirty=true;return true;}'
    block=block.replace(power_back_old,power_back_new,1)
    text=text[:state4]+block+text[state8:]

    # Deterministic capture/navigation of Printer & Power should also identify
    # System as its logical parent.
    capture_old='if (strcmp(pageName, "settings-printer-power") == 0) { setPage(SCREEN_HUB_MORE);g_ui12SettingsView=4;g_ui12SystemView=0;g_networkSettingsView=false;g_audioSettingsView=false;g_dirty=true;return true; }'
    capture_new='if (strcmp(pageName, "settings-printer-power") == 0) { setPage(SCREEN_HUB_MORE);gOs12SettingsParent=1;g_ui12SettingsView=4;g_ui12SystemView=0;g_networkSettingsView=false;g_audioSettingsView=false;g_dirty=true;return true; }'
    if capture_old not in text:
        raise PatchError("Printer & Power native route anchor missing")
    text=text.replace(capture_old,capture_new,1)

    p.write_text(text,encoding="utf-8")
    print("Workshop OS 12 Home/Workshop/More/System product surfaces completed")

def main()->int:
    ap=argparse.ArgumentParser();ap.add_argument("--repo",required=True);ap.add_argument("--apply",action="store_true");a=ap.parse_args()
    if not a.apply: raise SystemExit("refusing to modify source without --apply")
    try: apply(Path(a.repo).resolve())
    except PatchError as exc: raise SystemExit(f"FAIL: {exc}") from exc
    return 0

if __name__=="__main__": raise SystemExit(main())
