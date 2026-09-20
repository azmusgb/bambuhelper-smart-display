#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
import re
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATCHER = ROOT / "apply_workshop_os12_portal_login_hardening.py"


def fail(message: str) -> None:
    raise SystemExit(f"FAIL: {message}")


def load_patcher():
    spec = importlib.util.spec_from_file_location("os12_portal_login", PATCHER)
    if spec is None or spec.loader is None:
        fail("unable to load OS12 portal-login patcher")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def need(text: str, needle: str, label: str) -> None:
    if needle not in text:
        fail(f"missing {label}: {needle}")


def forbid(text: str, needle: str, label: str) -> None:
    if needle in text:
        fail(f"forbidden {label}: {needle}")


def synthetic_security() -> str:
    return r'''#include "security_manager.h"
#include "wifi_manager.h"
#include "recovery_manager.h"
#include <WebServer.h>
#include <esp_system.h>
#include <cstring>

namespace {
constexpr char kUsername[] = "admin";
constexpr char kAlphabet[] = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789";
constexpr size_t kAlphabetLen = sizeof(kAlphabet) - 1;
constexpr size_t kCodeLen = 10;
constexpr char kCookieName[] = "BHSESSION";
constexpr size_t kSessionTokenLen = 32;  // 128 random bits as hex

char g_portalCode[kCodeLen + 1] = {};
char g_sessionToken[kSessionTokenLen + 1] = {};
bool g_initialized = false;
bool g_sessionTokenReady = false;

void generatePortalCode() {
  static_assert(kAlphabetLen == 32, "portal alphabet must contain 32 symbols");
}

void ensureSessionToken() {
  if (g_sessionTokenReady) return;
  g_sessionTokenReady = true;
}

void ensureInitialized() {
  if (g_initialized) return;
  generatePortalCode();
  ensureSessionToken();
  g_initialized = true;
  Serial.println();
  Serial.println("Workshop OS portal session security enabled");
  Serial.println("The code changes after every reboot and is shown on the System screen.");
}

bool constantTimeEqual(const char* a, const char* b) {
  return a && b;
}

bool cookieMatches(WebServer& server) {
  if (!g_sessionTokenReady) return false;
  String cookie = server.header("Cookie");
  if (cookie.length() == 0) return false;
  return constantTimeEqual(cookie.c_str(), g_sessionToken);
}

bool sameOrigin(WebServer& server) {
  return server.header("Origin").length() > 0;
}

void issueSessionCookie(WebServer& server) {
  ensureSessionToken();
  String cookie = String(kCookieName) + "=" + g_sessionToken +
      "; Path=/; HttpOnly; SameSite=Strict; Max-Age=86400";
  server.sendHeader("Set-Cookie", cookie);
  server.sendHeader("Cache-Control", "no-store");
}

void expireSessionCookie(WebServer& server) {
  server.sendHeader("Set-Cookie",
      String(kCookieName) + "=; Path=/; HttpOnly; SameSite=Strict; Max-Age=0");
  server.sendHeader("Cache-Control", "no-store");
}
}  // namespace

bool securitySessionValid(WebServer& server) {
  ensureInitialized();
  return cookieMatches(server);
}

bool securityLogin(WebServer& server, const String& submittedCode) {
  ensureInitialized();
  String code = submittedCode;
  code.trim();
  code.toUpperCase();
  if (!constantTimeEqual(code.c_str(), g_portalCode)) return false;
  issueSessionCookie(server);
  return true;
}

void securityLogout(WebServer& server) {
  ensureInitialized();
  memset(g_sessionToken, 0, sizeof(g_sessionToken));
  g_sessionTokenReady = false;
  ensureSessionToken();
  expireSessionCookie(server);
}

bool securityAuthorize(WebServer& server, bool mutating) {
  if (!cookieMatches(server)) return false;
  if (mutating && !sameOrigin(server)) return false;
  return true;
}
'''


def synthetic_web() -> str:
    return r'''static void sendPortalLoginPage(bool badCode = false) {
  String html;
  html.reserve(3600);
  html += F("<!doctype html><html><head><meta name='viewport' content='width=device-width,initial-scale=1'>"
            "<meta name='color-scheme' content='dark'><title>Workshop OS Secure Sign In</title><style>"
            ".brand{font-weight:820}button{font-weight:850}</style></head><body>"
            "<main><div>Secure LAN access</div></main>");
  if (badCode) html += F("<div class='err' role='alert'>Bad code</div>");
  html += F("<form method='post' action='/login'><input id='code' name='code' maxlength='10' minlength='10' pattern='[ABCDEFGHJKLMNPQRSTUVWXYZ23456789]{10}' autocomplete='one-time-code' autocapitalize='characters' spellcheck='false' autofocus required>"
            "<button type='submit'>Sign in securely</button></form></body></html>");
  server.sendHeader("Cache-Control", "no-store");
  server.send(badCode ? 401 : 200, "text/html", html);
}

static void handlePortalLoginPage() {
  if (securitySessionValid(server)) {
    server.sendHeader("Location", "/");
    server.send(303, "text/plain", "Already signed in");
    return;
  }
  sendPortalLoginPage(false);
}

static void handlePortalLoginSubmit() {
  if (!server.hasArg("code") || !securityLogin(server, server.arg("code"))) {
    sendPortalLoginPage(true);
    return;
  }
  server.sendHeader("Location", "/");
  server.send(303, "text/plain", "Signed in");
}
'''


