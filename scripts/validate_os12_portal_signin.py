#!/usr/bin/env python3
"""Validate the restored Workshop OS 12 Local Portal sign-in (reconstructed source).

Need/forbid checks in the style of the other OS12 validators, plus a route-table
audit: every route registered without the SECURE_* wrappers must be on an
explicit, reviewed public list. The host-compiled policy smoke test
(tests/workshop_os12_portal_access_smoke.cpp) proves the decision table itself.
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path


class ValidationError(RuntimeError):
    pass


def need(text: str, needle: str, label: str) -> None:
    if needle not in text:
        raise ValidationError(f"missing {label}: {needle}")


def forbid(text: str, needle: str, label: str) -> None:
    if needle in text:
        raise ValidationError(f"forbidden {label}: {needle}")


def read(path: Path) -> str:
    if not path.is_file():
        raise ValidationError(f"missing file: {path}")
    return path.read_text(encoding="utf-8")


def block(text: str, signature: str) -> str:
    start = text.find(signature)
    if start < 0:
        raise ValidationError(f"missing function: {signature}")
    brace = text.find("{", start)
    depth = 0
    for i in range(brace, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    raise ValidationError(f"unterminated function: {signature}")


# Routes registered with plain server.on(...). Each one either has no secret
# and no side effect, or performs its own securityAuthorize()/token check.
PUBLIC_ROUTES = {
    ("/login", "HTTP_GET"),  # sign-in page
    ("/login", "HTTP_POST"),  # rate-limited code check
    ("/api/portal-security", "HTTP_GET"),  # handler calls securityAuthorize(false)
    ("/api/portal-security", "HTTP_POST"),  # handler calls securityAuthorize(true)
    ("/generate_204", "HTTP_GET"),
    ("/gen_204", "HTTP_GET"),
    ("/connecttest.txt", "HTTP_GET"),
    ("/hotspot-detect.html", "HTTP_GET"),
    ("/canonical.html", "HTTP_GET"),
    ("/app.css", "HTTP_GET"),
    ("/app.js", "HTTP_GET"),
    ("/recovery/status", "HTTP_GET"),  # accepted v11.20 readiness probe; no secrets
    ("/recovery/touch", "HTTP_POST"),  # recoveryMutationAllowed()
    ("/recovery/reboot", "HTTP_POST"),
    ("/recovery/safe", "HTTP_POST"),
    ("/recovery/rollback", "HTTP_POST"),
    ("/recovery/reset-ui", "HTTP_POST"),
    ("/recovery/reset-auth", "HTTP_POST"),
    ("/recovery/reset-wifi", "HTTP_POST"),
}

# Routes that must stay behind the session wrapper.
SECURE_ROUTES = (
    'SECURE_GET("/", handleRoot);',
    'SECURE_GET("/status", handleStatus);',
    'SECURE_GET("/hardware/health", handleHardwareHealth);',
    'SECURE_POST("/printer/control", handlePrinterControl);',
    'SECURE_POST("/printer/power", handlePrinterPower);',
    'SECURE_POST("/power/control", handlePowerControl);',
    'SECURE_POST("/light/set", handleLightSet);',
    'SECURE_GET("/printer/access-code", handlePrinterAccessCode);',
    'SECURE_GET("/printer/config", handlePrinterConfig);',
    'SECURE_GET("/settings/export", handleSettingsExport);',
    'SECURE_GET("/hub/frame.ppm", handleHubFramePpm);',
    'SECURE_GET("/hub/views", handleHubViews);',
    'SECURE_POST("/hub/show", handleHubShow);',
    'SECURE_GET("/debug", handleDebug);',
    'SECURE_GET("/recovery", handleRecoveryPage);',
    'SECURE_GET("/os12/update/status", handleWorkshopUpdateStatus);',
    'SECURE_POST("/os12/update/install", handleWorkshopUpdateInstall);',
    'SECURE_POST("/reset", handleReset);',
    'SECURE_POST("/reboot", handleReboot);',
)


def check_route_table(web: str, extra_public: set[tuple[str, str]]) -> None:
    allowed = PUBLIC_ROUTES | extra_public
    for path, method in re.findall(r'server\.on\(\s*"([^"]+)"\s*,\s*(HTTP_[A-Z]+)', web):
        if (path, method) not in allowed:
            raise ValidationError(f"route registered without session wrapper: {method} {path}")
    for marker in SECURE_ROUTES:
        need(web, marker, "session-protected route")
    for path in ("/ota/upload",):
        if not re.search(r'SECURE_UPLOAD\(\s*"' + re.escape(path) + '"', web):
            raise ValidationError(f"missing session-protected upload route: {path}")
    need(web, "server.onNotFound([]() { if (securityAuthorize(server, false)) handleNotFound(); });",
         "not-found route stays behind authorization")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True, help="reconstructed firmware tree")
    ap.add_argument("--source-root", default=str(Path(__file__).resolve().parents[1]))
    ap.add_argument("--extra-public-route", action="append", default=[],
                    help="METHOD:/path registered by a later reviewed overlay with its own auth")
    args = ap.parse_args()
    root = Path(args.repo).resolve()
    source_root = Path(args.source_root).resolve()

    sec = read(root / "src/security_manager.cpp")
    web = read(root / "src/web_server.cpp")
    html = read(root / "include/web_pages.h")
    hub = read(root / "src/smart_hub.cpp")
    build = read(root / "include/smart_home_build.h")
    policy_installed = read(root / "include/workshop_portal_access_policy.hpp")
    policy_source = read(source_root / "firmware/platform/security/portal_access_policy.hpp")
    recipe = read(source_root / "scripts/run_os12_ux_local.sh")

    # Build identity and recipe.
    need(build, "#define WORKSHOP_OS_PORTAL_SIGNIN_RESTORED 1", "sign-in restore build identity")
    need(build, "#define WORKSHOP_OS_PORTAL_CONTROL_PLANE_V4 1", "control-plane v4 base")
    forbid(build, "WORKSHOP_OS_CODE_FREE_PORTAL", "code-free portal build identity")
    forbid(build, "SMART_HOME_DEV_UNLOCK", "development unlock")
    forbid(recipe, "apply_workshop_os12_code_free_portal.py", "code-free overlay in recipe")
    need(recipe, "apply_workshop_os12_portal_signin_restore.py", "sign-in restore overlay in recipe")
    if policy_installed != policy_source:
        raise ValidationError("installed portal access policy differs from firmware/platform source")

    # Pure policy content.
    for marker in (
        "inline bool sameOriginHeaders(const char* host, const char* origin, const char* referer)",
        "inline PortalAccess decidePortalAccess(const PortalRequestFacts& r)",
        "if (r.mutating && !r.sameOrigin) return PortalAccess::RejectCrossOrigin;",
        "if (r.sessionValid) return PortalAccess::Allow;",
        "if (!r.mutating && !r.portalLocked && !r.apMode && openReadRoute(uri))",
        "bool portalLocked{true};",
    ):
        need(policy_source, marker, "portal access policy")
    forbid(policy_source, "X-BambuHelper-Client", "client marker header in policy")
    for never in ('"/printer/access-code"', '"/settings/export"', '"/hub/frame.ppm"', '"/debug"',
                  '"/printer/config"', '"/recovery",\n'):
        open_list = policy_source.split("inline bool openReadRoute", 1)[1].split("inline bool signInNavigationRoute", 1)[0]
        forbid(open_list, never, "sensitive route in open-read list")

    # security_manager.cpp
    need(sec, '#include "workshop_portal_access_policy.hpp"', "policy include")
    forbid(sec, "X-BambuHelper-Client", "client marker header shortcut")
    forbid(sec, "if (isAPMode()) return true", "blanket AP authorization")
    forbid(sec, "if (!mutating && !securityPortalCodeRequired()) return true;", "unbounded open-read policy")
    forbid(sec, "device code disabled", "code-free initialization")
    forbid(sec, "kTemporaryNoCodeLan", "temporary physical-test bypass")
    forbid(sec, "static bool apPublicRouteAllowed", "duplicate AP allowlist authority")
    same_origin = block(sec, "bool sameOrigin(WebServer& server)")
    need(same_origin, "workshop::security::sameOriginHeaders(", "pure same-origin check")
    forbid(same_origin, "return true;", "unconditional same-origin acceptance")
    authorize = block(sec, "bool securityAuthorize(WebServer& server, bool mutating)")
    for marker in (
        "facts.sessionValid = cookieMatches(server);",
        "facts.sameOrigin = mutating ? sameOrigin(server) : false;",
        "facts.apMode = isAPMode();",
        "facts.recoverySafeMode = recoverySafeModeActive();",
        "facts.portalLocked = securityPortalCodeRequired();",
        "workshop::security::decidePortalAccess(facts)",
        "server.send(401, \"application/json\"",
        "server.send(403, \"application/json\"",
        'server.sendHeader("Location", "/login");',
    ):
        need(authorize, marker, "authorization decision")
    init = block(sec, "void ensureInitialized()")
    need(init, "generatePortalCode();", "boot-scoped portal code generation")
    for line in sec.splitlines():
        if "Serial." in line and ("g_portalCode" in line or "securityPortalCode" in line):
            raise ValidationError("portal code reaches Serial output")
    need(sec, "constantTimeEqual(code.c_str(), g_portalCode)", "constant-time code comparison")
    retry = block(sec, "uint32_t retryAfterSeconds(WebServer& server)")
    need(retry, "if (bucket.blockedUntilMs == 0) return 0;", "wrap-safe login backoff")
    need(block(sec, "void noteLoginFailure(WebServer& server)"), "if (bucket.blockedUntilMs == 0) bucket.blockedUntilMs = 1;",
         "non-zero login backoff deadline")
    need(sec, "HttpOnly; SameSite=Strict", "session cookie attributes")
    reset = block(sec, "void securityResetPortalPolicy()")
    need(reset, "g_requirePortalCode = true;", "factory reset restores locked portal")
    need(sec, "g_requirePortalCode = prefs.getBool(kPortalPolicyKey, true);", "locked portal default")

    # web_server.cpp
    forbid(web, "X-BambuHelper-Client", "client marker header collection")
    forbid(web, "local-code-free", "code-free runtime contract")
    forbid(web, "Workshop OS device code is disabled", "code-free login redirect")
    need(web, "<form id='login-form' method='post' action='/login'>", "portal-code sign-in form")
    need(web, 'd["mutationsRequireSession"]=true;', "session-required mutation report")
    need(web, "static bool recoveryMutationAllowed(){return securityAuthorize(server,true);}", "recovery mutation guard")
    recovery_status = block(web, "static void handleRecoveryStatus()")
    need(recovery_status, 'd["runningSourceCommit"]=WORKSHOP_OS_SOURCE_SHA;', "public runtime identity")
    for leak in ("g_portalCode", "securityPortalCode()", "accessCode", "wifiPass"):
        forbid(recovery_status, leak, "secret in public recovery status")
    extra = set()
    for item in args.extra_public_route:
        method, _, path = item.partition(":")
        extra.add((path, method))
    check_route_table(web, extra)

    # Portal and touchscreen UX.
    need(html, 'id="portalCodeRequired" type="checkbox" checked', "access-code setting defaults on")
    need(html, "Controls, settings, credentials, camera and screen capture, diagnostics and Recovery always require sign-in.",
         "access-code setting scope copy")
    forbid(html, "No device code required", "code-free portal copy")
    app_js = read(root / "web/app.js")
    need(app_js, "Status viewing is open on this Wi-Fi network without signing in.", "open-status setting copy")
    forbid(app_js, "Read-only portal browsing is open on this LAN", "overbroad open-read copy")
    need(hub, "static void drawUi12PortalAccess()", "touchscreen Local Portal view")
    need(block(hub, "static void drawUi12PortalAccess()"), "securityPortalCode()", "touchscreen shows current code")

    print("PASS: Local Portal sign-in restored; status/control/capture routes need a session; "
          "mutations need real same-origin provenance; AP and Recovery Safe Mode exceptions are route-scoped")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ValidationError as exc:
        raise SystemExit(f"FAIL: {exc}")
