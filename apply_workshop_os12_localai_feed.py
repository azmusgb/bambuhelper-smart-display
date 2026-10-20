#!/usr/bin/env python3
"""Install the Local AI cards for the calm idle screen (Workshop OS 12.3.10).

Copies firmware/platform/localai (the rules header, the fetch service) into the tree, starts the service from
main.cpp beside Filament Inventory, includes it where the calm screen is drawn, and adds three portal routes:

  GET  /os12/localai/status   what the display last got (cards, when, why not); never the key or CA
  POST /os12/localai/config   address, name, key, ca (form fields); scripts/configure_localai_feed.py sends them
  POST /os12/localai/clear    forget the settings

The calm screen's drawing is in firmware/platform/ui/tabs_pages.cppfrag (wtDrawCalm, wtDrawCalmAiCard). Run after
apply_workshop_os12_tabs_overhaul.py. Every change is staged and written only after every anchor validates.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import sys as _sys
from pathlib import Path as _Path

_here = _Path(__file__).resolve().parent
if str(_here) not in _sys.path:
    _sys.path.insert(0, str(_here))

from scripts.smart_home_patch_utils import PatchError

FILES = {
    "workshop_localai_feed_core.hpp": "include",
    "workshop_localai_feed.h": "include",
    "workshop_localai_feed.cpp": "src",
}
INCLUDE = '#include "workshop_localai_feed.h"\n'

HANDLERS = r'''
// ---------------------------------------------------------------------------
// Workshop OS 12.3.10 -> Local AI cards for the calm idle screen
// ---------------------------------------------------------------------------
static void sendWorkshopLocalAiStatus(int httpCode = 200) {
  const WorkshopLocalAiFeedSnapshot snap = workshopLocalAiFeedSnapshot();
  JsonDocument doc;
  doc["configured"] = snap.configured;
  doc["busy"] = snap.busy;
  doc["failures"] = snap.failures;
  doc["lastSuccessAgoS"] = snap.lastSuccessAtMs ? (long)((millis() - snap.lastSuccessAtMs) / 1000UL) : -1L;
  doc["status"] = snap.status;
  doc["nvsFreeEntries"] = (unsigned)workshopLocalAiFeedNvsFreeEntries();
  JsonArray cards = doc["cards"].to<JsonArray>();
  for (uint8_t i = 0; i < snap.count; ++i) {
    JsonObject c = cards.add<JsonObject>();
    c["kind"] = snap.cards[i].kind;
    c["title"] = snap.cards[i].title;
    c["text"] = snap.cards[i].text;
  }
  String json;
  serializeJson(doc, json);
  server.sendHeader("Cache-Control", "no-store");
  server.send(httpCode, "application/json", json);
}

static void handleWorkshopLocalAiStatus() { sendWorkshopLocalAiStatus(); }

static void handleWorkshopLocalAiConfig() {
  for (const char* field : {"address", "name", "key", "ca"}) {
    if (!server.hasArg(field)) { server.send(400, "application/json", "{\"error\":\"address, name, key and ca are required\"}"); return; }
  }
  const bool ok = workshopLocalAiFeedConfigure(server.arg("address").c_str(), server.arg("name").c_str(),
                                               server.arg("key").c_str(), server.arg("ca").c_str());
  if (!ok) { sendWorkshopLocalAiStatus(400); return; }  // status says why: invalid settings, or storage full
  sendWorkshopLocalAiStatus(202);
}

static void handleWorkshopLocalAiClear() {
  workshopLocalAiFeedClear();
  sendWorkshopLocalAiStatus();
}
'''
# 12.4.0: the third tab is Local AI (its cards, then the workshop tools). /hub/views keeps the "workshop" id.
TAB_LABELS_OLD = 'static const char* labels[4]={"Home","Printer","Workshop","More"};'
TAB_LABELS_NEW = 'static const char* labels[4]={"Home","Printer","Local AI","More"};'
TAB_ICON_OLD = "hubV1125TabIcon(i,cx,r.y+16,fg);"
TAB_ICON_NEW = "if(i==2)wtDrawAiTabIcon(cx,r.y+16,fg);else hubV1125TabIcon(i,cx,r.y+16,fg);"
TAB_ICON_FN_ANCHOR = "static void uiBottomNav(uint8_t active,const char* nextPage) {"
TAB_ICON_FN = """// 12.4.0 Local AI tab icon: a four-point sparkle with a small one beside it.
static void wtDrawAiTabIcon(int16_t cx, int16_t cy, uint16_t c) {
  tft.fillTriangle(cx - 2, cy, cx + 2, cy, cx, cy - 9, c);
  tft.fillTriangle(cx - 2, cy, cx + 2, cy, cx, cy + 9, c);
  tft.fillTriangle(cx, cy - 2, cx, cy + 2, cx - 9, cy, c);
  tft.fillTriangle(cx, cy - 2, cx, cy + 2, cx + 9, cy, c);
  tft.fillCircle(cx + 9, cy - 7, 2, c);
}

