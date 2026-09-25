#!/usr/bin/env python3
"""Harden the Workshop OS 12 local portal login without modifying frozen UI13.

This patch is intentionally applied *after* the reconstructed UI13 source and the
initial OS12 platform bridge. It keeps the existing portal-code trust model while
fixing validation/accessibility defects and strengthening brute-force/session
handling for the LAN portal.
"""
from __future__ import annotations

import argparse
from pathlib import Path
from scripts.smart_home_patch_utils import PatchError, fail, replace_once, replace_braced_block




def load(path: Path) -> str:
    if not path.exists():
        raise PatchError(f"missing {path}")
    return path.read_text(encoding="utf-8")


def block_end(text: str, start: int) -> int:
    brace = text.find("{", start)
    if brace < 0:
        raise PatchError("opening brace missing")
    depth = 0
    string: str | None = None
    escape = False
    line_comment = False
    block_comment = False
    i = brace
    while i < len(text):
        c = text[i]
        n = text[i + 1] if i + 1 < len(text) else ""
        if line_comment:
            if c == "\n":
                line_comment = False
        elif block_comment:
            if c == "*" and n == "/":
                block_comment = False
                i += 1
        elif string:
            if escape:
                escape = False
            elif c == "\\":
                escape = True
            elif c == string:
                string = None
        elif c == "/" and n == "/":
            line_comment = True
            i += 1
        elif c == "/" and n == "*":
            block_comment = True
            i += 1
        elif c in ('"', "'"):
            string = c
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    raise PatchError("unterminated braced block")


def replace_block(text: str, signature: str, replacement: str, label: str) -> str:
    start = text.find(signature)
    if start < 0:
        raise PatchError(f"{label}: signature missing")
    if text.find(signature, start + 1) >= 0:
        raise PatchError(f"{label}: signature is not unique")
    end = block_end(text, start)
    return text[:start] + replacement.rstrip() + text[end:]


SECURITY_HEADER_OLD = """bool securitySessionValid(WebServer& server);\nbool securityLogin(WebServer& server, const String& submittedCode);\nvoid securityLogout(WebServer& server);\nbool securityAuthorize(WebServer& server, bool mutating);"""

SECURITY_HEADER_NEW = """enum class SecurityLoginResult : uint8_t {\n  Success = 0,\n  InvalidCode,\n  RateLimited,\n};\n\nbool securitySessionValid(WebServer& server);\nSecurityLoginResult securityLogin(WebServer& server, const String& submittedCode, uint32_t& retryAfterSeconds);\nvoid securityLogout(WebServer& server);\nbool securityAuthorize(WebServer& server, bool mutating);"""

STATE_OLD = """constexpr char kCookieName[] = \"BHSESSION\";\nconstexpr size_t kSessionTokenLen = 32;  // 128 random bits as hex\n\nchar g_portalCode[kCodeLen + 1] = {};\nchar g_sessionToken[kSessionTokenLen + 1] = {};\nbool g_initialized = false;\nbool g_sessionTokenReady = false;"""

STATE_NEW = """constexpr char kCookieName[] = \"BHSESSION\";\nconstexpr size_t kSessionTokenLen = 32;  // 128 random bits as hex\nconstexpr size_t kMaxSessions = 6;\nconstexpr uint32_t kSessionTtlMs = 8UL * 60UL * 60UL * 1000UL;\nconstexpr size_t kRateLimitBuckets = 6;\nconstexpr uint8_t kFreeFailures = 2;\nconstexpr uint32_t kMaxBackoffMs = 60000UL;\n\nstruct SessionSlot {\n  char token[kSessionTokenLen + 1];\n  uint32_t expiresAtMs;\n  bool active;\n};\n\nstruct LoginRateBucket {\n  uint32_t clientKey;\n  uint32_t blockedUntilMs;\n  uint32_t lastSeenMs;\n  uint8_t failures;\n  bool active;\n};\n\nchar g_portalCode[kCodeLen + 1] = {};\nSessionSlot g_sessions[kMaxSessions] = {};\nLoginRateBucket g_loginRate[kRateLimitBuckets] = {};\nsize_t g_nextSessionSlot = 0;\nbool g_initialized = false;"""

