#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="${ROOT:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
BUILD="${BUILD:-/tmp/ws350-os12-ux-build}"
BASE_URL="${WORKSHOP_OS_URL:-http://10.0.0.124}"
FLASH=0
CONFIRM_IDLE=0
ALLOW_DIRTY=0
FULL_BACKUP=0

usage() {
  cat <<'EOF'
Usage:
  bash scripts/bootstrap_ws350_os12_usb_macos.sh
  bash scripts/bootstrap_ws350_os12_usb_macos.sh --flash --confirm-printer-idle

Options:
  --flash                  Perform the guarded USB bootstrap upload after checks.
  --confirm-printer-idle   Required with --flash. Confirms no printer is preparing,
                           printing, or paused before the display is rebooted.
  --full-backup            Read the full 16 MB device flash before upload. Slower.
  --allow-dirty            Allow building from a dirty local checkout.
  --base-url URL           Local portal base URL used for the post-flash probe.
  -h, --help               Show this help.

Default mode is non-mutating with respect to device firmware: build the exact local
OS12 image, identify the attached WS350, back up critical flash metadata, and compare
the live partition table with the expected Workshop OS 16 MB layout. A partition
mismatch fails closed; cross-line migration must use the approved Full image at 0x0.
EOF
}

while (( $# )); do
  case "$1" in
    --flash) FLASH=1 ;;
    --confirm-printer-idle) CONFIRM_IDLE=1 ;;
    --full-backup) FULL_BACKUP=1 ;;
    --allow-dirty) ALLOW_DIRTY=1 ;;
    --base-url)
      shift
      [[ $# -gt 0 ]] || { echo "ERROR: --base-url requires a value" >&2; exit 64; }
      BASE_URL="$1"
      ;;
    -h|--help) usage; exit 0 ;;
    *) echo "ERROR: unknown argument: $1" >&2; usage >&2; exit 64 ;;
  esac
  shift
done

cd "$ROOT"
[[ -d .git ]] || { echo "ERROR: not inside the Workshop OS git repository" >&2; exit 2; }
[[ -f scripts/run_os12_ux_local.sh ]] || { echo "ERROR: OS12 UX/control-plane build helper missing" >&2; exit 2; }
[[ -f scripts/waveshare-usb.sh ]] || { echo "ERROR: WS350 USB resolver missing" >&2; exit 2; }
[[ -f scripts/ensure-platformio.sh ]] || { echo "ERROR: PlatformIO setup helper missing" >&2; exit 2; }
command -v python3 >/dev/null 2>&1 || { echo "ERROR: python3 is required" >&2; exit 2; }

if [[ "$ALLOW_DIRTY" -ne 1 ]]; then
  if ! git diff --quiet || ! git diff --cached --quiet; then
    echo "ERROR: local checkout has uncommitted changes." >&2
    echo "Commit/stash them or rerun with --allow-dirty if intentional." >&2
    exit 3
  fi
fi

HEAD_SHA="$(git rev-parse HEAD)"
BRANCH="$(git branch --show-current || true)"
printf '=== Workshop OS 12 WS350 USB bootstrap ===\n'
printf 'Repository: %s\n' "$ROOT"
printf 'Branch: %s\n' "${BRANCH:-detached}"
printf 'Source SHA: %s\n' "$HEAD_SHA"
printf 'Build root: %s\n' "$BUILD"
printf 'Portal probe: %s\n' "$BASE_URL"

PIO_BIN="$(ROOT="$ROOT" bash scripts/ensure-platformio.sh)"
[[ -x "$PIO_BIN" ]] || { echo "ERROR: PlatformIO setup did not return an executable" >&2; exit 4; }
printf 'PlatformIO: %s\n' "$PIO_BIN"
"$PIO_BIN" --version

PIO_BIN="$PIO_BIN" BUILD="$BUILD" OS12_SOURCE_SHA="$HEAD_SHA" bash scripts/run_os12_ux_local.sh --build

