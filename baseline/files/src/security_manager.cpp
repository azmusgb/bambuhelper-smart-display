#include "security_manager.h"
#include "smart_home_build.h"

#if defined(WORKSHOP_OS_TEMP_NO_CODE_LAN)
#error "RC6 secure physical acceptance forbids WORKSHOP_OS_TEMP_NO_CODE_LAN"
#endif

#include "wifi_manager.h"
#include "recovery_manager.h"

#include <WebServer.h>
#include <esp_system.h>
#include <cstring>

// Legacy DIGEST_AUTH browser challenges are intentionally NOT used in RC3.
// The token appears here only as an upgrade/CI marker for the removed mechanism.

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
  uint32_t word = 0;
  uint8_t available = 0;
  for (size_t i = 0; i < kCodeLen; ++i) {
    if (available < 5) {
      word = esp_random();
      available = 32;
    }
    g_portalCode[i] = kAlphabet[word & 0x1FU];
    word >>= 5;
    available -= 5;
  }
  g_portalCode[kCodeLen] = '\0';
}

void ensureSessionToken() {
  if (g_sessionTokenReady) return;
  for (size_t i = 0; i < 4; ++i) {
    const uint32_t r = esp_random();
    snprintf(g_sessionToken + i * 8, 9, "%08lx", (unsigned long)r);
  }
  g_sessionToken[kSessionTokenLen] = '\0';
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
  if (!a || !b) return false;
  const size_t aLen = strlen(a);
  const size_t bLen = strlen(b);
  const size_t n = aLen > bLen ? aLen : bLen;
  unsigned char diff = static_cast<unsigned char>(aLen ^ bLen);
  for (size_t i = 0; i < n; ++i) {
    const unsigned char av = i < aLen ? static_cast<unsigned char>(a[i]) : 0;
    const unsigned char bv = i < bLen ? static_cast<unsigned char>(b[i]) : 0;
    diff |= av ^ bv;
  }
  return diff == 0;
}

bool cookieMatches(WebServer& server) {
  if (!g_sessionTokenReady) return false;
  String cookie = server.header("Cookie");
  if (cookie.length() == 0) return false;

  const String needle = String(kCookieName) + "=";
  int pos = cookie.indexOf(needle);
  while (pos >= 0) {
    if (pos == 0 || cookie[pos - 1] == ' ' || cookie[pos - 1] == ';') {
      const int valueStart = pos + needle.length();
      int valueEnd = cookie.indexOf(';', valueStart);
      if (valueEnd < 0) valueEnd = cookie.length();
      String value = cookie.substring(valueStart, valueEnd);
      value.trim();
      return constantTimeEqual(value.c_str(), g_sessionToken);
    }
    pos = cookie.indexOf(needle, pos + 1);
  }
  return false;
}

bool sameOrigin(WebServer& server) {
  // Explicit API clients may opt in after establishing a valid session. This
  // never bypasses authentication; it only replaces browser Origin semantics.
  if (server.header("X-BambuHelper-Client") == "1") return true;

  const String host = server.hostHeader();
  if (host.length() == 0) return false;

  String origin = server.header("Origin");
  origin.trim();
  if (origin.length() > 0) {
    const String httpOrigin = String("http://") + host;
    const String httpsOrigin = String("https://") + host;
    return origin.equalsIgnoreCase(httpOrigin) || origin.equalsIgnoreCase(httpsOrigin);
  }

  String referer = server.header("Referer");
  referer.trim();
  if (referer.length() > 0) {
    const String httpPrefix = String("http://") + host + "/";
    const String httpsPrefix = String("https://") + host + "/";
    return referer.startsWith(httpPrefix) || referer.startsWith(httpsPrefix);
  }

  return false;
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

void securityInit() {
  ensureInitialized();
}

const char* securityUsername() {
  return kUsername;
}

const char* securityPortalCode() {
  ensureInitialized();
  return g_portalCode;
}

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

static bool apPublicRouteAllowed(WebServer& server) {
  if (!isAPMode()) return false;

  const String uri = server.uri();

  // Captive setup AP: expose only what is necessary to join Wi-Fi and render
  // the local setup surface. A fallback into AP mode must never turn the
  // known-default AP password into an implicit printer-admin credential.
  if (uri == "/" || uri == "/save/wifi" ||
      uri == "/app.css" || uri == "/app.js") {
    return true;
  }

  // Recovery actions are unauthenticated only in deliberate Recovery Safe
  // Mode, which requires a physical recovery transition. Ordinary AP fallback
  // does not expose these routes. Settings export remains authenticated because
  // it can contain printer access codes and other secrets.
  if (recoverySafeModeActive()) {
    if (uri == "/recovery" || uri.startsWith("/recovery/") ||
        uri == "/ota/upload" || uri == "/reset") {
      return true;
    }
  }

  return false;
}

bool securityAuthorize(WebServer& server, bool mutating) {
  ensureInitialized();

  if (apPublicRouteAllowed(server)) {
    // Even rescue/setup mutations keep the browser provenance guard.
    if (mutating && !sameOrigin(server)) {
      server.send(403, "application/json",
          "{\"status\":\"error\",\"message\":\"Rejected by Workshop OS same-origin protection.\"}");
      return false;
    }
    return true;
  }

  if (!cookieMatches(server)) {
    server.sendHeader("Cache-Control", "no-store");
    if (server.method() == HTTP_GET) {
      // No WWW-Authenticate header: Safari must never show a native repeating
      // credential dialog. Interactive requests land on our stable login page.
      server.sendHeader("Location", "/login");
      server.send(303, "text/plain", "Sign in required");
    } else {
      server.send(401, "application/json",
          "{\"status\":\"error\",\"message\":\"Portal session expired. Reload and sign in again.\"}");
    }
    return false;
  }

  if (mutating && !sameOrigin(server)) {
    server.send(403, "application/json",
        "{\"status\":\"error\",\"message\":\"Rejected by Smart Home same-origin protection.\"}");
    return false;
  }

  return true;
}
