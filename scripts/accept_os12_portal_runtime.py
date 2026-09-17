#!/usr/bin/env python3
"""Runtime acceptance helper for the Workshop OS 12 local portal.

This exercises the network/browser authentication contract against a real device.
It deliberately does not claim physical acceptance: framebuffer/touch/recovery and
reboot observations still require the actual WS350 acceptance procedure.

The portal code is read from WORKSHOP_OS_PORTAL_CODE or entered with getpass. It
is never printed and is never written to disk by this script. Prefer the prompt
over passing credentials on a command line, where shell history can retain them.
"""
from __future__ import annotations

import argparse
import getpass
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from http.cookiejar import CookieJar

ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
CODE_LEN = 10


class AcceptanceError(RuntimeError):
    pass


@dataclass
class Response:
    status: int
    body: str
    headers: object
    final_url: str


class Client:
    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.cookies = CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.cookies)
        )

    def request(
        self,
        path: str,
        *,
        method: str = "GET",
        form: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
        timeout: float = 10.0,
    ) -> Response:
        url = urllib.parse.urljoin(self.base_url + "/", path.lstrip("/"))
        data = None
        request_headers = {
            "User-Agent": "WorkshopOS-Portal-Acceptance/1",
            "Accept": "text/html,application/json;q=0.9,*/*;q=0.8",
        }
        if headers:
            request_headers.update(headers)
        if form is not None:
            data = urllib.parse.urlencode(form).encode("utf-8")
            request_headers["Content-Type"] = "application/x-www-form-urlencoded"
        req = urllib.request.Request(url, data=data, method=method, headers=request_headers)
        try:
            with self.opener.open(req, timeout=timeout) as resp:
                body = resp.read().decode("utf-8", errors="replace")
                return Response(resp.status, body, resp.headers, resp.geturl())
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            return Response(exc.code, body, exc.headers, exc.geturl())
        except urllib.error.URLError as exc:
            raise AcceptanceError(f"request failed for {url}: {exc.reason}") from exc


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AcceptanceError(message)


def normalized_code(raw: str) -> str:
    code = raw.strip().upper()
    check(len(code) == CODE_LEN, f"portal code must contain exactly {CODE_LEN} characters")
    bad = [ch for ch in code if ch not in ALPHABET]
    check(not bad, "portal code contains a character outside the canonical device alphabet")
    return code


def protected_root_is_open(client: Client) -> bool:
    response = client.request("/")
    final_path = urllib.parse.urlparse(response.final_url).path or "/"
    return response.status == 200 and final_path != "/login"


def assert_login_markup(client: Client) -> None:
    response = client.request("/login")
    check(response.status == 200, f"GET /login returned HTTP {response.status}")
    text = response.body
    required = (
        "<html lang='en'>",
        "<meta charset='utf-8'>",
        "Local device access",
        "<h1 class='brand'>Workshop OS</h1>",
        "id='code-help'",
        "autocomplete='off'",
        "autocorrect='off'",
        "aria-live='polite'",
        "button:disabled",
    )
    forbidden = (
        "Secure LAN access",
        "Sign in securely",
        "autocomplete='one-time-code'",
        "font-weight:820",
        "font-weight:850",
    )
    for marker in required:
        check(marker in text, f"login page missing expected marker: {marker}")
    for marker in forbidden:
        check(marker not in text, f"login page still contains stale marker: {marker}")
    print("PASS  login markup/accessibility contract")


def assert_unauthenticated_gate(base_url: str) -> None:
    anonymous = Client(base_url)
    response = anonymous.request("/")
    final_path = urllib.parse.urlparse(response.final_url).path or "/"
    check(final_path == "/login", "unauthenticated root did not finish at /login")
    print("PASS  unauthenticated root is gated")


def wrong_valid_code(code: str) -> str:
    replacement = ALPHABET[0] if code[0] != ALPHABET[0] else ALPHABET[1]
    return replacement + code[1:]


