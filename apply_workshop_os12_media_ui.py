#!/usr/bin/env python3
"""Add a capability-safe Media experience to the reconstructed UI13 settings flow."""
from __future__ import annotations

import argparse
from pathlib import Path


class PatchError(RuntimeError):
    pass


INCLUDE = '#include "workshop_media_runtime.h"\n'

MEDIA_UI = r'''
static void drawOs12Media() {
  const workshop::media::Snapshot& m=workshopMediaSnapshot();
  tft.fillScreen(C10_BG);drawHeader("Media",workshop::media::sessionStateName(m.runtime.session),3);uiBottomNav(3,nullptr);
  char volume[16];snprintf(volume,sizeof(volume),"%u%%",(unsigned)m.runtime.volumePercent);
  hubUi13StepperRow(hubUi13RowRect(0),"Speaker Volume",volume,m.capabilities.speakerAvailable?(m.runtime.muted?"Muted":"Output ready"):"Speaker unavailable",m.capabilities.speakerAvailable?C10_ACCENT:C10_MUTED);
  hubUi13InfoRow(hubUi13RowRect(1),"Speaker Test",m.capabilities.speakerAvailable?"Tap to test":"Unavailable",m.capabilities.speakerAvailable?"Local diagnostic tone":"Hardware not detected",m.capabilities.speakerAvailable?C10_GREEN:C10_MUTED);
  char mic[20];if(m.capabilities.microphoneAvailable)snprintf(mic,sizeof(mic),"%u%%",(unsigned)m.runtime.microphoneLevelPercent);else strlcpy(mic,"Unavailable",sizeof(mic));
  hubUi13InfoRow(hubUi13RowRect(2),"Microphone",mic,m.capabilities.microphoneAvailable?"Tap to sample 250 ms":"Hardware not detected",m.capabilities.microphoneAvailable?C10_ACCENT:C10_MUTED);
  hubV1125Action(hubUi13BackRect(),"Back",C10_ACCENT,true,false);hubV1125Action(hubUi13ActionRect(),"Media Lab",C10_ACCENT,true,false);hubMarkFrameDirty();g_dirty=false;
}

static void drawOs12MediaLab() {
  const workshop::media::Snapshot& m=workshopMediaSnapshot();
  tft.fillScreen(C10_BG);drawHeader("Media Lab","Diagnostics",3);uiBottomNav(3,nullptr);
  hubUi13InfoRow(hubUi13RowRect(0),"Recording",m.capabilities.microphoneAvailable&&m.capabilities.psramAvailable?"Backend pending":"Unavailable","Bounded capture must be physically validated",C10_MUTED);
  hubUi13InfoRow(hubUi13RowRect(1),"Video",m.capabilities.videoDecoderAvailable?"Ready":"Unavailable",m.capabilities.videoDecoderAvailable?"MJPEG decoder ready":"Decoder is not advertised yet",m.capabilities.videoDecoderAvailable?C10_GREEN:C10_MUTED);
  char ram[28];if(m.capabilities.psramAvailable)snprintf(ram,sizeof(ram),"%lu KB",(unsigned long)(m.capabilities.psramFreeBytes/1024U));else strlcpy(ram,"Unavailable",sizeof(ram));
  hubUi13InfoRow(hubUi13RowRect(2),"PSRAM",ram,"Media working memory",m.capabilities.psramAvailable?C10_GREEN:C10_MUTED);
  hubV1125Action(hubUi13BackRect(),"Back",C10_ACCENT,true,false);hubV1125Action(hubUi13ActionRect(),"Printer Alerts",C10_ACCENT,true,false);hubMarkFrameDirty();g_dirty=false;
}
'''

MEDIA_TOUCH = r'''
      if(g_ui12SettingsView==10){
        workshop::media::MediaService& media=workshopMediaService();
        if(hubUi13MinusRect(0).contains(x,y)||hubUi13PlusRect(0).contains(x,y)){
          int v=(int)media.snapshot().runtime.volumePercent+(hubUi13MinusRect(0).contains(x,y)?-10:10);if(v<0)v=0;if(v>100)v=100;
          if(media.setVolume((uint8_t)v)){buzzerSettings.volume=(uint8_t)v;saveBuzzerSettings();buzzerPlay(BUZZ_CLICK);}g_dirty=true;return true;
        }
        if(hubUi13RowRect(1).contains(x,y)){if(media.snapshot().runtime.session!=workshop::media::SessionState::Idle)media.stop(millis());if(media.testSpeaker(millis())){delay(120);media.stop(millis());}g_dirty=true;return true;}
        if(hubUi13RowRect(2).contains(x,y)){if(media.snapshot().runtime.session==workshop::media::SessionState::Idle)media.sampleMicrophone(millis());g_dirty=true;return true;}
        if(hubUi13BackRect().contains(x,y)){g_ui12SettingsView=2;buzzerPlay(BUZZ_CLICK);g_dirty=true;return true;}
        if(hubUi13ActionRect().contains(x,y)){g_ui12SettingsView=11;buzzerPlay(BUZZ_CLICK);g_dirty=true;return true;}
        return true;
      }
      if(g_ui12SettingsView==11){
        if(hubUi13BackRect().contains(x,y)){g_ui12SettingsView=10;buzzerPlay(BUZZ_CLICK);g_dirty=true;return true;}
        if(hubUi13ActionRect().contains(x,y)){g_ui12SettingsView=6;buzzerPlay(BUZZ_CLICK);g_dirty=true;return true;}
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


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise PatchError(f"{label}: expected one anchor, found {count}")
    return text.replace(old, new, 1)


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
        'if(g_ui12SettingsView==2){drawUi13Sound();return;}if(g_ui12SettingsView==10){drawOs12Media();return;}if(g_ui12SettingsView==11){drawOs12MediaLab();return;}if(g_ui12SettingsView==3)',
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
