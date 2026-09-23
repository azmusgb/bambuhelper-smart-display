#!/usr/bin/env python3
"""Deterministic release/repository-state checks for Waveshare Workshop OS."""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Static download channel intentionally remains one release behind accepted source.
PRODUCTION_FULL = Path("firmware/BambuHelper-ws_lcd_350-v3.8.1-Smart-Home-v11.19.1-Physical-Fit-RC2-Full.bin")
PRODUCTION_OTA = Path("firmware/BambuHelper-ws_lcd_350-v3.8.1-Smart-Home-v11.19.1-Physical-Fit-RC2-OTA.bin")
ROLLBACK_FULL = Path("firmware/BambuHelper-ws_lcd_350-v3.8.1-Full-smart-home-v7.2-validated.bin")
ROLLBACK_OTA = Path("firmware/BambuHelper-ws_lcd_350-v3.8.1-Smart-Home-v7.2-OTA.bin")
UPSTREAM_BASELINE = "8cb1cbbb6d3c175af91989e8ebe1bbdcbe848ac4"
ACCEPTED_SOURCE_VERSION = "11.22"
STATIC_VERSION = "11.19.1"
STATIC_ROLLBACK_VERSION = "7.2"

ALLOWED_FIRMWARE = {
    PRODUCTION_FULL.as_posix(),
    PRODUCTION_OTA.as_posix(),
    ROLLBACK_FULL.as_posix(),
    ROLLBACK_OTA.as_posix(),
}
ALLOWED_WORKFLOWS = {
    "companion-ios.yml",
    "firmware-candidate.yml",
    "os12-platform-bridge.yml",
    "os12-tooling.yml",
    "os12-ux-architecture.yml",
    "release-gate.yml",
    "release-main.yml",
    "ui13-appliance-settings.yml",
    "validate.yml",
}
REQUIRED = [
    Path("README.md"), Path("LICENSE"), Path("NOTICE.md"), Path("SECURITY.md"),
    Path("CONTRIBUTING.md"), Path("release.json"), Path("releases/current.json"),
    Path("docs/REPOSITORY_HYGIENE.md"), Path("docs/UPSTREAM_SYNC.md"),
    Path("docs/RELEASE_PROCESS.md"), Path("docs/CONTROL_SAFETY.md"),
    Path("scripts/capture-ws350-views.zsh"), Path(".github/pull_request_template.md"),
    Path(".github/workflows/firmware-candidate.yml"), Path(".github/workflows/validate.yml"),
    PRODUCTION_FULL, PRODUCTION_OTA, ROLLBACK_FULL, ROLLBACK_OTA,
]
FORBIDDEN_PREFIXES = ("firmware/build/", ".v95/", "waveshare-workshop-os/")
FORBIDDEN_PATHS = {"web/os.config.json"}
FORBIDDEN_SECRET_FILENAMES = {".env", "id_rsa", "id_ed25519"}
FORBIDDEN_SECRET_SUFFIXES = {".pem", ".p12", ".pfx", ".key"}
SHA40 = re.compile(r"^[0-9a-f]{40}$")


def fail(message: str) -> None:
    print(f"ERROR: {message}")
    raise SystemExit(1)


def require_nonempty_string(mapping: dict, key: str, label: str) -> str:
    value = mapping.get(key)
    if not isinstance(value, str) or not value.strip():
        fail(f"{label}.{key} must be a non-empty string")
    return value.strip()


def validate_candidate(candidate: object, readme_text: str) -> str:
    if candidate is None:
        if "| active candidate | **None** |" not in readme_text:
            fail("README must explicitly show active candidate None when candidate is null")
        return "none"
    if not isinstance(candidate, dict):
        fail("candidate must be null or an object")
    version = require_nonempty_string(candidate, "version", "candidate")
    branch = require_nonempty_string(candidate, "branch", "candidate")
    name = require_nonempty_string(candidate, "name", "candidate")
    require_nonempty_string(candidate, "purpose", "candidate")
    if branch == "main":
        fail("active candidate branch must not be main before promotion")
    pr_number = candidate.get("pullRequest")
    if not isinstance(pr_number, int) or isinstance(pr_number, bool) or pr_number <= 0:
        fail("candidate.pullRequest must be a positive integer")
    if candidate.get("status") != "physical-acceptance-required":
        fail("hardware-facing candidate.status must be physical-acceptance-required")
    if candidate.get("exactHeadCi") != "required":
        fail("candidate.exactHeadCi must be required before promotion")
    if candidate.get("physicalAcceptance") != "required":
        fail("hardware-facing candidate.physicalAcceptance must be required before promotion")
    if name not in readme_text or f"PR #{pr_number}" not in readme_text:
        fail("README must identify the active candidate and PR")
    return f"{version} / PR #{pr_number} / {branch}"


