#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="${ROOT:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
BASE_URL="${WORKSHOP_OS_URL:-http://10.0.0.124}"
ARTIFACT_ZIP=""
CONFIRM_IDLE=0
FULL_BACKUP=0

usage() {
  cat <<'EOF'
Usage:
  bash scripts/install_accept_os12_candidate_macos.sh \
    --artifact-zip ~/Downloads/os12-ux-ws350-<sha>.zip \
    --confirm-printer-idle \
    --full-backup \
    [--base-url http://10.0.0.124]

One-command exact-candidate install + unattended acceptance.

The script:
  1. extracts the CI artifact into an isolated temp directory;
  2. reads exact source/firmware identity from candidate.json;
  3. requires local git HEAD to match the artifact source SHA;
  4. invokes the canonical guarded macOS physical-candidate installer;
  5. verifies post-reboot runningSourceCommit;
  6. runs unattended whole-device acceptance against that exact installed SHA.

It does not locally rebuild firmware and does not weaken physical/recovery gates.
EOF
}

while (( $# )); do
  case "$1" in
    --artifact-zip) shift; ARTIFACT_ZIP="${1:-}" ;;
    --confirm-printer-idle) CONFIRM_IDLE=1 ;;
    --full-backup) FULL_BACKUP=1 ;;
    --base-url) shift; BASE_URL="${1:-}" ;;
    -h|--help) usage; exit 0 ;;
    *) echo "ERROR: unknown argument: $1" >&2; usage >&2; exit 64 ;;
  esac
  shift
done

[[ -n "$ARTIFACT_ZIP" ]] || { echo "ERROR: --artifact-zip is required" >&2; exit 64; }
[[ -s "$ARTIFACT_ZIP" ]] || { echo "ERROR: artifact zip missing: $ARTIFACT_ZIP" >&2; exit 64; }
[[ "$CONFIRM_IDLE" -eq 1 ]] || { echo "ERROR: --confirm-printer-idle is required" >&2; exit 64; }
[[ "$FULL_BACKUP" -eq 1 ]] || { echo "ERROR: --full-backup is required" >&2; exit 64; }

cd "$ROOT"
[[ -d .git ]] || { echo "ERROR: not inside Workshop OS repository" >&2; exit 2; }

WORK_DIR="$(mktemp -d "${TMPDIR:-/tmp}/os12-candidate.XXXXXX")"
cleanup(){ rm -rf "$WORK_DIR"; }
trap cleanup EXIT

unzip -q "$ARTIFACT_ZIP" -d "$WORK_DIR"
for f in candidate.json SHA256SUMS.txt firmware.bin partitions.bin; do
  [[ -s "$WORK_DIR/$f" ]] || { echo "ERROR: artifact missing $f" >&2; exit 24; }
done

read -r SOURCE_SHA FIRMWARE_SHA < <(
python3 - "$WORK_DIR/candidate.json" <<'PY'
import json, re, sys
with open(sys.argv[1], "r", encoding="utf-8") as fh:
    d=json.load(fh)
source=str(d.get("sourceSha","")).lower()
firmware=str(d.get("firmwareSha256","")).lower()
if not re.fullmatch(r"[0-9a-f]{40}",source):
    raise SystemExit("FAIL: candidate sourceSha invalid")
if not re.fullmatch(r"[0-9a-f]{64}",firmware):
    raise SystemExit("FAIL: candidate firmwareSha256 invalid")
if d.get("artifactRole")!="physical-acceptance-candidate":
    raise SystemExit("FAIL: artifact is not a physical-acceptance candidate")
if d.get("candidateAuthority")!="os12-ux-architecture":
    raise SystemExit("FAIL: candidate authority is not os12-ux-architecture")
if d.get("accepted") is not False or d.get("stable") is not False:
    raise SystemExit("FAIL: CI candidate metadata improperly claims accepted/stable")
print(source, firmware)
PY
)

LOCAL_SHA="$(git rev-parse HEAD)"
if [[ "$LOCAL_SHA" != "$SOURCE_SHA" ]]; then
  echo "STOP: local checkout does not match candidate source." >&2
  echo "Local:     $LOCAL_SHA" >&2
  echo "Candidate: $SOURCE_SHA" >&2
  exit 22
fi

echo "PASS: candidate identity resolved from artifact"
echo "Source SHA: $SOURCE_SHA"
echo "Firmware SHA-256: $FIRMWARE_SHA"

bash scripts/flash_os12_ci_candidate_macos.sh \
  --candidate-dir "$WORK_DIR" \
  --expect-source-sha "$SOURCE_SHA" \
  --expect-firmware-sha256 "$FIRMWARE_SHA" \
  --confirm-printer-idle \
  --full-backup \
  --base-url "$BASE_URL"

echo
echo "=== Exact post-install source check ==="
RUNNING_SHA="$(curl -fsS --max-time 10 "$BASE_URL/os12/update/status" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("runningSourceCommit",""))')"
if [[ "$RUNNING_SHA" != "$SOURCE_SHA" ]]; then
  echo "FAIL: installed runtime source mismatch: $RUNNING_SHA != $SOURCE_SHA" >&2
  exit 30
fi
echo "PASS: runningSourceCommit=$RUNNING_SHA"

echo
echo "=== Unattended whole-device acceptance ==="
python3 scripts/accept_os12_unattended.py \
  --base-url "$BASE_URL" \
  --expect-source-sha "$SOURCE_SHA"

cat <<EOF

OS12 EXACT-CANDIDATE INSTALL + UNATTENDED ACCEPTANCE COMPLETE
Source SHA: $SOURCE_SHA
Firmware SHA-256: $FIRMWARE_SHA

This proves guarded exact-candidate installation plus unattended objective acceptance.
It does not convert LCD appearance, finger-touch comfort, acoustic quality, or
recovery/rollback into automated physical truth.
EOF
