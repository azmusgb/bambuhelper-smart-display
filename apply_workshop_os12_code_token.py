#!/usr/bin/env python3
"""Install the Workshop OS sign-in code key (candidate 12.2.0).

A second device-issued key, separate from the read-only status token, so Local
AI's web page can show the current Local Portal sign-in code and the owner
does not have to walk to the display. Its only power is one route:

    GET /api/portal-code   Authorization: Bearer wsc_...
    -> 200 {"code":"ABCDEFGHJK","bootId":"0123456789abcdef"}   Cache-Control: no-store

* The key is created in the signed-in Local Portal (More -> Sign-in code
  access) and only after a tap on "Allow" on the touchscreen within 60 s
  ("Allow Local AI to show the sign-in code?"). It is shown once.
* Only its SHA-256 digest is stored (NVS ``workshop-sec``/``code_sha``, not the
  status token's ``lite_sha``). Creating a new key replaces the old one.
  Revoke and factory reset clear it.
* The key text is ``wsc_`` + 26 characters; the status token is ``wsl_`` + 26.
  Neither is accepted by the other's route, ``securityAuthorize()`` never reads
  either, and no other route accepts it.
* The route is rate-limited per client like /api/status/lite (one answer every
  2 s, back-off after bad keys), is refused while the client is locked out of
  sign-in, and every wrong key counts as a failed sign-in, so the route cannot
  be used to guess. Station Wi-Fi only.
* Neither the code nor the key is ever written to Serial or logs.
* The touchscreen Local Portal page shows whether the key is set up (the
  More overhaul, which runs next, draws that row).

Runs after apply_workshop_os12_status_lite.py and before
apply_workshop_os12_more_overhaul.py: the prompt is laid out with the More
layout's dialog geometry (workshop_more_layout.hpp, installed by the More
overhaul) and the More pages read workshopCodeTokenConfigured() and the
prompt's visibility.
"""
from __future__ import annotations

import argparse
import shutil
import sys as _sys
from pathlib import Path

_here = Path(__file__).resolve().parent
if str(_here) not in _sys.path:
    _sys.path.insert(0, str(_here))
from scripts.smart_home_patch_utils import PatchError  # noqa: E402

BUILD_MARKER = "#define WORKSHOP_OS_CODE_TOKEN 1"
STATUS_LITE_MARKER = "#define WORKSHOP_OS_STATUS_LITE_TOKEN 1"
MORE_OVERHAUL_MARKER = "#define WORKSHOP_OS12_MORE_OVERHAUL 1"

COPIES = (
    (Path("firmware/platform/code_token_core.hpp"), Path("include/workshop_platform/code_token_core.hpp")),
    (Path("firmware/platform/code_token/workshop_code_token.h"), Path("include/workshop_code_token.h")),
    (Path("firmware/platform/code_token/workshop_code_token.cpp"), Path("src/workshop_code_token.cpp")),
)

SECURITY_DECL_ANCHOR = "void securityResetPortalPolicy();\n"
SECURITY_DECL = '''
// Shared sign-in lock-out (per client address). The sign-in code key route
// refuses a client that is locked out and counts every wrong key as a failed
// sign-in, so it cannot be used to guess around the login back-off.
uint32_t securityLoginRetryAfter(WebServer& server);
void securityNoteLoginFailure(WebServer& server);
'''

SECURITY_IMPL_ANCHOR = "bool securityAuthorize(WebServer& server, bool mutating) {\n"
SECURITY_IMPL = '''uint32_t securityLoginRetryAfter(WebServer& server) {
  ensureInitialized();
  return retryAfterSeconds(server);
}

void securityNoteLoginFailure(WebServer& server) {
  ensureInitialized();
  noteLoginFailure(server);
}

'''

WEB_WRAPPERS = r'''
// ---------------------------------------------------------------------------
// Workshop OS sign-in code key management (session + same-origin only)
// ---------------------------------------------------------------------------
static void handleCodeTokenState() { workshopCodeTokenHandleState(server); }
static void handleCodeTokenCreate() { workshopCodeTokenHandleCreate(server); }
static void handleCodeTokenClaim() { workshopCodeTokenHandleClaim(server); }
static void handleCodeTokenRevoke() { workshopCodeTokenHandleRevoke(server); }

'''

