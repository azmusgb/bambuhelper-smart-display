#!/usr/bin/env python3
"""Deterministic release-gate checks for the Waveshare Smart Display repository."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

PRODUCTION_FULL = Path(
    "firmware/BambuHelper-ws_lcd_350-v3.8.1-Full-smart-home-v7.2-validated.bin"
)
PRODUCTION_OTA = Path(
    "firmware/BambuHelper-ws_lcd_350-v3.8.1-Smart-Home-v7.2-OTA.bin"
)
ROLLBACK_FULL = Path(
    "firmware/BambuHelper-ws_lcd_350-v3.8.1-Full-smart-home-v7.1-validated.bin"
)
ROLLBACK_OTA = Path(
    "firmware/BambuHelper-ws_lcd_350-v3.8.1-Smart-Home-v7.1-OTA.bin"
)

ALLOWED_FIRMWARE = {
    PRODUCTION_FULL.as_posix(),
    PRODUCTION_OTA.as_posix(),
    ROLLBACK_FULL.as_posix(),
    ROLLBACK_OTA.as_posix(),
}

REQUIRED = [
    Path("README.md"),
    Path("release.json"),
    Path("releases/current.json"),
    Path(".github/workflows/validate.yml"),
    PRODUCTION_FULL,
    PRODUCTION_OTA,
    ROLLBACK_FULL,
    ROLLBACK_OTA,
]

FORBIDDEN_PREFIXES = (
    "firmware/build/",
    ".v95/",
    "waveshare-workshop-os/",
)
FORBIDDEN_PATHS = {
    "web/os.config.json",
}


def fail(message: str) -> None:
    print(f"ERROR: {message}")
    raise SystemExit(1)


def main() -> int:
    for rel in REQUIRED:
        if not (ROOT / rel).is_file():
            fail(f"missing required release asset: {rel}")

    tracked_firmware: set[str] = set()
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue

        rel = path.relative_to(ROOT).as_posix()
        if rel.startswith(FORBIDDEN_PREFIXES):
            fail(f"forbidden generated/superseded content is present: {rel}")
        if rel in FORBIDDEN_PATHS:
            fail(f"forbidden superseded content is present: {rel}")
        if path.parent == ROOT and path.name.startswith("validation-report"):
            fail(f"ad-hoc validation report is present in repository root: {rel}")

        if rel.startswith("firmware/") and rel.endswith(".bin"):
            tracked_firmware.add(rel)
            if rel not in ALLOWED_FIRMWARE:
                fail(f"unexpected tracked firmware binary: {rel}")

    if tracked_firmware != ALLOWED_FIRMWARE:
        missing = sorted(ALLOWED_FIRMWARE - tracked_firmware)
        extra = sorted(tracked_firmware - ALLOWED_FIRMWARE)
        fail(f"firmware retention mismatch; missing={missing}, extra={extra}")

    parsed: dict[str, dict] = {}
    for rel in (Path("release.json"), Path("releases/current.json")):
        try:
            parsed[rel.as_posix()] = json.loads((ROOT / rel).read_text(encoding="utf-8"))
        except Exception as exc:
            fail(f"invalid JSON in {rel}: {exc}")

    manifest = parsed["releases/current.json"]
    if not manifest.get("version"):
        fail("releases/current.json has no version")
    if not manifest.get("channel"):
        fail("releases/current.json has no channel")

    release = parsed["release.json"]
    profiles = release.get("profiles", {})
    if set(profiles) != {"smart-home-v7.2", "smart-home-v7.1"}:
        fail("release.json must expose exactly production v7.2 and rollback v7.1")
    if profiles["smart-home-v7.2"].get("file") != PRODUCTION_FULL.as_posix():
        fail("release.json production Full firmware path is inconsistent")
    if profiles["smart-home-v7.2"].get("otaFile") != PRODUCTION_OTA.as_posix():
        fail("release.json production OTA firmware path is inconsistent")
    if profiles["smart-home-v7.1"].get("file") != ROLLBACK_FULL.as_posix():
        fail("release.json rollback Full firmware path is inconsistent")
    if profiles["smart-home-v7.1"].get("otaFile") != ROLLBACK_OTA.as_posix():
        fail("release.json rollback OTA firmware path is inconsistent")

    print("Release gate: PASS")
    print(f"Current candidate: {manifest['version']} ({manifest['channel']})")
    print("Accepted download firmware: v7.2 Full + OTA")
    print("Immediate rollback firmware: v7.1 Full + OTA")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
