#!/usr/bin/env python3
from __future__ import annotations
import argparse
from pathlib import Path

class PatchError(RuntimeError):
    pass

def once(text: str, old: str, new: str, label: str) -> str:
    n = text.count(old)
    if n != 1:
        raise PatchError(f"{label}: expected 1 match, found {n}")
    return text.replace(old, new, 1)

def replace_region(text: str, start: str, end: str, replacement: str, label: str) -> str:
    a = text.find(start)
    if a < 0:
        raise PatchError(f"{label}: start anchor not found")
    b = text.find(end, a + len(start))
    if b < 0:
        raise PatchError(f"{label}: end anchor not found")
    return text[:a] + replacement + text[b:]

def patch_build(repo: Path) -> None:
    p = repo / 'include' / 'smart_home_build.h'
    t = p.read_text()
    t = once(t, '#define SMART_HOME_VERSION "v9.9.1"', '#define SMART_HOME_VERSION "v10.0"', 'version')
    t = once(t, '#define SMART_HOME_PROFILE "display-experience-boot-persistence"', '#define SMART_HOME_PROFILE "workshop-os-graphite-ember"', 'profile')
    t = once(t, '#define SMART_HOME_BUILD_LABEL "Smart Home v9.9.1 Boot + Persistence RC1"', '#define SMART_HOME_BUILD_LABEL "Smart Home v10.0 Workshop OS Theme RC1"', 'build label')
    p.write_text(t)

