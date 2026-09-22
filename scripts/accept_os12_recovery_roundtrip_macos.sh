#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="${ROOT:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
BASE_URL="${WORKSHOP_OS_URL:-http://10.0.0.124}"
ARTIFACT_ZIP=""
CONFIRM_IDLE=0
EXERCISE=0
PORT_OVERRIDE="${WAVESHARE_PORT:-}"
VID_PID="${WAVESHARE_VID_PID:-303A:1001}"
FLASH_SIZE_HEX=0x1000000

usage() {
  cat <<'EOF'
Usage:
  bash scripts/accept_os12_recovery_roundtrip_macos.sh \
    --artifact-zip ~/Downloads/os12-ux-ws350-<sha>.zip \
    --confirm-printer-idle \
    --exercise \
    --base-url http://10.0.0.124

Purpose:
  Prove the WS350 full-image recovery path at flash offset 0x0 without changing
  the intended installed release. The script captures the device's current full
  16 MB flash, writes that exact captured image back to 0x0, verifies the device
  reboots into the same exact Workshop OS source SHA, and records evidence.

Safety:
  - no operator y/n/u prompts;
  - exact OS12 CI artifact identity is checked against releases/current.json;
  - current runtime source must equal the tested OS12 candidate source;
  - live partition table must equal the CI partitions.bin byte-for-byte;
  - a full 16 MB safety image is captured before any write;
  - only that just-captured image may be written at 0x0;
  - no erase_flash command is used;
  - no PlatformIO build or substitute firmware is used;
  - --confirm-printer-idle and --exercise are both required before mutation.

This validates the mechanical full-image recovery/boot path. It does not claim a
historical-version rollback, sensory acceptance, accepted state, or stable state.
EOF
}

