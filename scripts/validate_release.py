#!/usr/bin/env python3
"""Deterministic release/repository-state checks for Waveshare Workshop OS."""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

PRODUCTION_FULL = Path("firmware/BambuHelper-ws_lcd_350-v3.8.1-Smart-Home-v11.19.1-Physical-Fit-RC2-Full.bin")
PRODUCTION_OTA = Path("firmware/BambuHelper-ws_lcd_350-v3.8.1-Smart-Home-v11.19.1-Physical-Fit-RC2-OTA.bin")
ROLLBACK_FULL = Path("firmware/BambuHelper-ws_lcd_350-v3.8.1-Full-smart-home-v7.2-validated.bin")
ROLLBACK_OTA = Path("firmware/BambuHelper-ws_lcd_350-v3.8.1-Smart-Home-v7.2-OTA.bin")
UPSTREAM_BASELINE = "8cb1cbbb6d3c175af91989e8ebe1bbdcbe848ac4"
ACCEPTED_SOURCE_VERSION = "11.19.1"

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
    Path("LICENSE"),
    Path("NOTICE.md"),
    Path("SECURITY.md"),
    Path("CONTRIBUTING.md"),
    Path("release.json"),
    Path("releases/current.json"),
    Path("docs/REPOSITORY_HYGIENE.md"),
    Path("docs/UPSTREAM_SYNC.md"),
    Path("docs/RELEASE_PROCESS.md"),
    Path("docs/CONTROL_SAFETY.md"),
    Path("scripts/capture-ws350-views.zsh"),
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


def require_nonempty_string(mapping: dict, key: str, label: str) -> str:
    value = mapping.get(key)
    if not isinstance(value, str) or not value.strip():
        fail(f"{label}.{key} must be a non-empty string")
    return value.strip()


def validate_candidate(candidate: object, readme_text: str) -> str:
    """Validate zero-or-one active candidate without conflating it with accepted source."""
    if candidate is None:
        if "| active candidate | **None** |" not in readme_text:
            fail("README must explicitly show active candidate None when releases/current.json candidate is null")
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
        fail("candidate.physicalAcceptance must be required before promotion")

    if name not in readme_text:
        fail("README must name the active candidate from releases/current.json")
    if f"PR #{pr_number}" not in readme_text:
        fail("README must identify the active candidate pull request")
    if "| active candidate | **None** |" in readme_text:
        fail("README cannot claim there is no active candidate while candidate metadata is present")

    return f"{version} / PR #{pr_number} / {branch}"


def validate_capture_security() -> None:
    """Keep physical acceptance bundles useful without preserving live credentials."""
    capture = (ROOT / "scripts" / "capture-ws350-views.zsh").read_text(encoding="utf-8")
    required_markers = [
        'echo "Usage: $0 <device-host-or-ip>"',
        'HOST="$1"',
        'RAW_PPM="$(mktemp -t bambu-capture-frame)"',
        "stty -echo",
        "stty echo 2>/dev/null || true",
        'chmod 600 "$COOKIE" "$LOGIN_BODY" "$RAW_PPM"',
        'rm -f "$COOKIE" "$LOGIN_BODY" "$RAW_PPM"',
        "trap cleanup EXIT",
        "trap 'exit 130' INT",
        "trap 'exit 143' TERM",
        "--data-urlencode 'code@-'",
        "unset CODE",
        "Deliberately do not capture /printer/config or settings exports",
        "ppm_dst = Path(sys.argv[2])",
        "png_dst = Path(sys.argv[3])",
        "view_id == 'system'",
        "Refusing unverified System redaction geometry",
        "x0, y0, x1, y1 = 330, 196, 468, 230",
        "ppm_dst.write_bytes(header + rgb)",
        'curl -fsS -b "$COOKIE" "$BASE/hub/frame.ppm" -o "$RAW_PPM"',
        'python3 "$OUT/ppm_to_png.py" "$RAW_PPM" "$PPM" "$PNG" "$ID"',
        ': > "$RAW_PPM"',
        "SECURITY-NOTE.txt",
        "Raw framebuffer: TEMPORARY 0600 ONLY",
        "Printer configuration/settings exports: EXCLUDED",
    ]
    for marker in required_markers:
        if marker not in capture:
            fail(f"visual capture credential-safety contract missing: {marker}")

    forbidden_markers = [
        "10.0.0.124",
        '--data-urlencode "code=$CODE"',
        'echo "$CODE"',
        'echo $CODE',
        'printf "%s\\n" "$CODE"',
        '"$BASE/printer/config?slot=0"',
        '"$BASE/settings/export"',
        '"$BASE/hub/frame.ppm" -o "$PPM"',
        "src.write_bytes(header + rgb)",
        "set -x",
    ]
    for marker in forbidden_markers:
        if marker in capture:
            fail(f"visual capture helper may disclose sensitive/environment-specific configuration: {marker}")


