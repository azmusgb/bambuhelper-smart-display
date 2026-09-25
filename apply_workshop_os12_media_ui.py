#!/usr/bin/env python3
"""Add a capability-safe Media experience to the reconstructed UI13 settings flow."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys as _sys
from pathlib import Path as _Path
_here = _Path(__file__).resolve().parent
if str(_here) not in _sys.path:
    _sys.path.insert(0, str(_here))
from scripts.smart_home_patch_utils import PatchError, fail, replace_once, replace_braced_block




INCLUDE = '#include "workshop_media_runtime.h"\n'

MEDIA_UI = r'''
static void drawOs12Media() {
  const workshop::media::Snapshot& m=workshopMediaSnapshot();
  const bool videoPlaying=m.runtime.session==workshop::media::SessionState::PlayingVideo||m.runtime.session==workshop::media::SessionState::Paused;
  tft.fillScreen(C10_BG);drawHeader("Media",workshop::media::sessionStateName(m.runtime.session),3);uiBottomNav(3,nullptr);
  char volume[16];snprintf(volume,sizeof(volume),"%u%%",(unsigned)m.runtime.volumePercent);
  hubUi13StepperRow(hubUi13RowRect(0),"Speaker",volume,m.capabilities.speakerAvailable?(m.runtime.muted?"Muted • tap center to test":"Output ready • tap center to test"):"Speaker unavailable",m.capabilities.speakerAvailable?C10_ACCENT:C10_MUTED);
  char mic[20];if(m.capabilities.microphoneAvailable)snprintf(mic,sizeof(mic),"%u%%",(unsigned)m.runtime.microphoneLevelPercent);else strlcpy(mic,"Unavailable",sizeof(mic));
  hubUi13InfoRow(hubUi13RowRect(1),"Microphone",mic,m.capabilities.microphoneAvailable?"Tap to sample":"Hardware not detected",m.capabilities.microphoneAvailable?C10_ACCENT:C10_MUTED);
  hubUi13InfoRow(hubUi13RowRect(2),"Video",videoPlaying?"Playing":(m.capabilities.videoDecoderAvailable?"Play demo":"Unavailable"),m.capabilities.videoDecoderAvailable?"WS350 local motion test":"Decoder unavailable",videoPlaying?C10_GREEN:(m.capabilities.videoDecoderAvailable?C10_ACCENT:C10_MUTED));
  hubV1125Action(hubUi13BackRect(),"Back",C10_ACCENT,true,false);hubV1125Action(hubUi13ActionRect(),"Recorder",C10_ACCENT,true,false);hubMarkFrameDirty();g_dirty=false;
}

static bool gOs12VideoViewerPrimed=false;

static void drawOs12VideoViewer() {
  const workshop::media::Snapshot& m=workshopMediaSnapshot();
  if(!gOs12VideoViewerPrimed){
    tft.fillScreen(TFT_BLACK);
    uiDrawFit("Video Viewer",12,18,tft.width()-24,FONT_BODY,TL_DATUM,C10_TEXT,TFT_BLACK);
    uiDrawFit("Workshop OS media playback",12,44,tft.width()-24,FONT_SMALL,TL_DATUM,C10_MUTED,TFT_BLACK);
    gOs12VideoViewerPrimed=true;
  }
  const bool paused=m.runtime.session==workshop::media::SessionState::Paused;
  hubV1125Action(hubUi13BackRect(),"Stop",C10_RED,true,false);
  hubV1125Action(hubUi13ActionRect(),paused?"Resume":"Pause",C10_ACCENT,true,false);
  hubMarkFrameDirty();g_dirty=false;
}

static void drawOs12Recorder() {
  const workshop::media::Snapshot& m=workshopMediaSnapshot();
  const bool recordReady=m.capabilities.microphoneAvailable&&m.capabilities.psramAvailable;
  const bool recording=m.runtime.session==workshop::media::SessionState::Recording;
  const bool playing=m.runtime.session==workshop::media::SessionState::PlayingRecording;
  tft.fillScreen(C10_BG);drawHeader("Recorder",workshop::media::sessionStateName(m.runtime.session),3);uiBottomNav(3,nullptr);
  const char* recordValue=recording?"Recording":(recordReady?"Tap to record":"Unavailable");
  const char* recordDetail=recordReady?"5 sec max • bounded PSRAM":"Microphone + PSRAM required";
  hubUi13InfoRow(hubUi13RowRect(0),"Recording",recordValue,recording?"Tap to stop":recordDetail,recording?C10_ORANGE:(recordReady?C10_ACCENT:C10_MUTED));
  const char* playValue=playing?"Playing":(m.runtime.recordingAvailable?"Tap to play":"No recording");
  hubUi13InfoRow(hubUi13RowRect(1),"Playback",playValue,playing?"Tap to stop":"Uses the captured local buffer",playing?C10_GREEN:(m.runtime.recordingAvailable?C10_ACCENT:C10_MUTED));
  const bool printerConfigured=isAnyPrinterConfigured();
  const PrinterSlot* p=printerConfigured?&displayedPrinter():nullptr;
  char cameraValue[32];char cameraDetail[80];
  if(p&&p->state.ipcamSeen){
    snprintf(cameraValue,sizeof(cameraValue),"Live %s • RTSP %s",p->state.liveviewPreview?"on":"off",p->state.rtspEnabled?"on":"off");
    snprintf(cameraDetail,sizeof(cameraDetail),"%s • BRTC %s • TUTK %s",p->state.cameraResolution[0]?p->state.cameraResolution:"resolution ?",p->state.brtcServiceEnabled?"on":"off",p->state.tutkServiceEnabled?"on":"off");
  }else{
    strlcpy(cameraValue,printerConfigured?"Unknown":"Not configured",sizeof(cameraValue));
    strlcpy(cameraDetail,printerConfigured?"No camera capability report observed":"Configure a printer to observe camera capability",sizeof(cameraDetail));
  }
  hubUi13InfoRow(hubUi13RowRect(2),"Printer Camera",cameraValue,cameraDetail,p&&p->state.rtspEnabled?C10_GREEN:(p&&p->state.ipcamSeen?C10_ORANGE:C10_MUTED));
  hubV1125Action(hubUi13BackRect(),"Back",C10_ACCENT,true,false);hubV1125Action(hubUi13ActionRect(),"Done",C10_ACCENT,true,false);hubMarkFrameDirty();g_dirty=false;
}
'''

MEDIA_TOUCH = r'''
      if(g_ui12SettingsView==10){
        workshop::media::MediaService& media=workshopMediaService();
        if(hubUi13MinusRect(0).contains(x,y)||hubUi13PlusRect(0).contains(x,y)){
          int v=(int)media.snapshot().runtime.volumePercent+(hubUi13MinusRect(0).contains(x,y)?-10:10);if(v<0)v=0;if(v>100)v=100;
          if(media.setVolume((uint8_t)v)){buzzerSettings.volume=(uint8_t)v;saveBuzzerSettings();buzzerPlay(BUZZ_CLICK);}g_dirty=true;return true;
        }
        HubRect speakerCenter=hubUi13RowRect(0);speakerCenter.x+=60;speakerCenter.w-=120;
        if(speakerCenter.contains(x,y)){if(media.snapshot().runtime.session==workshop::media::SessionState::Idle)media.testSpeaker(millis());g_dirty=true;return true;}
        if(hubUi13RowRect(1).contains(x,y)){if(media.snapshot().runtime.session==workshop::media::SessionState::Idle)media.sampleMicrophone(millis());g_dirty=true;return true;}
        if(hubUi13RowRect(2).contains(x,y)){
          if(media.snapshot().runtime.session==workshop::media::SessionState::Idle&&media.snapshot().capabilities.videoDecoderAvailable){
            gOs12VideoViewerPrimed=false;g_ui12SettingsView=12;
            if(!media.playMjpeg("demo-video",millis()))g_ui12SettingsView=10;
          }
          g_dirty=true;return true;
        }
        if(hubUi13BackRect().contains(x,y)){g_ui12SettingsView=2;buzzerPlay(BUZZ_CLICK);g_dirty=true;return true;}
        if(hubUi13ActionRect().contains(x,y)){g_ui12SettingsView=11;buzzerPlay(BUZZ_CLICK);g_dirty=true;return true;}
        return true;
      }
      if(g_ui12SettingsView==12){
        workshop::media::MediaService& media=workshopMediaService();
        const workshop::media::SessionState state=media.snapshot().runtime.session;
        if(hubUi13BackRect().contains(x,y)){
          if(state!=workshop::media::SessionState::Idle)media.stop(millis());
          gOs12VideoViewerPrimed=false;
          g_ui12SettingsView=10;
          buzzerPlay(BUZZ_CLICK);g_dirty=true;return true;
        }
        if(hubUi13ActionRect().contains(x,y)){
          if(state==workshop::media::SessionState::PlayingVideo)media.pauseVideo(true,millis());
          else if(state==workshop::media::SessionState::Paused)media.pauseVideo(false,millis());
          g_dirty=true;return true;
        }
        return true;
      }
      if(g_ui12SettingsView==11){
        workshop::media::MediaService& media=workshopMediaService();
        if(media.snapshot().runtime.session==workshop::media::SessionState::PlayingVideo||media.snapshot().runtime.session==workshop::media::SessionState::Paused){
          media.stop(millis());g_dirty=true;return true;
        }
        if(hubUi13RowRect(0).contains(x,y)){
          if(media.snapshot().runtime.session==workshop::media::SessionState::Recording)media.stopRecording(millis());
          else if(media.snapshot().runtime.session==workshop::media::SessionState::Idle&&media.snapshot().capabilities.microphoneAvailable&&media.snapshot().capabilities.psramAvailable)media.startRecording(5000U,millis());
          g_dirty=true;return true;
        }
        if(hubUi13RowRect(1).contains(x,y)){
          if(media.snapshot().runtime.session==workshop::media::SessionState::PlayingRecording)media.stop(millis());
          else if(media.snapshot().runtime.session==workshop::media::SessionState::Idle&&media.snapshot().runtime.recordingAvailable)media.playRecording(millis());
          g_dirty=true;return true;
        }
        if(hubUi13RowRect(2).contains(x,y)){return true;}
        if(hubUi13BackRect().contains(x,y)){
          if(media.snapshot().runtime.session==workshop::media::SessionState::Recording)media.stopRecording(millis());
          else if(media.snapshot().runtime.session!=workshop::media::SessionState::Idle)media.stop(millis());
          g_ui12SettingsView=10;buzzerPlay(BUZZ_CLICK);g_dirty=true;return true;
        }
        if(hubUi13ActionRect().contains(x,y)){
          if(media.snapshot().runtime.session==workshop::media::SessionState::Recording)media.stopRecording(millis());
          else if(media.snapshot().runtime.session!=workshop::media::SessionState::Idle)media.stop(millis());
          g_ui12SettingsView=10;buzzerPlay(BUZZ_CLICK);g_dirty=true;return true;
        }
        return true;
      }
'''


def insert_include(text: str) -> str:
    if INCLUDE.strip() in text:
        return text
    pos = text.find("#include ")
    if pos < 0:
        raise PatchError("smart_hub.cpp has no include anchor")
    return text[:pos] + INCLUDE + text[pos:]


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


def replace_in_function(text: str, signature: str, old: str, new: str, label: str) -> str:
    start = text.find(signature)
    if start < 0 or text.find(signature, start + 1) >= 0:
        raise PatchError(f"{label}: function signature missing/non-unique")
    end = braced_end(text, start, label)
    block = text[start:end]
    count = block.count(old)
    if count != 1:
        raise PatchError(f"{label}: expected one scoped anchor, found {count}")
    block = block.replace(old, new, 1)
    return text[:start] + block + text[end:]


def apply(repo: Path) -> None:
    hub_path = repo / "src/smart_hub.cpp"
    runtime_h = repo / "include/workshop_media_runtime.h"
    if not hub_path.is_file() or not runtime_h.is_file():
        raise PatchError("media UI requires reconstructed OS12 media runtime")

    text = insert_include(hub_path.read_text(encoding="utf-8"))
    if "static void drawOs12Media()" not in text:
        text = replace_once(text, "static void drawUi13PrinterAlerts() {", MEDIA_UI + "\nstatic void drawUi13PrinterAlerts() {", "media renderer insertion")

    text = replace_in_function(
        text,
        "static void drawUi13Sound()",
        'hubV1125Action(hubUi13ActionRect(),"Printer Alerts",C10_ACCENT,true,false);',
        'hubV1125Action(hubUi13ActionRect(),"Media",C10_ACCENT,true,false);',
        "sound action label",
    )
    text = replace_once(
        text,
        'if(g_ui12SettingsView==2){drawUi13Sound();return;}if(g_ui12SettingsView==3)',
        'if(g_ui12SettingsView==2){drawUi13Sound();return;}if(g_ui12SettingsView==10){drawOs12Media();return;}if(g_ui12SettingsView==11){drawOs12Recorder();return;}if(g_ui12SettingsView==12){drawOs12VideoViewer();return;}if(g_ui12SettingsView==3)',
        "media render routing",
    )
    text = replace_once(
        text,
        'if(hubUi13ActionRect().contains(x,y)){g_ui12SettingsView=6;buzzerPlay(BUZZ_CLICK);g_dirty=true;return true;}\n        return true;\n      }\n      if(g_ui12SettingsView==6){',
        'if(hubUi13ActionRect().contains(x,y)){g_ui12SettingsView=10;buzzerPlay(BUZZ_CLICK);g_dirty=true;return true;}\n        return true;\n      }' + MEDIA_TOUCH + '      if(g_ui12SettingsView==6){',
        "media touch routing",
    )

    hub_path.write_text(text, encoding="utf-8")
    print("Workshop OS 12 Media touchscreen UI installed")


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
        raise SystemExit(str(exc)) from exc
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
