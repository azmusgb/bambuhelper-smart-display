#!/usr/bin/env python3
from __future__ import annotations
import argparse
from pathlib import Path

class ValidationError(RuntimeError): pass

def load(path:Path)->str:
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

def req(h:str,n:str,l:str):
    if n not in h: raise ValidationError(f"{l}: missing {n}")

def forbid(h:str,n:str,l:str):
    if n in h: raise ValidationError(f"{l}: forbidden {n}")

def main()->int:
    ap=argparse.ArgumentParser();ap.add_argument("--repo",required=True);a=ap.parse_args()
    hub=load(Path(a.repo).resolve()/"src"/"smart_hub.cpp")
    printer=block(hub,"static void drawPrinter(bool full)")
    for n in (
        "workshopPlatformState().configuredPrinterCount==0",
        "workshopPlatformPrinterPaused(os12Slot)",
        "workshopPlatformPrinterPrinting(os12Slot)",
        "workshopPlatformPrinterActive(os12Slot)",
        "workshopPlatformPrinterOnline(os12Slot)",
        'g_printerMode==HUB_PRINTER_STATUS',
        'g_printerMode==HUB_PRINTER_AMS',
        '"Printer-reported AMS telemetry"',
        '"Inventory identity and placement remain authoritative in Filament Inventory."',
        '"Commands remain pending until fresh printer telemetry confirms state."',
        "hubV1125Action(",
    ): req(printer,n,"Printer product surface")
    for n in ("matchSpoolByColor","matchSpoolByMaterial","resolveSpool"):
        forbid(printer,n,"Printer inventory boundary")

    media=block(hub,"static void drawOs12Media()")
    req(media,'"Built-in WS350 motion test"',"Media")
    req(media,'"Recorder"',"Media")
    forbid(media,"uiBottomNav(","Media child navigation")

    recorder=block(hub,"static void drawOs12Recorder()")
    for n in ('"Microphone"','"Live input activity"','"Recording"','"Playback"','"5 sec maximum"'):
        req(recorder,n,"Recorder")
    forbid(recorder,"Printer Camera","Recorder normal surface")
    forbid(recorder,"uiBottomNav(","Recorder child navigation")

    video=block(hub,"static void drawOs12VideoViewer()")
    for n in ('"Video Viewer"','"Built-in WS350 motion test"','"Stop"','"Pause"','"Resume"'):
        req(video,n,"Video Viewer")
    req(video,'hubV1125Action(hubUi13BackRect(),"Stop",C10_RED,true,true)',"Video destructive stop")
    forbid(video,"uiBottomNav(","Video child navigation")

    print("PASS: OS12 product surfaces preserve normalized state/authority while presenting coherent Printer and Media appliance UX")
    return 0

if __name__=="__main__":
    try: raise SystemExit(main())
    except ValidationError as exc: raise SystemExit(f"FAIL: {exc}") from exc
