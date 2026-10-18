#!/usr/bin/env python3
"""Install the Workshop OS read-only status token (candidate 12.1.0).

Adds exactly one token-checked route, ``GET /api/status/lite``, for Local AI's
Home line. It answers a minimal printer summary (connection, activity,
freshness, age, progress, time left, error summary) to a client that presents
the current device-issued bearer token. No job name, IP, MAC or serial.

* The token is created in the signed-in Local Portal and only after a tap on
  "Allow" on the touchscreen within 60 s. It is shown once.
* Only its SHA-256 digest is stored (NVS ``workshop-sec``/``lite_sha``).
  Creating a new token replaces the old one. Revoke and factory reset clear it.
* The route is rate-limited per client (one answer every 2 s, exponential
  backoff after bad tokens) and served on station Wi-Fi only.
* The token opens nothing else: ``securityAuthorize()`` never reads it, the
  route never reads the portal session, and there is no control access.

Requires the 12.0.1 portal sign-in restore (session-protected management).
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

BUILD_MARKER = "#define WORKSHOP_OS_STATUS_LITE_TOKEN 1"

COPIES = (
    (Path("firmware/platform/status_lite_core.hpp"), Path("include/workshop_platform/status_lite_core.hpp")),
    (Path("firmware/platform/status_lite/workshop_status_lite.h"), Path("include/workshop_status_lite.h")),
    (Path("firmware/platform/status_lite/workshop_status_lite.cpp"), Path("src/workshop_status_lite.cpp")),
)

WEB_WRAPPERS = r'''
// ---------------------------------------------------------------------------
// Workshop OS read-only status token management (session + same-origin only)
// ---------------------------------------------------------------------------
static void handleStatusTokenState() { workshopStatusTokenHandleState(server); }
static void handleStatusTokenCreate() { workshopStatusTokenHandleCreate(server); }
static void handleStatusTokenClaim() { workshopStatusTokenHandleClaim(server); }
static void handleStatusTokenRevoke() { workshopStatusTokenHandleRevoke(server); }

'''

WEB_ROUTES = '''  // Read-only status token. /api/status/lite checks its own bearer token and
  // never the portal session; it is deliberately not SECURE_GET. Token
  // management requires a signed-in, same-origin portal session.
  server.on("/api/status/lite", HTTP_GET, []() { workshopStatusLiteHandleRead(server); });
  SECURE_GET("/api/status-token", handleStatusTokenState);
  SECURE_POST("/api/status-token/create", handleStatusTokenCreate);
  SECURE_POST("/api/status-token/claim", handleStatusTokenClaim);
  SECURE_POST("/api/status-token/revoke", handleStatusTokenRevoke);
'''

HUB_PROMPT = r'''
// ---------------------------------------------------------------------------
// Read-only status token consent prompt. Modal while visible: only Allow and
// Cancel respond. The token itself is never drawn on the touchscreen.
// ---------------------------------------------------------------------------
static bool g_statusTokenPromptShown = false;
static uint32_t g_statusTokenPromptSecond = 0;

static HubRect hubStatusTokenCancelRect() {
  const int16_t W=tft.width(),H=tft.height();const int16_t bw=(int16_t)((W-OS12_MARGIN_X*2-12)/2);
  return hr(OS12_MARGIN_X,(int16_t)(H-68),bw,56);
}

static HubRect hubStatusTokenAllowRect() {
  const int16_t W=tft.width(),H=tft.height();const int16_t bw=(int16_t)((W-OS12_MARGIN_X*2-12)/2);
  return hr((int16_t)(OS12_MARGIN_X+bw+12),(int16_t)(H-68),bw,56);
}

static void hubStatusTokenPromptService() {
  const bool visible=workshopStatusTokenPromptVisible();
  const uint32_t second=visible?workshopStatusTokenPromptSecondsLeft():0;
  if(visible!=g_statusTokenPromptShown||(visible&&second!=g_statusTokenPromptSecond))g_dirty=true;
}

static bool hubStatusTokenPromptDraw(bool force) {
  if(!workshopStatusTokenPromptVisible()){
    if(g_statusTokenPromptShown){g_statusTokenPromptShown=false;g_dirty=true;}
    return false;
  }
  const uint32_t second=workshopStatusTokenPromptSecondsLeft();
  if(g_statusTokenPromptShown&&!force&&!g_dirty&&second==g_statusTokenPromptSecond)return true;
  g_statusTokenPromptShown=true;g_statusTokenPromptSecond=second;
  const int16_t W=tft.width(),H=tft.height();
  tft.fillScreen(OS12V_BG);drawHeader("Local AI access","ALLOW?",3);
  HubRect card=hr(OS12_MARGIN_X,48,(int16_t)(W-OS12_MARGIN_X*2),(int16_t)(H-48-80));
  hubV1125Card(card,OS12V_AMBER,true);
  uiDrawFit("Allow Local AI to read printer status?",card.x+16,card.y+14,card.w-32,FONT_BODY,TL_DATUM,OS12V_TEXT,OS12V_SURFACE2);
  uiDrawFit("Read only: printer state, progress, time left and errors.",card.x+16,card.y+48,card.w-32,FONT_SMALL,TL_DATUM,OS12V_MUTED,OS12V_SURFACE2);
  uiDrawFit("No controls, camera, settings or job names.",card.x+16,card.y+72,card.w-32,FONT_SMALL,TL_DATUM,OS12V_MUTED,OS12V_SURFACE2);
  uiDrawFit("Replaces any earlier Local AI access.",card.x+16,card.y+96,card.w-32,FONT_SMALL,TL_DATUM,OS12V_MUTED,OS12V_SURFACE2);
  char left[64];snprintf(left,sizeof(left),"Requested from Local Portal - %lus left",(unsigned long)second);
  uiDrawFit(left,card.x+16,(int16_t)(card.y+card.h-12),card.w-32,FONT_SMALL,BL_DATUM,OS12V_AMBER,OS12V_SURFACE2);
  hubV1125Action(hubStatusTokenCancelRect(),"Cancel",OS12V_ACCENT,true,false);
  hubV1125Action(hubStatusTokenAllowRect(),"Allow",OS12V_ACCENT,true,false);
  hubMarkFrameDirty();g_dirty=false;
  return true;
}

static bool hubStatusTokenPromptTouch(int16_t x,int16_t y) {
  if(!workshopStatusTokenPromptVisible())return false;
  if(hubStatusTokenAllowRect().contains(x,y)){workshopStatusTokenAllow();g_dirty=true;return true;}
  if(hubStatusTokenCancelRect().contains(x,y)){workshopStatusTokenDeny();g_dirty=true;return true;}
  return true;
}

'''

PORTAL_PANEL = '''  <section class="os12-integration os12-status-token" aria-labelledby="statusTokenTitle"><small>LOCAL AI</small><h3 id="statusTokenTitle">Read-only status access</h3><p>Lets Local AI show printer state, progress, time left and errors. It can read one status summary and nothing else: no controls, camera, settings, job names or network details. Creating access asks you to tap Allow on the display, and replaces any earlier access.</p><div class="os12-contract-row"><span>Route</span><strong>GET /api/status/lite</strong></div><div class="os12-contract-row"><span>Access</span><strong id="statusTokenState">Checking…</strong></div><div class="os12-feed-actions"><button type="button" class="btn btn-primary btn-sm" id="statusTokenCreate" onclick="createStatusToken()">Create access</button><button type="button" class="btn btn-danger btn-sm" onclick="revokeStatusToken()">Revoke</button></div><label class="os12-feed-token" id="statusTokenReveal" hidden><span>Copy this token now. It will not be shown again.</span><input id="statusTokenValue" type="text" readonly autocomplete="off" autocorrect="off" autocapitalize="off" spellcheck="false"></label><p class="small text-dim" id="statusTokenStatus" role="status" aria-live="polite"></p></section>
'''

PORTAL_JS = r'''

/* Workshop OS read-only status token (Local AI) */
async function loadStatusTokenState(){
  var state=document.getElementById('statusTokenState');
  if(!state)return null;
  try{
    var r=await fetch('/api/status-token',{cache:'no-store',credentials:'same-origin'});
    if(r.status===401){state.textContent='Sign in required';return null;}
    var d=await r.json();
    state.textContent=d.configured?'On (one token)':'Off';
    return d;
  }catch(e){state.textContent='Unavailable';return null;}
}
function statusTokenSleep(ms){return new Promise(function(res){setTimeout(res,ms);});}
async function createStatusToken(){
  var status=document.getElementById('statusTokenStatus'),btn=document.getElementById('statusTokenCreate');
  var reveal=document.getElementById('statusTokenReveal'),value=document.getElementById('statusTokenValue');
  if(!status)return;
  reveal.hidden=true;value.value='';btn.disabled=true;
  try{
    var r=await fetch('/api/status-token/create',{method:'POST',credentials:'same-origin'});
    var d=await r.json();
    if(!r.ok)throw new Error(d.message||'request refused');
    var id=d.requestId;
    status.textContent='Tap Allow on the display within '+d.secondsLeft+' seconds.';
    for(var i=0;i<70;i++){
      await statusTokenSleep(1000);
      var s=await loadStatusTokenState();
      if(!s)continue;
      if(s.phase==='pending'){status.textContent='Tap Allow on the display ('+s.secondsLeft+' s left).';continue;}
      if(s.phase==='approved'){
        var c=await fetch('/api/status-token/claim',{method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded'},body:'requestId='+encodeURIComponent(id),credentials:'same-origin'});
        var t=await c.json();
        if(!c.ok||!t.token)throw new Error(t.message||'token could not be collected');
        value.value=t.token;reveal.hidden=false;value.focus();value.select();
        status.textContent='Access created. Any earlier token no longer works.';
        await loadStatusTokenState();return;
      }
      if(s.phase==='denied'){status.textContent='Cancelled on the display. Nothing changed.';return;}
      if(s.phase==='expired'){status.textContent='Timed out. Try again and tap Allow on the display.';return;}
    }
    status.textContent='Timed out. Try again.';
  }catch(e){status.textContent='Could not create access: '+e.message;}
  finally{btn.disabled=false;}
}
async function revokeStatusToken(){
  var status=document.getElementById('statusTokenStatus');
  if(!status||!confirm('Revoke Local AI read-only status access?'))return;
  document.getElementById('statusTokenReveal').hidden=true;document.getElementById('statusTokenValue').value='';
  try{
    var r=await fetch('/api/status-token/revoke',{method:'POST',credentials:'same-origin'});
    if(!r.ok)throw new Error('HTTP '+r.status);
    status.textContent='Access revoked.';
  }catch(e){status.textContent='Could not revoke: '+e.message;}
  loadStatusTokenState();
}
setTimeout(loadStatusTokenState,0);
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


def patch_web_server(repo: Path) -> None:
    path = repo / "src" / "web_server.cpp"
    text = load(path)
    text = replace_once(text, '#include "security_manager.h"\n',
                        '#include "security_manager.h"\n#include "workshop_status_lite.h"\n', "status lite include")
    anchor = "// ---------------------------------------------------------------------------\n// Smart Home v8 route-policy wrappers"
    text = replace_once(text, anchor, WEB_WRAPPERS.lstrip("\n") + anchor, "status token wrappers")
    text = replace_once(text, "  server.onNotFound([]() { if (securityAuthorize(server, false)) handleNotFound(); });\n",
                        WEB_ROUTES + "  server.onNotFound([]() { if (securityAuthorize(server, false)) handleNotFound(); });\n",
                        "status lite routes")
    text = replace_once(text, '    "Cookie"\n  };', '    "Cookie",\n    "Authorization"\n  };', "collect Authorization header")
    text = replace_once(text, "  securityResetPortalPolicy(); // OS12 secure factory default\n",
                        "  securityResetPortalPolicy(); // OS12 secure factory default\n"
                        "  workshopStatusTokenFactoryReset(); // status token does not survive factory reset\n",
                        "factory reset clears status token")
    save(path, text)


def patch_smart_hub(repo: Path) -> None:
    path = repo / "src" / "smart_hub.cpp"
    text = load(path)
    text = replace_once(text, '#include "smart_hub.h"\n', '#include "smart_hub.h"\n#include "workshop_status_lite.h"\n',
                        "hub status lite include")
    # Before smartHubInit/Service/Draw/HandleTouch, which all use the helpers.
    anchor = "void smartHubInit() {\n  if (g_initialized) return;"
    text = replace_once(text, anchor, HUB_PROMPT.lstrip("\n") + anchor, "consent prompt helpers")
    text = replace_once(
        text,
        "  switch (screen) {\n    case SCREEN_HUB_HOME:     drawHome(effectiveForce);     break;",
        "  if (hubStatusTokenPromptDraw(effectiveForce)) {\n"
        "    // The consent prompt owns the frame while it is visible.\n"
        "  } else switch (screen) {\n    case SCREEN_HUB_HOME:     drawHome(effectiveForce);     break;",
        "consent prompt draw hook",
    )
    text = replace_once(
        text,
        "int16_t x=0,y=0;mapHubTouch(rawX,rawY,x,y);ScreenState cur=getScreenState();",
        "int16_t x=0,y=0;mapHubTouch(rawX,rawY,x,y);ScreenState cur=getScreenState();\n"
        "  if(hubStatusTokenPromptTouch(x,y))return true;",
        "consent prompt touch hook",
    )
    text = replace_once(
        text,
        "if(!g_cfg.enabled||!smartHubIsScreen(getScreenState()))return;",
        "if(!g_cfg.enabled||!smartHubIsScreen(getScreenState()))return;\n"
        "  if(workshopStatusTokenPromptVisible())return;",
        "consent prompt suppresses hold progress",
    )
    text = replace_once(
        text,
        "  if (!g_initialized) smartHubInit();\n  unsigned long now = millis();\n",
        "  if (!g_initialized) smartHubInit();\n  unsigned long now = millis();\n  hubStatusTokenPromptService();\n",
        "consent prompt service hook",
    )
    save(path, text)


def patch_portal(repo: Path) -> None:
    html_path = repo / "include" / "web_pages.h"
    html = load(html_path)
    anchor = '  <section class="os12-integration" aria-labelledby="fiDeviceFeedTitle">'
    html = replace_once(html, anchor, PORTAL_PANEL + anchor, "status token portal panel")
    save(html_path, html)

    js_path = repo / "web" / "app.js"
    js = load(js_path)
    if "createStatusToken" in js:
        raise PatchError("status token portal script already present")
    save(js_path, js.rstrip("\n") + PORTAL_JS)


def apply(repo: Path, source_root: Path) -> None:
    build_path = repo / "include" / "smart_home_build.h"
    build = load(build_path)
    if "#define WORKSHOP_OS_PORTAL_SIGNIN_RESTORED 1" not in build:
        raise PatchError("status token requires the 12.0.1 portal sign-in restore")
    if BUILD_MARKER in build:
        raise PatchError("status token overlay is already applied")
    install_sources(repo, source_root)
    patch_web_server(repo)
    patch_smart_hub(repo)
    patch_portal(repo)
    save(build_path, build.rstrip() + "\n" + BUILD_MARKER + "\n")
    print("Workshop OS read-only status token installed")


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
