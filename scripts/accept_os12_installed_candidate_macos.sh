#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="${ROOT:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
BASE_URL="${WORKSHOP_OS_URL:-http://10.0.0.124}"
ARTIFACT_ZIP=""
EXERCISE_RECOVERY=0
CONFIRM_IDLE=0

usage() {
  cat <<'EOF'
Usage:
  bash scripts/accept_os12_installed_candidate_macos.sh \
    --artifact-zip ~/Downloads/os12-ux-ws350-<sha>.zip \
    [--base-url http://10.0.0.124] \
    [--exercise-recovery --confirm-printer-idle]

Runs the complete machine-verifiable acceptance set against an already-installed
exact CI candidate. No local firmware rebuild and no OTA install are performed.

Automatic evidence:
  - exact runtime source identity from candidate.json
  - unattended whole-device acceptance
  - complete 15-view 480x320 capture
  - cross-evidence validation
  - optional same-state full-image recovery round-trip at 0x0

Sensory LCD/touch/audio/microphone observations remain outside automation.
EOF
}

while (( $# )); do
  case "$1" in
    --artifact-zip) shift; ARTIFACT_ZIP="${1:-}" ;;
    --base-url) shift; BASE_URL="${1:-}" ;;
    --exercise-recovery) EXERCISE_RECOVERY=1 ;;
    --confirm-printer-idle) CONFIRM_IDLE=1 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "ERROR: unknown argument: $1" >&2; usage >&2; exit 64 ;;
  esac
  shift
done

[[ -n "$ARTIFACT_ZIP" ]] || { echo "ERROR: --artifact-zip is required" >&2; exit 64; }
[[ -s "$ARTIFACT_ZIP" ]] || { echo "ERROR: artifact ZIP missing: $ARTIFACT_ZIP" >&2; exit 64; }
if [[ "$EXERCISE_RECOVERY" -eq 1 && "$CONFIRM_IDLE" -ne 1 ]]; then
  echo "ERROR: --confirm-printer-idle is required with --exercise-recovery" >&2
  exit 64
fi

cd "$ROOT"
[[ -d .git ]] || { echo "ERROR: not inside Workshop OS repository" >&2; exit 2; }

WORK_DIR="$(mktemp -d "${TMPDIR:-/tmp}/os12-installed-candidate.XXXXXX")"
cleanup(){ rm -rf "$WORK_DIR"; }
trap cleanup EXIT

unzip -q "$ARTIFACT_ZIP" -d "$WORK_DIR"
for f in candidate.json SHA256SUMS.txt firmware.bin partitions.bin; do
  [[ -s "$WORK_DIR/$f" ]] || { echo "ERROR: artifact missing $f" >&2; exit 24; }
done

read -r SOURCE_SHA FIRMWARE_SHA < <(
python3 - "$WORK_DIR/candidate.json" "$WORK_DIR/firmware.bin" "$WORK_DIR/SHA256SUMS.txt" <<'PY'
import hashlib, json, re, sys
meta_path, firmware_path, sums_path = sys.argv[1:]
meta=json.load(open(meta_path, encoding="utf-8"))
source=str(meta.get("sourceSha","")).lower()
firmware=str(meta.get("firmwareSha256","")).lower()
if not re.fullmatch(r"[0-9a-f]{40}",source):
    raise SystemExit("FAIL: candidate sourceSha invalid")
if not re.fullmatch(r"[0-9a-f]{64}",firmware):
    raise SystemExit("FAIL: candidate firmwareSha256 invalid")
if meta.get("artifactRole")!="physical-acceptance-candidate":
    raise SystemExit("FAIL: artifact role is not physical-acceptance-candidate")
if meta.get("candidateAuthority")!="os12-ux-architecture":
    raise SystemExit("FAIL: candidate authority is not os12-ux-architecture")
actual=hashlib.sha256(open(firmware_path,"rb").read()).hexdigest()
if actual != firmware:
    raise SystemExit("FAIL: firmware.bin hash does not match candidate.json")
sums=set(open(sums_path,encoding="utf-8").read().splitlines())
if f"{firmware}  firmware.bin" not in sums:
    raise SystemExit("FAIL: SHA256SUMS.txt does not attest firmware.bin")
print(source, firmware)
PY
)

echo "PASS: exact CI candidate artifact verified"
echo "Source SHA: $SOURCE_SHA"
echo "Firmware SHA-256: $FIRMWARE_SHA"

RUNNING_SHA="$(curl -fsS --max-time 10 "$BASE_URL/os12/update/status" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("runningSourceCommit",""))')"
if [[ "$RUNNING_SHA" != "$SOURCE_SHA" ]]; then
  echo "FAIL: installed runtime source mismatch: $RUNNING_SHA != $SOURCE_SHA" >&2
  exit 30
fi
echo "PASS: runningSourceCommit=$RUNNING_SHA"

STAMP="$(date +%Y%m%d-%H%M%S)"
EVIDENCE_DIR="${WS350_ACCEPTANCE_EVIDENCE_DIR:-$HOME/Downloads/workshop-os12-auto-acceptance-$STAMP}"
mkdir -p "$EVIDENCE_DIR"

echo
echo "=== Unattended whole-device acceptance ==="
python3 scripts/accept_os12_unattended.py \
  --base-url "$BASE_URL" \
  --expect-source-sha "$SOURCE_SHA" \
  --output "$EVIDENCE_DIR/unattended.json"

echo
echo "=== Unattended 15-view framebuffer capture ==="
python3 scripts/capture_os12_views_unattended.py \
  --base-url "$BASE_URL" \
  --expect-source-sha "$SOURCE_SHA" \
  --output-dir "$EVIDENCE_DIR/view-capture"

if [[ "$EXERCISE_RECOVERY" -eq 1 ]]; then
  echo
  echo "=== Same-state full-image recovery round-trip ==="
  RECOVERY_DIR="$EVIDENCE_DIR/recovery-roundtrip"
  WS350_RECOVERY_EVIDENCE_DIR="$RECOVERY_DIR" \
    bash scripts/accept_os12_recovery_roundtrip_macos.sh \
      --artifact-zip "$ARTIFACT_ZIP" \
      --confirm-printer-idle \
      --exercise \
      --base-url "$BASE_URL"
fi

echo
echo "=== Automatic evidence-bundle validation ==="
python3 scripts/validate_os12_automatic_candidate.py \
  --unattended "$EVIDENCE_DIR/unattended.json" \
  --capture-manifest "$EVIDENCE_DIR/view-capture/manifest.json" \
  --expect-source-sha "$SOURCE_SHA" \
  --expect-firmware-sha256 "$FIRMWARE_SHA" \
  --output "$EVIDENCE_DIR/automatic-validation.json"

cat <<EOF

OS12 INSTALLED-CANDIDATE AUTOMATIC VALIDATION COMPLETE
Source SHA: $SOURCE_SHA
Firmware SHA-256: $FIRMWARE_SHA
Evidence bundle: $EVIDENCE_DIR
Recovery exercised: $([[ "$EXERCISE_RECOVERY" -eq 1 ]] && echo YES || echo NO)

Automatic machine-verifiable validation: PASS
Sensory physical acceptance: PENDING
EOF
