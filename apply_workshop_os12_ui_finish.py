#!/usr/bin/env python3
"""Apply Workshop OS 12 system-wide WS350 visual/interaction finish."""
from __future__ import annotations
import argparse
from pathlib import Path
import sys as _sys
from pathlib import Path as _Path
_here = _Path(__file__).resolve().parent
if str(_here) not in _sys.path:
    _sys.path.insert(0, str(_here))
from scripts.smart_home_patch_utils import PatchError


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
            if depth==0: return i+1
        i+=1
    raise PatchError(f"{label}: closing brace missing")

def replace_function(text: str, signature: str, replacement: str) -> str:
    start=text.find(signature)
    if start<0 or text.find(signature,start+1)>=0: raise PatchError(f"function missing/non-unique: {signature}")
    return text[:start]+replacement.strip()+text[braced_end(text,start,signature):]

TOKENS=r'''
static constexpr int16_t OS12_UI_RADIUS = 14;
static constexpr int16_t OS12_UI_RADIUS_SMALL = 10;
static constexpr int16_t OS12_UI_TOUCH_MIN = 44;
static constexpr int16_t OS12_UI_CONTROL_H = 44;
'''

CARD=r'''
static void hubV1125Card(const HubRect& r,uint16_t rail=UI_BORDER_2,bool strong=false) {
  const uint16_t bg=strong?C10_SURFACE_2:C10_SURFACE;
  tft.fillRoundRect(r.x,r.y,r.w,r.h,OS12_UI_RADIUS,bg);
  tft.drawRoundRect(r.x,r.y,r.w,r.h,OS12_UI_RADIUS,strong?C10_SURFACE_3:C10_SEPARATOR);
  const bool semantic=rail!=UI_BORDER_2 && rail!=UI_BORDER && rail!=W25_LINE;
  if(semantic)tft.fillCircle(r.x+r.w-16,r.y+16,4,rail);
}
'''

MODE_TABS=r'''
static void hubV1125ModeTabs() {
  static const char* labels[3]={"Status","AMS","Control"};
  const int16_t W=tft.width();
  HubRect group=hr(OS12_MARGIN_X,44,W-OS12_MARGIN_X*2,48);
  tft.fillRoundRect(group.x,group.y,group.w,group.h,OS12_UI_RADIUS,C10_SURFACE);
  tft.drawRoundRect(group.x,group.y,group.w,group.h,OS12_UI_RADIUS,C10_SEPARATOR);
  for(uint8_t i=0;i<3;i++) {
    HubRect r=hubV1125PrinterModeRect(i); const bool selected=g_printerMode==i;
    const uint16_t bg=selected?C10_SURFACE_3:C10_SURFACE;
    if(selected){tft.fillRoundRect(r.x+4,r.y+4,r.w-8,r.h-8,OS12_UI_RADIUS_SMALL,bg);tft.fillRoundRect(r.x+r.w/2-16,r.y+r.h-6,32,3,2,C10_ACCENT);}
    uiDrawFit(labels[i],r.x+r.w/2,r.y+r.h/2-1,r.w-18,FONT_BODY,MC_DATUM,selected?C10_TEXT:C10_MUTED,bg);
  }
}
'''

ACTION=r'''
static void hubV1125Action(const HubRect& r,const char* label,uint16_t c,bool enabled=true,bool destructive=false) {
  const uint16_t bg=enabled?C10_SURFACE_2:C10_SURFACE;
  const uint16_t border=!enabled?C10_SEPARATOR:(destructive?C10_RED:C10_SURFACE_3);
  const uint16_t text=!enabled?C10_MUTED:(destructive?C10_RED:C10_TEXT);
  tft.fillRoundRect(r.x,r.y,r.w,r.h,OS12_UI_RADIUS,bg);
  tft.drawRoundRect(r.x,r.y,r.w,r.h,OS12_UI_RADIUS,border);
  if(enabled)tft.fillCircle(r.x+18,r.y+r.h/2,4,destructive?C10_RED:c);
  uiDrawFit(label,r.x+r.w/2+6,r.y+r.h/2,r.w-46,FONT_BODY,MC_DATUM,text,bg);
}
'''

