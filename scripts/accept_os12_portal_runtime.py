#!/usr/bin/env python3
"""Workshop OS 12 Local Portal runtime acceptance and shared signed-in client.

This module is the shared import surface for every OS12 acceptance helper.

Security contract checked against a running WS350 (12.0.1 and later):

* unauthenticated page navigation redirects to the custom ``/login`` page;
* unauthenticated ``GET /status`` and ``GET /hardware/health`` answer 401;
* an unauthenticated mutation is refused even when it carries the legacy
  ``X-BambuHelper-Client: 1`` header: 403 without Origin (the header is not
  same-origin proof), 401 with a matching Origin (no session);
* after sign-in, ``/api/portal-security`` reports ``mutationsRequireSession``.

Probes never touch printer control, power, update install or other side-effect
routes: the refused-mutation probe uses ``/api/portal-security``.

Credential handling (SECURITY.md):

* the portal code is read with ``getpass`` (never echoed, never a process
  argument, never written to disk or evidence), unless this machine has the
  device-issued ``wsc_`` sign-in code key: from ``WORKSHOP_OS_CODE_KEY`` or the
  macOS login Keychain (account ``ws350``, service ``workshop-os-code-key``),
  the helper fetches the current code from ``GET /api/portal-code`` itself;
* the resulting session cookie may be kept in an owner-only cookie jar named by
  ``WORKSHOP_OS_COOKIE_JAR`` so several helpers in one run share one sign-in;
  wrappers create it with mode 0600 and delete it on exit;
* the running identity is read from the public ``/recovery/status`` probe, so
  identity checks across reboots never need a session.
"""
from __future__ import annotations

import argparse
import getpass
import http.cookiejar
import json
import os
import stat
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

COOKIE_JAR_ENV = "WORKSHOP_OS_COOKIE_JAR"
SESSION_COOKIE = "BHSESSION"
CODE_ALPHABET = set("ABCDEFGHJKLMNPQRSTUVWXYZ23456789")


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


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AcceptanceError(message)


def _owner_only(path: str) -> None:
    st = os.stat(path)
    if st.st_mode & (stat.S_IRWXG | stat.S_IRWXO):
        raise AcceptanceError(f"cookie jar {path} must be readable by its owner only (chmod 600)")


class Client:
    """HTTP client for the WS350 Local Portal.

    Mutations automatically carry the device's own ``Origin`` so the firmware's
    same-origin check sees real browser-equivalent provenance. Authentication is
    the session cookie; no marker header is sent or relied upon.
    """

    def __init__(self, base_url: str, follow_redirects: bool = True, *, anonymous: bool = False) -> None:
        self.base_url = base_url.rstrip("/")
        self.jar_path = None if anonymous else os.environ.get(COOKIE_JAR_ENV) or None
        self.jar = http.cookiejar.MozillaCookieJar(self.jar_path) if self.jar_path else http.cookiejar.CookieJar()
        if self.jar_path and os.path.exists(self.jar_path) and os.path.getsize(self.jar_path) > 0:
            _owner_only(self.jar_path)
            self.jar.load(ignore_discard=True, ignore_expires=True)
        self.follow_redirects = follow_redirects

    @property
    def opener(self):
        return self._opener(self.follow_redirects)

    def _opener(self, follow_redirects: bool):
        handlers: list = [urllib.request.HTTPCookieProcessor(self.jar)]
        if not follow_redirects:
            handlers.append(NoRedirect())
        return urllib.request.build_opener(*handlers)

    def request(self, path: str, *, method: str = "GET", headers: dict[str, str] | None = None,
                form: dict[str, str] | None = None, timeout: float = 10.0,
                follow_redirects: bool | None = None) -> Response:
        url = urllib.parse.urljoin(self.base_url + "/", path.lstrip("/"))
        req_headers = {"User-Agent": "WorkshopOS-Acceptance/2", "Accept": "*/*"}
        if method.upper() != "GET":
            req_headers["Origin"] = self.base_url
        if headers:
            req_headers.update(headers)
        # An empty value means "do not send this header" (e.g. a probe without Origin).
        req_headers = {k: v for k, v in req_headers.items() if v != ""}
        data = None
        if form is not None:
            data = urllib.parse.urlencode(form).encode("utf-8")
            req_headers["Content-Type"] = "application/x-www-form-urlencoded"
        elif method.upper() == "POST":
            data = b""
        req = urllib.request.Request(url, data=data, method=method, headers=req_headers)
        try:
            follow = self.follow_redirects if follow_redirects is None else follow_redirects
            with self._opener(follow).open(req, timeout=timeout) as resp:
                return Response(resp.status, resp.read().decode("utf-8", "replace"), resp.headers, resp.geturl())
        except urllib.error.HTTPError as exc:
            return Response(exc.code, exc.read().decode("utf-8", "replace"), exc.headers, exc.geturl())
        except urllib.error.URLError as exc:
            raise AcceptanceError(f"request failed for {url}: {exc.reason}") from exc

    def has_session_cookie(self) -> bool:
        return any(c.name == SESSION_COOKIE and c.value for c in self.jar)

    def save_session(self) -> None:
        if not self.jar_path:
            return
        old = os.umask(0o077)
        try:
            self.jar.save(ignore_discard=True, ignore_expires=True)
        finally:
            os.umask(old)
        os.chmod(self.jar_path, 0o600)

    def sign_in(self, code: str) -> None:
        normalized = "".join(ch for ch in code.strip().upper() if ch.isalnum())
        check(len(normalized) == 10 and set(normalized) <= CODE_ALPHABET,
              "portal code must be 10 characters from the WS350 alphabet (no I, O, 0 or 1)")
        resp = self.request("/login", method="POST", form={"code": normalized}, follow_redirects=False)
        if resp.status == 429:
            raise AcceptanceError("sign-in is rate-limited; wait and read the current code from System -> Local Portal")
        check(resp.status == 303 and self.has_session_cookie(),
              f"sign-in failed (HTTP {resp.status}); check the code on System -> Local Portal")
        self.save_session()

    def session_valid(self) -> bool:
        if not self.has_session_cookie():
            return False
        resp = self.request("/api/portal-security", headers={"Accept": "application/json"})
        return resp.status == 200

    def sign_out(self) -> None:
        if self.has_session_cookie():
            self.request("/logout", method="POST")
        self.jar.clear()
        self.save_session()


