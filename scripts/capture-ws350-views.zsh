#!/bin/zsh
set -euo pipefail

HOST="${1:-10.0.0.124}"
BASE="http://$HOST"
STAMP="$(date '+%Y%m%d-%H%M%S')"
OUT="$HOME/Desktop/BambuHelper-Visual-Capture-$STAMP"
COOKIE="$(mktemp -t bambu-capture-cookie)"
LOGIN_BODY="$(mktemp -t bambu-capture-login)"
CATALOG="$OUT/views.json"

cleanup() {
  rm -f "$COOKIE" "$LOGIN_BODY"
}
trap cleanup EXIT INT TERM

mkdir -p "$OUT/png" "$OUT/ppm" "$OUT/state"

printf "Portal code: "
stty -echo
IFS= read -r CODE
stty echo
printf "\n"
CODE="$(printf '%s' "$CODE" | tr -cd '[:alnum:]' | tr '[:lower:]' '[:upper:]')"

if [ "${#CODE}" -ne 10 ]; then
  echo "ERROR: portal code must normalize to exactly 10 characters."
  exit 1
fi

HTTP="$({ curl -sS -X POST -c "$COOKIE" -o "$LOGIN_BODY" -w '%{http_code}' \
  --data-urlencode "code=$CODE" "$BASE/login"; } || true)"
if [ "$HTTP" != "303" ]; then
  echo "LOGIN FAILED - HTTP $HTTP"
  cat "$LOGIN_BODY" 2>/dev/null || true
  exit 1
fi

echo "LOGIN OK"

curl -fsS -b "$COOKIE" "$BASE/recovery/status" > "$OUT/state/recovery-status.json"
curl -fsS -b "$COOKIE" "$BASE/hardware/health?slot=0" > "$OUT/state/hardware-health.json"
curl -fsS -b "$COOKIE" "$BASE/status?slot=0" > "$OUT/state/printer-status-slot0.json"
curl -fsS -b "$COOKIE" "$BASE/printer/config?slot=0" > "$OUT/state/printer-config-slot0.json"
curl -fsS -b "$COOKIE" "$BASE/power/stats" > "$OUT/state/power-stats.json"
curl -fsS -b "$COOKIE" "$BASE/hub/views" > "$CATALOG"

cat > "$OUT/ppm_to_png.py" <<'PY'
#!/usr/bin/env python3
from pathlib import Path
import binascii
import struct
import sys
import zlib

src = Path(sys.argv[1])
dst = Path(sys.argv[2])

with src.open('rb') as f:
    magic = f.readline().strip()
    if magic != b'P6':
        raise SystemExit(f'Not P6 PPM: {src}')
    dims = f.readline().strip().split()
    while dims and dims[0].startswith(b'#'):
        dims = f.readline().strip().split()
    w, h = map(int, dims)
    maxv = int(f.readline().strip())
    if maxv != 255:
        raise SystemExit(f'Unsupported max value {maxv}')
    rgb = f.read()

expected = w * h * 3
if len(rgb) != expected:
    raise SystemExit(f'{src}: expected {expected} RGB bytes, got {len(rgb)}')

def chunk(kind: bytes, data: bytes) -> bytes:
    return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', binascii.crc32(kind + data) & 0xffffffff)

scan = bytearray()
row = w * 3
for y in range(h):
    scan.append(0)
    scan.extend(rgb[y * row:(y + 1) * row])

png = bytearray(b'\x89PNG\r\n\x1a\n')
png += chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 2, 0, 0, 0))
png += chunk(b'IDAT', zlib.compress(bytes(scan), 9))
png += chunk(b'IEND', b'')
dst.write_bytes(png)
PY
chmod +x "$OUT/ppm_to_png.py"

printf 'index,id,label,group,png,ppm\n' > "$OUT/manifest.csv"

python3 - "$CATALOG" <<'PY' > "$OUT/view-list.tsv"
import json, sys
with open(sys.argv[1], encoding='utf-8') as f:
    data = json.load(f)
for i, v in enumerate(data['views'], 1):
    print(f"{i}\t{v['id']}\t{v['label']}\t{v['group']}")
PY

while IFS=$'\t' read -r IDX ID LABEL GROUP; do
  NUM="$(printf '%02d' "$IDX")"
  SAFE_ID="${ID//[^A-Za-z0-9_-]/_}"
  PPM="$OUT/ppm/$NUM-$SAFE_ID.ppm"
  PNG="$OUT/png/$NUM-$SAFE_ID.png"

  echo "[$NUM] $GROUP / $LABEL"

  SHOW_HTTP="$({ curl -sS -b "$COOKIE" \
    -H 'X-BambuHelper-Client: 1' \
    -X POST \
    --data-urlencode "page=$ID" \
    -o "$OUT/.show-response" \
    -w '%{http_code}' \
    "$BASE/hub/show"; } || true)"

  if [ "$SHOW_HTTP" != "200" ]; then
    echo "  SHOW FAILED - HTTP $SHOW_HTTP"
    cat "$OUT/.show-response" 2>/dev/null || true
    exit 1
  fi

  curl -fsS -b "$COOKIE" "$BASE/hub/frame.ppm" -o "$PPM"
  python3 "$OUT/ppm_to_png.py" "$PPM" "$PNG"

  QLABEL="${LABEL//\"/\"\"}"
  QGROUP="${GROUP//\"/\"\"}"
  printf '%s,%s,"%s","%s",png/%s.png,ppm/%s.ppm\n' \
    "$NUM" "$ID" "$QLABEL" "$QGROUP" "$NUM-$SAFE_ID" "$NUM-$SAFE_ID" >> "$OUT/manifest.csv"
done < "$OUT/view-list.tsv"

rm -f "$OUT/.show-response"

curl -sS -b "$COOKIE" -H 'X-BambuHelper-Client: 1' -X POST \
  --data-urlencode 'page=home' "$BASE/hub/show" >/dev/null || true

rm -f "$OUT/view-list.tsv"

ZIP="$HOME/Desktop/BambuHelper-Visual-Capture-$STAMP.zip"
(
  cd "$HOME/Desktop"
  /usr/bin/zip -qr "$(basename "$ZIP")" "$(basename "$OUT")"
)

echo
echo "CAPTURE COMPLETE"
echo "Folder: $OUT"
echo "ZIP:    $ZIP"
echo "PNG frames: $(find "$OUT/png" -type f -name '*.png' | wc -l | tr -d ' ')"
