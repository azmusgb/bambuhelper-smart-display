#!/usr/bin/env python3
"""Runtime acceptance for the read-only status token route (GET only).

Unattended and non-destructive: every request is a GET, and no control,
power, update or settings route is ever called. Checks on a running WS350:

* GET /api/status/lite without a token -> 401;
* a well-formed but wrong token -> 401, and repeated bad tokens back off (429);
* the real token -> 200 with schema 1 and only the allowed fields;
* an immediate second read -> 429 with Retry-After (one answer every 2 s);
* the token opens nothing else: /status, /hardware/health and
  /api/status-token answer 401 when presented with it.

The token is read at a hidden prompt, or from an owner-only (0600) file named
by WORKSHOP_OS_STATUS_TOKEN_FILE. It is never printed or written to evidence.
"""
from __future__ import annotations

import argparse
import getpass
import json
import os
import re
import stat
import sys
import time
import urllib.error
import urllib.request

TOKEN_RE = re.compile(r"^wsl_[ABCDEFGHJKLMNPQRSTUVWXYZ23456789]{26}$")
TOP_KEYS = {"schema", "firmware", "printers"}
FIRMWARE_KEYS = {"version", "sourceCommit"}
PRINTER_KEYS = {"slot", "connection", "activity", "freshness", "ageSeconds", "progressPercent",
                "remainingMinutes", "error"}
ERROR_KEYS = {"code", "text", "canceled"}
CONNECTIONS = {"online", "connecting", "offline", "degraded", "unknown"}
ACTIVITIES = {"idle", "preparing", "printing", "paused", "finished", "error", "unknown"}
FRESHNESS = {"fresh", "stale", "unknown"}
WRONG_TOKEN = "wsl_" + "A" * 26


class AcceptanceError(RuntimeError):
    pass


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AcceptanceError(message)


