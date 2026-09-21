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
        'if [[ "$HEAD_SHA" != "$EXPECT_SOURCE_SHA" ]]',
        'if [[ "$FIRMWARE_SHA256" != "$EXPECT_FIRMWARE_SHA256" ]]',
    ):
        require(bootstrap, needle, "physical flash exact-artifact guard")

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

    print(
        "PASS: Workshop OS build/flash tooling has one pinned PlatformIO authority, "
        "rejects known-bad Python 3.13+, and requires exact CI source+firmware identity for physical flash"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ValidationError as exc:
        print(f"FAIL: {exc}")
        raise SystemExit(1)