HEADER=r'''
static void drawHeader(const char* title,const char* right,uint8_t page) {
  const int16_t W=tft.width(),HH=hubHeaderH(); const bool online=WiFi.status()==WL_CONNECTED;
  const bool explicitState=right&&right[0]; tft.fillRect(0,0,W,HH,C10_BG);
  uiDrawFit(title?title:"Home",OS12_MARGIN_X,8,hubLandscape()?270:178,FONT_BODY,TL_DATUM,C10_TEXT,C10_BG);
  const char* state=explicitState?right:(online?"Online":"Offline");
  const uint16_t c=hubUi13HeaderStateColor(state,explicitState,online); const int16_t pw=hubLandscape()?112:96;
  tft.fillCircle(W-pw+5,18,4,c);uiDrawFit(state,W-OS12_MARGIN_X,18,pw-18,FONT_SMALL,MR_DATUM,c,C10_BG);
  tft.drawFastHLine(OS12_MARGIN_X,HH-1,W-OS12_MARGIN_X*2,C10_SEPARATOR);
  (void)hubV1125UiFingerprint(page);
}
'''

BOTTOM_NAV=r'''
static void uiBottomNav(uint8_t active,const char* nextPage) {
  (void)nextPage;const int16_t y=tft.height()-hubNavH(),W=tft.width();
  static const char* labels[4]={"Home","Printer","Workshop","More"};
  tft.fillRect(0,y,W,hubNavH(),C10_SURFACE);tft.drawFastHLine(0,y,W,C10_SEPARATOR);
  for(uint8_t i=0;i<4;i++){HubRect r=hubNavRect(i);const bool selected=i==active;const uint16_t c=selected?C10_ACCENT:C10_MUTED;
    if(selected)tft.fillRoundRect(r.x+9,r.y+4,r.w-18,r.h-8,OS12_UI_RADIUS,C10_SURFACE_2);
    const int16_t cx=r.x+r.w/2;hubV1125TabIcon(i,cx,r.y+16,c);
    uiDrawFit(labels[i],cx,r.y+34,r.w-12,FONT_SMALL,TC_DATUM,c,selected?C10_SURFACE_2:C10_SURFACE);
  }
}
'''

TELEMETRY=r'''
static void hubV1125TelemetryColumn(const HubRect& r,const BambuState& s) {
  hubV1125Card(r,s.connected?C10_GREEN:C10_ORANGE,false);
  uiDrawFit("Temperatures",r.x+14,r.y+12,r.w-28,FONT_SMALL,TL_DATUM,C10_MUTED,C10_SURFACE);
  const char* labels[3]={"Nozzle","Bed","Chamber"};char vals[3][14];
  if(s.connected){snprintf(vals[0],sizeof(vals[0]),"%.0f C",s.nozzleTemp);snprintf(vals[1],sizeof(vals[1]),"%.0f C",s.bedTemp);snprintf(vals[2],sizeof(vals[2]),"%.0f C",s.chamberTemp);}
  else for(uint8_t i=0;i<3;i++)strlcpy(vals[i],"--",sizeof(vals[i]));
  const int16_t top=r.y+34,row=(r.h-38)/3;
  for(uint8_t i=0;i<3;i++){if(i)tft.drawFastHLine(r.x+14,top+i*row,r.w-28,C10_SEPARATOR);uiDrawFit(labels[i],r.x+14,top+i*row+row/2,r.w/2-18,FONT_SMALL,ML_DATUM,C10_MUTED,C10_SURFACE);uiDrawFit(vals[i],r.x+r.w-14,top+i*row+row/2,r.w/2-18,FONT_BODY,MR_DATUM,s.connected?C10_TEXT:C10_MUTED,C10_SURFACE);}
}
'''

AMS_SLOT=r'''
static void hubV1125AmsSlot(const HubRect& r,const AmsTray* tr,bool active,uint8_t index) {
  const bool present=tr&&tr->present;const uint16_t bg=active?C10_SURFACE_3:C10_SURFACE;
  tft.fillRoundRect(r.x,r.y,r.w,r.h,OS12_UI_RADIUS,bg);tft.drawRoundRect(r.x,r.y,r.w,r.h,OS12_UI_RADIUS,active?C10_ACCENT:C10_SEPARATOR);
  if(active)tft.fillCircle(r.x+r.w-15,r.y+15,4,C10_ACCENT);
  char slot[8];snprintf(slot,sizeof(slot),"%u",(unsigned)(index+1));char remain[12];
  if(present&&tr->remain>=0)snprintf(remain,sizeof(remain),"%d%%",(int)tr->remain);else strlcpy(remain,"--",sizeof(remain));
  uiDrawFit(slot,r.x+12,r.y+10,28,FONT_BODY,TL_DATUM,active?C10_ACCENT:C10_MUTED,bg);uiDrawFit(remain,r.x+r.w-12,r.y+10,42,FONT_SMALL,TR_DATUM,present?C10_TEXT:C10_MUTED,bg);
  uint16_t filament=present?tr->colorRgb565:C10_SEPARATOR;if(present&&filament==0)filament=0x1082;uiSpoolScaled(r.x+r.w/2,r.y+49,filament,active,present?tr->remain:-1,13);
  uiDrawFit(present&&tr->type[0]?tr->type:"Empty",r.x+r.w/2,r.y+74,r.w-18,FONT_BODY,TC_DATUM,present?C10_TEXT:C10_MUTED,bg);
}
'''