def get(base: str, path: str, token: str | None = None, timeout: float = 8.0) -> tuple[int, dict, str]:
    headers = {"User-Agent": "WorkshopOS-StatusLite-Acceptance/1", "Accept": "application/json"}
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(base + path, method="GET", headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, dict(resp.headers), resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return exc.code, dict(exc.headers), exc.read().decode("utf-8", "replace")
    except urllib.error.URLError as exc:
        raise AcceptanceError(f"request failed for {path}: {exc.reason}") from exc


def validate_payload(payload: object) -> None:
    check(isinstance(payload, dict) and set(payload) == TOP_KEYS, f"unexpected top-level fields: {payload!r:.200}")
    check(payload["schema"] == 1, "schema is not 1")
    fw = payload["firmware"]
    check(isinstance(fw, dict) and set(fw) == FIRMWARE_KEYS, "unexpected firmware fields")
    printers = payload["printers"]
    check(isinstance(printers, list), "printers is not a list")
    for p in printers:
        check(isinstance(p, dict) and set(p) == PRINTER_KEYS, f"unexpected printer fields: {sorted(p)}")
        check(isinstance(p["slot"], int) and 0 <= p["slot"] < 4, "slot out of range")
        check(p["connection"] in CONNECTIONS, f"connection {p['connection']!r}")
        check(p["activity"] in ACTIVITIES, f"activity {p['activity']!r}")
        check(p["freshness"] in FRESHNESS, f"freshness {p['freshness']!r}")
        current = p["connection"] == "online" and p["freshness"] == "fresh"
        if not current:
            check(p["activity"] == "unknown", "activity reported for telemetry that is not current")
            check(p["progressPercent"] is None and p["remainingMinutes"] is None, "progress reported while not current")
            check(p["error"] is None, "error reported while not current")
        if p["activity"] not in ("preparing", "printing", "paused"):
            check(p["progressPercent"] is None and p["remainingMinutes"] is None,
                  "progress/time left reported outside an active print")
        if p["progressPercent"] is not None:
            check(isinstance(p["progressPercent"], int) and 0 <= p["progressPercent"] <= 100, "progress out of range")
        if p["error"] is not None:
            check(isinstance(p["error"], dict) and set(p["error"]) == ERROR_KEYS, "unexpected error fields")
            check(isinstance(p["error"]["canceled"], bool), "error.canceled is not boolean")


def read_token() -> str:
    path = os.environ.get("WORKSHOP_OS_STATUS_TOKEN_FILE")
    if path:
        mode = os.stat(path).st_mode
        check(not mode & (stat.S_IRWXG | stat.S_IRWXO), f"{path} must be readable by its owner only (chmod 600)")
        return open(path, encoding="utf-8").read().strip()
    check(sys.stdin.isatty(), "run interactively or set WORKSHOP_OS_STATUS_TOKEN_FILE")
    return getpass.getpass("Read-only status token (from Local Portal): ").strip()


def run(base: str, token: str, pause: float = 2.2) -> None:
    check(TOKEN_RE.fullmatch(token) is not None, "the status token is not in the wsl_ format")
    check(token != WRONG_TOKEN, "refusing to use the probe token as the real token")

    status, _, _ = get(base, "/api/status/lite")
    check(status == 401, f"no token returned HTTP {status}, expected 401")
    print("PASS  no token -> 401")
    time.sleep(pause)

    status, headers, _ = get(base, "/api/status/lite", WRONG_TOKEN)
    check(status == 401, f"wrong token returned HTTP {status}, expected 401")
    check("Bearer" in headers.get("WWW-Authenticate", ""), "401 lacks WWW-Authenticate: Bearer")
    print("PASS  wrong token -> 401")
    time.sleep(pause)

    # Third bad attempt starts the backoff; the next read is refused while blocked.
    get(base, "/api/status/lite", WRONG_TOKEN)
    time.sleep(pause)
    status, headers, _ = get(base, "/api/status/lite", WRONG_TOKEN)
    check(status in (401, 429), f"repeated wrong token returned HTTP {status}")
    blocked = 0
    while status != 429 and blocked < 3:
        time.sleep(0.2)
        status, headers, _ = get(base, "/api/status/lite", WRONG_TOKEN)
        blocked += 1
    check(status == 429 and headers.get("Retry-After"), "repeated wrong tokens did not back off with 429 + Retry-After")
    print("PASS  repeated wrong tokens back off (429 + Retry-After)")
    time.sleep(min(60.0, float(headers.get("Retry-After", "2")) + pause))

    status, headers, body = get(base, "/api/status/lite", token)
    while status == 429:
        time.sleep(float(headers.get("Retry-After", "2")) + 0.2)
        status, headers, body = get(base, "/api/status/lite", token)
    check(status == 200, f"valid token returned HTTP {status}, expected 200")
    check("no-store" in headers.get("Cache-Control", ""), "response is cacheable")
    payload = json.loads(body)
    validate_payload(payload)
    for leak in ("ip", "mac", "serial", "name", "subtask", "rssi", "ams"):
        check(f'"{leak}"' not in body.lower(), f"forbidden field {leak!r} present")
    check(token not in body, "token echoed in the response")
    print(f"PASS  valid token -> 200, schema 1, {len(payload['printers'])} printer(s), allowed fields only")

    status, headers, _ = get(base, "/api/status/lite", token)
    check(status == 429 and headers.get("Retry-After"), f"immediate second read returned HTTP {status}, expected 429")
    print("PASS  one answer every 2 s per client (429 + Retry-After)")

    for path in ("/status?slot=0", "/hardware/health?slot=0", "/api/status-token"):
        status, _, _ = get(base, path, token)
        check(status == 401, f"token opened {path} (HTTP {status}); it must open nothing else")
    print("PASS  the token opens no other route")

    print()
    print("RUNTIME STATUS TOKEN ACCEPTANCE SUBSET: PASS (GET-only, non-destructive)")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default=os.environ.get("WORKSHOP_OS_URL", "http://10.0.0.124"))
    args = ap.parse_args()
    base = args.base_url.rstrip("/")
    try:
        check(base.startswith(("http://", "https://")), "--base-url must start with http:// or https://")
        run(base, read_token())
    except AcceptanceError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
