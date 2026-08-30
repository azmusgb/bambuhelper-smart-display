#!/usr/bin/env python3
from pathlib import Path
import hashlib
import json
import shutil

root = Path(__file__).resolve().parent
dist = root / 'dist'
if dist.exists():
    shutil.rmtree(dist)
dist.mkdir()

for name in ['index.html', 'styles.css', 'app.js', 'release.json']:
    shutil.copy2(root / name, dist / name)

release = json.loads((root / 'release.json').read_text())
assert release['release'] == 'production-rc-v7.1'
assert release['board']['id'] == 'ws_lcd_350'


def verify_and_publish(profile_id, source_path, expected_size, expected_sha, label):
    source = root / source_path
    raw = source.read_bytes()
    actual = hashlib.sha256(raw).hexdigest()
    if len(raw) != expected_size:
        raise SystemExit(f'{profile_id} {label} size mismatch: {len(raw)} != {expected_size}')
    if actual != expected_sha:
        raise SystemExit(f'{profile_id} {label} SHA mismatch: {actual}')
    output = dist / source_path
    output.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, output)
    print('Verified and published', profile_id, label, len(raw), actual)


for profile_id, p in release['profiles'].items():
    verify_and_publish(profile_id, p['file'], p['size'], p['sha256'], 'Full')
    if p.get('otaFile'):
        verify_and_publish(profile_id, p['otaFile'], p['otaSize'], p['otaSha256'], 'OTA')