ROW_SURFACE=r'''
static void hubOs12RowSurface(const HubRect& r) {
  tft.fillRoundRect(r.x,r.y,r.w,r.h,OS12_UI_RADIUS_SMALL,C10_SURFACE);
  tft.drawRoundRect(r.x,r.y,r.w,r.h,OS12_UI_RADIUS_SMALL,C10_SEPARATOR);
  tft.drawFastHLine(r.x+OS12_ROW_INSET_X,r.y+r.h-1,r.w-OS12_ROW_INSET_X*2,C10_SEPARATOR);
}
'''

NAV_ROW=r'''
static void hubOs12NavRow(const HubRect& r,const char* title,const char* detail,uint16_t valueColor=C10_MUTED) {
  hubOs12RowSurface(r);const int16_t rightPad=42;
  uiDrawFit(title,r.x+OS12_ROW_INSET_X,r.y+8,r.w-OS12_ROW_INSET_X-rightPad,FONT_BODY,TL_DATUM,C10_TEXT,C10_SURFACE);
  uiDrawFit(detail,r.x+OS12_ROW_INSET_X,r.y+r.h-9,r.w-OS12_ROW_INSET_X-rightPad,FONT_SMALL,BL_DATUM,valueColor,C10_SURFACE);
  const int16_t cx=r.x+r.w-18,cy=r.y+r.h/2;tft.drawLine(cx-4,cy-5,cx+1,cy,C10_MUTED);tft.drawLine(cx+1,cy,cx-4,cy+5,C10_MUTED);
}
'''

EVIDENCE_ROW=r'''
static void hubOs12EvidenceRow(const HubRect& r,const char* title,const char* value,const char* detail,uint16_t valueColor=C10_MUTED) {
  hubOs12RowSurface(r);const int16_t inset=OS12_ROW_INSET_X;const int16_t valueW=176;const int16_t detailX=r.x+inset+valueW+8;const int16_t detailW=r.x+r.w-inset-detailX;
  uiDrawFit(title,r.x+inset,r.y+7,r.w-inset*2,FONT_SMALL,TL_DATUM,C10_MUTED,C10_SURFACE);
  uiDrawFit(value,r.x+inset,r.y+r.h-10,valueW,FONT_BODY,BL_DATUM,valueColor,C10_SURFACE);
  uiDrawFit(detail,detailX,r.y+r.h-10,detailW,FONT_SMALL,BR_DATUM,C10_MUTED,C10_SURFACE);
}
'''

INFO_ROW=r'''
static void hubUi13InfoRow(const HubRect& r,const char* label,const char* value,const char* detail,uint16_t accent=C10_ACCENT) {
  hubOs12EvidenceRow(r,label,value,detail,accent);
}
'''

TOGGLE_ROW=r'''
static void hubUi13ToggleRow(const HubRect& r,const char* label,const char* detail,bool on,uint16_t accent=C10_ACCENT) {
  hubOs12RowSurface(r);const int16_t controlW=62;
  uiDrawFit(label,r.x+OS12_ROW_INSET_X,r.y+8,r.w-controlW-OS12_ROW_INSET_X*3,FONT_BODY,TL_DATUM,C10_TEXT,C10_SURFACE);
  uiDrawFit(detail,r.x+OS12_ROW_INSET_X,r.y+r.h-9,r.w-controlW-OS12_ROW_INSET_X*3,FONT_SMALL,BL_DATUM,C10_MUTED,C10_SURFACE);
  HubRect sw=hr(r.x+r.w-controlW-OS12_ROW_INSET_X,r.y+(r.h-34)/2,controlW,34);tft.fillRoundRect(sw.x,sw.y,sw.w,sw.h,17,on?accent:C10_SURFACE_3);tft.drawRoundRect(sw.x,sw.y,sw.w,sw.h,17,on?accent:C10_SEPARATOR);
  const int16_t d=26;const int16_t cx=on?(sw.x+sw.w-4-d/2):(sw.x+4+d/2);tft.fillCircle(cx,sw.y+sw.h/2,d/2,C10_TEXT);
}
'''

