#!/usr/bin/env python3
"""The hub's custom-endpoint fetch checks the declared body length before it reads the body.

baseline/files/src/smart_hub.cpp used to call http.getString() (the whole body) and only then compare it with
HUB_HTTP_LIMIT, so an endpoint could make the device buffer an unbounded reply. Every getString() in that file must now
come through readBoundedBody(), which calls checkBodyLength() (tests/workshop_os12_hub_body_limit_smoke.cpp) first.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    hub = (ROOT / "baseline/files/src/smart_hub.cpp").read_text(encoding="utf-8")
    problems = []
    start = hub.find("static bool readBoundedBody(")
    if start < 0:
        problems.append("readBoundedBody() is missing")
    else:
        end = hub.find("\n}\n", start)
        body = hub[start:end]
        if "checkBodyLength(" not in body:
            problems.append("readBoundedBody() does not call checkBodyLength()")
        elif body.find("getString()") >= 0 and body.find("checkBodyLength(") > body.find("getString()"):
            problems.append("readBoundedBody() reads the body before checking its length")
    uses = [m.start() for m in re.finditer(r"\.getString\(\)", hub)]
    inside = [u for u in uses if start >= 0 and start <= u <= (hub.find("\n}\n", start) if start >= 0 else -1)]
    if len(uses) != len(inside):
        problems.append(f"{len(uses) - len(inside)} getString() call(s) outside readBoundedBody()")
    if 'include "workshop_http_body_limit.hpp"' not in hub:
        problems.append("smart_hub.cpp does not include workshop_http_body_limit.hpp")
    if problems:
        print("FAIL: hub fetch limit")
        for p in problems:
            print(" -", p)
        return 1
    print("PASS: the hub fetch checks the declared length before reading the body")
    return 0


if __name__ == "__main__":
    sys.exit(main())
