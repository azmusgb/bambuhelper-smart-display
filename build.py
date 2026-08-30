#!/usr/bin/env python3
from pathlib import Path
import hashlib, json, lzma, shutil

root = Path(__file__).resolve().parent
dist = root / "dist"
if dist.exists():
    shutil.rmtree(dist)
dist.mkdir()

for name in ["index.html", "styles.css", "app.js", "release.json"]:
    shutil.copy2(root / name, dist / name)

(dist / "firmware").mkdir()
raw = lzma.decompress((root / "firmware-source.xz").read_bytes())
expected_sha = "82265502dac6b93356ee2ab3d7c4edcaad47bdd7584be85d24ddef348166d5ac"
actual = hashlib.sha256(raw).hexdigest()
if actual != expected_sha:
    raise SystemExit(f"firmware SHA mismatch: {actual}")

release = json.loads((root / "release.json").read_text())
profile = release["profiles"]["smart-display"]
if len(raw) != profile["size"] or actual != profile["sha256"]:
    raise SystemExit("release manifest does not match firmware source")

output = dist / profile["file"]
output.parent.mkdir(parents=True, exist_ok=True)
output.write_bytes(raw)
print("Built", output.relative_to(dist), len(raw), actual)