def prepare_repo(root: Path, *, ui13: bool = True) -> None:
    (root / "include").mkdir(parents=True)
    (root / "src").mkdir(parents=True)
    (root / "include/smart_home_build.h").write_text(
        "#pragma once\n" + ("#define WORKSHOP_OS_V11_28_UI13 1\n" if ui13 else ""),
        encoding="utf-8",
    )
    (root / "include/security_manager.h").write_text(
        """#pragma once\n#include <Arduino.h>\nclass WebServer;\nbool securitySessionValid(WebServer& server);\nbool securityLogin(WebServer& server, const String& submittedCode);\nvoid securityLogout(WebServer& server);\nbool securityAuthorize(WebServer& server, bool mutating);\n""",
        encoding="utf-8",
    )
    (root / "src/security_manager.cpp").write_text(synthetic_security(), encoding="utf-8")
    (root / "src/web_server.cpp").write_text(synthetic_web(), encoding="utf-8")


def validate_output(repo: Path) -> None:
    build = (repo / "include/smart_home_build.h").read_text(encoding="utf-8")
    header = (repo / "include/security_manager.h").read_text(encoding="utf-8")
    security = (repo / "src/security_manager.cpp").read_text(encoding="utf-8")
    web = (repo / "src/web_server.cpp").read_text(encoding="utf-8")

    forbid(build, "#define WORKSHOP_OS_TEMP_NO_CODE_LAN", "temporary open-LAN build marker")
    forbid(
        security,
        "#if defined(WORKSHOP_OS_TEMP_NO_CODE_LAN) && WORKSHOP_OS_TEMP_NO_CODE_LAN",
        "temporary open-LAN authorization bypass",
    )
    forbid(security, "if (!isAPMode()) return true;", "station-LAN authentication bypass")

    for marker in (
        "enum class SecurityLoginResult : uint8_t",
        "SecurityLoginResult securityLogin",
    ):
        need(header, marker, "typed login API")

    for marker in (
        'constexpr char kAlphabet[] = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789";',
        "normalizePortalCode",
        "normalized.toUpperCase()",
        "strchr(kAlphabet, normalized[i])",
        "kRateLimitBuckets = 6",
        "kFreeFailures = 2",
        "kMaxBackoffMs = 60000UL",
        "retryAfterSeconds",
        "noteLoginFailure",
        "noteLoginSuccess",
        "kMaxSessions = 6",
        "kSessionTtlMs = 8UL * 60UL * 60UL * 1000UL",
        "generateSessionToken(slot.token)",
        "SameSite=Strict; Max-Age=28800",
        "SecurityLoginResult::RateLimited",
        "expireSessionCookie(server)",
    ):
        need(security, marker, "server authentication hardening")

    for marker in (
        "g_sessionToken",
        "g_sessionTokenReady",
        "ensureSessionToken()",
        "Max-Age=86400",
    ):
        forbid(security, marker, "legacy global-session behavior")

    for marker in (
        "<html lang='en'>",
        "<meta charset='utf-8'>",
        "<h1 class='brand'>Workshop OS</h1>",
        "<p class='eyebrow'>Local device access</p>",
        "id='code-help'",
        "aria-describedby='code-help",
        "aria-invalid='true",
        "role='alert'",
        "aria-live='polite'",
        "aria-busy",
        "autocomplete='off'",
        "autocorrect='off'",
        "button:disabled",
        "button:active:not(:disabled)",
        "@media(hover:hover) and (pointer:fine)",
        "Retry-After",
        "server.send(limited ? 429",
        "PortalLoginPageState::RateLimited",
        "this.value=this.value.toUpperCase()",
        "font-weight:800",
        "font-weight:700",
    ):
        need(web, marker, "login UX/accessibility contract")

    for marker in (
        "Workshop OS Secure Sign In",
        "Secure LAN access",
        "Sign in securely",
        "autocomplete='one-time-code'",
        "font-weight:820",
        "font-weight:850",
    ):
        forbid(web, marker, "stale/misleading login UX")

    server_match = re.search(r'constexpr char kAlphabet\[\] = "([A-Z0-9]+)";', security)
    pattern_match = re.search(r"pattern='\[([A-Za-z0-9]+)\]\{10\}'", web)
    if not server_match or not pattern_match:
        fail("unable to extract client/server portal alphabets")
    server_alphabet = server_match.group(1)
    client_symbols = pattern_match.group(1)
    expected_client = server_alphabet + "".join(ch.lower() for ch in server_alphabet if ch.isalpha())
    if set(client_symbols) != set(expected_client):
        fail("client pattern and server alphabet diverge")
    if any(ch in client_symbols for ch in "IOio01"):
        fail("ambiguous portal-code symbols are accepted by client pattern")


def validate_synthetic() -> None:
    patcher = load_patcher()
    with tempfile.TemporaryDirectory(prefix="os12-portal-login-") as tmp:
        repo = Path(tmp)
        prepare_repo(repo)
        patcher.apply(repo)
        patcher.apply(repo)
        validate_output(repo)

    with tempfile.TemporaryDirectory(prefix="os12-portal-login-no-ui13-") as tmp:
        repo = Path(tmp)
        prepare_repo(repo, ui13=False)
        try:
            patcher.apply(repo)
        except patcher.PatchError:
            pass
        else:
            fail("portal hardening applied without the required frozen UI13 baseline marker")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=None)
    args = ap.parse_args()

    if args.repo:
        validate_output(Path(args.repo).resolve())
        print("Workshop OS 12 portal login reconstructed-source validation passed")
    else:
        validate_synthetic()
        print("Workshop OS 12 portal login hardening validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
