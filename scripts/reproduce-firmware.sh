#!/usr/bin/env bash
set -euo pipefail

EXPECTED_SHA=82265502dac6b93356ee2ab3d7c4edcaad47bdd7584be85d24ddef348166d5ac
EXPECTED_SIZE=2207040
UPSTREAM_COMMIT=8cb1cbbb6d3c175af91989e8ebe1bbdcbe848ac4
OUT=firmware/BambuHelper-ws_lcd_350-v3.8.1-Full-smart-display-v6-validated.bin

rm -rf upstream
git clone --quiet https://github.com/Keralots/BambuHelper.git upstream
git -C upstream checkout --quiet "$UPSTREAM_COMMIT"

v1=https://raw.githubusercontent.com/azmusgb/filamentinventory/741a6f0651fb4e20d8e2674f2c0ce726b0d7bdf9/.bambuhelper-validation
v3=https://raw.githubusercontent.com/azmusgb/filamentinventory/07ce909fa7dd485abfc556eaf9addfbbd82e3cb3/.bambuhelper-validation
v6=https://raw.githubusercontent.com/azmusgb/filamentinventory/c1a6cdf389be14b18f26eecefd5c5a62b5d1e7dc/.bambuhelper-validation

curl -fsSL "$v1/installer.zlib.b64" -o /tmp/installer.b64
for n in 0 1 2 3; do curl -fsSL "$v1/device.part$n" -o "/tmp/device.part$n"; done
cat /tmp/device.part{0,1,2,3} > /tmp/device.b64
curl -fsSL "$v3/v2.zlib.b64" -o /tmp/v2.b64
curl -fsSL "$v3/v3.zlib.b64" -o /tmp/v3.b64
curl -fsSL "$v6/v4.zlib.b64" -o /tmp/v4.b64
curl -fsSL "$v6/v5.zlib.b64" -o /tmp/v5.b64
curl -fsSL "$v6/v6.zlib.b64" -o /tmp/v6.b64

python - <<'PY'
from pathlib import Path
import base64, zlib
pairs = [
    ('/tmp/installer.b64', 'apply_installer_evolution.py'),
    ('/tmp/device.b64', 'apply_device_onboarding_evolution.py'),
    ('/tmp/v2.b64', 'apply_resilience_evolution_v2.py'),
    ('/tmp/v3.b64', 'apply_smart_profiles_evolution_v3.py'),
    ('/tmp/v4.b64', 'apply_ws350_remote_dashboard_v4.py'),
    ('/tmp/v5.b64', 'apply_commissioning_evolution_v5.py'),
    ('/tmp/v6.b64', 'apply_smart_display_platform_v6.py'),
]
for src, dst in pairs:
    raw = zlib.decompress(base64.b64decode(Path(src).read_text().strip()))
    Path(dst).write_bytes(raw)
    print(dst, len(raw))
PY

python - <<'PY'
from pathlib import Path
p = Path('apply_smart_profiles_evolution_v3.py')
text = p.read_text(encoding='utf-8')
needle = '"app/profile-account-selection",'
pos = text.find(needle)
if pos >= 0:
    start = text.rfind('    text = replace_once(', 0, pos)
    end = text.find('\n    )', pos)
    if min(start, end) < 0:
        raise SystemExit('v3 repair anchor malformed')
    end += len('\n    )')
    replacement = """    profile_refresh_anchor = '''  updatePrinterOnboarding();\n  refreshPrinterHealth(false);'''\n    profile_refresh_count = text.count(profile_refresh_anchor)\n    if profile_refresh_count < 1:\n        raise PatchError(\n            \"app/profile-context-refresh: expected at least one v2 refresh anchor\"\n        )\n    text = text.replace(\n        profile_refresh_anchor,\n        '''  updatePrinterOnboarding();\n  refreshGaugeProfileUi();\n  refreshPrinterHealth(false);''',\n    )"""
    text = text[:start] + replacement + text[end:]
    p.write_text(text, encoding='utf-8')
PY
python -m py_compile apply_*evolution*.py apply_smart_display_platform_v6.py

python apply_installer_evolution.py --repo upstream --apply
python apply_device_onboarding_evolution.py --repo upstream --apply
python apply_resilience_evolution_v2.py --repo upstream --apply
python apply_smart_profiles_evolution_v3.py --repo upstream --apply
python apply_ws350_remote_dashboard_v4.py --repo upstream --apply
python apply_commissioning_evolution_v5.py --repo upstream --apply
python apply_smart_display_platform_v6.py --repo upstream --apply

node --check upstream/docs/flasher.js
node --check upstream/web/app.js
test -f upstream/src/smart_hub.h
test -f upstream/src/smart_hub.cpp
grep -Fq 'SCREEN_HUB_HOME' upstream/src/display_ui.h
grep -Fq 'smartHubDraw' upstream/src/display_ui.cpp
grep -Fq 'smartHubEnter' upstream/src/main.cpp
grep -Fq 'server.on("/hub/config"' upstream/src/web_server.cpp
grep -Fq 'Smart Display Platform' upstream/include/web_pages.h
grep -Fq 'BOARD_IS_WS350=1' upstream/boards/ws_lcd_350.ini
grep -Fq 'DISPLAY_320x480=1' upstream/boards/ws_lcd_350.ini
grep -Fq 'USE_FT6336=1' upstream/boards/ws_lcd_350.ini

python -m pip install --upgrade platformio
(cd upstream && pio run -e ws_lcd_350)
(cd upstream && pio run -e jc3248w535)
(cd upstream && python merge_bins.py --board ws_lcd_350 --full)

FULL="$(find upstream/firmware -type f -name 'BambuHelper-ws_lcd_350-*-Full.bin' | sort | tail -1)"
test -n "$FULL" && test -f "$FULL"
ACTUAL="$(sha256sum "$FULL" | awk '{print $1}')"
SIZE="$(stat -c%s "$FULL")"
test "$ACTUAL" = "$EXPECTED_SHA"
test "$SIZE" = "$EXPECTED_SIZE"
mkdir -p firmware
cp "$FULL" "$OUT"

cat > firmware-build-report.txt <<EOF
BambuHelper Smart Display production firmware build
=================================================
upstream_commit=$UPSTREAM_COMMIT
target=ws_lcd_350
profile=Smart Display v6
size=$SIZE
sha256=$ACTUAL
shared_layout_regression=jc3248w535_passed
EOF

node --check app.js
python build.py
sha256sum -c <(echo "$EXPECTED_SHA  dist/$OUT")
echo "Verified production firmware: $OUT ($SIZE bytes, $ACTUAL)"
