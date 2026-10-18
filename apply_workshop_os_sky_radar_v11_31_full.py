#!/usr/bin/env python3
"""Complete Sky Radar wiring — one pass, all sites.

NOTE: Two cosmetic fixes (sprite background clear, retry-counter
clamp) were applied by hand to the build tree after this script ran.
They need to be folded in here next session."""
from __future__ import annotations
import argparse, re, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from scripts.smart_home_patch_utils import PatchError, replace_once, replace_braced_block


def patch_enum(repo: Path) -> None:
    h = repo / "src" / "display_ui.h"
    src = h.read_text()
    if "SCREEN_SKY_RADAR" in src:
        return
    src = src.replace(
        "SCREEN_HUB_SYSTEM, SCREEN_HUB_PRINTER, SCREEN_HUB_MORE",
        "SCREEN_HUB_SYSTEM, SCREEN_HUB_PRINTER, SCREEN_HUB_MORE, SCREEN_SKY_RADAR",
        1,
    )
    h.write_text(src)
    print("  enum: added SCREEN_SKY_RADAR")


def patch_display_dispatch(repo: Path) -> None:
    c = repo / "src" / "display_ui.cpp"
    src = c.read_text()
    if "case SCREEN_SKY_RADAR:" in src and "smartHubDraw" in src:
        return
    needle = "    case SCREEN_HUB_SYSTEM:\n      smartHubDraw(currentScreen, forceRedraw);"
    if needle not in src:
        raise PatchError("display_ui dispatch anchor missing")
    src = src.replace(
        needle,
        "    case SCREEN_HUB_SYSTEM:\n    case SCREEN_SKY_RADAR:\n      smartHubDraw(currentScreen, forceRedraw);",
        1,
    )
    c.write_text(src)
    print("  display_ui.cpp: added fall-through case")


def patch_is_screen(repo: Path) -> None:
    h = repo / "src" / "smart_hub.cpp"
    src = h.read_text()
    old = """bool smartHubIsScreen(ScreenState screen) {
  return screen == SCREEN_HUB_HOME ||
         screen == SCREEN_HUB_PRINTER ||
         screen == SCREEN_HUB_WORKSHOP ||
         screen == SCREEN_HUB_MORE ||
         screen == SCREEN_HUB_CUSTOM ||
         screen == SCREEN_HUB_SYSTEM;
}"""
    new = """bool smartHubIsScreen(ScreenState screen) {
  return screen == SCREEN_HUB_HOME ||
         screen == SCREEN_HUB_PRINTER ||
         screen == SCREEN_HUB_WORKSHOP ||
         screen == SCREEN_HUB_MORE ||
         screen == SCREEN_HUB_CUSTOM ||
         screen == SCREEN_HUB_SYSTEM ||
         screen == SCREEN_SKY_RADAR;
}"""
    if "screen == SCREEN_SKY_RADAR;\n}" in src:
        return
    if old not in src:
        raise PatchError("smartHubIsScreen anchor missing")
    h.write_text(src.replace(old, new, 1))
    print("  smart_hub.cpp: added to smartHubIsScreen whitelist")


def patch_hub_draw(repo: Path) -> None:
    h = repo / "src" / "smart_hub.cpp"
    src = h.read_text()
    if "case SCREEN_SKY_RADAR:    drawSkyRadar" in src:
        return
    needle = "    case SCREEN_HUB_SYSTEM:   drawSystem(effectiveForce);   break;"
    if needle not in src:
        raise PatchError("smartHubDraw switch anchor missing")
    src = src.replace(
        needle,
        needle + "\n    case SCREEN_SKY_RADAR:    drawSkyRadar();               break;",
        1,
    )
    h.write_text(src)
    print("  smart_hub.cpp: added drawSkyRadar dispatch")


def patch_advance(repo: Path) -> None:
    h = repo / "src" / "smart_hub.cpp"
    src = h.read_text()
    if "case SCREEN_SKY_RADAR:    setPage(SCREEN_HUB_HOME)" in src:
        return
    needle = "    case SCREEN_HUB_SYSTEM:   setPage(SCREEN_HUB_HOME);     break;"
    if needle not in src:
        raise PatchError("smartHubAdvance anchor missing")
    src = src.replace(
        needle,
        "    case SCREEN_HUB_SYSTEM:\n    case SCREEN_SKY_RADAR:    setPage(SCREEN_HUB_HOME);     break;",
        1,
    )
    h.write_text(src)
    print("  smart_hub.cpp: added advance cycle case")


def patch_show_page(repo: Path) -> None:
    h = repo / "src" / "smart_hub.cpp"
    src = h.read_text()
    if 'strcmp(pageName, "sky-radar")' in src:
        return
    m = re.search(r'bool smartHubShowPage\([^)]*\)\s*\{\s*\n', src)
    if not m:
        raise PatchError("smartHubShowPage signature not found")
    insert = (
        '  if (strcmp(pageName, "sky-radar") == 0) {\n'
        '    setPage(SCREEN_SKY_RADAR); g_dirty = true; return true;\n'
        '  }\n'
    )
    src = src[:m.end()] + insert + src[m.end():]
    h.write_text(src)
    print("  smart_hub.cpp: added early sky-radar route")


def patch_catalog(repo: Path) -> None:
    w = repo / "src" / "web_server.cpp"
    src = w.read_text()
    if '"id":"sky-radar"' in src:
        return
    anchor = '    {"id":"system","label":"System","group":"Primary"},\n'
    if anchor not in src:
        raise PatchError("catalog anchor missing")
    src = src.replace(
        anchor,
        anchor + '    {"id":"sky-radar","label":"Sky Radar","group":"Primary"},\n',
        1,
    )
    w.write_text(src)
    print("  web_server.cpp: added catalog entry")


def patch_knetwork(repo: Path) -> None:
    h = repo / "src" / "smart_hub.cpp"
    src = h.read_text()
    old = "for(uint8_t i=0;i<HUB_NETWORK_PAGE_COUNT;i++) {"
    new = "for(uint8_t i=0;i<sizeof(kNetworkPages)/sizeof(kNetworkPages[0]);i++) {"
    if old in src:
        h.write_text(src.replace(old, new))
        print("  smart_hub.cpp: fixed kNetworkPages loop bound")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    if not args.apply:
        raise SystemExit("refusing to modify without --apply")
    repo = Path(args.repo).resolve()
    print("Applying complete Sky Radar wiring:")
    try:
        patch_enum(repo)
        patch_display_dispatch(repo)
        patch_is_screen(repo)
        patch_hub_draw(repo)
        patch_advance(repo)
        patch_show_page(repo)
        patch_catalog(repo)
        patch_knetwork(repo)
    except PatchError as exc:
        raise SystemExit(f"FAILED: {exc}")
    print("Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
