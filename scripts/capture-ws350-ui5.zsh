#!/bin/zsh
set -euo pipefail

if [ "$#" -lt 1 ]; then
  echo "Usage: $0 <device-host-or-ip>"
  exit 2
fi
HOST="$1"
BASE="http://$HOST"
STAMP="$(date '+%Y%m%d-%H%M%S')"
OUT="$HOME/Desktop/Workshop-OS-UI5-Capture-$STAMP"
COOKIE="$(mktemp -t workshop-ui5-cookie)"
RAW_PPM="$(mktemp -t workshop-ui5-frame)"
CATALOG="$OUT/views.json"
LOGIN_REQUIRED=0
chmod 600 "$COOKIE" "$RAW_PPM"

cleanup(){ stty echo 2>/dev/null || true; unset CODE 2>/dev/null || true; rm -f "$COOKIE" "$RAW_PPM"; }
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
mkdir -p "$OUT/png" "$OUT/ppm" "$OUT/state"

# RC5 physical-test builds intentionally allow station-LAN access without the
# boot code. Secure follow-up builds still work: detect the redirect and ask for
# the code only when the device actually requires it.
HTTP="$(curl -sS -o "$CATALOG" -w '%{http_code}' "$BASE/hub/views" || true)"
AUTH=()
if [ "$HTTP" != "200" ]; then
  LOGIN_REQUIRED=1
  printf "Portal code: "
  stty -echo
  IFS= read -r CODE
  stty echo
  printf "\n"
  CODE="$(printf '%s' "$CODE" | tr -cd '[:alnum:]' | tr '[:lower:]' '[:upper:]')"
  if [ "${#CODE}" -ne 10 ]; then echo "ERROR: portal code must normalize to 10 characters."; exit 1; fi
  LOGIN_HTTP="$({ printf '%s' "$CODE" | curl -sS -X POST -c "$COOKIE" -o "$OUT/.login" -w '%{http_code}' --data-urlencode 'code@-' "$BASE/login"; } || true)"
  unset CODE
  if [ "$LOGIN_HTTP" != "303" ]; then echo "LOGIN FAILED - HTTP $LOGIN_HTTP"; cat "$OUT/.login" 2>/dev/null || true; exit 1; fi
  AUTH=(-b "$COOKIE")
  curl -fsS "${AUTH[@]}" "$BASE/hub/views" > "$CATALOG"
  echo "ACCESS: AUTHENTICATED"
else
  echo "ACCESS: OPEN TEST LAN (NO CODE)"
fi

curl -fsS "${AUTH[@]}" "$BASE/recovery/status" > "$OUT/state/recovery-status.json" || true
curl -fsS "${AUTH[@]}" "$BASE/hardware/health?slot=0" > "$OUT/state/hardware-health.json" || true
curl -fsS "${AUTH[@]}" "$BASE/status?slot=0" > "$OUT/state/printer-status-slot0.json" || true

cat > "$OUT/ppm_to_png.py" <<'PY'
#!/usr/bin/env python3
from pathlib import Path
import binascii, hashlib, struct, sys, zlib
src, ppm_dst, png_dst, view_id, secure = map(str, sys.argv[1:6])
raw=Path(src).read_bytes()
lines=raw.split(b'\n',3)
if len(lines)<4 or lines[0].strip()!=b'P6': raise SystemExit('Not P6 PPM')
dims=lines[1].split(); w,h=map(int,dims); maxv=int(lines[2]); rgb=bytearray(lines[3])
if (w,h)!=(480,320): raise SystemExit(f'Expected 480x320, got {w}x{h}')
if maxv!=255 or len(rgb)!=w*h*3: raise SystemExit('Invalid framebuffer payload')
# Secure System captures may expose the rotating code. Redact the lower access
# region before anything is persisted. Test/no-code builds contain no secret.
if secure=='1' and view_id=='system':
    x0,y0,x1,y1=324,190,472,252
    fill=(21,30,40)
    for y in range(y0,y1):
        row=y*w*3
        for x in range(x0,x1):
            i=row+x*3; rgb[i:i+3]=bytes(fill)
# Basic blank-frame rejection catches wrong renderer/failed draw paths.
sample=set()
for y in range(0,h,16):
    for x in range(0,w,16):
        i=(y*w+x)*3; sample.add(bytes(rgb[i:i+3]))
