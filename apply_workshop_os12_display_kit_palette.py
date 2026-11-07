#!/usr/bin/env python3
"""Put the WS350 touchscreen on the appliance-ui kit's colours (display-kit K1, K5, K7; rollout step 3).

Replaces apply_workshop_os12_device_localai_palette.py, which repainted the role-named RGB565 constants with LocalAI's
navy and blue. The kit is now the one source of colour, so:

- the kit's header files in assets/ui (tokens.h, words.h, needs.h and display/*.h) are installed as include/kit/, after
  assets/ui/VERSION's checksums are verified (the same drift check as assets/ui/verify.py);
- firmware/platform/ui/display_palette.h (written by scripts/generate_display_palette.py, and checked here to be what
  that script gives for this kit) is installed as include/workshop_display_palette.h. It defines every UI_*, OS12V_*,
  C10_* and W25_* constant of smart_hub.cpp as a kit token, so those definitions are removed from smart_hub.cpp and the
  header is included instead: accent coolant teal, greys the kit's graphite, one set of lamp colours;
- firmware/platform/ui/lgfx_canvas.hpp, the LovyanGFX adapter for the kit's UiCanvas, is installed as
  include/workshop_lgfx_canvas.hpp and instantiated once in smart_hub.cpp, so it is compiled against the real
  library. Nothing draws through it yet (rollout steps 4 and 5 port the screens) and no Archivo font is linked in;
- display_ui.cpp includes the kit's tokens (the boot splash's colours are kit tokens);
- the kit's parts are C++17 (a constexpr lambda in display/canvas.h), so the WS350 and JC3248W535 environments compile
  with -std=gnu++17 instead of the framework's gnu++11.

Runs where the LocalAI palette step ran: after the More overhaul, before the Home, Printer and Workshop tabs.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import shutil
import sys
from pathlib import Path

_here = Path(__file__).resolve().parent
if str(_here) not in sys.path:
    sys.path.insert(0, str(_here))

from scripts.smart_home_patch_utils import PatchError, replace_once

MARKER = "// Workshop OS 12 display kit palette (apply_workshop_os12_display_kit_palette.py)"
KIT_DIR = Path("assets") / "ui"
PALETTE_SOURCE = Path("firmware") / "platform" / "ui" / "display_palette.h"
PALETTE_TARGET = Path("include") / "workshop_display_palette.h"
CANVAS_SOURCE = Path("firmware") / "platform" / "ui" / "lgfx_canvas.hpp"
CANVAS_TARGET = Path("include") / "workshop_lgfx_canvas.hpp"
KIT_TARGET = Path("include") / "kit"
CPP17_ENVS = (("boards/ws_lcd_350.ini", "ws_lcd_350"), ("platformio.ini", "jc3248w535"))

HUB_ANCHOR = '#include "smart_hub.h"\n'
HUB_INCLUDES = (
    HUB_ANCHOR
    + '#include "workshop_display_palette.h"\n'
    + '#include "workshop_lgfx_canvas.hpp"\n'
)
UI_ANCHOR = '#include "smart_home_build.h"\n'
UI_INCLUDES = UI_ANCHOR + '#include "kit/tokens.h"\n'

# The adapter is instantiated with the real library type once, so every member is compiled and the datum constant is
# checked against the library's own. Unused, it costs no flash (the linker drops it).
INSTANTIATION = (
    "\n" + MARKER + "\n"
    "static_assert((int)lgfx::textdatum::baseline_left == (int)UiLgfxCanvas<lgfx::LovyanGFX>::kBaselineLeft,\n"
    '              "UiLgfxCanvas::kBaselineLeft must be lgfx::textdatum::baseline_left");\n'
    "template class UiLgfxCanvas<lgfx::LovyanGFX>;\n"
)


def load_generator(source_root: Path):
    path = source_root / "scripts" / "generate_display_palette.py"
    spec = importlib.util.spec_from_file_location("generate_display_palette", path)
    if spec is None or spec.loader is None:
        raise PatchError(f"missing {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def verify_kit(kit: Path) -> dict:
    """assets/ui/verify.py, in-process: every file the VERSION lists is there and unedited."""
    version = json.loads((kit / "VERSION").read_text(encoding="utf-8"))
    bad = []
    for name, digest in version["files"].items():
        try:
            ok = hashlib.sha256((kit / name).read_bytes()).hexdigest() == digest
        except OSError:
            ok = False
        if not ok:
            bad.append(name)
    if bad:
        raise PatchError(f"assets/ui drifted from appliance-ui v{version['version']}: {', '.join(bad)} (sync, do not edit)")
    return version


def install_kit(repo: Path, kit: Path, version: dict) -> int:
    target = repo / KIT_TARGET
    if target.exists():
        shutil.rmtree(target)
    count = 0
    for name in version["files"]:
        if not name.endswith(".h"):
            continue
        dest = target / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(kit / name, dest)
        count += 1
    if not (target / "display" / "canvas.h").is_file() or not (target / "tokens.h").is_file():
        raise PatchError("the kit has no display/canvas.h or tokens.h: sync assets/ui with --display")
    return count


def remove_definitions(text: str, names: list[str]) -> tuple[str, int]:
    """Each old constant is defined once, as `static [constexpr|const] uint16_t NAME = 0x....;` and a comment."""
    removed = 0
    for name in names:
        pattern = re.compile(r"^[ \t]*static (?:constexpr |const )uint16_t " + re.escape(name) + r"\s*=\s*0x[0-9A-Fa-f]{4};[^\n]*\n", re.M)
        text, n = pattern.subn("", text)
        if n != 1:
            raise PatchError(f"{name}: expected one definition in smart_hub.cpp, found {n}")
        removed += n
    return text, removed


def insert_after_includes(text: str) -> str:
    """The instantiation goes after the file's opening block of #include lines, where lgfx types are visible."""
    block = re.compile(r"\A(?:(?:#include[^\n]*|[ \t]*|//[^\n]*)\n)+")
    match = block.match(text)
    if not match or "#include" not in match.group(0) or '"smart_hub.h"' not in match.group(0):
        raise PatchError("smart_hub.cpp does not open with the expected block of #include lines")
    return text[:match.end()] + INSTANTIATION + text[match.end():]


