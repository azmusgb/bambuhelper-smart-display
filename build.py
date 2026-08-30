#!/usr/bin/env python3
from pathlib import Path
import hashlib
import json
import shutil

root = Path(__file__).resolve().parent
dist = root / "dist"
if dist.exists():
    shutil.rmtree(dist)
dist.mkdir()

for name in ["index.html", "styles.css", "app.js", "release.json"]:
    shutil.copy2(root / name, dist / name)

release = json.loads((root / "release.json").read_text())
profile = release["profiles"]["smart-display"]
source = root / profile["file"]
if not source.is_file():
    raise SystemExit(f"missing verified firmware asset: {source}")

raw = source.read_bytes()
actual = hashlib.sha256(raw).hexdigest()
if len(raw) != profile["size"]:
    raise SystemExit(f"firmware size mismatch: {len(raw)} != {profile['size']}")
if actual != profile["sha256"]:
    raise SystemExit(f"firmware SHA mismatch: {actual}")

output = dist / profile["file"]
output.parent.mkdir(parents=True, exist_ok=True)
shutil.copy2(source, output)
print("Verified and published", output.relative_to(dist), len(raw), actual)
