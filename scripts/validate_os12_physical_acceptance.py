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
        raise ValidationError(f"{label}: forbidden marker present: {needle!r}")


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    media = (root / "scripts/accept_os12_media_physical.py").read_text(encoding="utf-8")
    ui = (root / "scripts/accept_os12_device_ui_physical.py").read_text(encoding="utf-8")
    bootstrap = (root / "scripts/bootstrap_ws350_os12_usb_macos.sh").read_text(encoding="utf-8")

    for label, text in (("media physical acceptance", media), ("whole-device UI physical acceptance", ui)):
        for needle in (
            "--expect-source-sha",
            "exactly 40 lowercase hex characters",
            "assert_code_free_portal",
            'portalMode"] = "local-code-free"',
            'identity["runningSourceCommit"]',
            "args.expect_source_sha",
        ):
            require(text, needle, label)
        for stale in (
            'portalMode"] = "temporary-open-lan"',
            'portalMode"]="temporary-open-lan"',
            "DEV OPEN",
        ):
            forbid(text, stale, label)

    require(
        bootstrap,
        'accept_os12_media_physical.py --base-url "$BASE_URL" --expect-source-sha "$HEAD_SHA"',
        "bootstrap media acceptance handoff",
    )
    require(
        bootstrap,
        'accept_os12_device_ui_physical.py --base-url "$BASE_URL" --expect-source-sha "$HEAD_SHA"',
        "bootstrap whole-device acceptance handoff",
    )

    print(
        "PASS: physical acceptance is fail-closed on the code-free same-origin portal contract and pinned to the exact running source SHA"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ValidationError as exc:
        raise SystemExit(f"FAIL: {exc}")
