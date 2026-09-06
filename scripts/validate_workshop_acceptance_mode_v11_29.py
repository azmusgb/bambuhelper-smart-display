#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path


def fail(message: str) -> None:
    raise SystemExit(f"v11.29 Acceptance Mode validation failed: {message}")


def need(body: str, needle: str, label: str) -> None:
    if needle not in body:
        fail(f"missing {label}: {needle}")


def forbid(body: str, needle: str, label: str) -> None:
    if needle in body:
        fail(f"forbidden {label}: {needle}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("repo", nargs="?", default=".")
    root = Path(ap.parse_args().repo).resolve()

    build = (root / "include/smart_home_build.h").read_text(encoding="utf-8")
    security = (root / "src/security_manager.cpp").read_text(encoding="utf-8")
    web = (root / "src/web_server.cpp").read_text(encoding="utf-8")
    app = (root / "web/app.js").read_text(encoding="utf-8")
    hub = (root / "src/smart_hub.cpp").read_text(encoding="utf-8")
    companion = (root / "src/companion_web.cpp").read_text(encoding="utf-8")

    for marker in [
        'SMART_HOME_VERSION "v11.29"',
        'SMART_HOME_PROFILE "acceptance-open-lan"',
        'Smart Home v11.29 Acceptance Open LAN RC1',
        '#define WORKSHOP_OS_ACCEPTANCE_OPEN_LAN 1',
        'Workshop OS v11.29 Acceptance Open LAN RC1',
    ]:
        need(build, marker, "candidate identity")

    for marker in [
        '#include "smart_home_build.h"',
        "Workshop OS v11.29 acceptance mode: LAN sign-in disabled",
        "if (!isAPMode()) return true;",
        'uri == "/settings/export" || uri == "/debug"',
        "Sensitive export/debug is disabled in Acceptance Mode.",
        "if (mutating && !sameOrigin(server))",
        "Rejected by Workshop OS same-origin protection.",
        "return cookieMatches(server);",
        "securityLogin(WebServer& server",
        "securityPortalCode()",
        "recoverySafeModeActive()",
    ]:
        need(security, marker, "acceptance-mode/security fallback contract")

    need(
        security,
        "#if !defined(WORKSHOP_OS_ACCEPTANCE_OPEN_LAN) || !WORKSHOP_OS_ACCEPTANCE_OPEN_LAN",
        "header-only API provenance disabled in open mode",
    )

    for forbidden in [
        "WORKSHOP_OS_TEMP_LAN_OPEN",
        'Serial.printf("Portal code:',
        'Serial.print(g_portalCode',
        'Serial.println(g_portalCode',
    ]:
        forbid(build + security, forbidden, "legacy bypass/credential disclosure")

    # Safari must not perform its own brittle regex validation. Firmware-side
    # trim/uppercase/constant-time comparison remains the future auth authority.
    need(web, "maxlength='10' inputmode='text' enterkeyhint='go' autocomplete='one-time-code'", "Safari-safe login input")
    forbid(web, "pattern='[A-HJ-NP-Z2-9]{10}'", "brittle Safari portal-code regex")
    need(web, 'server.on("/login", HTTP_GET, handlePortalLoginPage)', "retained future login GET")
    need(web, 'server.on("/login", HTTP_POST, handlePortalLoginSubmit)', "retained future login POST")

    for marker in [
        "function v1129AcceptanceOpenLanBanner()",
        "LOCAL ACCEPTANCE MODE",
        "Portal sign-in is off on normal Wi-Fi",
        "sensitive export/debug is blocked",
    ]:
        need(app, marker, "visible acceptance-mode disclosure")

    need(hub, '"LOCAL ACCESS"', "physical open-LAN card")
    need(hub, '"OPEN"', "physical open state")
    forbid(hub, "securityPortalCode()", "physical portal-code disclosure")
    forbid(hub, '"PORTAL ACCESS"', "stale portal-access card")

    # Existing Companion functionality must survive the security-mode delta.
    for marker in [
        'server.on("/companion/state", HTTP_GET',
        'server.on("/companion/capture", HTTP_POST',
        'server.on("/companion/capture/show", HTTP_POST',
        "kCaptureMaxBytes = 256U * 1024U",
        "MALLOC_CAP_SPIRAM",
    ]:
        need(companion, marker, "inherited Companion functionality")

    print("Workshop OS v11.29 Acceptance Open LAN contracts: PASS")
    print("Normal-LAN portal code: DISABLED BY DEFAULT")
    print("Physical portal-code display: ABSENT")
    print("Normal-LAN browser GETs: OPEN")
    print("Browser mutations: SAME-ORIGIN REQUIRED")
    print("Header-only mutation provenance: DISABLED")
    print("Sensitive export/debug: BLOCKED")
    print("AP/recovery route scoping: PRESERVED")
    print("Future portal-code implementation: RETAINED, SAFARI INPUT FIXED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
