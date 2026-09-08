#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path


def fail(message: str) -> None:
    raise SystemExit(f"RC7 validation failed: {message}")


def require(text: str, needle: str, where: str) -> None:
    if needle not in text:
        fail(f"{where}: missing {needle!r}")


def forbid(text: str, needle: str, where: str) -> None:
    if needle in text:
        fail(f"{where}: forbidden {needle!r}")


def main() -> int:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
    frag_dir = root / "firmware" / "ui-v11.25-rc7"
    expected = {"shared.cppfrag", "home.cppfrag", "printer.cppfrag", "workshop.cppfrag", "more_system.cppfrag"}
    actual = {p.name for p in frag_dir.glob("*.cppfrag")}
    if actual != expected:
        fail(f"fragment set mismatch: expected {sorted(expected)}, got {sorted(actual)}")

    combined = "\n".join((frag_dir / name).read_text(encoding="utf-8") for name in sorted(expected))
    patcher = (root / "apply_workshop_os_ui_overhaul_v11_25_rc7.py").read_text(encoding="utf-8")
    css = (root / "assets" / "v11_25_rc7_portal.css").read_text(encoding="utf-8")
    doc = (root / "docs" / "UX_UI_V11_25_RC7.md").read_text(encoding="utf-8")

    for marker in ("UI7-H", "UI7-P", "UI7-W", "UI7-M", "UI7-S"):
        require(combined, marker, "native fragments")
    for label in ("HOME", "PRINTER", "WORKSHOP", "MORE", "STATUS", "AMS", "CONTROL"):
        require(combined, f'"{label}"', "native fragments")
    for state in ("SET UP PRINTER", "PRINTER OFFLINE", "NEXT ACTION", "NO PRINTER", "HOLD TO STOP", "PORTAL CODE"):
        require(combined, state, "native fragments")
    require(combined, "securityPortalCode()", "System secure access")
    if combined.count("securityPortalCode()") < 2:
        fail("portal code must render in both landscape and portrait System layouts")

    for forbidden in ("TEST / NO CODE", "Inventory: Unknown", "DIRECT CONTROLS"):
        forbid(combined, forbidden, "RC7 presentation")

    for needle in (
        "Workshop OS v11.25 RC6 Secure Physical Acceptance",
        "Workshop OS v11.25 RC7 Touch-First UX Overhaul",
        "secure-physical-acceptance",
        "touch-first-ux",
        'WORKSHOP_OS_UI_SCHEMA "UI7"',
        "securityPortalCode()",
        "v11_25_rc7_portal.css",
        "HOLD TO APPLY",
    ):
        require(patcher, needle, "RC7 patcher")
    for forbidden in ("matchSpoolByColor", "matchSpoolByMaterial", "resolveSpool"):
        require(patcher, forbidden, "fail-closed inventory guard")

    for needle in ("--rc7-touch: 48px", ":focus-visible", "prefers-reduced-motion", "min-height: var(--rc7-touch)"):
        require(css, needle, "portal CSS")
    require(doc, "Touch first", "UX contract")
    require(doc, "Physical acceptance after CI", "UX contract")

    print("RC7 UX source contracts: PASS")
    print("- native UI7 fragments complete")
    print("- secure portal-code visibility retained")
    print("- action-first copy and guarded-action language present")
    print("- portal touch/focus/reduced-motion rules present")
    print("- inventory inference remains fail-closed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