SESSION_HELPERS = r'''void generateSessionToken(char* out) {
  if (!out) return;
  for (size_t i = 0; i < 4; ++i) {
    const uint32_t r = esp_random();
    snprintf(out + i * 8, 9, "%08lx", (unsigned long)r);
  }
  out[kSessionTokenLen] = '\0';
}

bool deadlinePending(uint32_t now, uint32_t deadline) {
  return static_cast<int32_t>(deadline - now) > 0;
}

uint32_t clientKey(WebServer& server) {
  const auto ip = server.client().remoteIP();
  return (static_cast<uint32_t>(ip[0]) << 24) |
         (static_cast<uint32_t>(ip[1]) << 16) |
         (static_cast<uint32_t>(ip[2]) << 8) |
         static_cast<uint32_t>(ip[3]);
}

LoginRateBucket& rateBucketFor(WebServer& server) {
  const uint32_t key = clientKey(server);
  const uint32_t now = millis();
  LoginRateBucket* replacement = &g_loginRate[0];
  uint32_t replacementAge = 0;

  for (size_t i = 0; i < kRateLimitBuckets; ++i) {
    LoginRateBucket& bucket = g_loginRate[i];
    if (bucket.active && bucket.clientKey == key) {
      bucket.lastSeenMs = now;
      return bucket;
    }
    if (!bucket.active) {
      replacement = &bucket;
      replacementAge = 0xFFFFFFFFUL;
      break;
    }
    const uint32_t age = now - bucket.lastSeenMs;
    if (age >= replacementAge) {
      replacement = &bucket;
      replacementAge = age;
    }
  }

  *replacement = {};
  replacement->active = true;
  replacement->clientKey = key;
  replacement->lastSeenMs = now;
  return *replacement;
}

uint32_t retryAfterSeconds(WebServer& server) {
  LoginRateBucket& bucket = rateBucketFor(server);
  const uint32_t now = millis();
  if (!deadlinePending(now, bucket.blockedUntilMs)) return 0;
  const uint32_t remainingMs = bucket.blockedUntilMs - now;
  return (remainingMs + 999UL) / 1000UL;
}

void noteLoginFailure(WebServer& server) {
  LoginRateBucket& bucket = rateBucketFor(server);
  if (bucket.failures < 15) ++bucket.failures;
  if (bucket.failures <= kFreeFailures) return;

  uint8_t shift = bucket.failures - kFreeFailures - 1;
  if (shift > 6) shift = 6;
  uint32_t backoffMs = 1000UL << shift;
  if (backoffMs > kMaxBackoffMs) backoffMs = kMaxBackoffMs;
  bucket.blockedUntilMs = millis() + backoffMs;
}

void noteLoginSuccess(WebServer& server) {
  LoginRateBucket& bucket = rateBucketFor(server);
  bucket.failures = 0;
  bucket.blockedUntilMs = 0;
}

bool normalizePortalCode(const String& submittedCode, String& normalized) {
  normalized = submittedCode;
  normalized.trim();
  normalized.toUpperCase();
  if (normalized.length() != kCodeLen) return false;
  for (size_t i = 0; i < kCodeLen; ++i) {
    if (strchr(kAlphabet, normalized[i]) == nullptr) return false;
  }
  return true;
}'''

