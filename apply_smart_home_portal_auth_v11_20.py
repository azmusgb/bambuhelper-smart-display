#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path


class PatchError(RuntimeError):
    pass


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise PatchError(f"{label}: expected exactly 1 match, found {count}")
    return text.replace(old, new, 1)


def patch_build(repo: Path) -> None:
    p = repo / "include" / "smart_home_build.h"
    text = p.read_text(encoding="utf-8")
    text = replace_once(text, '#define SMART_HOME_VERSION "v11.19.1"\n', '#define SMART_HOME_VERSION "v11.20"\n', "version")
    text = replace_once(text, '#define SMART_HOME_PROFILE "physical-fit"\n', '#define SMART_HOME_PROFILE "portal-auth"\n', "profile")
    text = replace_once(
        text,
        '#define SMART_HOME_BUILD_LABEL "Smart Home v11.19.1 Physical Fit RC2"\n',
        '#define SMART_HOME_BUILD_LABEL "Smart Home v11.20 Portal Auth RC1"\n',
        "build label",
    )
    text = replace_once(text, '#define SMART_HOME_DEV_UNLOCK 1\n', '', "remove development unlock")
    p.write_text(text, encoding="utf-8")


def patch_security(repo: Path) -> None:
    p = repo / "src" / "security_manager.cpp"
    text = p.read_text(encoding="utf-8")
    text = replace_once(text, '#include "smart_home_build.h"\n', '', "remove dev build include")
    text = replace_once(
        text,
        '''static bool portalAuthRequired() {\n#if defined(BOARD_IS_WS350) && defined(SMART_HOME_DEV_UNLOCK) && SMART_HOME_DEV_UNLOCK\n  return false;\n#else\n  return true;\n#endif\n}\n\n''',
        '',
        "remove dev auth policy",
    )
    text = replace_once(
        text,
        '''bool securitySessionValid(WebServer& server) {\n  if (isAPMode()) return true;\n  if (!portalAuthRequired()) return true;\n  ensureInitialized();\n  return cookieMatches(server);\n}\n''',
        '''bool securitySessionValid(WebServer& server) {\n  // Recovery AP remains independently accessible. Normal LAN access requires\n  // the current boot-scoped portal-code session.\n  if (isAPMode()) return true;\n  ensureInitialized();\n  return cookieMatches(server);\n}\n''',
        "session auth enforcement",
    )
    text = replace_once(
        text,
        '''  // Development phase: the WS350 portal stays open on the trusted LAN so a\n  // display/input regression cannot strand the owner behind a one-time code.\n  // Mutating browser requests still keep same-origin protection.\n  if (!portalAuthRequired()) {\n    if (mutating && !sameOrigin(server)) {\n      server.send(403, "application/json",\n          "{\\\"status\\\":\\\"error\\\",\\\"message\\\":\\\"Rejected by Smart Home same-origin protection.\\\"}");\n      return false;\n    }\n    return true;\n  }\n\n''',
        '',
        "remove dev authorization bypass",
    )
    p.write_text(text, encoding="utf-8")


