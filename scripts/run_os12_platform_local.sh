#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="${ROOT:-$(git rev-parse --show-toplevel)}"
BUILD="${BUILD:-/tmp/ws350-os12-platform-build}"
OS12_RELEASE_VERSION="${OS12_RELEASE_VERSION:-12.0.0}"
OS12_SOURCE_SHA="${OS12_SOURCE_SHA:-$(git -C "$ROOT" rev-parse HEAD)}"

cd "$ROOT"
echo "=== Workshop OS 12 device-platform reconstruction ==="
echo "ROOT=$ROOT"
echo "BUILD=$BUILD"
echo "OS12_RELEASE_VERSION=$OS12_RELEASE_VERSION"
echo "OS12_SOURCE_SHA=$OS12_SOURCE_SHA"

BUILD="$BUILD" bash "$ROOT/scripts/run_ui13_local.sh"
python3 "$ROOT/apply_workshop_os12_platform_bridge.py" --repo "$BUILD" --source-root "$ROOT" --apply
python3 "$ROOT/scripts/validate_os12_platform_bridge.py"

python3 "$ROOT/apply_workshop_os12_ui_state_reads.py" --repo "$BUILD" --apply
python3 "$ROOT/scripts/validate_os12_ui_state_reads.py"

python3 "$ROOT/apply_workshop_os12_system_state_reads.py" --repo "$BUILD" --apply
python3 "$ROOT/scripts/validate_os12_system_state_reads.py"

python3 "$ROOT/apply_workshop_os12_non_destructive_controls.py" --repo "$BUILD" --apply
python3 "$ROOT/scripts/validate_os12_non_destructive_controls.py"

python3 "$ROOT/apply_workshop_os12_guarded_stop.py" --repo "$BUILD" --apply
python3 "$ROOT/scripts/validate_os12_guarded_stop.py"
python3 "$ROOT/scripts/validate_os12_control_boundary.py" --repo "$BUILD"

python3 "$ROOT/apply_workshop_os12_portal_login_hardening.py" --repo "$BUILD" --apply
python3 "$ROOT/scripts/validate_os12_portal_login.py" --repo "$BUILD"

python3 "$ROOT/apply_workshop_os12_device_update.py" --repo "$BUILD" --source-root "$ROOT" --apply
python3 "$ROOT/apply_workshop_os12_release_identity.py" --repo "$BUILD" --version "$OS12_RELEASE_VERSION" --source-sha "$OS12_SOURCE_SHA" --apply

python3 "$ROOT/apply_workshop_os12_media_hardware.py" --repo "$BUILD" --apply
python3 "$ROOT/scripts/validate_os12_media_hardware.py" --repo "$BUILD"

python3 "$ROOT/apply_workshop_os12_media_capture.py" --repo "$BUILD" --apply
python3 "$ROOT/scripts/validate_os12_media_capture.py" --repo "$BUILD"

python3 "$ROOT/apply_workshop_os12_media_runtime.py" --repo "$BUILD" --source-root "$ROOT" --apply
python3 "$ROOT/apply_workshop_os12_media_signal_hardening.py" --repo "$BUILD" --apply
python3 "$ROOT/apply_workshop_os12_x2d_camera_test_support.py" --repo "$BUILD" --apply
python3 "$ROOT/apply_workshop_os12_camera_ownership.py" --repo "$BUILD" --apply
python3 "$ROOT/scripts/validate_os12_media_signal.py" --repo "$BUILD"
python3 "$ROOT/scripts/validate_os12_media_service.py"
python3 "$ROOT/scripts/validate_os12_media_runtime.py" --repo "$BUILD"

python3 "$ROOT/apply_workshop_os12_media_ui.py" --repo "$BUILD" --apply
python3 "$ROOT/scripts/validate_os12_media_ui.py" --repo "$BUILD"

python3 "$ROOT/apply_workshop_os12_media_api.py" --repo "$BUILD" --apply
python3 "$ROOT/scripts/validate_os12_media_api.py" --repo "$BUILD"

python3 "$ROOT/scripts/validate_os12_device_update.py" --source-root "$ROOT" --repo "$BUILD"

