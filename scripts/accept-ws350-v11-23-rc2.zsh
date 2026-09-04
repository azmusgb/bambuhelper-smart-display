#!/bin/zsh
set -euo pipefail

HOST="${1:-10.0.0.124}"
BASE="http://${HOST}"
BASELINE="$(mktemp -t bambu-v1123rc2-baseline)"
CHECK="$(mktemp -t bambu-v1123rc2-check)"
STATUS_FILE="$(mktemp -t bambu-v1123rc2-status)"
VIEWS="$(mktemp -t bambu-v1123rc2-views)"
chmod 600 "$BASELINE" "$CHECK" "$STATUS_FILE" "$VIEWS"

cleanup() {
  rm -f "$BASELINE" "$CHECK" "$STATUS_FILE" "$VIEWS"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

fetch_settings() {
  local out="$1"
  local http_status
  http_status="$(curl -sS -o "$out" -w '%{http_code}' "$BASE/settings/export")"
  if [[ "$http_status" != "200" ]]; then
    echo "FAIL: unauthenticated trusted-LAN settings export returned HTTP $http_status" >&2
    exit 1
  fi
}

fetch_status() {
  local http_status
  http_status="$(curl -sS -o "$STATUS_FILE" -w '%{http_code}' "$BASE/recovery/status")"
  if [[ "$http_status" != "200" ]]; then
    echo "FAIL: no-code trusted-LAN recovery/status returned HTTP $http_status" >&2
    exit 1
  fi
}

show_baseline() {
  python3 - "$1" <<'PY'
import json, sys
p=sys.argv[1]
d=json.load(open(p))
n=d.get('network',{})
disp=d.get('display',{})
print(f"  DHCP:       {n.get('useDHCP')}")
print(f"  Static IP:  {n.get('staticIP')!r}")
print(f"  Gateway:    {n.get('gateway')!r}")
print(f"  Subnet:     {n.get('subnet')!r}")
print(f"  DNS:        {n.get('dns')!r}")
print(f"  Timezone:   {n.get('timezoneStr')}")
print(f"  Rotation:   R{disp.get('rotation')}")
PY
}

compare_fields() {
  python3 - "$1" "$2" <<'PY'
import json, sys
a=json.load(open(sys.argv[1])); b=json.load(open(sys.argv[2]))
keys=[
 ('network','useDHCP'),('network','staticIP'),('network','gateway'),
 ('network','subnet'),('network','dns'),('network','timezoneIndex'),
 ('network','timezoneStr'),('display','rotation')
]
bad=[]
for section,key in keys:
    av=a.get(section,{}).get(key); bv=b.get(section,{}).get(key)
    if av != bv: bad.append((section,key,av,bv))
if bad:
    for section,key,av,bv in bad:
        print(f"CHANGED: {section}.{key}: {av!r} -> {bv!r}")
    raise SystemExit(1)
print('Relevant persisted settings match baseline.')
PY
}

echo "============================================================"
echo " Workshop OS v11.23 RC2 Physical Acceptance Helper"
echo "============================================================"
echo "Target: $BASE"
echo

echo "[1/5] Verify portal-code-free trusted-LAN access"
fetch_status
fetch_settings "$BASELINE"
VIEWS_HTTP="$(curl -sS -o "$VIEWS" -w '%{http_code}' "$BASE/hub/views")"
[[ "$VIEWS_HTTP" == "200" ]] || { echo "FAIL: /hub/views returned HTTP $VIEWS_HTTP"; exit 1; }
python3 - "$STATUS_FILE" "$VIEWS" <<'PY'
import json, sys
s=json.load(open(sys.argv[1])); v=json.load(open(sys.argv[2]))
print('  build:          ',s.get('build'))
print('  safeMode:       ',s.get('safeMode'))
print('  webReady:       ',s.get('webReady'))
print('  touchResponsive:',s.get('touchResponsive'))
print('  capture views:  ',len(v.get('views',[])))
if s.get('build') != 'Smart Home v11.23 Network Locale Layout RC2':
    raise SystemExit('FAIL: device is not running v11.23 RC2')
if s.get('safeMode') is not False or s.get('webReady') is not True or s.get('touchResponsive') is not True:
    raise SystemExit('FAIL: device health precondition failed')
if len(v.get('views',[])) < 32:
    raise SystemExit('FAIL: capture catalog has fewer than 32 views')
print('NO-CODE TRUSTED-LAN ACCESS: PASS')
PY

echo
echo "Baseline:"
show_baseline "$BASELINE"

echo
echo "[2/5] TIMEZONE UX"
echo "On the WS350 open Network -> Time & Locale."
echo "Use the visible NEXT timezone button once, confirm the clock/timezone changes,"
echo "then use the visible PREV button to restore the original timezone."
printf "Press ENTER after it is restored: "
read -r _
fetch_settings "$CHECK"
python3 - "$BASELINE" "$CHECK" <<'PY'
import json, sys
a=json.load(open(sys.argv[1])); b=json.load(open(sys.argv[2]))
for k in ('timezoneIndex','timezoneStr'):
    if a['network'].get(k) != b['network'].get(k):
        raise SystemExit(f'FAIL: timezone not restored: {k}')
print('TIMEZONE UX + RESTORE: PASS')
PY

echo
echo "[3/5] STAGED ADDRESS UX — NO APPLY"
echo "On the WS350 open Network -> Address Editor."
echo "Select an octet, change it with a visible +/- button, then open Review."
echo "Confirm STAGED / NOT APPLIED is obvious. DO NOT hold Apply."
echo "Use DISCARD, then return to the Network page."
printf "Press ENTER after DISCARD: "
read -r _
fetch_settings "$CHECK"
python3 - "$BASELINE" "$CHECK" <<'PY'
import json, sys
a=json.load(open(sys.argv[1])); b=json.load(open(sys.argv[2]))
keys=('useDHCP','staticIP','gateway','subnet','dns')
bad=[k for k in keys if a['network'].get(k) != b['network'].get(k)]
if bad:
    raise SystemExit('FAIL: persisted network settings changed before Apply: '+', '.join(bad))
print('STAGED-NO-APPLY + DISCARD: PASS')
PY

echo
echo "[4/5] ROTATION PREVIEW + GUARDED COMMIT + TOUCH"
echo "On the WS350 open Display -> Extras and TAP the ROTATION card."
echo "A dedicated ROTATION preview should open; the physical orientation must not change."
echo "Use NEXT once. PREVIEW should change while CURRENT and the physical orientation stay unchanged."
echo "Short-tap HOLD TO COMMIT ROTATION once. It must NOT commit."
printf "Did preview/short-tap leave the physical orientation unchanged? [y/N]: "
read -r PREVIEW_OK
case "$PREVIEW_OK" in
  y|Y|yes|YES) ;;
  *) echo "FAIL: rotation preview/short-tap guard not confirmed"; exit 1 ;;
