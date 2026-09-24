#!/usr/bin/env python3
"""Apply post-capture Workshop OS 12 UI hardening.

This final reconstruction layer addresses issues observed in the real 480x320
framebuffer capture without changing inventory authority, placement authority,
release promotion rules, or device control authority.

It runs after the whole-device visual overhaul so later presentation work cannot
re-introduce the overlap/truth-model defects found during screenshot review.
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


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise PatchError(f"{label}: expected one anchor, found {count}")
    return text.replace(old, new, 1)


EVIDENCE = r'''
static void hubOs12EvidenceRow(const HubRect& r,const char* title,const char* value,const char* detail,uint16_t valueColor=C10_MUTED) {
  hubOs12RowSurface(r);
  uint16_t vc=OS12V_MUTED;
  if(valueColor==C10_GREEN||valueColor==OS12V_GREEN)vc=OS12V_GREEN;
  else if(valueColor==C10_ORANGE||valueColor==OS12V_AMBER)vc=OS12V_AMBER;
  else if(valueColor==C10_RED||valueColor==OS12V_RED)vc=OS12V_RED;
  else if(valueColor==C10_ACCENT||valueColor==OS12V_ACCENT)vc=OS12V_ACCENT;
  else if(valueColor==C10_TEXT||valueColor==OS12V_TEXT)vc=OS12V_TEXT;

  const int16_t inset=OS12V_INSET;
  const int16_t dotReserve=(vc!=OS12V_MUTED)?28:8;
  const int16_t textW=r.w-inset*2-dotReserve;
  const bool compact=r.h<64;
  const FontID valueFont=compact?FONT_SMALL:FONT_BODY;
  const int16_t valueY=r.y+(compact?22:25);
  const int16_t detailBottom=r.y+r.h-(compact?5:7);
  uiDrawFit(title,r.x+inset,r.y+6,textW,FONT_SMALL,TL_DATUM,OS12V_MUTED,OS12V_SURFACE);
  uiDrawFit(value,r.x+inset,valueY,textW,valueFont,TL_DATUM,vc,OS12V_SURFACE);
  uiDrawFit(detail,r.x+inset,detailBottom,textW,FONT_SMALL,BL_DATUM,OS12V_MUTED,OS12V_SURFACE);

  if(vc!=OS12V_MUTED)tft.fillCircle(r.x+r.w-17,r.y+17,4,vc);
}
'''

INFO = r'''
static void hubUi13InfoRow(const HubRect& r,const char* label,const char* value,const char* detail,uint16_t accent=C10_ACCENT) {
  hubOs12EvidenceRow(r,label,value,detail,accent);
}
'''

STEPPER = r'''
static void hubUi13StepperRow(const HubRect& r,const char* label,const char* value,const char* detail,uint16_t accent=C10_ACCENT) {
  (void)accent;hubOs12RowSurface(r);
  const int16_t buttonW=44,buttonH=44,controlStart=r.x+r.w-204;
  uiDrawFit(label,r.x+OS12V_INSET,r.y+7,controlStart-r.x-OS12V_INSET*2,FONT_SMALL,TL_DATUM,OS12V_MUTED,OS12V_SURFACE);
  uiDrawFit(detail,r.x+OS12V_INSET,r.y+r.h-9,controlStart-r.x-OS12V_INSET*2,FONT_SMALL,BL_DATUM,OS12V_MUTED,OS12V_SURFACE);
  HubRect minus=hr(controlStart,r.y+(r.h-buttonH)/2,buttonW,buttonH);
  HubRect plus=hr(r.x+r.w-buttonW-OS12V_INSET,r.y+(r.h-buttonH)/2,buttonW,buttonH);
  for(HubRect b:{minus,plus}){tft.fillRoundRect(b.x,b.y,b.w,b.h,10,OS12V_SURFACE2);tft.drawRoundRect(b.x,b.y,b.w,b.h,10,OS12V_LINE);}
  uiDrawFit("-",minus.x+minus.w/2,minus.y+minus.h/2,minus.w-8,FONT_LARGE,MC_DATUM,OS12V_ACCENT,OS12V_SURFACE2);
  uiDrawFit("+",plus.x+plus.w/2,plus.y+plus.h/2,plus.w-8,FONT_LARGE,MC_DATUM,OS12V_ACCENT,OS12V_SURFACE2);
  const int16_t valueX=minus.x+minus.w+6;
  const int16_t valueW=plus.x-valueX-6;
  uiDrawFit(value,valueX,r.y+r.h/2,valueW,FONT_SMALL,MC_DATUM,OS12V_TEXT,OS12V_SURFACE);
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
  hubOs12EvidenceRow(inventory,"FILAMENT INVENTORY","Unknown","Add or sync evidence in Filament Inventory",C10_MUTED);
  hubMarkFrameDirty();g_dirty=false;
}
'''

WORKSHOP = r'''
static void drawWorkshop(bool full) {
  (void)full;const int16_t W=tft.width();
  tft.fillScreen(OS12V_BG);drawHeader("Workshop","INVENTORY",2);uiBottomNav(2,nullptr);
  const BambuState* s=isAnyPrinterConfigured()?&displayedPrinter().state:nullptr;
  const bool printerAlert=s&&uiHmsCount(*s)>0;
  HubRect readiness=hr(OS12V_INSET,48,W-OS12V_INSET*2,66);
  HubRect loaded=hr(OS12V_INSET,120,W-OS12V_INSET*2,60);
  HubRect attention=hr(OS12V_INSET,186,W-OS12V_INSET*2,64);
  hubOs12EvidenceRow(readiness,"PRINT READINESS","Undetermined","Add print requirements and inventory evidence",C10_MUTED);
  hubOs12EvidenceRow(loaded,"LOADED SPOOLS","Unknown","Confirm canonical placement in Filament Inventory",C10_MUTED);
  hubOs12EvidenceRow(attention,"ATTENTION",printerAlert?"Printer alert":"No inventory signal",printerAlert?"Review Printer diagnostics":"No authoritative attention evidence",printerAlert?C10_ORANGE:C10_MUTED);
  hubMarkFrameDirty();g_dirty=false;
}
'''

COMPACT_HELPERS = r'''
static const char* hubOs12CompactTimezoneLabel() {
  static char compact[20];
  const char* full=hubTimezoneLabel();
  if(!full||!full[0])return "Unknown";
  if(full[0]=='('){
    const char* close=strchr(full,')');
    if(close){
      const size_t n=(size_t)(close-full+1);
      if(n<sizeof(compact)){memcpy(compact,full,n);compact[n]=0;return compact;}
    }
  }
  strlcpy(compact,full,sizeof(compact));
  return compact;
}
'''

SYSTEM = r'''
static void drawSystem(bool full) {
  if(g_audioSettingsView){drawAudioSettings(full);return;}if(g_networkSettingsView){drawNetworkEssentials(full);return;}if(g_ui12SystemView==1){drawUi12PortalAccess();return;}if(g_ui12SystemView==2){drawUi13DateTime();return;}if(g_ui12SystemView==3){drawUi13SoftwareUpdate();return;}if(g_ui12SystemView==4){drawUi13Diagnostics();return;}
  (void)full;const bool touchOk=hubTouchHealthy(),recoveryOk=recoveryWebReady();const bool healthy=touchOk&&recoveryOk;
  const bool configured=workshopPlatformState().configuredPrinterCount>0;const uint8_t slot=rotState.displayIndex<MAX_PRINTERS?rotState.displayIndex:0;const bool printerOk=configured&&workshopPlatformPrinterOnline(slot);
  tft.fillScreen(OS12V_BG);drawHeader("System",healthy?"HEALTHY":"CHECK",3);
  hubOs12NavRow(hubUi13SystemCardRect(0),"Device Health",healthy?"Healthy":"Needs attention",healthy?C10_GREEN:C10_ORANGE);
  hubOs12NavRow(hubUi13SystemCardRect(1),"Printer & Power",!configured?"Not configured":(printerOk?"Connected":"Unavailable"),printerOk?C10_GREEN:(configured?C10_ORANGE:C10_MUTED));
  hubOs12NavRow(hubUi13SystemCardRect(2),"Date & Time",hubOs12CompactTimezoneLabel(),C10_MUTED);
  hubOs12NavRow(hubUi13SystemCardRect(3),"Software Update","Runtime · candidate · verification",C10_MUTED);
  hubV1125Action(hubUi13BackRect(),"Back",C10_ACCENT,true,false);hubV1125Action(hubUi13ActionRect(),"Local Portal",C10_ACCENT,workshopPlatformWifiOnline(),false);
  hubMarkFrameDirty();g_dirty=false;
}
'''

DATE_TIME = r'''
static void drawUi13DateTime() {
  tft.fillScreen(OS12V_BG);drawHeader("Date & Time","LOCAL",3);
  hubUi13StepperRow(hubUi13RowRect(0),"Time Zone",hubOs12CompactTimezoneLabel(),"Use - / + to change",C10_ACCENT);
  hubUi13ToggleRow(hubUi13RowRect(1),"24-Hour Clock",netSettings.use24h?"Showing 24-hour time":"Showing 12-hour time",netSettings.use24h,C10_ACCENT);
  hubUi13StepperRow(hubUi13RowRect(2),"Date Format",hubDateFormatLabel(netSettings.dateFormat),"Use - / + to change",C10_ACCENT);
  hubV1125Action(hubUi13BackRect(),"Back",C10_ACCENT,true,false);hubV1125Action(hubUi13ActionRect(),"Done",C10_ACCENT,true,false);
  hubMarkFrameDirty();g_dirty=false;
}
'''

UPDATE = r'''
static void drawUi13SoftwareUpdate() {
  const int16_t W=tft.width();tft.fillScreen(OS12V_BG);drawHeader("Software Update","CANDIDATE",3);
  HubRect hero=hr(OS12V_INSET,48,W-OS12V_INSET*2,76);hubV1125Card(hero,C10_ACCENT,true);
  char runtimeVer[48];snprintf(runtimeVer,sizeof(runtimeVer),"Workshop OS %s",WORKSHOP_OS_RELEASE_VERSION);
  uiDrawFit("RUNTIME BUILD",hero.x+14,hero.y+10,hero.w-28,FONT_SMALL,TL_DATUM,OS12V_MUTED,OS12V_SURFACE2);
  uiDrawFit(runtimeVer,hero.x+14,hero.y+31,hero.w-28,FONT_LARGE,TL_DATUM,OS12V_TEXT,OS12V_SURFACE2);
  hubUi13InfoRow(hr(OS12V_INSET,130,W-OS12V_INSET*2,54),"Release State","Candidate","Physical acceptance required",C10_ORANGE);
  char baseVer[40];snprintf(baseVer,sizeof(baseVer),"UI base %s",SMART_HOME_VERSION);
  hubUi13InfoRow(hr(OS12V_INSET,190,W-OS12V_INSET*2,54),"Reconstruction Base",baseVer,"Not an acceptance claim",C10_MUTED);
  hubV1125Action(hubUi13BackRect(),"Back",C10_ACCENT,true,false);hubV1125Action(hubUi13ActionRect(),"Local Portal",C10_ACCENT,true,false);
  hubMarkFrameDirty();g_dirty=false;
}
'''

NETWORK = r'''
static void drawUi13Network() {
  const bool wifi=workshopPlatformWifiOnline();String ip=wifi?WiFi.localIP().toString():String("Unknown");
  tft.fillScreen(OS12V_BG);drawHeader("Network",wifi?"Connected":"Offline",3);
  hubUi13InfoRow(hubUi13RowRect(0),"Wi-Fi",wifi?"Connected":"Unavailable",wifi?ip.c_str():"No active network connection",wifi?C10_GREEN:C10_ORANGE);
  hubUi13ToggleRow(hubUi13RowRect(1),"Local Hostname","Advertise the device on the LAN",netSettings.mdnsEnabled,C10_ACCENT);
  hubUi13ToggleRow(hubUi13RowRect(2),"Show IP at Startup","Show address after connection",netSettings.showIPAtStartup,C10_ACCENT);
  hubV1125Action(hubUi13BackRect(),"Back",C10_ACCENT,true,false);hubV1125Action(hubUi13ActionRect(),"Local Portal",C10_ACCENT,wifi,false);
  hubMarkFrameDirty();g_dirty=false;
}
'''

MEDIA = r'''
static void drawOs12Media() {
  const workshop::media::Snapshot& m=workshopMediaSnapshot();
  const bool videoPlaying=m.runtime.session==workshop::media::SessionState::PlayingVideo||m.runtime.session==workshop::media::SessionState::Paused;
  tft.fillScreen(OS12V_BG);drawHeader("Media",workshop::media::sessionStateName(m.runtime.session),3);
  char volume[16];snprintf(volume,sizeof(volume),"%u%%",(unsigned)m.runtime.volumePercent);
  hubUi13StepperRow(hubUi13RowRect(0),"Speaker",volume,m.capabilities.speakerAvailable?(m.runtime.muted?"Muted · tap value to test":"Tap value to test speaker"):"Speaker unavailable",C10_ACCENT);
  char mic[20];if(m.capabilities.microphoneAvailable)snprintf(mic,sizeof(mic),"%u%%",(unsigned)m.runtime.microphoneLevelPercent);else strlcpy(mic,"Unavailable",sizeof(mic));
  hubUi13InfoRow(hubUi13RowRect(1),"Microphone",mic,m.capabilities.microphoneAvailable?"Tap row to sample input":"Hardware not detected",m.capabilities.microphoneAvailable?C10_GREEN:C10_MUTED);
  hubUi13InfoRow(hubUi13RowRect(2),"Video",videoPlaying?"Active":(m.capabilities.videoDecoderAvailable?"Ready":"Unavailable"),m.capabilities.videoDecoderAvailable?"Tap row to open motion test":"Decoder unavailable",videoPlaying?C10_GREEN:(m.capabilities.videoDecoderAvailable?C10_ACCENT:C10_MUTED));
  hubV1125Action(hubUi13BackRect(),"Back",C10_ACCENT,true,false);hubV1125Action(hubUi13ActionRect(),"Recorder",C10_ACCENT,m.capabilities.microphoneAvailable,false);
  hubMarkFrameDirty();g_dirty=false;
}
'''

RECORDER = r'''
static void drawOs12Recorder() {
  const workshop::media::Snapshot& m=workshopMediaSnapshot();const bool recordReady=m.capabilities.microphoneAvailable&&m.capabilities.psramAvailable;
  const bool recording=m.runtime.session==workshop::media::SessionState::Recording;const bool playing=m.runtime.session==workshop::media::SessionState::PlayingRecording;
  tft.fillScreen(OS12V_BG);drawHeader("Recorder",workshop::media::sessionStateName(m.runtime.session),3);
  char level[20];snprintf(level,sizeof(level),"%u%%",(unsigned)m.runtime.microphoneLevelPercent);
  hubUi13InfoRow(hubUi13RowRect(0),"Microphone",m.capabilities.microphoneAvailable?level:"Unavailable",m.capabilities.microphoneAvailable?"Tap to sample live input":"Microphone unavailable",m.capabilities.microphoneAvailable?C10_GREEN:C10_MUTED);
  hubUi13InfoRow(hubUi13RowRect(1),"Recording",recording?"Recording":(recordReady?"Ready":"Unavailable"),recording?"Tap to stop":"Tap to record · 5 sec maximum",recording?C10_ORANGE:(recordReady?C10_ACCENT:C10_MUTED));
  hubUi13InfoRow(hubUi13RowRect(2),"Playback",playing?"Playing":(m.runtime.recordingAvailable?"Ready":"No recording"),playing?"Tap to stop":(m.runtime.recordingAvailable?"Tap to play captured audio":"Record audio first"),playing?C10_GREEN:(m.runtime.recordingAvailable?C10_ACCENT:C10_MUTED));
  hubV1125Action(hubUi13BackRect(),"Back",C10_ACCENT,true,false);hubV1125Action(hubUi13ActionRect(),"Done",C10_ACCENT,true,false);
  hubMarkFrameDirty();g_dirty=false;
}
'''

VIDEO = r'''
static void drawOs12VideoViewer() {
  const workshop::media::Snapshot& m=workshopMediaSnapshot();
  const bool paused=m.runtime.session==workshop::media::SessionState::Paused;
  const bool videoActive=m.runtime.session==workshop::media::SessionState::PlayingVideo||paused;

  if(!videoActive){
    gOs12VideoViewerPrimed=false;
    tft.fillScreen(TFT_BLACK);
    uiDrawFit("Video Viewer",OS12V_INSET,14,tft.width()-OS12V_INSET*2,FONT_BODY,TL_DATUM,OS12V_TEXT,TFT_BLACK);
    uiDrawFit("No active video session",OS12V_INSET,48,tft.width()-OS12V_INSET*2,FONT_BODY,TL_DATUM,OS12V_MUTED,TFT_BLACK);
    uiDrawFit("Start the built-in motion test from Media.",OS12V_INSET,77,tft.width()-OS12V_INSET*2,FONT_SMALL,TL_DATUM,OS12V_MUTED,TFT_BLACK);
    uiDrawFit("This surface never reuses Recorder content.",OS12V_INSET,98,tft.width()-OS12V_INSET*2,FONT_SMALL,TL_DATUM,OS12V_MUTED,TFT_BLACK);
    hubV1125Action(hubUi13BackRect(),"Stop & Back",C10_RED,true,true);
    hubV1125Action(hubUi13ActionRect(),"Pause",C10_ACCENT,false,false);
    hubMarkFrameDirty();g_dirty=false;return;
  }

  if(!gOs12VideoViewerPrimed){
    tft.fillScreen(TFT_BLACK);
    uiDrawFit("Video Viewer",OS12V_INSET,9,tft.width()-OS12V_INSET*2,FONT_BODY,TL_DATUM,OS12V_TEXT,TFT_BLACK);
    uiDrawFit("Built-in motion diagnostic",OS12V_INSET,31,tft.width()-OS12V_INSET*2,FONT_SMALL,TL_DATUM,OS12V_MUTED,TFT_BLACK);
    uiDrawFit("Stop & Back returns to Media",OS12V_INSET,50,tft.width()-OS12V_INSET*2,FONT_SMALL,TL_DATUM,OS12V_MUTED,TFT_BLACK);
    gOs12VideoViewerPrimed=true;
  }
  hubV1125Action(hubUi13BackRect(),"Stop & Back",C10_RED,true,true);
  hubV1125Action(hubUi13ActionRect(),paused?"Resume":"Pause",C10_ACCENT,true,false);
  hubMarkFrameDirty();g_dirty=false;
}
'''


def patch_recorder_touch(text: str) -> str:
    row0_old = '''if(hubUi13RowRect(0).contains(x,y)){
          if(media.snapshot().runtime.session==workshop::media::SessionState::Recording)media.stopRecording(millis());
          else if(media.snapshot().runtime.session==workshop::media::SessionState::Idle&&media.snapshot().capabilities.microphoneAvailable&&media.snapshot().capabilities.psramAvailable)media.startRecording(5000U,millis());
          g_dirty=true;return true;
        }'''
    row0_new = '''if(hubUi13RowRect(0).contains(x,y)){
          if(media.snapshot().runtime.session==workshop::media::SessionState::Idle&&media.snapshot().capabilities.microphoneAvailable)media.sampleMicrophone(millis());
          g_dirty=true;return true;
        }'''
    row1_old = '''if(hubUi13RowRect(1).contains(x,y)){
          if(media.snapshot().runtime.session==workshop::media::SessionState::PlayingRecording)media.stop(millis());
          else if(media.snapshot().runtime.session==workshop::media::SessionState::Idle&&media.snapshot().runtime.recordingAvailable)media.playRecording(millis());
          g_dirty=true;return true;
        }'''
    row1_new = '''if(hubUi13RowRect(1).contains(x,y)){
          if(media.snapshot().runtime.session==workshop::media::SessionState::Recording)media.stopRecording(millis());
          else if(media.snapshot().runtime.session==workshop::media::SessionState::Idle&&media.snapshot().capabilities.microphoneAvailable&&media.snapshot().capabilities.psramAvailable)media.startRecording(5000U,millis());
          g_dirty=true;return true;
        }'''
    row2_old = 'if(hubUi13RowRect(2).contains(x,y)){return true;}'
    row2_new = '''if(hubUi13RowRect(2).contains(x,y)){
          if(media.snapshot().runtime.session==workshop::media::SessionState::PlayingRecording)media.stop(millis());
          else if(media.snapshot().runtime.session==workshop::media::SessionState::Idle&&media.snapshot().runtime.recordingAvailable)media.playRecording(millis());
          g_dirty=true;return true;
        }'''
    text=replace_once(text,row0_old,row0_new,"Recorder microphone touch")
    text=replace_once(text,row1_old,row1_new,"Recorder recording touch")
    text=replace_once(text,row2_old,row2_new,"Recorder playback touch")
    return text


def apply(repo: Path) -> None:
    path=repo/"src"/"smart_hub.cpp"
    text=load(path)

    text=replace_function(text,"static void hubOs12EvidenceRow(",EVIDENCE)
    text=replace_function(text,"static void hubUi13InfoRow(",INFO)
    text=replace_function(text,"static void hubUi13StepperRow(",STEPPER)
    text=replace_function(text,"static void drawHome(bool full)",HOME)
    text=replace_function(text,"static void drawWorkshop(bool full)",WORKSHOP)

    if "static const char* hubOs12CompactTimezoneLabel()" not in text:
        # Date & Time is emitted before System in the reconstructed source, so
        # the helper must be declared before the first consumer.
        anchor="static void drawUi13DateTime()"
        if text.count(anchor)!=1:
            raise PatchError("Date & Time helper insertion anchor missing/non-unique")
        text=text.replace(anchor,COMPACT_HELPERS.strip()+"\n\n"+anchor,1)

    text=replace_function(text,"static void drawSystem(bool full)",SYSTEM)
    text=replace_function(text,"static void drawUi13DateTime()",DATE_TIME)
    text=replace_function(text,"static void drawUi13SoftwareUpdate()",UPDATE)
    text=replace_function(text,"static void drawUi13Network()",NETWORK)
    text=replace_function(text,"static void drawOs12Media()",MEDIA)
    text=replace_function(text,"static void drawOs12Recorder()",RECORDER)
    text=replace_function(text,"static void drawOs12VideoViewer()",VIDEO)
    text=patch_recorder_touch(text)

    path.write_text(text,encoding="utf-8")
    print("Workshop OS 12 post-capture UI hardening applied")


def main() -> int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--repo",required=True)
    ap.add_argument("--apply",action="store_true")
    args=ap.parse_args()
    if not args.apply:
        raise SystemExit("refusing to modify source without --apply")
    try:
        apply(Path(args.repo).resolve())
    except PatchError as exc:
        raise SystemExit(f"FAIL: {exc}") from exc
    return 0


if __name__=="__main__":
    raise SystemExit(main())