FIRMWARE="$BUILD/.pio/build/ws_lcd_350/firmware.bin"
PARTITIONS="$BUILD/.pio/build/ws_lcd_350/partitions.bin"
[[ -s "$FIRMWARE" ]] || { echo "ERROR: expected WS350 firmware.bin missing" >&2; exit 4; }
[[ -s "$PARTITIONS" ]] || { echo "ERROR: expected WS350 partitions.bin missing" >&2; exit 4; }

printf '\n=== Candidate identity ===\n'
ls -lh "$FIRMWARE" "$PARTITIONS"
shasum -a 256 "$FIRMWARE"

PORT="$(PIO_BIN="$PIO_BIN" bash scripts/waveshare-usb.sh port)"
printf '\n=== Attached device ===\n'
printf 'Port: %s\n' "$PORT"

ensure_esptool_runtime() {
  local tool_root="${WORKSHOP_TOOL_ROOT:-$ROOT/.workshop-tools}"
  local venv="$tool_root/esptool"
  local py="$venv/bin/python"

  if [[ -x "$py" ]] && "$py" -c 'import esptool, intelhex' >/dev/null 2>&1; then
    printf '%s\n' "$py|-m|esptool"
    return 0
  fi

  echo "Provisioning isolated esptool runtime at $venv" >&2
  mkdir -p "$tool_root"
  if [[ ! -x "$py" ]]; then
    python3 -m venv "$venv"
  fi

  "$py" -m pip install \
    --disable-pip-version-check \
    --upgrade \
    'pip>=24,<26' \
    'esptool==4.9.0' \
    'intelhex>=2.3,<3' >&2

  "$py" -c 'import esptool, intelhex' >/dev/null 2>&1 || {
    echo "ERROR: isolated esptool runtime is incomplete after provisioning." >&2
    return 1
  }

  printf '%s\n' "$py|-m|esptool"
}

ESP_SPEC="$(ensure_esptool_runtime)" || {
  echo "ERROR: unable to provision a complete isolated esptool runtime." >&2
  exit 5
}
IFS='|' read -r -a ESPTOOL <<<"$ESP_SPEC"

run_esptool() {
  "${ESPTOOL[@]}" --chip esp32s3 --port "$PORT" "$@"
}

printf '\n=== Chip probe ===\n'
run_esptool flash_id

STAMP="$(date +%Y%m%d-%H%M%S)"
BACKUP_DIR="${WS350_BACKUP_DIR:-$HOME/Downloads/workshop-os12-ws350-preflash-$STAMP}"
mkdir -p "$BACKUP_DIR"

PART_SIZE="$(python3 - "$PARTITIONS" <<'PY'
import os, sys
print(os.path.getsize(sys.argv[1]))
PY
)"

printf '\n=== Critical recovery capture ===\n'
run_esptool read_flash 0x8000 "$PART_SIZE" "$BACKUP_DIR/partition-table.bin"
run_esptool read_flash 0x9000 0x5000 "$BACKUP_DIR/nvs.bin"
run_esptool read_flash 0xe000 0x2000 "$BACKUP_DIR/otadata.bin"

if [[ "$FULL_BACKUP" -eq 1 ]]; then
  echo "Reading full 16 MB flash; this can take several minutes..."
  run_esptool read_flash 0x0 0x1000000 "$BACKUP_DIR/full-flash-16mb.bin"
fi

{
  echo "captured_at=$STAMP"
  echo "source_sha=$HEAD_SHA"
  echo "branch=${BRANCH:-detached}"
  echo "usb_port=$PORT"
  echo "build_root=$BUILD"
  echo "firmware=$FIRMWARE"
  echo "firmware_sha256=$(shasum -a 256 "$FIRMWARE" | awk '{print $1}')"
  echo "partition_sha256=$(shasum -a 256 "$BACKUP_DIR/partition-table.bin" | awk '{print $1}')"
  echo "expected_partition_sha256=$(shasum -a 256 "$PARTITIONS" | awk '{print $1}')"
} > "$BACKUP_DIR/BOOTSTRAP-INFO.txt"