def exercise_rate_limit(client: Client, code: str) -> None:
    # One malformed-alphabet attempt plus valid-shape wrong attempts prove that
    # server-side validation participates in the same failure/backoff boundary.
    attempts = ["I" * CODE_LEN, wrong_valid_code(code), wrong_valid_code(code)]
    limited: Response | None = None
    for candidate in attempts:
        response = client.request("/login", method="POST", form={"code": candidate})
        check(response.status in (401, 429), f"bad login unexpectedly returned HTTP {response.status}")
        if response.status == 429:
            limited = response
            break

    if limited is None:
        # The current policy allows two free failures, so the third should block.
        response = client.request("/login", method="POST", form={"code": wrong_valid_code(code)})
        check(response.status == 429, f"expected HTTP 429 after repeated failures, got {response.status}")
        limited = response

    retry_raw = limited.headers.get("Retry-After") if limited.headers else None
    check(retry_raw is not None, "rate-limited response omitted Retry-After")
    try:
        retry_after = max(1, int(retry_raw))
    except (TypeError, ValueError) as exc:
        raise AcceptanceError(f"invalid Retry-After header: {retry_raw!r}") from exc
    check("Too many unsuccessful attempts" in limited.body, "rate-limit page omitted visible error state")
    check("role='alert'" in limited.body, "rate-limit error is not exposed as an alert")
    print(f"PASS  bounded login backoff engaged (Retry-After={retry_after}s)")

    # Wait only as long as the device told us. Never hammer a locked device.
    time.sleep(retry_after + 1)


def login(client: Client, submitted_code: str, label: str) -> None:
    response = client.request("/login", method="POST", form={"code": submitted_code})
    check(response.status == 200, f"{label}: login flow ended with HTTP {response.status}")
    final_path = urllib.parse.urlparse(response.final_url).path or "/"
    check(final_path != "/login", f"{label}: login did not leave /login")
    check(protected_root_is_open(client), f"{label}: authenticated root is not accessible")
    cookie_names = {cookie.name for cookie in client.cookies}
    check("BHSESSION" in cookie_names, f"{label}: BHSESSION cookie was not issued")
    print(f"PASS  {label}")


def logout(client: Client) -> None:
    response = client.request(
        "/logout",
        method="POST",
        headers={"X-BambuHelper-Client": "1"},
    )
    check(response.status == 200, f"logout flow ended with HTTP {response.status}")
    final_path = urllib.parse.urlparse(response.final_url).path or "/"
    check(final_path == "/login", "logout did not return to /login")


def run(args: argparse.Namespace) -> int:
    base_url = args.base_url.rstrip("/")
    check(base_url.startswith(("http://", "https://")), "--base-url must start with http:// or https://")

    raw_code = os.environ.get("WORKSHOP_OS_PORTAL_CODE")
    if not raw_code:
        raw_code = getpass.getpass("Current portal code shown on WS350 System screen: ")
    code = normalized_code(raw_code)
    raw_code = ""  # drop the original reference promptly

    print(f"Target: {base_url}")
    print("Credential handling: portal code will not be printed or written by this script")

    probe = Client(base_url)
    assert_login_markup(probe)
    assert_unauthenticated_gate(base_url)

    if args.exercise_rate_limit:
        exercise_rate_limit(probe, code)

    # Lowercase submission proves the actual value path, not CSS text-transform.
    session_a = Client(base_url)
    login(session_a, code.lower(), "lowercase normalization + session A")

    # A second independent browser must receive a separate valid session.
    session_b = Client(base_url)
    login(session_b, code, "independent session B")

    logout(session_a)
    check(not protected_root_is_open(session_a), "session A remained authorized after logout")
    check(protected_root_is_open(session_b), "logging out session A revoked independent session B")
    print("PASS  logout revokes only the presenting session")

    print()
    print("RUNTIME PORTAL ACCEPTANCE SUBSET: PASS")
    print("Not yet physically accepted. Still verify on the WS350:")
    print("  - reboot rotates the portal code and invalidates both old sessions")
    print("  - touch, Recovery Safe Mode/AP, and normal controls remain healthy")
    print("  - target-browser focus/error/rate-limit presentation is physically acceptable")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--base-url",
        default=os.environ.get("WORKSHOP_OS_URL", "http://10.0.0.124"),
        help="Workshop OS device URL (default: WORKSHOP_OS_URL or http://10.0.0.124)",
    )
    parser.add_argument(
        "--exercise-rate-limit",
        action="store_true",
        help="deliberately submit bad codes to verify HTTP 429/backoff before authenticating",
    )
    args = parser.parse_args()
    try:
        return run(args)
    except AcceptanceError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nCancelled; no acceptance result recorded.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
