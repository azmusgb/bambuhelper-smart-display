#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path


class ValidationError(RuntimeError):
    pass


def require(text: str, needle: str, label: str) -> None:
    if needle not in text:
        raise ValidationError(f"{label}: missing {needle!r}")


def forbid(text: str, needle: str, label: str) -> None:
    if needle in text:
        raise ValidationError(f"{label}: forbidden marker present: {needle!r}")


def read(path: Path) -> str:
    if not path.is_file():
        raise ValidationError(f"missing {path}")
    return path.read_text(encoding="utf-8")


def validate_source(source_root: Path) -> None:
    header = read(source_root / "firmware/platform/update/workshop_update_service.h")
    cpp = read(source_root / "firmware/platform/update/workshop_update_service.cpp")
    state = read(source_root / "firmware/platform/workshop_state.hpp")
    bridge = read(source_root / "firmware/platform/bridge/workshop_platform_bridge.h")
    patcher = read(source_root / "apply_workshop_os12_device_update.py")

    for needle in (
        "workshopUpdateRequestCheck",
        "workshopUpdateRequestInstall",
        "workshopUpdateSetChannel",
        "WorkshopUpdateRuntimeSnapshot",
    ):
        require(header, needle, "UpdateService API")

    for needle in (
        "raw.githubusercontent.com/azmusgb/bambuhelper-smart-display/main/releases/device-update.json",
        'constexpr char kAuthority[] = "azmusgb/bambuhelper-smart-display";',
        'constexpr char kBoard[] = "ws_lcd_350";',
        "setCACertBundle(rootca_crt_bundle_start)",
        "HTTPC_DISABLE_FOLLOW_REDIRECTS",
        "safeArtifactPath",
        "esp_ota_get_next_update_partition",
        "esp_ota_begin",
        "esp_ota_write",
        "mbedtls_sha256_update_ret",
        "std::memcmp(actualSha, expectedSha",
        "esp_ota_set_boot_partition",
        "UpdateChannel::Stable",
        "UpdateChannel::Candidate",
    ):
        require(cpp, needle, "UpdateService source")
    forbid(cpp, "setInsecure", "UpdateService TLS")

    for needle in (
        "kUpdateLabelLength",
        "kUpdateMessageLength",
        "artifactSha256",
        "artifactSize",
        "progressPercent",
        "updateAvailable",
        "artifactIdentityVerified",
    ):
        require(state, needle, "normalized UpdateState")
    require(bridge, "workshopPlatformUpdateState", "update state facade")

    for needle in (
        "legacy /ota/auto route remains registered",
        "workshopUpdateRequestCheck()",
        "workshopUpdateRequestInstall()",
        "workshopUpdateSetChannel(next)",
        "printer.telemetryFreshness != Freshness::Fresh",
        "state.progressPercent = snap.progressPercent",
        "SECURE_GET(\"/os12/update/status\"",
        "SECURE_POST(\"/os12/update/install\"",
        "Size + SHA-256 required",
        "Do not power off the WS350 during the update.",
    ):
        require(patcher, needle, "device update patcher")

    manifest_path = source_root / "releases/device-update.json"
    if manifest_path.is_file():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("schemaVersion") != 1:
            raise ValidationError("device-update manifest schema must be 1")
        if manifest.get("board") != "ws_lcd_350":
            raise ValidationError("device-update manifest board must be ws_lcd_350")
        if manifest.get("authority") != "azmusgb/bambuhelper-smart-display":
            raise ValidationError("device-update manifest authority mismatch")
        base = manifest.get("artifactBaseUrl", "")
        if base != "https://raw.githubusercontent.com/azmusgb/bambuhelper-smart-display/main/":
            raise ValidationError("device-update artifactBaseUrl must stay pinned to raw main")
        rules = manifest.get("rules", {})
        if rules.get("normalDeviceUpdateUsesOtaOnly") is not True:
            raise ValidationError("normal OTA-only rule missing")
        if rules.get("verifySizeBeforeInstall") is not True or rules.get("verifySha256BeforeInstall") is not True:
            raise ValidationError("size/SHA-256 verification rules missing")
        if rules.get("fullFlashRequiresRecoveryFlow") is not True:
            raise ValidationError("Full image recovery boundary missing")


def validate_reconstructed(repo: Path) -> None:
    service = read(repo / "src/workshop_update_service.cpp")
    service_h = read(repo / "include/workshop_update_service.h")
    main = read(repo / "src/main.cpp")
    web = read(repo / "src/web_server.cpp")
    hub = read(repo / "src/smart_hub.cpp")
    board = read(repo / "boards/ws_lcd_350.ini")
    build = read(repo / "include/smart_home_build.h")

    require(service_h, "workshopUpdateRequestInstall", "reconstructed update API")
    for needle in (
        "printer.telemetryFreshness != Freshness::Fresh",
        "state.progressPercent = snap.progressPercent",
        "state.updateAvailable = snap.updateAvailable",
        "esp_ota_set_boot_partition",
        "setCACertBundle(rootca_crt_bundle_start)",
    ):
        require(service, needle, "reconstructed UpdateService")
    forbid(service, "setInsecure", "reconstructed UpdateService TLS")
    forbid(service.lower(), "signed manifest", "manifest authenticity wording")

    if main.count("workshopUpdateServiceBegin();") != 1:
        raise ValidationError("workshopUpdateServiceBegin must be wired exactly once")
    if main.count("workshopUpdateServiceLoop();") != 1:
        raise ValidationError("workshopUpdateServiceLoop must be wired exactly once")

    require(board, "-D ENABLE_OTA_AUTO=1", "WS350 TLS update plumbing")

    init_start = web.find("void initWebServer() {")
    init_end = web.find("\nvoid handleWebServer()", init_start)
    if init_start < 0 or init_end < 0:
        raise ValidationError("web server init block missing")
    init = web[init_start:init_end]
    forbid(init, '"/ota/auto"', "legacy online-update authority")
    forbid(init, '"/ota/status"', "legacy online-update status authority")
    for route in (
        'SECURE_GET("/os12/update/status"',
        'SECURE_POST("/os12/update/check"',
        'SECURE_POST("/os12/update/channel"',
        'SECURE_POST("/os12/update/install"',
    ):
        require(init, route, "OS12 update API")

    for needle in (
        "workshopPlatformUpdateState()",
        "workshopUpdateRequestCheck()",
        "workshopUpdateRequestInstall()",
        "drawUi13UpdateConfirm",
        "Review & Install",
        "SHA-256 verified",
    ):
        require(hub, needle, "Software Update touch UI")

    require(build, "WORKSHOP_OS12_DEVICE_UPDATE", "OS12 build identity")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--repo", help="optional reconstructed source root")
    args = parser.parse_args()
    try:
        source_root = Path(args.source_root).resolve()
        validate_source(source_root)
        if args.repo:
            validate_reconstructed(Path(args.repo).resolve())
    except (ValidationError, json.JSONDecodeError) as exc:
        raise SystemExit(f"FAIL: {exc}") from exc
    print("OS12 device-native GitHub update validation: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
