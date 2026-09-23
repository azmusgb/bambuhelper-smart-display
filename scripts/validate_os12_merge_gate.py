#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path


class ValidationError(RuntimeError):
    pass


def require(text: str, needle: str, label: str) -> None:
    if needle not in text:
        raise ValidationError(f"{label}: missing {needle!r}")


def forbid(text: str, needle: str, label: str) -> None:
    if needle in text:
        raise ValidationError(f"{label}: forbidden broad ownership marker {needle!r}")


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    workflows = root / ".github" / "workflows"
    release_gate = (workflows / "release-gate.yml").read_text(encoding="utf-8")
    platform = (workflows / "os12-platform-bridge.yml").read_text(encoding="utf-8")
    ux = (workflows / "os12-ux-architecture.yml").read_text(encoding="utf-8")
    tooling = (workflows / "os12-tooling.yml").read_text(encoding="utf-8")
    platform_trigger = platform.split("permissions:", 1)[0]
    ux_trigger = ux.split("permissions:", 1)[0]
    tooling_trigger = tooling.split("permissions:", 1)[0]

    # Release Gate is the path-aware aggregator. It must always require the
    # lightweight core Validate workflow and conditionally add OS12 owners.
    for needle in (
        'required=("Validate")',
        "os12_required=0",
        "platform_required=0",
        "tooling_required=0",
        ".github/workflows/os12-platform-bridge.yml",
        ".github/workflows/os12-ux-architecture.yml",
        ".github/workflows/os12-tooling.yml",
        'required+=("Workshop OS 12 Platform Bridge")',
        'required+=("Workshop OS 12 UX Architecture")',
        'required+=("Workshop OS 12 Tooling Checks")',
        "Wait for required workflow gates",
    ):
        require(release_gate, needle, "OS12 merge-gate coverage")

    poll_i = release_gate.index("Wait for required workflow gates")
    for needle in (
        'required+=("Workshop OS 12 Platform Bridge")',
        'required+=("Workshop OS 12 UX Architecture")',
        'required+=("Workshop OS 12 Tooling Checks")',
    ):
        if release_gate.index(needle) > poll_i:
            raise ValidationError(f"{needle} is added after merge-gate polling")

    # Platform Bridge owns platform/service/control inputs only. Presentation
    # reconstruction and acceptance helpers must not broaden this trigger.
    for needle in (
        "firmware/platform/**",
        "apply_workshop_os12_platform_bridge.py",
        "apply_workshop_os12_inventory_service.py",
        "scripts/run_os12_platform_local.sh",
    ):
        require(platform_trigger, needle, "Platform Bridge PR trigger coverage")
    for needle in (
        "apply_workshop_os12_*.py",
        "scripts/*os12*",
        ".github/workflows/validate.yml",
    ):
        forbid(platform_trigger, needle, "Platform Bridge PR trigger")

    # UX Architecture owns final reconstruction/build inputs and validators,
    # not physical-acceptance/capture/recovery helpers.
    for needle in (
        "apply_workshop_os12_*.py",
        "scripts/run_os12_ux_local.sh",
        "scripts/validate_os12_ux_architecture.py",
        "firmware/platform/**",
    ):
        require(ux_trigger, needle, "UX Architecture PR trigger coverage")
    for needle in (
        "scripts/*os12*",
        "scripts/accept_os12_*.py",
        "scripts/accept_os12_*.sh",
        "scripts/capture-ws350-views.zsh",
        "scripts/bootstrap_ws350_os12_usb_macos.sh",
        "docs/WORKSHOP_OS12_DEVICE_PLATFORM.md",
        "docs/DEVICE_NATIVE_UPDATES.md",
        "docs/MEDIA_PHYSICAL_ACCEPTANCE.md",
    ):
        forbid(ux_trigger, needle, "UX Architecture PR trigger")

    # Acceptance/recovery tooling has its own cheap, non-firmware workflow.
    for needle in (
        "name: Workshop OS 12 Tooling Checks",
        "scripts/accept_os12_*.py",
        "scripts/accept_os12_*.sh",
        "scripts/validate_os12_physical_acceptance.py",
        "scripts/validate_os12_recovery_roundtrip.py",
        "Validate recovery round-trip contract",
    ):
        require(tooling, needle, "OS12 Tooling PR trigger coverage")
    for needle in ("run_os12_ux_local.sh --build", "pio run", "PlatformIO"):
        forbid(tooling, needle, "OS12 Tooling workflow")

    print(
        "PASS: OS12 merge gate is path-aware; platform, UX, and "
        "acceptance/recovery tooling retain separate ownership"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ValidationError as exc:
        print(f"FAIL: {exc}")
        raise SystemExit(1)
