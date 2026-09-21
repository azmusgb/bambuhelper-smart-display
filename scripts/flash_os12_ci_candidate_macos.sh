#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="${ROOT:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
BUILD="${BUILD:-/tmp/ws350-os12-ux-build}"
BASE_URL="${WORKSHOP_OS_URL:-http://10.0.0.124}"
CANDIDATE_DIR=""
EXPECT_SOURCE_SHA=""
EXPECT_FIRMWARE_SHA256=""
CONFIRM_IDLE=0
FULL_BACKUP=0

usage() {
  cat <<'EOF'
Usage:
  bash scripts/flash_os12_ci_candidate_macos.sh \
    --candidate-dir /tmp/os12-ci-candidate \
    --expect-source-sha <40-hex-source-sha> \
    --expect-firmware-sha256 <64-hex-ci-firmware-sha256> \
    --confirm-printer-idle

Options:
  --candidate-dir DIR        Extracted CI artifact directory containing
                             candidate.json, SHA256SUMS.txt, and firmware.bin.
  --expect-source-sha SHA    Exact CI candidate source SHA.
  --expect-firmware-sha256 H Exact CI candidate firmware.bin SHA-256.
  --confirm-printer-idle     Required. Confirms the printer is not preparing,
                             printing, or paused before the WS350 is reset.
  --full-backup              Ask the canonical bootstrap preflight for a full
                             16 MB backup before the application image is written.
  --base-url URL             Local portal URL for post-flash runtime acceptance.
  -h, --help                 Show this help.

This helper never rebuilds a substitute firmware for flashing. It first invokes the
canonical bootstrap in preflight-only mode to reconstruct source, probe the attached
WS350, capture recovery evidence, and require an exact partition-table match. It then
stages the already-verified CI firmware.bin into that build tree and uses PlatformIO
'nobuild' upload so the physical device receives the exact CI application bytes.
EOF
}

