#!/usr/bin/env python3
"""Validate post-capture Workshop OS 12 UI hardening."""
from __future__ import annotations
import argparse
from pathlib import Path

class ValidationError(RuntimeError):
    pass

def load(path: Path) -> str:
    if not path.is_file():
        raise ValidationError(f"missing {path}")
    return path.read_text(encoding="utf-8")

def block(text: str, signature: str) -> str:
    start=text.find(signature)
    if start<0 or text.find(signature,start+1)>=0:
        raise ValidationError(f"missing/non-unique block: {signature}")
    brace=text.find("{",start)
    if brace<0:
        raise ValidationError(f"opening brace missing: {signature}")
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
            if depth==0:
                return text[start:i+1]
        i+=1
    raise ValidationError(f"unterminated block: {signature}")

def need(text: str, needle: str, label: str) -> None:
    if needle not in text:
        raise ValidationError(f"{label}: missing {needle}")

def forbid(text: str, needle: str, label: str) -> None:
    if needle in text:
        raise ValidationError(f"{label}: forbidden {needle}")

def main() -> int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--repo",required=True)
    args=ap.parse_args()
    repo=Path(args.repo).resolve()
    hub=load(repo/"src"/"smart_hub.cpp")

    evidence=block(hub,"static void hubOs12EvidenceRow(")
    for marker in ("dotReserve","textW","r.y+25","r.y+r.h-7"):
        need(evidence,marker,"evidence row non-overlap")
    forbid(evidence,"BR_DATUM","evidence row stacked layout")

    info=block(hub,"static void hubUi13InfoRow(")
    need(info,"hubOs12EvidenceRow","info row shared layout")

    stepper=block(hub,"static void hubUi13StepperRow(")
    for marker in ("buttonW=44","controlStart","valueW","FONT_SMALL"):
        need(stepper,marker,"stepper long-value fit")

    home=block(hub,"static void drawHome(bool full)")
    need(home,"Add or sync evidence in Filament Inventory","Home actionable unknown")
    for forbidden in ("matchSpoolByColor","matchSpoolByMaterial","activeTray"):
        forbid(home,forbidden,"Home authority")

    workshop=block(hub,"static void drawWorkshop(bool full)")
    for marker in (
        "Add print requirements and inventory evidence",
        "Confirm canonical placement in Filament Inventory",
        "No authoritative attention evidence",
    ):
        need(workshop,marker,"Workshop next-step guidance")
    for forbidden in ("matchSpoolByColor","matchSpoolByMaterial","activeTray"):
        forbid(workshop,forbidden,"Workshop authority")

    need(hub,"static const char* hubOs12CompactTimezoneLabel()","compact timezone helper")
    compact=block(hub,"static const char* hubOs12CompactTimezoneLabel()")
    need(compact,"strchr(full,')')","compact timezone prefix")
    need(compact,"sizeof(compact)","compact timezone bounds")

    system=block(hub,"static void drawSystem(bool full)")
    need(system,"hubOs12CompactTimezoneLabel()","System timezone fit")
    need(system,'"Runtime · candidate · verification"',"System release wording")

    date=block(hub,"static void drawUi13DateTime()")
    need(date,"hubOs12CompactTimezoneLabel()","Date & Time compact timezone")

    update=block(hub,"static void drawUi13SoftwareUpdate()")
    for marker in (
        "WORKSHOP_OS_RELEASE_VERSION",
        '"RUNTIME BUILD"',
        '"Release State"',
        '"Candidate"',
        '"Physical acceptance required"',
        '"Reconstruction Base"',
        '"Not an acceptance claim"',
    ):
        need(update,marker,"Software Update truth model")
    forbid(update,'"INSTALLED"',"Software Update truth model")
    forbid(update,"Install Now","Software Update authority")

    network=block(hub,"static void drawUi13Network()")
    need(network,'wifi?ip.c_str():"No active network connection"',"Network IP placement")

    media=block(hub,"static void drawOs12Media()")
    for marker in ("Tap value to test speaker","Tap row to sample input","Tap row to open motion test"):
        need(media,marker,"Media affordance")

    recorder=block(hub,"static void drawOs12Recorder()")
    for marker in ("Tap to sample live input","Tap to record · 5 sec maximum","Record audio first"):
        need(recorder,marker,"Recorder affordance")

    video=block(hub,"static void drawOs12VideoViewer()")
    need(video,'"Stop & Back"',"Video explicit exit")
    need(video,'"Stop & Back returns to Media"',"Video exit guidance")

    # Touch dispatch is injected into the reconstructed source by an earlier
    # layer and its concrete function name varies across historical bases.
    # Validate the exact action wiring globally instead of assuming a stale
    # function signature.
    need(hub,"media.sampleMicrophone(millis())","Recorder microphone action")
    need(hub,"media.startRecording(5000U,millis())","Recorder record action")
    need(hub,"media.playRecording(millis())","Recorder playback action")

    # Preserve global product invariants.
    for forbidden in ("matchSpoolByColor","matchSpoolByMaterial","WORKSHOP_OS_TEMP_NO_CODE_LAN"):
        forbid(hub,forbidden,"whole-device authority")

    print("PASS: post-capture WS350 UI hardening fixes layout robustness, release truth, recorder action mapping, and explicit media affordances")
    return 0

if __name__=="__main__":
    try:
        raise SystemExit(main())
    except ValidationError as exc:
        raise SystemExit(f"FAIL: {exc}") from exc
