#!/usr/bin/env python3
from __future__ import annotations
import sys
from pathlib import Path


def need(body: str, marker: str, label: str) -> None:
    if marker not in body:
        raise SystemExit(f"V11.23 RC2 CONTRACT FAILED: missing {label}: {marker}")


def forbid(body: str, marker: str, label: str) -> None:
    if marker in body:
        raise SystemExit(f"V11.23 RC2 CONTRACT FAILED: forbidden {label}: {marker}")


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit(f"Usage: {sys.argv[0]} <reconstructed-repo>")
    repo=Path(sys.argv[1]).resolve()
    hub=(repo/"src/smart_hub.cpp").read_text(encoding="utf-8",errors="replace")
    security=(repo/"src/security_manager.cpp").read_text(encoding="utf-8",errors="replace")
    web=(repo/"src/web_server.cpp").read_text(encoding="utf-8",errors="replace")
    app=(repo/"web/app.js").read_text(encoding="utf-8",errors="replace")
    build=(repo/"include/smart_home_build.h").read_text(encoding="utf-8",errors="replace")

    for m in [
        'SMART_HOME_VERSION "v11.23"',
        'SMART_HOME_PROFILE "network-touch-ux"',
        'Smart Home v11.23 Network Locale Layout RC2',
        '#define WORKSHOP_OS_TEMP_LAN_OPEN 1',
        '#define WORKSHOP_OS_RC2_TOUCH_UX 1',
        'Workshop OS v11.23 RC2 touch UX and temporary trusted-LAN portal bypass',
    ]:
        need(build,m,"RC2 identity")

    for m in [
        "hubRc2ButtonRef",
        "hubRc2CardRef",
        "hubRc2HitRef",
        "hubRc2PageIndicator",
        '"STAGED - NOT APPLIED"',
        '"< PREV"',
        '"NEXT >"',
        '"-10"',
        '"+10"',
        '"DISCARD"',
        '"HOLD APPLY + RESTART"',
        "hubNetworkDiscardEdit",
        "if(longPress&&hubStaticNetworkValid())hubCommitNetworkAndRestart()",
        "const bool hubRc2Reverse=(x<tft.width()/2)",
        "i==3&&longPress",
        "HOLD TO ROTATE CLOCKWISE",
    ]:
        need(hub,m,"touch UX")
    forbid(hub,"Tap next / hold previous","hidden reverse gesture copy")
    forbid(hub,"Tap next / hold prev","hidden reverse gesture copy")

    for m in [
        '#include "smart_home_build.h"',
        "WORKSHOP_OS_TEMP_LAN_OPEN",
        "if (!isAPMode()) return true;",
        "if (mutating && !sameOrigin(server))",
        "return cookieMatches(server);",
        "static bool apPublicRouteAllowed(WebServer& server)",
    ]:
        need(security,m,"temporary trusted-LAN policy")
    forbid(security,"if (isAPMode()) return true;","blanket AP authorization")

    for m in [
        "v1123Rc2LanOpenBanner",
        "TEMPORARY TRUSTED-LAN MODE",
        "Same-origin mutation protection and AP/recovery boundaries remain active",
    ]:
        need(app,m,"temporary LAN-open disclosure")

    for m in [
        'SECURE_GET("/", handleRoot)',
        'SECURE_POST("/printer/control", handlePrinterControl)',
        'SECURE_GET("/hub/views", handleHubViews)',
        'SECURE_GET("/hub/frame.ppm", handleHubFramePpm)',
        'SECURE_POST("/hub/show", handleHubShow)',
    ]:
        need(web,m,"centralized route wrapper")

    for m in ["requestSpeedCommand","requestFanCommand"]:
        forbid(hub,m,"speculative printer command")

    print("v11.23 RC2 touch UX / trusted-LAN contract: PASS")
    print("Touch UX: explicit navigation + explicit increment/decrement controls")
    print("Network staging: visible NOT APPLIED state + Back / Discard / guarded Apply")
    print("Display Expert reverse: visible left/right semantics, no hold-to-reverse")
    print("Rotation: hold-guarded")
    print("Normal Wi-Fi portal code: TEMPORARILY BYPASSED")
    print("Same-origin mutation protection: PRESERVED")
    print("AP/recovery authorization boundaries: PRESERVED")
    return 0


if __name__=="__main__":
    raise SystemExit(main())
