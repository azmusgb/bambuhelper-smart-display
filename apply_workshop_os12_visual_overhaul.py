#!/usr/bin/env python3
"""Apply the final Workshop OS 12 whole-device visual overhaul.

Presentation only. Keeps all printer, inventory, update, recovery, media and
security authorities unchanged while replacing the WS350 480x320 visual system
and the primary/secondary product surfaces.
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
            if depth==0: return i+1
        i+=1
    raise PatchError(f"{label}: closing brace missing")

def replace_function(text: str, signature: str, replacement: str) -> str:
    start=text.find(signature)
    if start<0 or text.find(signature,start+1)>=0:
        raise PatchError(f"function missing/non-unique: {signature}")
    return text[:start]+replacement.strip()+text[braced_end(text,start,signature):]

PALETTE=r'''
static constexpr uint16_t OS12V_BG       = 0x0841; // graphite
static constexpr uint16_t OS12V_SURFACE  = 0x10A2; // raised graphite
static constexpr uint16_t OS12V_SURFACE2 = 0x18E3; // selected/interactive
static constexpr uint16_t OS12V_LINE     = 0x2945; // quiet separator
static constexpr uint16_t OS12V_TEXT     = 0xF7BE; // warm white
static constexpr uint16_t OS12V_MUTED    = 0x9D33; // cool gray
static constexpr uint16_t OS12V_ACCENT   = 0x05F6; // cyan/teal
static constexpr uint16_t OS12V_BLUE     = 0x3CFF; // information
static constexpr uint16_t OS12V_GREEN    = 0x36EA; // ready
static constexpr uint16_t OS12V_AMBER    = 0xFDC0; // attention
static constexpr uint16_t OS12V_RED      = 0xF3AA; // destructive/fault
static constexpr int16_t OS12V_RADIUS    = 12;
static constexpr int16_t OS12V_INSET     = 12;
'''

CARD=r'''
static void hubV1125Card(const HubRect& r,uint16_t rail=UI_BORDER_2,bool strong=false) {
  const uint16_t bg=strong?OS12V_SURFACE2:OS12V_SURFACE;
  tft.fillRoundRect(r.x,r.y,r.w,r.h,OS12V_RADIUS,bg);
  tft.drawRoundRect(r.x,r.y,r.w,r.h,OS12V_RADIUS,strong?OS12V_LINE:OS12V_LINE);
  const bool semantic=rail!=UI_BORDER_2 && rail!=UI_BORDER && rail!=W25_LINE;
  if(semantic){
    const uint16_t c=(rail==C10_RED||rail==OS12V_RED)?OS12V_RED:((rail==C10_ORANGE||rail==OS12V_AMBER)?OS12V_AMBER:((rail==C10_GREEN||rail==OS12V_GREEN)?OS12V_GREEN:OS12V_ACCENT));
    tft.fillRoundRect(r.x,r.y,4,r.h,2,c);
  }
}
'''

HEADER=r'''
static void drawHeader(const char* title,const char* right,uint8_t page) {
  const int16_t W=tft.width(),HH=hubHeaderH();
  const bool online=WiFi.status()==WL_CONNECTED;
  const bool explicitState=right&&right[0];
  tft.fillRect(0,0,W,HH,OS12V_BG);
  uiDrawFit(title?title:"Home",OS12V_INSET,7,286,FONT_BODY,TL_DATUM,OS12V_TEXT,OS12V_BG);
  const char* state=explicitState?right:(online?"ONLINE":"OFFLINE");
  uint16_t c=OS12V_MUTED;
  if(explicitState)c=hubUi13HeaderStateColor(state,true,online);
  else c=online?OS12V_GREEN:OS12V_AMBER;
  tft.fillCircle(W-100,17,4,c);
  uiDrawFit(state,W-OS12V_INSET,17,82,FONT_SMALL,MR_DATUM,c,OS12V_BG);
  tft.drawFastHLine(OS12V_INSET,HH-1,W-OS12V_INSET*2,OS12V_LINE);
  (void)hubV1125UiFingerprint(page);
}
'''

BOTTOM=r'''
static void uiBottomNav(uint8_t active,const char* nextPage) {
  (void)nextPage;
  const int16_t y=tft.height()-hubNavH(),W=tft.width();
  static const char* labels[4]={"Home","Printer","Workshop","More"};
  tft.fillRect(0,y,W,hubNavH(),OS12V_SURFACE);
  tft.drawFastHLine(0,y,W,OS12V_LINE);
  for(uint8_t i=0;i<4;i++){
    HubRect r=hubNavRect(i);const bool selected=i==active;
    const uint16_t fg=selected?OS12V_ACCENT:OS12V_MUTED;
    if(selected){
      tft.fillRoundRect(r.x+8,r.y+4,r.w-16,r.h-8,10,OS12V_SURFACE2);
      tft.fillRoundRect(r.x+r.w/2-18,r.y+3,36,3,2,OS12V_ACCENT);
    }
    const int16_t cx=r.x+r.w/2;
    hubV1125TabIcon(i,cx,r.y+16,fg);
    uiDrawFit(labels[i],cx,r.y+34,r.w-12,FONT_SMALL,TC_DATUM,fg,selected?OS12V_SURFACE2:OS12V_SURFACE);
  }
}
'''

ACTION=r'''
static void hubV1125Action(const HubRect& r,const char* label,uint16_t c,bool enabled=true,bool destructive=false) {
  const uint16_t bg=enabled?OS12V_SURFACE2:OS12V_SURFACE;
  const uint16_t semantic=destructive?OS12V_RED:((c==C10_GREEN||c==OS12V_GREEN)?OS12V_GREEN:((c==C10_ORANGE||c==OS12V_AMBER)?OS12V_AMBER:OS12V_ACCENT));
  const uint16_t fg=enabled?(destructive?OS12V_RED:OS12V_TEXT):OS12V_MUTED;
  tft.fillRoundRect(r.x,r.y,r.w,r.h,OS12V_RADIUS,bg);
  tft.drawRoundRect(r.x,r.y,r.w,r.h,OS12V_RADIUS,enabled?semantic:OS12V_LINE);
  if(enabled)tft.fillCircle(r.x+17,r.y+r.h/2,4,semantic);
  uiDrawFit(label,r.x+r.w/2+5,r.y+r.h/2,r.w-44,FONT_BODY,MC_DATUM,fg,bg);
}
'''

ROW=r'''
static void hubOs12RowSurface(const HubRect& r) {
  tft.fillRoundRect(r.x,r.y,r.w,r.h,10,OS12V_SURFACE);
  tft.drawRoundRect(r.x,r.y,r.w,r.h,10,OS12V_LINE);
}
'''

NAVROW=r'''
static void hubOs12NavRow(const HubRect& r,const char* title,const char* detail,uint16_t valueColor=C10_MUTED) {
  hubOs12RowSurface(r);
  uint16_t detailColor=OS12V_MUTED;
  if(valueColor==C10_GREEN||valueColor==OS12V_GREEN)detailColor=OS12V_GREEN;
  else if(valueColor==C10_ORANGE||valueColor==OS12V_AMBER)detailColor=OS12V_AMBER;
  else if(valueColor==C10_RED||valueColor==OS12V_RED)detailColor=OS12V_RED;
  uiDrawFit(title,r.x+OS12V_INSET,r.y+8,r.w-58,FONT_BODY,TL_DATUM,OS12V_TEXT,OS12V_SURFACE);
  uiDrawFit(detail,r.x+OS12V_INSET,r.y+r.h-9,r.w-58,FONT_SMALL,BL_DATUM,detailColor,OS12V_SURFACE);
  const int16_t cx=r.x+r.w-18,cy=r.y+r.h/2;
  tft.drawLine(cx-4,cy-5,cx+1,cy,OS12V_MUTED);
  tft.drawLine(cx+1,cy,cx-4,cy+5,OS12V_MUTED);
}
'''

EVIDENCE=r'''
static void hubOs12EvidenceRow(const HubRect& r,const char* title,const char* value,const char* detail,uint16_t valueColor=C10_MUTED) {
  hubOs12RowSurface(r);
  uint16_t vc=OS12V_MUTED;
  if(valueColor==C10_GREEN||valueColor==OS12V_GREEN)vc=OS12V_GREEN;
  else if(valueColor==C10_ORANGE||valueColor==OS12V_AMBER)vc=OS12V_AMBER;
  else if(valueColor==C10_RED||valueColor==OS12V_RED)vc=OS12V_RED;
  else if(valueColor==C10_ACCENT||valueColor==OS12V_ACCENT)vc=OS12V_ACCENT;
  else if(valueColor==C10_TEXT||valueColor==OS12V_TEXT)vc=OS12V_TEXT;
  const int16_t valueW=180;
  uiDrawFit(title,r.x+OS12V_INSET,r.y+7,r.w-OS12V_INSET*2,FONT_SMALL,TL_DATUM,OS12V_MUTED,OS12V_SURFACE);
  uiDrawFit(value,r.x+OS12V_INSET,r.y+r.h-10,valueW,FONT_BODY,BL_DATUM,vc,OS12V_SURFACE);
  uiDrawFit(detail,r.x+r.w-OS12V_INSET,r.y+r.h-10,r.w-valueW-OS12V_INSET*3,FONT_SMALL,BR_DATUM,OS12V_MUTED,OS12V_SURFACE);
}
'''

TOGGLE=r'''
static void hubUi13ToggleRow(const HubRect& r,const char* label,const char* detail,bool on,uint16_t accent=C10_ACCENT) {
  (void)accent;hubOs12RowSurface(r);
  const int16_t controlW=62;
  uiDrawFit(label,r.x+OS12V_INSET,r.y+8,r.w-controlW-OS12V_INSET*3,FONT_BODY,TL_DATUM,OS12V_TEXT,OS12V_SURFACE);
  uiDrawFit(detail,r.x+OS12V_INSET,r.y+r.h-9,r.w-controlW-OS12V_INSET*3,FONT_SMALL,BL_DATUM,OS12V_MUTED,OS12V_SURFACE);
  HubRect sw=hr(r.x+r.w-controlW-OS12V_INSET,r.y+(r.h-34)/2,controlW,34);
  tft.fillRoundRect(sw.x,sw.y,sw.w,sw.h,17,on?OS12V_ACCENT:OS12V_SURFACE2);
  tft.drawRoundRect(sw.x,sw.y,sw.w,sw.h,17,on?OS12V_ACCENT:OS12V_LINE);
  const int16_t d=26,cx=on?(sw.x+sw.w-4-d/2):(sw.x+4+d/2);
  tft.fillCircle(cx,sw.y+sw.h/2,d/2,OS12V_TEXT);
}
'''

STEPPER=r'''
static void hubUi13StepperRow(const HubRect& r,const char* label,const char* value,const char* detail,uint16_t accent=C10_ACCENT) {
  (void)accent;hubOs12RowSurface(r);
  const int16_t buttonW=48,buttonH=44;
  uiDrawFit(label,r.x+OS12V_INSET,r.y+7,r.w-230,FONT_SMALL,TL_DATUM,OS12V_MUTED,OS12V_SURFACE);
  uiDrawFit(detail,r.x+OS12V_INSET,r.y+r.h-9,r.w-230,FONT_SMALL,BL_DATUM,OS12V_MUTED,OS12V_SURFACE);
  HubRect minus=hr(r.x+r.w-220,r.y+(r.h-buttonH)/2,buttonW,buttonH);
  HubRect plus=hr(r.x+r.w-buttonW-OS12V_INSET,r.y+(r.h-buttonH)/2,buttonW,buttonH);
  for(HubRect b:{minus,plus}){tft.fillRoundRect(b.x,b.y,b.w,b.h,10,OS12V_SURFACE2);tft.drawRoundRect(b.x,b.y,b.w,b.h,10,OS12V_LINE);}
  uiDrawFit("-",minus.x+minus.w/2,minus.y+minus.h/2,minus.w-8,FONT_LARGE,MC_DATUM,OS12V_ACCENT,OS12V_SURFACE2);
  uiDrawFit("+",plus.x+plus.w/2,plus.y+plus.h/2,plus.w-8,FONT_LARGE,MC_DATUM,OS12V_ACCENT,OS12V_SURFACE2);
  uiDrawFit(value,minus.x+minus.w+8,r.y+r.h/2,plus.x-minus.x-minus.w-16,FONT_BODY,MC_DATUM,OS12V_TEXT,OS12V_SURFACE);
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
  const uint8_t slot=rotState.displayIndex<MAX_PRINTERS?rotState.displayIndex:0;
  const bool paused=configured&&workshopPlatformPrinterPaused(slot);
  const bool printing=configured&&workshopPlatformPrinterPrinting(slot);
  const bool online=configured&&workshopPlatformPrinterOnline(slot);
  const bool alert=s&&uiHmsCount(*s)>0;
  const uint16_t sc=!configured?C10_MUTED:(!online?C10_ORANGE:(alert?C10_RED:(paused?C10_ORANGE:(printing?C10_ACCENT:C10_GREEN))));
  const char* state=!configured?"SETUP":(!online?"OFFLINE":(alert?"ATTENTION":(paused?"PAUSED":(printing?"PRINTING":"READY"))));

  tft.fillScreen(OS12V_BG);drawHeader("Home",state,0);uiBottomNav(0,nullptr);

  HubRect hero=hr(OS12V_INSET,46,W-OS12V_INSET*2,76);
  hubV1125Card(hero,sc,true);
  uiDrawFit(p&&p->config.name[0]?p->config.name:"Printer",hero.x+14,hero.y+11,hero.w-28,FONT_SMALL,TL_DATUM,OS12V_MUTED,OS12V_SURFACE2);
  uiDrawFit(state,hero.x+14,hero.y+31,hero.w-28,FONT_LARGE,TL_DATUM,
      !configured?OS12V_MUTED:(!online?OS12V_AMBER:(alert?OS12V_RED:(printing?OS12V_ACCENT:OS12V_GREEN))),OS12V_SURFACE2);
  uiDrawFit(printing||paused?"Print in progress":(online?"Ready for work":"Check connection"),hero.x+14,hero.y+65,hero.w-28,FONT_SMALL,BL_DATUM,OS12V_MUTED,OS12V_SURFACE2);

  HubRect job=hr(OS12V_INSET,128,W-OS12V_INSET*2,54);
  if(printing||paused){char meta[36],rem[20];formatDuration(s->remainingMinutes,rem,sizeof(rem));snprintf(meta,sizeof(meta),"%u%% · %s left",(unsigned)s->progress,rem);hubOs12EvidenceRow(job,"CURRENT PRINT",jobDisplayName(*s),meta,C10_TEXT);}
  else hubOs12EvidenceRow(job,"CURRENT PRINT",online?"None":"Unknown",online?"Printer idle":"No fresh printer evidence",online?C10_TEXT:C10_MUTED);

  HubRect inventory=hr(OS12V_INSET,188,W-OS12V_INSET*2,62);
  hubOs12EvidenceRow(inventory,"FILAMENT INVENTORY","Unknown","No authoritative inventory evidence",C10_MUTED);
  hubMarkFrameDirty();g_dirty=false;
}
'''

WORKSHOP=r'''
static void drawWorkshop(bool full) {
  (void)full;const int16_t W=tft.width();
  tft.fillScreen(OS12V_BG);drawHeader("Workshop","INVENTORY",2);uiBottomNav(2,nullptr);
  const BambuState* s=isAnyPrinterConfigured()?&displayedPrinter().state:nullptr;
  const bool printerAlert=s&&uiHmsCount(*s)>0;
  HubRect readiness=hr(OS12V_INSET,48,W-OS12V_INSET*2,66);
  HubRect loaded=hr(OS12V_INSET,120,W-OS12V_INSET*2,60);
  HubRect attention=hr(OS12V_INSET,186,W-OS12V_INSET*2,64);
  hubOs12EvidenceRow(readiness,"PRINT READINESS","Undetermined","Print requirements or inventory evidence missing",C10_MUTED);
  hubOs12EvidenceRow(loaded,"LOADED SPOOLS","Unknown","Canonical placement unknown",C10_MUTED);
  hubOs12EvidenceRow(attention,"ATTENTION",printerAlert?"Printer alert":"No inventory signal",printerAlert?"Review Printer diagnostics":"Authoritative attention evidence unavailable",printerAlert?C10_ORANGE:C10_MUTED);
  hubMarkFrameDirty();g_dirty=false;
}
'''

MORE=r'''
static void drawMore(bool full) {
  if(g_displayExperienceView){drawDisplayExperience(full);return;}if(g_toolsView){drawTools(full);return;}
  if(g_ui12SettingsView==1){drawUi13Display();return;}if(g_ui12SettingsView==2){drawUi13Sound();return;}if(g_ui12SettingsView==3){drawUi13Network();return;}if(g_ui12SettingsView==4){drawUi13PrinterPower();return;}if(g_ui12SettingsView==5){drawUi13AfterPrint();return;}if(g_ui12SettingsView==6){drawUi13PrinterAlerts();return;}if(g_ui12SettingsView==7){drawUi13AlertSignals();return;}if(g_ui12SettingsView==8){drawUi13PowerOptions();return;}if(g_ui12SettingsView==9){drawUi13AutoOffConfirm();return;}if(g_ui12SettingsView==10){drawOs12Media();return;}if(g_ui12SettingsView==11){drawOs12Recorder();return;}if(g_ui12SettingsView==12){drawOs12VideoViewer();return;}
  (void)full;const bool wifi=workshopPlatformWifiOnline();const bool healthy=hubTouchHealthy()&&recoveryWebReady();
  tft.fillScreen(OS12V_BG);drawHeader("More",healthy?"HEALTHY":"CHECK",3);uiBottomNav(3,nullptr);
  hubOs12NavRow(hubUi12SettingsRect(0),"Display & Appearance","Brightness · standby · after print",C10_MUTED);
  hubOs12NavRow(hubUi12SettingsRect(1),"Sound & Media","Volume · microphone · recorder · video",C10_MUTED);
  hubOs12NavRow(hubUi12SettingsRect(2),"Network",wifi?"Connected":"Offline",wifi?C10_GREEN:C10_ORANGE);
  hubOs12NavRow(hubUi12SettingsRect(3),"System",healthy?"Healthy · power · time · updates · diagnostics":"Needs attention · open diagnostics",healthy?C10_GREEN:C10_ORANGE);
  hubMarkFrameDirty();g_dirty=false;
}
'''

SYSTEM=r'''
static void drawSystem(bool full) {
  if(g_audioSettingsView){drawAudioSettings(full);return;}if(g_networkSettingsView){drawNetworkEssentials(full);return;}if(g_ui12SystemView==1){drawUi12PortalAccess();return;}if(g_ui12SystemView==2){drawUi13DateTime();return;}if(g_ui12SystemView==3){drawUi13SoftwareUpdate();return;}if(g_ui12SystemView==4){drawUi13Diagnostics();return;}
  (void)full;const bool touchOk=hubTouchHealthy(),recoveryOk=recoveryWebReady();const bool healthy=touchOk&&recoveryOk;
  const bool configured=workshopPlatformState().configuredPrinterCount>0;const uint8_t slot=rotState.displayIndex<MAX_PRINTERS?rotState.displayIndex:0;const bool printerOk=configured&&workshopPlatformPrinterOnline(slot);
  tft.fillScreen(OS12V_BG);drawHeader("System",healthy?"HEALTHY":"CHECK",3);
  hubOs12NavRow(hubUi13SystemCardRect(0),"Device Health",healthy?"Healthy":"Needs attention",healthy?C10_GREEN:C10_ORANGE);
  hubOs12NavRow(hubUi13SystemCardRect(1),"Printer & Power",!configured?"Not configured":(printerOk?"Connected":"Unavailable"),printerOk?C10_GREEN:(configured?C10_ORANGE:C10_MUTED));
  hubOs12NavRow(hubUi13SystemCardRect(2),"Date & Time",hubTimezoneLabel(),C10_MUTED);
  hubOs12NavRow(hubUi13SystemCardRect(3),"Software Update","Version · candidate · verification",C10_MUTED);
  hubV1125Action(hubUi13BackRect(),"Back",C10_ACCENT,true,false);hubV1125Action(hubUi13ActionRect(),"Local Portal",C10_ACCENT,workshopPlatformWifiOnline(),false);
  hubMarkFrameDirty();g_dirty=false;
}
'''

DATE_TIME=r'''
static void drawUi13DateTime() {
  tft.fillScreen(OS12V_BG);drawHeader("Date & Time","LOCAL",3);
  hubUi13StepperRow(hubUi13RowRect(0),"Time Zone",hubTimezoneLabel(),"Use - / + to change",C10_ACCENT);
  hubUi13ToggleRow(hubUi13RowRect(1),"24-Hour Clock",netSettings.use24h?"Showing 24-hour time":"Showing 12-hour time",netSettings.use24h,C10_ACCENT);
  hubUi13StepperRow(hubUi13RowRect(2),"Date Format",hubDateFormatLabel(netSettings.dateFormat),"Use - / + to change",C10_ACCENT);
  hubV1125Action(hubUi13BackRect(),"Back",C10_ACCENT,true,false);hubV1125Action(hubUi13ActionRect(),"Done",C10_ACCENT,true,false);
  hubMarkFrameDirty();g_dirty=false;
}
'''

UPDATE=r'''
static void drawUi13SoftwareUpdate() {
  const int16_t W=tft.width();tft.fillScreen(OS12V_BG);drawHeader("Software Update","CANDIDATE",3);
  HubRect hero=hr(OS12V_INSET,48,W-OS12V_INSET*2,76);hubV1125Card(hero,C10_ACCENT,true);
  char ver[40];snprintf(ver,sizeof(ver),"Workshop OS %s",SMART_HOME_VERSION);
  uiDrawFit("INSTALLED",hero.x+14,hero.y+10,hero.w-28,FONT_SMALL,TL_DATUM,OS12V_MUTED,OS12V_SURFACE2);
  uiDrawFit(ver,hero.x+14,hero.y+31,hero.w-28,FONT_LARGE,TL_DATUM,OS12V_TEXT,OS12V_SURFACE2);
  hubUi13InfoRow(hr(OS12V_INSET,130,W-OS12V_INSET*2,54),"Release State","Candidate","Physical acceptance required",C10_ORANGE);
  hubUi13InfoRow(hr(OS12V_INSET,190,W-OS12V_INSET*2,54),"Update Method","Local Portal","Only exact validated artifacts",C10_ACCENT);
  hubV1125Action(hubUi13BackRect(),"Back",C10_ACCENT,true,false);hubV1125Action(hubUi13ActionRect(),"Local Portal",C10_ACCENT,true,false);
  hubMarkFrameDirty();g_dirty=false;
}
'''

MEDIA=r'''
static void drawOs12Media() {
  const workshop::media::Snapshot& m=workshopMediaSnapshot();
  const bool videoPlaying=m.runtime.session==workshop::media::SessionState::PlayingVideo||m.runtime.session==workshop::media::SessionState::Paused;
  tft.fillScreen(OS12V_BG);drawHeader("Media",workshop::media::sessionStateName(m.runtime.session),3);
  char volume[16];snprintf(volume,sizeof(volume),"%u%%",(unsigned)m.runtime.volumePercent);
  hubUi13StepperRow(hubUi13RowRect(0),"Speaker",volume,m.capabilities.speakerAvailable?(m.runtime.muted?"Muted · tap center to test":"Output ready · tap center to test"):"Speaker unavailable",C10_ACCENT);
  char mic[20];if(m.capabilities.microphoneAvailable)snprintf(mic,sizeof(mic),"%u%%",(unsigned)m.runtime.microphoneLevelPercent);else strlcpy(mic,"Unavailable",sizeof(mic));
  hubUi13InfoRow(hubUi13RowRect(1),"Microphone",mic,m.capabilities.microphoneAvailable?"Tap row to sample input":"Hardware not detected",m.capabilities.microphoneAvailable?C10_GREEN:C10_MUTED);
  hubUi13InfoRow(hubUi13RowRect(2),"Video",videoPlaying?"Active":(m.capabilities.videoDecoderAvailable?"Ready":"Unavailable"),m.capabilities.videoDecoderAvailable?"Built-in WS350 motion test":"Decoder unavailable",videoPlaying?C10_GREEN:(m.capabilities.videoDecoderAvailable?C10_ACCENT:C10_MUTED));
  hubV1125Action(hubUi13BackRect(),"Back",C10_ACCENT,true,false);hubV1125Action(hubUi13ActionRect(),"Recorder",C10_ACCENT,m.capabilities.microphoneAvailable,false);
  hubMarkFrameDirty();g_dirty=false;
}
'''

RECORDER=r'''
static void drawOs12Recorder() {
  const workshop::media::Snapshot& m=workshopMediaSnapshot();const bool recordReady=m.capabilities.microphoneAvailable&&m.capabilities.psramAvailable;
  const bool recording=m.runtime.session==workshop::media::SessionState::Recording;const bool playing=m.runtime.session==workshop::media::SessionState::PlayingRecording;
  tft.fillScreen(OS12V_BG);drawHeader("Recorder",workshop::media::sessionStateName(m.runtime.session),3);
  char level[20];snprintf(level,sizeof(level),"%u%%",(unsigned)m.runtime.microphoneLevelPercent);
  hubUi13InfoRow(hubUi13RowRect(0),"Microphone",m.capabilities.microphoneAvailable?level:"Unavailable",m.capabilities.microphoneAvailable?"Live input activity":"Microphone unavailable",m.capabilities.microphoneAvailable?C10_GREEN:C10_MUTED);
  hubUi13InfoRow(hubUi13RowRect(1),"Recording",recording?"Recording":(recordReady?"Ready":"Unavailable"),recording?"Tap to stop":"Tap to record · 5 sec maximum",recording?C10_ORANGE:(recordReady?C10_ACCENT:C10_MUTED));
  hubUi13InfoRow(hubUi13RowRect(2),"Playback",playing?"Playing":(m.runtime.recordingAvailable?"Ready":"No recording"),playing?"Tap to stop":(m.runtime.recordingAvailable?"Tap to play captured audio":"Record audio first"),playing?C10_GREEN:(m.runtime.recordingAvailable?C10_ACCENT:C10_MUTED));
  hubV1125Action(hubUi13BackRect(),"Back",C10_ACCENT,true,false);hubV1125Action(hubUi13ActionRect(),"Done",C10_ACCENT,true,false);
  hubMarkFrameDirty();g_dirty=false;
}
'''

VIDEO=r'''
static void drawOs12VideoViewer() {
  const workshop::media::Snapshot& m=workshopMediaSnapshot();
  if(!gOs12VideoViewerPrimed){tft.fillScreen(TFT_BLACK);uiDrawFit("Video Viewer",OS12V_INSET,9,tft.width()-OS12V_INSET*2,FONT_BODY,TL_DATUM,OS12V_TEXT,TFT_BLACK);uiDrawFit("Built-in motion diagnostic",OS12V_INSET,31,tft.width()-OS12V_INSET*2,FONT_SMALL,TL_DATUM,OS12V_MUTED,TFT_BLACK);gOs12VideoViewerPrimed=true;}
  const bool paused=m.runtime.session==workshop::media::SessionState::Paused;
  hubV1125Action(hubUi13BackRect(),"Stop",C10_RED,true,true);hubV1125Action(hubUi13ActionRect(),paused?"Resume":"Pause",C10_ACCENT,true,false);
  hubMarkFrameDirty();g_dirty=false;
}
'''


def remap_visual_tokens(text: str, signature: str) -> str:
    start=text.find(signature)
    if start<0: return text
    if text.find(signature,start+1)>=0: raise PatchError(f"function non-unique: {signature}")
    end=braced_end(text,start,signature)
    body=text[start:end]
    mapping=(
        ("C10_BG","OS12V_BG"),
        ("C10_SURFACE_3","OS12V_SURFACE2"),
        ("C10_SURFACE_2","OS12V_SURFACE2"),
        ("C10_SURFACE","OS12V_SURFACE"),
        ("C10_SEPARATOR","OS12V_LINE"),
        ("C10_TEXT","OS12V_TEXT"),
        ("C10_MUTED","OS12V_MUTED"),
        ("C10_ACCENT","OS12V_ACCENT"),
        ("C10_GREEN","OS12V_GREEN"),
        ("C10_ORANGE","OS12V_AMBER"),
        ("C10_RED","OS12V_RED"),
    )
    for old,new in mapping:
        body=body.replace(old,new)
    return text[:start]+body+text[end:]

def apply(repo: Path) -> None:
    path=repo/"src"/"smart_hub.cpp";text=load(path)

    # Install palette before render helpers.
    for line in [x.strip() for x in PALETTE.strip().splitlines() if x.strip()]:
        if text.count(line)>1: raise PatchError(f"duplicate visual token: {line}")
        if line in text: text=text.replace(line,"",1)
    anchor="namespace {\n"
    pos=text.find(anchor)
    if pos<0: raise PatchError("anonymous namespace anchor missing")
    pos+=len(anchor)
    text=text[:pos]+"\n"+PALETTE.strip()+"\n\n"+text[pos:]

    for sig,repl in (
        ("static void hubV1125Card(",CARD),
        ("static void drawHeader(",HEADER),
        ("static void uiBottomNav(",BOTTOM),
        ("static void hubV1125Action(",ACTION),
        ("static void hubOs12RowSurface(",ROW),
        ("static void hubOs12NavRow(",NAVROW),
        ("static void hubOs12EvidenceRow(",EVIDENCE),
        ("static void hubUi13ToggleRow(",TOGGLE),
        ("static void hubUi13StepperRow(",STEPPER),
        ("static void drawHome(bool full)",HOME),
        ("static void drawWorkshop(bool full)",WORKSHOP),
        ("static void drawMore(bool full)",MORE),
        ("static void drawSystem(bool full)",SYSTEM),
        ("static void drawUi13DateTime()",DATE_TIME),
        ("static void drawUi13SoftwareUpdate()",UPDATE),
        ("static void drawOs12Media()",MEDIA),
        ("static void drawOs12Recorder()",RECORDER),
        ("static void drawOs12VideoViewer()",VIDEO),
    ):
        text=replace_function(text,sig,repl)

    # Extend the palette to every active device surface without changing touch
    # geometry or control dispatch. These functions retain their existing
    # semantics and only consume the final visual tokens.
    for sig in (
        "static void drawPrinter(bool full)",
        "static void drawUi13Display()",
        "static void drawUi13AfterPrint()",
        "static void drawUi13Sound()",
        "static void drawUi13PrinterAlerts()",
        "static void drawUi13AlertSignals()",
        "static void drawUi13Network()",
        "static void drawUi13PrinterPower()",
        "static void drawUi13PowerOptions()",
        "static void drawUi13AutoOffConfirm()",
        "static void drawUi13Diagnostics()",
        "static void drawUi12PortalAccess()",
    ):
        text=remap_visual_tokens(text,sig)

    path.write_text(text,encoding="utf-8")
    print("Workshop OS 12 whole-device visual overhaul applied")

def main() -> int:
    ap=argparse.ArgumentParser();ap.add_argument("--repo",required=True);ap.add_argument("--apply",action="store_true");a=ap.parse_args()
    if not a.apply: raise SystemExit("refusing to modify source without --apply")
    try: apply(Path(a.repo).resolve())
    except PatchError as exc: raise SystemExit(f"FAIL: {exc}") from exc
    return 0

if __name__=="__main__":
    raise SystemExit(main())
