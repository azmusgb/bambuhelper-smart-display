#!/usr/bin/env python3
"""Host test for the signed-in OS12 acceptance client (no device needed).

A loopback fake WS350 implements the 12.0.1 portal policy. The test proves:

* the signed-out boundary check passes against a compliant device and FAILS
  against a device that still serves /status anonymously (the 12.0.0 code-free
  behaviour) or accepts the X-BambuHelper-Client shortcut;
* sign-in posts the code only in the request body, stores just the session
  cookie in an owner-only (0600) jar, and the jar is reused by a second client;
* every mutation carries the device's own Origin and never the marker header;
* runtime identity is read from the public /recovery/status probe;
* sign-out revokes the session;
* sign-in itself needs the device's own Origin (12.3.8), and a device that
  takes a cross-site sign-in is detected.
"""
from __future__ import annotations

import http.server
import json
import os
import stat
import sys
import tempfile
import threading
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import accept_os12_portal_runtime as portal  # noqa: E402

CODE = "ABCDEFGHJK"
SOURCE = "0123456789abcdef0123456789abcdef01234567"


class FakeDevice(http.server.BaseHTTPRequestHandler):
    sessions: set[str] = set()
    seen: list[dict] = []
    code_free = False  # emulate the retired 12.0.0 overlay
    trust_marker = False  # emulate the retired X-BambuHelper-Client shortcut
    login_cross_site_open = False  # emulate 12.3.7 and earlier: /login took any origin

    def log_message(self, *args):  # quiet
        pass

    def _session(self) -> bool:
        cookie = self.headers.get("Cookie", "")
        for part in cookie.split(";"):
            name, _, value = part.strip().partition("=")
            if name == "BHSESSION" and value in self.sessions:
                return True
        return False

    def _same_origin(self) -> bool:
        if self.trust_marker and self.headers.get("X-BambuHelper-Client") == "1":
            return True
        host = self.headers.get("Host", "")
        origin = self.headers.get("Origin")
        return origin is not None and origin.lower() == f"http://{host}".lower()

    def _send(self, code: int, body: str = "", ctype: str = "application/json", headers: dict | None = None):
        raw = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(raw)))
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(raw)

    def _record(self, method: str, body: str = ""):
        self.seen.append({"method": method, "path": self.path, "headers": dict(self.headers), "body": body})

    def do_GET(self):
        self._record("GET")
        path = urllib.parse.urlparse(self.path).path
        if path == "/recovery/status":
            return self._send(200, json.dumps({"releaseVersion": "12.0.1", "runningSourceCommit": SOURCE}))
        if path == "/login":
            return self._send(200, "<form id='login-form'><input name='code'></form>", "text/html")
        if path == "/api/portal-code":
            if self.headers.get("Authorization") == f"Bearer {CODE_KEY}":
                return self._send(200, json.dumps({"bootId": "b1", "code": CODE}))
            return self._send(401, "", "text/plain", {"WWW-Authenticate": "Bearer"})
        if self.code_free or self._session():
            if path == "/api/portal-security":
                return self._send(200, json.dumps({"authMode": "portal-code", "mutationsRequireSession": True,
                                                   "sameOriginProtection": True}))
            return self._send(200, "{}")
        if path == "/":
            return self._send(303, "", "text/plain", {"Location": "/login"})
        return self._send(401, '{"status":"error"}')

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0") or 0)
        body = self.rfile.read(length).decode()
        self._record("POST", body)
        path = urllib.parse.urlparse(self.path).path
        if path == "/login":
            # 12.3.8: sign-in needs the device's own Origin like any mutation.
            if not self.login_cross_site_open and not self._same_origin():
                return self._send(403, '{"status":"error"}')
            code = urllib.parse.parse_qs(body).get("code", [""])[0]
            if code != CODE:
                return self._send(401, "bad", "text/html")
            token = "f" * 32
            self.sessions.add(token)
            return self._send(303, "", "text/plain",
                              {"Location": "/", "Set-Cookie": f"BHSESSION={token}; Path=/; HttpOnly; SameSite=Strict; Max-Age=28800"})
        if not self._same_origin():
            return self._send(403, '{"status":"error"}')
        if not (self.code_free or self._session()):
            return self._send(401, '{"status":"error"}')
        if path == "/logout":
            self.sessions.clear()
            return self._send(303, "", "text/plain", {"Location": "/login"})
        return self._send(200, '{"status":"ok"}')


def serve() -> tuple[http.server.ThreadingHTTPServer, str]:
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), FakeDevice)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_address[1]}"


