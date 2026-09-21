#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="${ROOT:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
BASE_URL="${WORKSHOP_OS_URL:-http://10.0.0.124}"
CANDIDATE_DIR=""
EXPECT_SOURCE_SHA=""
EXPECT_FIRMWARE_SHA256=""
CONFIRM_IDLE=0
FULL_BACKUP=0
PORT_OVERRIDE="${WAVESHARE_PORT:-}"
VID_PID="${WAVESHARE_VID_PID:-303A:1001}"

usage() {
  cat <<'EOF'
Usage:
  bash scripts/flash_os12_ci_candidate_macos.sh \
    --candidate-dir /path/to/extracted-ci-artifact \
    --expect-source-sha <40-hex-source-sha> \
    --expect-firmware-sha256 <64-hex-ci-firmware-sha256> \
    --confirm-printer-idle \
    --full-backup

Options:
  --candidate-dir DIR        Extracted CI artifact containing candidate.json,
                             SHA256SUMS.txt, firmware.bin and partitions.bin.
  --expect-source-sha SHA    Exact CI candidate source SHA.
  --expect-firmware-sha256 H Exact CI candidate firmware.bin SHA-256.
  --confirm-printer-idle     Required before USB reset/readback.
  --full-backup              Required for physical-acceptance install. Captures
                             the full 16 MB device flash before OTA install.
  --port PORT                Optional explicit /dev/cu.* device.
  --base-url URL             Local portal URL used for exact artifact OTA.
  -h, --help                 Show this help.

This is the canonical macOS physical-candidate installer. It DOES NOT rebuild
firmware locally and DOES NOT invoke PlatformIO. CI is the sole build authority.

Sequence:
  1. verify exact source + CI artifact metadata/hashes;
  2. provision an isolated esptool/pyserial runtime only;
  3. confirm the live partition table byte-for-byte against CI partitions.bin;
  4. preserve NVS, OTA data and a full 16 MB recovery image;
  5. upload the exact CI firmware.bin through the device's manual OTA endpoint;
  6. probe the rebooted runtime.

Cross-line migration remains a separate full-image-at-0x0 recovery procedure.
EOF
}

