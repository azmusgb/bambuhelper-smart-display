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
  6. runs unattended whole-device acceptance against that exact installed SHA;
  7. captures all 15 required native 480x320 views without prompts;
  8. validates the machine-produced evidence bundle for one exact candidate.

It does not locally rebuild firmware and does not weaken physical/recovery gates.
Sensory observations remain separate because they cannot be established honestly by automation.
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

read -r SOURCE_SHA FIRMWARE_SHA PARTITION_SHA < <(
python3 - "$WORK_DIR/candidate.json" <<'PY'
import json, re, sys
with open(sys.argv[1], "r", encoding="utf-8") as fh:
    d=json.load(fh)
source=str(d.get("sourceSha","")).lower()
firmware=str(d.get("firmwareSha256","")).lower()
partition=str(d.get("partitionSha256","")).lower()
if not re.fullmatch(r"[0-9a-f]{40}",source):
    raise SystemExit("FAIL: candidate sourceSha invalid")
if not re.fullmatch(r"[0-9a-f]{64}",firmware):
    raise SystemExit("FAIL: candidate firmwareSha256 invalid")
if not re.fullmatch(r"[0-9a-f]{64}",partition):
    raise SystemExit("FAIL: candidate partitionSha256 invalid")
if d.get("artifactRole")!="physical-acceptance-candidate":
    raise SystemExit("FAIL: artifact is not a physical-acceptance candidate")
if d.get("candidateAuthority")!="os12-ux-architecture":
    raise SystemExit("FAIL: candidate authority is not os12-ux-architecture")
if d.get("accepted") is not False or d.get("stable") is not False:
    raise SystemExit("FAIL: CI candidate metadata improperly claims accepted/stable")
print(source, firmware, partition)
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

STAMP="$(date +%Y%m%d-%H%M%S)"
EVIDENCE_DIR="${WS350_ACCEPTANCE_EVIDENCE_DIR:-$HOME/Downloads/workshop-os12-auto-acceptance-$STAMP}"
mkdir -p "$EVIDENCE_DIR"

python3 - "$EVIDENCE_DIR/collection-context.json" "$SOURCE_SHA" "$FIRMWARE_SHA" "$PARTITION_SHA" "$LOCAL_SHA" "$BASE_URL" "$ARTIFACT_ZIP" <<'PY'
from datetime import datetime, timezone
import hashlib, json, pathlib, sys
out, source, firmware, partition, collector, base_url, artifact = sys.argv[1:]
artifact_path=pathlib.Path(artifact).expanduser().resolve()
h=hashlib.sha256()
with artifact_path.open("rb") as fh:
    for chunk in iter(lambda: fh.read(1024*1024), b""):
        h.update(chunk)
payload={
    "schemaVersion":1,
    "kind":"workshop-os12-automatic-evidence-collection-context",
    "recordedAt":datetime.now(timezone.utc).isoformat(),
    "candidateSourceSha":source,
    "firmwareSha256":firmware,
    "partitionSha256":partition,
    "collectorSourceSha":collector,
    "baseUrl":base_url,
    "candidateArtifact":{
        "fileName":artifact_path.name,
        "sha256":h.hexdigest(),
        "bytes":artifact_path.stat().st_size,
    },
    "deviceMutationPerformed":True,
    "collectionMode":"install-and-accept",
    "accepted":False,
    "stable":False,
}
pathlib.Path(out).write_text(json.dumps(payload,indent=2,sort_keys=True)+"\n",encoding="utf-8")
PY

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

echo
echo "=== Automatic evidence-bundle validation ==="
python3 scripts/validate_os12_automatic_candidate.py \
  --unattended "$EVIDENCE_DIR/unattended.json" \
  --capture-manifest "$EVIDENCE_DIR/view-capture/manifest.json" \
  --expect-source-sha "$SOURCE_SHA" \
  --expect-firmware-sha256 "$FIRMWARE_SHA" \
  --output "$EVIDENCE_DIR/automatic-validation.json"

echo
echo "=== Finalize and independently verify tamper-evident evidence bundle ==="
FINAL_JSON="$(python3 scripts/finalize_os12_evidence_bundle.py \
  --evidence-dir "$EVIDENCE_DIR" \
  --source-sha "$SOURCE_SHA" \
  --firmware-sha256 "$FIRMWARE_SHA" \
  --artifact-zip "$ARTIFACT_ZIP" \
  --collector-source-sha "$LOCAL_SHA")"
read -r EVIDENCE_INDEX_SHA BUNDLE_PATH BUNDLE_SHA < <(
python3 - "$FINAL_JSON" <<'PY'
import json,sys
d=json.loads(sys.argv[1])
print(d["evidenceIndexSha256"], d["bundleZip"], d["bundleSha256"])
PY
)
python3 scripts/verify_os12_evidence_bundle.py \
  --bundle "$BUNDLE_PATH" \
  --expect-bundle-sha256 "$BUNDLE_SHA"
echo "PASS: evidence index SHA-256=$EVIDENCE_INDEX_SHA"
echo "PASS: bundle ZIP=$BUNDLE_PATH"
echo "PASS: bundle ZIP SHA-256=$BUNDLE_SHA"

cat <<EOF

OS12 EXACT-CANDIDATE INSTALL + AUTOMATIC VALIDATION COMPLETE
Source SHA: $SOURCE_SHA
Firmware SHA-256: $FIRMWARE_SHA
Evidence bundle: $EVIDENCE_DIR

Automatic machine-verifiable validation: PASS
Offline bundle verification: PASS
Tamper-evident evidence bundle: $BUNDLE_PATH
Evidence bundle SHA-256: $BUNDLE_SHA
Sensory physical acceptance: PENDING

The automatic path now includes exact runtime identity, whole-device unattended
acceptance, settled 15-view native framebuffer captures, cross-view stale-content
checks, retained-file hash verification, and a tamper-evident evidence index/ZIP.
It does not fabricate LCD appearance, finger-touch feel,
speaker quality, microphone intelligibility, or recovery/rollback evidence.
EOF