if len(sample)<4: raise SystemExit(f'Frame appears blank/unrendered: {len(sample)} sampled colors')
header=f'P6\n{w} {h}\n255\n'.encode(); retained=header+rgb; Path(ppm_dst).write_bytes(retained)
def chunk(t,d): return struct.pack('>I',len(d))+t+d+struct.pack('>I',binascii.crc32(t+d)&0xffffffff)
scan=bytearray(); row=w*3
for y in range(h): scan.append(0); scan.extend(rgb[y*row:(y+1)*row])
png=bytearray(b'\x89PNG\r\n\x1a\n'); png+=chunk(b'IHDR',struct.pack('>IIBBBBB',w,h,8,2,0,0,0)); png+=chunk(b'IDAT',zlib.compress(bytes(scan),9)); png+=chunk(b'IEND',b''); Path(png_dst).write_bytes(png)
print(hashlib.sha256(retained).hexdigest())
PY
chmod +x "$OUT/ppm_to_png.py"

printf 'index,id,label,group,fingerprint,sha256,png,ppm\n' > "$OUT/manifest.csv"
python3 - "$CATALOG" <<'PY' > "$OUT/view-list.tsv"
import json,sys
with open(sys.argv[1],encoding='utf-8') as f: data=json.load(f)
for i,v in enumerate(data['views'],1): print(f"{i}\t{v['id']}\t{v['label']}\t{v['group']}")
PY

fingerprint(){
  case "$1" in
    home*) echo UI5-H;; printer*) echo UI5-P;; workshop*) echo UI5-W;; system*) echo UI5-S;; *) echo UI5-M;; esac
}

while IFS=$'\t' read -r IDX ID LABEL GROUP; do
  NUM="$(printf '%02d' "$IDX")"; SAFE_ID="${ID//[^A-Za-z0-9_-]/_}"; PPM="$OUT/ppm/$NUM-$SAFE_ID.ppm"; PNG="$OUT/png/$NUM-$SAFE_ID.png"
  echo "[$NUM] $GROUP / $LABEL"
  SHOW_HTTP="$(curl -sS "${AUTH[@]}" -H 'X-BambuHelper-Client: 1' -X POST --data-urlencode "page=$ID" -o "$OUT/.show" -w '%{http_code}' "$BASE/hub/show" || true)"
  if [ "$SHOW_HTTP" != "200" ]; then echo "SHOW FAILED - HTTP $SHOW_HTTP"; cat "$OUT/.show" 2>/dev/null || true; exit 1; fi
  curl -fsS "${AUTH[@]}" "$BASE/hub/frame.ppm" -o "$RAW_PPM"
  SHA="$(python3 "$OUT/ppm_to_png.py" "$RAW_PPM" "$PPM" "$PNG" "$ID" "$LOGIN_REQUIRED")"
  : > "$RAW_PPM"
  FP="$(fingerprint "$ID")"
  QLABEL="${LABEL//\"/\"\"}"; QGROUP="${GROUP//\"/\"\"}"
  printf '%s,%s,"%s","%s",%s,%s,png/%s.png,ppm/%s.ppm\n' "$NUM" "$ID" "$QLABEL" "$QGROUP" "$FP" "$SHA" "$NUM-$SAFE_ID" "$NUM-$SAFE_ID" >> "$OUT/manifest.csv"
done < "$OUT/view-list.tsv"

curl -sS "${AUTH[@]}" -H 'X-BambuHelper-Client: 1' -X POST --data-urlencode 'page=home' "$BASE/hub/show" >/dev/null || true
rm -f "$OUT/.show" "$OUT/.login" "$OUT/view-list.tsv"
cat > "$OUT/ACCEPTANCE.txt" <<EOF2
Workshop OS UI5 physical capture
Expected display: 480x320
Expected visible renderer fingerprints: UI5-H / UI5-P / UI5-W / UI5-M / UI5-S
Login required: $LOGIN_REQUIRED
Review every PNG for clipping, hierarchy, touch/visual alignment, semantic state, and the expected fingerprint.
Automated build evidence does not constitute physical acceptance.
EOF2
ZIP="$HOME/Desktop/Workshop-OS-UI5-Capture-$STAMP.zip"
(cd "$HOME/Desktop" && /usr/bin/zip -qr "$(basename "$ZIP")" "$(basename "$OUT")")
echo "CAPTURE COMPLETE"
echo "Folder: $OUT"
echo "ZIP:    $ZIP"
echo "Frames: $(find "$OUT/png" -type f -name '*.png' | wc -l | tr -d ' ')"