while (( $# )); do
  case "$1" in
    --candidate-dir)
      shift; [[ $# -gt 0 ]] || { echo "ERROR: --candidate-dir requires a value" >&2; exit 64; }
      CANDIDATE_DIR="$1"
      ;;
    --expect-source-sha)
      shift; [[ $# -gt 0 ]] || { echo "ERROR: --expect-source-sha requires a value" >&2; exit 64; }
      EXPECT_SOURCE_SHA="$1"
      ;;
    --expect-firmware-sha256)
      shift; [[ $# -gt 0 ]] || { echo "ERROR: --expect-firmware-sha256 requires a value" >&2; exit 64; }
      EXPECT_FIRMWARE_SHA256="$1"
      ;;
    --confirm-printer-idle) CONFIRM_IDLE=1 ;;
    --full-backup) FULL_BACKUP=1 ;;
    --port)
      shift; [[ $# -gt 0 ]] || { echo "ERROR: --port requires a value" >&2; exit 64; }
      PORT_OVERRIDE="$1"
      ;;
    --base-url)
      shift; [[ $# -gt 0 ]] || { echo "ERROR: --base-url requires a value" >&2; exit 64; }
      BASE_URL="$1"
      ;;
    -h|--help) usage; exit 0 ;;
    *) echo "ERROR: unknown argument: $1" >&2; usage >&2; exit 64 ;;
  esac
  shift
done

[[ "$CONFIRM_IDLE" -eq 1 ]] || { echo "ERROR: --confirm-printer-idle is required." >&2; exit 64; }
[[ "$FULL_BACKUP" -eq 1 ]] || { echo "ERROR: --full-backup is required for physical-acceptance install." >&2; exit 64; }
[[ "$EXPECT_SOURCE_SHA" =~ ^[0-9a-f]{40}$ ]] || { echo "ERROR: invalid --expect-source-sha" >&2; exit 64; }
[[ "$EXPECT_FIRMWARE_SHA256" =~ ^[0-9a-f]{64}$ ]] || { echo "ERROR: invalid --expect-firmware-sha256" >&2; exit 64; }
[[ -d "$CANDIDATE_DIR" ]] || { echo "ERROR: candidate directory missing: $CANDIDATE_DIR" >&2; exit 64; }

cd "$ROOT"
[[ -d .git ]] || { echo "ERROR: not inside the Workshop OS repository" >&2; exit 2; }
if ! git diff --quiet || ! git diff --cached --quiet; then
  echo "ERROR: tracked checkout changes are present; refusing physical candidate install." >&2
  exit 3
fi

HEAD_SHA="$(git rev-parse HEAD)"
if [[ "$HEAD_SHA" != "$EXPECT_SOURCE_SHA" ]]; then
  echo "STOP: local source SHA does not match the exact CI candidate." >&2
  echo "Local:    $HEAD_SHA" >&2
  echo "Expected: $EXPECT_SOURCE_SHA" >&2
  exit 22
fi

CANDIDATE_DIR="$(cd "$CANDIDATE_DIR" && pwd)"
CI_FIRMWARE="$CANDIDATE_DIR/firmware.bin"
CI_PARTITIONS="$CANDIDATE_DIR/partitions.bin"
CI_METADATA="$CANDIDATE_DIR/candidate.json"
CI_SUMS="$CANDIDATE_DIR/SHA256SUMS.txt"

for required in "$CI_FIRMWARE" "$CI_PARTITIONS" "$CI_METADATA" "$CI_SUMS"; do
  [[ -s "$required" ]] || { echo "ERROR: missing candidate file: $required" >&2; exit 24; }
done

read -r PARTITION_SHA PARTITION_SIZE < <(
python3 - "$CI_METADATA" "$CI_FIRMWARE" "$CI_PARTITIONS" "$CI_SUMS" "$EXPECT_SOURCE_SHA" "$EXPECT_FIRMWARE_SHA256" <<'PY'
import hashlib, json, os, sys
metadata_path, firmware_path, partitions_path, sums_path, expected_source, expected_fw = sys.argv[1:]

def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

with open(metadata_path, "r", encoding="utf-8") as fh:
    meta = json.load(fh)
with open(sums_path, "r", encoding="utf-8") as fh:
    sums = set(fh.read().splitlines())

fw_hash = sha256(firmware_path)
part_hash = sha256(partitions_path)
fw_size = os.path.getsize(firmware_path)
part_size = os.path.getsize(partitions_path)

required = {
    "product": "Workshop OS",
    "board": "ws_lcd_350",
    "sourceSha": expected_source,
    "firmwareSha256": expected_fw,
    "firmwareSize": fw_size,
    "partitionSha256": part_hash,
    "partitionSize": part_size,
    "artifactRole": "physical-acceptance-candidate",
    "candidateAuthority": "os12-ux-architecture",
    "physicalAcceptance": "required",
    "accepted": False,
    "stable": False,
}
for key, expected in required.items():
    actual = meta.get(key)
    if actual != expected:
        raise SystemExit(f"FAIL: candidate metadata {key}={actual!r}, expected {expected!r}")

if fw_hash != expected_fw:
    raise SystemExit(f"FAIL: firmware SHA-256 {fw_hash} != expected {expected_fw}")
if f"{expected_fw}  firmware.bin" not in sums:
    raise SystemExit("FAIL: SHA256SUMS.txt does not attest firmware.bin")
if f"{part_hash}  partitions.bin" not in sums:
    raise SystemExit("FAIL: SHA256SUMS.txt does not attest partitions.bin")

print(part_hash, part_size)
PY
)

echo "PASS: exact CI candidate metadata and hashes verified."
echo "Source SHA: $EXPECT_SOURCE_SHA"
echo "Firmware SHA-256: $EXPECT_FIRMWARE_SHA256"
echo "Partition SHA-256: $PARTITION_SHA"

select_python() {
  local p
  for p in "$(command -v python3.12 2>/dev/null || true)" \
           "$(command -v python3.11 2>/dev/null || true)" \
           "$(command -v python3.10 2>/dev/null || true)" \
           "$(command -v python3.9 2>/dev/null || true)"; do
    [[ -n "$p" && -x "$p" ]] || continue
    printf '%s\n' "$p"
    return 0
  done
  return 1
}

PYTHON_BIN="$(select_python || true)"
[[ -n "$PYTHON_BIN" ]] || {
  echo "ERROR: Python 3.9-3.12 is required for the isolated esptool runtime." >&2
  exit 4
}

TOOL_ROOT="${WORKSHOP_TOOL_ROOT:-$ROOT/.workshop-tools}"
ESP_VENV="$TOOL_ROOT/esptool-direct"
ESP_PY="$ESP_VENV/bin/python"
if [[ ! -x "$ESP_PY" ]]; then
  echo "Provisioning isolated direct-flash runtime at $ESP_VENV"
  mkdir -p "$TOOL_ROOT"
  "$PYTHON_BIN" -m venv "$ESP_VENV"
fi
"$ESP_PY" -m pip install --disable-pip-version-check --quiet \
  'pip>=24,<26' 'esptool==4.9.0' 'pyserial==3.5' 'intelhex>=2.3,<3'
"$ESP_PY" -c 'import esptool, serial, intelhex' >/dev/null

resolve_port() {
  if [[ -n "$PORT_OVERRIDE" ]]; then
    [[ -e "$PORT_OVERRIDE" ]] || { echo "ERROR: explicit port not found: $PORT_OVERRIDE" >&2; return 2; }
    printf '%s\n' "$PORT_OVERRIDE"
    return 0
  fi
  "$ESP_PY" - "$VID_PID" <<'PY'
import sys
from serial.tools import list_ports
raw = sys.argv[1]
vid_s, pid_s = raw.split(":", 1)
vid, pid = int(vid_s, 16), int(pid_s, 16)
matches = [p.device for p in list_ports.comports() if p.vid == vid and p.pid == pid]
if len(matches) != 1:
    if not matches:
        raise SystemExit(f"ERROR: no USB serial device matched VID:PID {raw}")
    raise SystemExit("ERROR: multiple matching USB serial devices: " + ", ".join(matches))
print(matches[0])
PY
}

PORT="$(resolve_port)"
echo "Printer-idle confirmation received before USB reset/readback."
echo "WS350 USB port: $PORT"

run_esptool() {
  "$ESP_PY" -m esptool --chip esp32s3 --port "$PORT" "$@"
}

printf '\n=== Chip probe ===\n'
run_esptool flash_id

STAMP="$(date +%Y%m%d-%H%M%S)"
BACKUP_DIR="${WS350_BACKUP_DIR:-$HOME/Downloads/workshop-os12-ws350-preflash-$STAMP}"
mkdir -p "$BACKUP_DIR"

printf '\n=== Recovery capture ===\n'
run_esptool read_flash 0x8000 "$PARTITION_SIZE" "$BACKUP_DIR/partition-table.bin"
run_esptool read_flash 0x9000 0x5000 "$BACKUP_DIR/nvs.bin"
run_esptool read_flash 0xe000 0x2000 "$BACKUP_DIR/otadata.bin"
echo "Reading full 16 MB flash; this can take several minutes..."
run_esptool read_flash 0x0 0x1000000 "$BACKUP_DIR/full-flash-16mb.bin"

printf '\n=== Partition-layout gate ===\n'
if ! cmp -s "$BACKUP_DIR/partition-table.bin" "$CI_PARTITIONS"; then
  echo "STOP: attached device partition table does not match the CI candidate layout." >&2
  echo "No application firmware was installed." >&2
  echo "Cross-line migration requires the approved full image at offset 0x0." >&2
  echo "Recovery evidence: $BACKUP_DIR" >&2
  exit 20
fi
echo "PASS: live partition table exactly matches CI partitions.bin."

{
  echo "captured_at=$STAMP"
  echo "source_sha=$EXPECT_SOURCE_SHA"
  echo "firmware_sha256=$EXPECT_FIRMWARE_SHA256"
  echo "partition_sha256=$PARTITION_SHA"
  echo "usb_port=$PORT"
  echo "install_transport=manual-ota-exact-ci-artifact"
} > "$BACKUP_DIR/BOOTSTRAP-INFO.txt"
shasum -a 256 "$BACKUP_DIR"/*.bin > "$BACKUP_DIR/SHA256SUMS.txt"

printf '\n=== Return device to runtime ===\n'
run_esptool run || true

READY=0
for _ in $(seq 1 30); do
  if curl -fsS --max-time 3 "$BASE_URL/recovery/status" >/dev/null 2>&1; then
    READY=1
    break
  fi
  sleep 2
done
if [[ "$READY" -ne 1 ]]; then
  echo "STOP: device did not return to the local recovery/runtime surface at $BASE_URL." >&2
  echo "No OTA upload was attempted. Recovery evidence: $BACKUP_DIR" >&2
  exit 27
fi

printf '\n=== Exact CI application OTA ===\n'
OTA_RESPONSE="$BACKUP_DIR/ota-upload-response.txt"
HTTP_CODE="$(curl -sS --max-time 180 \
  -o "$OTA_RESPONSE" \
  -w '%{http_code}' \
  -H "Origin: $BASE_URL" \
  -H "Referer: $BASE_URL/recovery" \
  -H "X-SHA256: $EXPECT_FIRMWARE_SHA256" \
  -F "file=@$CI_FIRMWARE;filename=Workshop-OS-12.0.0.bin;type=application/octet-stream" \
  "$BASE_URL/ota/upload" || true)"

if [[ "$HTTP_CODE" != "200" && "$HTTP_CODE" != "202" ]]; then
  echo "STOP: manual OTA endpoint did not accept the exact CI artifact (HTTP $HTTP_CODE)." >&2
  cat "$OTA_RESPONSE" >&2 || true
  echo "Recovery evidence: $BACKUP_DIR" >&2
  exit 28
fi
echo "PASS: exact CI firmware accepted by the device OTA endpoint (HTTP $HTTP_CODE)."
cat "$OTA_RESPONSE" || true

printf '\n=== Reboot / runtime probe ===\n'
sleep 10
READY=0
for _ in $(seq 1 30); do
  if curl -fsS --max-time 3 "$BASE_URL/recovery/status" >/dev/null 2>&1; then
    READY=1
    break
  fi
  sleep 2
done
[[ "$READY" -eq 1 ]] || {
  echo "FAIL: OTA upload completed but the runtime did not return at $BASE_URL." >&2
  echo "Use preserved recovery evidence at: $BACKUP_DIR" >&2
  exit 29
}

python3 scripts/accept_os12_portal_runtime.py --base-url "$BASE_URL" --probe-only

cat <<EOF

EXACT-CI PHYSICAL CANDIDATE INSTALL COMPLETE
Source SHA: $EXPECT_SOURCE_SHA
Firmware SHA-256: $EXPECT_FIRMWARE_SHA256
Candidate directory: $CANDIDATE_DIR
Recovery capture: $BACKUP_DIR
Install transport: manual OTA exact CI artifact
Local firmware rebuild: NO
PlatformIO used on Mac: NO

This establishes the exact physical candidate install plus the portal runtime subset.
Whole-device 480x320 acceptance, media quality, printer controls, recovery and GitHub
OTA remain separate gates before accepted/stable.
EOF
