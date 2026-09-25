# Sky Radar — Context Bundle (Complete)

## 1. ScreenState enum
```cpp
enum ScreenState {
  SCREEN_SPLASH,
  SCREEN_AP_MODE,
  SCREEN_CONNECTING_WIFI,
  SCREEN_WIFI_CONNECTED,
  SCREEN_CONNECTING_MQTT,
  SCREEN_IDLE,
  SCREEN_PRINTING,
  SCREEN_FINISHED,
  SCREEN_CLOCK,
  SCREEN_OFF,
  SCREEN_OTA_UPDATE,
  SCREEN_SPLIT,         // two printers side-by-side (top/bottom bands)
  SCREEN_CAMERA,        // fullscreen P1/A1 chamber image (#120); tap to exit
  SCREEN_POWER_CONFIRM, // fullscreen plug on/off confirmation (#136); hold to confirm
  SCREEN_DRY_PEEK,      // AMS drying view tapped up during a print (#150); auto-closes
  SCREEN_HMS,           // printer error detail; tap to open while one is active
  SCREEN_HUB_HOME,      // Smart Display v6: clock + printer at-a-glance
  SCREEN_HUB_WORKSHOP,  // Smart Display v6: printer + AMS workshop view
  SCREEN_HUB_CUSTOM,    // Smart Display v6: external read-only JSON card feed
  SCREEN_HUB_SYSTEM, SCREEN_HUB_PRINTER, SCREEN_HUB_MORE     // Smart Display v6: ESP32 / network health
};
```

## 2. Color constants — CLR_* (global, from config.h)
```cpp

// =============================================================================
//  Color palette (RGB565)
// =============================================================================
#define CLR_BG          0x0000   // black
#define CLR_CARD        0x1926   // dark card bg
#define CLR_HEADER      0x10A2   // header bar bg
// Text colors are user-configurable (#163), so these two are only the factory
// DEFAULTS. The live values are CLR_TEXT / CLR_TEXT_DIM, defined in settings.h
// as dispSettings lookups - a drawing file must include settings.h to paint
// text, and gets a compile error rather than a silently unthemed screen if it
// forgets. Do not reintroduce CLR_TEXT here.
#define CLR_TEXT_DEFAULT     0xFFFF   // white
#define CLR_TEXT_DIM_DEFAULT 0xC618   // gray text
#define CLR_TEXT_DARK        0x7BEF   // darker gray (chrome: inactive dots,
                                      // arc tracks - not text, stays fixed)
#define CLR_GREEN        0x07E0   // bright green
#define CLR_GREEN_DARK   0x0400   // dark green (track)
#define CLR_BLUE         0x34DF   // accent blue
#define CLR_ORANGE       0xFBE0   // nozzle accent
#define CLR_CYAN         0x07FF   // bed accent
#define CLR_RED          0xF800   // error / hot
#define CLR_YELLOW       0xFFE0   // pause / warm
#define CLR_GOLD         0xFEA0   // progress near done
#define CLR_TRACK        0x18E3   // arc background track

// =============================================================================
//  MQTT / Bambu
// =============================================================================
#define BAMBU_PORT                  8883
#define BAMBU_USERNAME              "bblp"
```

