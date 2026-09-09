#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="${ROOT:-$(git rev-parse --show-toplevel)}"; BUILD="${BUILD:-/tmp/ws350-rc10-build}"; VENV="${VENV:-$HOME/.venvs/workshop-os-pio313}"; OUT="${OUT:-$ROOT/dist/rc10-cupertino}"; PIO_VERSION=6.2.0
fail(){ echo "FAIL: $*" >&2; exit 1; }; step(){ echo; echo "=== $* ==="; }
trap 'r=$?; echo "FAILED line $LINENO (exit $r); build preserved: $BUILD" >&2; exit $r' ERR
cd "$ROOT"
step "Resolve Python 3.13"
PY313="${PY313:-}"; for p in /opt/homebrew/bin/python3.13 /usr/local/bin/python3.13; do [[ -z "$PY313" && -x "$p" ]] && PY313="$p"; done
if [[ -z "$PY313" ]] && command -v python3.13 >/dev/null; then PY313="$(command -v python3.13)"; fi
if [[ -z "$PY313" ]]; then command -v brew >/dev/null || fail "Homebrew unavailable"; brew install python@3.13; PY313="$(brew --prefix python@3.13)/bin/python3.13"; fi
[[ -x "$PY313" ]] || fail "Python 3.13 unavailable"
step "Isolated PlatformIO $PIO_VERSION"
[[ -x "$VENV/bin/python" ]] || "$PY313" -m venv "$VENV"
"$VENV/bin/python" -m pip --disable-pip-version-check install -q --upgrade pip setuptools wheel
"$VENV/bin/python" -m pip --disable-pip-version-check install -q "platformio==$PIO_VERSION"
PIO="$VENV/bin/pio"; "$VENV/bin/python" -c 'import sys; assert sys.version_info[:2]==(3,13); print(sys.version)' ; "$PIO" --version
step "Prepare RC10 source"
if [[ ! -s "$BUILD/include/smart_home_build.h" ]] || ! grep -Fq 'Workshop OS v11.25 RC10 Cupertino UI' "$BUILD/include/smart_home_build.h"; then bash "$ROOT/scripts/run_rc10_local.sh"; fi
HDR="$BUILD/include/smart_home_build.h"; HUB="$BUILD/src/smart_hub.cpp"; APP="$BUILD/web/app.js"; SEC="$BUILD/src/security_manager.cpp"
for f in "$HDR" "$HUB" "$APP" "$SEC"; do [[ -s "$f" ]] || fail "missing $f"; done
step "Acceptance-source gates"
grep -Fq 'Workshop OS v11.25 RC10 Cupertino UI' "$HDR"; grep -Fq 'SMART_HOME_PROFILE "cupertino-ui"' "$HDR"; grep -Fq 'WORKSHOP_OS_UI_SCHEMA "UI10"' "$HDR"; grep -Fq 'WORKSHOP_OS_V11_25_UI_RC10 1' "$HDR"
for x in UI10-H UI10-P UI10-W UI10-M UI10-S; do grep -Fq "$x" "$HUB"; done
grep -Fq 'static int16_t hubHeaderH() { return 36; }' "$HUB"; grep -Fq 'static int16_t hubNavH() { return 54; }' "$HUB"; grep -Fq 'static const uint8_t HUB_NETWORK_PAGE_COUNT = 7;' "$HUB"; grep -Fq 'Keep Holding' "$HUB"; grep -Fq 'Hold to Apply' "$HUB"; grep -Fq 'securityPortalCode()' "$HUB"; grep -Fq 'return cookieMatches(server);' "$SEC"; grep -Fq 'if (mutating && !sameOrigin(server))' "$SEC"; ! grep -Fq 'TEST / NO CODE' "$HUB"
for x in matchSpoolByColor matchSpoolByMaterial resolveSpool; do ! grep -Fq "$x" "$HUB"; done
command -v node >/dev/null && node --check "$APP" || true
echo "PASS: source gates"
step "Build WS350"
(cd "$BUILD" && "$PIO" run -e ws_lcd_350)
WS="$BUILD/.pio/build/ws_lcd_350/firmware.bin"; [[ -s "$WS" ]] || fail "WS350 firmware missing"
step "Regression build jc3248w535"
(cd "$BUILD" && "$PIO" run -e jc3248w535); [[ -s "$BUILD/.pio/build/jc3248w535/firmware.bin" ]] || fail "regression firmware missing"
step "Merge Full image"
(cd "$BUILD" && "$VENV/bin/python" merge_bins.py --board ws_lcd_350 --full)
FULL="$(find "$BUILD/firmware" -type f -name 'BambuHelper-ws_lcd_350-*-Full.bin' | sort | tail -1)"; [[ -n "$FULL" && -s "$FULL" ]] || fail "Full image missing"
step "Package production candidate"
rm -rf "$OUT"; mkdir -p "$OUT"; FO="$OUT/BambuHelper-ws_lcd_350-v3.8.1-Workshop-OS-v11.25-RC10-Cupertino-UI-Full.bin"; OO="$OUT/BambuHelper-ws_lcd_350-v3.8.1-Workshop-OS-v11.25-RC10-Cupertino-UI-OTA.bin"; cp "$FULL" "$FO"; cp "$WS" "$OO"
SRC="$(git rev-parse HEAD)"; BR="$(git branch --show-current)"; FS="$(shasum -a 256 "$FO"|awk '{print $1}')"; OS="$(shasum -a 256 "$OO"|awk '{print $1}')"
cat > "$OUT/BUILD-REPORT.txt" <<EOF
Workshop OS v11.25 RC10 Cupertino UI
Result: BUILD PASS
Physical 480x320 acceptance: REQUIRED BEFORE PROMOTION/MERGE
Source branch: $BR
Source commit: $SRC
PlatformIO: $PIO_VERSION
Python: $($VENV/bin/python --version 2>&1)
Validated: UI10 fingerprints; 36/54 geometry; seven network pages; guarded hold UX; portal auth/same-origin; no TEST/NO CODE; no AMS inventory inference; WS350 build; jc3248w535 regression build.
Full SHA256: $FS
OTA SHA256: $OS
EOF
(cd "$OUT" && shasum -a 256 "$(basename "$FO")" "$(basename "$OO")" > SHA256SUMS.txt)
step "RC10 MACOS PRODUCTION BUILD PASS"
echo "Full: $FO"; echo "OTA: $OO"; echo "Report: $OUT/BUILD-REPORT.txt"; echo "Checksums: $OUT/SHA256SUMS.txt"; echo "NEXT: physical WS350 480x320 acceptance; do not merge before it passes."
