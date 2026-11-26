#!/usr/bin/env python3
"""Copied into each app by appliance-ui's sync. Fails when a shared file was edited or removed by hand:
change appliance-ui and sync again instead. Usage: python3 verify.py <folder>"""
import hashlib
import json
import os
import sys

folder = sys.argv[1] if len(sys.argv) > 1 else os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(folder, "VERSION")) as f:
    version = json.load(f)
bad = []
for name, digest in version["files"].items():
    try:
        with open(os.path.join(folder, name), "rb") as f:
            ok = hashlib.sha256(f.read()).hexdigest() == digest
    except OSError:
        ok = False
    if not ok:
        bad.append(name)
if bad:
    print(f"appliance-ui v{version['version']}: changed or missing in {folder}: {', '.join(bad)}. Edit appliance-ui and sync instead.", file=sys.stderr)
    sys.exit(1)
print(f"appliance-ui v{version['version']}: {len(version['files'])} files match")