CODE_KEY_ENV = "WORKSHOP_OS_CODE_KEY"
CODE_KEY_KEYCHAIN = ("ws350", "workshop-os-code-key")  # macOS login Keychain: account, service


def portal_code_key() -> str:
    """The device-issued wsc_ key for GET /api/portal-code, if this machine has one.

    Read from WORKSHOP_OS_CODE_KEY, else the macOS login Keychain, so it never
    appears in argv or a file. Returns "" when neither is set.
    """
    key = os.environ.get(CODE_KEY_ENV, "").strip()
    if key or sys.platform != "darwin":
        return key
    account, service = CODE_KEY_KEYCHAIN
    # posix_spawn, not subprocess: once urllib has run, macOS has loaded
    # CoreFoundation for the system proxy lookup, and a fork()ed child then
    # crashes before exec (security exited with SIGSEGV).
    read_end, write_end = os.pipe()
    try:
        actions = [(os.POSIX_SPAWN_DUP2, write_end, 1), (os.POSIX_SPAWN_CLOSE, read_end),
                   (os.POSIX_SPAWN_OPEN, 2, os.devnull, os.O_WRONLY, 0)]
        pid = os.posix_spawnp("security", ["security", "find-generic-password", "-a", account, "-s", service, "-w"],
                              os.environ, file_actions=actions)
    except OSError:
        os.close(read_end)
        os.close(write_end)
        return ""
    os.close(write_end)
    with os.fdopen(read_end, "rb") as out:
        value = out.read().decode("utf-8", "replace").strip()
    _, status = os.waitpid(pid, 0)
    return value if os.waitstatus_to_exitcode(status) == 0 else ""


