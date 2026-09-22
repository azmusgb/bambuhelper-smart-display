#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="${ROOT:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
BUILD="${BUILD:-/tmp/ws350-os12-ux-build}"
BASE_URL="${WORKSHOP_OS_URL:-http://10.0.0.124}"
FLASH=0
CONFIRM_IDLE=0
ALLOW_DIRTY=0
FULL_BACKUP=0
EXPECT_SOURCE_SHA=""
EXPECT_FIRMWARE_SHA256=""

usage() {
  cat <<'EOF'
Usage:
  bash scripts/bootstrap_ws350_os12_usb_macos.sh
  bash scripts/bootstrap_ws350_os12_usb_macos.sh \
    --flash \
    --confirm-printer-idle \
    --expect-source-sha <40-hex-source-sha> \
    --expect-firmware-sha256 <64-hex-ci-firmware-sha256>

Options:
  --flash                    Perform the guarded USB bootstrap upload after checks.
  --confirm-printer-idle     Required before any USB chip probe/read/flash. Confirms
                             no printer is preparing, printing, or paused before the
                             local-control display can be reset into bootloader.
  --expect-source-sha SHA    Exact CI candidate source SHA. Required with --flash.
  --expect-firmware-sha256 H Exact CI candidate firmware.bin SHA-256. Required with
                             --flash. The locally reconstructed bytes must match.
  --full-backup              Read the full 16 MB device flash before upload. Slower.
  --allow-dirty              Allow building from a dirty local checkout.
  --base-url URL             Local portal base URL used for the post-flash probe.
  -h, --help                 Show this help.

Default mode is build-only and does not touch the attached device. Add
--confirm-printer-idle to permit USB chip probing/recovery reads and partition-table
comparison. Those operations can reset the WS350 into bootloader even though they do
not modify firmware. A partition mismatch fails closed; cross-line migration must use
the approved Full image at 0x0.

A physical-acceptance flash must also be byte-identical to the recorded exact-head
CI physical candidate. Source SHA alone is not sufficient release evidence.
EOF
}

