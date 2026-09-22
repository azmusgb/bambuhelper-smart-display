#!/usr/bin/env python3
"""Runtime acceptance for the Workshop OS 12 code-free local portal."""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass


class AcceptanceError(RuntimeError):
    pass


@dataclass
class Response:
    status: int
    body: str
    headers: object
    final_url: str


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, hdrs, newurl):
        return None


class Client:
    def __init__(self, base_url: str, follow_redirects: bool = True) -> None:
        self.base_url = base_url.rstrip("/")
        handlers = [] if follow_redirects else [NoRedirect()]
        self.opener = urllib.request.build_opener(*handlers)

    def request(self, path: str, *, method: str = "GET", headers: dict[str, str] | None = None, form: dict[str, str] | None = None, timeout: float = 10.0) -> Response:
        url = urllib.parse.urljoin(self.base_url + "/", path.lstrip("/"))
        req_headers = {"User-Agent": "WorkshopOS-CodeFree-Acceptance/1", "Accept": "*/*"}
        if headers:
            req_headers.update(headers)
        data = None
        if form is not None:
            data = urllib.parse.urlencode(form).encode("utf-8")
            req_headers["Content-Type"] = "application/x-www-form-urlencoded"
        req = urllib.request.Request(url, data=data, method=method, headers=req_headers)
        try:
            with self.opener.open(req, timeout=timeout) as resp:
                return Response(resp.status, resp.read().decode("utf-8", "replace"), resp.headers, resp.geturl())
        except urllib.error.HTTPError as exc:
            return Response(exc.code, exc.read().decode("utf-8", "replace"), exc.headers, exc.geturl())
        except urllib.error.URLError as exc:
            raise AcceptanceError(f"request failed for {url}: {exc.reason}") from exc


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AcceptanceError(message)



def assert_code_free_portal(client: Client) -> None:
    root = client.request("/")
    check(root.status == 200, f"GET / returned HTTP {root.status}")
    check("/login" not in urllib.parse.urlparse(root.final_url).path,
          "root unexpectedly redirected to /login")

    login = Client(client.base_url, follow_redirects=False).request("/login")
    check(login.status in (302, 303, 307, 308),
          f"GET /login returned HTTP {login.status}, expected redirect")
    location = login.headers.get("Location") if login.headers else None
    check(location == "/", f"/login did not redirect to / (Location={location!r})")
    check("Portal code" not in login.body and "name='code'" not in login.body,
          "device-code prompt leaked from /login")

    status = client.request("/api/portal-security", headers={"Accept": "application/json"})
    check(status.status == 200, f"GET /api/portal-security returned HTTP {status.status}")
    try:
        policy = json.loads(status.body)
    except Exception as exc:
        raise AcceptanceError("portal security status is not valid JSON") from exc
    check(policy.get("requirePortalCode") is False, "requirePortalCode is not false")
    check(policy.get("deviceCodeEnabled") is False, "deviceCodeEnabled is not false")
    check(policy.get("authMode") == "local-code-free",
          f"unexpected authMode: {policy.get('authMode')!r}")
    check(policy.get("mutationsRequireSession") is False,
          "mutationsRequireSession is not false")
    check(policy.get("sameOriginProtection") is True,
          "sameOriginProtection is not true")


def run(args: argparse.Namespace) -> int:
    base = args.base_url.rstrip("/")
    check(base.startswith(("http://", "https://")), "--base-url must start with http:// or https://")
    print(f"Target: {base}")

    client = Client(base)
    root = client.request("/")
    check(root.status == 200, f"GET / returned HTTP {root.status}")
    check("/login" not in urllib.parse.urlparse(root.final_url).path, "root unexpectedly redirected to /login")
    print("PASS  local portal opens without a device code")

    login = Client(base, follow_redirects=False).request("/login")
    check(login.status in (302, 303, 307, 308), f"GET /login returned HTTP {login.status}, expected redirect")
    location = login.headers.get("Location") if login.headers else None
    check(location == "/", f"/login did not redirect to / (Location={location!r})")
    check("Portal code" not in login.body and "name='code'" not in login.body, "device-code prompt leaked from /login")
    print("PASS  legacy /login no longer exposes a device-code prompt")

    status = client.request("/api/portal-security", headers={"Accept": "application/json"})
    check(status.status == 200, f"GET /api/portal-security returned HTTP {status.status}")
    try:
        policy = json.loads(status.body)
    except Exception as exc:
        raise AcceptanceError("portal security status is not valid JSON") from exc

    check(policy.get("requirePortalCode") is False, "requirePortalCode is not false")
    check(policy.get("deviceCodeEnabled") is False, "deviceCodeEnabled is not false")
    check(policy.get("authMode") == "local-code-free", f"unexpected authMode: {policy.get('authMode')!r}")
    check(policy.get("mutationsRequireSession") is False, "mutationsRequireSession is not false")
    check(policy.get("sameOriginProtection") is True, "sameOriginProtection is not true")
    print("PASS  runtime reports code-free local access policy")

    cross = client.request(
        "/api/portal-security",
        method="POST",
        headers={"Origin": "http://invalid.example"},
        form={"required": "1"},
    )
    check(cross.status == 403, f"cross-origin mutation returned HTTP {cross.status}, expected 403")
    print("PASS  cross-origin mutation is rejected")

    same = client.request(
        "/api/portal-security",
        method="POST",
        headers={"Origin": base},
        form={"required": "1"},
    )
    check(same.status == 405, f"same-origin portal-code mutation returned HTTP {same.status}, expected 405")
    check("device code is disabled" in same.body.lower(), "disabled-policy response omitted code-free explanation")
    print("PASS  device-code policy cannot be re-enabled through the portal")

    print()
    print("RUNTIME CODE-FREE PORTAL ACCEPTANCE SUBSET: PASS")
    print("This does not constitute whole-device physical acceptance.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--base-url",
        default=os.environ.get("WORKSHOP_OS_URL", "http://10.0.0.124"),
        help="Workshop OS device URL",
    )
    parser.add_argument("--probe-only", action="store_true", help="retained for bootstrap compatibility; the code-free probe is already non-destructive")
    args = parser.parse_args()
    try:
        return run(args)
    except AcceptanceError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
