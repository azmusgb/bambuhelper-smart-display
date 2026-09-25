#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="${ROOT:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
BASE_URL="${WORKSHOP_OS_URL:-http://10.0.0.124}"
ARTIFACT_ZIP=""
OUTPUT_DIR=""

usage() {
  cat <<'EOF'
Usage:
  bash scripts/collect_os12_candidate_evidence_macos.sh \
    --artifact-zip ~/Downloads/os12-ux-ws350-<sha>.zip \
    [--base-url http://10.0.0.124] \
    [--output-dir ~/Downloads/workshop-os12-evidence-...]

Purpose:
  Collect and verify automatic evidence from an already-installed exact WS350
  candidate without flashing, erasing, backing up, or writing device flash.

The collector:
  1. validates candidate artifact metadata and internal firmware/partition hashes;
  2. records the collector tooling source SHA separately from candidate firmware;
  3. requires the live device source SHA to equal the candidate artifact source;
  4. runs unattended runtime/media/native-view validation;
  5. captures settled 15-view 480x320 framebuffer evidence;
  6. validates retained PPM/PNG bytes and cross-view isolation;
  7. builds a tamper-evident evidence index and ZIP;
  8. re-opens that ZIP and verifies every indexed byte/hash offline.

This does not establish LCD panel quality, finger-touch feel, speaker quality,
microphone intelligibility, accepted state, or stable state.
EOF
}

while (( $# )); do
  case "$1" in
    --artifact-zip) shift; ARTIFACT_ZIP="${1:-}" ;;
    --base-url) shift; BASE_URL="${1:-}" ;;
    --output-dir) shift; OUTPUT_DIR="${1:-}" ;;
    -h|--help) usage; exit 0 ;;
    *) echo "ERROR: unknown argument: $1" >&2; usage >&2; exit 64 ;;
  esac
  shift
done

[[ -n "$ARTIFACT_ZIP" ]] || { echo "ERROR: --artifact-zip is required" >&2; exit 64; }
[[ -s "$ARTIFACT_ZIP" ]] || { echo "ERROR: artifact zip missing: $ARTIFACT_ZIP" >&2; exit 64; }

cd "$ROOT"
[[ -d .git ]] || { echo "ERROR: not inside Workshop OS repository" >&2; exit 2; }
if ! git diff --quiet || ! git diff --cached --quiet; then
  echo "ERROR: tracked checkout changes are present; refusing unaudited evidence collection." >&2
  exit 3
fi

COLLECTOR_SHA="$(git rev-parse HEAD)"
WORK_DIR="$(mktemp -d "${TMPDIR:-/tmp}/os12-evidence-artifact.XXXXXX")"
cleanup(){ rm -rf "$WORK_DIR"; }
trap cleanup EXIT
unzip -q "$ARTIFACT_ZIP" -d "$WORK_DIR"

for f in candidate.json SHA256SUMS.txt firmware.bin partitions.bin; do
  [[ -s "$WORK_DIR/$f" ]] || { echo "ERROR: artifact missing $f" >&2; exit 24; }
done

read -r SOURCE_SHA FIRMWARE_SHA PARTITION_SHA < <(
python3 - "$WORK_DIR" <<'PY'
import hashlib, json, pathlib, re, sys
root=pathlib.Path(sys.argv[1])
meta=json.loads((root/"candidate.json").read_text(encoding="utf-8"))
source=str(meta.get("sourceSha","")).lower()
firmware=str(meta.get("firmwareSha256","")).lower()
partition=str(meta.get("partitionSha256","")).lower()
if not re.fullmatch(r"[0-9a-f]{40}",source):
    raise SystemExit("FAIL: candidate sourceSha invalid")
for label,value in (("firmwareSha256",firmware),("partitionSha256",partition)):
    if not re.fullmatch(r"[0-9a-f]{64}",value):
        raise SystemExit(f"FAIL: candidate {label} invalid")
if meta.get("artifactRole")!="physical-acceptance-candidate":
    raise SystemExit("FAIL: artifactRole is not physical-acceptance-candidate")
if meta.get("candidateAuthority")!="os12-ux-architecture":
    raise SystemExit("FAIL: candidateAuthority is not os12-ux-architecture")
if meta.get("accepted") is not False or meta.get("stable") is not False:
    raise SystemExit("FAIL: candidate artifact improperly claims accepted/stable")

def digest(path):
    h=hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()

actual_fw=digest(root/"firmware.bin")
actual_part=digest(root/"partitions.bin")
if actual_fw != firmware:
    raise SystemExit("FAIL: firmware.bin hash does not match candidate.json")
if actual_part != partition:
    raise SystemExit("FAIL: partitions.bin hash does not match candidate.json")
sums=set((root/"SHA256SUMS.txt").read_text(encoding="utf-8").splitlines())
if f"{firmware}  firmware.bin" not in sums:
    raise SystemExit("FAIL: SHA256SUMS.txt does not attest firmware.bin")
if f"{partition}  partitions.bin" not in sums:
    raise SystemExit("FAIL: SHA256SUMS.txt does not attest partitions.bin")
print(source, firmware, partition)
PY
)

