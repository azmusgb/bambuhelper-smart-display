#!/usr/bin/env python3
"""Runtime acceptance for the sign-in code key route (GET only).

Unattended and non-destructive: every request is a GET, and no control,
power, update, sign-in or settings route is ever changed. Checks on a running
WS350:

* GET /api/portal-code without a key -> 401 with WWW-Authenticate: Bearer;
* a well-formed but wrong "wsc_" key -> 401, and a status-token-shaped
  "wsl_" key -> 401;
* repeated wrong keys back off with 429 + Retry-After;
* the real key -> 200 with exactly {"code","bootId"}, Cache-Control: no-store,
  a 10-character code and a 16-hex boot id;
* an immediate second read -> 429 with Retry-After (one answer every 2 s);
  a later read gives the same code and boot id;
* the key opens nothing else: every other probed route answers the same with
  the key as without it, and never 200 for the protected ones.

Wrong keys count as failed sign-ins for this computer's address, like wrong
codes on the sign-in page. The script waits out the back-off it causes before
it finishes, and a successful sign-in resets the count.

The key is read at a hidden prompt, or from an owner-only (0600) file named by
WORKSHOP_OS_CODE_TOKEN_FILE. Neither the key nor the code is printed or
written anywhere.
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

ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
KEY_RE = re.compile(rf"^wsc_[{ALPHABET}]{{26}}$")
CODE_RE = re.compile(rf"^[{ALPHABET}]{{10}}$")
BOOT_RE = re.compile(r"^[0-9a-f]{16}$")
WRONG_KEY = "wsc_" + "A" * 26
STATUS_SHAPED = "wsl_" + "A" * 26
ROUTE = "/api/portal-code"
# Never 200 for this key, whatever the "Require access code" setting.
PROTECTED = ("/api/code-token", "/api/status-token", "/api/status/lite", "/printer/access-code",
             "/settings/export")
# Open reads when "Require access code" is off; the key must not change the answer.
SAME_AS_ANONYMOUS = ("/status?slot=0", "/hardware/health?slot=0")


class AcceptanceError(RuntimeError):
    pass


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AcceptanceError(message)


def get(base: str, path: str, key: str | None = None, timeout: float = 8.0) -> tuple[int, dict, str]:
    headers = {"User-Agent": "WorkshopOS-CodeToken-Acceptance/1", "Accept": "application/json"}
    if key is not None:
        headers["Authorization"] = f"Bearer {key}"
    req = urllib.request.Request(base + path, method="GET", headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, dict(resp.headers), resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return exc.code, dict(exc.headers), exc.read().decode("utf-8", "replace")
    except urllib.error.URLError as exc:
        raise AcceptanceError(f"request failed for {path}: {exc.reason}") from exc


def retry_after(headers: dict, default: float = 2.0) -> float:
    try:
        return float(headers.get("Retry-After", default))
    except ValueError:
        return default


def read_until_answered(base: str, key: str, pause: float) -> tuple[int, dict, str]:
    status, headers, body = get(base, ROUTE, key)
    tries = 0
    while status == 429 and tries < 8:
        time.sleep(min(60.0, retry_after(headers)) + pause)
        status, headers, body = get(base, ROUTE, key)
        tries += 1
    return status, headers, body


def validate_payload(body: str, key: str) -> dict:
    payload = json.loads(body)
    check(isinstance(payload, dict) and set(payload) == {"code", "bootId"},
          f"unexpected fields: {sorted(payload) if isinstance(payload, dict) else type(payload).__name__}")
    check(isinstance(payload["code"], str) and CODE_RE.fullmatch(payload["code"]) is not None,
          "code is not 10 characters of the portal alphabet")
    check(isinstance(payload["bootId"], str) and BOOT_RE.fullmatch(payload["bootId"]) is not None,
          "bootId is not 16 lower-case hex characters")
    check(key not in body, "key echoed in the response")
    return payload


def run(base: str, key: str, pause: float = 2.2) -> None:
    check(KEY_RE.fullmatch(key) is not None, "the key is not in the wsc_ format")
    check(key != WRONG_KEY, "refusing to use the probe key as the real key")

    status, headers, _ = get(base, ROUTE)
    check(status == 401, f"no key returned HTTP {status}, expected 401")
    check("Bearer" in headers.get("WWW-Authenticate", ""), "401 lacks WWW-Authenticate: Bearer")
    print("PASS  no key -> 401")
    time.sleep(pause)

    status, _, _ = get(base, ROUTE, WRONG_KEY)
    check(status == 401, f"wrong key returned HTTP {status}, expected 401")
    print("PASS  wrong key -> 401")
    time.sleep(pause)

    status, headers, _ = get(base, ROUTE, STATUS_SHAPED)
    check(status in (401, 429), f"status-token-shaped key returned HTTP {status}, expected 401")
    if status == 429:  # the device may already be backing off after two bad keys
        time.sleep(min(60.0, retry_after(headers)) + pause)
        status, _, _ = get(base, ROUTE, STATUS_SHAPED)
    check(status in (401, 429), f"status-token-shaped key returned HTTP {status}, expected 401")
    print("PASS  a wsl_ (status token) key does not open the code route")
    time.sleep(pause)

    status, headers, _ = get(base, ROUTE, WRONG_KEY)
    tries = 0
    while status != 429 and tries < 4:
        time.sleep(0.2)
        status, headers, _ = get(base, ROUTE, WRONG_KEY)
        tries += 1
    check(status == 429 and headers.get("Retry-After"), "repeated wrong keys did not back off with 429 + Retry-After")
    print("PASS  repeated wrong keys back off (429 + Retry-After)")
    time.sleep(min(60.0, retry_after(headers)) + pause)

    status, headers, body = read_until_answered(base, key, pause)
    check(status == 200, f"valid key returned HTTP {status}, expected 200")
    check("no-store" in headers.get("Cache-Control", ""), "response is cacheable")
    first = validate_payload(body, key)
    print("PASS  valid key -> 200, exactly code + bootId, no-store")

    status, headers, _ = get(base, ROUTE, key)
    check(status == 429 and headers.get("Retry-After"), f"immediate second read returned HTTP {status}, expected 429")
    print("PASS  one answer every 2 s per client (429 + Retry-After)")
    time.sleep(min(60.0, retry_after(headers)) + pause)

    status, _, body = read_until_answered(base, key, pause)
    check(status == 200, f"second valid read returned HTTP {status}")
    second = validate_payload(body, key)
    check(second == first, "code or bootId changed between two reads without a restart")
    print("PASS  code and bootId are stable within a boot")

    for path in PROTECTED:
        status, _, _ = get(base, path, key)
        check(status != 200 and status in (401, 403, 429), f"key opened {path} (HTTP {status}); it must open nothing else")
    for path in SAME_AS_ANONYMOUS:
        anonymous, _, _ = get(base, path)
        with_key, _, _ = get(base, path, key)
        check(with_key == anonymous, f"key changed the answer of {path} (HTTP {anonymous} -> {with_key})")
    print("PASS  the key opens no other route")

    print()
    print("RUNTIME SIGN-IN CODE KEY ACCEPTANCE SUBSET: PASS (GET-only, non-destructive)")


def read_key() -> str:
    path = os.environ.get("WORKSHOP_OS_CODE_TOKEN_FILE")
    if path:
        mode = os.stat(path).st_mode
        check(not mode & (stat.S_IRWXG | stat.S_IRWXO), f"{path} must be readable by its owner only (chmod 600)")
        return open(path, encoding="utf-8").read().strip()
    check(sys.stdin.isatty(), "run interactively or set WORKSHOP_OS_CODE_TOKEN_FILE")
    return getpass.getpass("Sign-in code key (from Local Portal): ").strip()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default=os.environ.get("WORKSHOP_OS_URL", "http://10.0.0.124"))
    args = ap.parse_args()
    base = args.base_url.rstrip("/")
    try:
        check(base.startswith(("http://", "https://")), "--base-url must start with http:// or https://")
        run(base, read_key())
    except AcceptanceError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
