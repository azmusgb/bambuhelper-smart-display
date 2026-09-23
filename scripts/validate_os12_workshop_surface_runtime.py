#!/usr/bin/env python3
"""Validate the OS12 Workshop runtime surface fix."""
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
    start = text.find(signature)
    if start < 0 or text.find(signature, start + 1) >= 0:
        raise ValidationError(f"missing/non-unique block: {signature}")
    brace = text.find("{", start)
    if brace < 0:
        raise ValidationError(f"opening brace missing: {signature}")
    depth = 0
    string = None
    escape = False
    line = False
    comment = False
    i = brace
    while i < len(text):
        c = text[i]
        n = text[i + 1] if i + 1 < len(text) else ""
        if line:
            if c == "\n":
                line = False
        elif comment:
            if c == "*" and n == "/":
                comment = False
                i += 1
        elif string:
            if escape:
                escape = False
            elif c == "\\":
                escape = True
            elif c == string:
                string = None
        elif c == "/" and n == "/":
            line = True
            i += 1
        elif c == "/" and n == "*":
            comment = True
            i += 1
        elif c in ('"', "'"):
            string = c
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return text[start:i + 1]
        i += 1
    raise ValidationError(f"unterminated block: {signature}")


def need(text: str, needle: str, label: str) -> None:
    if needle not in text:
        raise ValidationError(f"{label}: missing {needle}")


def forbid(text: str, needle: str, label: str) -> None:
    if needle in text:
        raise ValidationError(f"{label}: forbidden {needle}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    args = ap.parse_args()
    repo = Path(args.repo).resolve()
    hub = load(repo / "src" / "smart_hub.cpp")

    need(hub, '#include "workshop_inventory_service.h"', "Workshop inventory consumer include")

    action = block(hub, "static HubRect hubOs12WorkshopActionRect(")
    for marker in ("y=220", "h=44", "(W-2*m-g)/2"):
        need(action, marker, "Workshop visible action geometry")

    workshop = block(hub, "static void drawWorkshop(bool full)")
    for marker in (
        "workshopInventorySnapshot()",
        "hubOs12WorkshopHeaderState(inv)",
        '"PRINT READINESS"',
        '"LOADED SPOOLS"',
        '"ATTENTION"',
        "state.placementState",
        "state.readiness",
        "state.quantityVerificationRequired",
        "state.placementVerificationRequired",
        'inv.credentialConfigured?"Local Portal":"Set Up Inventory"',
        'inv.busy?"Refreshing":"Refresh"',
        "hubOs12WorkshopActionRect(0)",
        "hubOs12WorkshopActionRect(1)",
    ):
        need(workshop, marker, "Workshop functional surface")

    for forbidden in (
        'drawHeader("Workshop","INVENTORY"',
        'hubOs12EvidenceRow(readiness,"PRINT READINESS","Undetermined"',
        'hubOs12EvidenceRow(loaded,"LOADED SPOOLS","Unknown"',
        "activeTray",
        "matchSpoolByColor",
        "matchSpoolByMaterial",
        ".ams.",
    ):
        forbid(workshop, forbidden, "Workshop authority/runtime wiring")

    touch = block(hub, "if(cur==SCREEN_HUB_WORKSHOP){")
    for marker in (
        "workshopInventorySnapshot()",
        "hubOs12WorkshopActionRect(0).contains(x,y)",
        "workshopInventoryRequestRefresh()",
        "hubOs12WorkshopActionRect(1).contains(x,y)",
        "g_ui12SystemView=1",
        "setPage(SCREEN_HUB_SYSTEM)",
    ):
        need(touch, marker, "Workshop explicit action mapping")

    # Regression that escaped automated acceptance: the v11.25 handler retained
    # four invisible action zones after later renderers removed those buttons.
    for forbidden in (
        "hubWorkshopActionRect(",
        "requestLightCommand(",
        "g_toolsView=true",
        "setPage(SCREEN_HUB_PRINTER)",
    ):
        forbid(touch, forbidden, "Workshop hidden action regression")

    print(
        "PASS: Workshop surface uses authoritative device-feed state, exposes two visible "
        "44px actions, and has no stale hidden v11.25 touch zones"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ValidationError as exc:
        raise SystemExit(f"FAIL: {exc}") from exc