STATUS_ROUTES_END = '  SECURE_POST("/api/status-token/revoke", handleStatusTokenRevoke);\n'
WEB_ROUTES = '''  // Sign-in code key. /api/portal-code checks its own bearer key ("wsc_...")
  // and never the portal session; it is deliberately not SECURE_GET. Key
  // management requires a signed-in, same-origin portal session.
  server.on("/api/portal-code", HTTP_GET, []() { workshopPortalCodeHandleRead(server); });
  SECURE_GET("/api/code-token", handleCodeTokenState);
  SECURE_POST("/api/code-token/create", handleCodeTokenCreate);
  SECURE_POST("/api/code-token/claim", handleCodeTokenClaim);
  SECURE_POST("/api/code-token/revoke", handleCodeTokenRevoke);
'''

FACTORY_RESET_OLD = "  workshopStatusTokenFactoryReset(); // status token does not survive factory reset\n"
FACTORY_RESET_NEW = (FACTORY_RESET_OLD +
                     "  workshopCodeTokenFactoryReset(); // sign-in code key does not survive factory reset\n")

HUB_PROMPT = r'''
// ---------------------------------------------------------------------------
// Sign-in code key consent prompt. Modal while visible: only Allow and Cancel
// respond. Laid out on the 12.1 More geometry: a header without Back, the
// More dialog card and its buttons in the content area, and an empty tab-bar
// band (the prompt is modal, so no tab is drawn there or live). Neither the
// key nor the code is drawn.
// ---------------------------------------------------------------------------
static bool g_codeTokenPromptShown = false;
static uint32_t g_codeTokenPromptSecond = 0;

static HubRect hubCodeTokenCancelRect() { return wsHub(wsm::dialogCancelRect(wsScreen())); }
static HubRect hubCodeTokenAllowRect() { return wsHub(wsm::dialogConfirmRect(wsScreen())); }

static void hubCodeTokenPromptService() {
  const bool visible=workshopCodeTokenPromptVisible();
  const uint32_t second=visible?workshopCodeTokenPromptSecondsLeft():0;
  if(visible!=g_codeTokenPromptShown||(visible&&second!=g_codeTokenPromptSecond))g_dirty=true;
}

static bool hubCodeTokenPromptDraw(bool force) {
  if(!workshopCodeTokenPromptVisible()){
    if(g_codeTokenPromptShown){g_codeTokenPromptShown=false;g_dirty=true;}
    return false;
  }
  const uint32_t second=workshopCodeTokenPromptSecondsLeft();
  if(g_codeTokenPromptShown&&!force&&!g_dirty&&second==g_codeTokenPromptSecond)return true;
  g_codeTokenPromptShown=true;g_codeTokenPromptSecond=second;
  const wsm::Screen s=wsScreen();
  tft.fillScreen(OS12V_BG);
  // Header: title, and a chip that counts down. No Back: the prompt is modal.
  tft.fillRoundRect(OS12V_INSET,12,4,20,2,OS12V_AMBER);
  const wsm::Rect title=wsm::titleRect(s,true,false);
  const wsm::Rect chip=wsm::chipRect(s);
  uiDrawFit("Local AI access",(int16_t)(title.x+10),(int16_t)(title.y+title.h/2),(int16_t)(chip.x-8-(title.x+10)),FONT_BODY,ML_DATUM,OS12V_TEXT,OS12V_BG);
  char left[24];snprintf(left,sizeof(left),"Allow? %lus",(unsigned long)second);
  tft.fillRoundRect(chip.x,chip.y,chip.w,chip.h,13,OS12V_SURFACE);
  tft.drawRoundRect(chip.x,chip.y,chip.w,chip.h,13,OS12V_LINE);
  tft.fillCircle(chip.x+12,chip.y+chip.h/2,4,OS12V_AMBER);
  uiDrawFit(left,(int16_t)(chip.x+22),(int16_t)(chip.y+chip.h/2),(int16_t)(chip.w-28),FONT_SMALL,ML_DATUM,OS12V_AMBER,OS12V_SURFACE);
  tft.drawFastHLine(OS12V_INSET,wsm::kHeaderH-1,s.w-OS12V_INSET*2,OS12V_LINE);
  // The question, on the More dialog card (inside the content area).
  const wsm::Rect card=wsm::dialogCard(s);
  hubV1125Card(wsHub(card),OS12V_AMBER,true);
  const int16_t x=(int16_t)(card.x+16),w=(int16_t)(card.w-32);
  const uint8_t lines=s.landscape()?2:3;
  uiDrawFit("Allow Local AI to show the sign-in code?",x,(int16_t)(card.y+14),w,FONT_BODY,TL_DATUM,OS12V_TEXT,OS12V_SURFACE2);
  wsDrawWrapped("Local AI's page will show the code you type to sign in here, so you don't have to come to the display.",
                x,(int16_t)(card.y+46),w,22,lines,FONT_SMALL,OS12V_MUTED,OS12V_SURFACE2);
  wsDrawWrapped("Anyone with this key can sign in to the Local Portal. Replaces any earlier sign-in code key.",
                x,(int16_t)(card.y+46+22*lines+8),w,22,lines,FONT_SMALL,OS12V_AMBER,OS12V_SURFACE2);
  hubV1125Action(hubCodeTokenCancelRect(),"Cancel",OS12V_ACCENT,true,false);
  hubV1125Action(hubCodeTokenAllowRect(),"Allow",OS12V_AMBER,true,false);
  hubMarkFrameDirty();g_dirty=false;
  return true;
}

static bool hubCodeTokenPromptTouch(int16_t x,int16_t y) {
  if(!workshopCodeTokenPromptVisible())return false;
  if(hubCodeTokenAllowRect().contains(x,y)){workshopCodeTokenAllow();g_dirty=true;return true;}
  if(hubCodeTokenCancelRect().contains(x,y)){workshopCodeTokenDeny();g_dirty=true;return true;}
  return true;
}

'''

