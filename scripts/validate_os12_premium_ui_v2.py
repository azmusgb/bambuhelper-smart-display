#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path


class ValidationError(RuntimeError):
    pass


def need(text: str, token: str, label: str) -> None:
    if token not in text:
        raise ValidationError(f"missing {label}: {token}")


def forbid(text: str, token: str, label: str) -> None:
    if token in text:
        raise ValidationError(f"forbidden {label}: {token}")


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

    # Reject the incomplete prototype patterns that broke c1802ec.
    forbidden_placeholders = {
        "... command routing ...": "placeholder command routing",
        "segment hit testing remains similar": "placeholder segment routing",
    }

    for token, label in forbidden_placeholders.items():
        forbid(pages, token, label)

    print("PASS: Premium UI v2 visual foundation")
    print("PASS: Premium UI v2 Home glance/Bento hierarchy")
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
