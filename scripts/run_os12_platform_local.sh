#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="${ROOT:-$(git rev-parse --show-toplevel)}"
BUILD="${BUILD:-/tmp/ws350-os12-platform-build}"

cd "$ROOT"
echo "=== Workshop OS 12 device-platform reconstruction ==="
echo "ROOT=$ROOT"
echo "BUILD=$BUILD"

BUILD="$BUILD" bash "$ROOT/scripts/run_ui13_local.sh"
python3 "$ROOT/apply_workshop_os12_platform_bridge.py" \
  --repo "$BUILD" \
  --source-root "$ROOT" \
  --apply
python3 "$ROOT/scripts/validate_os12_platform_bridge.py"

python3 "$ROOT/apply_workshop_os12_ui_state_reads.py" \
  --repo "$BUILD" \
  --apply
python3 "$ROOT/scripts/validate_os12_ui_state_reads.py"

python3 "$ROOT/apply_workshop_os12_system_state_reads.py" \
  --repo "$BUILD" \
  --apply
python3 "$ROOT/scripts/validate_os12_system_state_reads.py"

python3 "$ROOT/apply_workshop_os12_non_destructive_controls.py" \
  --repo "$BUILD" \
  --apply
python3 "$ROOT/scripts/validate_os12_non_destructive_controls.py"

python3 "$ROOT/apply_workshop_os12_guarded_stop.py" \
  --repo "$BUILD" \
  --apply
python3 "$ROOT/scripts/validate_os12_guarded_stop.py"

# UI status surfaces consume normalized read-only facts. Physical Light,
# Pause/Resume, and guarded Stop now dispatch through the OS12 command facade,
# which still uses the existing deferred Bambu MQTT transport underneath.
grep -q '#include "workshop_platform_bridge.h"' "$BUILD/src/main.cpp"
test "$(grep -c 'workshopPlatformBegin();' "$BUILD/src/main.cpp")" -eq 1
test "$(grep -c 'workshopPlatformPoll();' "$BUILD/src/main.cpp")" -eq 1
test -s "$BUILD/src/workshop_platform_bridge.cpp"
test -s "$BUILD/include/workshop_platform/workshop_state.hpp"
grep -q 'workshopPlatformState().configuredPrinterCount>0' "$BUILD/src/smart_hub.cpp"
grep -q 'workshopPlatformPrinterOnline(os12Slot)' "$BUILD/src/smart_hub.cpp"
grep -q 'workshopPlatformWifiOnline()' "$BUILD/src/smart_hub.cpp"
grep -q 'os12Network=workshopPlatformState().network' "$BUILD/src/smart_hub.cpp"
grep -q 'workshopPlatformDispatchPrinterCommand' "$BUILD/src/smart_hub.cpp"
grep -q 'workshop::platform::PrinterCommand::Stop,true' "$BUILD/src/smart_hub.cpp"
if grep -q 'requestPrinterControlCommand(slot,PRINTER_CTRL_STOP)' "$BUILD/src/smart_hub.cpp"; then
  echo 'FAIL: direct physical STOP transport call survived OS12 migration' >&2
  exit 1
fi
grep -q 'longPress' "$BUILD/src/smart_hub.cpp"

if [[ "${1:-}" == "--build" ]]; then
  if ! command -v pio >/dev/null 2>&1; then
    echo "PlatformIO not found; installing for current user..."
    python3 -m pip install --user --upgrade platformio
    export PATH="$HOME/.local/bin:$PATH"
  fi
  command -v pio >/dev/null 2>&1 || { echo 'FAIL: pio unavailable after install' >&2; exit 1; }

  echo "=== Build WS350 OS12 normalized state/control bridge ==="
  (cd "$BUILD" && pio run -e ws_lcd_350)
  test -s "$BUILD/.pio/build/ws_lcd_350/firmware.bin" || { echo 'FAIL: WS350 OS12 image missing' >&2; exit 1; }

  echo "=== Cross-board compile regression ==="
  (cd "$BUILD" && pio run -e jc3248w535)
  test -s "$BUILD/.pio/build/jc3248w535/firmware.bin" || { echo 'FAIL: jc3248w535 OS12 image missing' >&2; exit 1; }
fi

echo "=== OS12 platform reconstruction complete ==="
echo "State: normalized observation bridge + informational read migration implemented."
echo "Physical Light/Pause/Resume/Stop: OS12 facade -> existing deferred Bambu transport."
echo "Stop UX guard: existing long-press preserved; facade enforces destructive guard contract."
echo "Power authority: unchanged Tasmota path."
echo "Inventory authority: unchanged Filament Inventory path."
echo "UI13 physical acceptance candidate: untouched."
echo "Stable promotion: forbidden by this script."