COOKIE_MATCHES_NEW = r'''bool cookieValue(WebServer& server, String& value) {
  String cookie = server.header("Cookie");
  if (cookie.length() == 0) return false;

  const String needle = String(kCookieName) + "=";
  int pos = cookie.indexOf(needle);
  while (pos >= 0) {
    if (pos == 0 || cookie[pos - 1] == ' ' || cookie[pos - 1] == ';') {
      const int valueStart = pos + needle.length();
      int valueEnd = cookie.indexOf(';', valueStart);
      if (valueEnd < 0) valueEnd = cookie.length();
      value = cookie.substring(valueStart, valueEnd);
      value.trim();
      return value.length() == kSessionTokenLen;
    }
    pos = cookie.indexOf(needle, pos + 1);
  }
  return false;
}

bool cookieMatches(WebServer& server) {
  String value;
  if (!cookieValue(server, value)) return false;

  const uint32_t now = millis();
  for (size_t i = 0; i < kMaxSessions; ++i) {
    SessionSlot& slot = g_sessions[i];
    if (!slot.active) continue;
    if (!deadlinePending(now, slot.expiresAtMs)) {
      memset(slot.token, 0, sizeof(slot.token));
      slot.active = false;
      continue;
    }
    if (constantTimeEqual(value.c_str(), slot.token)) return true;
  }
  return false;
}'''

ISSUE_COOKIE_NEW = r'''void issueSessionCookie(WebServer& server) {
  SessionSlot& slot = g_sessions[g_nextSessionSlot];
  g_nextSessionSlot = (g_nextSessionSlot + 1) % kMaxSessions;
  memset(slot.token, 0, sizeof(slot.token));
  generateSessionToken(slot.token);
  slot.expiresAtMs = millis() + kSessionTtlMs;
  slot.active = true;

  String cookie = String(kCookieName) + "=" + slot.token +
      "; Path=/; HttpOnly; SameSite=Strict; Max-Age=28800";
  server.sendHeader("Set-Cookie", cookie);
  server.sendHeader("Cache-Control", "no-store");
}'''

LOGIN_NEW = r'''SecurityLoginResult securityLogin(WebServer& server, const String& submittedCode, uint32_t& retryAfterSecondsOut) {
  ensureInitialized();
  retryAfterSecondsOut = retryAfterSeconds(server);
  if (retryAfterSecondsOut > 0) return SecurityLoginResult::RateLimited;

  String code;
  if (!normalizePortalCode(submittedCode, code) ||
      !constantTimeEqual(code.c_str(), g_portalCode)) {
    noteLoginFailure(server);
    retryAfterSecondsOut = retryAfterSeconds(server);
    return retryAfterSecondsOut > 0 ? SecurityLoginResult::RateLimited
                                    : SecurityLoginResult::InvalidCode;
  }

  noteLoginSuccess(server);
  issueSessionCookie(server);
  retryAfterSecondsOut = 0;
  return SecurityLoginResult::Success;
}'''

LOGOUT_NEW = r'''void securityLogout(WebServer& server) {
  ensureInitialized();
  String value;
  if (cookieValue(server, value)) {
    for (size_t i = 0; i < kMaxSessions; ++i) {
      SessionSlot& slot = g_sessions[i];
      if (slot.active && constantTimeEqual(value.c_str(), slot.token)) {
        memset(slot.token, 0, sizeof(slot.token));
        slot.active = false;
      }
    }
  }
  expireSessionCookie(server);
}'''