while (( $# )); do
  case "$1" in
    --artifact-zip)
      shift; [[ $# -gt 0 ]] || { echo "ERROR: --artifact-zip requires a value" >&2; exit 64; }
      ARTIFACT_ZIP="$1"
      ;;
    --confirm-printer-idle) CONFIRM_IDLE=1 ;;
    --exercise) EXERCISE=1 ;;
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

[[ -n "$ARTIFACT_ZIP" ]] || { echo "ERROR: --artifact-zip is required" >&2; exit 64; }
[[ -f "$ARTIFACT_ZIP" ]] || { echo "ERROR: artifact ZIP not found: $ARTIFACT_ZIP" >&2; exit 64; }
[[ "$CONFIRM_IDLE" -eq 1 ]] || { echo "ERROR: --confirm-printer-idle is required before USB reset/readback." >&2; exit 64; }
[[ "$EXERCISE" -eq 1 ]] || { echo "ERROR: --exercise is required before any full-image write." >&2; exit 64; }

cd "$ROOT"
[[ -d .git ]] || { echo "ERROR: not inside Workshop OS repository" >&2; exit 2; }
if ! git diff --quiet || ! git diff --cached --quiet; then
  echo "ERROR: tracked checkout changes are present; refusing recovery exercise." >&2
  exit 3
fi

TMP_DIR="$(mktemp -d -t workshop-os12-recovery-artifact)"
cleanup() { rm -rf "$TMP_DIR"; }
trap cleanup EXIT

python3 - "$ARTIFACT_ZIP" "$TMP_DIR" <<'PY'
import pathlib, sys, zipfile
src, dst = pathlib.Path(sys.argv[1]).expanduser(), pathlib.Path(sys.argv[2])
wanted = {"candidate.json", "SHA256SUMS.txt", "partitions.bin"}
with zipfile.ZipFile(src) as zf:
    by_name = {pathlib.PurePosixPath(n).name: n for n in zf.namelist()}
    missing = sorted(wanted - set(by_name))
    if missing:
        raise SystemExit("FAIL: artifact ZIP missing: " + ", ".join(missing))
    for name in wanted:
        (dst / name).write_bytes(zf.read(by_name[name]))
PY

CI_METADATA="$TMP_DIR/candidate.json"
CI_SUMS="$TMP_DIR/SHA256SUMS.txt"
CI_PARTITIONS="$TMP_DIR/partitions.bin"

read -r EXPECT_SOURCE_SHA EXPECT_FIRMWARE_SHA256 EXPECT_PARTITION_SHA256 PARTITION_SIZE < <(
python3 - "$CI_METADATA" "$CI_SUMS" "$CI_PARTITIONS" "$ROOT/releases/current.json" <<'PY'
import hashlib, json, os, re, sys
meta_path, sums_path, partitions_path, release_path = sys.argv[1:]
meta = json.load(open(meta_path, encoding="utf-8"))
release = json.load(open(release_path, encoding="utf-8"))
state = release.get("mainState") or {}
source = meta.get("sourceSha")
fw = meta.get("firmwareSha256")
part = hashlib.sha256(open(partitions_path, "rb").read()).hexdigest()
if not isinstance(source, str) or not re.fullmatch(r"[0-9a-f]{40}", source):
    raise SystemExit("FAIL: candidate.json sourceSha is invalid")
if not isinstance(fw, str) or not re.fullmatch(r"[0-9a-f]{64}", fw):
    raise SystemExit("FAIL: candidate.json firmwareSha256 is invalid")
if source != state.get("testedCandidateCommit"):
    raise SystemExit("FAIL: artifact source is not releases/current.json testedCandidateCommit")
if fw != state.get("testedFirmwareSha256"):
    raise SystemExit("FAIL: artifact firmware hash is not releases/current.json testedFirmwareSha256")
if meta.get("partitionSha256") != part:
    raise SystemExit("FAIL: candidate.json partition SHA does not match partitions.bin")
sums = set(open(sums_path, encoding="utf-8").read().splitlines())
if f"{part}  partitions.bin" not in sums:
    raise SystemExit("FAIL: SHA256SUMS.txt does not attest partitions.bin")
print(source, fw, part, os.path.getsize(partitions_path))
PY
)

runtime_source() {
  PYTHONPATH="$ROOT/scripts" python3 - "$BASE_URL" <<'PY'
import sys
from accept_os12_media_physical import update_identity
from accept_os12_portal_runtime import Client, assert_code_free_portal
client = Client(sys.argv[1].rstrip("/"))
assert_code_free_portal(client)
print(update_identity(client)["runningSourceCommit"])
PY
}

wait_for_runtime() {
  local expected="$1"
  local got=""
  for _ in $(seq 1 45); do
    got="$(runtime_source 2>/dev/null || true)"
    if [[ "$got" == "$expected" ]]; then
      printf '%s\n' "$got"
      return 0
    fi
    sleep 2
  done
  return 1
}

START_SOURCE="$(runtime_source)"
if [[ "$START_SOURCE" != "$EXPECT_SOURCE_SHA" ]]; then
  echo "STOP: running source does not match the exact tested OS12 candidate." >&2
  echo "Running:  $START_SOURCE" >&2
  echo "Expected: $EXPECT_SOURCE_SHA" >&2
  exit 22
fi

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
[[ -n "$PYTHON_BIN" ]] || { echo "ERROR: Python 3.9-3.12 is required." >&2; exit 4; }
TOOL_ROOT="${WORKSHOP_TOOL_ROOT:-$ROOT/.workshop-tools}"
ESP_VENV="$TOOL_ROOT/esptool-direct"
ESP_PY="$ESP_VENV/bin/python"
if [[ ! -x "$ESP_PY" ]]; then
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
vid_s, pid_s = sys.argv[1].split(":", 1)
vid, pid = int(vid_s, 16), int(pid_s, 16)
matches = [p.device for p in list_ports.comports() if p.vid == vid and p.pid == pid]
if len(matches) != 1:
    raise SystemExit("ERROR: expected exactly one WS350 USB device, found: " + ", ".join(matches))
print(matches[0])
PY
}

PORT="$(resolve_port)"
run_esptool() { "$ESP_PY" -m esptool --chip esp32s3 --port "$PORT" "$@"; }

STAMP="$(date +%Y%m%d-%H%M%S)"
EVIDENCE_DIR="${WS350_RECOVERY_EVIDENCE_DIR:-$HOME/Downloads/workshop-os12-recovery-roundtrip-$STAMP}"
mkdir -p "$EVIDENCE_DIR"
FULL_IMAGE="$EVIDENCE_DIR/current-full-flash-16mb.bin"
LIVE_PARTITIONS="$EVIDENCE_DIR/live-partition-table.bin"
LOG="$EVIDENCE_DIR/recovery-roundtrip.log"
exec > >(tee -a "$LOG") 2>&1

