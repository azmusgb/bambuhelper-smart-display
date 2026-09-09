#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="${ROOT:-$(git rev-parse --show-toplevel)}"
PY313="${PY313:-/opt/homebrew/bin/python3.13}"
VENV="${VENV:-$HOME/.venvs/platformio313}"
BUILD="${BUILD:-/tmp/ws350-rc10-build}"

cd "$ROOT"

echo "=== Workshop OS RC10 macOS build ==="
echo "ROOT=$ROOT"
echo "BUILD=$BUILD"

# PlatformIO/esptool currently crashes in this environment when Homebrew's
# PlatformIO runs under Python 3.14. Keep PlatformIO isolated on Python 3.13.
if [[ ! -x "$PY313" ]]; then
  if command -v brew >/dev/null 2>&1; then
    echo "Python 3.13 not found; installing with Homebrew..."
    brew install python@3.13
  else
    echo "FAIL: Homebrew is required to install Python 3.13." >&2
    exit 1
  fi
fi

[[ -x "$PY313" ]] || { echo "FAIL: Python 3.13 not found at $PY313" >&2; exit 1; }

if [[ ! -x "$VENV/bin/python" ]]; then
  echo "=== Create isolated PlatformIO Python 3.13 environment ==="
  "$PY313" -m venv "$VENV"
fi

"$VENV/bin/python" -m pip install --disable-pip-version-check --upgrade pip
"$VENV/bin/python" -m pip install --disable-pip-version-check "platformio==6.2.0"

PIO="$VENV/bin/pio"
[[ -x "$PIO" ]] || { echo "FAIL: PlatformIO executable missing: $PIO" >&2; exit 1; }

echo "=== Toolchain ==="
"$VENV/bin/python" --version
"$PIO" --version

# If a validated RC10 tree already exists, preserve it. Otherwise reconstruct
# it with the repository's canonical clean runner, but do not let that runner
# invoke its Homebrew/Python-3.14 PlatformIO path.
if [[ ! -s "$BUILD/include/smart_home_build.h" ]] || ! grep -Fq 'Workshop OS v11.25 RC10 Cupertino UI' "$BUILD/include/smart_home_build.h"; then
  echo "=== RC10 build tree missing/stale; reconstruct source candidate ==="
  bash "$ROOT/scripts/run_rc10_local.sh"
fi

HDR="$BUILD/include/smart_home_build.h"
HUB="$BUILD/src/smart_hub.cpp"
APP="$BUILD/web/app.js"
SEC="$BUILD/src/security_manager.cpp"
for f in "$HDR" "$HUB" "$APP" "$SEC"; do
  [[ -s "$f" ]] || { echo "FAIL: missing generated file $f" >&2; exit 1; }
done

grep -Fq 'Workshop OS v11.25 RC10 Cupertino UI' "$HDR"
grep -Fq 'SMART_HOME_PROFILE "cupertino-ui"' "$HDR"
grep -Fq 'WORKSHOP_OS_UI_SCHEMA "UI10"' "$HDR"
for fp in UI10-H UI10-P UI10-W UI10-M UI10-S; do grep -Fq "$fp" "$HUB"; done
grep -Fq 'static int16_t hubHeaderH() { return 36; }' "$HUB"
grep -Fq 'static int16_t hubNavH() { return 54; }' "$HUB"
grep -Fq 'static const uint8_t HUB_NETWORK_PAGE_COUNT = 7;' "$HUB"
grep -Fq 'Keep Holding' "$HUB"
grep -Fq 'Hold to Apply' "$HUB"
grep -Fq 'securityPortalCode()' "$HUB"
grep -Fq 'return cookieMatches(server);' "$SEC"
grep -Fq 'if (mutating && !sameOrigin(server))' "$SEC"
! grep -Fq 'TEST / NO CODE' "$HUB"
for bad in matchSpoolByColor matchSpoolByMaterial resolveSpool; do ! grep -Fq "$bad" "$HUB"; done
if command -v node >/dev/null 2>&1; then node --check "$APP"; fi

echo "=== RC10 source validation PASS ==="
grep -E 'SMART_HOME_BUILD_LABEL|SMART_HOME_PROFILE|WORKSHOP_OS_UI_SCHEMA|WORKSHOP_OS_V11_25_UI_RC10' "$HDR"

echo "=== Clean WS350 build ==="
(cd "$BUILD" && "$PIO" run -e ws_lcd_350 -t clean)
(cd "$BUILD" && "$PIO" run -e ws_lcd_350)

echo "=== Regression build jc3248w535 ==="
(cd "$BUILD" && "$PIO" run -e jc3248w535)

echo "=== Merge Full WS350 image ==="
(cd "$BUILD" && "$VENV/bin/python" merge_bins.py --board ws_lcd_350 --full)

FULL=$(find "$BUILD/firmware" -type f -name 'BambuHelper-ws_lcd_350-*-Full.bin' | sort | tail -1)
OTA="$BUILD/.pio/build/ws_lcd_350/firmware.bin"
[[ -n "$FULL" && -f "$FULL" ]] || { echo "FAIL: Full WS350 image not found" >&2; exit 1; }
[[ -f "$OTA" ]] || { echo "FAIL: OTA WS350 image not found" >&2; exit 1; }

echo "=== SHA256 ==="
shasum -a 256 "$FULL" "$OTA"
echo
echo "PASS: Full image: $FULL"
echo "PASS: OTA image:  $OTA"
echo "=== RC10 MACOS BUILD PASS ==="