## 3. Color constants — UI_* (local to smart_hub.cpp)
```cpp
// The WS350 is only 320x480. v9 gets the richer appearance with procedural
// graphics and small reusable primitives instead of large bitmaps, preserving
// flash/heap headroom and avoiding image-decoder stalls during live printing.
static const uint16_t UI_BG       = 0x0020; // #050607 graphite black
static const uint16_t UI_PANEL    = 0x0862; // #0B0D10 primary surface
static const uint16_t UI_PANEL_2  = 0x10A3; // #111418 elevated surface
static const uint16_t UI_PANEL_3  = 0x10C4; // #171B20 active surface
static const uint16_t UI_BORDER   = 0x2966; // #292E34 precision border
static const uint16_t UI_BORDER_2 = 0x2125; // #21252A soft separator
static const uint16_t UI_ORANGE   = 0xFBC0; // #FF7A00 Workshop OS ember
static const uint16_t UI_ORANGE_2 = 0xFC43; // #FF8A1F highlight
static const uint16_t UI_GLOW     = 0x38E0; // #3A1D05 low glow
static const uint16_t UI_GREEN    = 0x3E8F; // #3AD17D semantic healthy
static const uint16_t UI_CYAN     = 0x6D5F; // semantic info
static const uint16_t UI_BLUE     = 0x6D5F;
static const uint16_t UI_PURPLE   = 0xA45F;
static const uint16_t UI_AMBER    = 0xFDA9; // #FFB44A semantic warning
static const uint16_t UI_RED      = 0xFACB; // #FF5A5F semantic fault
static const uint16_t UI_TEXT     = 0xF7BE; // #F4F4F2
static const uint16_t UI_DIM      = 0xA576; // #A7ADB5
static const uint16_t UI_MUTED    = 0x6BAF; // #6D747D
static const uint16_t UI_GREEN_BG = 0x1103;
static const uint16_t UI_WARN_BG  = 0x20A1;
static const uint16_t UI_PURP_BG  = 0x1082;
static const uint16_t UI_CYAN_BG  = 0x1082;


char g_audioDiagMessage[56] = "Audio ready";
```

