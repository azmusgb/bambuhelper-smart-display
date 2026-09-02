#!/usr/bin/env python3
from __future__ import annotations

import base64
import sys
import zlib
from pathlib import Path

payload = Path(__file__).resolve().parent / ".bambuhelper-validation" / "v10-theme-patcher.zlib.b64"
source = zlib.decompress(base64.b64decode(payload.read_text().strip())).decode("utf-8")
namespace = {"__name__": "__main__", "__file__": str(Path(__file__).resolve())}
exec(compile(source, str(Path(__file__).resolve()), "exec"), namespace, namespace)
