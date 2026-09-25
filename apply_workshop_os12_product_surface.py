#!/usr/bin/env python3
"""Apply Workshop OS 12 product-surface layouts after the shared UI finish.

This pass changes presentation only. It preserves normalized printer status reads,
existing command dispatch/touch handlers, read-only AMS telemetry, media ownership,
and Filament Inventory authority boundaries.
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


def load(path: Path)->str:
    if not path.is_file(): raise PatchError(f"missing {path}")
    return path.read_text(encoding="utf-8")

def braced_end(text:str,start:int,label:str)->int:
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

PRINTER=r'''
static void drawPrinter(bool full) {
  (void)full;
  const int16_t W=tft.width();
  tft.fillScreen(C10_BG);
  drawHeader("Printer",nullptr,1);
  uiBottomNav(1,nullptr);
  hubV1125ModeTabs();

  if(workshopPlatformState().configuredPrinterCount==0){
    HubRect r=hr(OS12_MARGIN_X,104,W-OS12_MARGIN_X*2,138);
    hubV1125Card(r,C10_ORANGE,true);
    uiDrawFit("No printer configured",r.x+16,r.y+18,r.w-32,FONT_LARGE,TL_DATUM,C10_TEXT,C10_SURFACE_2);
    uiDrawFit("Configure printer access from More > System.",r.x+16,r.y+72,r.w-32,FONT_BODY,TL_DATUM,C10_MUTED,C10_SURFACE_2);
    hubMarkFrameDirty();g_dirty=false;return;
  }

  const PrinterSlot& p=displayedPrinter();
  const BambuState& s=p.state;
  const uint8_t os12Slot=rotState.displayIndex<MAX_PRINTERS?rotState.displayIndex:0;
  const bool paused=workshopPlatformPrinterPaused(os12Slot);
  const bool printing=workshopPlatformPrinterPrinting(os12Slot);
  const bool active=workshopPlatformPrinterActive(os12Slot);
  const bool online=workshopPlatformPrinterOnline(os12Slot);
  const uint16_t sc=!online?C10_ORANGE:(paused?C10_ORANGE:(printing?C10_ACCENT:C10_GREEN));
  const char* state=!online?"Offline":(paused?"Paused":(printing?"Printing":"Ready"));

  if(g_printerMode==HUB_PRINTER_STATUS){
    HubRect hero=hr(OS12_MARGIN_X,100,292,150);
    HubRect telem=hr(312,100,W-OS12_MARGIN_X-312,150);
    hubV1125Card(hero,sc,true);
    uiDrawFit(p.config.name[0]?p.config.name:"Printer",hero.x+16,hero.y+14,hero.w-32,FONT_SMALL,TL_DATUM,C10_MUTED,C10_SURFACE_2);
    uiDrawFit(state,hero.x+16,hero.y+38,hero.w-32,FONT_LARGE,TL_DATUM,sc,C10_SURFACE_2);
    if(active){
      char rem[20],meta[42];formatDuration(s.remainingMinutes,rem,sizeof(rem));
      snprintf(meta,sizeof(meta),"%u%%  ·  %s left",(unsigned)s.progress,rem);
      uiDrawFit(jobDisplayName(s),hero.x+16,hero.y+78,hero.w-32,FONT_BODY,TL_DATUM,C10_TEXT,C10_SURFACE_2);
      uiProgressBar(hero.x+16,hero.y+108,hero.w-32,s.progress,C10_ACCENT);
      uiDrawFit(meta,hero.x+16,hero.y+136,hero.w-32,FONT_SMALL,BL_DATUM,C10_MUTED,C10_SURFACE_2);
    }else{
      uiDrawFit(online?"Ready for the next print":"Check printer connection",hero.x+16,hero.y+90,hero.w-32,FONT_BODY,TL_DATUM,online?C10_TEXT:C10_ORANGE,C10_SURFACE_2);
    }
    hubV1125TelemetryColumn(telem,s);
  } else if(g_printerMode==HUB_PRINTER_AMS){
    const int16_t gap=8;
    const int16_t cw=(W-OS12_MARGIN_X*2-gap*3)/4;
    uint8_t n=s.ams.present?s.ams.unitCount*4:0;if(n>4)n=4;
    for(uint8_t i=0;i<4;i++){
      HubRect r=hr(OS12_MARGIN_X+i*(cw+gap),104,cw,122);
      hubV1125AmsSlot(r,(i<n)?&s.ams.trays[i]:nullptr,s.ams.present&&s.ams.activeTray==i,i);
    }
    uiDrawFit(s.ams.present?"Printer-reported AMS telemetry":"No AMS telemetry available",OS12_MARGIN_X,244,W-OS12_MARGIN_X*2,FONT_SMALL,BL_DATUM,s.ams.present?C10_MUTED:C10_ORANGE,C10_BG);
    uiDrawFit("Inventory identity and placement remain authoritative in Filament Inventory.",OS12_MARGIN_X,259,W-OS12_MARGIN_X*2,FONT_SMALL,BL_DATUM,C10_MUTED,C10_BG);
  } else {
    const char* light=s.lightState==1?"Light Off":"Light On";
    const char* pause=paused?"Resume":"Pause";
    const uint8_t plug=tasmotaControlPlugForSlot(rotState.displayIndex);
    const bool powerMapped=plug!=0xFF;
    const char* labels[4]={
      printerFeedbackLabel(0,light),
      printerFeedbackLabel(1,pause),
      powerMapped?"Printer Power":"Power Unavailable",
      printerFeedbackLabel(3,active?"Hold to Stop":"Stop")
    };
    for(uint8_t i=0;i<4;i++){
      HubRect r=hubPrinterActionRect(i);
      const bool enabled=i==0?online:i==1?(online&&active):i==2?powerMapped:(online&&active);
      const uint16_t c=i==0?C10_ACCENT:i==1?(paused?C10_GREEN:C10_ACCENT):i==2?C10_ORANGE:C10_RED;
      hubV1125Action(r,labels[i],c,enabled,i==3);
    }
    uiDrawFit(active?"Commands remain pending until fresh printer telemetry confirms state.":"Controls become available when printer state permits.",OS12_MARGIN_X,258,W-OS12_MARGIN_X*2,FONT_SMALL,BL_DATUM,C10_MUTED,C10_BG);
  }
  hubMarkFrameDirty();g_dirty=false;
}
'''

MEDIA=r'''
static void drawOs12Media() {
  const workshop::media::Snapshot& m=workshopMediaSnapshot();
  const bool videoPlaying=m.runtime.session==workshop::media::SessionState::PlayingVideo||m.runtime.session==workshop::media::SessionState::Paused;
  tft.fillScreen(C10_BG);drawHeader("Media",workshop::media::sessionStateName(m.runtime.session),3);
  char volume[16];snprintf(volume,sizeof(volume),"%u%%",(unsigned)m.runtime.volumePercent);
  hubUi13StepperRow(hubUi13RowRect(0),"Speaker",volume,m.capabilities.speakerAvailable?(m.runtime.muted?"Muted · tap center to test":"Output ready · tap center to test"):"Speaker unavailable",m.capabilities.speakerAvailable?C10_ACCENT:C10_MUTED);
  char mic[20];if(m.capabilities.microphoneAvailable)snprintf(mic,sizeof(mic),"%u%%",(unsigned)m.runtime.microphoneLevelPercent);else strlcpy(mic,"Unavailable",sizeof(mic));
  hubUi13InfoRow(hubUi13RowRect(1),"Microphone",mic,m.capabilities.microphoneAvailable?"Tap row to sample input":"Hardware not detected",m.capabilities.microphoneAvailable?C10_GREEN:C10_MUTED);
  hubUi13InfoRow(hubUi13RowRect(2),"Video",videoPlaying?"Active":(m.capabilities.videoDecoderAvailable?"Ready":"Unavailable"),m.capabilities.videoDecoderAvailable?"Built-in WS350 motion test":"Decoder unavailable",videoPlaying?C10_GREEN:(m.capabilities.videoDecoderAvailable?C10_ACCENT:C10_MUTED));
  hubV1125Action(hubUi13BackRect(),"Back",C10_ACCENT,true,false);
  hubV1125Action(hubUi13ActionRect(),"Recorder",C10_ACCENT,m.capabilities.microphoneAvailable,false);
  hubMarkFrameDirty();g_dirty=false;
}
'''

RECORDER=r'''
static void drawOs12Recorder() {
  const workshop::media::Snapshot& m=workshopMediaSnapshot();
  const bool recordReady=m.capabilities.microphoneAvailable&&m.capabilities.psramAvailable;
  const bool recording=m.runtime.session==workshop::media::SessionState::Recording;
  const bool playing=m.runtime.session==workshop::media::SessionState::PlayingRecording;
  tft.fillScreen(C10_BG);drawHeader("Recorder",workshop::media::sessionStateName(m.runtime.session),3);

  char level[20];snprintf(level,sizeof(level),"%u%%",(unsigned)m.runtime.microphoneLevelPercent);
  hubUi13InfoRow(hubUi13RowRect(0),"Microphone",m.capabilities.microphoneAvailable?level:"Unavailable",m.capabilities.microphoneAvailable?"Live input activity":"Microphone unavailable",m.capabilities.microphoneAvailable?C10_GREEN:C10_MUTED);

  const char* recordValue=recording?"Recording":(recordReady?"Ready":"Unavailable");
  const char* recordDetail=recording?"Tap to stop":"Tap to record · 5 sec maximum";
  hubUi13InfoRow(hubUi13RowRect(1),"Recording",recordValue,recordReady?recordDetail:"Microphone + PSRAM required",recording?C10_ORANGE:(recordReady?C10_ACCENT:C10_MUTED));

  const char* playValue=playing?"Playing":(m.runtime.recordingAvailable?"Ready":"No recording");
  hubUi13InfoRow(hubUi13RowRect(2),"Playback",playValue,playing?"Tap to stop":(m.runtime.recordingAvailable?"Tap to play captured audio":"Record audio first"),playing?C10_GREEN:(m.runtime.recordingAvailable?C10_ACCENT:C10_MUTED));

  hubV1125Action(hubUi13BackRect(),"Back",C10_ACCENT,true,false);
  hubV1125Action(hubUi13ActionRect(),"Done",C10_ACCENT,true,false);
  hubMarkFrameDirty();g_dirty=false;
}
'''

VIDEO=r'''
static void drawOs12VideoViewer() {
  const workshop::media::Snapshot& m=workshopMediaSnapshot();
  if(!gOs12VideoViewerPrimed){
    tft.fillScreen(TFT_BLACK);
    uiDrawFit("Video Viewer",OS12_MARGIN_X,10,tft.width()-OS12_MARGIN_X*2,FONT_BODY,TL_DATUM,C10_TEXT,TFT_BLACK);
    uiDrawFit("Built-in WS350 motion test",OS12_MARGIN_X,34,tft.width()-OS12_MARGIN_X*2,FONT_SMALL,TL_DATUM,C10_MUTED,TFT_BLACK);
    gOs12VideoViewerPrimed=true;
  }
  const bool paused=m.runtime.session==workshop::media::SessionState::Paused;
  hubV1125Action(hubUi13BackRect(),"Stop",C10_RED,true,true);
  hubV1125Action(hubUi13ActionRect(),paused?"Resume":"Pause",C10_ACCENT,true,false);
  hubMarkFrameDirty();g_dirty=false;
}
'''

def apply(repo:Path)->None:
    p=repo/"src"/"smart_hub.cpp";text=load(p)
    for sig,repl in (
        ("static void drawPrinter(bool full)",PRINTER),
        ("static void drawOs12Media()",MEDIA),
        ("static void drawOs12Recorder()",RECORDER),
        ("static void drawOs12VideoViewer()",VIDEO),
    ): text=replace_function(text,sig,repl)
    p.write_text(text,encoding="utf-8")
    print("Workshop OS 12 product-surface layouts installed")

def main()->int:
    ap=argparse.ArgumentParser();ap.add_argument("--repo",required=True);ap.add_argument("--apply",action="store_true");a=ap.parse_args()
    if not a.apply: raise SystemExit("refusing to modify source without --apply")
    try: apply(Path(a.repo).resolve())
    except PatchError as exc: raise SystemExit(f"FAIL: {exc}") from exc
    return 0

if __name__=="__main__": raise SystemExit(main())
