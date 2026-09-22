#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path


class ValidationError(RuntimeError):
    pass


def require(text: str, needle: str, label: str) -> None:
    if needle not in text:
        raise ValidationError(f"{label}: missing {needle!r}")


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    workflow = (root / ".github/workflows/release-gate.yml").read_text(encoding="utf-8")

    for needle in (
        "os12_required=0",
        ".github/workflows/os12-platform-bridge.yml",
        ".github/workflows/os12-ux-architecture.yml",
        "apply_workshop_os12_*.py",
        "firmware/platform/*",
        "scripts/*os12*",
        "scripts/ensure-platformio.sh",
        "docs/DEVICE_NATIVE_UPDATES.md",
        'required+=("Workshop OS 12 Platform Bridge")',
        'required+=("Workshop OS 12 UX Architecture")',
    ):
        require(workflow, needle, "OS12 merge-gate coverage")

    platform_i = workflow.index('required+=("Workshop OS 12 Platform Bridge")')
    ux_i = workflow.index('required+=("Workshop OS 12 UX Architecture")')
    poll_i = workflow.index("Wait for required conditional workflow gates")
    if platform_i > poll_i or ux_i > poll_i:
        raise ValidationError("OS12 workflows are not added before merge-gate polling")

    platform_workflow = (root / ".github/workflows/os12-platform-bridge.yml").read_text(encoding="utf-8")
    ux_workflow = (root / ".github/workflows/os12-ux-architecture.yml").read_text(encoding="utf-8")
    shared_trigger_needles = (
        "apply_workshop_os12_*.py",
        "contracts/**",
        "firmware/platform/**",
        "firmware/ui-v11.25-rc10/**",
        "firmware/ui-v11.26-ui11/**",
        "firmware/ui-v11.27-ui12/**",
        "firmware/ui-v11.28-ui13/**",
        "scripts/*os12*",
        "scripts/ensure-platformio.sh",
        "scripts/waveshare-usb.sh",
        "scripts/capture-ws350-views.zsh",
        "docs/WORKSHOP_OS12_DEVICE_PLATFORM.md",
        "docs/DEVICE_NATIVE_UPDATES.md",
        "docs/MEDIA_PHYSICAL_ACCEPTANCE.md",
        "releases/device-update.json",
        ".github/workflows/os12-platform-bridge.yml",
        ".github/workflows/os12-ux-architecture.yml",
    )
    for needle in shared_trigger_needles:
        require(platform_workflow, needle, "Platform Bridge PR trigger coverage")
        require(ux_workflow, needle, "UX Architecture PR trigger coverage")

    print("PASS: OS12-sensitive PRs require exact-head Platform Bridge and UX Architecture workflows before merge")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ValidationError as exc:
        print(f"FAIL: {exc}")
        raise SystemExit(1)