STEPPER_ROW=r'''
static void hubUi13StepperRow(const HubRect& r,const char* label,const char* value,const char* detail,uint16_t accent=C10_ACCENT) {
  hubOs12RowSurface(r);const int16_t buttonW=46,buttonH=44;
  uiDrawFit(label,r.x+OS12_ROW_INSET_X,r.y+7,r.w-230,FONT_SMALL,TL_DATUM,C10_MUTED,C10_SURFACE);uiDrawFit(detail,r.x+OS12_ROW_INSET_X,r.y+r.h-9,r.w-230,FONT_SMALL,BL_DATUM,C10_MUTED,C10_SURFACE);
  HubRect minus=hr(r.x+r.w-218,r.y+(r.h-buttonH)/2,buttonW,buttonH),plus=hr(r.x+r.w-buttonW-OS12_ROW_INSET_X,r.y+(r.h-buttonH)/2,buttonW,buttonH);
  tft.fillRoundRect(minus.x,minus.y,minus.w,minus.h,OS12_UI_RADIUS_SMALL,C10_SURFACE_2);tft.drawRoundRect(minus.x,minus.y,minus.w,minus.h,OS12_UI_RADIUS_SMALL,C10_SEPARATOR);
  tft.fillRoundRect(plus.x,plus.y,plus.w,plus.h,OS12_UI_RADIUS_SMALL,C10_SURFACE_2);tft.drawRoundRect(plus.x,plus.y,plus.w,plus.h,OS12_UI_RADIUS_SMALL,C10_SEPARATOR);
  uiDrawFit("-",minus.x+minus.w/2,minus.y+minus.h/2,minus.w-8,FONT_LARGE,MC_DATUM,accent,C10_SURFACE_2);uiDrawFit("+",plus.x+plus.w/2,plus.y+plus.h/2,plus.w-8,FONT_LARGE,MC_DATUM,accent,C10_SURFACE_2);
  uiDrawFit(value,minus.x+minus.w+OS12_ACTION_GAP,r.y+r.h/2,plus.x-minus.x-minus.w-OS12_ACTION_GAP*2,FONT_BODY,MC_DATUM,C10_TEXT,C10_SURFACE);
}
'''

def apply(repo: Path) -> None:
    path=repo/"src"/"smart_hub.cpp";text=load(path)
    # Keep finish tokens at namespace scope before every drawing primitive.
    # Merely finding the token text later in the file is insufficient in C++:
    # declarations must precede the functions that consume them.
    token_lines=tuple(line.strip() for line in TOKENS.strip().splitlines() if line.strip())
    for token in token_lines:
        count=text.count(token)
        if count>1: raise PatchError(f"duplicate OS12 UI finish token: {token}")
        if count==1: text=text.replace(token,"",1)
    anchor="namespace {\n"
    pos=text.find(anchor)
    if pos<0: raise PatchError("anonymous namespace anchor missing for UI finish tokens")
    pos+=len(anchor)
    text=text[:pos]+"\n"+TOKENS.strip()+"\n\n"+text[pos:]
    for signature,replacement in (
        ("static void hubV1125Card(",CARD),("static void hubV1125ModeTabs()",MODE_TABS),("static void hubV1125Action(",ACTION),
        ("static void hubV1125TelemetryColumn(",TELEMETRY),("static void hubV1125AmsSlot(",AMS_SLOT),("static void drawHeader(",HEADER),
        ("static void uiBottomNav(",BOTTOM_NAV),("static void hubOs12RowSurface(",ROW_SURFACE),("static void hubOs12NavRow(",NAV_ROW),
        ("static void hubOs12EvidenceRow(",EVIDENCE_ROW),("static void hubUi13InfoRow(",INFO_ROW),("static void hubUi13ToggleRow(",TOGGLE_ROW),
        ("static void hubUi13StepperRow(",STEPPER_ROW),
    ): text=replace_function(text,signature,replacement)
    text=text.replace('drawHeader("Settings",nullptr,3)','drawHeader("More",nullptr,3)')
    text=text.replace('"Camera Viewer"','"Video Viewer"').replace('"Media Lab"','"Recorder"')
    path.write_text(text,encoding="utf-8")
    print("Workshop OS 12 system-wide UI finish installed")

def main()->int:
    ap=argparse.ArgumentParser();ap.add_argument("--repo",required=True);ap.add_argument("--apply",action="store_true");args=ap.parse_args()
    if not args.apply: raise SystemExit("refusing to modify source without --apply")
    try: apply(Path(args.repo).resolve())
    except PatchError as exc: raise SystemExit(f"FAIL: {exc}") from exc
    return 0

if __name__=="__main__": raise SystemExit(main())
