#!/usr/bin/env python3
"""Complete Sky Radar wiring — one pass, all sites.

Every edit is staged in memory and the four files are written only after all
anchors validate, so a mismatch leaves the tree untouched. Re-running on an
already wired tree is a no-op.

NOTE: Two cosmetic fixes (sprite background clear, retry-counter
clamp) were applied by hand to the build tree after this script ran.
They need to be folded in here next session."""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from scripts.smart_home_patch_utils import PatchError


def insert_once(src: str, anchor: str, replacement: str, label: str) -> str:
    if src.count(anchor) != 1:
        raise PatchError(f"{label}: anchor missing/non-unique")
    return src.replace(anchor, replacement, 1)


def patch_enum(src: str) -> str:
    if "SCREEN_SKY_RADAR" in src:
        return src
    anchor = "SCREEN_HUB_SYSTEM, SCREEN_HUB_PRINTER, SCREEN_HUB_MORE"
    print("  enum: added SCREEN_SKY_RADAR")
    return insert_once(src, anchor, anchor + ", SCREEN_SKY_RADAR", "ScreenState enum")


def patch_display_dispatch(src: str) -> str:
    if "case SCREEN_SKY_RADAR:" in src:
        return src
    needle = "    case SCREEN_HUB_SYSTEM:\n      smartHubDraw(currentScreen, forceRedraw);"
    print("  display_ui.cpp: added fall-through case")
    return insert_once(
        src,
        needle,
        "    case SCREEN_HUB_SYSTEM:\n    case SCREEN_SKY_RADAR:\n      smartHubDraw(currentScreen, forceRedraw);",
        "display_ui dispatch",
    )


def patch_is_screen(src: str) -> str:
    if "screen == SCREEN_SKY_RADAR;\n}" in src:
        return src
    old = """         screen == SCREEN_HUB_CUSTOM ||
         screen == SCREEN_HUB_SYSTEM;
}"""
    new = """         screen == SCREEN_HUB_CUSTOM ||
         screen == SCREEN_HUB_SYSTEM ||
         screen == SCREEN_SKY_RADAR;
}"""
    print("  smart_hub.cpp: added to smartHubIsScreen whitelist")
    return insert_once(src, old, new, "smartHubIsScreen")


def patch_hub_draw(src: str) -> str:
    if "case SCREEN_SKY_RADAR:    drawSkyRadar" in src:
        return src
    needle = "    case SCREEN_HUB_SYSTEM:   drawSystem(effectiveForce);   break;"
    print("  smart_hub.cpp: added drawSkyRadar dispatch")
    return insert_once(
        src,
        needle,
        needle + "\n    case SCREEN_SKY_RADAR:    drawSkyRadar();               break;",
        "smartHubDraw switch",
    )


def patch_advance(src: str) -> str:
    if "case SCREEN_SKY_RADAR:    setPage(SCREEN_HUB_HOME)" in src:
        return src
    needle = "    case SCREEN_HUB_SYSTEM:   setPage(SCREEN_HUB_HOME);     break;"
    print("  smart_hub.cpp: added advance cycle case")
    return insert_once(
        src,
        needle,
        "    case SCREEN_HUB_SYSTEM:\n    case SCREEN_SKY_RADAR:    setPage(SCREEN_HUB_HOME);     break;",
        "smartHubAdvance",
    )


def patch_show_page(src: str) -> str:
    if 'strcmp(pageName, "sky-radar")' in src:
        return src
    matches = list(re.finditer(r"bool smartHubShowPage\(const char\* pageName\)\s*\{\s*\n", src))
    if len(matches) != 1:
        raise PatchError(f"smartHubShowPage definition: expected one, found {len(matches)}")
    end = matches[0].end()
    insert = (
        '  if (strcmp(pageName, "sky-radar") == 0) {\n'
        '    setPage(SCREEN_SKY_RADAR); g_dirty = true; return true;\n'
        '  }\n'
    )
    print("  smart_hub.cpp: added early sky-radar route")
    return src[:end] + insert + src[end:]


def patch_knetwork(src: str) -> str:
    # OS12 trees are already bounded by rc8; kept for older reconstructions.
    old = "for(uint8_t i=0;i<HUB_NETWORK_PAGE_COUNT;i++) {\n    if(strcmp(pageName,kNetworkPages[i])==0) {"
    if old not in src:
        return src
    print("  smart_hub.cpp: fixed kNetworkPages loop bound")
    return src.replace(
        old,
        "for(uint8_t i=0;i<(uint8_t)(sizeof(kNetworkPages)/sizeof(kNetworkPages[0]));i++) {\n"
        "    if(strcmp(pageName,kNetworkPages[i])==0) {",
        1,
    )


def patch_catalog(src: str) -> str:
    if '"id":"sky-radar"' in src:
        return src
    anchor = '    {"id":"system","label":"System","group":"Primary"},\n'
    print("  web_server.cpp: added catalog entry")
    return insert_once(
        src, anchor, anchor + '    {"id":"sky-radar","label":"Sky Radar","group":"Primary"},\n', "view catalog"
    )


PATCHES = {
    "display_ui.h": (patch_enum,),
    "display_ui.cpp": (patch_display_dispatch,),
    "smart_hub.cpp": (patch_is_screen, patch_hub_draw, patch_advance, patch_show_page, patch_knetwork),
    "web_server.cpp": (patch_catalog,),
}


def apply(repo: Path) -> None:
    paths = {name: repo / "src" / name for name in PATCHES}
    missing = [str(path) for path in paths.values() if not path.is_file()]
    if missing:
        raise PatchError(f"missing reconstructed source: {', '.join(missing)}")
    staged = {}
    for name, patches in PATCHES.items():
        src = paths[name].read_text(encoding="utf-8")
        for patch in patches:
            src = patch(src)
        staged[name] = src
    for name, src in staged.items():
        paths[name].write_text(src, encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    if not args.apply:
        raise SystemExit("refusing to modify without --apply")
    print("Applying complete Sky Radar wiring:")
    try:
        apply(Path(args.repo).resolve())
    except PatchError as exc:
        raise SystemExit(f"FAILED: {exc}")
    print("Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