DRAW_OLD = ("  if (hubStatusTokenPromptDraw(effectiveForce)) {\n"
            "    // The consent prompt owns the frame while it is visible.\n"
            "  } else switch (screen) {")
DRAW_NEW = ("  if (hubStatusTokenPromptDraw(effectiveForce)) {\n"
            "    // The consent prompt owns the frame while it is visible.\n"
            "  } else if (hubCodeTokenPromptDraw(effectiveForce)) {\n"
            "    // So does the sign-in code key prompt (one question at a time).\n"
            "  } else switch (screen) {")

TOUCH_OLD = "  if(hubStatusTokenPromptTouch(x,y))return true;\n"
TOUCH_NEW = TOUCH_OLD + "  if(hubCodeTokenPromptTouch(x,y))return true;\n"

HOLD_OLD = "  if(workshopStatusTokenPromptVisible())return;\n"
HOLD_NEW = HOLD_OLD + "  if(workshopCodeTokenPromptVisible())return;\n"

SERVICE_OLD = "  hubStatusTokenPromptService();\n"
SERVICE_NEW = SERVICE_OLD + "  hubCodeTokenPromptService();\n"

PORTAL_ANCHOR = '  <section class="os12-integration" aria-labelledby="fiDeviceFeedTitle">'
PORTAL_PANEL = '''  <section class="os12-integration os12-code-token" aria-labelledby="codeTokenTitle"><small>LOCAL AI</small><h3 id="codeTokenTitle">Sign-in code access</h3><p>Lets Local AI show the code you use to sign in to this Local Portal, so you don't have to walk to the display. Anyone who has this key can read the code and sign in, so keep it only in Local AI. It is a separate key from read-only status access and opens nothing else. Creating it asks you to tap Allow on the display, and replaces any earlier key.</p><div class="os12-contract-row"><span>Route</span><strong>GET /api/portal-code</strong></div><div class="os12-contract-row"><span>Access</span><strong id="codeTokenState">Checking…</strong></div><div class="os12-feed-actions"><button type="button" class="btn btn-primary btn-sm" id="codeTokenCreate" onclick="createCodeToken()">Create</button><button type="button" class="btn btn-danger btn-sm" onclick="revokeCodeToken()">Revoke</button></div><div id="codeTokenReveal" hidden><label class="os12-feed-token"><span>Copy this key now. It will not be shown again.</span><input id="codeTokenValue" type="text" readonly autocomplete="off" autocorrect="off" autocapitalize="off" spellcheck="false"></label></div><p class="small text-dim" id="codeTokenStatus" role="status" aria-live="polite"></p></section>
'''

