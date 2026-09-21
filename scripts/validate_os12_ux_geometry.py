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
            if c == "\n":
                line = False
        elif block:
            if c == "*" and n == "/":
                block = False
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
            block = True
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
    fail(f"unterminated function: {signature}")
    return ""


def require(haystack: str, needles: tuple[str, ...], label: str) -> None:
    for needle in needles:
        if needle not in haystack:
            fail(f"{label}: missing {needle!r}")


def forbid(haystack: str, needles: tuple[str, ...], label: str) -> None:
    for needle in needles:
        if needle in haystack:
            fail(f"{label}: forbidden {needle!r}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    args = ap.parse_args()
    path = Path(args.repo).resolve() / "src" / "smart_hub.cpp"
    if not path.is_file():
        fail(f"missing {path}")
    text = path.read_text(encoding="utf-8")

    tokens = (
        "static constexpr int16_t OS12_MARGIN_X = 12;",
        "static constexpr int16_t OS12_HEADER_H = 44;",
        "static constexpr int16_t OS12_CONTENT_TOP = 48;",
        "static constexpr int16_t OS12_ROW_H = 52;",
        "static constexpr int16_t OS12_ROW_INSET_X = 14;",
        "static constexpr int16_t OS12_SECTION_GAP = 8;",
        "static constexpr int16_t OS12_ACTION_H = 52;",
        "static constexpr int16_t OS12_ACTION_GAP = 8;",
        "static constexpr int16_t OS12_BOTTOM_SAFE = 12;",
    )
    require(text, tokens, "geometry tokens")
    for token in tokens:
        if text.count(token) != 1:
            fail(f"geometry token must exist exactly once: {token}")

    declaration_pos = text.find("static constexpr int16_t OS12_MARGIN_X = 12;")
    for signature in (
        "static void drawHeader(",
        "static void uiBottomNav(",
        "static void hubV1125Card(",
        "static void hubOs12RowSurface(",
        "static HubRect hubUi13RowRect(",
    ):
        consumer_pos = text.find(signature)
        if consumer_pos >= 0 and declaration_pos > consumer_pos:
            fail(f"geometry tokens are declared after consumer: {signature}")

    row = braced_block(text, "static void hubOs12RowSurface(")
    require(row, (
        "OS12_ROW_INSET_X",
        "tft.drawFastHLine",
        "tft.fillRoundRect",
        "tft.drawRoundRect",
        "OS12_UI_RADIUS_SMALL",
    ), "row surface")
    forbid(row, ("hubV1125Card(",), "row surface")

    nav = braced_block(text, "static void hubOs12NavRow(")
    require(nav, ("OS12_ROW_INSET_X", "tft.drawLine", "cy-5", "cy+5"), "navigation row")
    forbid(nav, ('uiDrawFit(">")',), "navigation row glyph")

    evidence = braced_block(text, "static void hubOs12EvidenceRow(")
    require(evidence, (
        "const int16_t inset=OS12_ROW_INSET_X;",
        "const int16_t valueW=176;",
        "const int16_t detailX=",
        "const int16_t detailW=",
        "BR_DATUM",
    ), "evidence row")
    forbid(evidence, ("OS12_TRAILING_COL_W",), "evidence row")

    settings = braced_block(text, "static HubRect hubUi12SettingsRect(")
    require(settings, (
        "OS12_MARGIN_X",
        "OS12_CONTENT_TOP+i*OS12_ROW_H",
        "W-OS12_MARGIN_X*2",
        "OS12_ROW_H",
    ), "More geometry")

    child_rows = braced_block(text, "static HubRect hubUi13RowRect(")
    require(child_rows, (
        "OS12_MARGIN_X",
        "OS12_CONTENT_TOP+i*56",
        "W-OS12_MARGIN_X*2",
        ",54)",
    ), "child row geometry")

    back = braced_block(text, "static HubRect hubUi13BackRect()")
    action = braced_block(text, "static HubRect hubUi13ActionRect()")
    require(back, ("OS12_MARGIN_X", "OS12_BOTTOM_SAFE", "OS12_ACTION_H", "116"), "Back action geometry")
    require(action, ("OS12_MARGIN_X", "OS12_BOTTOM_SAFE", "OS12_ACTION_H", "184"), "primary action geometry")

    system = braced_block(text, "static HubRect hubUi13SystemCardRect(")
    require(system, (
        "OS12_MARGIN_X",
        "OS12_CONTENT_TOP+i*OS12_ROW_H",
        "W-OS12_MARGIN_X*2",
    ), "System list geometry")

    home = braced_block(text, "static void drawHome(bool full)")
    require(home, (
        "hr(OS12_MARGIN_X,48,W-OS12_MARGIN_X*2,64)",
        "hr(OS12_MARGIN_X,118,W-OS12_MARGIN_X*2,68)",
        "hr(OS12_MARGIN_X,192,W-OS12_MARGIN_X*2,60)",
        '"No authoritative inventory evidence"',
    ), "Home geometry")
    forbid(home, ("hr(8,", "hubV1125Card("), "Home geometry")

    workshop = braced_block(text, "static void drawWorkshop(bool full)")
    require(workshop, (
        "hr(OS12_MARGIN_X,48,W-OS12_MARGIN_X*2,60)",
        "hr(OS12_MARGIN_X,112,W-OS12_MARGIN_X*2,60)",
        "hr(OS12_MARGIN_X,176,W-OS12_MARGIN_X*2,72)",
        "W-OS12_MARGIN_X*2",
        '"Undetermined"',
        '"Canonical placement unknown"',
    ), "Workshop geometry")
    forbid(workshop, ("hr(8,", "hubV1125Card("), "Workshop geometry")

    toggle = braced_block(text, "static void hubUi13ToggleRow(")
    stepper = braced_block(text, "static void hubUi13StepperRow(")
    require(toggle, ("OS12_ROW_INSET_X", "controlW=62", "34", "d=26"), "toggle geometry")
    require(stepper, ("buttonW=46", "buttonH=44", "OS12_ACTION_GAP"), "stepper geometry")

    print("PASS: OS12 480x320 geometry uses canonical margins, rows, action bars, and compact physical evidence columns")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
