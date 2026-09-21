#!/usr/bin/env python3
"""Apply the final Workshop OS 12 code-free local portal policy.

This overlay runs after the hardened portal/control-plane layers. It removes the
user-facing device-code flow while retaining same-origin enforcement for every
mutation. Read and write access are local-LAN only by product policy; this layer
must never be confused with the retired temporary physical-test bypass.
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


def block_end(text: str, start: int) -> int:
    brace = text.find("{", start)
    if brace < 0:
        raise PatchError("opening brace missing")
    depth = 0
    quote = None
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
    if start < 0:
        raise PatchError(f"{label}: signature missing: {signature}")
    if text.find(signature, start + 1) >= 0:
        raise PatchError(f"{label}: signature is not unique: {signature}")
    return text[:start] + replacement.rstrip() + text[block_end(text, start):]


def patch_security(repo: Path) -> None:
    path = repo / "src" / "security_manager.cpp"
    text = load(path)

    text = replace_block(
        text,
        "void ensureInitialized()",
        r'''void ensureInitialized() {
  if (g_initialized) return;
  g_initialized = true;

  Serial.println();
  Serial.println("Workshop OS local portal: device code disabled");
  Serial.println("Local mutations require same-origin requests.");
}''',
        "code-free security initialization",
    )

    text = replace_block(
        text,
        "bool securityAuthorize(WebServer& server, bool mutating)",
        r'''bool securityAuthorize(WebServer& server, bool mutating) {
  ensureInitialized();

  if (mutating && !sameOrigin(server)) {
    server.send(403, "application/json",
        "{\"status\":\"error\",\"message\":\"Rejected by Workshop OS same-origin protection.\"}");
    return false;
  }

  // Intentional production policy: the local Workshop OS portal is code-free.
  // This is not the retired temporary physical-test bypass. Mutations remain
  // constrained by the same-origin gate above.
  return true;
}''',
        "code-free authorization policy",
    )

    text = replace_block(
        text,
        "bool securityPortalCodeRequired()",
        r'''bool securityPortalCodeRequired() {
  return false;
}''',
        "portal-code disabled state",
    )

    text = replace_block(
        text,
        "bool securitySetPortalCodeRequired(bool required)",
        r'''bool securitySetPortalCodeRequired(bool required) {
  (void)required;
  return false;
}''',
        "portal-code immutable disabled state",
    )

    text = replace_block(
        text,
        "void securityResetPortalPolicy()",
        r'''void securityResetPortalPolicy() {
  Preferences prefs;
  if (prefs.begin(kPortalPolicyNamespace, false)) {
    prefs.putBool(kPortalPolicyKey, false);
    prefs.end();
  }
  g_requirePortalCode = false;
  g_portalPolicyLoaded = true;
}''',
        "factory-reset code-free policy",
    )

    save(path, text)


def patch_web_server(repo: Path) -> None:
    path = repo / "src" / "web_server.cpp"
    text = load(path)

    text = replace_block(
        text,
        "static void sendPortalLoginPage(",
        r'''static void sendPortalLoginPage(PortalLoginPageState state = PortalLoginPageState::Ready, uint32_t retryAfterSeconds = 0) {
  (void)state;
  (void)retryAfterSeconds;
  server.sendHeader("Location", "/");
  server.sendHeader("Cache-Control", "no-store");
  server.send(303, "text/plain", "Workshop OS device code is disabled");
}''',
        "remove device-code login page",
    )

    text = replace_block(
        text,
        "static void handlePortalLoginPage()",
        r'''static void handlePortalLoginPage() {
  server.sendHeader("Location", "/");
  server.sendHeader("Cache-Control", "no-store");
  server.send(303, "text/plain", "Workshop OS device code is disabled");
}''',
        "login GET redirect",
    )

    text = replace_block(
        text,
        "static void handlePortalLoginSubmit()",
        r'''static void handlePortalLoginSubmit() {
  server.sendHeader("Location", "/");
  server.sendHeader("Cache-Control", "no-store");
  server.send(303, "text/plain", "Workshop OS device code is disabled");
}''',
        "login POST redirect",
    )

    text = replace_block(
        text,
        "static void handlePortalSecurityStatus()",
        r'''static void handlePortalSecurityStatus(){
  if(!securityAuthorize(server,false)) return;
  JsonDocument d;
  d["requirePortalCode"]=false;
  d["deviceCodeEnabled"]=false;
  d["authMode"]="local-code-free";
  d["mutationsRequireSession"]=false;
  d["sameOriginProtection"]=true;
  String out;serializeJson(d,out);server.sendHeader("Cache-Control","no-store");server.send(200,"application/json",out);
}''',
        "code-free security status",
    )

    text = replace_block(
        text,
        "static void handlePortalSecuritySave()",
        r'''static void handlePortalSecuritySave(){
  if(!securityAuthorize(server,true)) return;
  server.send(405,"application/json",
      "{\"status\":\"error\",\"message\":\"Workshop OS device code is disabled by product policy.\"}");
}''',
        "disable portal-code policy mutation",
    )

    text = text.replace(
        '(securityPortalCodeRequired()?"portal-code":"open-readonly")',
        '"local-code-free"',
    )
    save(path, text)


def patch_portal_html(repo: Path) -> None:
    path = repo / "include" / "web_pages.h"
    text = load(path)

    replacement = '''<section class="os12-security-panel os12-local-access" aria-labelledby="localAccessTitle">
    <div><small>LOCAL ACCESS</small><h3 id="localAccessTitle">No device code required</h3><p>Workshop OS opens directly on the trusted local network. Mutating requests remain protected by same-origin enforcement.</p></div>
  </section>'''

    # Anchor on semantic copy that survives all preceding reconstruction layers.
    # Find the section containing PORTAL SECURITY / Require access code, then
    # replace only that section. Do not depend on a particular class ordering,
    # whitespace layout, or following integration-section markup.
    marker = "PORTAL SECURITY"
    marker_pos = text.find(marker)
    if marker_pos < 0:
        marker = "Require access code"
        marker_pos = text.find(marker)
    if marker_pos < 0:
        raise PatchError("portal security semantic marker missing")

    start = text.rfind("<section", 0, marker_pos)
    if start < 0:
        raise PatchError("portal security section start missing")

    # The generated portal sections are flat here; take the first closing
    # section after the security marker.
    end = text.find("</section>", marker_pos)
    if end < 0:
        raise PatchError("portal security section end missing")
    end += len("</section>")

    old = text[start:end]
    if "portalSecurity" not in old and "Require access code" not in old and "PORTAL SECURITY" not in old:
        raise PatchError("refusing to replace non-security section")

    text = text[:start] + replacement + text[end:]
    save(path, text)


def patch_identity(repo: Path) -> None:
    path = repo / "include" / "smart_home_build.h"
    text = load(path)
    marker = "#define WORKSHOP_OS_CODE_FREE_PORTAL 1"
    if marker not in text:
        text = text.rstrip() + "\n" + marker + "\n"
    save(path, text)


def apply(repo: Path) -> None:
    build = repo / "include" / "smart_home_build.h"
    if "WORKSHOP_OS_PORTAL_CONTROL_PLANE_V4" not in load(build):
        raise PatchError("code-free portal overlay requires OS12 portal control-plane v4")

    patch_security(repo)
    patch_web_server(repo)
    patch_portal_html(repo)
    patch_identity(repo)
    print("Workshop OS 12 code-free local portal policy applied")


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