PORTAL_JS = r'''

/* Workshop OS sign-in code key (Local AI) */
async function loadCodeTokenState(){
  var state=document.getElementById('codeTokenState');
  if(!state)return null;
  try{
    var r=await fetch('/api/code-token',{cache:'no-store',credentials:'same-origin'});
    if(r.status===401){state.textContent='Sign in required';return null;}
    var d=await r.json();
    state.textContent=d.configured?'On (one key)':'Off';
    return d;
  }catch(e){state.textContent='Unavailable';return null;}
}
function codeTokenSleep(ms){return new Promise(function(res){setTimeout(res,ms);});}
async function createCodeToken(){
  var status=document.getElementById('codeTokenStatus'),btn=document.getElementById('codeTokenCreate');
  var reveal=document.getElementById('codeTokenReveal'),value=document.getElementById('codeTokenValue');
  if(!status)return;
  reveal.hidden=true;value.value='';btn.disabled=true;
  try{
    var r=await fetch('/api/code-token/create',{method:'POST',credentials:'same-origin'});
    var d=await r.json();
    if(!r.ok)throw new Error(d.message||'request refused');
    var id=d.requestId;
    status.textContent='Tap Allow on the display within '+d.secondsLeft+' seconds.';
    for(var i=0;i<70;i++){
      await codeTokenSleep(1000);
      var s=await loadCodeTokenState();
      if(!s)continue;
      if(s.phase==='pending'){status.textContent='Tap Allow on the display ('+s.secondsLeft+' s left).';continue;}
      if(s.phase==='approved'){
        var c=await fetch('/api/code-token/claim',{method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded'},body:'requestId='+encodeURIComponent(id),credentials:'same-origin'});
        var t=await c.json();
        if(!c.ok||!t.token)throw new Error(t.message||'key could not be collected');
        value.value=t.token;reveal.hidden=false;value.focus();value.select();
        status.textContent='Key created. Any earlier sign-in code key no longer works.';
        await loadCodeTokenState();return;
      }
      if(s.phase==='denied'){status.textContent='Cancelled on the display. Nothing changed.';return;}
      if(s.phase==='expired'){status.textContent='Timed out. Try again and tap Allow on the display.';return;}
    }
    status.textContent='Timed out. Try again.';
  }catch(e){status.textContent='Could not create the key: '+e.message;}
  finally{btn.disabled=false;}
}
async function revokeCodeToken(){
  var status=document.getElementById('codeTokenStatus');
  if(!status||!confirm('Revoke Local AI sign-in code access?'))return;
  document.getElementById('codeTokenReveal').hidden=true;document.getElementById('codeTokenValue').value='';
  try{
    var r=await fetch('/api/code-token/revoke',{method:'POST',credentials:'same-origin'});
    if(!r.ok)throw new Error('HTTP '+r.status);
    status.textContent='Key revoked.';
  }catch(e){status.textContent='Could not revoke: '+e.message;}
  loadCodeTokenState();
}
setTimeout(loadCodeTokenState,0);
'''


def load(path: Path) -> str:
    if not path.exists():
        raise PatchError(f"missing {path}")
    return path.read_text(encoding="utf-8")


def save(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise PatchError(f"{label}: expected exactly one anchor, found {count}")
    return text.replace(old, new, 1)


def install_sources(repo: Path, source_root: Path) -> None:
    for source, target in COPIES:
        src = source_root / source
        if not src.is_file():
            raise PatchError(f"missing source {src}")
        dst = repo / target
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)