def portal_code_from_key(base_url: str, key: str) -> str:
    req = urllib.request.Request(base_url.rstrip("/") + "/api/portal-code",
                                 headers={"Authorization": f"Bearer {key}", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            code = json.loads(resp.read()).get("code", "")
    except (urllib.error.URLError, OSError, ValueError) as exc:
        raise AcceptanceError(f"GET /api/portal-code with the sign-in code key failed: {exc}") from exc
    check(bool(code), "GET /api/portal-code returned no code; re-approve the key on the WS350")
    return code


def read_portal_code(prompt: str = "Portal code (System -> Local Portal on the WS350): ") -> str:
    if not sys.stdin.isatty():
        raise AcceptanceError("a portal code is required; run interactively or provide a signed-in "
                              f"{COOKIE_JAR_ENV} created by scripts/accept_os12_portal_runtime.py --sign-in")
    return getpass.getpass(prompt)


def runtime_identity(base_url: str) -> dict:
    """Running release version and exact source commit from the public probe."""
    resp = Client(base_url, anonymous=True).request("/recovery/status", headers={"Accept": "application/json"})
    check(resp.status == 200, f"GET /recovery/status returned HTTP {resp.status}")
    try:
        payload = json.loads(resp.body)
    except json.JSONDecodeError as exc:
        raise AcceptanceError("recovery status is not valid JSON") from exc
    commit = str(payload.get("runningSourceCommit", ""))
    check(len(commit) == 40 and all(c in "0123456789abcdef" for c in commit),
          "running firmware does not report runningSourceCommit on /recovery/status (pre-12.0.1 build?)")
    return {"releaseVersion": payload.get("releaseVersion"), "runningSourceCommit": commit}


def assert_unauthenticated_contract(base_url: str) -> None:
    """Prove the signed-out boundary. Never touches control or side-effect routes."""
    anon = Client(base_url, follow_redirects=False, anonymous=True)

    root = anon.request("/")
    location = root.headers.get("Location") if root.headers else None
    check(root.status == 303 and location == "/login",
          f"signed-out GET / returned HTTP {root.status} Location={location!r}, expected 303 -> /login")

    login = anon.request("/login")
    check(login.status == 200 and "name='code'" in login.body, "custom /login page with a code field is missing")

    for path in ("/status?slot=0", "/hardware/health?slot=0", "/os12/update/status"):
        resp = anon.request(path, headers={"Accept": "application/json"})
        check(resp.status == 401, f"signed-out GET {path} returned HTTP {resp.status}, expected 401")

    legacy = anon.request("/api/portal-security", method="POST", form={"required": "1"},
                          headers={"X-BambuHelper-Client": "1", "Origin": ""})
    # Without Origin/Referer the marker header must not count as same-origin,
    # so the firmware refuses with 403 before it even looks for a session.
    check(legacy.status == 403,
          f"signed-out mutation with only X-BambuHelper-Client returned HTTP {legacy.status}, expected 403")

    forged = anon.request("/api/portal-security", method="POST", form={"required": "1"},
                          headers={"X-BambuHelper-Client": "1"})
    check(forged.status == 401, f"signed-out same-origin mutation returned HTTP {forged.status}, expected 401")

    cross = anon.request("/api/portal-security", method="POST", form={"required": "1"},
                         headers={"Origin": "http://invalid.example"})
    check(cross.status == 403, f"cross-origin mutation returned HTTP {cross.status}, expected 403")


def establish_portal_session(client: Client, *, fresh_code: bool = False) -> str:
    """Check the signed-out boundary, sign in (or reuse the shared session) and
    return the portal mode for evidence. ``fresh_code`` forces a new code, e.g.
    after a reboot rotated it."""
    assert_unauthenticated_contract(client.base_url)
    if fresh_code or not client.session_valid():
        client.jar.clear()
        prompt = ("New portal code after reboot (System -> Local Portal): " if fresh_code
                  else "Portal code (System -> Local Portal on the WS350): ")
        key = portal_code_key()
        if key:
            print("Signing in with the WS350 sign-in code key (GET /api/portal-code)")
            client.sign_in(portal_code_from_key(client.base_url, key))
        else:
            client.sign_in(read_portal_code(prompt))
    resp = client.request("/api/portal-security", headers={"Accept": "application/json"})
    check(resp.status == 200, f"signed-in GET /api/portal-security returned HTTP {resp.status}")
    try:
        policy = json.loads(resp.body)
    except json.JSONDecodeError as exc:
        raise AcceptanceError("portal security status is not valid JSON") from exc
    check(policy.get("mutationsRequireSession") is True, "mutationsRequireSession is not true")
    check(policy.get("sameOriginProtection") is True, "sameOriginProtection is not true")
    mode = policy.get("authMode")
    check(mode in ("portal-code", "open-readonly"), f"unexpected authMode: {mode!r}")
    return "session-required" if mode == "portal-code" else "session-required-open-status"


def run(args: argparse.Namespace) -> int:
    base = args.base_url.rstrip("/")
    check(base.startswith(("http://", "https://")), "--base-url must start with http:// or https://")
    print(f"Target: {base}")

    if args.sign_out:
        Client(base).sign_out()
        print("Signed out; shared session cleared")
        return 0

    assert_unauthenticated_contract(base)
    print("PASS  signed-out GET / redirects to the custom /login page")
    print("PASS  signed-out GET /status, /hardware/health and /os12/update/status answer 401")
    print("PASS  signed-out mutations are refused, including with X-BambuHelper-Client: 1")
    print("PASS  cross-origin mutation is rejected")
    if args.probe_only:
        print()
        print("RUNTIME PORTAL SIGN-IN BOUNDARY (PROBE): PASS")
        return 0

    client = Client(base)
    mode = establish_portal_session(client)
    print(f"PASS  signed in; portal mode {mode}; mutations require a session and same-origin provenance")
    if args.sign_in:
        check(client.jar_path is not None, f"--sign-in needs {COOKIE_JAR_ENV} to name an owner-only cookie jar")
        print(f"Shared session stored in {client.jar_path}")
    print()
    print("RUNTIME PORTAL SIGN-IN ACCEPTANCE SUBSET: PASS")
    print("This does not constitute whole-device physical acceptance.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default=os.environ.get("WORKSHOP_OS_URL", "http://10.0.0.124"),
                        help="Workshop OS device URL")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--probe-only", action="store_true", help="signed-out boundary checks only; no code needed")
    mode.add_argument("--sign-in", action="store_true", help=f"sign in once and keep the session in ${COOKIE_JAR_ENV}")
    mode.add_argument("--sign-out", action="store_true", help=f"revoke the session in ${COOKIE_JAR_ENV}")
    args = parser.parse_args()
    try:
        return run(args)
    except AcceptanceError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
