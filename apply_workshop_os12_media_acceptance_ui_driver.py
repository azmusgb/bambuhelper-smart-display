#!/usr/bin/env python3
"""Install a narrow OS12 media-acceptance UI driver into reconstructed firmware.

This is a test/acceptance control surface, not a second UI authority. It only
navigates the native Workshop OS touchscreen to the existing Media or Media Lab
views so host acceptance can visibly exercise the same device surfaces while it
calls the bounded MediaService diagnostics API.
"""
from __future__ import annotations

import argparse
from pathlib import Path


class PatchError(RuntimeError):
    pass


HEADER = """#pragma once

#include <stdint.h>

// Acceptance-only navigation into existing native media views.
// 10 = Media, 11 = Media Lab.
bool workshopMediaAcceptanceShowView(uint8_t view);
"""

IMPL = r'''
// OS12 media physical-acceptance UI driver.
// This does not synthesize touches or duplicate media behavior. It selects the
// existing native More -> Media / Media Lab views and lets normal rendering own
// the screen. It is injected beside the native Media renderers so it inherits
// the same board/preprocessor boundary as those WS350 UI internals.
bool workshopMediaAcceptanceShowView(uint8_t view) {
  if (view != 10U && view != 11U) return false;
  setPage(SCREEN_HUB_MORE);
  g_ui12SettingsView = view;
  g_dirty = true;
  hubMarkFrameDirty();
  return true;
}
'''

STUB = r'''#include "workshop_media_acceptance_ui.h"

// Cross-board fallback. WS350 provides the strong implementation from
// smart_hub.cpp inside the native Media UI compilation boundary.
bool __attribute__((weak)) workshopMediaAcceptanceShowView(uint8_t) {
  return false;
}
'''

WEB_INCLUDE = '#include "workshop_media_acceptance_ui.h"\n'

WEB_HANDLERS = r'''
static void handleWorkshopMediaAcceptanceShowMedia() {
  const bool ok = workshopMediaAcceptanceShowView(10U);
  sendWorkshopMediaStatus(ok ? 200 : 409);
}

static void handleWorkshopMediaAcceptanceShowLab() {
  const bool ok = workshopMediaAcceptanceShowView(11U);
  sendWorkshopMediaStatus(ok ? 200 : 409);
}
'''

ROUTES = '''  SECURE_POST("/os12/media/acceptance/show-media", handleWorkshopMediaAcceptanceShowMedia);\n  SECURE_POST("/os12/media/acceptance/show-lab", handleWorkshopMediaAcceptanceShowLab);\n'''


def load(path: Path) -> str:
    if not path.is_file():
        raise PatchError(f"missing reconstructed source: {path}")
    return path.read_text(encoding="utf-8")


def apply(repo: Path) -> None:
    hub = repo / "src" / "smart_hub.cpp"
    web = repo / "src" / "web_server.cpp"
    header = repo / "include" / "workshop_media_acceptance_ui.h"
    stub = repo / "src" / "workshop_media_acceptance_ui.cpp"

    hub_text = load(hub)
    web_text = load(web)
    if "static void drawOs12Media()" not in hub_text or "static void drawOs12MediaLab()" not in hub_text:
        raise PatchError("native OS12 Media/Media Lab views must exist first")
    if "sendWorkshopMediaStatus" not in web_text:
        raise PatchError("OS12 media API must exist before acceptance UI driver")

    header.parent.mkdir(parents=True, exist_ok=True)
    header.write_text(HEADER, encoding="utf-8")
    stub.write_text(STUB, encoding="utf-8")

    if "bool workshopMediaAcceptanceShowView(uint8_t view)" not in hub_text:
        anchor = "static void drawUi13PrinterAlerts() {"
        if hub_text.count(anchor) != 1:
            raise PatchError("native Media renderer boundary anchor missing/non-unique")
        hub_text = hub_text.replace(anchor, IMPL.strip() + "\n\n" + anchor, 1)
        hub.write_text(hub_text, encoding="utf-8")

    if WEB_INCLUDE.strip() not in web_text:
        anchor = '#include "workshop_media_runtime.h"\n'
        if web_text.count(anchor) != 1:
            raise PatchError("media runtime include anchor missing/non-unique")
        web_text = web_text.replace(anchor, anchor + WEB_INCLUDE, 1)

    if "handleWorkshopMediaAcceptanceShowMedia" not in web_text:
        marker = "\nvoid initWebServer() {\n"
        if web_text.count(marker) != 1:
            raise PatchError("web init anchor missing/non-unique")
        web_text = web_text.replace(marker, "\n" + WEB_HANDLERS.strip() + marker, 1)

    if '/os12/media/acceptance/show-media' not in web_text:
        route_anchor = '  SECURE_POST("/os12/media/stop", handleWorkshopMediaStop);\n'
        if web_text.count(route_anchor) != 1:
            raise PatchError("media stop route anchor missing/non-unique")
        web_text = web_text.replace(route_anchor, route_anchor + ROUTES, 1)

    web.write_text(web_text, encoding="utf-8")

    final_hub = load(hub)
    final_web = load(web)
    for needle in (
        "workshopMediaAcceptanceShowView(10U)",
        "workshopMediaAcceptanceShowView(11U)",
        '/os12/media/acceptance/show-media',
        '/os12/media/acceptance/show-lab',
    ):
        if needle not in final_hub and needle not in final_web:
            raise PatchError(f"acceptance UI driver missing after patch: {needle}")

    print("Workshop OS 12 media acceptance UI driver installed")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    if not args.apply:
        raise SystemExit("refusing to modify source without --apply")
    try:
        apply(Path(args.repo).resolve())
    except PatchError as exc:
        raise SystemExit(f"FAIL: {exc}") from exc
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
