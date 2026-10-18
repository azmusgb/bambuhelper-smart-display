#!/usr/bin/env bash
set -Eeuo pipefail

# Experimental X2D bridge development candidate for the WS350.
#
# Copies the reconstructed canonical OS12 UX tree, applies the X2D overlays in
# order, and optionally builds and USB-flashes it. The canonical tree is never
# modified. This is a development candidate: it is never byte-identical to a CI
# physical-acceptance candidate because the bridge URL is compiled in.

ROOT="${ROOT:-$(git rev-parse --show-toplevel)}"
BASE="${BASE:-/tmp/ws350-os12-ux-build}"
BUILD="${BUILD:-/tmp/ws350-os12-x2d-build}"
BASE_URL="${WORKSHOP_OS_URL:-http://10.0.0.124}"
BRIDGE_URL="${X2D_BRIDGE_URL:-}"
RECONSTRUCT=0
DO_BUILD=0
FLASH=0
CONFIRM_IDLE=0

usage() {
  cat <<'EOF'
Usage:
  X2D_BRIDGE_URL=http://<mac-lan-ip>:8091/x2d/frame.jpg \
    bash scripts/run_x2d_local.sh [--reconstruct] [--build] [--flash --confirm-printer-idle]

Options:
  --reconstruct           Rebuild the canonical OS12 UX tree at $BASE first
                          (automatic when $BASE does not exist).
  --build                 Compile the ws_lcd_350 image in $BUILD.
  --flash                 USB-flash the built image (implies --build). Captures
                          partition table, NVS and otadata first and refuses on a
                          partition-layout mismatch. NVS is not erased.
  --confirm-printer-idle  Required with --flash. The live printer state is also
                          checked through the device portal when reachable.

Environment: BASE, BUILD, X2D_BRIDGE_URL, WORKSHOP_OS_URL, PIO_BIN.
EOF
}

while (( $# )); do
  case "$1" in
    --reconstruct) RECONSTRUCT=1 ;;
    --build) DO_BUILD=1 ;;
    --flash) FLASH=1; DO_BUILD=1 ;;
    --confirm-printer-idle) CONFIRM_IDLE=1 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "ERROR: unknown argument: $1" >&2; usage >&2; exit 64 ;;
  esac
  shift
done

[[ -n "$BRIDGE_URL" ]] || { echo "ERROR: X2D_BRIDGE_URL is required" >&2; usage >&2; exit 64; }
if [[ "$FLASH" -eq 1 && "$CONFIRM_IDLE" -ne 1 ]]; then
  echo "ERROR: --flash requires --confirm-printer-idle." >&2
  exit 21
fi

cd "$ROOT"

if [[ "$RECONSTRUCT" -eq 1 || ! -d "$BASE/src" ]]; then
  BUILD="$BASE" bash "$ROOT/scripts/run_os12_ux_local.sh"
fi

echo "=== X2D overlay candidate ==="
echo "BASE=$BASE"
echo "BUILD=$BUILD"
rm -rf "$BUILD"
# Copy .pio too so the overlay build reuses the canonical object cache.
cp -a "$BASE" "$BUILD"

python3 "$ROOT/apply_workshop_os12_x2d_bridge_camera.py" --repo "$BUILD" --bridge-url "$BRIDGE_URL" --apply
python3 "$ROOT/apply_workshop_os12_x2d_viewer_polish.py" --repo "$BUILD" --apply

[[ "$DO_BUILD" -eq 1 ]] || { echo "X2D overlays applied (no build requested)."; exit 0; }

PIO_BIN="${PIO_BIN:-$(ROOT="$ROOT" bash "$ROOT/scripts/ensure-platformio.sh")}"
[[ -x "$PIO_BIN" ]] || { echo 'FAIL: pio unavailable' >&2; exit 1; }
(cd "$BUILD" && "$PIO_BIN" run -e ws_lcd_350)
FIRMWARE="$BUILD/.pio/build/ws_lcd_350/firmware.bin"
PARTITIONS="$BUILD/.pio/build/ws_lcd_350/partitions.bin"
test -s "$FIRMWARE" || { echo 'FAIL: WS350 X2D image missing' >&2; exit 1; }
echo "X2D firmware: $FIRMWARE"
echo "X2D firmware SHA-256: $(shasum -a 256 "$FIRMWARE" | awk '{print $1}')"

[[ "$FLASH" -eq 1 ]] || exit 0

printf '\n=== Printer-idle gate ===\n'
if STATE_JSON="$(curl -fsS --max-time 4 -H 'X-BambuHelper-Client: 1' "$BASE_URL/status" 2>/dev/null)"; then
  STATE="$(printf '%s' "$STATE_JSON" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("state",""))')"
  echo "Printer state reported by the WS350: ${STATE:-unknown}"
  case "$STATE" in
    IDLE|FINISH|FAILED) ;;
    *) echo "STOP: printer is not idle (state=${STATE:-unknown}). No device access was attempted." >&2; exit 22 ;;
  esac
else
  echo "WARN: $BASE_URL/status unreachable; relying on --confirm-printer-idle."
fi

PORT="$(PIO_BIN="$PIO_BIN" bash "$ROOT/scripts/waveshare-usb.sh" port)"
echo "WS350 USB port: $PORT"
esptool() { "$PIO_BIN" pkg exec -p tool-esptoolpy -- esptool.py --chip esp32s3 --port "$PORT" "$@"; }

BACKUP_DIR="${WS350_BACKUP_DIR:-$HOME/Downloads/workshop-os12-x2d-preflash-$(date +%Y%m%d-%H%M%S)}"
mkdir -p "$BACKUP_DIR"
printf '\n=== Recovery capture ===\n'
esptool read_flash 0x8000 "$(stat -f '%z' "$PARTITIONS")" "$BACKUP_DIR/partition-table.bin"
esptool read_flash 0x9000 0x5000 "$BACKUP_DIR/nvs.bin"
esptool read_flash 0xe000 0x2000 "$BACKUP_DIR/otadata.bin"
shasum -a 256 "$BACKUP_DIR"/*.bin > "$BACKUP_DIR/SHA256SUMS.txt"
echo "Recovery capture: $BACKUP_DIR"

if ! cmp -s "$BACKUP_DIR/partition-table.bin" "$PARTITIONS"; then
  echo "STOP: device partition table does not match the X2D candidate layout. No firmware upload was attempted." >&2
  exit 20
fi
echo "PASS: partition layout matches."

printf '\n=== USB upload (development candidate) ===\n'
(cd "$BUILD" && "$PIO_BIN" run -e ws_lcd_350 -t upload --upload-port "$PORT")

printf '\n=== Portal reachability ===\n'
for _ in $(seq 1 30); do
  if curl -fsS --max-time 3 -H 'X-BambuHelper-Client: 1' "$BASE_URL/os12/update/status" 2>/dev/null; then
    echo
    exit 0
  fi
  sleep 2
done
echo "WARN: portal at $BASE_URL not reachable yet; the device may still be joining Wi-Fi." >&2
