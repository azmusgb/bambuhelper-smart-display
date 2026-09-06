#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

MARKER = "Workshop OS v11.29 Acceptance Open LAN RC1"
FLAG = "WORKSHOP_OS_ACCEPTANCE_OPEN_LAN"


class PatchError(RuntimeError):
    pass


def load(root: Path, rel: str) -> str:
    path = root / rel
    if not path.exists():
        raise PatchError(f"missing reconstructed source: {rel}")
    return path.read_text(encoding="utf-8")


def save(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.write_text(text, encoding="utf-8")


def once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise PatchError(f"{label}: expected exactly one anchor, found {count}")
    return text.replace(old, new, 1)


def replace_braced_block(text: str, start: str, replacement: str, label: str) -> str:
    pos = text.find(start)
    if pos < 0:
        raise PatchError(f"{label}: start anchor missing")
    brace = text.find("{", pos)
    if brace < 0:
        raise PatchError(f"{label}: opening brace missing")
    depth = 0
    in_string = False
    quote = ""
    escape = False
    for i in range(brace, len(text)):
        c = text[i]
        if in_string:
            if escape:
                escape = False
            elif c == "\\":
                escape = True
            elif c == quote:
                in_string = False
            continue
        if c in ("'", '"'):
            in_string = True
            quote = c
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return text[:pos] + replacement + text[i + 1:]
    raise PatchError(f"{label}: closing brace missing")


def get_braced_block(text: str, start: str, label: str) -> tuple[int, int, str]:
    pos = text.find(start)
    if pos < 0:
        raise PatchError(f"{label}: start anchor missing")
    brace = text.find("{", pos)
    if brace < 0:
        raise PatchError(f"{label}: opening brace missing")
    depth = 0
    in_string = False
    quote = ""
    escape = False
    for i in range(brace, len(text)):
        c = text[i]
        if in_string:
            if escape:
                escape = False
            elif c == "\\":
                escape = True
            elif c == quote:
                in_string = False
            continue
        if c in ("'", '"'):
            in_string = True
            quote = c
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return pos, i + 1, text[pos:i + 1]
    raise PatchError(f"{label}: closing brace missing")


def patch_build(root: Path) -> None:
    rel = "include/smart_home_build.h"
    text = load(root, rel)
    text = once(text, '#define SMART_HOME_VERSION "v11.28"', '#define SMART_HOME_VERSION "v11.29"', "version")
    text = once(text, '#define SMART_HOME_PROFILE "companion-viewer"', '#define SMART_HOME_PROFILE "acceptance-open-lan"', "profile")
    text = once(
        text,
        'Smart Home v11.28 Physical Companion Viewer RC1',
        'Smart Home v11.29 Acceptance Open LAN RC1',
        "build label",
    )
    label = '#define SMART_HOME_BUILD_LABEL "Smart Home v11.29 Acceptance Open LAN RC1"\n'
    if f"#define {FLAG} 1" not in text:
        text = once(text, label, label + f"#define {FLAG} 1\n", "acceptance mode flag")
    if MARKER not in text:
        text += f"\n// {MARKER}\n"
    save(root, rel, text)


def patch_security(root: Path) -> None:
    rel = "src/security_manager.cpp"
    text = load(root, rel)

    if '#include "smart_home_build.h"' not in text:
        text = once(
            text,
            '#include "wifi_manager.h"\n',
            '#include "smart_home_build.h"\n#include "wifi_manager.h"\n',
            "build flag include",
        )

    text = replace_braced_block(
        text,
        "void securityInit()",
        f'''void securityInit() {{
#if defined({FLAG}) && {FLAG}
  // Acceptance build: normal station-mode access intentionally starts open.
  // Do not generate a boot credential that the physical UI does not expose.
  Serial.println("Workshop OS v11.29 acceptance mode: LAN sign-in disabled");
  return;
#else
  ensureInitialized();
#endif
}}''',
        "security init",
    )

    text = replace_braced_block(
        text,
        "bool securitySessionValid(WebServer& server)",
        f'''bool securitySessionValid(WebServer& server) {{
#if defined({FLAG}) && {FLAG}
  if (!isAPMode()) return true;
#endif
  ensureInitialized();
  return cookieMatches(server);
}}''',
        "session policy",
    )

    api_header = '''  // Explicit API clients may opt in after establishing a valid session. This
  // never bypasses authentication; it only replaces browser Origin semantics.
  if (server.header("X-BambuHelper-Client") == "1") return true;
'''
    if api_header in text:
        text = once(
            text,
            api_header,
            f'''#if !defined({FLAG}) || !{FLAG}
{api_header}#endif
''',
            "disable header-only mutation provenance in open mode",
        )

    start, end, auth = get_braced_block(
        text,
        "bool securityAuthorize(WebServer& server, bool mutating)",
        "authorize policy",
    )
    marker = "  ensureInitialized();"
    if marker not in auth:
        raise PatchError("authorize policy: ensureInitialized anchor missing")
    open_policy = f'''#if defined({FLAG}) && {FLAG}
  // User-requested physical acceptance mode: normal trusted-LAN pages are open
  // without a portal cookie. Destructive/state-changing browser calls still
  // require same-origin provenance. Header-only API provenance is deliberately
  // disabled above while there is no session credential to bind it to.
  if (!isAPMode()) {{
    const String uri = server.uri();
    if (uri == "/settings/export" || uri == "/debug") {{
      server.send(403, "application/json",
          "{{\\\"status\\\":\\\"error\\\",\\\"message\\\":\\\"Sensitive export/debug is disabled in Acceptance Mode.\\\"}}");
      return false;
    }}
    if (mutating && !sameOrigin(server)) {{
      server.send(403, "application/json",
          "{{\\\"status\\\":\\\"error\\\",\\\"message\\\":\\\"Rejected by Workshop OS same-origin protection.\\\"}}");
      return false;
    }}
    return true;
  }}
#endif

  ensureInitialized();'''
    auth = auth.replace(marker, open_policy, 1)
    text = text[:start] + auth + text[end:]

    save(root, rel, text)


def patch_login_compatibility(root: Path) -> None:
    rel = "src/web_server.cpp"
    text = load(root, rel)

    # Safari/iOS validation must never be the authority for the rotating code.
    # The firmware already trims, uppercases and constant-time-compares it.
    # Removing the brittle regex fixes the observed "Match requested format"
    # failure and keeps future opt-in authentication compatible with iOS.
    old = " maxlength='10' minlength='10' pattern='[A-HJ-NP-Z2-9]{10}' autocomplete='one-time-code'"
    new = " maxlength='10' inputmode='text' enterkeyhint='go' autocomplete='one-time-code'"
    text = once(text, old, new, "Safari portal-code input compatibility")

    save(root, rel, text)


def patch_browser_banner(root: Path) -> None:
    rel = "web/app.js"
    text = load(root, rel)
    if "v1129AcceptanceOpenLanBanner" in text:
        return
    anchor = "function v1120Ws350Safety(){"
    banner = r'''function v1129AcceptanceOpenLanBanner(){
  var style=document.createElement('style');
  style.textContent='.v1129-open-banner{margin:10px 0 16px;padding:11px 14px;border:1px solid rgba(84,214,125,.45);border-radius:10px;background:rgba(84,214,125,.08);font-size:12.5px;line-height:1.45}.v1129-open-banner strong{color:#72e89a}';
  document.head.appendChild(style);
  var main=document.querySelector('main')||document.body;
  if(main&&!document.getElementById('v1129AcceptanceOpenLan')){
    var b=document.createElement('div');
    b.id='v1129AcceptanceOpenLan';
    b.className='v1129-open-banner';
    b.innerHTML='<strong>LOCAL ACCEPTANCE MODE</strong> · Portal sign-in is off on normal Wi-Fi. Browser-origin protection remains active for changes; sensitive export/debug is blocked.';
    main.insertBefore(b,main.firstChild);
  }
}
setTimeout(v1129AcceptanceOpenLanBanner,0);

'''
    text = once(text, anchor, banner + anchor, "acceptance-mode browser banner")
    save(root, rel, text)


def patch_physical_system(root: Path) -> None:
    rel = "src/smart_hub.cpp"
    text = load(root, rel)

    count = text.count("securityPortalCode()")
    if count < 1:
        raise PatchError("physical System UI: portal-code reference not found")
    text = text.replace("securityPortalCode()", '"OPEN"')
    text = text.replace('"PORTAL ACCESS"', '"LOCAL ACCESS"')
    text = text.replace('"PORTAL CODE  %s"', '"LOCAL ACCESS  %s"')
    text = text.replace('"Changes after reboot"', '"No sign-in required"')
    text = text.replace('"Session auth + same-origin protection"', '"LAN open + same-origin protection"')

    if "securityPortalCode()" in text:
        raise PatchError("physical System UI still exposes rotating portal code")
    save(root, rel, text)


def apply(root: Path) -> None:
    build = load(root, "include/smart_home_build.h")
    if MARKER in build:
        print("Workshop OS v11.29 Acceptance Open LAN already applied")
        return
    if 'SMART_HOME_VERSION "v11.28"' not in build:
        raise PatchError("v11.29 requires reconstructed v11.28 Companion Viewer source")

    patch_build(root)
    patch_security(root)
    patch_login_compatibility(root)
    patch_browser_banner(root)
    patch_physical_system(root)
    print("Workshop OS v11.29 Acceptance Open LAN RC1 applied")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default=".")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    if not args.apply:
        print("v11.29 Acceptance Open LAN patch ready. Use --apply to modify reconstructed source.")
        return 0
    apply(Path(args.repo).resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
