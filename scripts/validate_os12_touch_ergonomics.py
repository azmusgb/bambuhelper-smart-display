#!/usr/bin/env python3
"""Validate the 12.3.6 touch ergonomics in a reconstructed WS350 tree.

Checks that the finished tree has 55 px rows, press feedback on every hub
screen, swipe-to-scroll wired from main.cpp, and a Pause that (like Stop) only
fires for a hold that started and stayed on its button.
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path


class ValidationError(Exception):
    pass


def need(text: str, needle: str, label: str) -> None:
    if needle not in text:
        raise ValidationError(f"missing: {label} ({needle!r})")


def block(text: str, signature: str) -> str:
    start = text.find(signature)
    if start < 0:
        raise ValidationError(f"missing function: {signature}")
    depth, i = 0, text.find("{", start)
    while i < len(text):
        depth += {"{": 1, "}": -1}.get(text[i], 0)
        if depth == 0:
            return text[start:i + 1]
        i += 1
    raise ValidationError(f"unterminated function: {signature}")


def validate(repo: Path) -> None:
    hub = (repo / "src/smart_hub.cpp").read_text(encoding="utf-8")
    main = (repo / "src/main.cpp").read_text(encoding="utf-8")
    layout = (repo / "include/workshop_more_layout.hpp").read_text(encoding="utf-8")
    if not re.search(r"static const int16_t kRowH = (5[2-9]|6\d);", layout):
        raise ValidationError("rows must be at least 52 px (about 8 mm) tall")

    hold = block(hub, "void smartHubUpdateHoldProgress(uint16_t rawX, uint16_t rawY, uint32_t holdMs)")
    need(hold, "wsPressFeedback(x,y);", "press outline on the first sample")
    need(hold, "g_pressFeedbackShown=false;", "press outline re-armed for the next press")
    need(hold, "const bool pauseHeld=wtPauseHoldTrack(x,y,pause);", "Pause hold tracked on every sample")
    need(hold, "if(wtStopHoldTrack(x,y,stop))", "Stop hold tracked on every sample")
    need(hold, "wtDrawPauseHold(", "Pause hold progress drawn")

    touch = block(hub, "static bool wtPrinterTouch(int16_t x, int16_t y, bool longPress)")
    need(touch, "const bool pauseHeld = wtPauseHoldConsume();", "Pause hold state read for every press")
    primary = touch[touch.find("case wtl::ItemId::ControlPrimary:"):touch.find("case wtl::ItemId::ControlLight:")]
    gate, dispatch = primary.find("if (!(longPress && pauseHeld))"), primary.find("workshopPlatformDispatchPrinterCommand(")
    if gate < 0 or dispatch < 0 or gate > dispatch:
        raise ValidationError("Pause/Resume must require a hold on the Pause button before dispatching")
    track = block(hub, "static bool wtPauseHoldTrack(int16_t x, int16_t y, wsm::Rect& drawn)")
    need(track, "if (!g_wtPauseHoldStarted) { g_wtPauseHoldStarted = true; g_wtPauseHoldValid = on; }", "hold must start on Pause")
    need(track, "else if (!on) g_wtPauseHoldValid = false;", "hold must stay on Pause")

    swipe = block(hub, "bool smartHubHandleSwipe(uint16_t rawX0, uint16_t rawY0, uint16_t rawX1, uint16_t rawY1)")
    for needle, label in (("wtStopHoldConsume();", "a drag never sends Stop"),
                          ("wtPauseHoldConsume();", "a drag never sends Pause"),
                          ("if (ady < 32 || ady <= adx) return false;", "only a clear vertical drag is a swipe")):
        need(swipe, needle, label)
    need(block(hub, "bool smartHubHandleTouch(uint16_t rawX, uint16_t rawY, bool longPress)"), "g_dirty = true;",
         "a touch repaints the page and clears the outline")
    need(main, "smartHubHandleSwipe(hubTouchStartX, hubTouchStartY, hubTouchX, hubTouchY)", "main.cpp routes drags to the swipe")
    need(main, "hubTouchStartValid = hubTouchHasPoint;", "a drag needs a real start point")
    if main.find("smartHubHandleSwipe(") > main.find("smartHubHandleTouch(hubTouchX, hubTouchY"):
        raise ValidationError("the swipe check must come before the tap")
    print("PASS: OS12 touch ergonomics (55 px rows, press outline, swipe to scroll, hold-guarded Pause)")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True)
    args = parser.parse_args()
    try:
        validate(Path(args.repo).resolve())
    except ValidationError as exc:
        raise SystemExit(f"FAIL: {exc}") from exc
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
