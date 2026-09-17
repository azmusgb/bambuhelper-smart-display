#!/usr/bin/env python3
"""Apply Workshop OS 12 portal/control-plane v4 after the physical-fit UX layer.

This is the final reconstructed-source layer for the browser portal. It does not
modify frozen historical patchers. It establishes one Workshop OS identity,
Home/Printer/Workshop/More IA, truth-preserving inventory language, a persisted
portal-code policy, and the Filament Inventory device-feed v1 presentation
contract.
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path


class PatchError(RuntimeError):
    pass


def load(path: Path) -> str:
    if not path.exists():
        raise PatchError(f"missing {path}")
    return path.read_text(encoding="utf-8")


def save(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise PatchError(f"{label}: expected exactly one match, found {count}")
    return text.replace(old, new, 1)


def replace_between(text: str, start: str, end: str, replacement: str, label: str) -> str:
    a = text.find(start)
    if a < 0:
        raise PatchError(f"{label}: start marker missing")
    b = text.find(end, a + len(start))
    if b < 0:
        raise PatchError(f"{label}: end marker missing")
    return text[:a] + replacement.rstrip() + "\n\n" + text[b:]


def block_end(text: str, start: int) -> int:
    brace = text.find("{", start)
    if brace < 0:
        raise PatchError("opening brace missing")
    depth = 0
    quote: str | None = None
    escape = False
    line_comment = False
    block_comment = False
    i = brace
    while i < len(text):
        c = text[i]
        n = text[i + 1] if i + 1 < len(text) else ""
        if line_comment:
            if c == "\n":
                line_comment = False
        elif block_comment:
            if c == "*" and n == "/":
                block_comment = False
                i += 1
        elif quote:
            if escape:
                escape = False
            elif c == "\\":
                escape = True
            elif c == quote:
                quote = None
        elif c == "/" and n == "/":
            line_comment = True
            i += 1
        elif c == "/" and n == "*":
            block_comment = True
            i += 1
        elif c in ('"', "'"):
            quote = c
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    raise PatchError("unterminated braced block")


def replace_block(text: str, signature: str, replacement: str, label: str) -> str:
    start = text.find(signature)
    if start < 0 or text.find(signature, start + 1) >= 0:
        raise PatchError(f"{label}: signature missing/non-unique")
    return text[:start] + replacement.rstrip() + text[block_end(text, start):]


HOME = r'''<!-- ===== Workshop OS 12 control-plane Home ===== -->
<div class="section os12-home" id="sec-home" hidden>
  <header class="os12-page-head">
    <div><span class="os12-eyebrow">WORKSHOP OS</span><h2>Workshop at a glance</h2><p>Printer state, authoritative inventory evidence and device health.</p></div>
    <div class="os12-health"><span class="hh-orb" id="hhOverallOrb"></span><div><strong id="hhOverall">Checking…</strong><small id="hhUpdated">Reading local state</small></div></div>
  </header>
  <div class="os12-overview">
    <button type="button" class="os12-overview-row" onclick="loadSection('printer')"><span><small>PRINTER</small><strong id="hhPrinterState">Checking…</strong></span><span id="hhPrinterDetail">Selected printer</span></button>
    <button type="button" class="os12-overview-row" onclick="loadSection('workshop')"><span><small>INVENTORY</small><strong>Unknown</strong></span><span>No authoritative Filament Inventory evidence</span></button>
    <button type="button" class="os12-overview-row" onclick="loadSection('workshop')"><span><small>PRINT READINESS</small><strong>Undetermined</strong></span><span>Print requirements unavailable</span></button>
    <button type="button" class="os12-overview-row" onclick="loadSection('more')"><span><small>DEVICE</small><strong id="hhDeviceState">Checking…</strong></span><span id="hhDeviceDetail">WS350 control plane</span></button>
  </div>
  <section class="os12-attention" aria-live="polite"><div><small>ATTENTION</small><strong id="hhAttentionTitle">Checking workshop state…</strong><p id="hhAttentionText">Only authoritative inventory evidence will appear as inventory.</p></div></section>
  <div class="os12-primary-actions"><button type="button" class="btn btn-primary" onclick="loadSection('printer')">Printer</button><button type="button" class="btn btn-ghost" onclick="loadSection('workshop')">Workshop</button><button type="button" class="btn btn-ghost" onclick="loadSection('more')">More</button></div>
</div>'''

WORKSHOP = r'''<!-- ===== Workshop OS 12 Workshop workspace ===== -->
<div class="section os12-workshop" id="sec-workshop" hidden>
  <header class="os12-page-head"><div><span class="os12-eyebrow">WORKSHOP</span><h2>Can I print this now?</h2><p>Inventory facts come only from Filament Inventory. Printer telemetry is shown separately.</p></div></header>
  <div class="os12-evidence-list">
    <div class="os12-evidence-row"><span><small>PRINT READINESS</small><strong id="fiReadiness">Undetermined</strong></span><span id="fiReadinessDetail">Print requirements unavailable</span></div>
    <div class="os12-evidence-row"><span><small>LOADED INVENTORY</small><strong id="fiLoaded">Unknown</strong></span><span id="fiLoadedDetail">Canonical placement unavailable</span></div>
    <div class="os12-evidence-row"><span><small>QUANTITY EVIDENCE</small><strong id="fiQuantity">Unknown</strong></span><span id="fiQuantityDetail">No authoritative quantity evidence</span></div>
    <div class="os12-evidence-row"><span><small>FRESHNESS</small><strong id="fiFreshness">Unknown</strong></span><span id="fiFreshnessDetail">Device feed not configured</span></div>
  </div>
  <section class="os12-source-note"><strong>Filament Inventory is the source of truth.</strong><p>AMS material, color and tray metadata reported by the printer are telemetry only and never create spool identity, ownership, quantity or placement.</p></section>
  <section class="os12-printer-telemetry"><div><small>PRINTER TELEMETRY</small><strong id="wkState">Checking…</strong><span id="wkUpdated">Reading printer state</span></div><button type="button" class="btn btn-ghost btn-sm" onclick="loadSection('printer')">Open Printer</button></section>
</div>'''

MORE = r'''<!-- ===== Workshop OS 12 More ===== -->
<div class="section os12-more" id="sec-more" hidden>
  <header class="os12-page-head"><div><span class="os12-eyebrow">MORE</span><h2>Device settings</h2><p>Secondary controls stay out of the primary workspace.</p></div></header>
  <div class="os12-settings-list">
    <button type="button" onclick="loadSection('display')"><span><strong>Display</strong><small>Brightness, standby and print presentation</small></span><b>›</b></button>
    <button type="button" onclick="loadSection('hardware')"><span><strong>Sound &amp; Hardware</strong><small>Speaker, microphone, touch and board hardware</small></span><b>›</b></button>
    <button type="button" onclick="loadSection('wifi')"><span><strong>Network &amp; Updates</strong><small>Wi-Fi, firmware, backup and restore</small></span><b>›</b></button>
    <button type="button" onclick="loadSection('power')"><span><strong>Power &amp; Automation</strong><small>Smart plugs and power rules</small></span><b>›</b></button>
    <button type="button" onclick="loadSection('errors')"><span><strong>Printer Errors</strong><small>HMS reporting and alert behavior</small></span><b>›</b></button>
    <button type="button" onclick="loadSection('diag')"><span><strong>System</strong><small>Diagnostics, recovery and advanced operations</small></span><b>›</b></button>
  </div>
  <section class="os12-security-panel" aria-labelledby="portalSecurityTitle">
    <div><small>PORTAL SECURITY</small><h3 id="portalSecurityTitle">Require access code</h3><p>When off, read-only portal pages open directly on this LAN. Changes still require an authenticated session and same-origin protection.</p></div>
    <div class="os12-security-control"><label for="portalCodeRequired">Require access code</label><input id="portalCodeRequired" type="checkbox" checked><button type="button" class="btn btn-primary btn-sm" onclick="savePortalSecurity()">Save</button></div>
    <p class="small text-dim" id="portalSecurityStatus" role="status" aria-live="polite">Loading security policy…</p>
  </section>
  <section class="os12-integration"><small>FILAMENT INVENTORY</small><h3>Device Feed v1</h3><p>Profile-scoped, evidence-aware contract. Until a validated feed is configured, inventory and readiness remain Unknown / Undetermined.</p><div class="os12-contract-row"><span>Schema</span><strong>device-feed/v1</strong></div><div class="os12-contract-row"><span>Inventory authority</span><strong>Filament Inventory</strong></div></section>
</div>'''

SIDEBAR = r'''<aside class="sidebar" id="sidebar">
  <div class="portal-nav-brand"><span class="portal-nav-mark">OS</span><span><strong>Workshop OS</strong><small>WS350 · 12.0.0</small></span></div>
  <h4>Workspaces</h4>
  <button class="nav-item" type="button" data-section="home" aria-current="true"><span>Home</span></button>
  <button class="nav-item" type="button" data-section="printer"><span>Printer</span></button>
  <button class="nav-item" type="button" data-section="workshop"><span>Workshop</span></button>
  <button class="nav-item" type="button" data-section="more"><span>More</span></button>
  <div class="sidebar-footer"><div><strong>Workshop OS 12.0.0</strong></div><div style="margin-top:2px">WS350 · local control plane</div></div>
</aside>'''

CSS = r'''
/* Workshop OS 12 portal control-plane v4 */
.os12-page-head{display:flex;justify-content:space-between;gap:24px;align-items:flex-start;margin:0 0 24px}.os12-page-head h2{margin:4px 0 6px;font-size:28px;letter-spacing:-.025em}.os12-page-head p{margin:0;color:var(--text-mid);max-width:680px;line-height:1.5}.os12-eyebrow,.os12-overview-row small,.os12-evidence-row small,.os12-attention small,.os12-security-panel>div>small,.os12-integration>small,.os12-printer-telemetry small{font-size:11px;font-weight:750;letter-spacing:.09em;color:var(--text-dim)}.os12-health{display:flex;align-items:center;gap:10px;min-width:170px}.os12-health div{display:flex;flex-direction:column;gap:2px}.os12-health small{color:var(--text-dim)}.os12-overview,.os12-evidence-list,.os12-settings-list{border-top:1px solid var(--line-soft)}.os12-overview-row,.os12-settings-list>button{width:100%;display:flex;align-items:center;justify-content:space-between;gap:24px;text-align:left;background:transparent;color:var(--text);border:0;border-bottom:1px solid var(--line-soft);padding:16px 4px;min-height:64px}.os12-overview-row>span:first-child{display:flex;flex-direction:column;gap:4px;min-width:180px}.os12-overview-row>span:last-child{color:var(--text-mid);text-align:right}.os12-overview-row:hover,.os12-settings-list>button:hover{background:color-mix(in srgb,var(--accent) 5%,transparent)}.os12-attention,.os12-source-note,.os12-security-panel,.os12-integration,.os12-printer-telemetry{margin-top:22px;padding:18px 0;border-top:1px solid var(--line-soft)}.os12-attention strong,.os12-source-note strong{display:block;margin:5px 0}.os12-attention p,.os12-source-note p,.os12-security-panel p,.os12-integration p{color:var(--text-mid);line-height:1.5;margin:6px 0 0}.os12-primary-actions{display:flex;gap:10px;flex-wrap:wrap;margin-top:20px}.os12-evidence-row{display:grid;grid-template-columns:minmax(180px,.7fr) minmax(220px,1.3fr);gap:28px;padding:16px 4px;border-bottom:1px solid var(--line-soft)}.os12-evidence-row>span{display:flex;flex-direction:column;gap:4px}.os12-evidence-row>span:last-child{color:var(--text-mid)}.os12-printer-telemetry{display:flex;justify-content:space-between;align-items:center;gap:20px}.os12-printer-telemetry>div{display:flex;flex-direction:column;gap:4px}.os12-settings-list>button span{display:flex;flex-direction:column;gap:3px}.os12-settings-list>button small{color:var(--text-mid);font-size:12px;font-weight:400}.os12-settings-list>button b{font-size:24px;font-weight:300;color:var(--text-dim)}.os12-security-panel,.os12-integration{max-width:760px}.os12-security-control{display:grid;grid-template-columns:1fr auto auto;gap:12px;align-items:center;margin-top:16px}.os12-security-control input{width:22px;height:22px}.os12-contract-row{display:flex;justify-content:space-between;gap:20px;padding:12px 0;border-bottom:1px solid var(--line-soft)}.os12-contract-row span{color:var(--text-mid)}.section>.card{box-shadow:none}.section .card .card{box-shadow:none}.section-intro{margin-bottom:20px}.section-intro p{max-width:760px}.card{border-color:var(--line-soft)}@media(max-width:760px){.os12-page-head{display:block}.os12-health{margin-top:14px}.os12-evidence-row{grid-template-columns:1fr;gap:7px}.os12-overview-row{align-items:flex-start}.os12-overview-row>span:last-child{text-align:left}.os12-security-control{grid-template-columns:1fr auto}.os12-security-control button{grid-column:1/-1}.os12-printer-telemetry{align-items:flex-start;flex-direction:column}}
'''

JS = r'''

/* Workshop OS 12 portal control-plane v4 */
async function loadPortalSecurity(){
  var el=document.getElementById('portalCodeRequired'),status=document.getElementById('portalSecurityStatus');
  if(!el)return;
  try{
    var r=await fetch('/api/portal-security',{cache:'no-store',credentials:'same-origin'});
    if(r.status===401){status.textContent='Sign in with the current device code to view or change security policy.';return;}
    var d=await r.json();
    el.checked=!!d.requirePortalCode;
    status.textContent=d.requirePortalCode?'Access code is required for portal browsing.':'Read-only portal browsing is open on this LAN; changes still require authentication.';
  }catch(e){status.textContent='Security policy unavailable.';}
}
async function savePortalSecurity(){
  var el=document.getElementById('portalCodeRequired'),status=document.getElementById('portalSecurityStatus');
  if(!el)return;
  status.textContent='Saving…';
  try{
    var r=await fetch('/api/portal-security',{method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded'},body:'required='+(el.checked?'1':'0'),credentials:'same-origin'});
    if(r.status===401){status.textContent='Authentication required. Open /login, enter the device code, then retry.';return;}
    var d=await r.json();
    if(!r.ok)throw new Error(d.message||d.error||'save failed');
    el.checked=!!d.requirePortalCode;
    status.textContent=d.requirePortalCode?'Access code enabled.':'Access code disabled for read-only LAN browsing; authenticated sessions are still required for changes.';
  }catch(e){status.textContent='Could not save portal security: '+e.message;}
}
setTimeout(loadPortalSecurity,0);
'''

SECURITY_API_DECL = r'''
bool securityPortalCodeRequired();
bool securitySetPortalCodeRequired(bool required);
void securityResetPortalPolicy();'''

SECURITY_STATE = r'''
constexpr char kPortalPolicyNamespace[] = "workshop-sec";
constexpr char kPortalPolicyKey[] = "portal_lock";
bool g_portalPolicyLoaded = false;
bool g_requirePortalCode = true;

void loadPortalPolicy() {
  if (g_portalPolicyLoaded) return;
  Preferences prefs;
  if (prefs.begin(kPortalPolicyNamespace, true)) {
    g_requirePortalCode = prefs.getBool(kPortalPolicyKey, true);
    prefs.end();
  } else {
    g_requirePortalCode = true;
  }
  g_portalPolicyLoaded = true;
}
'''

SECURITY_AUTHORIZE = r'''bool securityAuthorize(WebServer& server, bool mutating) {
  ensureInitialized();

  if (apPublicRouteAllowed(server)) {
    if (mutating && !sameOrigin(server)) {
      server.send(403, "application/json",
          "{\"status\":\"error\",\"message\":\"Rejected by Workshop OS same-origin protection.\"}");
      return false;
    }
    return true;
  }

  if (mutating && !sameOrigin(server)) {
    server.send(403, "application/json",
        "{\"status\":\"error\",\"message\":\"Rejected by Workshop OS same-origin protection.\"}");
    return false;
  }

  // Disabling the portal lock opens read-only station-LAN browsing only.
  // Every mutation still requires a valid portal session.
  if (!mutating && !securityPortalCodeRequired()) return true;
  if (cookieMatches(server)) return true;

  if (mutating) {
    server.send(401, "application/json",
        "{\"status\":\"error\",\"message\":\"Authentication required for Workshop OS changes.\"}");
  } else {
    server.sendHeader("Location", "/login");
    server.send(303, "text/plain", "Authentication required");
  }
  return false;
}'''

SECURITY_PUBLIC = r'''
bool securityPortalCodeRequired() {
  loadPortalPolicy();
  return g_requirePortalCode;
}

bool securitySetPortalCodeRequired(bool required) {
  loadPortalPolicy();
  Preferences prefs;
  if (!prefs.begin(kPortalPolicyNamespace, false)) return false;
  const size_t written = prefs.putBool(kPortalPolicyKey, required);
  prefs.end();
  if (written == 0) return false;
  g_requirePortalCode = required;
  return true;
}

void securityResetPortalPolicy() {
  Preferences prefs;
  if (prefs.begin(kPortalPolicyNamespace, false)) {
    prefs.remove(kPortalPolicyKey);
    prefs.end();
  }
  g_requirePortalCode = true;
  g_portalPolicyLoaded = true;
}
'''

WEB_HANDLERS = r'''
static void handlePortalSecurityStatus(){
  if(!securityAuthorize(server,false)) return;
  JsonDocument d;
  d["requirePortalCode"]=securityPortalCodeRequired();
  d["authMode"]=securityPortalCodeRequired()?"portal-code":"open-readonly";
  d["mutationsRequireSession"]=true;
  d["sameOriginProtection"]=true;
  String out;serializeJson(d,out);server.sendHeader("Cache-Control","no-store");server.send(200,"application/json",out);
}
static void handlePortalSecuritySave(){
  if(!securityAuthorize(server,true)) return;
  if(!server.hasArg("required")){server.send(400,"application/json","{\"status\":\"error\",\"message\":\"required is missing\"}");return;}
  String raw=server.arg("required");raw.toLowerCase();
  const bool required=(raw=="1"||raw=="true"||raw=="on");
  if(!securitySetPortalCodeRequired(required)){server.send(500,"application/json","{\"status\":\"error\",\"message\":\"Portal security policy could not be persisted.\"}");return;}
  JsonDocument d;d["status"]="ok";d["requirePortalCode"]=securityPortalCodeRequired();String out;serializeJson(d,out);server.send(200,"application/json",out);
}
'''


def patch_html(repo: Path) -> None:
    p = repo / "include" / "web_pages.h"
    text = load(p)
    if "Workshop OS 12 control-plane Home" in text:
        return

    text = text.replace("<title>Waveshare Home</title>", "<title>Workshop OS</title>")
    text = text.replace('<div class="mark">WH</div>', '<div class="mark">OS</div>')
    text = text.replace('<span>Waveshare Home</span>', '<span>Workshop OS</span>')
    text = re.sub(r'<span class="version-pill">Workshop OS · v[^<]+</span>', '<span class="version-pill">Workshop OS · 12.0.0</span>', text, count=1)

    aside_start = '<aside class="sidebar" id="sidebar">'
    a = text.find(aside_start)
    if a < 0:
        raise PatchError("portal sidebar missing")
    b = text.find('</aside>', a)
    if b < 0:
        raise PatchError("portal sidebar end missing")
    text = text[:a] + SIDEBAR + text[b + len('</aside>'):]

    text = replace_between(text,
        '<!-- ===== Smart Home v10.4.1 workshop-first Home ===== -->',
        '<!-- ===== Workshop workspace ===== -->', HOME, "Home consolidation")
    text = replace_between(text,
        '<!-- ===== Workshop workspace ===== -->',
        '<!-- ===== Section 1: Printer ===== -->', WORKSHOP, "Workshop authority cleanup")

    insert = '<!-- ===== Section 2: Display ===== -->'
    if insert not in text:
        raise PatchError("Display section marker missing")
    text = text.replace(insert, MORE + "\n\n" + insert, 1)

    # Remove invalid duplicate style attribute observed on the legacy cloud-password wrapper.
    text = text.replace('id="cl_passWrap" style="display:none" style="display:none"', 'id="cl_passWrap" style="display:none"')

    # Repair the recurring invalid label-inside-label pattern without changing input IDs.
    nested = re.compile(r'(<label class="check-row"[^>]*>\s*)(<input[^>]*>)(\s*)<label for="([^"]+)">(.*?)</label>\s*</label>', re.S)
    text, repairs = nested.subn(lambda m: m.group(1) + m.group(2) + m.group(3) + '<span>' + m.group(5) + '</span></label>', text)
    if repairs == 0:
        raise PatchError("nested-label correctness repair matched nothing")

    replacements = {
        'ACTIVE MATERIAL':'PRINTER-REPORTED MATERIAL',
        'Loaded tray':'Printer-reported slot',
        'Waiting for AMS / external spool data':'Printer telemetry is not inventory evidence',
        'Waiting for AMS data':'Printer telemetry available separately',
        'Filament &amp; AMS':'Printer material telemetry',
        'Smart Display Platform':'Display platform',
        'Enable Smart Display pages':'Enable device pages',
        'Smart HOME replaces the legacy idle clock.':'Workshop OS manages the idle display.',
    }
    for old,new in replacements.items():
        text = text.replace(old,new)

    save(p, text)


def patch_js_css(repo: Path) -> None:
    js_path = repo / "web" / "app.js"
    js = load(js_path)
    if "Workshop OS 12 portal control-plane v4" not in js:
        # Extend the section title registry without coupling to its historic formatting.
        m = re.search(r"const SECTION_LABELS\s*=\s*\{(.*?)\};", js, re.S)
        if m:
            body = m.group(1)
            if "more:" not in body:
                body = body.rstrip() + ",\n  more: 'More'\n"
                js = js[:m.start(1)] + body + js[m.end(1):]
        else:
            m = re.search(r"var SECTION_LABELS\s*=\s*\{(.*?)\};", js, re.S)
            if not m:
                raise PatchError("SECTION_LABELS registry missing")
            body = m.group(1)
            if "more:" not in body:
                body = body.rstrip() + ",\n  more: 'More'\n"
                js = js[:m.start(1)] + body + js[m.end(1):]
        js += JS
        save(js_path, js)

    css_path = repo / "web" / "app.css"
    css = load(css_path)
    if "Workshop OS 12 portal control-plane v4" not in css:
        save(css_path, css + CSS)


def patch_security(repo: Path) -> None:
    hp = repo / "include" / "security_manager.h"
    header = load(hp)
    if "securityPortalCodeRequired" not in header:
        header = header.rstrip() + "\n" + SECURITY_API_DECL + "\n"
        save(hp, header)

    cp = repo / "src" / "security_manager.cpp"
    text = load(cp)
    if "kPortalPolicyNamespace" in text:
        return
    if "#include <Preferences.h>" not in text:
        include_anchor = '#include "security_manager.h"\n'
        text = replace_once(text, include_anchor, include_anchor + '#include <Preferences.h>\n', "Preferences include")

    state_anchor = "bool g_initialized = false;"
    if state_anchor not in text:
        raise PatchError("security initialized-state anchor missing")
    text = text.replace(state_anchor, state_anchor + "\n" + SECURITY_STATE, 1)

    # Load persisted policy as part of security initialization.
    init_sig = "void ensureInitialized()"
    start = text.find(init_sig)
    if start < 0:
        raise PatchError("ensureInitialized missing")
    brace = text.find("{", start)
    text = text[:brace + 1] + "\n  loadPortalPolicy();" + text[brace + 1:]

    text = replace_block(text, "bool securityAuthorize(WebServer& server, bool mutating)", SECURITY_AUTHORIZE, "authorization policy")

    # Public persisted-policy API is outside the anonymous helper namespace boundary.
    insert_at = text.find("bool securitySessionValid(WebServer& server)")
    if insert_at < 0:
        raise PatchError("security public API anchor missing")
    text = text[:insert_at] + SECURITY_PUBLIC + "\n" + text[insert_at:]
    save(cp, text)


def patch_web_server(repo: Path) -> None:
    p = repo / "src" / "web_server.cpp"
    text = load(p)
    if "handlePortalSecurityStatus" not in text:
        anchor = "static void handlePortalLoginPage()"
        pos = text.find(anchor)
        if pos < 0:
            raise PatchError("portal login handler anchor missing")
        text = text[:pos] + WEB_HANDLERS + "\n" + text[pos:]

        route_anchor = 'server.on("/login", HTTP_GET, handlePortalLoginPage);'
        if route_anchor not in text:
            raise PatchError("portal login route anchor missing")
        routes = route_anchor + '\n  server.on("/api/portal-security", HTTP_GET, handlePortalSecurityStatus);\n  server.on("/api/portal-security", HTTP_POST, handlePortalSecuritySave);'
        text = text.replace(route_anchor, routes, 1)

    # Runtime diagnostics must report the actual policy, not a compile-time label.
    text = text.replace('d["authMode"]=ap?(recoverySafeModeActive()?"recovery-safe-mode":"setup-ap"):WORKSHOP_OS_AUTH_MODE;',
                        'd["authMode"]=ap?(recoverySafeModeActive()?"recovery-safe-mode":"setup-ap"):(securityPortalCodeRequired()?"portal-code":"open-readonly");')

    # Factory-reset route is historically /reset. Ensure its handler restores secure default.
    # Patch the first function whose body contains the factory-reset settings clear and restart.
    if "securityResetPortalPolicy(); // OS12 secure factory default" not in text:
        candidates = ["static void handleReset()", "static void handleFactoryReset()", "void handleReset()", "void handleFactoryReset()"]
        patched = False
        for sig in candidates:
            s = text.find(sig)
            if s < 0:
                continue
            e = block_end(text, s)
            body = text[s:e]
            if "reset" in body.lower() or "restart" in body.lower() or "clear" in body.lower():
                brace = body.find("{")
                body = body[:brace + 1] + "\n  securityResetPortalPolicy(); // OS12 secure factory default" + body[brace + 1:]
                text = text[:s] + body + text[e:]
                patched = True
                break
        if not patched:
            raise PatchError("factory reset handler not found; refusing to ship portal policy without reset-to-secure default")

    save(p, text)


def patch_identity(repo: Path) -> None:
    p = repo / "include" / "smart_home_build.h"
    text = load(p)
    # Keep historical compatibility macros but make current user-facing identity unambiguous.
    if '#define WORKSHOP_OS_PORTAL_CONTROL_PLANE_V4 1' not in text:
        text += '\n#define WORKSHOP_OS_PORTAL_CONTROL_PLANE_V4 1\n#define WORKSHOP_OS_DEVICE_FEED_SCHEMA 1\n'
    save(p, text)


def apply(repo: Path) -> None:
    build = repo / "include" / "smart_home_build.h"
    if "WORKSHOP_OS_RELEASE_VERSION" not in load(build):
        raise PatchError("portal control-plane v4 requires reconstructed Workshop OS 12 source")
    patch_identity(repo)
    patch_html(repo)
    patch_js_css(repo)
    patch_security(repo)
    patch_web_server(repo)
    print("Workshop OS 12 portal control-plane v4 applied")


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
        raise SystemExit(f"FAIL: {exc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