def patch_security(repo: Path) -> None:
    header_path = repo / "include" / "security_manager.h"
    header = load(header_path)
    header = replace_once(header, SECURITY_DECL_ANCHOR, SECURITY_DECL_ANCHOR + SECURITY_DECL, "lock-out declarations")
    save(header_path, header)

    path = repo / "src" / "security_manager.cpp"
    text = load(path)
    text = replace_once(text, SECURITY_IMPL_ANCHOR, SECURITY_IMPL + SECURITY_IMPL_ANCHOR, "lock-out wrappers")
    save(path, text)


def patch_web_server(repo: Path) -> None:
    path = repo / "src" / "web_server.cpp"
    text = load(path)
    text = replace_once(text, '#include "workshop_status_lite.h"\n',
                        '#include "workshop_status_lite.h"\n#include "workshop_code_token.h"\n', "code key include")
    anchor = "// ---------------------------------------------------------------------------\n// Smart Home v8 route-policy wrappers"
    text = replace_once(text, anchor, WEB_WRAPPERS.lstrip("\n") + anchor, "code key wrappers")
    text = replace_once(text, STATUS_ROUTES_END, STATUS_ROUTES_END + WEB_ROUTES, "code key routes")
    text = replace_once(text, FACTORY_RESET_OLD, FACTORY_RESET_NEW, "factory reset clears code key")
    save(path, text)


def patch_smart_hub(repo: Path) -> None:
    path = repo / "src" / "smart_hub.cpp"
    text = load(path)
    text = replace_once(text, '#include "workshop_status_lite.h"\n',
                        '#include "workshop_status_lite.h"\n#include "workshop_code_token.h"\n', "hub code key include")
    anchor = "void smartHubInit() {\n  if (g_initialized) return;"
    text = replace_once(text, anchor, HUB_PROMPT.lstrip("\n") + anchor, "code key prompt helpers")
    text = replace_once(text, DRAW_OLD, DRAW_NEW, "code key prompt draw hook")
    text = replace_once(text, TOUCH_OLD, TOUCH_NEW, "code key prompt touch hook")
    text = replace_once(text, HOLD_OLD, HOLD_NEW, "code key prompt suppresses hold progress")
    text = replace_once(text, SERVICE_OLD, SERVICE_NEW, "code key prompt service hook")
    save(path, text)


def patch_portal(repo: Path) -> None:
    html_path = repo / "include" / "web_pages.h"
    html = load(html_path)
    if 'id="statusTokenTitle"' not in html:
        raise PatchError("status token portal panel missing; the code key panel sits next to it")
    html = replace_once(html, PORTAL_ANCHOR, PORTAL_PANEL + PORTAL_ANCHOR, "code key portal panel")
    save(html_path, html)

    js_path = repo / "web" / "app.js"
    js = load(js_path)
    if "createCodeToken" in js:
        raise PatchError("code key portal script already present")
    save(js_path, js.rstrip("\n") + PORTAL_JS)


def apply(repo: Path, source_root: Path) -> None:
    build_path = repo / "include" / "smart_home_build.h"
    build = load(build_path)
    if STATUS_LITE_MARKER not in build:
        raise PatchError("the sign-in code key requires the 12.1.0 status token (apply_workshop_os12_status_lite.py)")
    if MORE_OVERHAUL_MARKER in build:
        raise PatchError("the sign-in code key must be applied before apply_workshop_os12_more_overhaul.py")
    if BUILD_MARKER in build:
        raise PatchError("sign-in code key overlay is already applied")
    install_sources(repo, source_root)
    patch_security(repo)
    patch_web_server(repo)
    patch_smart_hub(repo)
    patch_portal(repo)
    save(build_path, build.rstrip() + "\n" + BUILD_MARKER + "\n")
    print("Workshop OS sign-in code key installed")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    ap.add_argument("--source-root", default=str(_here))
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    if not args.apply:
        raise SystemExit("refusing to modify source without --apply")
    try:
        apply(Path(args.repo).resolve(), Path(args.source_root).resolve())
    except PatchError as exc:
        raise SystemExit(f"FAIL: {exc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