RUNNING_SHA="$(curl -fsS --max-time 10 "$BASE_URL/os12/update/status" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("runningSourceCommit",""))')"
if [[ "$RUNNING_SHA" != "$SOURCE_SHA" ]]; then
  echo "STOP: running device source does not match candidate artifact." >&2
  echo "Running:   $RUNNING_SHA" >&2
  echo "Candidate: $SOURCE_SHA" >&2
  exit 30
fi

STAMP="$(date +%Y%m%d-%H%M%S)"
if [[ -n "$OUTPUT_DIR" ]]; then
  EVIDENCE_DIR="$(cd "$(dirname "$OUTPUT_DIR")" && pwd)/$(basename "$OUTPUT_DIR")"
else
  EVIDENCE_DIR="$HOME/Downloads/workshop-os12-hardened-evidence-$STAMP"
fi
[[ ! -e "$EVIDENCE_DIR" ]] || { echo "ERROR: evidence directory already exists: $EVIDENCE_DIR" >&2; exit 31; }
mkdir -p "$EVIDENCE_DIR"

python3 - "$EVIDENCE_DIR/collection-context.json" "$SOURCE_SHA" "$FIRMWARE_SHA" "$PARTITION_SHA" "$COLLECTOR_SHA" "$BASE_URL" "$ARTIFACT_ZIP" <<'PY'
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
    "deviceFlashMutationPerformed":False,
    "runtimeDiagnosticMutationsPerformed":True,
    "collectionMode":"no-flash-runtime-evidence",
    "accepted":False,
    "stable":False,
}
pathlib.Path(out).write_text(json.dumps(payload,indent=2,sort_keys=True)+"\n",encoding="utf-8")
PY

echo "=== OS12 no-flash automatic evidence collection ==="
echo "Candidate source:  $SOURCE_SHA"
echo "Firmware SHA-256:  $FIRMWARE_SHA"
echo "Partition SHA-256: $PARTITION_SHA"
echo "Collector source:  $COLLECTOR_SHA"
echo "Running source:    $RUNNING_SHA"
echo "Device mutation:   NO"

python3 scripts/accept_os12_unattended.py \
  --base-url "$BASE_URL" \
  --expect-source-sha "$SOURCE_SHA" \
  --output "$EVIDENCE_DIR/unattended.json"

python3 scripts/capture_os12_views_unattended.py \
  --base-url "$BASE_URL" \
  --expect-source-sha "$SOURCE_SHA" \
  --output-dir "$EVIDENCE_DIR/view-capture"

python3 scripts/validate_os12_automatic_candidate.py \
  --unattended "$EVIDENCE_DIR/unattended.json" \
  --capture-manifest "$EVIDENCE_DIR/view-capture/manifest.json" \
  --expect-source-sha "$SOURCE_SHA" \
  --expect-firmware-sha256 "$FIRMWARE_SHA" \
  --output "$EVIDENCE_DIR/automatic-validation.json"

FINAL_JSON="$(python3 scripts/finalize_os12_evidence_bundle.py \
  --evidence-dir "$EVIDENCE_DIR" \
  --source-sha "$SOURCE_SHA" \
  --firmware-sha256 "$FIRMWARE_SHA" \
  --artifact-zip "$ARTIFACT_ZIP" \
  --collector-source-sha "$COLLECTOR_SHA")"

read -r BUNDLE_PATH BUNDLE_SHA < <(
python3 - "$FINAL_JSON" <<'PY'
import json,sys
d=json.loads(sys.argv[1])
print(d["bundleZip"], d["bundleSha256"])
PY
)

python3 scripts/verify_os12_evidence_bundle.py \
  --bundle "$BUNDLE_PATH" \
  --expect-bundle-sha256 "$BUNDLE_SHA"

cat <<EOF

OS12 NO-FLASH AUTOMATIC EVIDENCE COLLECTION: PASS
Candidate source: $SOURCE_SHA
Collector source: $COLLECTOR_SHA
Evidence folder:  $EVIDENCE_DIR
Bundle ZIP:       $BUNDLE_PATH
Bundle SHA-256:   $BUNDLE_SHA

Automatic evidence: PASS
Offline bundle verification: PASS
Physical sensory acceptance: PENDING
Device flash mutation: NO
EOF