def validate_main_state(main_state: object, readme_text: str) -> str:
    if main_state is None:
        return "none"
    if not isinstance(main_state, dict):
        fail("mainState must be null or an object")
    version = require_nonempty_string(main_state, "version", "mainState")
    commit = require_nonempty_string(main_state, "commit", "mainState")
    name = require_nonempty_string(main_state, "name", "mainState")
    branch = require_nonempty_string(main_state, "originatingBranch", "mainState")
    if not SHA40.fullmatch(commit):
        fail("mainState.commit must be a 40-character lowercase SHA")
    if main_state.get("status") != "merged-unaccepted":
        fail("mainState.status must be merged-unaccepted")
    if main_state.get("exactHeadCi") != "passed" or main_state.get("physicalAcceptance") != "pending":
        fail("merged-unaccepted mainState must have CI passed and physical acceptance pending")
    if main_state.get("unattendedAcceptance") != "passed":
        fail("merged-unaccepted mainState must record unattendedAcceptance=passed")
    tested_commit = require_nonempty_string(main_state, "testedCandidateCommit", "mainState")
    if not SHA40.fullmatch(tested_commit):
        fail("mainState.testedCandidateCommit must be a 40-character lowercase SHA")
    tested_firmware_sha = require_nonempty_string(main_state, "testedFirmwareSha256", "mainState")
    if not re.fullmatch(r"[0-9a-f]{64}", tested_firmware_sha):
        fail("mainState.testedFirmwareSha256 must be a 64-character lowercase SHA-256")
    if branch == "main":
        fail("mainState.originatingBranch must identify the source branch")
    if name not in readme_text or "merged, physical acceptance pending" not in readme_text:
        fail("README must explain merged-unaccepted main state")
    return f"{version} / physical acceptance pending"


def validate_acceptance_policy() -> None:
    release_process = (ROOT / "docs" / "RELEASE_PROCESS.md").read_text(encoding="utf-8")
    required = [
        "Routine candidate/merge testing must not require the operator to answer interactive `y/n/u` prompts.",
        "Interactive physical scripts may be used as optional diagnostic/audit tools, but they are not ordinary merge gates.",
        "Automation must not convert sensory observations into fabricated physical truth.",
        "merged-unaccepted",
        "physically validated",
        "accepted",
        "stable",
    ]
    for marker in required:
        if marker not in release_process:
            fail(f"release acceptance policy missing required boundary: {marker}")


def validate_capture_security() -> None:
    capture = (ROOT / "scripts" / "capture-ws350-views.zsh").read_text(encoding="utf-8")
    required = [
        'echo "Usage: $0 <device-host-or-ip> [--resume <capture-folder>]"', 'HOST="$1"',
        'RAW_PPM="$(mktemp -t bambu-capture-frame)"', "stty -echo",
        'chmod 600 "$COOKIE" "$LOGIN_BODY" "$RAW_PPM"',
        'rm -f "$COOKIE" "$LOGIN_BODY" "$RAW_PPM"', "trap cleanup EXIT",
        "--data-urlencode 'code@-'", "unset CODE",
        "Deliberately do not capture /printer/config or settings exports",
        "catalog_version = int(sys.argv[6])", "sensitivity != 'portal-code'",
        "view_id != 'system-portal'", "Refusing unverified UI12 portal redaction geometry",
        "redaction = (236, 146, 472, 192)",
        "catalog_version == 1 and view_id == 'system'",
        "Refusing unverified legacy System redaction geometry",
        "redaction = (330, 196, 468, 230)", "Unsupported capture catalog version",
        '"$BASE/hub/frame.ppm"', '-o "$RAW_PPM"',
        "SECURITY-NOTE.txt", "Raw framebuffer: TEMPORARY 0600 ONLY",
        "Printer configuration/settings exports: EXCLUDED",
    ]
    for marker in required:
        if marker not in capture:
            fail(f"visual capture credential-safety contract missing: {marker}")
    forbidden = [
        "10.0.0.124", '--data-urlencode "code=$CODE"', 'echo "$CODE"',
        '"$BASE/printer/config?slot=0"', '"$BASE/settings/export"', "set -x",
    ]
    for marker in forbidden:
        if marker in capture:
            fail(f"capture helper may disclose sensitive/environment-specific configuration: {marker}")


