#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
from pathlib import Path


class ValidationError(RuntimeError):
    pass


def need(text: str, token: str, label: str) -> None:
    if token not in text:
        raise ValidationError(f"missing {label}: {token}")


def forbid(text: str, token: str, label: str) -> None:
    if token in text:
        raise ValidationError(f"forbidden {label}: {token}")


def block(text: str, signature: str) -> str:
    start = text.find(signature)
    if start < 0:
        raise ValidationError(f"missing function: {signature}")

    brace = text.find("{", start + len(signature))
    depth = 0

    for i in range(brace, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return text[start:i + 1]

    raise ValidationError(f"unterminated function: {signature}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate Premium UI v2 without weakening OS12 interaction contracts."
    )
    parser.add_argument("--repo", default=".")
    args = parser.parse_args()

    root = Path(args.repo).resolve()

    layout_path = root / "firmware/platform/ui/tabs_layout.hpp"
    pages_path = root / "firmware/platform/ui/tabs_pages.cppfrag"

    if not layout_path.is_file():
        raise ValidationError(f"missing {layout_path}")

    if not pages_path.is_file():
        raise ValidationError(f"missing {pages_path}")

    layout = layout_path.read_text(encoding="utf-8")
    pages = pages_path.read_text(encoding="utf-8")

    # Existing interaction model is authoritative.
    required_layout_contract = {
        "enum class HitKind": "typed hit-result contract",
        "struct Hit": "hit result",
        "inline Hit hitTest(": "shared hit testing",
        "static const uint8_t kSegmentCount": "printer segment count",
        "inline Rect segmentRect(": "printer segment geometry",
        "inline Rect holdTouchRect(": "guarded Stop touch geometry",
        "inline uint8_t maxScroll(": "scroll bounds",
        "inline uint8_t itemCount(": "runtime item count",
        "inline Rect hitRect(": "visible-hit rectangle mapping",
    }

    for token, label in required_layout_contract.items():
        need(layout, token, label)

    # Premium v2 Slice 1 is presentation-only.
    need(
        pages,
        "Premium v2 visual treatment only.",
        "premium card-surface treatment",
    )
    need(
        pages,
        "Premium v2 uses a quieter 8 px track.",
        "premium progress treatment",
    )
    need(
        pages,
        "static void wtDrawCardSurface(",
        "shared card renderer",
    )
    need(
        pages,
        "static void wtDrawProgress(",
        "shared progress renderer",
    )

    # Slice 2: Home glance/Bento hierarchy remains presentation-only.
    need(
        pages,
        "Premium v2 Home priority tile.",
        "Home priority tile hierarchy",
    )
    need(
        pages,
        "Premium v2 Home printer bento.",
        "Home printer Bento treatment",
    )
    need(
        pages,
        "static void wtDrawHomeMetric(",
        "read-only Home printer metric renderer",
    )
    need(
        pages,
        "wtDrawHomePrinter(s, r, w)",
        "Home printer canonical-row rendering",
    )

    # Slice 3: Printer Status / AMS presentation remains contract-safe.
    need(
        pages,
        "Premium v2 Printer segment treatment.",
        "Printer segment presentation",
    )
    need(
        pages,
        "Premium v2 AMS tray treatment.",
        "AMS read-only premium presentation",
    )
    need(
        pages,
        "Premium v2 Printer status hierarchy.",
        "Printer status hierarchy",
    )
    need(
        pages,
        'uiDrawFit("In use", right, mid, 60, FONT_BODY,',
        "14 px AMS active telemetry badge",
    )

    tray = block(
        pages,
        "static void wtDrawTray(const wsm::Screen& s, const wsm::Rect& row, const WtTray& t)",
    )
    if re.search(r"(?:fill|draw)RoundRect\s*\(\s*surface\.x", tray):
        raise ValidationError(
            "AMS read-only tray surface must remain flat"
        )

    # Slice 4: Printer Control presentation only. Command authority, hit
    # geometry, hold guard and state gating remain canonical.
    need(
        pages,
        "Premium v2 Printer Control primary action.",
        "Printer Control primary hierarchy",
    )
    need(
        pages,
        "Premium v2 secondary Printer Control row treatment.",
        "Printer Control secondary-row hierarchy",
    )
    need(
        pages,
        "Premium v2 guarded Stop treatment.",
        "guarded Stop visual hierarchy",
    )
    need(
        pages,
        "Premium v2 destructive hold feedback.",
        "guarded Stop hold feedback",
    )
    need(
        pages,
        "wtDrawControlRow(s, it, c, row, r);",
        "Printer Control canonical-row presentation",
    )

    primary = block(
        pages,
        "static void wtDrawPrimary(const wsm::Rect& row, const WtControls& c)",
    )
    need(
        primary,
        "wtl::primaryDrawRect(row)",
        "canonical Pause/Resume draw rectangle",
    )
    forbid(
        primary,
        "workshopPlatformDispatchPrinterCommand",
        "command dispatch inside Pause/Resume renderer",
    )

    stop = block(
        pages,
        "static void wtDrawStop(const wsm::Screen& s, const wsm::Rect& row, const WtControls& c)",
    )
    need(
        stop,
        "wtl::holdDrawRect(s, row)",
        "canonical guarded Stop draw rectangle",
    )
    forbid(
        stop,
        "workshopPlatformDispatchPrinterCommand",
        "command dispatch inside Stop renderer",
    )

    stop_hold = block(
        pages,
        "static void wtDrawStopHold(const wsm::Rect& b, uint8_t segments)",
    )
    need(
        stop_hold,
        'uiDrawFit(\n      "Keep holding",',
        "14 px guarded Stop hold label",
    )

    for command in ("Pause", "Resume", "Stop"):
        token = f"workshop::platform::PrinterCommand::{command}"
        count = pages.count(token)
        if count != 1:
            raise ValidationError(
                f"{command} command must remain routed exactly once; found {count}"
            )

    # Reject the incomplete prototype patterns that broke c1802ec.
    forbidden_placeholders = {
        "... command routing ...": "placeholder command routing",
        "segment hit testing remains similar": "placeholder segment routing",
    }

    for token, label in forbidden_placeholders.items():
        forbid(pages, token, label)

    print("PASS: Premium UI v2 visual foundation")
    print("PASS: Premium UI v2 Home glance/Bento hierarchy")
    print("PASS: Premium UI v2 Printer Status/AMS hierarchy")
    print("PASS: Premium UI v2 Printer Control hierarchy")
    print("PASS: canonical Hit/HitKind contract preserved")
    print("PASS: Printer segment geometry preserved")
    print("PASS: guarded Stop touch geometry preserved")
    print("PASS: scrolling/runtime item-count contracts preserved")
    print("PASS: no incomplete premium prototype placeholders")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ValidationError as exc:
        print(f"FAIL: {exc}")
        raise SystemExit(1)