def patch_hub(repo: Path) -> None:
    p = repo / 'src' / 'smart_hub.cpp'
    t = p.read_text()

    palette_start = 'static const uint16_t UI_BG       = 0x0882; // #081017\n'
    palette_end = '\n\n// Smart Home v9.6.1 zero-blip compositor.'
    palette = '''static const uint16_t UI_BG       = 0x0020; // #050607 graphite black
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
'''
    t = replace_region(t, palette_start, palette_end, palette, 'graphite ember palette')

    card_start = 'static void uiCard(int16_t x, int16_t y, int16_t w, int16_t h,\n'
    card_end = '\nstatic void uiProgressBar('
    card_block = r'''static void uiCard(int16_t x, int16_t y, int16_t w, int16_t h,
                   uint16_t accent = UI_BORDER, bool strong = false) {
  tft.fillRoundRect(x + 2, y + 3, w, h, 11, 0x0000);
  tft.fillRoundRect(x, y, w, h, 11, strong ? UI_GLOW : UI_BORDER_2);
  tft.fillRoundRect(x + 1, y + 1, w - 2, h - 2, 10, strong ? UI_PANEL_3 : UI_PANEL);
  tft.drawRoundRect(x + 1, y + 1, w - 2, h - 2, 10, strong ? accent : UI_BORDER);
  if (accent != UI_BORDER) {
    tft.fillRoundRect(x + 1, y + 8, 3, h - 16, 2, accent);
    tft.fillCircle(x + w - 12, y + 12, strong ? 3 : 2, accent);
  }
}

static void uiPanelFill(int16_t x, int16_t y, int16_t w, int16_t h) {
  tft.fillRoundRect(x, y, w, h, 9, UI_PANEL_2);
  tft.drawRoundRect(x, y, w, h, 9, UI_BORDER_2);
}

static void uiPill(int16_t x, int16_t y, int16_t w,
                   const char* text, uint16_t color) {
  tft.fillRoundRect(x, y, w, 20, 10, UI_PANEL_3);
  tft.drawRoundRect(x, y, w, 20, 10, color);
  tft.fillCircle(x + 10, y + 10, 3, color);
  uiDrawFit(text,x+18,y+10,w-24,FONT_SMALL,ML_DATUM,color,UI_PANEL_3);
}

static void uiSectionLabel(int16_t x, int16_t y, const char* label,
                           uint16_t accent, int16_t maxPx=180) {
  tft.fillRoundRect(x, y + 3, 3, 12, 2, accent);
  uiDrawFit(label,x+9,y+9,maxPx,FONT_SMALL,ML_DATUM,UI_TEXT,UI_PANEL);
}

static void uiMetric(int16_t x, int16_t y, int16_t w, int16_t h,
                     const char* label, const char* value, uint16_t accent,
                     const char* sub = nullptr) {
  uiCard(x, y, w, h, UI_BORDER, false);
  uiDrawFit(label && *label ? label : "—",x+9,y+7,w-18,FONT_SMALL,TL_DATUM,UI_MUTED,UI_PANEL);
  uiDrawFit(value && *value ? value : "—",x+9,y+27,w-18,h>=58?FONT_BODY:FONT_SMALL,TL_DATUM,accent,UI_PANEL);
  if (sub && *sub && h >= 54)
    uiDrawFit(sub,x+9,y+h-15,w-18,FONT_SMALL,TL_DATUM,UI_DIM,UI_PANEL);
}
'''
    t = replace_region(t, card_start, card_end, card_block, 'card system')

    page_accent_old = '''static uint16_t uiPageAccent(uint8_t page) {
  static const uint16_t accents[4] = { UI_ORANGE, UI_CYAN, UI_BLUE, UI_PURPLE };
  return accents[page < 4 ? page : 0];
}
'''
    page_accent_new = '''static uint16_t uiPageAccent(uint8_t page) {
  (void)page;
  return UI_ORANGE;
}
'''
    t = once(t, page_accent_old, page_accent_new, 'single accent system')

    header_start = 'static void drawHeader(const char* title, const char* right, uint8_t page) {'
    header_end = '\nstatic void uiNavIcon('
    header = r'''static void uiBackdrop() {
  const int16_t W=tft.width(), H=hubContentBottom();
  for (int16_t y=52; y<H; y+=48) tft.drawFastHLine(0,y,W,0x0841);
  for (int16_t x=24; x<W; x+=64) tft.drawFastVLine(x,40,H-40,0x0841);
  tft.drawFastHLine(10,44,58,UI_GLOW);
  tft.drawFastHLine(W-68,44,58,UI_GLOW);
  tft.fillCircle(68,44,2,UI_ORANGE);
  tft.fillCircle(W-68,44,2,UI_ORANGE);
}

static void drawHeader(const char* title, const char* right, uint8_t page) {
  const int16_t W = tft.width(), HH = hubHeaderH();
  const uint16_t accent = uiPageAccent(page);
  uiBackdrop();
  tft.fillRect(0, 0, W, HH, UI_BG);
  tft.fillRoundRect(8, 6, 27, 25, 7, UI_GLOW);
  tft.drawRoundRect(8, 6, 27, 25, 7, UI_ORANGE);
  uiDrawFit("W", 16, 18, 10, FONT_BODY, MC_DATUM, UI_TEXT, UI_GLOW);
  uiDrawFit("H", 26, 18, 10, FONT_SMALL, MC_DATUM, UI_ORANGE, UI_GLOW);
  uiDrawFit(title ? title : "SMART HOME", 43, 15, hubLandscape() ? 226 : 142,
            FONT_BODY, ML_DATUM, UI_TEXT, UI_BG);
  uiDrawFit("WORKSHOP OS", 43, 28, hubLandscape() ? 180 : 110,
            FONT_SMALL, ML_DATUM, UI_MUTED, UI_BG);
  char clockText[12]; uiClockText(clockText, sizeof(clockText));
  if (right && *right) {
    const bool bad=!strcmp(right,"OFFLINE") || !strcmp(right,"CHECK");
    const bool warn=!strcmp(right,"PAUSED") || !strcmp(right,"ATTENTION");
    const uint16_t stateC=bad?UI_RED:(warn?UI_AMBER:accent);
    tft.fillCircle(W - 15, clockText[0] ? 10 : 18, 3, stateC);
    uiDrawFit(right, W - 23, clockText[0] ? 10 : 18,
              hubLandscape() ? 130 : 76, FONT_SMALL, MR_DATUM, stateC, UI_BG);
  }
  if (clockText[0]) uiDrawFit(clockText, W - 12, 27, 64, FONT_SMALL, MR_DATUM, UI_DIM, UI_BG);
  tft.drawFastHLine(8, HH - 1, W - 16, UI_BORDER_2);
  tft.drawFastHLine(8, HH - 1, hubLandscape() ? 68 : 48, accent);
}

'''
    t = replace_region(t, header_start, header_end, header, 'header + backdrop')

    nav_start = 'static void uiBottomNav(uint8_t active, const char* nextPage) {'
    nav_end = '\n\nstatic void uiActionButton('
    nav = r'''static void uiBottomNav(uint8_t active, const char* nextPage) {
  (void)nextPage;
  const int16_t y = tft.height() - hubNavH();
  tft.fillRect(0, y, tft.width(), hubNavH(), UI_BG);
  tft.drawFastHLine(8, y, tft.width() - 16, UI_BORDER_2);
  static const char* labels[] = { "HOME", "PRINTER", "WORKSHOP", "MORE" };
  for (uint8_t i = 0; i < 4; i++) {
    HubRect r = hubNavRect(i);
    const bool selected=i==active;
    const uint16_t c = selected ? UI_ORANGE : UI_MUTED;
    if (selected) {
      tft.fillRoundRect(r.x + 6, r.y + 4, r.w - 12, r.h - 8, 9, UI_PANEL_3);
      tft.drawRoundRect(r.x + 6, r.y + 4, r.w - 12, r.h - 8, 9, UI_GLOW);
      tft.fillRoundRect(r.x + r.w / 2 - 11, r.y + 3, 22, 3, 2, UI_ORANGE);
    }
    uiNavIcon(r.x + r.w / 2, r.y + 15, i, c);
    uiDrawFit(labels[i], r.x + r.w / 2, r.y + 30, r.w - 8,
              FONT_SMALL, TC_DATUM, c, selected ? UI_PANEL_3 : UI_BG);
  }
}

static void uiActionButton(const HubRect& r, const char* label, uint16_t accent, bool filled=false) {
  const int16_t h = r.h < 44 ? 44 : r.h;
  const bool primary=filled || accent==UI_ORANGE || accent==UI_AMBER;
  const uint16_t edge=primary?UI_ORANGE:UI_BORDER;
  const uint16_t bg=filled?UI_ORANGE:UI_PANEL_2;
  tft.fillRoundRect(r.x + 1, r.y + 2, r.w, h, 10, 0x0000);
  tft.fillRoundRect(r.x, r.y, r.w, h, 10, bg);
  tft.drawRoundRect(r.x, r.y, r.w, h, 10, edge);
  if (!filled) {
    tft.fillRoundRect(r.x + 7, r.y + h / 2 - 8, 3, 16, 2, edge);
    if(primary)tft.fillCircle(r.x+r.w-11,r.y+10,2,UI_ORANGE);
  }
  uiDrawFit(label, r.x + r.w / 2 + (filled ? 0 : 2), r.y + h / 2,
            r.w - 24, FONT_SMALL, MC_DATUM, filled ? UI_BG : (primary?UI_ORANGE:UI_TEXT), bg);
}
'''
    t = replace_region(t, nav_start, nav_end, nav, 'nav/action system')

    material_start = 'static void uiMaterialSlot(const HubRect& r,const AmsTray* tr,bool active,uint8_t index,bool compact) {'
    material_end = '\nstatic void drawAmsCompact('
    material = r'''static void uiMaterialSlot(const HubRect& r,const AmsTray* tr,bool active,uint8_t index,bool compact) {
  const bool present=tr&&tr->present;
  const uint16_t filament=present?(tr->colorRgb565?tr->colorRgb565:UI_MUTED):UI_BORDER;
  tft.fillRoundRect(r.x,r.y,r.w,r.h,8,active?UI_PANEL_3:UI_PANEL_2);
  tft.drawRoundRect(r.x,r.y,r.w,r.h,8,active?UI_ORANGE:UI_BORDER_2);
  if(active)tft.fillRoundRect(r.x+3,r.y+6,3,r.h-12,2,UI_ORANGE);
  if(compact){
    uiSpoolScaled(r.x+18,r.y+r.h/2,filament,active,present?tr->remain:-1,10);
    char slot[6];snprintf(slot,sizeof(slot),"A%u",(unsigned)(index+1));
    uiDrawFit(slot,r.x+33,r.y+8,r.w-40,FONT_SMALL,TL_DATUM,active?UI_ORANGE:UI_MUTED,active?UI_PANEL_3:UI_PANEL_2);
    uiDrawFit(present&&tr->type[0]?tr->type:"EMPTY",r.x+33,r.y+22,r.w-40,FONT_SMALL,TL_DATUM,present?UI_TEXT:UI_MUTED,active?UI_PANEL_3:UI_PANEL_2);
    char remain[12];if(present&&tr->remain>=0)snprintf(remain,sizeof(remain),"%d%%",(int)tr->remain);else strlcpy(remain,"—",sizeof(remain));
    uiDrawFit(remain,r.x+r.w-7,r.y+r.h-7,r.w-40,FONT_SMALL,BR_DATUM,active?UI_ORANGE:UI_DIM,active?UI_PANEL_3:UI_PANEL_2);
  }else{
    const int16_t cx=r.x+r.w/2;
    uiSpoolScaled(cx,r.y+31,filament,active,present?tr->remain:-1,12);
    uiDrawFit(present&&tr->type[0]?tr->type:"EMPTY",cx,r.y+50,r.w-10,FONT_SMALL,TC_DATUM,present?UI_TEXT:UI_MUTED,active?UI_PANEL_3:UI_PANEL_2);
    char remain[12];if(present&&tr->remain>=0)snprintf(remain,sizeof(remain),"%d%%",(int)tr->remain);else strlcpy(remain,"—",sizeof(remain));
    uiDrawFit(remain,cx,r.y+r.h-8,r.w-10,FONT_SMALL,BC_DATUM,active?UI_ORANGE:UI_DIM,active?UI_PANEL_3:UI_PANEL_2);
  }
}

'''
    t = replace_region(t, material_start, material_end, material, 'material cards')

    t = t.replace('uiCard(r.x,r.y,r.w,r.h,UI_PURPLE,false);uiSectionLabel(r.x+10,r.y+8,"MATERIALS",UI_PURPLE,r.w-28);',
                  'uiCard(r.x,r.y,r.w,r.h,UI_BORDER,false);uiSectionLabel(r.x+10,r.y+8,"MATERIALS",UI_ORANGE,r.w-28);')
    t = t.replace('uiDrawFit("Advanced diagnostics in browser",18,416,W-36,FONT_SMALL,BL_DATUM,UI_BLUE,UI_PANEL);',
                  'uiDrawFit("Advanced diagnostics in browser",18,416,W-36,FONT_SMALL,BL_DATUM,UI_ORANGE,UI_PANEL);')

    p.write_text(t)

