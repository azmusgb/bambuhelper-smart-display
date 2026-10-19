#!/usr/bin/env python3
"""Host test for scripts/accept_os12_code_token_runtime.py (no device needed).

A loopback fake WS350 implements the /api/portal-code rules (key check, 2 s
rate limit, back-off after wrong wsc_ keys on the route's own counter). The acceptance
helper must pass against it, send only GET requests, never put the key in a
URL, and FAIL against devices that:
* let the key open another route;
* answer without a key;
* accept a status-token ("wsl_") key;
* add a field to the response;
* skip the 2-second rate limit;
* answer with a cacheable response;
* count a request without a well-formed key toward the lock-out.
"""
from __future__ import annotations

import http.server
import json
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import accept_os12_code_token_runtime as acc  # noqa: E402

KEY = "wsc_" + "B" * 20 + "234567"
CODE = "ABCDEFGHJK"
BOOT = "0123456789abcdef"
STEP = [0.0]  # fake clock, advanced by the patched sleep


class Fake(http.server.BaseHTTPRequestHandler):
    mode = "good"
    seen: list[tuple[str, str, str]] = []
    last_answer = [-10.0]
    failures = [0]
    blocked_until = [0.0]

    def log_message(self, *a):
        pass

    def _send(self, code, body, headers=None):
        raw = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        if self.mode != "cacheable":
            self.send_header("Cache-Control", "no-store")
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_POST(self):
        self.seen.append(("POST", self.path, ""))
        self._send(405, {})

    def do_GET(self):
        auth = self.headers.get("Authorization", "")
        self.seen.append(("GET", self.path, auth))
        path = self.path.split("?")[0]
        if path != "/api/portal-code":
            if self.mode == "opens-other" and auth == f"Bearer {KEY}":
                return self._send(200, {})
            return self._send(401, {})
        now = STEP[0]
        if now < self.blocked_until[0]:
            return self._send(429, {}, {"Retry-After": "1"})
        if self.mode != "no-limit" and now - self.last_answer[0] < 2.0:
            return self._send(429, {}, {"Retry-After": "2"})
        self.last_answer[0] = now
        accepted = {f"Bearer {KEY}"}
        if self.mode == "open":
            accepted.add("")
        if self.mode == "status-key":
            accepted.add("Bearer " + acc.STATUS_SHAPED)
        if auth not in accepted:
            # 12.3.8: only a well-formed wsc_ key counts (mode "counts-missing"
            # is the old behaviour, where any request without the key counted).
            if self.mode == "counts-missing" or acc.KEY_RE.fullmatch(auth[len("Bearer "):] if auth.startswith("Bearer ") else ""):
                self.failures[0] += 1
                if self.failures[0] > 2:
                    self.blocked_until[0] = now + 2 ** (self.failures[0] - 3)
            return self._send(401, {}, {"WWW-Authenticate": 'Bearer realm="workshop-os-code"'})
        body = {"code": CODE, "bootId": BOOT}
        if self.mode == "extra-field":
            body["ip"] = "10.0.0.2"
        return self._send(200, body)


def reset(mode: str) -> None:
    Fake.mode = mode
    Fake.seen.clear()
    Fake.last_answer[0] = -10.0
    Fake.failures[0] = 0
    Fake.blocked_until[0] = 0.0
    STEP[0] = 0.0


def main() -> int:
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Fake)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_address[1]}"

    def fake_sleep(seconds: float) -> None:
        STEP[0] += seconds

    acc.time.sleep = fake_sleep
    try:
        reset("good")
        acc.run(base, KEY)
        assert all(method == "GET" for method, _, _ in Fake.seen), Fake.seen
        assert all(KEY not in path for _, path, _ in Fake.seen)
        with_key = {path.split("?")[0] for _, path, auth in Fake.seen if KEY in auth}
        assert with_key == {"/api/portal-code", "/api/code-token", "/api/status-token", "/api/status/lite",
                            "/printer/access-code", "/settings/export", "/status", "/hardware/health"}, with_key

        for mode, label in (("opens-other", "key opening another route"), ("open", "answering without a key"),
                            ("status-key", "status token accepted"), ("extra-field", "extra response field"),
                            ("no-limit", "missing rate limit"), ("cacheable", "cacheable response"),
                            ("counts-missing", "requests without a key counting toward the lock-out")):
            reset(mode)
            try:
                acc.run(base, KEY)
            except acc.AcceptanceError:
                continue
            raise SystemExit(f"FAIL: acceptance did not detect {label}")

        for bad in ("wsc_short", "Bearer " + KEY, acc.WRONG_KEY, "wsl_" + "B" * 20 + "234567"):
            reset("good")
            try:
                acc.run(base, bad)
            except acc.AcceptanceError:
                continue
            raise SystemExit(f"FAIL: malformed key accepted: {bad!r}")
    finally:
        server.shutdown()
    print("PASS: sign-in code key runtime acceptance is GET-only and detects open, over-broad, leaking, "
          "unlimited, cacheable or status-token-accepting devices")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