def main() -> int:
    for rel in REQUIRED:
        if not (ROOT / rel).is_file():
            fail(f"missing required repository asset: {rel}")

    license_text = (ROOT / "LICENSE").read_text(encoding="utf-8")
    if not license_text.startswith("MIT License\n"):
        fail("top-level LICENSE must contain the MIT license text")

    notice_text = (ROOT / "NOTICE.md").read_text(encoding="utf-8")
    if "Keralots/BambuHelper" not in notice_text or UPSTREAM_BASELINE not in notice_text:
        fail("NOTICE.md must identify Keralots/BambuHelper and the accepted upstream baseline")
    if "does not invent" not in notice_text:
        fail("NOTICE.md must preserve the no-invented-upstream-copyright boundary")

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

    validate_capture_security()

    parsed: dict[str, dict] = {}
    for rel in (Path("release.json"), Path("releases/current.json")):
        try:
            parsed[rel.as_posix()] = json.loads((ROOT / rel).read_text(encoding="utf-8"))
        except Exception as exc:
            fail(f"invalid JSON in {rel}: {exc}")

    release = parsed["release.json"]
    profiles = release.get("profiles", {})
    if set(profiles) != {"workshop-os-v11.19.1", "smart-home-v7.2"}:
        fail("release.json must expose exactly production Workshop OS v11.19.1 and rollback v7.2")
    expected_paths = {
        ("workshop-os-v11.19.1", "file"): PRODUCTION_FULL.as_posix(),
        ("workshop-os-v11.19.1", "otaFile"): PRODUCTION_OTA.as_posix(),
        ("smart-home-v7.2", "file"): ROLLBACK_FULL.as_posix(),
        ("smart-home-v7.2", "otaFile"): ROLLBACK_OTA.as_posix(),
    }
    for (profile, key), expected in expected_paths.items():
        if profiles.get(profile, {}).get(key) != expected:
            fail(f"release.json {profile}.{key} must be {expected}")

    manifest = parsed["releases/current.json"]
    if manifest.get("channel") != "accepted-source":
        fail("releases/current.json channel must be accepted-source")
    if manifest.get("version") != ACCEPTED_SOURCE_VERSION:
        fail(f"releases/current.json version must identify accepted v{ACCEPTED_SOURCE_VERSION}")
    source = manifest.get("source") or {}
    if source.get("branch") != "main":
        fail("accepted source branch must be main")
    accepted_commit = source.get("acceptedFirmwareCommit", "")
    if not SHA40.fullmatch(accepted_commit):
        fail("acceptedFirmwareCommit must be a 40-character lowercase SHA")
    if source.get("physicalAcceptance") != "passed":
        fail("accepted source must record physicalAcceptance=passed")

    readme_text = (ROOT / "README.md").read_text(encoding="utf-8")
    candidate_summary = validate_candidate(manifest.get("candidate"), readme_text)

    download = manifest.get("download") or {}
    if download.get("channel") != "production-workshop-os-v11.19.1":
        fail("download channel must identify promoted Workshop OS v11.19.1")
    if str(download.get("rollbackVersion")) != "7.2":
        fail("download rollbackVersion must identify Smart Home v7.2")

    archive = ROOT / "releases" / "archive"
    if not (archive / "README.md").is_file():
        fail("historical release provenance must live under releases/archive")
    active_legacy = [p.name for p in (ROOT / "releases").glob("v9*") if p.is_dir()]
    if active_legacy:
        fail(f"historical v9 release directories remain in active namespace: {active_legacy}")

    print("Release gate: PASS")
    print(f"Accepted source: {manifest['version']} ({source.get('name', 'unnamed')})")
    print(f"Accepted firmware commit: {accepted_commit}")
    print(f"Active candidate: {candidate_summary}")
    print("Static download channel: Workshop OS v11.19.1 Full + OTA")
    print("Immediate rollback channel: Smart Home v7.2 Full + OTA")
    print("Visual capture credential redaction: REQUIRED BEFORE RETENTION")
    print("Raw framebuffer retention: FORBIDDEN; 0600 temporary file only")
    print("Capture environment-specific default host: FORBIDDEN")
    print("Capture config/settings secret export: FORBIDDEN")
    print("Firmware workflows: one reusable candidate gate + three repository/release gates")
    print("Workflow permissions: explicit contents: read on all workflows")
    print("Governance contract: SECURITY + CONTRIBUTING + release/control-safety docs + PR template present")
    print("License contract: MIT Workshop OS contributions + explicit upstream/third-party NOTICE present")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