grep -q '#include "workshop_platform_bridge.h"' "$BUILD/src/main.cpp"
test "$(grep -c 'workshopPlatformBegin();' "$BUILD/src/main.cpp")" -eq 1
test "$(grep -c 'workshopPlatformPoll();' "$BUILD/src/main.cpp")" -eq 1
grep -q '#include "workshop_media_runtime.h"' "$BUILD/src/main.cpp"
test "$(grep -c 'workshopMediaBegin();' "$BUILD/src/main.cpp")" -eq 1
test "$(grep -c 'workshopMediaPoll();' "$BUILD/src/main.cpp")" -eq 1
test "$(grep -c 'workshopUpdateServiceBegin();' "$BUILD/src/main.cpp")" -eq 1
test "$(grep -c 'workshopUpdateServiceLoop();' "$BUILD/src/main.cpp")" -eq 1
test -s "$BUILD/src/workshop_platform_bridge.cpp"
test -s "$BUILD/src/workshop_update_service.cpp"
test -s "$BUILD/src/media_service.cpp"
test -s "$BUILD/src/ws350_media_backend.cpp"
test -s "$BUILD/src/workshop_media_runtime.cpp"
test -s "$BUILD/include/workshop_platform/workshop_state.hpp"
test -s "$BUILD/include/media_service.h"
grep -q 'buzzerBackendSetVolume' "$BUILD/src/buzzer_backend.h"
grep -q 'buzzerBackendMicRecordBegin' "$BUILD/src/buzzer_backend.h"
grep -q 'MALLOC_CAP_SPIRAM' "$BUILD/src/buzzer_backend_es8311.cpp"
grep -q 'esWrite(ES_REG_SYS_14, 0x1A)' "$BUILD/src/buzzer_backend_es8311.cpp"
grep -q 'esWrite(ES_REG_ADC_17, 0xC8)' "$BUILD/src/buzzer_backend_es8311.cpp"
grep -q 'speakerTestEndsAtMs_ = nowMs + 750U' "$BUILD/src/media_service.cpp"
grep -q 'OS12 media video: rejected displayed-printer camera unavailable' "$BUILD/src/ws350_media_backend.cpp"
grep -q 'buz_vol' "$BUILD/src/settings.cpp"
grep -q 'drawOs12Media' "$BUILD/src/smart_hub.cpp"
grep -q 'drawOs12MediaLab' "$BUILD/src/smart_hub.cpp"
grep -q 'workshopMediaSnapshot()' "$BUILD/src/smart_hub.cpp"
grep -q 'playMjpeg("printer-camera"' "$BUILD/src/smart_hub.cpp"
grep -q 'cameraGetLatestFrame' "$BUILD/src/ws350_media_backend.cpp"
grep -q 'tft.drawJpg' "$BUILD/src/ws350_media_backend.cpp"
grep -q 'SECURE_GET("/os12/media/status"' "$BUILD/src/web_server.cpp"
grep -q 'SECURE_POST("/os12/media/speaker-test"' "$BUILD/src/web_server.cpp"
grep -q 'SECURE_POST("/os12/media/microphone-sample"' "$BUILD/src/web_server.cpp"
grep -q 'SECURE_POST("/os12/media/video/start"' "$BUILD/src/web_server.cpp"
grep -q 'SECURE_POST("/os12/media/video/pause"' "$BUILD/src/web_server.cpp"
grep -q 'SECURE_POST("/os12/media/video/resume"' "$BUILD/src/web_server.cpp"
! grep -q '/os12/media/acceptance/show-' "$BUILD/src/web_server.cpp"
grep -q 'workshopPlatformState().configuredPrinterCount>0' "$BUILD/src/smart_hub.cpp"
grep -q 'workshopPlatformPrinterOnline(os12Slot)' "$BUILD/src/smart_hub.cpp"
grep -q 'workshopPlatformWifiOnline()' "$BUILD/src/smart_hub.cpp"
grep -q 'os12Network=workshopPlatformState().network' "$BUILD/src/smart_hub.cpp"
grep -q 'workshopPlatformDispatchPrinterCommand' "$BUILD/src/smart_hub.cpp"
grep -q 'workshop::platform::PrinterCommand::Stop,true' "$BUILD/src/smart_hub.cpp"
grep -q 'longPress' "$BUILD/src/smart_hub.cpp"
grep -q 'SecurityLoginResult::RateLimited' "$BUILD/src/security_manager.cpp"
grep -q "<html lang='en'>" "$BUILD/src/web_server.cpp"
grep -q "autocomplete='off'" "$BUILD/src/web_server.cpp"
grep -q 'raw.githubusercontent.com/azmusgb/bambuhelper-smart-display/main/releases/device-update.json' "$BUILD/src/workshop_update_service.cpp"
grep -q 'esp_ota_set_boot_partition' "$BUILD/src/workshop_update_service.cpp"
grep -q 'workshopUpdateRequestInstall' "$BUILD/src/smart_hub.cpp"
grep -q "#define WORKSHOP_OS_RELEASE_VERSION \"$OS12_RELEASE_VERSION\"" "$BUILD/include/smart_home_build.h"
grep -q "#define WORKSHOP_OS_SOURCE_SHA \"$OS12_SOURCE_SHA\"" "$BUILD/include/smart_home_build.h"
test "$(grep -c 'WORKSHOP_OS_RELEASE_VERSION' "$BUILD/src/workshop_update_service.cpp")" -eq 2
grep -q 'WORKSHOP_OS_SOURCE_SHA' "$BUILD/src/workshop_update_service.cpp"
grep -q 'g_runtime.runningSourceCommit' "$BUILD/src/workshop_update_service.cpp"
grep -q 'char runningSourceCommit\[41\]' "$BUILD/include/workshop_update_service.h"
grep -q 'doc\["runningSourceCommit"\] = snap.runningSourceCommit;' "$BUILD/src/web_server.cpp"
! grep -q 'WORKSHOP_OS12_SOURCE_SHA' "$BUILD/src/workshop_update_service.cpp"
! grep -q 'SMART_HOME_VERSION' "$BUILD/src/workshop_update_service.cpp"
! sed -n '/void initWebServer()/,/void handleWebServer()/p' "$BUILD/src/web_server.cpp" | grep -q '"/ota/auto"'
! sed -n '/void initWebServer()/,/void handleWebServer()/p' "$BUILD/src/web_server.cpp" | grep -q 'server.on("/os12/media/'