def use_cpp17(repo: Path, relative: str, env: str) -> None:
    path = repo / relative
    if not path.is_file():
        raise PatchError(f"missing {relative}")
    text = path.read_text(encoding="utf-8")
    start = text.find(f"[env:{env}]")
    if start < 0:
        raise PatchError(f"{relative}: [env:{env}] missing")
    end = text.find("\n[", start + 1)
    end = len(text) if end < 0 else end
    section = text[start:end]
    if "-std=gnu++17" in section:
        print(f"{env}: already on -std=gnu++17")
        return
    if "build_unflags" in section:
        raise PatchError(f"{env}: has build_unflags already; merge -std=gnu++11 by hand")
    if section.count("\nbuild_flags =\n") != 1:
        raise PatchError(f"{env}: expected one build_flags list")
    section = section.replace("\nbuild_flags =\n", "\nbuild_unflags =\n    -std=gnu++11\nbuild_flags =\n    -std=gnu++17\n", 1)
    path.write_text(text[:start] + section + text[end:], encoding="utf-8")


def apply(repo: Path, source_root: Path) -> None:
    hub_path = repo / "src" / "smart_hub.cpp"
    ui_path = repo / "src" / "display_ui.cpp"
    for path in (hub_path, ui_path):
        if not path.is_file():
            raise PatchError(f"missing reconstructed source: {path}")
    hub = hub_path.read_text(encoding="utf-8")
    if MARKER in hub:
        print("WS350 display kit palette already applied")
        return

    generator = load_generator(source_root)
    tokens = generator.read_tokens(source_root / KIT_DIR / "tokens.h")
    generator.validate(tokens)
    palette = (source_root / PALETTE_SOURCE).read_text(encoding="utf-8")
    version = verify_kit(source_root / KIT_DIR)
    if palette != generator.render(tokens, version["version"]):
        raise PatchError("display_palette.h is stale: run python3 scripts/generate_display_palette.py")

    installed = install_kit(repo, source_root / KIT_DIR, version)
    (repo / PALETTE_TARGET).write_text(palette, encoding="utf-8")
    shutil.copyfile(source_root / CANVAS_SOURCE, repo / CANVAS_TARGET)

    hub, removed = remove_definitions(hub, list(generator.all_roles()))
    hub = replace_once(hub, HUB_ANCHOR, HUB_INCLUDES, "palette and adapter includes")
    hub = insert_after_includes(hub)
    hub_path.write_text(hub, encoding="utf-8")

    ui = ui_path.read_text(encoding="utf-8")
    ui_path.write_text(replace_once(ui, UI_ANCHOR, UI_INCLUDES, "kit tokens include"), encoding="utf-8")

    for relative, env in CPP17_ENVS:
        use_cpp17(repo, relative, env)
    print(f"WS350 display kit palette: kit v{version['version']} ({installed} headers), {removed} old colour constants now kit tokens")


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