"""
CATALOG_OLD = '{"id":"workshop","label":"Workshop","group":"Primary"}'
CATALOG_NEW = '{"id":"workshop","label":"Local AI","group":"Primary"}'

ROUTES = '''  SECURE_GET("/os12/localai/status", handleWorkshopLocalAiStatus);
  SECURE_POST("/os12/localai/config", handleWorkshopLocalAiConfig);
  SECURE_POST("/os12/localai/clear", handleWorkshopLocalAiClear);
'''


def insert_after_once(text: str, anchor: str, addition: str, label: str) -> str:
    if addition.strip() in text:
        return text
    count = text.count(anchor)
    if count != 1:
        raise PatchError(f"{label}: expected one anchor, found {count}")
    return text.replace(anchor, anchor + addition, 1)


def apply(repo: Path, source_root: Path) -> None:
    src = source_root / "firmware" / "platform" / "localai"
    staged: dict[Path, str] = {}
    for name, where in FILES.items():
        if not (src / name).is_file():
            raise PatchError(f"missing source asset: {src / name}")
        staged[repo / where / name] = (src / name).read_text(encoding="utf-8")

    def load(rel: str) -> str:
        p = repo / rel
        if p in staged:
            return staged[p]
        if not p.is_file():
            raise PatchError(f"missing reconstructed source: {p}")
        return p.read_text(encoding="utf-8")

    hub = load("src/smart_hub.cpp")
    if "wtDrawCalmAiCard(" not in hub:
        raise PatchError("the tabs overhaul with the 12.3.10 calm screen must be applied first")
    hub = insert_after_once(hub, '#include "workshop_tabs_layout.hpp"\n', INCLUDE, "smart_hub include")
    if TAB_LABELS_NEW not in hub:
        if hub.count(TAB_LABELS_OLD) != 1 or hub.count(TAB_ICON_OLD) != 1 or hub.count(TAB_ICON_FN_ANCHOR) != 1:
            raise PatchError("tab bar anchors missing/non-unique")
        hub = hub.replace(TAB_LABELS_OLD, TAB_LABELS_NEW, 1).replace(TAB_ICON_OLD, TAB_ICON_NEW, 1)
        hub = hub.replace(TAB_ICON_FN_ANCHOR, TAB_ICON_FN + TAB_ICON_FN_ANCHOR, 1)
    staged[repo / "src/smart_hub.cpp"] = hub

    main = load("src/main.cpp")
    main = insert_after_once(main, '#include "workshop_inventory_service.h"\n', INCLUDE, "main include")
    main = insert_after_once(main, "    workshopInventoryServiceBegin();\n", "    workshopLocalAiFeedBegin();\n", "feed begin")
    main = insert_after_once(main, "  workshopInventoryServiceLoop();\n", "  workshopLocalAiFeedLoop();\n", "feed loop")
    staged[repo / "src/main.cpp"] = main

    web = load("src/web_server.cpp")
    web = insert_after_once(web, '#include "workshop_inventory_service.h"\n', INCLUDE, "web include")
    if "sendWorkshopLocalAiStatus" not in web:
        marker = "void initWebServer() {\n"
        if web.count(marker) != 1:
            raise PatchError("web server init anchor missing/non-unique")
        web = web.replace(marker, HANDLERS + "\n" + marker, 1)
    web = insert_after_once(web, '  SECURE_POST("/os12/media/stop", handleWorkshopMediaStop);\n', ROUTES, "feed routes")
    if CATALOG_NEW not in web:
        if web.count(CATALOG_OLD) != 1:
            raise PatchError("catalog workshop entry missing/non-unique")
        web = web.replace(CATALOG_OLD, CATALOG_NEW, 1)
    staged[repo / "src/web_server.cpp"] = web

    for path, text in staged.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    print("Workshop OS 12.3.10 Local AI cards installed: calm screen card, /os12/localai/{status,config,clear}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True)
    parser.add_argument("--source-root", required=True)
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
