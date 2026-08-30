#!/usr/bin/env python3
from pathlib import Path
import hashlib,json,shutil
root=Path(__file__).resolve().parent
dist=root/'dist'
if dist.exists(): shutil.rmtree(dist)
dist.mkdir()
for name in ['index.html','styles.css','app.js','release.json']: shutil.copy2(root/name,dist/name)
release=json.loads((root/'release.json').read_text())
assert release['release']=='production-rc-v7'
assert release['board']['id']=='ws_lcd_350'
for profile_id,p in release['profiles'].items():
    source=root/p['file']
    raw=source.read_bytes()
    actual=hashlib.sha256(raw).hexdigest()
    if len(raw)!=p['size']: raise SystemExit(f"{profile_id} size mismatch")
    if actual!=p['sha256']: raise SystemExit(f"{profile_id} SHA mismatch: {actual}")
    output=dist/p['file']; output.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(source,output)
    print('Verified and published',profile_id,len(raw),actual)