def expect_failure(fn, label: str) -> None:
    try:
        fn()
    except portal.AcceptanceError:
        return
    raise SystemExit(f"FAIL: {label} was not detected")


CODE_KEY = "wsc_TESTKEY0000000000000000000"


def main() -> int:
    # Never consult a real key from the environment or the macOS Keychain.
    portal.portal_code_key = lambda: ""
    server, base = serve()
    try:
        with tempfile.TemporaryDirectory() as tmp:
            jar = os.path.join(tmp, "portal-session.cookies")
            os.environ[portal.COOKIE_JAR_ENV] = jar

            # Compliant device: signed-out boundary holds.
            portal.assert_unauthenticated_contract(base)

            # Sign in with an injected code (no TTY in tests).
            portal.read_portal_code = lambda prompt="": CODE.lower()
            client = portal.Client(base)
            mode = portal.establish_portal_session(client)
            assert mode == "session-required", mode
            assert os.path.exists(jar)
            assert stat.S_IMODE(os.stat(jar).st_mode) == 0o600, oct(os.stat(jar).st_mode)
            assert CODE not in Path(jar).read_text() and CODE.lower() not in Path(jar).read_text()

            # A second helper in the same run reuses the session without a code.
            portal.read_portal_code = lambda prompt="": (_ for _ in ()).throw(AssertionError("prompted twice"))
            second = portal.Client(base)
            assert second.session_valid()
            FakeDevice.seen.clear()
            resp = second.request("/hub/show", method="POST", form={"page": "home"})
            assert resp.status == 200, resp.status
            post = [r for r in FakeDevice.seen if r["method"] == "POST"][-1]
            assert post["headers"].get("Origin") == base, post["headers"]
            assert "X-BambuHelper-Client" not in post["headers"], post["headers"]

            # The code only ever travels in the /login body.
            for record in FakeDevice.seen:
                assert CODE not in record["path"] and CODE not in json.dumps(record["headers"])

            # Identity without a session.
            ident = portal.runtime_identity(base)
            assert ident["runningSourceCommit"] == SOURCE

            # Sign-out revokes.
            second.sign_out()
            assert not portal.Client(base).session_valid()

            # With a sign-in code key, the helper fetches the code itself and never prompts.
            portal.portal_code_key = lambda: CODE_KEY
            portal.read_portal_code = lambda prompt="": (_ for _ in ()).throw(AssertionError("prompted despite key"))
            keyed = portal.Client(base)
            assert portal.establish_portal_session(keyed) == "session-required"
            assert keyed.session_valid()
            assert CODE_KEY not in Path(jar).read_text()
            expect_failure(lambda: portal.portal_code_from_key(base, "wsc_WRONG"), "wrong sign-in code key")
            keyed.sign_out()
            portal.portal_code_key = lambda: ""

            # Wrong code is refused.
            bad = portal.Client(base, anonymous=True)
            expect_failure(lambda: bad.sign_in("ZZZZZZZZZZ"), "wrong portal code")
            expect_failure(lambda: bad.sign_in("I0I0I0I0I0"), "code outside the WS350 alphabet")

            # A device with the retired code-free policy fails the boundary check.
            FakeDevice.code_free = True
            expect_failure(lambda: portal.assert_unauthenticated_contract(base), "anonymous /status (code-free)")
            FakeDevice.code_free = False

            # A device that trusts the marker header fails it too.
            FakeDevice.trust_marker = True
            FakeDevice.sessions.clear()
            expect_failure(lambda: portal.assert_unauthenticated_contract(base), "X-BambuHelper-Client shortcut")
            FakeDevice.trust_marker = False

            # 12.3.8: cross-site sign-in is refused, and detected when it is not.
            portal.assert_cross_site_sign_in_refused(base)
            FakeDevice.login_cross_site_open = True
            expect_failure(lambda: portal.assert_cross_site_sign_in_refused(base), "cross-site sign-in accepted")
            FakeDevice.login_cross_site_open = False
            assert portal.release_at_least("12.3.8", (12, 3, 8)) and portal.release_at_least("12.10.0", (12, 3, 8))
            assert not portal.release_at_least("12.3.7", (12, 3, 8)) and not portal.release_at_least("x", (12, 3, 8))

            # A world-readable jar is refused.
            Path(jar).write_text("# Netscape HTTP Cookie File\n")
            os.chmod(jar, 0o644)
            expect_failure(lambda: portal.Client(base), "world-readable cookie jar")
    finally:
        server.shutdown()
    print("PASS: signed-in acceptance client keeps the code out of storage, sends real Origin, "
          "never sends the marker header, and detects code-free or marker-trusting firmware")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
