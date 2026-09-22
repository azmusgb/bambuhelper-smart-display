#!/usr/bin/env python3
"""Validate the final Workshop OS 12 whole-device visual overhaul."""
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

def need(text:str,needle:str,label:str):
    if needle not in text: raise ValidationError(f"{label}: missing {needle}")

def forbid(text:str,needle:str,label:str):
    if needle in text: raise ValidationError(f"{label}: forbidden {needle}")

def main()->int:
    ap=argparse.ArgumentParser();ap.add_argument("--repo",required=True);a=ap.parse_args()
    repo=Path(a.repo).resolve();hub=load(repo/"src"/"smart_hub.cpp")

    for marker in (
        "OS12V_BG","OS12V_SURFACE","OS12V_SURFACE2","OS12V_TEXT","OS12V_MUTED",
        "OS12V_ACCENT","OS12V_GREEN","OS12V_AMBER","OS12V_RED","OS12V_RADIUS"
    ): need(hub,marker,"visual palette")

    header=block(hub,"static void drawHeader(")
    for marker in ("OS12V_BG","OS12V_TEXT","ONLINE","OFFLINE","OS12V_LINE"): need(header,marker,"header")

    nav=block(hub,"static void uiBottomNav(")
    for marker in ('{"Home","Printer","Workshop","More"}',"OS12V_SURFACE2","OS12V_ACCENT"): need(nav,marker,"bottom navigation")

    action=block(hub,"static void hubV1125Action(")
    for marker in ("OS12V_SURFACE2","OS12V_RED","OS12V_ACCENT"): need(action,marker,"actions")

    for sig in ("static void hubOs12RowSurface(","static void hubOs12NavRow(","static void hubOs12EvidenceRow(",
                "static void hubUi13ToggleRow(","static void hubUi13StepperRow("):
        b=block(hub,sig)
        need(b,"OS12V_",sig)

    home=block(hub,"static void drawHome(bool full)")
    for marker in ('drawHeader("Home",state,0)','"CURRENT PRINT"','"FILAMENT INVENTORY"','"No authoritative inventory evidence"'):
        need(home,marker,"Home")
    for forbidden in ("matchSpoolByColor","matchSpoolByMaterial","resolveSpool"):
        forbid(home,forbidden,"Home authority")

    workshop=block(hub,"static void drawWorkshop(bool full)")
    for marker in ('drawHeader("Workshop","INVENTORY",2)','"PRINT READINESS"','"Undetermined"','"LOADED SPOOLS"','"Canonical placement unknown"','"ATTENTION"'):
        need(workshop,marker,"Workshop")
    for forbidden in ("matchSpoolByColor","matchSpoolByMaterial","resolveSpool"):
        forbid(workshop,forbidden,"Workshop authority")

    more=block(hub,"static void drawMore(bool full)")
    for marker in ('drawHeader("More"', '"Display & Appearance"','"Sound & Media"','"Network"','"System"'):
        need(more,marker,"More")

    system=block(hub,"static void drawSystem(bool full)")
    for marker in ('drawHeader("System"', '"Device Health"','"Printer & Power"','"Date & Time"','"Software Update"','"Local Portal"'):
        need(system,marker,"System")
    forbid(system,"securityPortalCode()","System secret boundary")

    date=block(hub,"static void drawUi13DateTime()")
    for marker in ('"Time Zone"','"24-Hour Clock"','"Date Format"','"Use - / + to change"'):
        need(date,marker,"Date & Time")

    update=block(hub,"static void drawUi13SoftwareUpdate()")
    for marker in ('"Release State"','"Candidate"','"Physical acceptance required"','"Only exact validated artifacts"'):
        need(update,marker,"Software Update")
    for marker in ("Install Now","Download & Install","0x0"):
        forbid(update,marker,"Software Update authority")

    for sig in ("static void drawOs12Media()","static void drawOs12Recorder()","static void drawOs12VideoViewer()"):
        b=block(hub,sig);need(b,"OS12V_BG" if sig!="static void drawOs12VideoViewer()" else "OS12V_",sig)

    # Whole-source invariants: visual work must not create inventory inference or
    # bypass the existing printer/security authority.
    for forbidden in ("matchSpoolByColor","matchSpoolByMaterial","WORKSHOP_OS_TEMP_NO_CODE_LAN"):
        forbid(hub,forbidden,"whole-device authority")

    print("PASS: Workshop OS 12 final visual overhaul palette, hierarchy, touch components, truth boundaries and major surfaces are coherent")
    return 0

if __name__=="__main__":
    try: raise SystemExit(main())
    except ValidationError as exc: raise SystemExit(f"FAIL: {exc}") from exc
