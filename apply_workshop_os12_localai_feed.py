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
  // 12.7: the Local Portal's Local AI panel (never the key or the CA).
  const WorkshopLocalAiExtras extras = workshopLocalAiFeedExtras();
  char address[16];
  workshopLocalAiFeedAddress(address, sizeof(address));
  doc["address"] = address;
  doc["live"] = extras.live;
  doc["pictures"] = extras.imageCount;
  doc["approvalsWaiting"] = extras.approvalSeq ? (int)extras.approvalTotal : -1;
  doc["pairing"] = extras.pairBusy;
  doc["pairOk"] = extras.pairOk;
  doc["pairStatus"] = extras.pairSeq ? extras.pairStatus : "";
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

// 12.7: pair from the Local Portal: address and the 6-digit code Local AI shows (Services › Workshop display).
static void handleWorkshopLocalAiPair() {
  if (!server.hasArg("address") || !server.hasArg("code")) { server.send(400, "application/json", "{\"error\":\"address and code are required\"}"); return; }
  if (!workshopLocalAiFeedPair(server.arg("address").c_str(), server.arg("code").c_str())) {
    server.send(400, "application/json", "{\"error\":\"Use Local AI's address on this network and its 6-digit code (or wait: pairing is running).\"}");
    return;
  }
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
  SECURE_POST("/os12/localai/pair", handleWorkshopLocalAiPair);
'''

# 12.7: a Local AI panel in the Local Portal, beside the other Local AI keys: the link's state, pairing and unpairing.
PORTAL_ANCHOR = '  <section class="os12-integration os12-code-token" aria-labelledby="codeTokenTitle">'
PORTAL_PANEL = '''  <section class="os12-integration os12-localai-link" aria-labelledby="localAiLinkTitle"><small>LOCAL AI</small><h3 id="localAiLinkTitle">Local AI on the display</h3><p>Local AI's cards, answers, pictures, messages and approvals come to the display over this link. To connect, open Local AI's Services, Workshop display, Pair display, and type its 6-digit code here or on the display (Local AI tab, Local AI connection).</p><div class="os12-contract-row"><span>Connection</span><strong id="localAiLinkState">Checking…</strong></div><div class="os12-contract-row"><span>Local AI</span><strong id="localAiLinkAddress">—</strong></div><div class="os12-contract-row"><span>Cards</span><strong id="localAiLinkCards">—</strong></div><div class="os12-contract-row"><span>Pictures · approvals</span><strong id="localAiLinkMore">—</strong></div><form class="os12-feed-actions" onsubmit="pairLocalAi(event)"><input id="localAiPairAddress" class="form-control" inputmode="decimal" autocomplete="off" placeholder="10.0.0.21" aria-label="Local AI address" style="max-width:10rem"><input id="localAiPairCode" class="form-control" inputmode="numeric" pattern="[0-9]{6}" maxlength="6" autocomplete="one-time-code" placeholder="6-digit code" aria-label="Pairing code" style="max-width:9rem"><button type="submit" class="btn btn-primary btn-sm" id="localAiPairButton">Pair</button><button type="button" class="btn btn-danger btn-sm" onclick="unpairLocalAi()">Unpair</button></form><p class="small text-dim" id="localAiLinkStatus" role="status" aria-live="polite"></p></section>
'''
PORTAL_JS = r'''

/* Workshop OS 12.7: Local AI on the display (status, pairing, unpairing) */
async function loadLocalAiLink(){
  var state=document.getElementById('localAiLinkState');
  if(!state)return null;
  try{
    var r=await fetch('/os12/localai/status',{cache:'no-store',credentials:'same-origin'});
    if(r.status===401){state.textContent='Sign in required';return null;}
    var d=await r.json();
    var fresh=d.lastSuccessAgoS>=0&&d.lastSuccessAgoS<=600;
    state.textContent=!d.configured?'Not paired':fresh?(d.live?'Connected · live':'Connected'):(d.lastSuccessAgoS<0?'Connecting':'Not answering');
    document.getElementById('localAiLinkAddress').textContent=d.address||'—';
    document.getElementById('localAiLinkCards').textContent=d.configured?((d.cards||[]).map(function(c){return c.title;}).join(' · ')||'none')+(d.lastSuccessAgoS>=0?' ('+d.lastSuccessAgoS+' s ago)':''):'—';
    document.getElementById('localAiLinkMore').textContent=d.configured?(d.pictures||0)+' · '+(d.approvalsWaiting<0?'open the Local AI tab to check':d.approvalsWaiting+' waiting'):'—';
    var addr=document.getElementById('localAiPairAddress');
    if(addr&&!addr.value)addr.value=d.address||'10.0.0.21';
    if(d.pairStatus)document.getElementById('localAiLinkStatus').textContent=d.pairing?'Pairing…':d.pairStatus;
    return d;
  }catch(e){state.textContent='Unavailable';return null;}
}
async function pairLocalAi(ev){
  ev.preventDefault();
  var status=document.getElementById('localAiLinkStatus'),btn=document.getElementById('localAiPairButton');
  var address=document.getElementById('localAiPairAddress').value.trim(),code=document.getElementById('localAiPairCode').value.trim();
  if(!/^[0-9]{6}$/.test(code)){status.textContent='The code is 6 digits.';return;}
  btn.disabled=true;status.textContent='Pairing…';
  try{
    var r=await fetch('/os12/localai/pair',{method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded'},body:'address='+encodeURIComponent(address)+'&code='+encodeURIComponent(code),credentials:'same-origin'});
    var d=await r.json().catch(function(){return {};});
    if(!r.ok)throw new Error(d.error||('HTTP '+r.status));
    document.getElementById('localAiPairCode').value='';
    for(var i=0;i<30;i++){
      await new Promise(function(res){setTimeout(res,1000);});
      var s=await loadLocalAiLink();
      if(s&&!s.pairing){status.textContent=s.pairOk?'Paired with Local AI.':(s.pairStatus||'Pairing failed.');return;}
    }
    status.textContent='Still pairing. Check again in a moment.';
  }catch(e){status.textContent='Could not pair: '+e.message;}
  finally{btn.disabled=false;}
}
async function unpairLocalAi(){
  var status=document.getElementById('localAiLinkStatus');
  if(!status||!confirm('Unpair the display from Local AI? Its cards stop until you pair again.'))return;
  try{
    var r=await fetch('/os12/localai/clear',{method:'POST',credentials:'same-origin'});
    if(!r.ok)throw new Error('HTTP '+r.status);
    status.textContent='Unpaired. The key is forgotten on the display.';
  }catch(e){status.textContent='Could not unpair: '+e.message;}
  loadLocalAiLink();
}
setTimeout(loadLocalAiLink,0);
setInterval(function(){if(!document.hidden)loadLocalAiLink();},10000);
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

    pages = load("include/web_pages.h")
    if 'id="localAiLinkTitle"' not in pages:
        if pages.count(PORTAL_ANCHOR) != 1:
            raise PatchError("Local Portal anchor (sign-in code access panel) missing/non-unique")
        pages = pages.replace(PORTAL_ANCHOR, PORTAL_PANEL + PORTAL_ANCHOR, 1)
    staged[repo / "include/web_pages.h"] = pages
    app_js = load("web/app.js")
    if "pairLocalAi" not in app_js:
        app_js = app_js.rstrip("\n") + PORTAL_JS
    staged[repo / "web/app.js"] = app_js

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
