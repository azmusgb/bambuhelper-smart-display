#!/usr/bin/env python3
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
            if c == "\n": line = False
        elif comment:
            if c == "*" and n == "/": comment = False; i += 1
        elif string:
            if escape: escape = False
            elif c == "\\": escape = True
            elif c == string: string = None
        elif c == "/" and n == "/": line = True; i += 1
        elif c == "/" and n == "*": comment = True; i += 1
        elif c in ('"', "'"): string = c
        elif c == "{": depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return text[start:i + 1]
        i += 1
    raise ValidationError(f"unterminated block: {signature}")


def require(text: str, needle: str, label: str) -> None:
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
    web = load(repo / "src" / "web_server.cpp")

    nav = block(hub, "static void uiBottomNav(")
    require(nav, 'static const char* labels[4]={"Home","Printer","Workshop","More"};', "root navigation")
    forbid(nav, '"Tools"', "root navigation")
    forbid(nav, '"Settings"', "root navigation")

    require(hub, "static uint8_t gOs12PortalParent = 0;", "portal parent state")
    require(hub, 'setPage(SCREEN_HUB_SYSTEM);g_ui12SettingsView=0;g_networkSettingsView=false;g_audioSettingsView=false;gOs12PortalParent=1;g_ui12SystemView=1;', "Network -> Local Portal order")
    require(hub, 'gOs12PortalParent=0;g_ui12SystemView=1;', "System -> Local Portal")
    require(hub, 'if(gOs12PortalParent==1){setPage(SCREEN_HUB_MORE);g_ui12SettingsView=3;}', "Local Portal exact-parent Back")

    evidence = block(hub, "static void hubOs12EvidenceRow(")
    require(evidence, "const int16_t valueW=176;", "physical-fit evidence row")
    require(evidence, "BR_DATUM", "physical-fit evidence row")
    forbid(evidence, "OS12_TRAILING_COL_W", "physical-fit evidence row")

    home = block(hub, "static void drawHome(bool full)")
    require(home, '"Filament Inventory","Unknown","No authoritative inventory evidence"', "Home inventory truth")
    for forbidden in ("activeTray", "AmsTray", "matchSpoolByColor", "matchSpoolByMaterial"):
        forbid(home, forbidden, "Home inventory truth")

    workshop = block(hub, "static void drawWorkshop(bool full)")
    require(workshop, '"Print Readiness","Undetermined","Requirements unknown"', "Workshop readiness truth")
    require(workshop, '"Loaded Spools","Unknown","Canonical placement unknown"', "Workshop placement truth")
    require(workshop, '"Inventory","Unknown","Authoritative inventory unavailable"', "Workshop inventory truth")
    for forbidden in ("activeTray", "AmsTray", "matchSpoolByColor", "matchSpoolByMaterial"):
        forbid(workshop, forbidden, "Workshop inventory truth")

    for duplicate in ('settings-experience', 'settings-printer', 'settings-update'):
        if f'"id":"{duplicate}"' in web or f'\\"id\\":\\"{duplicate}\\"' in web:
            raise ValidationError(f"capture catalog duplicate remains: {duplicate}")
    for canonical in ('settings-display', 'settings-printer-power', 'system-update', 'system-portal', 'media', 'media-lab'):
        if f'"id":"{canonical}"' not in web and f'\\"id\\":\\"{canonical}\\"' not in web:
            raise ValidationError(f"capture catalog canonical view missing: {canonical}")

    show = block(hub, "bool smartHubShowPage(const char* pageName)")
    require(show, 'strcmp(pageName, "media") == 0', "native Media route")
    require(show, 'g_ui12SettingsView = 10;', "native Media route")
    require(show, 'strcmp(pageName, "media-lab") == 0', "native Media Lab route")
    require(show, 'g_ui12SettingsView = 11;', "native Media Lab route")

    print("PASS: OS12 UX v3 root navigation, Local Portal parent routing, physical-fit evidence rows, media native routes, and capture catalog are coherent")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
