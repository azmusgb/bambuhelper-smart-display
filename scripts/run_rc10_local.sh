#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="${ROOT:-$(git rev-parse --show-toplevel)}"
BUILD="${BUILD:-/tmp/ws350-rc10-build}"

cd "$ROOT"

echo "=== Workshop OS v11.25 RC10 local runner ==="
echo "ROOT=$ROOT"
echo "BUILD=$BUILD"

for f in \
  apply_workshop_os_physical_polish_v11_25_rc8.py \
  apply_workshop_os_premium_appliance_ui_v11_25_rc9.py \
  apply_workshop_os_cupertino_ui_v11_25_rc10.py; do
  test -f "$ROOT/$f" || { echo "FAIL: missing $f" >&2; exit 1; }
done

test -s "$BUILD/src/smart_hub.cpp" || { echo "FAIL: $BUILD is not a reconstructed RC7 tree" >&2; exit 1; }
test -s "$BUILD/include/smart_home_build.h" || { echo "FAIL: missing smart_home_build.h" >&2; exit 1; }

echo "=== RC8 ==="
python3 "$ROOT/apply_workshop_os_physical_polish_v11_25_rc8.py" --repo "$BUILD" --apply

echo "=== RC9 ==="
mkdir -p "$BUILD/firmware"
rm -rf "$BUILD/firmware/ui-v11.25-rc9"
cp -R "$ROOT/firmware/ui-v11.25-rc9" "$BUILD/firmware/"
python3 "$ROOT/apply_workshop_os_premium_appliance_ui_v11_25_rc9.py" --repo "$BUILD" --apply

echo "=== RC10 ==="
rm -rf "$BUILD/firmware/ui-v11.25-rc10"
cp -R "$ROOT/firmware/ui-v11.25-rc10" "$BUILD/firmware/"
python3 "$ROOT/apply_workshop_os_cupertino_ui_v11_25_rc10.py" --repo "$BUILD" --apply

HDR="$BUILD/include/smart_home_build.h"
HUB="$BUILD/src/smart_hub.cpp"
APP="$BUILD/web/app.js"
WEB="$BUILD/src/web_server.cpp"
SEC="$BUILD/src/security_manager.cpp"

for f in "$HDR" "$HUB" "$APP" "$WEB" "$SEC"; do
  test -s "$f" || { echo "FAIL: missing generated file $f" >&2; exit 1; }
done

grep -Fq 'Workshop OS v11.25 RC10 Cupertino UI' "$HDR"
grep -Fq 'SMART_HOME_PROFILE "cupertino-ui"' "$HDR"
grep -Fq 'WORKSHOP_OS_UI_SCHEMA "UI10"' "$HDR"
grep -Fq 'WORKSHOP_OS_V11_25_UI_RC10 1' "$HDR"

for fp in UI10-H UI10-P UI10-W UI10-M UI10-S; do
  grep -Fq "$fp" "$HUB" || { echo "FAIL: missing $fp" >&2; exit 1; }
done

grep -Fq 'static int16_t hubHeaderH() { return 36; }' "$HUB"
grep -Fq 'static int16_t hubNavH() { return 54; }' "$HUB"
grep -Fq 'static const uint8_t HUB_NETWORK_PAGE_COUNT = 7;' "$HUB"
grep -Fq 'Keep Holding' "$HUB"
grep -Fq 'Hold to Apply' "$HUB"
grep -Fq 'securityPortalCode()' "$HUB"
grep -Fq 'return cookieMatches(server);' "$SEC"
grep -Fq 'if (mutating && !sameOrigin(server))' "$SEC"

if grep -Fq 'TEST / NO CODE' "$HUB"; then echo 'FAIL: TEST / NO CODE found' >&2; exit 1; fi
for bad in matchSpoolByColor matchSpoolByMaterial resolveSpool; do
  if grep -Fq "$bad" "$HUB"; then echo "FAIL: forbidden inventory inference: $bad" >&2; exit 1; fi
done

if command -v node >/dev/null 2>&1; then node --check "$APP"; fi

echo "=== RC10 source validation PASS ==="
grep -E 'SMART_HOME_BUILD_LABEL|SMART_HOME_PROFILE|WORKSHOP_OS_UI_SCHEMA|WORKSHOP_OS_V11_25_UI_RC10' "$HDR"

if [[ "${1:-}" == "--build" ]]; then
  command -v pio >/dev/null 2>&1 || { echo 'FAIL: PlatformIO (pio) is not installed' >&2; exit 1; }
  echo "=== Build WS350 ==="
  (cd "$BUILD" && pio run -e ws_lcd_350)
  echo "=== Regression build jc3248w535 ==="
  (cd "$BUILD" && pio run -e jc3248w535)
  echo "=== Merge Full image ==="
  (cd "$BUILD" && python3 merge_bins.py --board ws_lcd_350 --full)
  FULL=$(find "$BUILD/firmware" -type f -name 'BambuHelper-ws_lcd_350-*-Full.bin' | sort | tail -1)
  test -n "$FULL" || { echo 'FAIL: Full WS350 image not found' >&2; exit 1; }
  echo "PASS: Full image: $FULL"
fi

echo "=== DONE ==="