def patch_splash(repo: Path) -> None:
    p = repo / 'src' / 'display_ui.cpp'
    t = p.read_text()
    start = '  // Smart Home v9.9.1: workshop-OS boot splash. This is deliberately\n'
    end = '\n}\n\n// Repaint helper:'
    splash = r'''  // Smart Home v10: Graphite + Ember boot identity. The composition is
  // procedural so it is crisp at 320x480, rotation-safe, and carries no bitmap
  // decoder or flash-memory penalty.
  {
    const int16_t sw = uiW();
    const int16_t sh = uiH();
    const bool landscape = sw > sh;
    const int16_t cx = sw / 2;
    const uint16_t bg=0x0020, panel=0x0862, panel2=0x10A3, border=0x2966;
    const uint16_t orange=0xFBC0, orange2=0xFC43, glow=0x38E0;
    const uint16_t text=0xF7BE, dim=0xA576, muted=0x6BAF, healthy=0x3E8F;
    tft.fillScreen(bg);

    for(int16_t y=32;y<sh;y+=48)tft.drawFastHLine(0,y,sw,0x0841);
    for(int16_t x=24;x<sw;x+=64)tft.drawFastVLine(x,0,sh,0x0841);
    const int16_t markY=landscape?58:105;
    tft.drawCircle(cx,markY,58,glow);tft.drawCircle(cx,markY,43,border);
    tft.drawFastHLine(14,markY,sw/2-70,glow);tft.drawFastHLine(cx+70,markY,sw/2-84,glow);
    tft.fillCircle(14,markY,2,orange);tft.fillCircle(sw-14,markY,2,orange);

    tft.fillRoundRect(cx-34,markY-34,68,68,18,glow);
    tft.fillRoundRect(cx-30,markY-30,60,60,16,orange);
    tft.drawRoundRect(cx-30,markY-30,60,60,16,orange2);
    tft.setTextDatum(MC_DATUM);setFont(tft,FONT_LARGE);
    tft.setTextColor(text,orange);tft.drawString("W",cx-7,markY);
    setFont(tft,FONT_BODY);tft.setTextColor(text,orange);tft.drawString("H",cx+17,markY+4);

    const int16_t titleY=landscape?112:180;
    setFont(tft,FONT_BODY);tft.setTextColor(text,bg);tft.drawString("WAVESHARE",cx-32,titleY);
    tft.setTextColor(orange,bg);tft.drawString("HOME",cx+72,titleY);
    setFont(tft,FONT_SMALL);tft.setTextColor(dim,bg);tft.drawString("W  O  R  K  S  H  O  P     O  S",cx,titleY+24);
    tft.setTextColor(muted,bg);tft.drawString(SMART_HOME_VERSION,cx,titleY+45);

    uint8_t bootSlot = rotState.displayIndex < MAX_PRINTERS ? rotState.displayIndex : 0;
    const PrinterConfig& bootCfg = printers[bootSlot].config;
    const char* bootPrinter = bootCfg.name[0] ? bootCfg.name :
                              (bootCfg.serial[0] ? bootCfg.serial : "Local printer");
    char printerLine[64];snprintf(printerLine,sizeof(printerLine),"%s",bootPrinter);utf8TrimPartial(printerLine);

    const int16_t artY=landscape?170:267;
    const int16_t artX=landscape?(sw-178):cx-44;
    tft.drawRoundRect(artX,artY-28,88,62,7,border);
    tft.drawRect(artX+14,artY-17,60,37,muted);
    tft.drawFastHLine(artX+20,artY+15,48,orange);
    tft.fillTriangle(artX+37,artY+14,artX+44,artY,artX+51,artY+14,orange);
    tft.fillRoundRect(artX+8,artY-40,72,12,5,panel2);
    for(uint8_t i=0;i<4;i++){tft.fillCircle(artX+18+i*17,artY-34,4,i==0?orange:muted);tft.fillCircle(artX+18+i*17,artY-34,2,bg);}

    const int16_t plateY=landscape?190:344;
    tft.fillRoundRect(cx-(landscape?92:118),plateY-16,landscape?184:236,34,9,panel);
    tft.drawRoundRect(cx-(landscape?92:118),plateY-16,landscape?184:236,34,9,glow);
    setFont(tft,FONT_BODY);tft.setTextColor(text,panel);tft.drawString(printerLine,cx,plateY-1);
    tft.fillCircle(cx-(landscape?80:106),plateY+10,3,healthy);
    setFont(tft,FONT_SMALL);tft.setTextColor(orange,panel);tft.drawString("CONFIGURATION RETAINED",cx+10,plateY+10);

    const int16_t railY=landscape?(sh-39):(sh-75);const int16_t railX=landscape?28:34;const int16_t railW=sw-railX*2;
    tft.fillRoundRect(railX,railY,railW,8,4,panel2);tft.drawRoundRect(railX,railY,railW,8,4,border);
    tft.fillRoundRect(railX,railY,(railW*76)/100,8,4,orange);tft.fillCircle(railX+(railW*76)/100-3,railY+4,3,orange2);
    setFont(tft,FONT_SMALL);tft.setTextColor(text,bg);tft.drawString("Starting local control plane...",cx,railY+24);
    if(!landscape){tft.setTextColor(muted,bg);tft.drawString("Recovery ready   |   settings preserved",cx,sh-20);}
#if PANEL_REQUIRES_AXS_FRAME_SPRITE
    flushFrame();
#endif
  }
'''
    t = replace_region(t, start, end, splash, 'v10 splash')
    p.write_text(t)