def patch_browser(repo: Path) -> None:
    p = repo / "web" / "app.js"
    text = p.read_text(encoding="utf-8")
    text = replace_once(text, "    pill.textContent = 'Smart Home DEV';\n", "    pill.textContent = 'Workshop OS';\n", "portal build pill")
    old = r'''/* ============ Smart Home v9.3 development safety ============ */
function v93DevelopmentSafety(){
  var style = document.createElement('style');
  style.textContent = '.v93-dev-banner{margin:10px 0 16px;padding:11px 14px;border:1px solid rgba(255,176,32,.5);border-radius:10px;background:rgba(255,176,32,.09);color:var(--text);font-size:12.5px;line-height:1.45}.v93-dev-banner strong{color:#ffb020}';
  document.head.appendChild(style);

  var main = document.querySelector('main') || document.body;
  if (main && !document.getElementById('v93DevBanner')){
    var banner = document.createElement('div');
    banner.id = 'v93DevBanner';
    banner.className = 'v93-dev-banner';
    banner.innerHTML = '<strong>DEVELOPMENT MODE</strong> · Portal code is temporarily disabled. Recovery console: <b>/recovery</b>. Same-origin protection remains enabled for settings and OTA.';
    main.insertBefore(banner, main.firstChild);
  }

  var bt = document.getElementById('btntype');
  if (bt){
    bt.value = '3';
    bt.disabled = true;
    var row = bt.closest ? bt.closest('.field') : bt.parentElement;
    if (row && !document.getElementById('v93TouchNote')){
      var note = document.createElement('div');
      note.id = 'v93TouchNote';
      note.className = 'hint';
      note.textContent = 'WS350 integrated touchscreen is locked on during development to prevent a remote lockout.';
      row.appendChild(note);
    }
  }
}
setTimeout(v93DevelopmentSafety, 0);
'''
    new = r'''/* ============ Workshop OS v11.20 WS350 physical safety ============ */
function v1120Ws350Safety(){
  // Touch safety is independent of portal authentication: this integrated
  // panel must never inherit a persisted Disabled mode and strand recovery.
  var bt = document.getElementById('btntype');
  if (bt){
    bt.value = '3';
    bt.disabled = true;
    var row = bt.closest ? bt.closest('.field') : bt.parentElement;
    if (row && !document.getElementById('v1120TouchNote')){
      var note = document.createElement('div');
      note.id = 'v1120TouchNote';
      note.className = 'hint';
      note.textContent = 'WS350 integrated touchscreen stays enabled as an independent physical recovery path.';
      row.appendChild(note);
    }
  }
}
setTimeout(v1120Ws350Safety, 0);
'''
    text = replace_once(text, old, new, "replace development banner with touch safety")
    text = replace_once(text, "ccText('ccFirmwareDetail',d.safeMode?'Safe Mode':'Normal / Development');", "ccText('ccFirmwareDetail',d.safeMode?'Safe Mode':'Normal');", "browser normal mode label")
    p.write_text(text, encoding="utf-8")


def patch_recovery(repo: Path) -> None:
    p = repo / "src" / "web_server.cpp"
    text = p.read_text(encoding="utf-8")
    text = replace_once(
        text,
        'server.on("/recovery", HTTP_GET, handleRecoveryPage);',
        'SECURE_GET("/recovery", handleRecoveryPage);',
        "normal-LAN recovery page authentication",
    )
    text = replace_once(
        text,
        "<div class='sub'>Smart Home independent recovery plane. This page does not depend on the normal portal JavaScript.</div>",
        "<div class='sub'>Workshop OS independent recovery plane. On normal LAN, access uses your portal-code session; Recovery AP remains independently accessible.</div>",
        "recovery auth guidance",
    )
    text = replace_once(
        text,
        "['Mode',d.safeMode?'SAFE MODE':'Normal / Development'],['Auth','OFF · DEVELOPMENT']",
        "['Mode',d.safeMode?'SAFE MODE':'Normal'],['Auth','ON · PORTAL CODE']",
        "recovery auth status",
    )
    text = replace_once(
        text,
        '''static void handleRecoveryResetAuth(){if(!recoveryMutationAllowed())return;securityLogout(server);server.send(200,"application/json","{\\"status\\":\\"ok\\",\\"message\\":\\"Portal session reset. Development unlock remains active.\\"}");}\n''',
        '''static void handleRecoveryResetAuth(){if(!recoveryMutationAllowed())return;securityLogout(server);server.send(200,"application/json","{\\"status\\":\\"ok\\",\\"message\\":\\"Portal session reset. Sign in again with the current code shown on System.\\"}");}\n''',
        "recovery session reset message",
    )
    p.write_text(text, encoding="utf-8")


def apply(repo: Path) -> None:
    patch_build(repo)
    patch_security(repo)
    patch_browser(repo)
    patch_recovery(repo)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=".")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    repo = Path(args.repo).resolve()
    if not args.apply:
        print("Workshop OS v11.20 Portal Auth patch ready. Use --apply to modify the target tree.")
        return 0
    apply(repo)
    print("Workshop OS v11.20 Portal Auth RC1 applied")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
