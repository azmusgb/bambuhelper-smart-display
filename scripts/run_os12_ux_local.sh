#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="${ROOT:-$(git rev-parse --show-toplevel)}"
BUILD="${BUILD:-/tmp/ws350-os12-ux-build}"
OS12_RELEASE_VERSION="${OS12_RELEASE_VERSION:-12.0.0}"
OS12_SOURCE_SHA="${OS12_SOURCE_SHA:-$(git -C "$ROOT" rev-parse HEAD)}"

cd "$ROOT"

echo "=== Workshop OS 12 UX architecture reconstruction ==="
echo "ROOT=$ROOT"
echo "BUILD=$BUILD"
echo "OS12_RELEASE_VERSION=$OS12_RELEASE_VERSION"
echo "OS12_SOURCE_SHA=$OS12_SOURCE_SHA"

BUILD="$BUILD" \
OS12_RELEASE_VERSION="$OS12_RELEASE_VERSION" \
OS12_SOURCE_SHA="$OS12_SOURCE_SHA" \
bash "$ROOT/scripts/run_os12_platform_local.sh"

python3 "$ROOT/apply_workshop_os12_ux_architecture.py" --repo "$BUILD" --apply
python3 "$ROOT/apply_workshop_os12_ux_geometry.py" --repo "$BUILD" --apply
python3 "$ROOT/apply_workshop_os12_ux_physical_fit.py" --repo "$BUILD" --apply
python3 "$ROOT/scripts/validate_os12_ux_architecture.py" --repo "$BUILD"
python3 "$ROOT/scripts/validate_os12_ux_geometry.py" --repo "$BUILD"
python3 "$ROOT/scripts/validate_os12_ux_physical_fit.py" --repo "$BUILD"

if [[ "${1:-}" == "--build" ]]; then
  PIO_BIN="$(ROOT="$ROOT" bash "$ROOT/scripts/ensure-platformio.sh")"
  [[ -x "$PIO_BIN" ]] || { echo 'FAIL: pio unavailable after isolated setup' >&2; exit 1; }
  echo "PlatformIO: $PIO_BIN"
  "$PIO_BIN" --version

  echo "=== Build WS350 OS12 UX v3 physical-fit candidate ==="
  (cd "$BUILD" && "$PIO_BIN" run -e ws_lcd_350)
  test -s "$BUILD/.pio/build/ws_lcd_350/firmware.bin" || { echo 'FAIL: WS350 UX image missing' >&2; exit 1; }

  echo "=== Cross-board compile regression ==="
  (cd "$BUILD" && "$PIO_BIN" run -e jc3248w535)
  test -s "$BUILD/.pio/build/jc3248w535/firmware.bin" || { echo 'FAIL: cross-board UX image missing' >&2; exit 1; }
fi

echo "=== OS12 UX architecture reconstruction complete ==="
echo "Release identity: Workshop OS $OS12_RELEASE_VERSION @ $OS12_SOURCE_SHA"
echo "UX state: hierarchical-flat-v3 physical-fit/navigation corrections implemented."
echo "Root navigation: Home / Printer / Workshop / More enforced in reconstructed firmware."
echo "Local Portal: Network and System routes converge deterministically with exact-parent Back behavior."
echo "Child/config navigation: global bottom navigation removed from migrated screens."
echo "Geometry: 12px side margin, 52px canonical rows/actions, compact two-line physical evidence composition."
echo "Components: navigation row, command button, setting row/evidence row vocabulary."
echo "Home/Workshop: explicit Unknown/Undetermined where Filament Inventory evidence is unavailable."
echo "Inventory authority: unchanged; no spool identity, quantity, placement, or readiness is inferred."
echo "Physical acceptance: REQUIRED before integration into the canonical bootstrap/update path."
echo "Stable promotion: forbidden by this script."