## 4. Font + draw helpers
```cpp
upstream/src/smart_hub.cpp:492:static void uiDrawFit(const char* text, int16_t x, int16_t y, int16_t maxPx,
upstream/src/smart_hub.cpp:608:static void uiCard(int16_t x, int16_t y, int16_t w, int16_t h,
upstream/src/smart_hub.cpp:633:static void uiPill(int16_t x, int16_t y, int16_t w,
upstream/src/smart_hub.cpp:638:  uiDrawFit(text,x+18,y+10,w-24,FONT_SMALL,ML_DATUM,color,UI_PANEL_3);
upstream/src/smart_hub.cpp:644:  uiDrawFit(label,x+9,y+9,maxPx,FONT_SMALL,ML_DATUM,UI_TEXT,UI_PANEL);
upstream/src/smart_hub.cpp:647:static void uiMetric(int16_t x, int16_t y, int16_t w, int16_t h,
upstream/src/smart_hub.cpp:650:  uiCard(x, y, w, h, UI_BORDER, false);
upstream/src/smart_hub.cpp:651:  uiDrawFit(label && *label ? label : "—",x+9,y+7,w-18,FONT_SMALL,TL_DATUM,UI_MUTED,UI_PANEL);
upstream/src/smart_hub.cpp:652:  uiDrawFit(value && *value ? value : "—",x+9,y+27,w-18,h>=58?FONT_BODY:FONT_SMALL,TL_DATUM,accent,UI_PANEL);
upstream/src/smart_hub.cpp:654:    uiDrawFit(sub,x+9,y+h-15,w-18,FONT_SMALL,TL_DATUM,UI_DIM,UI_PANEL);
upstream/src/smart_hub.cpp:735:    if (family==UI_PF_A1_MINI) uiDrawFit("mini",cx,y+h-4,w-12,FONT_SMALL,TC_DATUM,UI_MUTED,UI_BG);
upstream/src/smart_hub.cpp:759:  uiDrawFit(line,cx,y,maxPx,FONT_SMALL,TC_DATUM,UI_DIM,UI_PANEL);
upstream/src/smart_hub.cpp:864:  uiDrawFit("W",16,18,10,FONT_BODY,MC_DATUM,UI_TEXT,UI_GLOW);
upstream/src/smart_hub.cpp:865:  uiDrawFit("H",26,18,10,FONT_SMALL,MC_DATUM,accent,UI_GLOW);
upstream/src/smart_hub.cpp:866:  uiDrawFit(title?title:"WORKSHOP",43,15,hubLandscape()?250:150,FONT_BODY,ML_DATUM,UI_TEXT,UI_BG);
upstream/src/smart_hub.cpp:870:  if(clockText[0]) uiDrawFit(clockText,W-12,17,58,FONT_BODY,MR_DATUM,UI_TEXT,UI_BG);
upstream/src/smart_hub.cpp:871:  else uiDrawFit(online?"":"OFFLINE",W-12,17,72,FONT_SMALL,MR_DATUM,online?UI_MUTED:UI_RED,UI_BG);
upstream/src/smart_hub.cpp:907:    uiDrawFit(labels[i], r.x + r.w / 2, r.y + 31, r.w - 10,
upstream/src/smart_hub.cpp:908:              FONT_SMALL, TC_DATUM, c, selected ? UI_PANEL_3 : UI_PANEL_2);
upstream/src/smart_hub.cpp:926:  uiDrawFit(label, r.x + r.w / 2 + (filled ? 0 : 2), r.y + h / 2,
upstream/src/smart_hub.cpp:927:            r.w - 24, FONT_SMALL, MC_DATUM, textColor, bg);
upstream/src/smart_hub.cpp:970:  uiMetric(r.x,r.y,r.w,r.h,hubWidgetLabel(g_widgets[slot]),value,selected?UI_ORANGE:accents[slot],sub);
upstream/src/smart_hub.cpp:975:  uiCard(r.x,r.y,r.w,r.h,s.connected?UI_BORDER:UI_RED,false);
upstream/src/smart_hub.cpp:978:  if(r.w>=260){const int16_t cell=r.w/4;for(uint8_t i=0;i<4;i++){if(i)tft.drawFastVLine(r.x+i*cell,r.y+9,r.h-18,UI_BORDER);int16_t cx=r.x+i*cell+cell/2;uiDrawFit(labels[i],cx,r.y+9,cell-8,FONT_SMALL,TC_DATUM,UI_DIM,UI_PANEL);uiDrawFit(vals[i],cx,r.y+31,cell-8,FONT_BODY,TC_DATUM,i==0?UI_ORANGE:i==1?UI_AMBER:i==2?UI_BLUE:UI_CYAN,UI_PANEL);}}
upstream/src/smart_hub.cpp:979:  else{const int16_t rowH=r.h/4;for(uint8_t i=0;i<4;i++){if(i)tft.drawFastHLine(r.x+8,r.y+i*rowH,r.w-16,UI_BORDER);uiDrawFit(labels[i],r.x+10,r.y+i*rowH+rowH/2,r.w/2-14,FONT_SMALL,ML_DATUM,UI_DIM,UI_PANEL);uiDrawFit(vals[i],r.x+r.w-10,r.y+i*rowH+rowH/2,r.w/2-14,FONT_BODY,MR_DATUM,i==0?UI_ORANGE:i==1?UI_AMBER:i==2?UI_BLUE:UI_CYAN,UI_PANEL);}}
```

## 5. Sprite / canvas globals
```cpp
upstream/src/smart_hub.cpp:384:static lgfx::LovyanGFX* g_hubPanelCanvas = nullptr;
upstream/src/smart_hub.cpp:385:static lgfx::LGFX_Sprite* g_hubFrame = nullptr;
upstream/src/smart_hub.cpp:386:static int16_t g_hubFrameW = 0;
upstream/src/smart_hub.cpp:387:static int16_t g_hubFrameH = 0;
upstream/src/smart_hub.cpp:388:static bool g_hubFrameDirty = true;
upstream/src/smart_hub.cpp:389:static bool g_hubFramePrimed = false;
upstream/src/smart_hub.cpp:392:  if (!g_hubPanelCanvas) g_hubPanelCanvas = tft_ptr;
upstream/src/smart_hub.cpp:393:  if (!g_hubPanelCanvas) return false;
upstream/src/smart_hub.cpp:395:  const int16_t w = (int16_t)g_hubPanelCanvas->width();
upstream/src/smart_hub.cpp:396:  const int16_t h = (int16_t)g_hubPanelCanvas->height();
upstream/src/smart_hub.cpp:399:  if (g_hubFrame && g_hubFrameW == w && g_hubFrameH == h &&
upstream/src/smart_hub.cpp:400:      g_hubFrame->getBuffer()) {
upstream/src/smart_hub.cpp:404:  if (g_hubFrame) {
upstream/src/smart_hub.cpp:405:    g_hubFrame->deleteSprite();
upstream/src/smart_hub.cpp:406:    delete g_hubFrame;
```

