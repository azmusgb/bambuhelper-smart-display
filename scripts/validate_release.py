#!/usr/bin/env python3
"""Deterministic release/repository-state checks for Waveshare Workshop OS."""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

PRODUCTION_FULL = Path("firmware/BambuHelper-ws_lcd_350-v3.8.1-Full-smart-home-v7.2-validated.bin")
PRODUCTION_OTA = Path("firmware/BambuHelper-ws_lcd_350-v3.8.1-Smart-Home-v7.2-OTA.bin")
ROLLBACK_FULL = Path("firmware/BambuHelper-ws_lcd_350-v3.8.1-Full-smart-home-v7.1-validated.bin")
ROLLBACK_OTA = Path("firmware/BambuHelper-ws_lcd_350-v3.8.1-Smart-Home-v7.1-OTA.bin")

ALLOWED_FIRMWARE = {
    PRODUCTION_FULL.as_posix(),
    PRODUCTION_OTA.as_posix(),
    ROLLBACK_FULL.as_posix(),
    ROLLBACK_OTA.as_posix(),
}
ALLOWED_WORKFLOWS = {
    "firmware-candidate.yml",
    "release-gate.yml",
    "release-main.yml",
    "validate.yml",
}

REQUIRED = [
    Path("README.md"),
    Path("SECURITY.md"),
    Path("CONTRIBUTING.md"),
    Path("release.json"),
    Path("releases/current.json"),
    Path("docs/REPOSITORY_HYGIENE.md"),
    Path("docs/UPSTREAM_SYNC.md"),
    Path("docs/RELEASE_PROCESS.md"),
    Path("docs/CONTROL_SAFETY.md"),
    Path(".github/pull_request_template.md"),
    Path(".github/workflows/firmware-candidate.yml"),
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
FORBIDDEN_PATHS = {"web/os.config.json"}
FORBIDDEN_SECRET_FILENAMES = {
    ".env",
    "id_rsa",
    "id_ed25519",
}
FORBIDDEN_SECRET_SUFFIXES = {".pem", ".p12", ".pfx", ".key"}
SHA40 = re.compile(r"^[0-9a-f]{40}$")


def fail(message: str) -> None:
    print(f"ERROR: {message}")
    raise SystemExit(1)


def main() -> int:
    for rel in REQUIRED:
        if not (ROOT / rel).is_file():
            fail(f"missing required repository asset: {rel}")

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
        if path.name in FORBIDDEN_SECRET_FILENAMES or path.suffix.lower() in FORBIDDEN_SECRET_SUFFIXES:
            fail(f"secret/private-key style file must not be tracked: {rel}")
        if path.name.startswith(".env.") and path.name != ".env.example":
            fail(f"environment secret file must not be tracked: {rel}")
        if rel.startswith("firmware/") and rel.endswith(".bin"):
            tracked_firmware.add(rel)
            if rel not in ALLOWED_FIRMWARE:
                fail(f"unexpected tracked firmware binary: {rel}")

    if tracked_firmware != ALLOWED_FIRMWARE:
        fail(
            "firmware retention mismatch; "
            f"missing={sorted(ALLOWED_FIRMWARE - tracked_firmware)}, "
            f"extra={sorted(tracked_firmware - ALLOWED_FIRMWARE)}"
        )

    workflows_dir = ROOT / ".github" / "workflows"
    workflows = {p.name for p in workflows_dir.glob("*.yml") if p.is_file()}
    if workflows != ALLOWED_WORKFLOWS:
        fail(
            "workflow surface mismatch; "
            f"missing={sorted(ALLOWED_WORKFLOWS - workflows)}, "
            f"extra={sorted(workflows - ALLOWED_WORKFLOWS)}"
        )
    if any(name.startswith("bambuhelper-v") for name in workflows):
        fail("version-named firmware workflow present; use firmware-candidate.yml")
    for name in sorted(ALLOWED_WORKFLOWS):
        workflow_text = (workflows_dir / name).read_text(encoding="utf-8")
        if "permissions:\n  contents: read" not in workflow_text:
            fail(f"workflow must declare least-privilege contents: read permissions: {name}")

    parsed: dict[str, dict] = {}
    for rel in (Path("release.json"), Path("releases/current.json")):
        try:
            parsed[rel.as_posix()] = json.loads((ROOT / rel).read_text(encoding="utf-8"))
        except Exception as exc:
            fail(f"invalid JSON in {rel}: {exc}")

    release = parsed["release.json"]
    profiles = release.get("profiles", {})
    if set(profiles) != {"smart-home-v7.2", "smart-home-v7.1"}:
        fail("release.json must expose exactly production v7.2 and rollback v7.1")
    expected_paths = {
        ("smart-home-v7.2", "file"): PRODUCTION_FULL.as_posix(),
        ("smart-home-v7.2", "otaFile"): PRODUCTION_OTA.as_posix(),
        ("smart-home-v7.1", "file"): ROLLBACK_FULL.as_posix(),
        ("smart-home-v7.1", "otaFile"): ROLLBACK_OTA.as_posix(),
    }
    for (profile, key), expected in expected_paths.items():
        if profiles.get(profile, {}).get(key) != expected:
            fail(f"release.json {profile}.{key} must be {expected}")

    manifest = parsed["releases/current.json"]
    if manifest.get("channel") != "accepted-source":
        fail("releases/current.json channel must be accepted-source")
    if manifest.get("version") != "11.19.1":
        fail("releases/current.json version must identify accepted v11.19.1")
    source = manifest.get("source") or {}
    if source.get("branch") != "main":
        fail("accepted source branch must be main")
    accepted_commit = source.get("acceptedFirmwareCommit", "")
    if not SHA40.fullmatch(accepted_commit):
        fail("acceptedFirmwareCommit must be a 40-character lowercase SHA")
    if source.get("physicalAcceptance") != "passed":
        fail("accepted source must record physicalAcceptance=passed")
    if manifest.get("candidate") is not None:
        fail("candidate must be null when no active firmware candidate exists")
    download = manifest.get("download") or {}
    if download.get("channel") != "production-rc-v7.2":
        fail("download channel must remain production-rc-v7.2 until separately promoted")
    if str(download.get("rollbackVersion")) != "7.1":
        fail("download rollbackVersion must remain 7.1")

    archive = ROOT / "releases" / "archive"
    if not (archive / "README.md").is_file():
        fail("historical release provenance must live under releases/archive")
    active_legacy = [p.name for p in (ROOT / "releases").glob("v9*") if p.is_dir()]
    if active_legacy:
        fail(f"historical v9 release directories remain in active namespace: {active_legacy}")

    print("Release gate: PASS")
    print(f"Accepted source: {manifest['version']} ({source.get('name', 'unnamed')})")
    print(f"Accepted firmware commit: {accepted_commit}")
    print("Static download channel: v7.2 Full + OTA")
    print("Immediate rollback channel: v7.1 Full + OTA")
    print("Firmware workflows: one reusable candidate gate + three repository/release gates")
    print("Workflow permissions: explicit contents: read on all workflows")
    print("Governance contract: SECURITY + CONTRIBUTING + release/control-safety docs + PR template present")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
