#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

import apply_smart_home_audio_console_v11_24 as base

MARKER = "Workshop OS v11.24 Hardware Console LED preservation"

DRAW = r'''static void drawAudioSettings(bool full) {
  (void)full;
  const int16_t W=tft.width();
  const uint8_t page=(uint8_t)(g_audioSettingsPage%7U);
  static const char* titles[] = {"OUTPUT","MIC","ALERTS","QUIET","LED","FINISH","ERROR"};
  tft.fillScreen(UI_BG);
  drawHeader("HARDWARE",titles[page],3);
  uiBottomNav(3,nullptr);

  char value[24];
  if(page==0){
    snprintf(value,sizeof(value),"%u%%",(unsigned)buzzerSettings.volume);
    uiDisplaySettingCard(hubMoreRect(0),"VOLUME -10",value,
                         "Lower ES8311 speaker output",UI_CYAN);
    uiDisplaySettingCard(hubMoreRect(1),"VOLUME +10",value,
                         "Raise ES8311 speaker output",UI_CYAN);
    uiDisplaySettingCard(hubMoreRect(2),"EVENT SOUNDS",buzzerSettings.enabled?"ON":"OFF",
                         "Print, connection and device events",UI_ORANGE);
    uiDisplaySettingCard(hubMoreRect(3),"SPEAKER TEST","RUN",
                         "Play a local two-tone hardware check",UI_PURPLE);
  }else if(page==1){
    if(g_audioConsoleMicLevel>=0) snprintf(value,sizeof(value),"%d%%",g_audioConsoleMicLevel);
    else strlcpy(value,"RUN",sizeof(value));
    uiDisplaySettingCard(hubMoreRect(0),"MIC LEVEL",value,
                         "Sample onboard microphone for 250 ms",UI_CYAN);
    uiDisplaySettingCard(hubMoreRect(1),"ECHO 1 SEC","RUN",
                         "Record locally, then play through speaker",UI_GREEN);
    uiDisplaySettingCard(hubMoreRect(2),"ECHO 3 SEC","RUN",
                         "Longer local talkback check",UI_GREEN);
    uiDisplaySettingCard(hubMoreRect(3),"ECHO 5 SEC","RUN",
                         "PSRAM-backed five-second voice loop",UI_PURPLE);
  }else if(page==2){
    snprintf(value,sizeof(value),"%u C",(unsigned)buzzerSettings.bedCooldownThresholdC);
    uiDisplaySettingCard(hubMoreRect(0),"BUTTON CLICKS",buzzerSettings.buttonClick?"ON":"OFF",
                         "Touch feedback sound",UI_CYAN);
    uiDisplaySettingCard(hubMoreRect(1),"BED COOLDOWN",buzzerSettings.bedCooldownAlert?"ON":"OFF",
                         "Alert when the bed reaches its threshold",UI_ORANGE);
    uiDisplaySettingCard(hubMoreRect(2),"THRESHOLD -5",value,
                         "Lower cooldown temperature",UI_PURPLE);
    uiDisplaySettingCard(hubMoreRect(3),"THRESHOLD +5",value,
                         "Raise cooldown temperature",UI_GREEN);
  }else if(page==3){
    char qs[12],qe[12];
    hubQuietHourLabel(buzzerSettings.quietStartHour,qs,sizeof(qs),true);
    hubQuietHourLabel(buzzerSettings.quietEndHour,qe,sizeof(qe),false);
    uiDisplaySettingCard(hubMoreRect(0),"QUIET START -1",qs,
                         "Move start one hour earlier",UI_PURPLE);
    uiDisplaySettingCard(hubMoreRect(1),"QUIET START +1",qs,
                         "Move start one hour later",UI_PURPLE);
    uiDisplaySettingCard(hubMoreRect(2),"QUIET END -1",qe,
                         "Move end one hour earlier",UI_GREEN);
    uiDisplaySettingCard(hubMoreRect(3),"QUIET END +1",qe,
                         "Move end one hour later",UI_GREEN);
  }else if(page==4){
    char br[16];snprintf(br,sizeof(br),"%u%%",(unsigned)hubLevelPct(ledSettings.brightness));
    uiDisplaySettingCard(hubMoreRect(0),"STATUS LED",ledSettings.enabled?"ON":"OFF",
                         "Master indicator output",UI_ORANGE);
    uiDisplaySettingCard(hubMoreRect(1),"BRIGHTNESS -25",br,
                         "Lower status LED brightness",UI_CYAN);
    uiDisplaySettingCard(hubMoreRect(2),"BRIGHTNESS +25",br,
                         "Raise status LED brightness",UI_CYAN);
    uiDisplaySettingCard(hubMoreRect(3),"PRINT AUTO",ledSettings.autoOnWhilePrinting?"ON":"OFF",
                         "Auto-on follows active printing",UI_PURPLE);
  }else if(page==5){
    char secs[20],peak[16];
    snprintf(secs,sizeof(secs),"%u SEC",(unsigned)ledSettings.finishSeconds);
    snprintf(peak,sizeof(peak),"%u%%",(unsigned)hubLevelPct(ledSettings.finishBrightness));
    uiDisplaySettingCard(hubMoreRect(0),"PAUSE BREATH",ledSettings.pauseBreathing?"ON":"OFF",
                         "Slow breath during print pause",UI_GREEN);
    uiDisplaySettingCard(hubMoreRect(1),"FINISH EFFECT",hubLedFinishModeLabel(),
                         "Tap to cycle effect",UI_ORANGE);
    uiDisplaySettingCard(hubMoreRect(2),"FINISH DURATION",secs,
                         "Tap to cycle 5-600 sec",UI_CYAN);
    uiDisplaySettingCard(hubMoreRect(3),"FINISH PEAK",peak,
                         "Tap to raise/wrap brightness",UI_PURPLE);
  }else{
    char secs[20];
    if(ledSettings.errorStrobeSeconds==0)strlcpy(secs,"UNTIL CLEAR",sizeof(secs));
    else snprintf(secs,sizeof(secs),"%u SEC",(unsigned)ledSettings.errorStrobeSeconds);
    uiDisplaySettingCard(hubMoreRect(0),"ERROR STROBE",ledSettings.errorStrobe?"ON":"OFF",
                         "Fast indicator strobe on error",UI_ORANGE);
    uiDisplaySettingCard(hubMoreRect(1),"ERROR DURATION",secs,
                         "Tap to cycle 0 / 5-600 sec",UI_CYAN);
    uiDisplaySettingCard(hubMoreRect(2),"LED DRIVER",hubLedDriverLabel(),
                         "Read-only; wiring stays in portal",UI_PURPLE);
    uiDisplaySettingCard(hubMoreRect(3),"GPIO & COLORS","PORTAL",
                         "Expert wiring and RGB color setup",UI_GREEN);
  }

  HubRect back=hubSystemSubBackRect(),next=hubSystemSubNextRect();
  const char* nextLabel=page==0?"MIC >":(page==1?"ALERTS >":(page==2?"QUIET >":(page==3?"LED >":(page==4?"FINISH >":(page==5?"ERROR >":"OUTPUT >")))));
  if(hubLandscape()){
    uiPanelFill(148,210,W-296,54);
    uiDrawFit(g_audioDiagMessage,158,237,W-316,FONT_SMALL,ML_DATUM,g_audioDiagColor,UI_PANEL_2);
  }else{
    uiPanelFill(10,306,W-20,48);
    uiDrawFit(g_audioDiagMessage,20,330,W-40,FONT_SMALL,ML_DATUM,g_audioDiagColor,UI_PANEL_2);
  }
  uiActionButton(back,"< SYSTEM",UI_BLUE);
  uiActionButton(next,nextLabel,UI_PURPLE);
  hubMarkFrameDirty();g_dirty=false;
}'''