def patch_browser(repo: Path) -> None:
    p=repo/'web'/'app.css'; t=p.read_text()
    marker='/* Smart Home v10 Workshop OS Graphite + Ember parity */'
    if marker not in t:
        t += r'''

/* Smart Home v10 Workshop OS Graphite + Ember parity */
.v98-device-canvas,.v99-head,.v98-nav{background:#050607!important}
.v98-device-canvas{border-color:#24282d!important;box-shadow:0 22px 44px rgba(0,0,0,.46),0 0 0 1px #383d43!important}
.v99-head{border-bottom-color:#21252a!important}
.v99-head>b{background:#3a1d05!important;border:1px solid #ff7a00!important;color:#f4f4f2!important}
.v99-head>strong{letter-spacing:.045em!important}.v99-head>small{color:#6d747d!important}
.v99-hero,.v99-materials,.v99-status,.v99-device,.v99-custom,.v99-health,.v99-moregrid>div,.v98-metric{background:#0b0d10!important;border-color:#292e34!important;box-shadow:0 3px 9px rgba(0,0,0,.18)}
.v99-hero:before{background:#ff7a00!important}.v99-hero.tone-red:before{background:#ff5a5f!important}.v99-hero.tone-amber:before{background:#ffb44a!important}
.v99-hero-copy em,.tone-orange .v99-hero-copy em{color:#ff7a00!important}.v99-hero-copy span,.v99-section span,.v99-mat span{color:#a7adb5!important}
.v99-progress{background:#171b20!important}.v99-progress i{background:#ff7a00!important}
.v99-mat{background:#111418!important;border-color:#292e34!important}.v99-mat.active{border-color:#ff7a00!important;box-shadow:inset 3px 0 #ff7a00!important}
.v99-actions button{background:#111418!important;border-color:#292e34!important;color:#f4f4f2!important}.v99-actions button:first-child{border-color:#ff7a00!important;color:#ff7a00!important}
.v98-nav{border-top-color:#21252a!important}.v98-nav button{color:#6d747d!important}.v98-nav button.active{border-color:#3a1d05!important;background:#171b20!important;color:#ff7a00!important;box-shadow:inset 0 2px #ff7a00}
.v99-moregrid .purple,.v99-moregrid .blue,.v99-moregrid .orange{color:#ff7a00!important}.v99-device em,.v99-custom em{color:#ff7a00!important}
.v99-section b,.v99-moregrid b{color:#f4f4f2!important}
'''
    p.write_text(t)

