#!/usr/bin/env python3
"""Install the Workshop OS 12.5 boot splash.

Replaces the v10 "Graphite + Ember" splash (orange, "WAVESHARE HOME") in initDisplay() with an animated one on the
LocalAI palette (firmware/platform/ui/boot_splash.cppfrag): a hexagon printed layer by layer, Local AI's sparkle cut
out of it, the name typing in, a boot bar and what Wi-Fi is doing. main.cpp draws a frame on every pass of the splash
phase (2.6 s, was 2 s) and ends on the finished frame. Run after apply_workshop_os12_tabs_overhaul.py (the Home tab's
/hub/show boot-splash preview calls bootSplashPreview). Every change is staged and written only after every anchor
validates.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_here = Path(__file__).resolve().parent
if str(_here) not in sys.path:
    sys.path.insert(0, str(_here))

from scripts.smart_home_patch_utils import PatchError

FRAGMENT = Path("firmware") / "platform" / "ui" / "boot_splash.cppfrag"
MARKER = "// Workshop OS 12.5 boot splash (apply_workshop_os12_boot_splash.py)."
OLD_START = "  // Smart Home v10: Graphite + Ember boot identity."
OLD_END = "#if PANEL_REQUIRES_AXS_FRAME_SPRITE\n    flushFrame();\n#endif\n  }\n"
INIT_SIGNATURE = "void initDisplay() {\n"
HEADER_ANCHOR = "void initDisplay();\n"
HEADER_ADDITION = (
    "// Workshop OS 12.5 boot splash: initDisplay() draws the first frame; the splash phase of loop() calls\n"
    "// bootSplashTick() for each next one and bootSplashEnd() when it is over.\n"
    "void bootSplashTick();\n"
    "void bootSplashEnd();\n"
    "// A frame at `percent` of the splash onto `g` (the hub framebuffer), for /hub/show boot-splash.\n"
    "void bootSplashPreview(lgfx::LovyanGFX& g, uint8_t percent);\n"
)
MAIN_HOLD_OLD = "  splashEnd = millis() + 2000;\n"
MAIN_HOLD_NEW = "  splashEnd = millis() + 2600;  // Workshop OS 12.5: the animated splash (boot_splash.cppfrag)\n"
MAIN_END_OLD = "  if (splashEnd > 0 && millis() > splashEnd) {\n    splashEnd = 0;\n"
MAIN_END_NEW = "  if (splashEnd > 0 && millis() > splashEnd) {\n    splashEnd = 0;\n    bootSplashEnd();\n"
MAIN_TICK_OLD = "  if (splashEnd > 0) {\n    delay(10);\n    return true;\n  }\n"
MAIN_TICK_NEW = "  if (splashEnd > 0) {\n    bootSplashTick();\n    return true;\n  }\n"


def once(text: str, old: str, new: str, label: str) -> str:
    if text.count(old) != 1:
        raise PatchError(f"{label}: expected one anchor, found {text.count(old)}")
    return text.replace(old, new, 1)


def apply(repo: Path, source_root: Path) -> None:
    ui_path, header_path, main_path = repo / "src" / "display_ui.cpp", repo / "src" / "display_ui.h", repo / "src" / "main.cpp"
    for path in (ui_path, header_path, main_path):
        if not path.is_file():
            raise PatchError(f"missing reconstructed source: {path}")
    ui = ui_path.read_text(encoding="utf-8")
    if MARKER in ui:
        print("Workshop OS 12.5 boot splash already installed")
        return
    fragment = (source_root / FRAGMENT).read_text(encoding="utf-8")
    start = ui.find(OLD_START)
    if start < 0 or ui.count(OLD_START) != 1:
        raise PatchError("old boot splash: expected one Graphite + Ember block")
    end = ui.find(OLD_END, start)
    if end < 0:
        raise PatchError("old boot splash: end of block not found")
    # The block opens with "  {" on the line after the comment; replace from the comment through its closing brace.
    ui = ui[:start] + "  bootSplashBegin();  // Workshop OS 12.5 (boot_splash.cppfrag)\n" + ui[end + len(OLD_END):]
    ui = once(ui, INIT_SIGNATURE, fragment.rstrip() + "\n\n" + INIT_SIGNATURE, "initDisplay")
    header = once(header_path.read_text(encoding="utf-8"), HEADER_ANCHOR, HEADER_ANCHOR + HEADER_ADDITION, "display_ui.h")
    main = main_path.read_text(encoding="utf-8")
    main = once(main, MAIN_HOLD_OLD, MAIN_HOLD_NEW, "splash hold")
    main = once(main, MAIN_END_OLD, MAIN_END_NEW, "splash end")
    main = once(main, MAIN_TICK_OLD, MAIN_TICK_NEW, "splash tick")
    if "WAVESHARE" in ui[ui.find("void initDisplay() {"):ui.find("void initDisplay() {") + 20000].split("\n}\n", 1)[0]:
        raise PatchError("old splash text is still in initDisplay()")
    ui_path.write_text(ui, encoding="utf-8")
    header_path.write_text(header, encoding="utf-8")
    main_path.write_text(main, encoding="utf-8")
    print("Workshop OS 12.5 boot splash installed: printed hexagon, Local AI sparkle, boot bar, Wi-Fi line (2.6 s)")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--source-root", type=Path, default=_here)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    if not args.apply:
        print("dry run: pass --apply")
        return 0
    try:
        apply(args.repo, args.source_root)
    except PatchError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