TOUCH = r'''    if(g_audioSettingsView){
      if(hubSystemSubBackRect().contains(x,y)){
        g_audioSettingsView=false;g_audioSettingsPage=0;g_audioConsoleMicLevel=-1;
        g_dirty=true;buzzerPlay(BUZZ_CLICK);return true;
      }
      if(hubSystemSubNextRect().contains(x,y)){
        g_audioSettingsPage=(uint8_t)((g_audioSettingsPage+1U)%7U);
        g_audioConsoleMicLevel=-1;g_dirty=true;buzzerPlay(BUZZ_CLICK);return true;
      }
      for(uint8_t i=0;i<4;i++) if(hubMoreRect(i).contains(x,y)){
        const uint8_t page=(uint8_t)(g_audioSettingsPage%7U);
        if(page==0){
          if(i==0 || i==1){
            int v=(int)buzzerSettings.volume+(i==0?-10:10);
            if(v<0)v=0;if(v>100)v=100;
            buzzerSettings.volume=(uint8_t)v;
            saveBuzzerSettings();
#if defined(BOARD_HAS_ES8311_AUDIO)
            buzzerBackendSetVolume(buzzerSettings.volume);
#endif
            char msg[48];snprintf(msg,sizeof(msg),"Speaker volume %u%%",(unsigned)buzzerSettings.volume);
            setAudioDiag(msg,buzzerSettings.volume?UI_CYAN:UI_DIM);
          }else if(i==2){
            buzzerSettings.enabled=!buzzerSettings.enabled;saveBuzzerSettings();initBuzzer();
            setAudioDiag(buzzerSettings.enabled?"Event sounds enabled":"Event sounds muted",
                         buzzerSettings.enabled?UI_GREEN:UI_DIM);
          }else{
            if(buzzerIsPlaying()) setAudioDiag("Speaker busy - try again",UI_AMBER);
            else{
              setAudioDiag("Speaker chime playing",UI_GREEN);drawAudioSettings(true);
#if defined(BOARD_HAS_ES8311_AUDIO)
              buzzerBackendApplyStep(1047);delay(90);buzzerBackendStop();delay(45);
              buzzerBackendApplyStep(1568);delay(130);buzzerBackendStop();
#else
              buzzerPlay(BUZZ_CONNECTED);
#endif
              setAudioDiag("Speaker test complete",UI_GREEN);
            }
          }
        }else if(page==1){
#if defined(BOARD_HAS_MICROPHONE)
          if(buzzerIsPlaying()) setAudioDiag("Wait for current sound",UI_AMBER);
          else if(i==0){
            setAudioDiag("Sampling microphone...",UI_PURPLE);drawAudioSettings(true);
            int level=buzzerBackendMicLevel(250);
            g_audioConsoleMicLevel=level;
            if(level<0)setAudioDiag("Microphone unavailable",UI_RED);
            else if(level<2){char msg[48];snprintf(msg,sizeof(msg),"Mic %d%% - very quiet",level);setAudioDiag(msg,UI_AMBER,level);}
            else if(level>85){char msg[48];snprintf(msg,sizeof(msg),"Mic %d%% - very loud",level);setAudioDiag(msg,UI_AMBER,level);}
            else{char msg[48];snprintf(msg,sizeof(msg),"Mic %d%% - input detected",level);setAudioDiag(msg,UI_GREEN,level);}
          }else{
            const uint16_t recordMs=(i==1)?1000U:(i==2)?3000U:5000U;
            char listening[56];snprintf(listening,sizeof(listening),"Listening %u sec - speak now",(unsigned)(recordMs/1000U));
            setAudioDiag(listening,UI_PURPLE);drawAudioSettings(true);
            int level=buzzerBackendMicEcho(recordMs);
            g_audioConsoleMicLevel=level;
            if(level<0)setAudioDiag("Mic echo unavailable",UI_RED);
            else if(level<2){char msg[56];snprintf(msg,sizeof(msg),"Mic %d%% - very quiet - try again",level);setAudioDiag(msg,UI_AMBER,level);}
            else{char msg[56];snprintf(msg,sizeof(msg),"Mic %d%% - playback complete",level);setAudioDiag(msg,UI_GREEN,level);}
          }
#else
          setAudioDiag("Microphone not available on this board",UI_DIM);
#endif
        }else if(page==2){
          if(i==0){
            buzzerSettings.buttonClick=!buzzerSettings.buttonClick;saveBuzzerSettings();
            setAudioDiag(buzzerSettings.buttonClick?"Button clicks enabled":"Button clicks disabled",
                         buzzerSettings.buttonClick?UI_GREEN:UI_DIM);
          }else if(i==1){
            buzzerSettings.bedCooldownAlert=!buzzerSettings.bedCooldownAlert;saveBuzzerSettings();
            setAudioDiag(buzzerSettings.bedCooldownAlert?"Bed cooldown alert enabled":"Bed cooldown alert disabled",
                         buzzerSettings.bedCooldownAlert?UI_GREEN:UI_DIM);
          }else{
            buzzerSettings.bedCooldownThresholdC=hubStepCooldownThreshold(
                buzzerSettings.bedCooldownThresholdC,i==2);
            saveBuzzerSettings();
            char msg[56];snprintf(msg,sizeof(msg),"Cooldown threshold %u C",(unsigned)buzzerSettings.bedCooldownThresholdC);
            setAudioDiag(msg,UI_CYAN);
          }
        }else if(page==3){
          if(i==0 || i==1){
            buzzerSettings.quietStartHour=hubStepHour(buzzerSettings.quietStartHour,i==0);
            saveBuzzerSettings();
            setAudioDiag(buzzerSettings.quietStartHour?"Quiet start updated":"Quiet hours disabled",UI_PURPLE);
          }else{
            buzzerSettings.quietEndHour=hubStepHour(buzzerSettings.quietEndHour,i==2);
            saveBuzzerSettings();setAudioDiag("Quiet end updated",UI_GREEN);
          }
        }else if(page==4){
          static const uint8_t ledLevels[]={0,64,128,192,255};
          if(i==0){
            ledSettings.enabled=!ledSettings.enabled;
            hubPersistLed(ledSettings.enabled?"Status LED enabled":"Status LED disabled",ledSettings.enabled?UI_GREEN:UI_DIM);
          }else if(i==1){
            ledSettings.brightness=hubStepPreset(ledSettings.brightness,ledLevels,5,true);
            hubPersistLed("LED brightness lowered",UI_CYAN);
          }else if(i==2){
            ledSettings.brightness=hubStepPreset(ledSettings.brightness,ledLevels,5,false);
            hubPersistLed("LED brightness raised",UI_CYAN);
          }else{
            ledSettings.autoOnWhilePrinting=!ledSettings.autoOnWhilePrinting;
            hubPersistLed("Print auto behavior updated",UI_PURPLE);
          }
        }else if(page==5){
          static const uint8_t ledLevels[]={0,64,128,192,255};
          if(i==0){
            ledSettings.pauseBreathing=!ledSettings.pauseBreathing;
            hubPersistLed("Pause breathing updated",UI_GREEN);
          }else if(i==1){
            ledSettings.finishMode=(uint8_t)((ledSettings.finishMode+1U)%3U);
            hubPersistLed("Finish effect updated",UI_ORANGE);
          }else if(i==2){
            ledSettings.finishSeconds=hubStepLedSeconds(ledSettings.finishSeconds,false,false);
            hubPersistLed("Finish duration updated",UI_CYAN);
          }else{
            ledSettings.finishBrightness=hubStepPreset(ledSettings.finishBrightness,ledLevels,5,false);
            hubPersistLed("Finish peak updated",UI_PURPLE);
          }
        }else{
          if(i==0){
            ledSettings.errorStrobe=!ledSettings.errorStrobe;
            hubPersistLed("Error strobe updated",ledSettings.errorStrobe?UI_RED:UI_DIM);
          }else if(i==1){
            ledSettings.errorStrobeSeconds=hubStepLedSeconds(ledSettings.errorStrobeSeconds,false,true);
            hubPersistLed("Error duration updated",UI_CYAN);
          }else{
            setAudioDiag("LED hardware wiring stays in portal",UI_DIM);
          }
        }
        g_dirty=true;return true;
      }
      return true;
    }'''