def verify(repo: Path) -> None:
    build=(repo/'include'/'smart_home_build.h').read_text()
    hub=(repo/'src'/'smart_hub.cpp').read_text()
    display=(repo/'src'/'display_ui.cpp').read_text()
    css=(repo/'web'/'app.css').read_text()
    web=(repo/'src'/'web_server.cpp').read_text()
    focal=(repo/'src'/'button_touch_focaltech.cpp').read_text()
    for n in ['#define SMART_HOME_VERSION "v10.0"','Workshop OS Theme RC1','workshop-os-graphite-ember']:
        if n not in build: raise PatchError('missing v10 identity: '+n)
    for n in ['UI_PANEL_3','UI_GLOW','uiBackdrop','W  O  R  K  S  H  O  P','CONFIGURATION RETAINED']:
        if n not in (hub+display): raise PatchError('missing visual invariant: '+n)
    for n in ['static const uint16_t UI_ORANGE   = 0xFBC0','return UI_ORANGE;','Workshop OS Graphite + Ember parity']:
        if n not in (hub+css): raise PatchError('missing theme invariant: '+n)
    for n in ['doc["hasAccessCode"]','savePrinterConfig(i)','NVS / OTA-preserved']:
        if n not in web: raise PatchError('v9.9.1 retention lost: '+n)
    if 'TouchEvent::Pressed' not in focal or 'ft6336RecoverBus' not in focal:
        raise PatchError('touch reliability foundation lost')
    a=web.index('static void handleRecoveryPage()'); b=web.index('static void handleRecoveryStatus()'); recovery=web[a:b]
    if 'recoverySha256HexArrayBuffer' not in recovery or 'crypto.subtle' in recovery:
        raise PatchError('Safari-safe recovery foundation lost')

def apply(repo: Path) -> None:
    patch_build(repo); patch_hub(repo); patch_splash(repo); patch_browser(repo); verify(repo)

def main() -> int:
    ap=argparse.ArgumentParser(); ap.add_argument('--repo',default='.'); ap.add_argument('--apply',action='store_true'); args=ap.parse_args()
    if not args.apply:
        print('Smart Home v10 Workshop OS theme patch ready. Use --apply.'); return 0
    apply(Path(args.repo).resolve()); print('Smart Home v10 Workshop OS Theme applied'); return 0

if __name__=='__main__': raise SystemExit(main())
