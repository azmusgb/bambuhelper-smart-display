#!/usr/bin/env python3
"""Validate the focused physical WS350 product-polish layer."""
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
    hub = load(Path(args.repo).resolve() / "src" / "smart_hub.cpp")

    header = block(hub, "static void drawHeader(const char* title,const char* right,uint8_t page)")
    need(header, "if(explicitState)", "Header explicit-state contract")
    forbid(header, 'online?"ONLINE":"OFFLINE"', "Header must not invent irrelevant network badge")
    forbid(header, 'online?"Online":"Offline"', "Header must not invent irrelevant network badge")

    action = block(hub, "static bool hubOs12SecondaryActionLabel(const char* label)")
    for label in ("Local Portal", "After Print", "Printer Alerts", "Power Options", "Recorder"):
        need(action, f'"{label}"', "Secondary action vocabulary")

    nav = block(hub, "static void hubOs12NavIcon(const HubRect& badge,const char* title,uint16_t c)")
    for category in ("Display", "Sound", "Network", "Date", "Update", "Printer", "System"):
        need(nav, f'"{category}"', "Distinct settings pictogram contract")

    toggle = block(hub, "static void hubUi13ToggleRow(const HubRect& r,const char* label,const char* detail,bool on,uint16_t accent=C10_ACCENT)")
    need(toggle, "on?OS12V_BG:OS12V_MUTED", "Quiet OFF-toggle knob")

    home_decl = "static const char* hubOs12WorkshopReadinessLabel(\n    workshop::platform::InventoryReadinessState state);"
    color_decl = "static uint16_t hubOs12WorkshopReadinessColor(\n    workshop::platform::InventoryReadinessState state);"
    need(hub, home_decl, "Home readiness helper declaration")
    need(hub, color_decl, "Home readiness color declaration")
    if hub.find(home_decl) > hub.find("static void drawHome(bool full)"):
        raise ValidationError("Home readiness helper declaration must precede drawHome")
    if hub.find(color_decl) > hub.find("static void drawHome(bool full)"):
        raise ValidationError("Home readiness color declaration must precede drawHome")

    home = block(hub, "static void drawHome(bool full)")
    for marker in (
        "workshopInventorySnapshot()",
        'drawHeader("Home",nullptr,0)',
        "const bool active=printing||paused;",
        'HubRect hero=hr(OS12V_INSET,46,W-OS12V_INSET*2,active?78:64);',
        '"Ready for your next print"',
        '"Set up a printer"',
        '"More  >  System  >  Printer & Power"',
        "uiProgressBar(",
        "HubRect printerCard=",
        "HubRect inventoryCard=",
        '"PRINTER"',
        '"FILAMENT"',
        '"Inventory unavailable"',
        "inventoryState.freshness",
        "inventoryState.spoolCount",
        "inventoryState.loadedCount",
        "hubOs12WorkshopReadinessLabel",
    ):
        need(home, marker, "Home v2 state-adaptive glance hierarchy")
    forbid(home, "hubOs12EvidenceRow(", "Home v2 must not regress to stacked diagnostic evidence rows")
    forbid(home, '"CURRENT PRINT"', "Home v2 must not duplicate the print state as a diagnostic section")
    for forbidden in ("matchSpoolByColor", "matchSpoolByMaterial", "resolveSpool", "activeTray"):
        forbid(home, forbidden, "Home inventory authority")

    more = block(hub, "static void drawMore(bool full)")
    need(more, 'drawHeader("More",nullptr,3)', "More header focus")
    forbid(more, 'drawHeader("More",healthy?"HEALTHY":"CHECK"', "More must not present global health as page state")

    system = block(hub, "static void drawSystem(bool full)")
    need(system, 'drawHeader("System",healthy?"HEALTHY":"CHECK",3)', "System status vocabulary")
    need(system, '"Candidate channel · physical validation pending"', "System update summary")

    network = block(hub, "static void drawUi13Network()")
    need(network, 'wifi?"CONNECTED":"OFFLINE"', "Network status vocabulary")

    update = block(hub, "static void drawUi13SoftwareUpdate()")
    for marker in ("CURRENT VERSION", "Update Channel", "Physical validation pending", "Build Details", "Source · artifact · recovery identity"):
        need(update, marker, "User-facing update hierarchy")
    forbid(update, "Reconstruction Base", "Engineering provenance must not dominate update UI")
    forbid(update, "Not an acceptance claim", "Engineering disclaimer must not dominate update UI")
    forbid(update, "RUNTIME BUILD", "Engineering label must not dominate update UI")

    sound = block(hub, "static void drawUi13Sound()")
    need(sound, 'hubOs12NavRow(hubUi13RowRect(2),"Media"', "Media affordance")

    print(
        "PASS: physical polish removes irrelevant header badges, demotes secondary navigation, "
        "adds distinct settings pictograms, quiets OFF toggles, makes Home inventory authoritative, "
        "adds a state-adaptive Home glance view, and simplifies Software Update without weakening release truth"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ValidationError as exc:
        raise SystemExit(f"FAIL: {exc}") from exc
