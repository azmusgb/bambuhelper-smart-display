#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path


def fail(message: str) -> None:
    raise SystemExit(f"FAIL: {message}")


def braced_block(text: str, signature: str) -> str:
    start = text.find(signature)
    if start < 0 or text.find(signature, start + 1) >= 0:
        fail(f"missing/non-unique function: {signature}")
    brace = text.find("{", start)
    if brace < 0:
        fail(f"missing opening brace: {signature}")
    depth = 0
    string = None
    escape = False
    line = False
    block = False
    i = brace
    while i < len(text):
        c = text[i]
        n = text[i + 1] if i + 1 < len(text) else ""
        if line:
            if c == "\n": line = False
        elif block:
            if c == "*" and n == "/": block = False; i += 1
        elif string:
            if escape: escape = False
            elif c == "\\": escape = True
            elif c == string: string = None
        elif c == "/" and n == "/": line = True; i += 1
        elif c == "/" and n == "*": block = True; i += 1
        elif c in ('"', "'"): string = c
        elif c == "{": depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0: return text[start:i + 1]
        i += 1
    fail(f"unterminated function: {signature}")
    return ""


def require(block: str, needles: tuple[str, ...], label: str) -> None:
    for needle in needles:
        if needle not in block:
            fail(f"{label}: missing {needle!r}")


def forbid(block: str, needles: tuple[str, ...], label: str) -> None:
    for needle in needles:
        if needle in block:
            fail(f"{label}: forbidden {needle!r}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    args = ap.parse_args()
    repo = Path(args.repo).resolve()
    path = repo / "src" / "smart_hub.cpp"
    if not path.is_file():
        fail(f"missing {path}")
    text = path.read_text(encoding="utf-8")

    for helper in (
        "static void hubOs12RowSurface(",
        "static void hubOs12NavRow(",
        "static void hubOs12EvidenceRow(",
        "static void hubUi13InfoRow(",
        "static void hubUi13ToggleRow(",
        "static void hubUi13StepperRow(",
    ):
        if text.count(helper) != 1:
            fail(f"helper must exist exactly once: {helper}")

    for helper in (
        "static void hubOs12RowSurface(",
        "static void hubOs12NavRow(",
        "static void hubOs12EvidenceRow(",
        "static void hubUi13InfoRow(",
        "static void hubUi13ToggleRow(",
        "static void hubUi13StepperRow(",
    ):
        forbid(braced_block(text, helper), ("hubV1125Card(",), helper)

    home = braced_block(text, "static void drawHome(bool full)")
    workshop = braced_block(text, "static void drawWorkshop(bool full)")
    more = braced_block(text, "static void drawMore(bool full)")
    system = braced_block(text, "static void drawSystem(bool full)")

    require(home, (
        "uiBottomNav(0,nullptr)",
        '"Filament Inventory"',
        '"Unknown"',
        '"Authoritative evidence unavailable"',
        "hubOs12EvidenceRow(",
    ), "Home")
    forbid(home, ("activeTray", ".ams.", "AmsTray", "hubV1125Card("), "Home")

    require(workshop, (
        "uiBottomNav(2,nullptr)",
        '"Print Readiness"',
        '"Undetermined"',
        '"Loaded Spools"',
        '"Unknown"',
        '"No canonical placement evidence"',
        "hubOs12EvidenceRow(",
    ), "Workshop")
    forbid(workshop, ("activeTray", ".ams.", "AmsTray", "materialValue", "hubV1125Card("), "Workshop")

    require(more, (
        "uiBottomNav(3,nullptr)",
        '"Display & Appearance"',
        '"Sound & Microphone"',
        '"Network"',
        '"System"',
        "hubOs12NavRow(",
    ), "More")
    forbid(more, ("hubUi12SettingsCard(", 'hubUi12SettingsRect(4)'), "More")

    require(system, (
        '"Device Health"',
        '"Printer & Power"',
        '"Date & Time"',
        '"Software Update"',
        "hubOs12NavRow(",
    ), "System")
    forbid(system, ("uiBottomNav(", "hubUi12SettingsCard("), "System")

    child_functions = (
        "static void drawUi13Display()","static void drawUi13AfterPrint()","static void drawUi13Sound()",
        "static void drawUi13PrinterAlerts()","static void drawUi13AlertSignals()","static void drawUi13Network()",
        "static void drawUi13PrinterPower()","static void drawUi13PowerOptions()","static void drawUi13AutoOffConfirm()",
        "static void drawUi13DateTime()","static void drawUi13SoftwareUpdate()","static void drawUi13Diagnostics()",
        "static void drawUi12PortalAccess()","static void drawUi12Experience()","static void drawUi12PrinterConnection()",
        "static void drawUi12SoftwareUpdate()","static void drawOs12Media()","static void drawOs12MediaLab()",
    )
    for sig in child_functions:
        if sig in text:
            forbid(braced_block(text, sig), ("uiBottomNav(",), sig)

    settings_rect = braced_block(text, "static HubRect hubUi12SettingsRect(")
    require(settings_rect, (
        "if(i>=4)",
        "OS12_CONTENT_TOP+i*OS12_ROW_H",
        "W-OS12_MARGIN_X*2",
        "OS12_ROW_H",
    ), "More touch geometry")

    require(text, (
        "for(uint8_t i=0;i<4;i++)if(hubUi12SettingsRect(i).contains(x,y))",
        "if(i<3){g_ui12SettingsView=(uint8_t)(i+1U)",
        "else if(i==1){g_ui12SettingsView=4;setPage(SCREEN_HUB_MORE);}",
    ), "touch routing")

    print("PASS: OS12 UX architecture is hierarchical, flat, root-nav scoped, and inventory-truth preserving")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
