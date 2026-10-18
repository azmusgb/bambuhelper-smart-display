#!/usr/bin/env python3
"""Host test for scripts/accept_os12_status_lite_runtime.py (no device needed).

A loopback fake WS350 implements the status-lite route rules. The acceptance
helper must pass against it, send only GET requests, never send the token to
anything but the routes it probes, and FAIL against devices that:
* let the token open another route;
* answer without a token;
* leak an identifying field;
* skip the 2-second rate limit.
"""
from __future__ import annotations

import http.server
import json
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import accept_os12_status_lite_runtime as acc  # noqa: E402

TOKEN = "wsl_" + "B" * 20 + "234567"
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
        if path != "/api/status/lite":
            if self.mode == "opens-other" and auth == f"Bearer {TOKEN}":
                return self._send(200, {})
            return self._send(401, {})
        now = STEP[0]
        if now < self.blocked_until[0]:
            return self._send(429, {}, {"Retry-After": "1"})
        if self.mode != "no-limit" and now - self.last_answer[0] < 2.0:
            return self._send(429, {}, {"Retry-After": "2"})
        self.last_answer[0] = now
        if auth != f"Bearer {TOKEN}" and self.mode != "open":
            self.failures[0] += 1
            if self.failures[0] > 2:
                self.blocked_until[0] = now + 2 ** (self.failures[0] - 3)
            return self._send(401, {}, {"WWW-Authenticate": 'Bearer realm="workshop-os-status"'})
        self.failures[0] = 0
        printer = {"slot": 0, "connection": "online", "activity": "printing", "freshness": "fresh",
                   "ageSeconds": 2, "progressPercent": 62, "remainingMinutes": 41, "error": None}
        if self.mode == "leak":
            printer["name"] = "Workshop X2D"
        return self._send(200, {"schema": 1, "firmware": {"version": "12.1.0", "sourceCommit": "a" * 40},
                                "printers": [printer]})


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
        acc.run(base, TOKEN)
        assert all(method == "GET" for method, _, _ in Fake.seen), Fake.seen
        assert all(TOKEN not in path for _, path, _ in Fake.seen)
        with_token = {path.split("?")[0] for _, path, auth in Fake.seen if TOKEN in auth}
        assert with_token == {"/api/status/lite", "/status", "/hardware/health", "/api/status-token"}, with_token

        for mode, label in (("opens-other", "token opening another route"), ("open", "answering without a token"),
                            ("leak", "identifying field"), ("no-limit", "missing rate limit")):
            reset(mode)
            try:
                acc.run(base, TOKEN)
            except acc.AcceptanceError:
                continue
            raise SystemExit(f"FAIL: acceptance did not detect {label}")

        for bad in ("wsl_short", "Bearer " + TOKEN, acc.WRONG_TOKEN):
            reset("good")
            try:
                acc.run(base, bad)
            except acc.AcceptanceError:
                continue
            raise SystemExit(f"FAIL: malformed token accepted: {bad!r}")
    finally:
        server.shutdown()
    print("PASS: status-lite runtime acceptance is GET-only and detects open, leaking, unlimited or over-broad tokens")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
