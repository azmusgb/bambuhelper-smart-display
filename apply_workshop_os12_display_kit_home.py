#!/usr/bin/env python3
"""Idle Home on the appliance-ui display kit, with Archivo (display-kit K3, K5, K6, K7; rollout step 4).

The kit's headers and the LovyanGFX adapter are already installed (apply_workshop_os12_display_kit_palette.py). This
layer adds what idle Home needs to draw through them:

- the kit's five Archivo faces (assets/ui/display/fonts/*.vlw, after assets/ui/VERSION's checksums are verified) as
  one PROGMEM array each in src/workshop_archivo_fonts.cpp, with include/workshop_archivo_fonts.h declaring the
  UiLgfxFonts the adapter takes. Generated here, not committed: the kit's .vlw files are the one copy of the faces;
- firmware/platform/ui/kit_screen.hpp and home_idle_kit.hpp (the helpers and idle Home's drawing, C++17, no graphics
  library; tests/workshop_os12_home_idle_kit_smoke.cpp draws them on a host) as include/workshop_kit/;
- the kit, the fonts and idle Home's drawing included in smart_hub.cpp, and /hub/show home (not only home-idle) ending a
  forced idle Home.

Runs after the Home, Printer and Workshop tabs, whose firmware/platform/ui/tabs_pages.cppfrag holds the screen's code
(wtDrawHomeIdleKit): includes are at the top of the file, so only the "home" show line depends on that layer.
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

_here = Path(__file__).resolve().parent
if str(_here) not in sys.path:
    sys.path.insert(0, str(_here))

from scripts.smart_home_patch_utils import PatchError, replace_once
import apply_workshop_os12_display_kit_palette as palette

MARKER = "// Workshop OS 12 display kit home (apply_workshop_os12_display_kit_home.py)"
KIT_DIR = palette.KIT_DIR
FONT_FILES = (  # in UiFont order: Fs3, Fs4, Fs5, Fs6, Readout
    ("archivo_14", "display/fonts/archivo-14.vlw"),
    ("archivo_16", "display/fonts/archivo-16.vlw"),
    ("archivo_20", "display/fonts/archivo-20.vlw"),
    ("archivo_26", "display/fonts/archivo-26.vlw"),
    ("archivo_readout_34", "display/fonts/archivo-readout-34.vlw"),
)
UI_DIR = Path("firmware") / "platform" / "ui"
KIT_SCREEN_FILES = ("kit_screen.hpp", "home_idle_kit.hpp", "more_picker.hpp", "picture_redraw.hpp", "row_kit.hpp")
FONTS_HEADER = Path("include") / "workshop_archivo_fonts.h"
FONTS_SOURCE = Path("src") / "workshop_archivo_fonts.cpp"

CANVAS_INCLUDE = '#include "workshop_lgfx_canvas.hpp"\n'
HUB_INCLUDES = (
    CANVAS_INCLUDE
    + '#include "kit/display/ui.h"\n'
    + '#include "workshop_archivo_fonts.h"\n'
    + '#include "workshop_kit/home_idle_kit.hpp"\n'
    + '#include "workshop_kit/more_picker.hpp"\n'
    + '#include "workshop_kit/picture_redraw.hpp"\n'
    + '#include "workshop_kit/row_kit.hpp"\n'
)
OLD_SHOW_HOME = '  if (strcmp(pageName, "home") == 0) { setPage(SCREEN_HUB_HOME); return true; }\n'
NEW_SHOW_HOME = (
    '  if (strcmp(pageName, "home") == 0) { wtHomeIdleForce(false); setPage(SCREEN_HUB_HOME); return true; }  '
    '// home-idle is wtShowPrinterView\'s\n'
)

HEADER = f"""{MARKER}
// The kit's Archivo faces for UiLgfxCanvas (display-kit K3), in UiFont order: 14, 16, 20, 26 px and the 34 px readout.
#pragma once
#include "workshop_lgfx_canvas.hpp"

extern const UiLgfxFonts kWorkshopArchivoFonts;
"""


def render_array(name: str, data: bytes, source: str) -> str:
    lines = [f"// {source}: {len(data)} bytes", f"static const uint8_t {name}[] PROGMEM = {{"]
    for i in range(0, len(data), 16):
        lines.append("    " + ", ".join(f"0x{b:02x}" for b in data[i:i + 16]) + ",")
    lines.append("};")
    return "\n".join(lines) + "\n"


def render_fonts_source(kit: Path) -> tuple[str, int]:
    parts = [
        MARKER,
        "// Generated from the kit's Archivo VLW files; defined once here so each is one copy in flash.",
        "#include <pgmspace.h>",
        '#include "workshop_archivo_fonts.h"',
        "",
    ]
    total = 0
    for name, relative in FONT_FILES:
        data = (kit / relative).read_bytes()
        if len(data) < 24:
            raise PatchError(f"{relative} is not a VLW file")
        total += len(data)
        parts.append(render_array(name, data, f"assets/ui/{relative}"))
    parts.append("const UiLgfxFonts kWorkshopArchivoFonts = {{" + ", ".join(name for name, _ in FONT_FILES) + "}};\n")
    return "\n".join(parts), total


def apply(repo: Path, source_root: Path) -> None:
    hub_path = repo / "src" / "smart_hub.cpp"
    if not hub_path.is_file():
        raise PatchError(f"missing reconstructed source: {hub_path}")
    hub = hub_path.read_text(encoding="utf-8")
    if MARKER in hub:
        print("WS350 display kit home already applied")
        return
    if CANVAS_INCLUDE not in hub:
        raise PatchError("the display kit palette layer has not run (no workshop_lgfx_canvas.hpp include)")

    kit = source_root / KIT_DIR
    palette.verify_kit(kit)  # the kit is unedited, fonts included

    source, total = render_fonts_source(kit)
    (repo / FONTS_SOURCE).write_text(source, encoding="utf-8")
    (repo / FONTS_HEADER).write_text(HEADER, encoding="utf-8")

    target = repo / "include" / "workshop_kit"
    target.mkdir(parents=True, exist_ok=True)
    for name in KIT_SCREEN_FILES:
        shutil.copyfile(source_root / UI_DIR / name, target / name)

    hub = replace_once(hub, CANVAS_INCLUDE, HUB_INCLUDES + "\n" + MARKER + "\n", "kit, fonts and idle Home includes")
    hub = replace_once(hub, OLD_SHOW_HOME, NEW_SHOW_HOME, "/hub/show home ends a forced idle Home")
    hub_path.write_text(hub, encoding="utf-8")
    print(f"WS350 display kit home: Archivo ({total} bytes in 5 faces) and idle Home's kit drawing installed")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True)
    parser.add_argument("--source-root", default=str(_here))
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    if not args.apply:
        raise SystemExit("refusing to modify reconstructed source without --apply")
    try:
        apply(Path(args.repo).resolve(), Path(args.source_root).resolve())
    except PatchError as exc:
        raise SystemExit(f"FAIL: {exc}") from exc
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