def main() -> int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--repo",required=True)
    ap.add_argument("--apply",action="store_true")
    args=ap.parse_args()
    if not args.apply:
        raise SystemExit("refusing to modify source without --apply")
    root=Path(args.repo).resolve()
    rel="src/smart_hub.cpp"
    text=base.load(root,rel)
    if MARKER in text:
        print("v11.24 LED preservation already applied")
        return 0
    text=base.replace_braced(text,"static void drawAudioSettings(bool full)",DRAW,"seven-page Hardware Console renderer")
    text=base.replace_braced(text,"    if(g_audioSettingsView){",TOUCH,"seven-page Hardware Console touch")
    text += f"\n// {MARKER}\n"
    base.save(root,rel,text)

    body=base.load(root,rel)
    for needle in [
        "g_audioSettingsPage%7U",
        "(g_audioSettingsPage+1U)%7U",
        '"OUTPUT"','"MIC"','"ALERTS"','"QUIET"','"LED"','"FINISH"','"ERROR"',
        '"STATUS LED"','"BRIGHTNESS -25"','"BRIGHTNESS +25"','"PRINT AUTO"',
        '"PAUSE BREATH"','"FINISH EFFECT"','"FINISH DURATION"','"FINISH PEAK"',
        '"ERROR STROBE"','"ERROR DURATION"','"LED DRIVER"','"GPIO & COLORS"',
        "saveLedSettings()","initLed()",
    ]:
        if needle not in body:
            raise base.PatchError(f"LED preservation contract missing: {needle}")
    print("Workshop OS v11.24 seven-page Hardware Console applied")
    return 0


if __name__=="__main__":
    raise SystemExit(main())