while (( $# )); do
  case "$1" in
    --candidate-dir)
      shift
      [[ $# -gt 0 ]] || { echo "ERROR: --candidate-dir requires a value" >&2; exit 64; }
      CANDIDATE_DIR="$1"
      ;;
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
    --confirm-printer-idle) CONFIRM_IDLE=1 ;;
    --full-backup) FULL_BACKUP=1 ;;
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

[[ "$CONFIRM_IDLE" -eq 1 ]] || { echo "ERROR: --confirm-printer-idle is required." >&2; exit 64; }
[[ "$EXPECT_SOURCE_SHA" =~ ^[0-9a-f]{40}$ ]] || { echo "ERROR: invalid --expect-source-sha" >&2; exit 64; }
[[ "$EXPECT_FIRMWARE_SHA256" =~ ^[0-9a-f]{64}$ ]] || { echo "ERROR: invalid --expect-firmware-sha256" >&2; exit 64; }
[[ -d "$CANDIDATE_DIR" ]] || { echo "ERROR: candidate directory missing: $CANDIDATE_DIR" >&2; exit 64; }

cd "$ROOT"
[[ -d .git ]] || { echo "ERROR: not inside the Workshop OS repository" >&2; exit 2; }
if ! git diff --quiet || ! git diff --cached --quiet; then
  echo "ERROR: tracked checkout changes are present; refusing physical candidate flash." >&2
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
CI_METADATA="$CANDIDATE_DIR/candidate.json"
CI_SUMS="$CANDIDATE_DIR/SHA256SUMS.txt"

[[ -s "$CI_FIRMWARE" ]] || { echo "ERROR: missing firmware.bin" >&2; exit 24; }
[[ -s "$CI_METADATA" ]] || { echo "ERROR: missing candidate.json" >&2; exit 24; }
[[ -s "$CI_SUMS" ]] || { echo "ERROR: missing SHA256SUMS.txt" >&2; exit 24; }

python3 - "$CI_METADATA" "$CI_FIRMWARE" "$CI_SUMS" "$EXPECT_SOURCE_SHA" "$EXPECT_FIRMWARE_SHA256" <<'PY'
import hashlib
import json
import os
import sys

metadata_path, firmware_path, sums_path, expected_source, expected_hash = sys.argv[1:]

with open(metadata_path, "r", encoding="utf-8") as fh:
    meta = json.load(fh)
with open(firmware_path, "rb") as fh:
    actual_hash = hashlib.sha256(fh.read()).hexdigest()
actual_size = os.path.getsize(firmware_path)
with open(sums_path, "r", encoding="utf-8") as fh:
    sums = fh.read().splitlines()

required = {
    "product": "Workshop OS",
    "board": "ws_lcd_350",
    "sourceSha": expected_source,
    "firmwareSha256": expected_hash,
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

if meta.get("firmwareSize") != actual_size:
    raise SystemExit(
        f"FAIL: candidate firmwareSize={meta.get('firmwareSize')} but file is {actual_size} bytes"
    )
if actual_hash != expected_hash:
    raise SystemExit(f"FAIL: firmware SHA-256 {actual_hash} != expected {expected_hash}")
if f"{expected_hash}  firmware.bin" not in sums:
    raise SystemExit("FAIL: SHA256SUMS.txt does not attest the expected firmware.bin")

print(f"PASS: exact CI physical candidate verified ({actual_size} bytes, {actual_hash})")
PY

printf '\n=== Canonical attached-device preflight ===\n'
PREFLIGHT_ARGS=(--confirm-printer-idle)
if [[ "$FULL_BACKUP" -eq 1 ]]; then
  PREFLIGHT_ARGS+=(--full-backup)
fi
WORKSHOP_OS_URL="$BASE_URL" BUILD="$BUILD" \
  bash scripts/bootstrap_ws350_os12_usb_macos.sh "${PREFLIGHT_ARGS[@]}"

PIO_BIN="$(ROOT="$ROOT" bash scripts/ensure-platformio.sh)"
[[ -x "$PIO_BIN" ]] || { echo "ERROR: PlatformIO unavailable after preflight" >&2; exit 4; }

PORT="$(PIO_BIN="$PIO_BIN" bash scripts/waveshare-usb.sh port)"
STAGED="$BUILD/.pio/build/ws_lcd_350/firmware.bin"
[[ -d "$(dirname "$STAGED")" ]] || {
  echo "ERROR: reconstructed WS350 build directory missing after preflight" >&2
  exit 4
}

printf '\n=== Stage exact CI application image ===\n'
cp "$CI_FIRMWARE" "$STAGED"
STAGED_SHA="$(shasum -a 256 "$STAGED" | awk '{print $1}')"
if [[ "$STAGED_SHA" != "$EXPECT_FIRMWARE_SHA256" ]]; then
  echo "STOP: staged firmware changed before upload." >&2
  echo "Staged:   $STAGED_SHA" >&2
  echo "Expected: $EXPECT_FIRMWARE_SHA256" >&2
  exit 25
fi

echo "PASS: staged firmware is byte-identical to the CI physical candidate."
echo "Upload port: $PORT"

printf '\n=== Guarded exact-CI USB upload ===\n'
(
  cd "$BUILD"
  "$PIO_BIN" run -e ws_lcd_350 -t nobuild -t upload --upload-port "$PORT"
)

printf '\n=== Post-upload candidate identity ===\n'
POST_SHA="$(shasum -a 256 "$STAGED" | awk '{print $1}')"
if [[ "$POST_SHA" != "$EXPECT_FIRMWARE_SHA256" ]]; then
  echo "FAIL: staged firmware identity changed during upload." >&2
  exit 26
fi

echo "Source SHA: $EXPECT_SOURCE_SHA"
echo "Firmware SHA-256: $POST_SHA"
echo "Flash source: exact CI artifact"
echo "NVS erase: NO"

printf '\n=== Reboot / runtime probe ===\n'
sleep 8
python3 scripts/accept_os12_portal_runtime.py --base-url "$BASE_URL" --probe-only

cat <<EOF

EXACT-CI PHYSICAL CANDIDATE FLASH COMPLETE
Source SHA: $EXPECT_SOURCE_SHA
Firmware SHA-256: $POST_SHA
Candidate directory: $CANDIDATE_DIR

This establishes only the exact-candidate physical install plus the portal runtime
subset above. Whole-device 480x320 acceptance, media quality, printer controls,
recovery, and OTA remain separate gates before accepted/stable.
EOF