echo "=== Workshop OS 12 unattended recovery round-trip ==="
echo "Expected running source: $EXPECT_SOURCE_SHA"
echo "Expected firmware SHA-256: $EXPECT_FIRMWARE_SHA256"
echo "Expected partition SHA-256: $EXPECT_PARTITION_SHA256"
echo "Printer-idle confirmation received: YES"
echo "Mutation authorization (--exercise): YES"
echo "No interactive prompts will be used."

echo
echo "=== USB chip probe ==="
run_esptool flash_id

echo
echo "=== Partition-layout gate ==="
run_esptool read_flash 0x8000 "$PARTITION_SIZE" "$LIVE_PARTITIONS"
if ! cmp -s "$LIVE_PARTITIONS" "$CI_PARTITIONS"; then
  echo "STOP: live partition table differs from exact CI candidate partitions.bin." >&2
  exit 20
fi
echo "PASS: live partition table matches exact CI candidate."

echo
echo "=== Capture current full-image safety snapshot ==="
echo "Reading full 16 MB flash; this can take several minutes."
run_esptool read_flash 0x0 "$FLASH_SIZE_HEX" "$FULL_IMAGE"
FULL_SHA256="$(shasum -a 256 "$FULL_IMAGE" | awk '{print $1}')"
FULL_SIZE="$(stat -f%z "$FULL_IMAGE" 2>/dev/null || stat -c%s "$FULL_IMAGE")"
[[ "$FULL_SIZE" == "16777216" ]] || { echo "STOP: full recovery image is not exactly 16 MB." >&2; exit 24; }
shasum -a 256 "$FULL_IMAGE" "$LIVE_PARTITIONS" > "$EVIDENCE_DIR/SHA256SUMS.txt"
echo "PASS: captured full recovery image: $FULL_SHA256"

echo
echo "=== Full-image recovery exercise at 0x0 ==="
echo "Writing ONLY the just-captured current-device 16 MB image back to flash."
run_esptool write_flash 0x0 "$FULL_IMAGE"

echo
echo "=== Reboot / exact-source validation ==="
run_esptool run || true
sleep 8
if ! END_SOURCE="$(wait_for_runtime "$EXPECT_SOURCE_SHA")"; then
  echo "FAIL: device did not return with expected exact source after full-image restore." >&2
  exit 29
fi
echo "PASS: full-image restore booted exact source $END_SOURCE"

python3 - "$EVIDENCE_DIR/evidence.json" "$EXPECT_SOURCE_SHA" "$EXPECT_FIRMWARE_SHA256" "$EXPECT_PARTITION_SHA256" "$FULL_SHA256" "$START_SOURCE" "$END_SOURCE" "$ARTIFACT_ZIP" <<'PY'
from datetime import datetime, timezone
import json, pathlib, sys
(out, expected_source, fw_sha, part_sha, full_sha, start_source, end_source, artifact) = sys.argv[1:]
payload = {
    "schemaVersion": 1,
    "kind": "workshop-os12-full-image-recovery-roundtrip",
    "recordedAt": datetime.now(timezone.utc).isoformat(),
    "artifactZip": str(pathlib.Path(artifact).expanduser()),
    "expectedSourceSha": expected_source,
    "testedFirmwareSha256": fw_sha,
    "partitionSha256": part_sha,
    "capturedFullImageSha256": full_sha,
    "fullImageBytes": 16777216,
    "startRuntimeSourceSha": start_source,
    "endRuntimeSourceSha": end_source,
    "flashOffset": "0x0",
    "sourcePreserved": start_source == end_source == expected_source,
    "partitionIdentityPassed": True,
    "fullImageCapturePassed": True,
    "fullImageWritePassed": True,
    "postRestoreRuntimePassed": True,
    "unattended": True,
    "historicalRollbackTested": False,
    "physicalSensoryAcceptance": None,
    "accepted": False,
    "stable": False,
    "scope": "same-state full-image recovery round-trip; proves recovery write/boot path without claiming historical-version rollback or sensory acceptance",
}
pathlib.Path(out).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY

cat <<EOF

UNATTENDED FULL-IMAGE RECOVERY ROUND-TRIP: PASS
Evidence: $EVIDENCE_DIR/evidence.json
Full-image SHA-256: $FULL_SHA256
Runtime source before: $START_SOURCE
Runtime source after:  $END_SOURCE

This proves the current-device full-image capture -> write at 0x0 -> reboot ->
exact-source recovery path. It does NOT prove a historical-version rollback and
does NOT by itself mark Workshop OS physically validated, accepted, or stable.
EOF
