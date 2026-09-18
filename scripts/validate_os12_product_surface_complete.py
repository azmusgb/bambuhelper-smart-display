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

    helper=block(hub,"static void hubOs12StatePanel(")
    for n in ("hubV1125Card","eyebrow","detail","color"): req(helper,n,"state panel")

    home=block(hub,"static void drawHome(bool full)")
    for n in (
        "workshopPlatformState().configuredPrinterCount>0",
        "workshopPlatformPrinterPaused(os12Slot)",
        "workshopPlatformPrinterPrinting(os12Slot)",
        "workshopPlatformPrinterOnline(os12Slot)",
        '"No authoritative inventory evidence"',
        '"No fresh printer evidence"',
    ): req(home,n,"Home")
    forbid(home,"const bool configured=isAnyPrinterConfigured()","Home normalized state")

    workshop=block(hub,"static void drawWorkshop(bool full)")
    for n in ('"Print Readiness"','"Undetermined"','"Canonical placement evidence unavailable"','"Filament Inventory device feed not authoritative here"'):
        req(workshop,n,"Workshop")
    for n in ("matchSpoolByColor","matchSpoolByMaterial","resolveSpool"): forbid(workshop,n,"Workshop inventory boundary")

    more=block(hub,"static void drawMore(bool full)")
    for n in ('drawHeader("More"','"Display & Appearance"','"Sound & Media"','"Network"','"Printer & Power"','"System"','workshopPlatformWifiOnline()'):
        req(more,n,"More")
    forbid(more,'drawHeader("Settings"',"More naming")

    system=block(hub,"static void drawSystem(bool full)")
    for n in ('"Device Health"','"Connectivity"','"Date & Time"','"Software Update"','workshopPlatformWifiOnline()'):
        req(system,n,"System")
    forbid(system,"securityPortalCode()","System root secret boundary")

    child_contracts={
        "static void drawUi13Display()":('"Display & Appearance"','"Brightness"','"Standby Brightness"','"Night Mode"'),
        "static void drawUi13AfterPrint()":('"After Print"','"Display Behavior"','"Finish Timeout"','"Animated Progress"'),
        "static void drawUi13Sound()":('"Sound & Media"','"Event Sounds"','"Touch Sounds"','"Media"'),
        "static void drawUi13Network()":('"Network"','"No active network connection"','"Local Hostname"','"Local Portal"'),
        "static void drawUi13PrinterPower()":('"Printer & Power"','"Fresh printer connection"','"No fresh printer connection"','"Automatic Power Off"'),
        "static void drawUi13PowerOptions()":('"Power Options"','"Unavailable"','"Advanced Setup"'),
        "static void drawUi13AutoOffConfirm()":('"Guarded automation"','"Automatic printer power-off"','"Cancel"','"Enable"'),
        "static void drawUi13DateTime()":('"Date & Time"','"Time Zone"','"24-Hour Time"','"Date Format"'),
        "static void drawUi13SoftwareUpdate()":('"Software Update"','"Candidate build · acceptance required"','"Install only exact validated candidate artifacts"'),
        "static void drawUi13Diagnostics()":('"Diagnostics"','"Touch"','"Recovery"','"Connectivity is not device-health proof"'),
        "static void drawUi12PortalAccess()":('"Local Portal"','"Authenticated local administration"','securityPortalCode()'),
    }
    for sig,needles in child_contracts.items():
        b=block(hub,sig)
        for n in needles:req(b,n,sig)

    print("PASS: OS12 Home/Workshop/More/System and child settings use completed product-surface/state contracts")
    return 0

if __name__=="__main__":
    try: raise SystemExit(main())
    except ValidationError as exc: raise SystemExit(f"FAIL: {exc}") from exc
