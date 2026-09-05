#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

import apply_smart_home_audio_console_v11_24 as base

MARKER="Workshop OS v11.24 Hardware Console Power Automation preservation"


def main()->int:
    ap=argparse.ArgumentParser();ap.add_argument("--repo",required=True);ap.add_argument("--apply",action="store_true");args=ap.parse_args()
    if not args.apply: raise SystemExit("refusing to modify source without --apply")
    root=Path(args.repo).resolve();rel="src/smart_hub.cpp";text=base.load(root,rel)
    if MARKER in text:
        print("v11.24 Power Automation preservation already applied");return 0

    a,b,draw=base.function_body(text,"static void drawAudioSettings(bool full)","Hardware Console renderer")
    draw=draw.replace("g_audioSettingsPage%7U","g_audioSettingsPage%9U",1)
    draw=draw.replace(
        'static const char* titles[] = {"OUTPUT","MIC","ALERTS","QUIET","LED","FINISH","ERROR"};',
        'static const char* titles[] = {"OUTPUT","MIC","ALERTS","QUIET","LED","FINISH","ERROR","POWER","AUTO OFF"};',1)
    draw=draw.replace(
        '  }else{\n    char secs[20];\n    if(ledSettings.errorStrobeSeconds==0)',
        '  }else if(page==6){\n    char secs[20];\n    if(ledSettings.errorStrobeSeconds==0)',1)
    power_render=r'''  }else if(page==7){
    const uint8_t plug=hubPowerConfigPlug();
    if(plug==0xFF){
      uiDisplaySettingCard(hubMoreRect(0),"PLUG STATUS","NO SLOT","Selected printer has no plug slot",UI_MUTED);
      uiDisplaySettingCard(hubMoreRect(1),"POLL INTERVAL","N/A","No mapped plug for this printer",UI_CYAN);
      uiDisplaySettingCard(hubMoreRect(2),"STATUS DISPLAY","N/A","Configure plug mapping in portal",UI_PURPLE);
      uiDisplaySettingCard(hubMoreRect(3),"BUTTON POWER",dispSettings.buttonPowerControl?"ON":"OFF","Global physical button option",UI_GREEN);
    }else{
      TasmotaSettings& ps=tasmotaSettings[plug];
      char poll[16],detail[48];snprintf(poll,sizeof(poll),"%u SEC",(unsigned)ps.pollInterval);
      snprintf(detail,sizeof(detail),"Plug %u - %s",(unsigned)(plug+1),ps.ip[0]?ps.ip:"set address in portal");
      uiDisplaySettingCard(hubMoreRect(0),"PLUG STATUS",ps.enabled?"ON":(ps.ip[0]?"OFF":"NEEDS IP"),detail,UI_ORANGE);
      uiDisplaySettingCard(hubMoreRect(1),"POLL INTERVAL",poll,"Tap to cycle 10-60 sec",UI_CYAN);
      uiDisplaySettingCard(hubMoreRect(2),"STATUS DISPLAY",hubPowerDisplayModeLabel(ps.displayMode),"Tap: Alternate / Power / Layer",UI_PURPLE);
      uiDisplaySettingCard(hubMoreRect(3),"BUTTON POWER",dispSettings.buttonPowerControl?"ON":"OFF","Physical button power-control option",UI_GREEN);
    }
  }else{
    const uint8_t plug=hubPowerConfigPlug();
    if(plug==0xFF){
      uiDisplaySettingCard(hubMoreRect(0),"AUTO OFF","UNAVAILABLE","No mapped plug for selected printer",UI_MUTED);
      uiDisplaySettingCard(hubMoreRect(1),"AUTO OFF DELAY","N/A","Configure plug mapping in portal",UI_CYAN);
      uiDisplaySettingCard(hubMoreRect(2),"CANCEL ON DOOR","N/A","No mapped power target",UI_PURPLE);
      uiDisplaySettingCard(hubMoreRect(3),"PLUG CONFIG","PORTAL","Configure printer/plug mapping",UI_GREEN);
    }else{
      TasmotaSettings& ps=tasmotaSettings[plug];
      char delay[20],detail[48];snprintf(delay,sizeof(delay),"%u MIN",(unsigned)ps.autoOffDelayMin);
      snprintf(detail,sizeof(detail),"%s - Plug %u",hubPowerTypeLabel(ps.plugType),(unsigned)(plug+1));
      uiDisplaySettingCard(hubMoreRect(0),"AUTO OFF",ps.autoOffEnabled?"ON":"OFF","Power down after print completion",UI_ORANGE);
      uiDisplaySettingCard(hubMoreRect(1),"AUTO OFF DELAY",delay,"Tap to cycle 1-240 min",UI_CYAN);
      uiDisplaySettingCard(hubMoreRect(2),"CANCEL ON DOOR",ps.autoOffCancelOnDoor?"ON":"OFF","Opening door cancels pending auto-off",UI_PURPLE);
      uiDisplaySettingCard(hubMoreRect(3),"PLUG CONFIG",detail,ps.ip[0]?ps.ip:"IP/type/outlet setup stays in portal",UI_GREEN);
    }
'''
    anchor='  }\n\n  HubRect back=hubSystemSubBackRect(),next=hubSystemSubNextRect();'
    if anchor not in draw: raise base.PatchError("Hardware Console render tail anchor missing")
    draw=draw.replace(anchor,power_render+'  }\n\n  HubRect back=hubSystemSubBackRect(),next=hubSystemSubNextRect();',1)
    old_next='const char* nextLabel=page==0?"MIC >":(page==1?"ALERTS >":(page==2?"QUIET >":(page==3?"LED >":(page==4?"FINISH >":(page==5?"ERROR >":"OUTPUT >")))));'
    new_next='const char* nextLabel=page==0?"MIC >":(page==1?"ALERTS >":(page==2?"QUIET >":(page==3?"LED >":(page==4?"FINISH >":(page==5?"ERROR >":(page==6?"POWER >":(page==7?"AUTO OFF >":"OUTPUT >")))))));'
    if old_next not in draw: raise base.PatchError("Hardware Console next-label anchor missing")
    draw=draw.replace(old_next,new_next,1)
    text=text[:a]+draw+text[b:]

    a,b,touch=base.function_body(text,"    if(g_audioSettingsView){","Hardware Console touch")
    touch=touch.replace("(g_audioSettingsPage+1U)%7U","(g_audioSettingsPage+1U)%9U",1)
    touch=touch.replace("g_audioSettingsPage%7U","g_audioSettingsPage%9U",1)
    touch=touch.replace(
        '        }else{\n          if(i==0){\n            ledSettings.errorStrobe=!ledSettings.errorStrobe;',
        '        }else if(page==6){\n          if(i==0){\n            ledSettings.errorStrobe=!ledSettings.errorStrobe;',1)
    power_touch=r'''        }else if(page==7){
          const uint8_t plug=hubPowerConfigPlug();
          if(i==3){
            dispSettings.buttonPowerControl=!dispSettings.buttonPowerControl;
            hubPersistPower("Button power-control setting updated",UI_GREEN);
          }else if(plug==0xFF){
            setAudioDiag("Selected printer has no smart-plug slot",UI_AMBER);
          }else{
            TasmotaSettings& ps=tasmotaSettings[plug];
            if(i==0){
              if(!ps.enabled&&!ps.ip[0]) setAudioDiag("Set plug IP in portal before enabling",UI_AMBER);
              else{ps.enabled=!ps.enabled;hubPersistPower(ps.enabled?"Smart plug enabled":"Smart plug disabled",ps.enabled?UI_GREEN:UI_DIM);}
            }else if(i==1){
              ps.pollInterval=hubStepPowerPoll(ps.pollInterval,false);hubPersistPower("Power poll interval updated",UI_CYAN);
            }else{
              ps.displayMode=(uint8_t)((ps.displayMode+1U)%3U);hubPersistPower("Power status display updated",UI_PURPLE);
            }
          }
        }else{
          const uint8_t plug=hubPowerConfigPlug();
          if(plug==0xFF){
            setAudioDiag("Selected printer has no smart-plug slot",UI_AMBER);
          }else{
            TasmotaSettings& ps=tasmotaSettings[plug];
            if(i==0){
              ps.autoOffEnabled=!ps.autoOffEnabled;hubPersistPower(ps.autoOffEnabled?"Printer auto-off enabled":"Printer auto-off disabled",ps.autoOffEnabled?UI_GREEN:UI_DIM);
            }else if(i==1){
              ps.autoOffDelayMin=hubStepAutoOffDelay(ps.autoOffDelayMin,false);hubPersistPower("Auto-off delay updated",UI_CYAN);
            }else if(i==2){
              ps.autoOffCancelOnDoor=!ps.autoOffCancelOnDoor;hubPersistPower("Door-cancel setting updated",UI_PURPLE);
            }else{
              setAudioDiag("Plug IP, type and outlet stay in portal",UI_DIM);
            }
          }
'''
    anchor='        }\n        g_dirty=true;return true;'
    if anchor not in touch: raise base.PatchError("Hardware Console touch tail anchor missing")
    touch=touch.replace(anchor,power_touch+'        }\n        g_dirty=true;return true;',1)
    text=text[:a]+touch+text[b:]
    text += f"\n// {MARKER}\n"
    base.save(root,rel,text)

    body=base.load(root,rel)
    for needle in [
        "g_audioSettingsPage%9U","(g_audioSettingsPage+1U)%9U",
        '"POWER"','"AUTO OFF"','"PLUG STATUS"','"POLL INTERVAL"','"STATUS DISPLAY"','"BUTTON POWER"',
        '"AUTO OFF DELAY"','"CANCEL ON DOOR"','"PLUG CONFIG"',
        "hubPowerConfigPlug","hubStepPowerPoll","hubStepAutoOffDelay","hubPersistPower",
        "ps.autoOffEnabled=!ps.autoOffEnabled","ps.autoOffCancelOnDoor=!ps.autoOffCancelOnDoor",
    ]:
        if needle not in body: raise base.PatchError(f"Power preservation contract missing: {needle}")
    print("Workshop OS v11.24 nine-page Hardware Console applied")
    return 0


if __name__=="__main__": raise SystemExit(main())