LOGIN_PAGE_NEW = r'''enum class PortalLoginPageState : uint8_t {
  Ready = 0,
  InvalidCode,
  RateLimited,
};

static void sendPortalLoginPage(PortalLoginPageState state = PortalLoginPageState::Ready, uint32_t retryAfterSeconds = 0) {
  const bool hasError = state != PortalLoginPageState::Ready;
  const bool limited = state == PortalLoginPageState::RateLimited && retryAfterSeconds > 0;
  String html;
  html.reserve(6200);
  html += F("<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
            "<meta name='color-scheme' content='dark'><title>Workshop OS Device Access</title><style>"
            ":root{color-scheme:dark;--bg:#0b0e10;--surface:#121719;--surface2:#171e20;--line:#2a3436;--text:#f4f7f6;--muted:#98a6a3;--accent:#20b7a8;--danger:#ef7676;}"
            "*{box-sizing:border-box}body{margin:0;min-height:100vh;background:var(--bg);color:var(--text);font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;}"
            ".wrap{max-width:430px;margin:0 auto;padding:40px 22px}.eyebrow{color:var(--accent);font-size:12px;font-weight:800;letter-spacing:.12em;text-transform:uppercase;margin:0 0 10px}"
            ".brand{font-weight:800;font-size:29px;letter-spacing:-.02em;margin:0 0 8px}.sub{color:var(--muted);line-height:1.5;margin:0 0 24px}"
            ".card{background:var(--surface);border:1px solid var(--line);border-radius:18px;padding:22px;box-shadow:0 14px 40px #0008}"
            "label{display:block;font-weight:700;margin-bottom:10px}.help{color:var(--muted);font-size:13px;line-height:1.45;margin:0 0 10px}"
            "input{width:100%;min-height:52px;font-size:22px;letter-spacing:.14em;text-transform:uppercase;background:var(--surface2);color:var(--text);border:1px solid #3b494b;border-radius:12px;padding:13px 14px;outline:2px solid transparent;outline-offset:2px}"
            "input:focus{border-color:var(--accent);outline-color:#20b7a855}input:focus-visible{box-shadow:0 0 0 3px #20b7a833;outline-color:#8ff4e8}"
            "button{width:100%;min-height:52px;margin-top:16px;border:1px solid #37c9bb;border-radius:12px;padding:13px;background:var(--accent);color:#06110f;font-size:17px;font-weight:800;cursor:pointer;transition:filter .14s ease,opacity .14s ease}"
            "button:focus{outline:3px solid #8ff4e8;outline-offset:3px}button:focus:not(:focus-visible){outline-color:transparent}button:focus-visible{outline-color:#8ff4e8}"
            "button:active:not(:disabled){opacity:.86}button:disabled,button[aria-busy='true']{opacity:.55;cursor:default}"
            "@media(hover:hover) and (pointer:fine){button:hover:not(:disabled){filter:brightness(1.07)}}"
            ".hint{color:var(--muted);font-size:14px;line-height:1.5;margin:16px 0 0}.err{background:#351c1f;color:#ffd0d0;border:1px solid #74343b;border-radius:10px;padding:11px 12px;margin:0 0 15px}"
            ".sr{position:absolute!important;width:1px!important;height:1px!important;padding:0!important;margin:-1px!important;overflow:hidden!important;clip:rect(0,0,0,0)!important;white-space:nowrap!important;border:0!important}"
            "@media(prefers-reduced-motion:reduce){*{scroll-behavior:auto!important;transition:none!important}}@media(forced-colors:active){input,button,.card{forced-color-adjust:auto;border:1px solid CanvasText}}"
            "</style></head><body><main class='wrap'><p class='eyebrow'>Local device access</p><h1 class='brand'>Workshop OS</h1>"
            "<p class='sub'>Enter the current portal code shown on the physical System screen. Access stays on this device and the code changes after a reboot.</p><section class='card' aria-labelledby='login-title'>"
            "<h2 id='login-title' class='sr'>Sign in to Workshop OS</h2>");

  if (state == PortalLoginPageState::InvalidCode) {
    html += F("<p class='err' role='alert' id='code-error'>That portal code was not accepted. Check System on the WS350 and try again.</p>");
  } else if (limited) {
    html += F("<p class='err' role='alert' id='code-error'>Too many unsuccessful attempts. Try again in <span id='retry-seconds'>");
    html += String(retryAfterSeconds);
    html += F("</span> seconds.</p>");
  }

  html += F("<form id='login-form' method='post' action='/login'><label for='code'>Portal code</label>"
            "<p class='help' id='code-help'>10 characters: letters and digits 2-9. I, O, 0, and 1 are not used.</p>"
            "<input id='code' name='code' maxlength='10' minlength='10' pattern='[ABCDEFGHJKLMNPQRSTUVWXYZabcdefghjklmnpqrstuvwxyz23456789]{10}' inputmode='text' autocomplete='off' autocorrect='off' autocapitalize='characters' spellcheck='false' title='10 characters: letters and digits 2-9, excluding I, O, 0, and 1' aria-describedby='code-help");
  if (hasError) html += F(" code-error' aria-invalid='true");
  html += F("' autofocus required>"
            "<button id='submit' type='submit'");
  if (limited) {
    html += F(" disabled aria-disabled='true' data-retry='");
    html += String(retryAfterSeconds);
    html += F("'");
  }
  html += F(">Continue</button><p id='submit-status' class='sr' aria-live='polite'></p></form>"
            "<p class='hint'>No Bambu account, printer access code, or cloud password is requested here.</p></section></main>"
            "<script>(function(){var f=document.getElementById('login-form'),i=document.getElementById('code'),b=document.getElementById('submit'),s=document.getElementById('submit-status'),r=document.getElementById('retry-seconds');"
            "if(i){i.addEventListener('input',function(){this.value=this.value.toUpperCase();});}"
            "if(f&&b){f.addEventListener('submit',function(){if(b.disabled)return;b.disabled=true;b.setAttribute('aria-busy','true');b.textContent='Signing in...';if(s)s.textContent='Signing in...';});}"
            "var left=b?parseInt(b.getAttribute('data-retry')||'0',10):0;if(b&&left>0){var tick=function(){if(left<=0){b.disabled=false;b.removeAttribute('aria-disabled');b.removeAttribute('data-retry');b.textContent='Continue';if(r)r.textContent='0';if(s)s.textContent='You can try again now.';clearInterval(timer);return;}b.textContent='Try again in '+left+'s';if(r)r.textContent=String(left);left-=1;};tick();var timer=setInterval(tick,1000);}"
            "window.addEventListener('pageshow',function(){if(b&&!(parseInt(b.getAttribute('data-retry')||'0',10)>0)){b.disabled=false;b.removeAttribute('aria-busy');b.textContent='Continue';}});})();</script></body></html>");

  server.sendHeader("Cache-Control", "no-store");
  server.sendHeader("Pragma", "no-cache");
  server.sendHeader("X-Content-Type-Options", "nosniff");
  server.sendHeader("Referrer-Policy", "no-referrer");
  if (limited) server.sendHeader("Retry-After", String(retryAfterSeconds));
  server.send(limited ? 429 : (state == PortalLoginPageState::InvalidCode ? 401 : 200), "text/html", html);
}'''