def validate_ci_ownership(workflows_dir: Path) -> None:
    validate = (workflows_dir / "validate.yml").read_text(encoding="utf-8")
    if "name: Core repository validation" not in validate:
        fail("Validate must remain the lightweight core repository gate")
    for forbidden in (
        "Workshop Companion iOS",
        "xcodebuild",
        "brew install xcodegen",
        "run_os12_platform_local.sh",
        "run_os12_ux_local.sh",
        "accept_os12_recovery_roundtrip",
    ):
        if forbidden in validate:
            fail(f"Validate contains domain-specific/heavy work: {forbidden}")

    tooling = (workflows_dir / "os12-tooling.yml").read_text(encoding="utf-8")
    for marker in (
        "name: Workshop OS 12 Tooling Checks",
        "- 'scripts/accept_os12_*.py'",
        "- 'scripts/accept_os12_*.sh'",
        "- 'scripts/validate_os12_physical_acceptance.py'",
        "- 'scripts/validate_os12_recovery_roundtrip.py'",
        "Validate recovery round-trip contract",
    ):
        if marker not in tooling:
            fail(f"OS12 Tooling workflow missing owned contract: {marker}")
    for forbidden in (
        "run_os12_ux_local.sh --build",
        "pio run",
        "PlatformIO",
    ):
        if forbidden in tooling:
            fail(f"OS12 Tooling workflow contains firmware-build work: {forbidden}")

    companion = (workflows_dir / "companion-ios.yml").read_text(encoding="utf-8")
    for marker in (
        "name: Workshop Companion iOS",
        "paths:",
        "- 'companion/**'",
        "- 'scripts/validate_companion_protocol.py'",
        "Compile iOS Simulator app",
    ):
        if marker not in companion:
            fail(f"Companion workflow missing path-owned contract: {marker}")

    legacy = (workflows_dir / "firmware-candidate.yml").read_text(encoding="utf-8")
    legacy_header = legacy.split("workflow_dispatch:", 1)[0]
    if "\n    paths:\n" not in legacy_header:
        fail("legacy firmware gate must be path-filtered")
    for forbidden in (
        "'scripts/validate_*.py'",
        "'apply_smart_home_*.py'",
        "'README.md'",
        "'SECURITY.md'",
    ):
        if forbidden in legacy_header:
            fail(f"legacy firmware gate trigger is too broad: {forbidden}")

    ux = (workflows_dir / "os12-ux-architecture.yml").read_text(encoding="utf-8")
    for forbidden in (
        "- 'scripts/*os12*'",
        "- 'scripts/accept_os12_*.py'",
        "- 'scripts/accept_os12_*.sh'",
        "- 'scripts/capture-ws350-views.zsh'",
        "- 'scripts/bootstrap_ws350_os12_usb_macos.sh'",
        "- 'docs/WORKSHOP_OS12_DEVICE_PLATFORM.md'",
        "- 'docs/DEVICE_NATIVE_UPDATES.md'",
        "- 'docs/MEDIA_PHYSICAL_ACCEPTANCE.md'",
    ):
        if forbidden in ux:
            fail(f"OS12 UX candidate trigger is too broad: {forbidden}")
    for marker in (
        "- 'apply_workshop_os12_*.py'",
        "- 'scripts/run_os12_ux_local.sh'",
        "- 'scripts/validate_os12_*.py'",
        "- 'firmware/platform/**'",
    ):
        if marker not in ux:
            fail(f"OS12 UX candidate lost a reconstruction input: {marker}")

    platform = (workflows_dir / "os12-platform-bridge.yml").read_text(encoding="utf-8")
    for forbidden in (
        "- 'apply_workshop_os12_*.py'",
        "- 'scripts/*os12*'",
        "- '.github/workflows/validate.yml'",
    ):
        if forbidden in platform:
            fail(f"OS12 Platform Bridge trigger is too broad: {forbidden}")
    for marker in (
        "- 'firmware/platform/**'",
        "- 'apply_workshop_os12_platform_bridge.py'",
        "- 'apply_workshop_os12_inventory_service.py'",
        "- 'scripts/run_os12_platform_local.sh'",
    ):
        if marker not in platform:
            fail(f"OS12 Platform Bridge lost an authoritative platform input: {marker}")

    release_gate = (workflows_dir / "release-gate.yml").read_text(encoding="utf-8")
    for marker in (
        'required=("Validate")',
        "legacy_firmware_required=0",
        "platform_required=0",
        "os12_required=0",
        "companion_required=0",
        "tooling_required=0",
        'required+=("Workshop OS 12 UX Architecture")',
        'required+=("Workshop OS 12 Platform Bridge")',
        'required+=("Workshop Companion iOS")',
        'required+=("Workshop OS 12 Tooling Checks")',
    ):
        if marker not in release_gate:
            fail(f"Release Gate missing path-aware aggregation contract: {marker}")
    if "Validate shell scripts" in release_gate:
        fail("Release Gate must not duplicate Core Validate shell syntax work")


