#!/usr/bin/env python3
from pathlib import Path
import argparse


class FixupError(RuntimeError):
    pass


def replace_exactly_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise FixupError(f"{label}: expected exactly 1 match, found {count}")
    return text.replace(old, new, 1)


def apply(repo: Path) -> None:
    p = repo / "src" / "smart_hub.cpp"
    text = p.read_text(encoding="utf-8")

    # v9.7 block replacement intentionally anchors on the following function
    # name. rb() preserves that end anchor, so RC1 composition can expose a
    # duplicated declaration at a replacement boundary. Normalize only the
    # exact known seams; fail closed if the generated source changes shape.
    text = replace_exactly_once(
        text,
        "static void uiWifiGlyphstatic void uiWifiGlyph",
        "static void uiWifiGlyph",
        "v97/ui-wifi-glyph-boundary",
    )
    text = replace_exactly_once(
        text,
        "static void drawTapHintstatic void drawTapHint",
        "static void drawTapHint",
        "v97/draw-tap-hint-boundary",
    )
    text = replace_exactly_once(
        text,
        "void smartHubReturnToPrinter() {\nvoid smartHubReturnToPrinter() {",
        "void smartHubReturnToPrinter() {",
        "v97/return-to-printer-boundary",
    )
    text = replace_exactly_once(
        text,
        "void smartHubDraw(ScreenState screen, bool forceRedraw) {\nvoid smartHubDraw(ScreenState screen, bool forceRedraw) {",
        "void smartHubDraw(ScreenState screen, bool forceRedraw) {",
        "v97/smart-hub-draw-boundary",
    )

    # The System replacement similarly retained the namespace end anchor after
    # writing its own copy. Keep exactly one anonymous-namespace close.
    text = replace_exactly_once(
        text,
        "\n} // namespace\n\n} // namespace\n",
        "\n} // namespace\n",
        "v97/namespace-boundary",
    )

    p.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    if not args.apply:
        raise SystemExit("Pass --apply")
    apply(Path(args.repo))
    print("Smart Home v9.7 boundary fixup applied")
