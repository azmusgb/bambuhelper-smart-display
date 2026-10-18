#!/usr/bin/env python3
"""Restore Local Portal sign-in for Workshop OS 12 (security candidate 12.0.1).

The 12.0.0 reconstruction ended with ``apply_workshop_os12_code_free_portal.py``.
That overlay made every GET anonymous and reduced mutation protection to
``sameOrigin()``, which itself accepted any request carrying the client-supplied
``X-BambuHelper-Client: 1`` header. A non-browser LAN client could therefore read
``/status``, ``/printer/access-code``, ``/settings/export`` and ``/hub/frame.ppm``
and POST printer controls without signing in.

This overlay runs on the hardened control-plane v4 source (the code-free overlay
is no longer part of the recipe) and:

* routes every ``securityAuthorize()`` decision through the host-tested pure
  policy ``firmware/platform/security/portal_access_policy.hpp``;
* removes the ``X-BambuHelper-Client`` same-origin shortcut, and stops
  collecting that header at all;
* answers unauthenticated API/status/control requests with HTTP 401 JSON and
  unauthenticated page navigations with 303 -> /login;
* keeps the AP captive-onboarding and Recovery Safe Mode exceptions exactly as
  docs/portal-auth-v11-20.md allows;
* narrows the owner's optional "Require access code = off" setting (default on)
  to an explicit list of read-only status routes on station Wi-Fi;
* reports the running release version and exact source commit on the public
  ``/recovery/status`` readiness probe, so install/recovery tooling can verify
  identity across reboots without a session.
"""
from __future__ import annotations

import argparse
import shutil
import sys as _sys
from pathlib import Path

_here = Path(__file__).resolve().parent
if str(_here) not in _sys.path:
    _sys.path.insert(0, str(_here))
from scripts.smart_home_patch_utils import PatchError, get_braced_block  # noqa: E402

BUILD_MARKER = "#define WORKSHOP_OS_PORTAL_SIGNIN_RESTORED 1"
POLICY_SOURCE = Path("firmware") / "platform" / "security" / "portal_access_policy.hpp"
POLICY_TARGET = Path("include") / "workshop_portal_access_policy.hpp"

SAME_ORIGIN = r'''bool sameOrigin(WebServer& server) {
  // Only real browser provenance (Origin, or Referer when Origin is absent)
  // proves a same-origin mutation. No client-supplied marker header is
  // accepted as a substitute; authentication is checked separately.
  String host = server.hostHeader();
  host.trim();
  String origin = server.header("Origin");
  origin.trim();
  String referer = server.header("Referer");
  referer.trim();
  return workshop::security::sameOriginHeaders(host.c_str(), origin.c_str(), referer.c_str());
}'''

SECURITY_AUTHORIZE = r'''bool securityAuthorize(WebServer& server, bool mutating) {
  ensureInitialized();

  const String uri = server.uri();
  workshop::security::PortalRequestFacts facts;
  facts.uri = uri.c_str();
  facts.mutating = mutating;
  facts.apMode = isAPMode();
  facts.recoverySafeMode = recoverySafeModeActive();
  facts.sameOrigin = mutating ? sameOrigin(server) : false;
  facts.sessionValid = cookieMatches(server);
  facts.portalLocked = securityPortalCodeRequired();

  switch (workshop::security::decidePortalAccess(facts)) {
    case workshop::security::PortalAccess::Allow:
      return true;
    case workshop::security::PortalAccess::RejectCrossOrigin:
      server.sendHeader("Cache-Control", "no-store");
      server.send(403, "application/json",
          "{\"status\":\"error\",\"message\":\"Rejected by Workshop OS same-origin protection.\"}");
      return false;
    case workshop::security::PortalAccess::SignInRedirect:
      server.sendHeader("Location", "/login");
      server.sendHeader("Cache-Control", "no-store");
      server.send(303, "text/plain", "Authentication required");
      return false;
    case workshop::security::PortalAccess::SignInRequired:
    default:
      break;
  }

  server.sendHeader("Cache-Control", "no-store");
  server.send(401, "application/json",
      "{\"status\":\"error\",\"message\":\"Sign in to Workshop OS with the code shown on the display.\",\"signIn\":\"/login\"}");
  return false;
}'''