while (( $# )); do
  case "$1" in
    --flash) FLASH=1 ;;
    --confirm-printer-idle) CONFIRM_IDLE=1 ;;
    --full-backup) FULL_BACKUP=1 ;;
    --allow-dirty) ALLOW_DIRTY=1 ;;
    --expect-source-sha)
      shift
      [[ $# -gt 0 ]] || { echo "ERROR: --expect-source-sha requires a value" >&2; exit 64; }
      EXPECT_SOURCE_SHA="$1"
      ;;
    --expect-firmware-sha256)
      shift
      [[ $# -gt 0 ]] || { echo "ERROR: --expect-firmware-sha256 requires a value" >&2; exit 64; }
      EXPECT_FIRMWARE_SHA256="$1"
      ;;
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

if [[ -n "$EXPECT_SOURCE_SHA" && ! "$EXPECT_SOURCE_SHA" =~ ^[0-9a-f]{40}$ ]]; then
  echo "ERROR: --expect-source-sha must be exactly 40 lowercase hex characters." >&2
  exit 64
fi
if [[ -n "$EXPECT_FIRMWARE_SHA256" && ! "$EXPECT_FIRMWARE_SHA256" =~ ^[0-9a-f]{64}$ ]]; then
  echo "ERROR: --expect-firmware-sha256 must be exactly 64 lowercase hex characters." >&2
  exit 64
fi
if [[ "$FLASH" -eq 1 && -z "$EXPECT_SOURCE_SHA" ]]; then
  echo "ERROR: --flash requires --expect-source-sha from the exact-head CI candidate." >&2
  exit 64
fi
if [[ "$FLASH" -eq 1 && -z "$EXPECT_FIRMWARE_SHA256" ]]; then
  echo "ERROR: --flash requires --expect-firmware-sha256 from the exact-head CI candidate." >&2
  exit 64
fi

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
if [[ -n "$EXPECT_SOURCE_SHA" && "$HEAD_SHA" != "$EXPECT_SOURCE_SHA" ]]; then
  echo "STOP: local source SHA does not match the exact-head CI candidate." >&2
  echo "Local:    $HEAD_SHA" >&2
  echo "Expected: $EXPECT_SOURCE_SHA" >&2
  echo "No build, device read, or firmware upload was attempted." >&2
  exit 22
fi

printf '=== Workshop OS 12 WS350 USB bootstrap ===\n'
printf 'Repository: %s\n' "$ROOT"
printf 'Branch: %s\n' "${BRANCH:-detached}"
printf 'Source SHA: %s\n' "$HEAD_SHA"
printf 'Build root: %s\n' "$BUILD"
printf 'Portal probe: %s\n' "$BASE_URL"
if [[ -n "$EXPECT_SOURCE_SHA" ]]; then
  printf 'Expected CI source SHA: %s\n' "$EXPECT_SOURCE_SHA"
fi
if [[ -n "$EXPECT_FIRMWARE_SHA256" ]]; then
  printf 'Expected CI firmware SHA-256: %s\n' "$EXPECT_FIRMWARE_SHA256"
fi

PIO_BIN="$(ROOT="$ROOT" bash scripts/ensure-platformio.sh)"
[[ -x "$PIO_BIN" ]] || { echo "ERROR: PlatformIO setup did not return an executable" >&2; exit 4; }
PIO_PYTHON="$(dirname "$PIO_BIN")/python"
[[ -x "$PIO_PYTHON" ]] || { echo "ERROR: PlatformIO Python runtime missing beside pio" >&2; exit 4; }
printf 'PlatformIO: %s\n' "$PIO_BIN"
printf 'PlatformIO Python: %s (%s)\n' "$PIO_PYTHON" "$("$PIO_PYTHON" --version 2>&1)"
"$PIO_BIN" --version

PIO_BIN="$PIO_BIN" BUILD="$BUILD" OS12_SOURCE_SHA="$HEAD_SHA" bash scripts/run_os12_ux_local.sh --build

FIRMWARE="$BUILD/.pio/build/ws_lcd_350/firmware.bin"
PARTITIONS="$BUILD/.pio/build/ws_lcd_350/partitions.bin"
[[ -s "$FIRMWARE" ]] || { echo "ERROR: expected WS350 firmware.bin missing" >&2; exit 4; }
[[ -s "$PARTITIONS" ]] || { echo "ERROR: expected WS350 partitions.bin missing" >&2; exit 4; }
FIRMWARE_SHA256="$(shasum -a 256 "$FIRMWARE" | awk '{print $1}')"

printf '\n=== Candidate identity ===\n'
ls -lh "$FIRMWARE" "$PARTITIONS"
printf '%s  %s\n' "$FIRMWARE_SHA256" "$FIRMWARE"

if [[ -n "$EXPECT_FIRMWARE_SHA256" ]]; then
  if [[ "$FIRMWARE_SHA256" != "$EXPECT_FIRMWARE_SHA256" ]]; then
    echo "STOP: locally reconstructed firmware does not match the exact-head CI candidate bytes." >&2
    echo "Local:    $FIRMWARE_SHA256" >&2
    echo "Expected: $EXPECT_FIRMWARE_SHA256" >&2
    echo "No device read or firmware upload was attempted." >&2
    exit 23
  fi
  echo "PASS: local firmware bytes exactly match the recorded CI candidate SHA-256."
fi

if [[ "$CONFIRM_IDLE" -ne 1 ]]; then
  cat <<EOF

CANDIDATE BUILD CHECKS: PASS
No USB device access was performed.
No firmware was changed.

To run the attached-device recovery/partition preflight, first confirm the printer
is not preparing, printing, or paused, then rerun with --confirm-printer-idle.
EOF
  exit 0
fi

echo "Printer-idle confirmation received before USB reset/probe."
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
    "$PIO_PYTHON" -m venv "$venv"
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
  echo "expected_source_sha=${EXPECT_SOURCE_SHA:-not-supplied}"
  echo "source_sha_verified=$([[ -n "$EXPECT_SOURCE_SHA" && "$HEAD_SHA" == "$EXPECT_SOURCE_SHA" ]] && echo true || echo false)"
  echo "branch=${BRANCH:-detached}"
  echo "usb_port=$PORT"
  echo "build_root=$BUILD"
  echo "firmware=$FIRMWARE"
  echo "firmware_sha256=$FIRMWARE_SHA256"
  echo "expected_firmware_sha256=${EXPECT_FIRMWARE_SHA256:-not-supplied}"
  echo "firmware_sha256_verified=$([[ -n "$EXPECT_FIRMWARE_SHA256" && "$FIRMWARE_SHA256" == "$EXPECT_FIRMWARE_SHA256" ]] && echo true || echo false)"
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

For a physical-acceptance flash, rerun only after exact-head CI is green and use
the CI-recorded source SHA + firmware SHA-256:

  bash scripts/bootstrap_ws350_os12_usb_macos.sh \
    --full-backup \
    --flash \
    --confirm-printer-idle \
    --expect-source-sha <EXACT_HEAD_SHA> \
    --expect-firmware-sha256 <CI_FIRMWARE_SHA256>
EOF
  exit 0
fi

# Defense in depth: the same confirmation is checked before USB probing above.
if [[ "$CONFIRM_IDLE" -ne 1 ]]; then
  echo "ERROR: --flash requires --confirm-printer-idle." >&2
  echo "Do not reboot the local-control display while printer state is active or uncertain." >&2
  exit 21
fi

printf '\n=== Guarded USB bootstrap upload ===\n'
echo "Source identity: VERIFIED against exact-head CI expectation."
echo "Firmware bytes: VERIFIED against exact-head CI SHA-256."
echo "Partition layout: VERIFIED against the attached WS350."
echo "Uploading the byte-identical reconstructed OS12 UX/control-plane candidate with the ws_lcd_350 PlatformIO target."
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
Firmware SHA-256: $FIRMWARE_SHA256
CI source identity verified: YES
CI firmware identity verified: YES
Recovery capture: $BACKUP_DIR

Next runtime gates once the device is reachable:
  python3 scripts/accept_os12_portal_runtime.py --base-url "$BASE_URL" --exercise-rate-limit
  python3 scripts/accept_os12_media_runtime.py --base-url "$BASE_URL" --exercise --exercise-video
  python3 scripts/accept_os12_media_physical.py --base-url "$BASE_URL" --expect-source-sha "$HEAD_SHA"
  python3 scripts/accept_os12_device_ui_physical.py --base-url "$BASE_URL" --expect-source-sha "$HEAD_SHA"
  python3 scripts/accept_os12_update_runtime.py --base-url "$BASE_URL" --channel candidate

Do not call the device accepted/stable yet. Touch/navigation, recovery, printer-control,
media quality and GitHub OTA behavior still require real-device acceptance.
EOF
