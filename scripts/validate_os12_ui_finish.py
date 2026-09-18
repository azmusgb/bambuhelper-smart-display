#!/usr/bin/env python3
from __future__ import annotations
import argparse
from pathlib import Path

class ValidationError(RuntimeError): pass

def load(path: Path)->str:
    if not path.is_file(): raise ValidationError(f"missing {path}")
    return path.read_text(encoding="utf-8")

def block(text:str,signature:str)->str:
    start=text.find(signature)
    if start<0 or text.find(signature,start+1)>=0: raise ValidationError(f"missing/non-unique block: {signature}")
    brace=text.find("{",start)
    if brace<0: raise ValidationError(f"opening brace missing: {signature}")
    depth=0; string=None; escape=False; line=False; comment=False; i=brace
    while i<len(text):
        c=text[i]; n=text[i+1] if i+1<len(text) else ""
        if line:
            if c=="\n": line=False
        elif comment:
            if c=="*" and n=="/": comment=False; i+=1
        elif string:
            if escape: escape=False
            elif c=="\\": escape=True
            elif c==string: string=None
        elif c=="/" and n=="/": line=True; i+=1
        elif c=="/" and n=="*": comment=True; i+=1
        elif c in ('"',"'"): string=c
        elif c=="{": depth+=1
        elif c=="}":
            depth-=1
            if depth==0:return text[start:i+1]
        i+=1
    raise ValidationError(f"unterminated block: {signature}")

def require(text:str,needle:str,label:str)->None:
    if needle not in text: raise ValidationError(f"{label}: missing {needle}")

def forbid(text:str,needle:str,label:str)->None:
    if needle in text: raise ValidationError(f"{label}: forbidden {needle}")

def main()->int:
    ap=argparse.ArgumentParser();ap.add_argument("--repo",required=True);args=ap.parse_args()
    hub=load(Path(args.repo).resolve()/"src"/"smart_hub.cpp")

    for token in (
        "static constexpr int16_t OS12_UI_RADIUS = 14;",
        "static constexpr int16_t OS12_UI_RADIUS_SMALL = 10;",
        "static constexpr int16_t OS12_UI_TOUCH_MIN = 44;",
        "static constexpr int16_t OS12_UI_CONTROL_H = 44;",
    ): require(hub,token,"UI finish tokens")

    header=block(hub,"static void drawHeader(")
    require(header,"hubUi13HeaderStateColor","header semantic status")
    require(header,"tft.drawFastHLine(OS12_MARGIN_X,HH-1","header separator")

    nav=block(hub,"static void uiBottomNav(")
    require(nav,'labels[4]={"Home","Printer","Workshop","More"}',"root nav")
    require(nav,"tft.fillRoundRect(r.x+9,r.y+4","selected root nav")
    forbid(nav,'"Settings"',"root nav label")

    tabs=block(hub,"static void hubV1125ModeTabs()")
    require(tabs,'labels[3]={"Status","AMS","Control"}',"printer tabs")
    require(tabs,"32,3,2,C10_ACCENT","printer tab selection")

    action=block(hub,"static void hubV1125Action(")
    require(action,"destructive?C10_RED","action destructive semantics")
    require(action,"tft.drawRoundRect","action boundary")

    card=block(hub,"static void hubV1125Card(")
    require(card,"tft.drawRoundRect","card boundary")
    require(card,"semantic","card semantic rail")

    row=block(hub,"static void hubOs12RowSurface(")
    require(row,"C10_SURFACE","list-row surface")
    require(row,"tft.drawRoundRect","list-row boundary")

    toggle=block(hub,"static void hubUi13ToggleRow(")
    require(toggle,"controlW=62","toggle control")
    require(toggle,"d=26","toggle thumb")

    stepper=block(hub,"static void hubUi13StepperRow(")
    require(stepper,"buttonW=46,buttonH=44","stepper touch target")
    require(stepper,"tft.drawRoundRect","stepper boundary")

    telemetry=block(hub,"static void hubV1125TelemetryColumn(")
    require(telemetry,"C10_ORANGE","offline telemetry warning semantics")

    ams=block(hub,"static void hubV1125AmsSlot(")
    require(ams,"active?C10_ACCENT:C10_SEPARATOR","AMS selection boundary")

    for sig in ("static void drawHome(bool full)","static void drawPrinter(bool full)","static void drawWorkshop(bool full)","static void drawMore(bool full)","static void drawSystem(bool full)","static void drawOs12Media()","static void drawOs12Recorder()","static void drawOs12VideoViewer()"):
        if sig in hub:
            b=block(hub,sig)
            forbid(b,'"Settings"',f"{sig} stale Settings root label")

    for stale in ('"Camera Viewer"','"Media Lab"'):
        forbid(hub,stale,"media naming")

    print("PASS: OS12 WS350 shared UI primitives are visually coherent across roots, child views, buttons, tabs, media, telemetry and AMS")
    return 0

if __name__=="__main__":
    try: raise SystemExit(main())
    except ValidationError as exc: raise SystemExit(f"FAIL: {exc}") from exc