esac

echo "Now HOLD TO COMMIT ROTATION deliberately."
echo "Confirm the screen rotates and touch targets remain aligned."
echo "Repeat the preview/commit flow as needed until the original rotation is restored."
printf "Did touch remain correctly aligned and was the original rotation restored? [y/N]: "
read -r TOUCH_OK
case "$TOUCH_OK" in
  y|Y|yes|YES) ;;
  *) echo "FAIL: touch alignment/restoration not confirmed"; exit 1 ;;
esac
fetch_settings "$CHECK"
python3 - "$BASELINE" "$CHECK" <<'PY'
import json, sys
a=json.load(open(sys.argv[1])); b=json.load(open(sys.argv[2]))
av=a['display'].get('rotation'); bv=b['display'].get('rotation')
if av != bv:
    raise SystemExit(f'FAIL: rotation not restored: R{av} -> R{bv}')
print(f'ROTATION PREVIEW + GUARD + TOUCH + RESTORE: PASS (R{bv})')
PY

echo
echo "[5/5] POST-TEST HEALTH / BASELINE"
fetch_status
fetch_settings "$CHECK"
python3 - "$STATUS_FILE" <<'PY'
import json, sys
d=json.load(open(sys.argv[1]))
if d.get('safeMode') is not False: raise SystemExit('FAIL: safeMode active')
if d.get('webReady') is not True: raise SystemExit('FAIL: webReady false')
if d.get('touchResponsive') is not True: raise SystemExit('FAIL: touchResponsive false')
print('POST-TEST DEVICE HEALTH: PASS')
PY
compare_fields "$BASELINE" "$CHECK"

echo
echo "============================================================"
echo " v11.23 RC2 PHYSICAL ACCEPTANCE CHECKS: PASS"
echo "============================================================"
echo "Portal code: NOT REQUIRED"
echo "Printer commands sent: NONE"
echo "Network Apply executed: NO"
echo "Rotation commit: GUARDED PREVIEW FLOW"
echo "All tested persisted settings: RESTORED"
