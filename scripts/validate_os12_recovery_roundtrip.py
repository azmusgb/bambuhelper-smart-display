#!/usr/bin/env python3
"""Validate the guarded unattended OS12 full-image recovery round-trip helper."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "accept_os12_recovery_roundtrip_macos.sh"


def fail(message: str) -> None:
    raise SystemExit(f"FAIL: {message}")


def main() -> int:
    if not SCRIPT.is_file():
        fail(f"missing recovery round-trip helper: {SCRIPT}")
    text = SCRIPT.read_text(encoding="utf-8")

    required = (
        "--artifact-zip",
        "--confirm-printer-idle",
        "--exercise",
        "releases/current.json",
        "testedCandidateCommit",
        "testedFirmwareSha256",
        "assert_code_free_portal",
        'read_flash 0x8000',
        'read_flash 0x0 "$FLASH_SIZE_HEX" "$FULL_IMAGE"',
        'write_flash 0x0 "$FULL_IMAGE"',
        "cmp -s",
        "16777216",
        "No interactive prompts will be used.",
        "historicalRollbackTested",
        '"accepted": False',
        '"stable": False',
        "does NOT prove a historical-version rollback",
    )
    for marker in required:
        if marker not in text:
            fail(f"recovery helper missing required safety/provenance marker: {marker}")

    forbidden = (
        "erase_flash",
        "input(",
        "read -p",
        " run -e ws_lcd_350 ",
        "write_flash 0x10000",
    )
    for marker in forbidden:
        if marker in text:
            fail(f"recovery helper contains prohibited mutation/interaction marker: {marker}")

    idle_guard = text.find('[[ "$CONFIRM_IDLE" -eq 1 ]]')
    exercise_guard = text.find('[[ "$EXERCISE" -eq 1 ]]')
    write = text.find('run_esptool write_flash 0x0 "$FULL_IMAGE"')
    capture = text.find('run_esptool read_flash 0x0 "$FLASH_SIZE_HEX" "$FULL_IMAGE"')
    partition_gate = text.find('if ! cmp -s "$LIVE_PARTITIONS" "$CI_PARTITIONS"')
    if min(idle_guard, exercise_guard, capture, partition_gate, write) < 0:
        fail("recovery helper guard ordering markers are incomplete")
    if not (idle_guard < exercise_guard < partition_gate < capture < write):
        fail("recovery mutation is not ordered behind idle/exercise/partition/capture guards")

    print("PASS: OS12 unattended recovery round-trip helper preserves guarded 0x0 recovery boundaries")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
