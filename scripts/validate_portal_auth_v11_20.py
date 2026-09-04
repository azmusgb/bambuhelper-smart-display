#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path


def fail(message: str) -> None:
    print(f"ERROR: {message}")
    raise SystemExit(1)


def need(body: str, needle: str, label: str) -> None:
    if needle not in body:
        fail(f"missing {label}: {needle}")


def forbid(body: str, needle: str, label: str) -> None:
    if needle in body:
        fail(f"forbidden {label}: {needle}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("repo", nargs="?", default=".")
    args = ap.parse_args()
    repo = Path(args.repo).resolve()

    build = (repo / "include" / "smart_home_build.h").read_text(encoding="utf-8")
    security = (repo / "src" / "security_manager.cpp").read_text(encoding="utf-8")
    web = (repo / "src" / "web_server.cpp").read_text(encoding="utf-8")
    app = (repo / "web" / "app.js").read_text(encoding="utf-8")
    hub = (repo / "src" / "smart_hub.cpp").read_text(encoding="utf-8")
    settings = (repo / "src" / "settings.cpp").read_text(encoding="utf-8")

    for marker in [
        'SMART_HOME_VERSION "v11.20"',
        'SMART_HOME_PROFILE "portal-auth"',
        'Smart Home v11.20 Portal Auth RC1',
    ]:
        need(build, marker, "candidate identity")
    forbid(build, "SMART_HOME_DEV_UNLOCK", "development unlock build flag")

    for marker in [
        "if (isAPMode()) return true;",
        "return cookieMatches(server);",
        "if (!cookieMatches(server))",
        "if (mutating && !sameOrigin(server))",
        'server.sendHeader("Location", "/login")',
        "Workshop OS portal session security enabled",
        "constexpr size_t kSessionTokenLen = 32",
        "constantTimeEqual",
        "; Path=/; HttpOnly; SameSite=Strict; Max-Age=86400",
        "memset(g_sessionToken, 0, sizeof(g_sessionToken));",
    ]:
        need(security, marker, "LAN session enforcement/hardening")
    for marker in [
        "portalAuthRequired",
        "Development phase: the WS350 portal stays open",
        "SMART_HOME_DEV_UNLOCK",
        "Smart Home v8.3 RC3 portal session security enabled",
    ]:
        forbid(security, marker, "development/stale auth surface")
    for marker in [
        'Serial.printf("Portal code:',
        'Serial.print(g_portalCode',
        'Serial.println(g_portalCode',
    ]:
        forbid(security, marker, "portal credential disclosure to serial logs")

    for marker in [
        'server.on("/login", HTTP_GET, handlePortalLoginPage)',
        'server.on("/login", HTTP_POST, handlePortalLoginSubmit)',
        'SECURE_POST("/logout", handlePortalLogout)',
        'SECURE_GET("/", handleRoot)',
        'SECURE_GET("/status", handleStatus)',
        'SECURE_POST("/printer/control", handlePrinterControl)',
        'SECURE_POST("/printer/power", handlePrinterPower)',
        'SECURE_GET("/hub/views", handleHubViews)',
        'SECURE_GET("/hub/frame.ppm", handleHubFramePpm)',
        'SECURE_GET("/recovery", handleRecoveryPage)',
        'static bool recoveryMutationAllowed(){return securityAuthorize(server,true);}',
        "['Auth','ON · PORTAL CODE']",
        "Recovery AP remains independently accessible",
        "Portal session reset. Sign in again with the current code shown on System.",
    ]:
        need(web, marker, "authenticated web/recovery contract")
    for marker in [
        'server.on("/recovery", HTTP_GET, handleRecoveryPage)',
        "OFF · DEVELOPMENT",
        "Development unlock remains active",
        "Normal / Development",
    ]:
        forbid(web, marker, "public/development recovery surface")

    for marker in [
        "function v1120Ws350Safety()",
        "WS350 integrated touchscreen stays enabled as an independent physical recovery path.",
        "pill.textContent = 'Workshop OS';",
    ]:
        need(app, marker, "authenticated portal UI")
    for marker in ["DEVELOPMENT MODE", "Portal code is temporarily disabled", "Smart Home DEV", "v93DevelopmentSafety"]:
        forbid(app, marker, "development portal UI")

    # The physical recovery path must not depend on the browser login route.
    # SECURE_GET remains safe in Recovery AP mode because securityAuthorize()
    # explicitly allows isAPMode() before checking the session cookie.
    need(hub, "securityPortalCode()", "physical portal code")
    need(hub, '"PORTAL ACCESS"', "physical portal access card")
    need(settings, "buttonType = BTN_TOUCHSCREEN;", "forced-safe WS350 touch")

    print("Workshop OS v11.20 portal authentication contracts: PASS")
    print("LAN portal authentication: REQUIRED")
    print("Boot-scoped 128-bit session token + HttpOnly/SameSite cookie: REQUIRED")
    print("Portal credential in serial logs: FORBIDDEN")
    print("Stale development/release auth identity: FORBIDDEN")
    print("Normal-LAN Recovery page authentication: REQUIRED")
    print("Recovery AP auth bypass: PRESERVED")
    print("WS350 physical touch safety: PRESERVED")
    print("Same-origin mutation protection: PRESERVED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