OLD_PANEL_COPY = (
    "<p>When off, read-only portal pages open directly on this LAN. Changes still require "
    "an authenticated session and same-origin protection.</p>"
)
NEW_PANEL_COPY = (
    "<p>On by default. When off, only the Home page and printer and display status can be viewed "
    "on this Wi-Fi network without signing in. Controls, settings, credentials, camera and screen "
    "capture, diagnostics and Recovery always require sign-in.</p>"
)


def load(path: Path) -> str:
    if not path.exists():
        raise PatchError(f"missing {path}")
    return path.read_text(encoding="utf-8")


def save(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def replace_unique_block(text: str, signature: str, replacement: str, label: str) -> str:
    if text.count(signature) != 1:
        raise PatchError(f"{label}: expected exactly one '{signature}', found {text.count(signature)}")
    start, end, _ = get_braced_block(text, signature, label)
    return text[:start] + replacement + text[end:]


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise PatchError(f"{label}: expected exactly one anchor, found {count}")
    return text.replace(old, new, 1)


def patch_security(repo: Path) -> None:
    path = repo / "src" / "security_manager.cpp"
    text = load(path)
    text = replace_once(
        text,
        '#include "smart_home_build.h"\n',
        '#include "smart_home_build.h"\n#include "workshop_portal_access_policy.hpp"\n',
        "policy include",
    )
    text = replace_unique_block(text, "bool sameOrigin(WebServer& server)", SAME_ORIGIN, "same-origin check")

    # The AP allowlist now lives in the pure policy; drop the duplicate helper
    # so there is exactly one authority for it.
    start, end, _ = get_braced_block(text, "static bool apPublicRouteAllowed(WebServer& server)", "AP allowlist")
    text = text[:start].rstrip() + "\n\n" + text[end:].lstrip()

    text = replace_unique_block(
        text, "bool securityAuthorize(WebServer& server, bool mutating)", SECURITY_AUTHORIZE, "authorization policy"
    )
    save(path, text)


def patch_web_server(repo: Path) -> None:
    path = repo / "src" / "web_server.cpp"
    text = load(path)
    text = replace_once(text, '    "X-BambuHelper-Client",\n', "", "stop collecting client marker header")

    start, end, block = get_braced_block(text, "static void handleRecoveryStatus()", "recovery status")
    anchor = 'd["build"]=SMART_HOME_BUILD_LABEL;'
    if block.count(anchor) != 1:
        raise PatchError("recovery status build anchor missing")
    block = block.replace(
        anchor,
        anchor + '\n  d["releaseVersion"]=WORKSHOP_OS_RELEASE_VERSION;\n  d["runningSourceCommit"]=WORKSHOP_OS_SOURCE_SHA;',
        1,
    )
    text = text[:start] + block + text[end:]
    save(path, text)


def patch_portal_html(repo: Path) -> None:
    path = repo / "include" / "web_pages.h"
    text = load(path)
    text = replace_once(text, OLD_PANEL_COPY, NEW_PANEL_COPY, "portal access setting copy")
    save(path, text)


def install_policy(repo: Path, source_root: Path) -> None:
    source = source_root / POLICY_SOURCE
    if not source.is_file():
        raise PatchError(f"missing policy source {source}")
    target = repo / POLICY_TARGET
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)


def apply(repo: Path, source_root: Path) -> None:
    build_path = repo / "include" / "smart_home_build.h"
    build = load(build_path)
    if "WORKSHOP_OS_PORTAL_CONTROL_PLANE_V4" not in build:
        raise PatchError("sign-in restore requires the OS12 portal control-plane v4 source")
    if "WORKSHOP_OS_CODE_FREE_PORTAL" in build:
        raise PatchError("code-free portal overlay is present; it must not be part of the recipe")
    if BUILD_MARKER in build:
        raise PatchError("portal sign-in restore is already applied")

    install_policy(repo, source_root)
    patch_security(repo)
    patch_web_server(repo)
    patch_portal_html(repo)
    save(build_path, build.rstrip() + "\n" + BUILD_MARKER + "\n")
    print("Workshop OS 12 Local Portal sign-in restored")


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