def main() -> int:
    for rel in REQUIRED:
        if not (ROOT / rel).is_file():
            fail(f"missing required repository asset: {rel}")

    if not (ROOT / "LICENSE").read_text(encoding="utf-8").startswith("MIT License\n"):
        fail("top-level LICENSE must contain MIT license text")
    notice_text = (ROOT / "NOTICE.md").read_text(encoding="utf-8")
    if "Keralots/BambuHelper" not in notice_text or UPSTREAM_BASELINE not in notice_text:
        fail("NOTICE.md must identify upstream BambuHelper and pinned baseline")
    if "does not invent" not in notice_text:
        fail("NOTICE.md must preserve upstream attribution boundary")

    tracked_firmware: set[str] = set()
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(ROOT).as_posix()
        if rel.startswith(FORBIDDEN_PREFIXES) or rel in FORBIDDEN_PATHS:
            fail(f"forbidden generated/superseded content is present: {rel}")
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
        fail(f"firmware retention mismatch: {sorted(tracked_firmware)}")

    workflows_dir = ROOT / ".github" / "workflows"
    workflows = {p.name for p in workflows_dir.glob("*.yml") if p.is_file()}
    if workflows != ALLOWED_WORKFLOWS:
        fail(f"workflow surface mismatch: {sorted(workflows)}")
    for name in sorted(ALLOWED_WORKFLOWS):
        text = (workflows_dir / name).read_text(encoding="utf-8")
        if "permissions:\n  contents: read" not in text:
            fail(f"workflow must declare contents: read: {name}")
    validate_ci_ownership(workflows_dir)
    validate_acceptance_policy()
    validate_capture_security()

    release = json.loads((ROOT / "release.json").read_text(encoding="utf-8"))
    manifest = json.loads((ROOT / "releases/current.json").read_text(encoding="utf-8"))

    profiles = release.get("profiles", {})
    if set(profiles) != {"workshop-os-v11.19.1", "smart-home-v7.2"}:
        fail("static release.json must still expose v11.19.1 production + v7.2 rollback")
    expected_paths = {
        ("workshop-os-v11.19.1", "file"): PRODUCTION_FULL.as_posix(),
        ("workshop-os-v11.19.1", "otaFile"): PRODUCTION_OTA.as_posix(),
        ("smart-home-v7.2", "file"): ROLLBACK_FULL.as_posix(),
        ("smart-home-v7.2", "otaFile"): ROLLBACK_OTA.as_posix(),
    }
    for (profile, key), expected in expected_paths.items():
        if profiles.get(profile, {}).get(key) != expected:
            fail(f"release.json {profile}.{key} must be {expected}")

    if manifest.get("channel") != "accepted-source":
        fail("releases/current.json channel must be accepted-source")
    if manifest.get("version") != ACCEPTED_SOURCE_VERSION:
        fail(f"accepted source version must be {ACCEPTED_SOURCE_VERSION}")
    source = manifest.get("source") or {}
    if source.get("branch") != "main":
        fail("accepted source branch must be main")
    accepted_commit = source.get("acceptedFirmwareCommit", "")
    if not SHA40.fullmatch(accepted_commit):
        fail("acceptedFirmwareCommit must be a 40-character lowercase SHA")
    if source.get("physicalAcceptance") != "passed":
        fail("accepted source must record physicalAcceptance=passed")

    readme_text = (ROOT / "README.md").read_text(encoding="utf-8")
    if "Workshop OS v11.22" not in readme_text:
        fail("README must identify accepted Workshop OS v11.22")
    candidate_summary = validate_candidate(manifest.get("candidate"), readme_text)
    main_state_summary = validate_main_state(manifest.get("mainState"), readme_text)

    download = manifest.get("download") or {}
    if download.get("channel") != "production-workshop-os-v11.19.1":
        fail("static download channel must remain Workshop OS v11.19.1 until binary promotion")
    if str(download.get("rollbackVersion")) != STATIC_ROLLBACK_VERSION:
        fail("static rollbackVersion must remain Smart Home v7.2")

    archive = ROOT / "releases" / "archive"
    if not (archive / "README.md").is_file():
        fail("historical release provenance must live under releases/archive")

    print("Release gate: PASS")
    print(f"Accepted source: {manifest['version']} ({source.get('name', 'unnamed')})")
    print(f"Accepted firmware commit: {accepted_commit}")
    print(f"Active candidate: {candidate_summary}")
    print(f"Main state: {main_state_summary}")
    print("Static download channel: Workshop OS v11.19.1 Full + OTA")
    print("Immediate static rollback: Smart Home v7.2 Full + OTA")
    print("Visual capture credential redaction: REQUIRED BEFORE RETENTION")
    print("CI ownership: lightweight core validate + path-owned domain gates + release aggregation")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
