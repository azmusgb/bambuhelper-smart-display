#!/usr/bin/env python3
"""Install the Workshop OS 12 Filament Inventory device-feed consumer.

This layer is applied after portal hardening and device-update TLS plumbing. It
adds one read-only, profile-scoped Filament Inventory transport using the
revocable fi_dev_* credential. It never receives the browser sync key and never
derives inventory from printer/AMS telemetry.
"""
from __future__ import annotations

import argparse
import shutil
from pathlib import Path


class PatchError(RuntimeError):
    pass


def load(path: Path) -> str:
    if not path.is_file():
        raise PatchError(f"missing {path}")
    return path.read_text(encoding="utf-8")


def copy_exact(source: Path, destination: Path) -> None:
    if not source.is_file():
        raise PatchError(f"missing source asset: {source}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)


def insert_after_once(text: str, anchor: str, addition: str, label: str) -> str:
    if addition.strip() in text:
        return text
    count = text.count(anchor)
    if count != 1:
        raise PatchError(f"{label}: expected one anchor, found {count}")
    return text.replace(anchor, anchor + addition, 1)


def patch_service(repo: Path, source_root: Path) -> None:
    source = source_root / "firmware" / "platform" / "inventory"
    copy_exact(source / "workshop_inventory_service.h", repo / "include" / "workshop_inventory_service.h")
    copy_exact(source / "workshop_inventory_service.cpp", repo / "src" / "workshop_inventory_service.cpp")


def patch_main(repo: Path) -> None:
    path = repo / "src" / "main.cpp"
    text = load(path)
    text = insert_after_once(
        text,
        '#include "workshop_update_service.h"\n',
        '#include "workshop_inventory_service.h"\n',
        "inventory service include",
    )
    text = insert_after_once(
        text,
        "    workshopUpdateServiceBegin();\n",
        "    workshopInventoryServiceBegin();\n",
        "inventory service begin",
    )
    text = insert_after_once(
        text,
        "  workshopUpdateServiceLoop();\n",
        "  workshopInventoryServiceLoop();\n",
        "inventory service poll",
    )
    path.write_text(text, encoding="utf-8")


HANDLERS = r'''
// ---------------------------------------------------------------------------
// Workshop OS 12 -> Filament Inventory device-feed v1
// ---------------------------------------------------------------------------
static void sendWorkshopInventoryStatus(int httpCode = 200) {
  const WorkshopInventoryRuntimeSnapshot snap = workshopInventorySnapshot();
  JsonDocument doc;
  doc["available"] = snap.state.available;
  doc["credentialConfigured"] = snap.credentialConfigured;
  doc["busy"] = snap.busy;
  doc["freshness"] = snap.state.freshness == workshop::platform::Freshness::Fresh
      ? "Fresh"
      : snap.state.freshness == workshop::platform::Freshness::Stale
          ? "Stale"
          : snap.state.freshness == workshop::platform::Freshness::Conflicting
              ? "Conflicting" : "Unknown";
  const char* quantityState = "Unknown";
  switch (snap.state.quantityState) {
    case workshop::platform::InventoryQuantityState::Current: quantityState = "Current"; break;
    case workshop::platform::InventoryQuantityState::Stale: quantityState = "Stale"; break;
    case workshop::platform::InventoryQuantityState::Conflict: quantityState = "Conflict"; break;
    case workshop::platform::InventoryQuantityState::InvalidLineage: quantityState = "InvalidLineage"; break;
    case workshop::platform::InventoryQuantityState::Unknown:
    default: break;
  }
  const char* placementState = "Unknown";
  switch (snap.state.placementState) {
    case workshop::platform::InventoryPlacementState::Current: placementState = "Current"; break;
    case workshop::platform::InventoryPlacementState::Stale: placementState = "Stale"; break;
    case workshop::platform::InventoryPlacementState::Conflict: placementState = "Conflict"; break;
    case workshop::platform::InventoryPlacementState::Unknown:
    default: break;
  }
  const char* readiness = "Undetermined";
  switch (snap.state.readiness) {
    case workshop::platform::InventoryReadinessState::Ready: readiness = "Ready"; break;
    case workshop::platform::InventoryReadinessState::ReadyWithSubstitute: readiness = "ReadyWithSubstitute"; break;
    case workshop::platform::InventoryReadinessState::NeedsLoad: readiness = "NeedsLoad"; break;
    case workshop::platform::InventoryReadinessState::NeedsDry: readiness = "NeedsDry"; break;
    case workshop::platform::InventoryReadinessState::InsufficientQuantity: readiness = "InsufficientQuantity"; break;
    case workshop::platform::InventoryReadinessState::EvidenceStale: readiness = "EvidenceStale"; break;
    case workshop::platform::InventoryReadinessState::Undetermined:
    default: break;
  }
  doc["quantityState"] = quantityState;
  doc["placementState"] = placementState;
  doc["readiness"] = readiness;
  doc["profileId"] = snap.state.profileId;
  doc["spoolCount"] = snap.state.spoolCount;
  doc["loadedCount"] = snap.state.loadedCount;
  doc["lowCount"] = snap.state.lowCount;
  doc["unknownQuantityCount"] = snap.state.unknownQuantityCount;
  doc["staleQuantityCount"] = snap.state.staleQuantityCount;
  doc["quantityConflictCount"] = snap.state.conflictCount;
  doc["invalidLineageCount"] = snap.state.invalidLineageCount;
  doc["unknownPlacementCount"] = snap.state.unknownPlacementCount;
  doc["stalePlacementCount"] = snap.state.stalePlacementCount;
  doc["placementConflictCount"] = snap.state.placementConflictCount;
  doc["status"] = snap.statusMessage;
  String json;
  serializeJson(doc, json);
  server.sendHeader("Cache-Control", "no-store");
  server.send(httpCode, "application/json", json);
}

static void handleWorkshopInventoryStatus() {
  sendWorkshopInventoryStatus();
}

static void handleWorkshopInventoryRefresh() {
  const bool accepted = workshopInventoryRequestRefresh();
  sendWorkshopInventoryStatus(accepted ? 202 : 409);
}

static void handleWorkshopInventoryCredential() {
  if (!server.hasArg("token")) {
    server.send(400, "application/json", "{\"error\":\"token is required\"}");
    return;
  }
  const String token = server.arg("token");
  const bool accepted = workshopInventorySetDeviceCredential(token.c_str());
  sendWorkshopInventoryStatus(accepted ? 202 : 400);
}

static void handleWorkshopInventoryCredentialClear() {
  workshopInventoryClearDeviceCredential();
  sendWorkshopInventoryStatus();
}
'''


def patch_web_server(repo: Path) -> None:
    path = repo / "src" / "web_server.cpp"
    text = load(path)
    text = insert_after_once(
        text,
        '#include "workshop_update_service.h"\n',
        '#include "workshop_inventory_service.h"\n',
        "inventory web include",
    )
    if "sendWorkshopInventoryStatus" not in text:
        marker = "void initWebServer() {\n"
        if text.count(marker) != 1:
            raise PatchError("web server init anchor missing/non-unique")
        text = text.replace(marker, HANDLERS + "\n" + marker, 1)

    route_anchor = '  SECURE_POST("/os12/update/install", handleWorkshopUpdateInstall);\n'
    routes = '''  SECURE_GET("/os12/inventory/status", handleWorkshopInventoryStatus);
  SECURE_POST("/os12/inventory/refresh", handleWorkshopInventoryRefresh);
  SECURE_POST("/os12/inventory/credential", handleWorkshopInventoryCredential);
  SECURE_POST("/os12/inventory/credential/clear", handleWorkshopInventoryCredentialClear);
'''
    text = insert_after_once(text, route_anchor, routes, "inventory routes")
    path.write_text(text, encoding="utf-8")


INTEGRATION_OLD = '''<section class="os12-integration"><small>FILAMENT INVENTORY</small><h3>Device Feed v1</h3><p>Profile-scoped, evidence-aware contract. Until a validated feed is configured, inventory and readiness remain Unknown / Undetermined.</p><div class="os12-contract-row"><span>Schema</span><strong>device-feed/v1</strong></div><div class="os12-contract-row"><span>Inventory authority</span><strong>Filament Inventory</strong></div></section>'''

INTEGRATION_NEW = '''<section class="os12-integration" aria-labelledby="fiDeviceFeedTitle"><small>FILAMENT INVENTORY</small><h3 id="fiDeviceFeedTitle">Device Feed v1</h3><p>Uses a revocable, read-only WS350 token. The broader browser sync key and model/provider credentials never belong on this device.</p><div class="os12-contract-row"><span>Schema</span><strong>device-feed/v1</strong></div><div class="os12-contract-row"><span>Inventory authority</span><strong>Filament Inventory</strong></div><div class="os12-contract-row"><span>Device access</span><strong id="fiDeviceAccessState">Checking…</strong></div><label class="os12-feed-token"><span>WS350 device token</span><input id="fiDeviceToken" type="password" autocomplete="off" autocorrect="off" autocapitalize="off" spellcheck="false" placeholder="fi_dev_…" maxlength="50" aria-describedby="fiDeviceTokenHelp"></label><p class="small text-dim" id="fiDeviceTokenHelp">Create this token in Filament Inventory → Sync → WS350 device access. It can be revoked without changing browser sync.</p><div class="os12-feed-actions"><button type="button" class="btn btn-primary btn-sm" onclick="saveInventoryDeviceToken()">Save token</button><button type="button" class="btn btn-ghost btn-sm" onclick="refreshInventoryDeviceFeed()">Refresh</button><button type="button" class="btn btn-danger btn-sm" onclick="clearInventoryDeviceToken()">Remove access</button></div><p class="small text-dim" id="fiDeviceFeedStatus" role="status" aria-live="polite">Loading device-feed status…</p></section>'''


PORTAL_JS = r'''
/* Workshop OS 12 Filament Inventory device-feed controls */
async function loadInventoryDeviceFeedStatus(){
  var status=document.getElementById('fiDeviceFeedStatus');
  var access=document.getElementById('fiDeviceAccessState');
  if(!status||!access)return;
  try{
    var r=await fetch('/os12/inventory/status',{cache:'no-store',credentials:'same-origin'});
    if(r.status===401){access.textContent='Sign in required';status.textContent='Authenticate with the current Workshop OS access code to view device-feed status.';return;}
    var d=await r.json();
    access.textContent=d.credentialConfigured?'Configured':'Not configured';
    status.textContent=d.status||'Filament Inventory status unavailable.';
    var q=document.getElementById('fiQuantity'),qd=document.getElementById('fiQuantityDetail');
    var l=document.getElementById('fiLoaded'),ld=document.getElementById('fiLoadedDetail');
    var f=document.getElementById('fiFreshness'),fd=document.getElementById('fiFreshnessDetail');
    var ready=document.getElementById('fiReadiness');
    if(q){q.textContent=d.quantityState||'Unknown';}
    if(qd){qd.textContent=(d.spoolCount||0)+' spools · '+(d.unknownQuantityCount||0)+' unknown · '+(d.quantityConflictCount||0)+' conflicts';}
    if(l){l.textContent=d.placementState||'Unknown';}
    if(ld){ld.textContent=(d.loadedCount||0)+' canonically loaded · '+(d.placementConflictCount||0)+' placement conflicts';}
    if(f){f.textContent=d.freshness||'Unknown';}
    if(fd){fd.textContent=d.profileId?'Profile '+d.profileId:'No validated profile-scoped feed';}
    if(ready){ready.textContent=d.readiness||'Undetermined';}
  }catch(e){access.textContent='Unavailable';status.textContent='Could not read Filament Inventory device-feed status.';}
}
async function saveInventoryDeviceToken(){
  var input=document.getElementById('fiDeviceToken'),status=document.getElementById('fiDeviceFeedStatus');
  var token=(input&&input.value||'').trim();
  if(!/^fi_dev_[A-Za-z0-9_-]{43}$/.test(token)){if(status)status.textContent='Enter the complete fi_dev_… token created by Filament Inventory.';return;}
  if(status)status.textContent='Saving device access…';
  try{
    var r=await fetch('/os12/inventory/credential',{method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded'},body:'token='+encodeURIComponent(token),credentials:'same-origin'});
    if(input)input.value='';
    var d=await r.json();
    if(!r.ok)throw new Error(d.error||d.status||'save failed');
    await loadInventoryDeviceFeedStatus();
  }catch(e){if(status)status.textContent='Could not save device access: '+e.message;}
}
async function clearInventoryDeviceToken(){
  var status=document.getElementById('fiDeviceFeedStatus');
  if(status)status.textContent='Removing device access…';
  try{
    var r=await fetch('/os12/inventory/credential/clear',{method:'POST',credentials:'same-origin'});
    var d=await r.json();
    if(!r.ok)throw new Error(d.error||d.status||'remove failed');
    await loadInventoryDeviceFeedStatus();
  }catch(e){if(status)status.textContent='Could not remove device access: '+e.message;}
}
async function refreshInventoryDeviceFeed(){
  var status=document.getElementById('fiDeviceFeedStatus');
  if(status)status.textContent='Refreshing Filament Inventory…';
  try{
    var r=await fetch('/os12/inventory/refresh',{method:'POST',credentials:'same-origin'});
    var d=await r.json();
    if(!r.ok&&r.status!==409)throw new Error(d.error||d.status||'refresh failed');
    if(status)status.textContent=d.status||'Refresh requested.';
    setTimeout(loadInventoryDeviceFeedStatus,900);
  }catch(e){if(status)status.textContent='Could not refresh Filament Inventory: '+e.message;}
}
setTimeout(loadInventoryDeviceFeedStatus,0);
'''

PORTAL_CSS = r'''
.os12-feed-token{display:flex;flex-direction:column;gap:6px;margin-top:16px;max-width:620px}.os12-feed-token span{font-size:12px;font-weight:650}.os12-feed-token input{min-height:44px;border:1px solid var(--line-soft);border-radius:8px;background:var(--surface);color:var(--text);padding:0 12px;font:inherit}.os12-feed-token input:focus-visible{outline:2px solid var(--accent);outline-offset:2px}.os12-feed-actions{display:flex;gap:10px;flex-wrap:wrap;margin-top:12px}@media(max-width:600px){.os12-feed-actions .btn{width:100%;min-height:44px}}
'''


def patch_portal(repo: Path) -> None:
    html_path = repo / "include" / "web_pages.h"
    js_path = repo / "web" / "app.js"
    css_path = repo / "web" / "app.css"
    html = load(html_path)
    if INTEGRATION_NEW not in html:
        if html.count(INTEGRATION_OLD) != 1:
            raise PatchError("Filament Inventory integration panel anchor missing/non-unique")
        html = html.replace(INTEGRATION_OLD, INTEGRATION_NEW, 1)
        html_path.write_text(html, encoding="utf-8")
    js = load(js_path)
    if "loadInventoryDeviceFeedStatus" not in js:
        js += "\n" + PORTAL_JS + "\n"
        js_path.write_text(js, encoding="utf-8")
    css = load(css_path)
    if ".os12-feed-token" not in css:
        css += "\n" + PORTAL_CSS + "\n"
        css_path.write_text(css, encoding="utf-8")


def patch_build_identity(repo: Path) -> None:
    path = repo / "include" / "smart_home_build.h"
    text = load(path)
    marker = "#define WORKSHOP_OS12_INVENTORY_DEVICE_FEED 1"
    if marker not in text:
        text += "\n// Workshop OS 12 least-authority Filament Inventory consumer.\n" + marker + "\n"
        path.write_text(text, encoding="utf-8")


def apply(repo: Path, source_root: Path) -> None:
    if not (repo / "include" / "workshop_update_service.h").is_file():
        raise PatchError("OS12 inventory service requires device-update TLS plumbing first")
    if not (repo / "include" / "workshop_platform_bridge.h").is_file():
        raise PatchError("OS12 inventory service requires the platform bridge first")

    patch_service(repo, source_root)
    patch_main(repo)
    patch_web_server(repo)
    patch_portal(repo)
    patch_build_identity(repo)
    print("Workshop OS 12 Filament Inventory device-feed consumer installed")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    ap.add_argument("--source-root", default=str(Path(__file__).resolve().parent))
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    if not args.apply:
        raise SystemExit("refusing to modify source without --apply")
    try:
        apply(Path(args.repo).resolve(), Path(args.source_root).resolve())
    except PatchError as exc:
        raise SystemExit(f"FAIL: {exc}") from exc
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