LOGIN_GET_NEW = r'''static void handlePortalLoginPage() {
  if (securitySessionValid(server)) {
    server.sendHeader("Location", "/");
    server.send(303, "text/plain", "Already signed in");
    return;
  }
  sendPortalLoginPage();
}'''

LOGIN_SUBMIT_NEW = r'''static void handlePortalLoginSubmit() {
  if (!server.hasArg("code")) {
    sendPortalLoginPage(PortalLoginPageState::InvalidCode);
    return;
  }

  uint32_t retryAfterSeconds = 0;
  const SecurityLoginResult result = securityLogin(server, server.arg("code"), retryAfterSeconds);
  if (result == SecurityLoginResult::RateLimited) {
    sendPortalLoginPage(PortalLoginPageState::RateLimited, retryAfterSeconds);
    return;
  }
  if (result != SecurityLoginResult::Success) {
    sendPortalLoginPage(PortalLoginPageState::InvalidCode);
    return;
  }

  server.sendHeader("Location", "/");
  server.send(303, "text/plain", "Signed in");
}'''


def patch_security_header(repo: Path) -> None:
    path = repo / "include" / "security_manager.h"
    text = load(path)
    if "SecurityLoginResult" in text:
        return
    text = replace_once(text, SECURITY_HEADER_OLD, SECURITY_HEADER_NEW, "security login API")
    path.write_text(text, encoding="utf-8")


