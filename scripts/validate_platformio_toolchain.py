#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path


class ValidationError(RuntimeError):
    pass


def read(path: Path) -> str:
    if not path.is_file():
        raise ValidationError(f"missing {path}")
    return path.read_text(encoding="utf-8")


def require(text: str, needle: str, label: str) -> None:
    if needle not in text:
        raise ValidationError(f"{label}: missing {needle!r}")


def forbid(text: str, needle: str, label: str) -> None:
    if needle in text:
        raise ValidationError(f"{label}: forbidden marker present: {needle!r}")


def main() -> int:
    root = Path(__file__).resolve().parents[1]

    ensure = read(root / "scripts/ensure-platformio.sh")
    bootstrap = read(root / "scripts/bootstrap_ws350_os12_usb_macos.sh")
    exact_ci_installer = read(root / "scripts/flash_os12_ci_candidate_macos.sh")
    ui13_runner = read(root / "scripts/run_ui13_local.sh")
    platform_workflow = read(root / ".github/workflows/os12-platform-bridge.yml")
    ux_workflow = read(root / ".github/workflows/os12-ux-architecture.yml")
    ui13_workflow = read(root / ".github/workflows/ui13-appliance-settings.yml")

    for needle in (
        "3.9|3.10|3.11|3.12) return 0",
        "WORKSHOP_PLATFORMIO_PYTHON",
        "Python 3.13+ is intentionally rejected",
        "platformio==6.2.0",
        'PlatformIO Python: $VENV/bin/python',
    ):
        require(ensure, needle, "repository PlatformIO authority")
    forbid(ensure, "3.9|3.10|3.11|3.12|3.13) return 0", "known-bad Python 3.13 acceptance")
    forbid(ensure, 'command -v python3.13', "known-bad Python 3.13 selection")

    for needle in (
        'PIO_PYTHON="$(dirname "$PIO_BIN")/python"',
        '"$PIO_PYTHON" -m venv "$venv"',
        "--expect-source-sha",
        "--expect-firmware-sha256",
        "local source SHA does not match the exact-head CI candidate",
        "locally reconstructed firmware does not match the exact-head CI candidate bytes",
        "PASS: local firmware bytes exactly match the recorded CI candidate SHA-256.",
        "=== Partition-layout gate ===",
        "Cross-line migration must use the approved Full image at flash offset 0x0",
    ):
        require(bootstrap, needle, "USB bootstrap toolchain/recovery/artifact boundary")

    for needle in (
        'if [[ "$FLASH" -eq 1 && -z "$EXPECT_SOURCE_SHA" ]]',
        'if [[ "$FLASH" -eq 1 && -z "$EXPECT_FIRMWARE_SHA256" ]]',
        'if [[ -n "$EXPECT_SOURCE_SHA" && "$HEAD_SHA" != "$EXPECT_SOURCE_SHA" ]]',
        'if [[ -n "$EXPECT_FIRMWARE_SHA256" ]]',
        'if [[ "$FIRMWARE_SHA256" != "$EXPECT_FIRMWARE_SHA256" ]]',
    ):
        require(bootstrap, needle, "physical flash exact-artifact guard")

    for needle in (
        "CANDIDATE BUILD CHECKS: PASS",
        "No USB device access was performed.",
        'if [[ "$CONFIRM_IDLE" -ne 1 ]]',
        "Printer-idle confirmation received before USB reset/probe.",
    ):
        require(bootstrap, needle, "USB preflight idle-safety guard")

    idle_gate = bootstrap.index('if [[ "$CONFIRM_IDLE" -ne 1 ]]')
    usb_resolver = bootstrap.index('PORT="$(PIO_BIN="$PIO_BIN" bash scripts/waveshare-usb.sh port)"')
    if idle_gate < 0 or usb_resolver < 0 or idle_gate > usb_resolver:
        raise ValidationError("printer-idle confirmation must be enforced before USB resolver/esptool access")

    for needle in (
        'PIO_BIN="$(ROOT="$ROOT" bash "$ROOT/scripts/ensure-platformio.sh")"',
        '"$PIO_BIN" run -e ws_lcd_350',
        '"$PIO_BIN" run -e jc3248w535',
    ):
        require(ui13_runner, needle, "UI13 build toolchain")
    for needle in (
        "pip install --user --upgrade platformio",
        '(cd "$BUILD" && pio run -e ws_lcd_350)',
        '(cd "$BUILD" && pio run -e jc3248w535)',
    ):
        forbid(ui13_runner, needle, "parallel/global PlatformIO path")

    for label, workflow in (
        ("OS12 platform workflow", platform_workflow),
        ("OS12 UX workflow", ux_workflow),
        ("UI13 workflow", ui13_workflow),
    ):
        require(workflow, "actions/setup-python@v5", label)
        require(workflow, "python-version: '3.12'", label)
        require(workflow, "scripts/ensure-platformio.sh", label)

    for label, workflow in (
        ("OS12 platform workflow", platform_workflow),
        ("OS12 UX workflow", ux_workflow),
        ("UI13 workflow", ui13_workflow),
    ):
        forbid(workflow, "python3 -m pip install --upgrade platformio", f"{label} global PlatformIO install")

    for needle in (
        "artifact_role=platform-regression-evidence",
        "physical_candidate=false",
        "flashable_artifact_published=false",
        "physical_candidate_authority=.github/workflows/os12-ux-architecture.yml",
        "name: workshop-os12-platform-regression-evidence-",
    ):
        require(platform_workflow, needle, "OS12 platform workflow artifact role")
    for needle in (
        "name: workshop-os12-ws350-ota-",
        'cp "$SOURCE" "$OUT/$NAME"',
        "artifact_type=OTA/application image",
    ):
        forbid(platform_workflow, needle, "parallel flashable platform artifact")

    for needle in (
        '"artifactRole": "physical-acceptance-candidate"',
        '"candidateAuthority": "os12-ux-architecture"',
        "name: os12-ux-ws350-",
        'cp "$SRC" "$OUT/firmware.bin"',
        'cp "$PART" "$OUT/partitions.bin"',
        '"partitionSha256": "%s"',
        '"partitionSize": %s',
    ):
        require(ux_workflow, needle, "OS12 UX physical candidate authority")

    for needle in (
        "This is the canonical macOS physical-candidate installer.",
        "DOES NOT rebuild",
        "DOES NOT invoke PlatformIO",
        'CI_PARTITIONS="$CANDIDATE_DIR/partitions.bin"',
        '"partitionSha256": part_hash',
        "--confirm-printer-idle",
        "--full-backup",
        "=== Partition-layout gate ===",
        'cmp -s "$BACKUP_DIR/partition-table.bin" "$CI_PARTITIONS"',
        'install_transport=manual-ota-exact-ci-artifact',
        'X-SHA256: $EXPECT_FIRMWARE_SHA256',
        '$BASE_URL/ota/upload',
        "PlatformIO used on Mac: NO",
    ):
        require(exact_ci_installer, needle, "exact-CI macOS physical installer")
    for needle in (
        "scripts/ensure-platformio.sh",
        "pio run",
        "run_os12_ux_local.sh",
        "firmware.bin changed before upload",
    ):
        forbid(exact_ci_installer, needle, "exact-CI installer local-build bypass")

    print(
        "PASS: Workshop OS build tooling has one pinned CI PlatformIO authority, "
        "the OS12 UX workflow is the sole flashable physical-candidate authority, "
        "and macOS physical acceptance verifies CI firmware+partition evidence before exact-artifact OTA "
        "without rebuilding firmware or invoking PlatformIO locally"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ValidationError as exc:
        print(f"FAIL: {exc}")
        raise SystemExit(1)