shasum -a 256 "$BACKUP_DIR"/*.bin > "$BACKUP_DIR/SHA256SUMS.txt"
printf 'Recovery capture: %s\n' "$BACKUP_DIR"

printf '\n=== Partition-layout gate ===\n'
if ! cmp -s "$BACKUP_DIR/partition-table.bin" "$PARTITIONS"; then
  echo "STOP: attached device partition table does not match the reconstructed Workshop OS 16 MB layout." >&2
  echo "No firmware upload was attempted." >&2
  echo "Cross-line migration must use the approved Full image at flash offset 0x0; do not force this bootstrap path." >&2
  echo "Recovery evidence is preserved at: $BACKUP_DIR" >&2
  exit 20
fi

echo "PASS: attached device partition table exactly matches the expected Workshop OS layout."

if [[ "$FLASH" -ne 1 ]]; then
  cat <<EOF

PRE-FLASH CHECKS: PASS
No firmware was changed.

To install this exact reconstructed OS12 UX/control-plane image after confirming the Bambu printer is idle:
  bash scripts/bootstrap_ws350_os12_usb_macos.sh --flash --confirm-printer-idle
EOF
  exit 0
fi

if [[ "$CONFIRM_IDLE" -ne 1 ]]; then
  echo "ERROR: --flash requires --confirm-printer-idle." >&2
  echo "Do not reboot the local-control display while printer state is active or uncertain." >&2
  exit 21
fi

printf '\n=== Guarded USB bootstrap upload ===\n'
echo "The partition layout matched exactly; uploading the exact reconstructed OS12 UX/control-plane candidate with the ws_lcd_350 PlatformIO target."
echo "NVS is not erased. Critical pre-flash recovery data is already captured."
(
  cd "$BUILD"
  "$PIO_BIN" run -e ws_lcd_350 -t upload --upload-port "$PORT"
)

printf '\n=== Reboot / USB rediscovery ===\n'
sleep 8
if NEW_PORT="$(PIO_BIN="$PIO_BIN" bash scripts/waveshare-usb.sh port 2>/dev/null)"; then
  echo "WS350 USB returned at: $NEW_PORT"
else
  echo "WS350 has not re-enumerated on USB yet; continue with the network probe after it finishes booting."
fi

printf '\n=== Local portal preflight ===\n'
READY=0
for _ in $(seq 1 20); do
  if curl -fsS --max-time 3 "$BASE_URL/login" >/dev/null 2>&1; then
    READY=1
    break
  fi
  sleep 2
done

if [[ "$READY" -eq 1 ]]; then
  python3 scripts/accept_os12_portal_runtime.py --base-url "$BASE_URL" --probe-only
else
  echo "INFO: local portal did not become reachable at $BASE_URL during this short probe window."
  echo "The USB upload completed; Wi-Fi may still be reconnecting or the device may use a different address."
fi

cat <<EOF

USB BOOTSTRAP COMPLETE
Source SHA: $HEAD_SHA
Firmware SHA-256: $(shasum -a 256 "$FIRMWARE" | awk '{print $1}')
Recovery capture: $BACKUP_DIR

Next runtime gates once the device is reachable:
  python3 scripts/accept_os12_portal_runtime.py --base-url "$BASE_URL" --exercise-rate-limit
  python3 scripts/accept_os12_media_runtime.py --base-url "$BASE_URL" --exercise --exercise-video
  python3 scripts/accept_os12_media_physical.py --base-url "$BASE_URL"
  python3 scripts/accept_os12_update_runtime.py --base-url "$BASE_URL" --channel candidate

Do not call the device accepted/stable yet. Touch/navigation, recovery, printer-control,
media quality and GitHub OTA behavior still require real-device acceptance.
EOF
