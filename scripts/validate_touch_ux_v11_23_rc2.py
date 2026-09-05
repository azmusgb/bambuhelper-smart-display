#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path


def need(body: str, marker: str, label: str) -> None:
    if marker not in body:
        raise SystemExit(f"V11.23 RC2 TOUCH FAILED: missing {label}: {marker}")


def forbid(body: str, marker: str, label: str) -> None:
    if marker in body:
        raise SystemExit(f"V11.23 RC2 TOUCH FAILED: forbidden {label}: {marker}")


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit(f"Usage: {sys.argv[0]} <reconstructed-repo>")

    repo = Path(sys.argv[1]).resolve()
    hub = (repo / "src/smart_hub.cpp").read_text(encoding="utf-8", errors="replace")
    web = (repo / "src/web_server.cpp").read_text(encoding="utf-8", errors="replace")
    build = (repo / "include/smart_home_build.h").read_text(encoding="utf-8", errors="replace")

    for marker in [
        'SMART_HOME_VERSION "v11.23"',
        'SMART_HOME_PROFILE "network-touch-ux"',
        'Smart Home v11.23 Network Locale Layout RC2',
        '#define WORKSHOP_OS_RC2_TOUCH_UX 1',
    ]:
        need(build, marker, "RC2 touch identity")

    for marker in [
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
        need(hub, marker, "touch UX")

    forbid(hub, "Tap next / hold previous", "hidden reverse gesture copy")
    forbid(hub, "Tap next / hold prev", "hidden reverse gesture copy")

    for marker in [
        'SECURE_GET("/", handleRoot)',
        'SECURE_POST("/printer/control", handlePrinterControl)',
        'SECURE_GET("/hub/views", handleHubViews)',
        'SECURE_GET("/hub/frame.ppm", handleHubFramePpm)',
        'SECURE_POST("/hub/show", handleHubShow)',
    ]:
        need(web, marker, "centralized route wrapper")

    for marker in ["requestSpeedCommand", "requestFanCommand"]:
        forbid(hub, marker, "speculative printer command")

    # Security is deliberately validated by the inherited v11.20 contract and
    # the final v11.23 authenticated-boundary validator. This validator owns
    # only the RC2 touch/interaction surface so a temporary intermediate state
    # cannot be mistaken for an approved security posture.
    print("v11.23 RC2 touch UX contract: PASS")
    print("Touch UX: explicit navigation + explicit increment/decrement controls")
    print("Network staging: visible NOT APPLIED state + Back / Discard / guarded Apply")
    print("Display Expert reverse: visible left/right semantics, no hold-to-reverse")
    print("Rotation: guarded interaction retained for finalization delta")
    print("Security posture: validated separately; not defined by this touch validator")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
