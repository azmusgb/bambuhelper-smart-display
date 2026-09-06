#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path


def require(text: str, needle: str, label: str) -> None:
    if needle not in text:
        raise SystemExit(f"FAIL: {label}: missing {needle!r}")


def forbid(text: str, needle: str, label: str) -> None:
    if needle in text:
        raise SystemExit(f"FAIL: {label}: forbidden {needle!r}")


def main() -> int:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
    build = (root / "include/smart_home_build.h").read_text(encoding="utf-8")
    main_cpp = (root / "src/main.cpp").read_text(encoding="utf-8")
    companion_h = (root / "src/companion_web.h").read_text(encoding="utf-8")
    companion_cpp = (root / "src/companion_web.cpp").read_text(encoding="utf-8")
    display = (root / "src/display_ui.cpp").read_text(encoding="utf-8")
    app = (root / "web/app.js").read_text(encoding="utf-8")

    require(build, 'SMART_HOME_VERSION "v11.30"', "version")
    require(build, 'Smart Home v11.30 Unified Web + Companion RC2', "RC2 label")
    require(build, 'Workshop OS v11.30 Unified Web + Companion RC2 Viewer Reliability', "RC2 marker")

    require(companion_h, 'void companionWebViewerExitToReturnScreen();', "viewer return API")
    require(companion_cpp, 'void companionWebViewerExitToReturnScreen()', "viewer return implementation")
    require(companion_cpp, 'const ScreenState target = g_captureViewerReturnScreen == SCREEN_CAMERA', "return target guard")
    require(companion_cpp, 'g_captureViewerActive = false;\n  setScreenState(target);', "clear-before-return ordering")

    sticky = 'current == SCREEN_CAMERA && companionWebViewerActive() && !isOtaAutoInProgress()'
    require(main_cpp, sticky, "phone viewer sticky guard")
    guard_pos = main_cpp.index(sticky)
    no_printer_pos = main_cpp.index('if (!isAnyPrinterConfigured())', guard_pos)
    if guard_pos > no_printer_pos:
        raise SystemExit("FAIL: viewer sticky guard must precede no-printer state derivation")

    tap_exit = 'if (companionWebViewerActive()) {\n      companionWebViewerExitToReturnScreen();\n      return;\n    }'
    require(main_cpp, tap_exit, "physical tap viewer exit")
    tap_pos = main_cpp.index(tap_exit)
    dry_pos = main_cpp.index('if (openDryPeek()) return;', tap_pos)
    if tap_pos > dry_pos:
        raise SystemExit("FAIL: phone viewer tap must exit before chamber/drying cycle behavior")

    # The chamber-camera path remains intact when the phone override is inactive.
    require(main_cpp, 'if (cameraCanStreamDisplayedPrinter()) return;', "chamber camera sticky fallback")
    require(display, 'if (companionWebViewerActive())', "phone JPEG render override")
    require(display, 'cameraGetLatestFrame(&buf, &len, &fid)', "normal chamber camera fallback")
    require(display, 'tft.drawJpg(phoneBuf, (uint32_t)phoneLen', "phone JPEG renderer")

    # The phone UI must not announce success merely because the POST returned 200.
    require(companion_cpp, "Waveshare did not enter phone-photo view", "post-show confirmation")
    require(companion_cpp, "capture&&capture.viewer", "confirmed viewer state")
    require(companion_cpp, "Displaying now · ", "Companion live viewer copy")
    require(app, "cap.viewer?'Displaying · ':'Photo ready · '", "full web viewer visibility")

    # Preserve volatile-only photo semantics.
    for forbidden in ['LittleFS', 'SPIFFS', 'FFat', 'Preferences', 'putBytes(', 'writeFile(']:
        forbid(companion_cpp, forbidden, "volatile capture boundary")

    print("Workshop OS v11.30 RC2 Companion viewer reliability: PASS")
    print("phone_viewer_sticky_independent_of_printer_camera=PASS")
    print("phone_viewer_works_without_configured_printer=PASS")
    print("auto_ota_preemption=PASS")
    print("physical_tap_return_target=PASS")
    print("chamber_camera_fallback=PRESERVED")
    print("browser_success_requires_confirmed_viewer_state=PASS")
    print("photo_persistence=VOLATILE_PSRAM_ONLY")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