if [[ "${1:-}" == "--build" ]]; then
  PIO_BIN="$(ROOT="$ROOT" bash "$ROOT/scripts/ensure-platformio.sh")"
  [[ -x "$PIO_BIN" ]] || { echo 'FAIL: pio unavailable after isolated setup' >&2; exit 1; }
  echo "PlatformIO: $PIO_BIN"
  "$PIO_BIN" --version

  echo "=== Build WS350 OS12 device platform + media runtime/UI/API ==="
  (cd "$BUILD" && "$PIO_BIN" run -e ws_lcd_350)
  test -s "$BUILD/.pio/build/ws_lcd_350/firmware.bin" || { echo 'FAIL: WS350 OS12 image missing' >&2; exit 1; }

  echo "=== Cross-board compile regression ==="
  (cd "$BUILD" && "$PIO_BIN" run -e jc3248w535)
  test -s "$BUILD/.pio/build/jc3248w535/firmware.bin" || { echo 'FAIL: jc3248w535 OS12 image missing' >&2; exit 1; }
fi

echo "=== OS12 platform reconstruction complete ==="
echo "Release identity: Workshop OS $OS12_RELEASE_VERSION @ $OS12_SOURCE_SHA"
echo "Source provenance: compiled into runtime status and required by post-reboot acceptance."
echo "State: normalized observation bridge + informational read migration implemented."
echo "Physical Light/Pause/Resume/Stop: OS12 facade -> existing deferred Bambu transport."
echo "Stop UX guard: existing long-press preserved; facade enforces destructive guard contract."
echo "Control boundary: direct physical Light/Pause/Resume/Stop transport bypasses rejected."
echo "Portal access: exact code alphabet/normalization, bounded login backoff, per-session RAM cookies, and accessible login states implemented."
echo "Media hardware: ES8311/I2S authority reused; WS350 analog mic route/gain explicitly configured and physically pending."
echo "Media recording: PSRAM-bounded five-second maximum, poll-driven capture and existing-task playback implemented."
echo "Media runtime: centralized MediaService + capability-safe hardware adapter wired into lifecycle."
echo "Media UI: capability-scoped Speaker/Microphone/Media Lab surfaces integrated into UI13 settings flow."
echo "Media diagnostics API: authenticated bounded audio/recording/video lifecycle routes; no arbitrary media URL."
echo "Media physical acceptance navigation: canonical /hub/views + /hub/show router only; no parallel acceptance UI route."
echo "Video: displayed-printer camera JPEG sequence via existing camera client + LovyanGFX drawJpg, paced to max 8 fps; startup diagnostics added; physical acceptance pending."
echo "Device updates: GitHub manifest -> exact WS350 OTA path -> size/SHA-256 verification -> inactive app partition -> reboot."
echo "Legacy online updater: /ota/auto route retired; manual local OTA remains a maintenance fallback."
echo "Full image / offset 0x0: recovery only, never device-native OTA."
echo "Power authority: unchanged Tasmota path."
echo "Inventory authority: unchanged Filament Inventory path."
echo "UI13 physical acceptance candidate: untouched."
echo "Stable promotion: forbidden by this script."
