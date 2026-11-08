#!/usr/bin/env python3
"""The hub's custom-endpoint fetch checks the declared body length before it reads the body.

baseline/files/src/smart_hub.cpp used to call http.getString() (the whole body) and only then compare it with
HUB_HTTP_LIMIT, so an endpoint could make the device buffer an unbounded reply. The fetch now refuses a Transfer-Encoding or
missing or over-limit Content-Length (checkReplyHeaders), then copies at most limit + 1 bytes from the socket under a
deadline (readBounded); both are tested on the host (tests/workshop_os12_hub_body_limit_smoke.cpp). It must never call
http.getString() again, and it must ask HTTPClient for the Transfer-Encoding header before each request.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    hub = (ROOT / "baseline/files/src/smart_hub.cpp").read_text(encoding="utf-8")
    problems = []
    if re.search(r"\bhttp\.getString\(", hub):
        problems.append("http.getString() reads a whole body: use readBoundedBody()")
    start = hub.find("static bool readBoundedBody(")
    if start < 0:
        problems.append("readBoundedBody() is missing")
    else:
        end = hub.find("\n}\n", start)
        body = hub[start:end]
        for needle in ('hasHeader("Transfer-Encoding")', "checkReplyHeaders(", "getStreamPtr()", "readBounded("):
            if needle not in body:
                problems.append(f"readBoundedBody() does not use {needle}")
        if "checkReplyHeaders(" in body and "readBounded(" in body and body.find("checkReplyHeaders(") > body.find("readBounded("):
            problems.append("readBoundedBody() reads before it checks the headers")
    fetch = hub.find("static void fetchCustom()")
    tail = hub[fetch:] if fetch >= 0 else ""
    gets = [m.start() for m in re.finditer(r"http\.GET\(\)", tail)]
    collect = tail.find("http.collectHeaders(")
    if not gets or collect < 0 or collect > gets[0]:
        problems.append("fetchCustom() must call http.collectHeaders() for Transfer-Encoding before http.GET()")
    if 'include "workshop_http_body_limit.hpp"' not in hub:
        problems.append("smart_hub.cpp does not include workshop_http_body_limit.hpp")
    if problems:
        print("FAIL: hub fetch limit")
        for p in problems:
            print(" -", p)
        return 1
    print("PASS: the hub fetch checks the headers, then reads a bounded body from the socket")
    return 0


if __name__ == "__main__":
    sys.exit(main())