## 6. Patch script template
```python
#!/usr/bin/env python3
"""Install the Workshop OS 12 media runtime into reconstructed UI13 source."""
from __future__ import annotations

import argparse
import shutil
from pathlib import Path
import sys as _sys
from pathlib import Path as _Path
_here = _Path(__file__).resolve().parent
if str(_here) not in _sys.path:
    _sys.path.insert(0, str(_here))
from scripts.smart_home_patch_utils import PatchError, fail, replace_once, replace_braced_block




MEDIA_HEADERS = (
    "media_service.h",
    "ws350_media_backend.h",
    "workshop_media_runtime.h",
)
MEDIA_SOURCES = (
    "media_service.cpp",
    "ws350_media_backend.cpp",
    "workshop_media_runtime.cpp",
)

INCLUDE_ANCHOR = '#include "workshop_platform_bridge.h"\n'
INCLUDE_LINE = '#include "workshop_media_runtime.h"\n'
BEGIN_ANCHOR = "    workshopPlatformBegin();\n"
POLL_ANCHOR = "  workshopPlatformPoll();\n"


def copy_exact(source: Path, destination: Path) -> None:
    if not source.is_file():
        raise PatchError(f"missing media source asset: {source}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)


def insert_once(text: str, anchor: str, addition: str, label: str) -> str:
    if addition.strip() in text:
        return text
    count = text.count(anchor)
    if count != 1:
        raise PatchError(f"{label}: expected one anchor, found {count}")
    return text.replace(anchor, anchor + addition, 1)


def insert_before_once(text: str, anchor: str, addition: str, label: str) -> str:
    if addition.strip() in text:
        return text
    count = text.count(anchor)
    if count != 1:
        raise PatchError(f"{label}: expected one anchor, found {count}")
    return text.replace(anchor, addition + anchor, 1)


def patch_audio_volume_contract(repo: Path) -> None:
    """Reuse the canonical ES8311 volume contract or install it if absent.

    The dedicated OS12 media-hardware layer is authoritative when it has already
    installed persisted BuzzerSettings volume plumbing. This fallback exists so
    the runtime patch remains independently reconstructable without creating a
    second codec authority.
    """
    header_path = repo / "src" / "buzzer_backend.h"
    es8311_path = repo / "src" / "buzzer_backend_es8311.cpp"
    settings_h = repo / "src" / "settings.h"
    settings_cpp = repo / "src" / "settings.cpp"
    for path in (header_path, es8311_path, settings_h, settings_cpp):
        if not path.is_file():
            raise PatchError(f"reconstructed audio dependency missing: {path}")

    header = header_path.read_text(encoding="utf-8")
    source = es8311_path.read_text(encoding="utf-8")
    settings_header = settings_h.read_text(encoding="utf-8")
    settings_source = settings_cpp.read_text(encoding="utf-8")

    already_installed = all((
        "buzzerBackendSetVolume" in header,
        "void buzzerBackendSetVolume(uint8_t percent)" in source,
        "buzzerSettings.volume" in source,
        "uint8_t volume;" in settings_header,
        'getUChar("buz_vol"' in settings_source,
        'putUChar("buz_vol"' in settings_source,
    ))
    if already_installed:
        return

    # Legacy reconstruction fallback. New OS12 reconstruction normally reaches
    # this function only after apply_workshop_os12_media_hardware.py.
    header = replace_once(
        header,
        "void buzzerBackendShutdown();\n",
        "void buzzerBackendSetVolume(uint8_t percent);\nvoid buzzerBackendShutdown();\n",
        "ES8311 volume API declaration",
    )
    header_path.write_text(header, encoding="utf-8")

    fixed_constant = "constexpr uint8_t  kCodecVolume    = 75;            // percent\n"
    if fixed_constant in source:
        source = source.replace(fixed_constant, "", 1)

    fixed_init = (
        "  uint8_t vol = (kCodecVolume == 0) ? 0 : "
        "(uint8_t)(((kCodecVolume * 256) / 100) - 1);\n"
    )
    dynamic_init = (
        "  uint8_t pct = buzzerSettings.volume <= 100 ? buzzerSettings.volume : 75;\n"
        "  uint8_t vol = (pct == 0) ? 0 : (uint8_t)(((pct * 256U) / 100U) - 1U);\n"
    )
    if dynamic_init not in source:
        if fixed_init not in source:
            raise PatchError("ES8311 startup volume anchor missing")
        source = source.replace(fixed_init, dynamic_init, 1)

    volume_function = """void buzzerBackendSetVolume(uint8_t percent) {
  if (percent > 100U) percent = 100U;
  buzzerSettings.volume = percent;
  if (!gCodecReady) return;
  const uint8_t vol = (percent == 0U)
      ? 0U
      : (uint8_t)(((uint16_t)percent * 256U) / 100U - 1U);
  esWrite(ES_REG_DAC_32, vol);
}

"""
    source = insert_before_once(
        source,
        "void buzzerBackendShutdown() {\n",
        volume_function,
        "ES8311 runtime volume implementation",
    )
    es8311_path.write_text(source, encoding="utf-8")

    final_header = header_path.read_text(encoding="utf-8")
    final_source = es8311_path.read_text(encoding="utf-8")
    if "buzzerBackendSetVolume" not in final_header:
        raise PatchError("ES8311 volume API declaration missing after patch")
    for needle in (
        "buzzerSettings.volume",
        "void buzzerBackendSetVolume(uint8_t percent)",
        "esWrite(ES_REG_DAC_32, vol);",
    ):
        if needle not in final_source:
            raise PatchError(f"ES8311 volume implementation missing after patch: {needle}")


def apply(repo: Path, source_root: Path) -> None:
    main_cpp = repo / "src" / "main.cpp"
    build_h = repo / "include" / "smart_home_build.h"
    buzzer_h = repo / "src" / "buzzer_backend.h"
    if not main_cpp.is_file() or not build_h.is_file() or not buzzer_h.is_file():
        raise PatchError("OS12 media runtime requires reconstructed firmware source")

    build_text = build_h.read_text(encoding="utf-8")
    if "WORKSHOP_OS_RELEASE_VERSION" not in build_text:
        raise PatchError("OS12 media runtime must be applied after release identity")

    patch_audio_volume_contract(repo)

    media_root = source_root / "firmware" / "platform" / "media"
    for name in MEDIA_HEADERS:
        copy_exact(media_root / name, repo / "include" / name)
    for name in MEDIA_SOURCES:
        copy_exact(media_root / name, repo / "src" / name)

    text = main_cpp.read_text(encoding="utf-8")
    text = insert_once(text, INCLUDE_ANCHOR, INCLUDE_LINE, "media runtime include")
    text = insert_once(text, BEGIN_ANCHOR, "    workshopMediaBegin();\n", "media begin")
    text = insert_once(text, POLL_ANCHOR, "  workshopMediaPoll();\n", "media poll")
    main_cpp.write_text(text, encoding="utf-8")

    if text.count("workshopMediaBegin();") != 1:
        raise PatchError("workshopMediaBegin must be injected exactly once")
    if text.count("workshopMediaPoll();") != 1:
        raise PatchError("workshopMediaPoll must be injected exactly once")

    print("Workshop OS 12 media runtime installed")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True)
    parser.add_argument("--source-root", default=str(Path(__file__).resolve().parent))
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    if not args.apply:
        raise SystemExit("refusing to modify source without --apply")
    try:
        apply(Path(args.repo).resolve(), Path(args.source_root).resolve())
    except PatchError as exc:
        raise SystemExit(str(exc)) from exc
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```