def patch_security_cpp(repo: Path) -> None:
    path = repo / "src" / "security_manager.cpp"
    text = load(path)
    if "kRateLimitBuckets" in text and "kMaxSessions" in text:
        return

    text = replace_once(text, STATE_OLD, STATE_NEW, "session/rate-limit state")
    text = replace_block(text, "void ensureSessionToken()", SESSION_HELPERS, "session helper replacement")
    text = replace_block(
        text,
        "void ensureInitialized()",
        r'''void ensureInitialized() {
  if (g_initialized) return;
  generatePortalCode();
  g_initialized = true;

  Serial.println();
  Serial.println("Workshop OS portal session security enabled");
  Serial.println("The code changes after every reboot and is shown on the System screen.");
}''',
        "security initialization",
    )
    text = replace_block(text, "bool cookieMatches(WebServer& server)", COOKIE_MATCHES_NEW, "cookie matching")
    text = replace_block(text, "void issueSessionCookie(WebServer& server)", ISSUE_COOKIE_NEW, "session cookie issuance")
    text = replace_block(text, "bool securityLogin(WebServer& server, const String& submittedCode)", LOGIN_NEW, "login result/rate limit")
    text = replace_block(text, "void securityLogout(WebServer& server)", LOGOUT_NEW, "per-session logout")

    forbidden = (
        "g_sessionToken",
        "g_sessionTokenReady",
        "ensureSessionToken()",
        "Max-Age=86400",
    )
    for needle in forbidden:
        if needle in text:
            raise PatchError(f"stale session implementation remains: {needle}")

    required = (
        'constexpr char kAlphabet[] = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789";',
        "normalizePortalCode",
        "strchr(kAlphabet, normalized[i])",
        "kRateLimitBuckets",
        "kMaxBackoffMs = 60000UL",
        "kMaxSessions = 6",
        "SameSite=Strict; Max-Age=28800",
        "SecurityLoginResult::RateLimited",
    )
    for needle in required:
        if needle not in text:
            raise PatchError(f"required security hardening marker missing: {needle}")

    path.write_text(text, encoding="utf-8")


def patch_web_server(repo: Path) -> None:
    path = repo / "src" / "web_server.cpp"
    text = load(path)
    if "PortalLoginPageState" in text and "Local device access" in text:
        return

    text = replace_block(text, "static void sendPortalLoginPage(bool badCode = false)", LOGIN_PAGE_NEW, "login page UX")
    text = replace_block(text, "static void handlePortalLoginPage()", LOGIN_GET_NEW, "login GET")
    text = replace_block(text, "static void handlePortalLoginSubmit()", LOGIN_SUBMIT_NEW, "login POST")

    forbidden = (
        "Workshop OS Secure Sign In",
        "Secure LAN access",
        "Sign in securely",
        "autocomplete='one-time-code'",
        "pattern='[ABCDEFGHJKLMNPQRSTUVWXYZ23456789]{10}'",
        "font-weight:820",
        "font-weight:850",
    )
    for needle in forbidden:
        if needle in text:
            raise PatchError(f"stale login page marker remains: {needle}")

    required = (
        "<html lang='en'>",
        "<meta charset='utf-8'>",
        "Local device access",
        "autocomplete='off'",
        "autocorrect='off'",
        "aria-describedby='code-help",
        "aria-invalid='true",
        "role='alert'",
        "aria-live='polite'",
        "aria-busy",
        "button:disabled",
        "button:active:not(:disabled)",
        "@media(hover:hover) and (pointer:fine)",
        "Retry-After",
        "PortalLoginPageState::RateLimited",
        "[ABCDEFGHJKLMNPQRSTUVWXYZabcdefghjklmnpqrstuvwxyz23456789]{10}",
        "this.value=this.value.toUpperCase()",
    )
    for needle in required:
        if needle not in text:
            raise PatchError(f"required login UX marker missing: {needle}")

    path.write_text(text, encoding="utf-8")


def apply(repo: Path) -> None:
    build = repo / "include" / "smart_home_build.h"
    if not build.exists():
        raise PatchError(f"missing reconstructed source: {build}")
    build_text = load(build)
    if "WORKSHOP_OS_V11_28_UI13" not in build_text:
        raise PatchError("OS12 portal hardening requires the reconstructed UI13 baseline")

    patch_security_header(repo)
    patch_security_cpp(repo)
    patch_web_server(repo)
    print("Workshop OS 12 portal login hardening applied")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    if not args.apply:
        raise SystemExit("refusing to modify source without --apply")
    try:
        apply(Path(args.repo).resolve())
    except PatchError as exc:
        raise SystemExit(f"FAIL: {exc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
