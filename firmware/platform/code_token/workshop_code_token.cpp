#include "workshop_code_token.h"

#include "workshop_platform/code_token_core.hpp"
#include "workshop_status_lite.h"
#include "security_manager.h"
#include "smart_hub.h"
#include "wifi_manager.h"

#include <Preferences.h>
#include <WebServer.h>
#include <esp_system.h>
#include <mbedtls/sha256.h>

#include <cstring>

namespace {

using namespace workshop::codetoken;
using workshop::statuslite::ApprovalFlow;
using workshop::statuslite::ReadDecision;
using workshop::statuslite::ReadLimiter;
using workshop::statuslite::approvalPhaseName;
using workshop::statuslite::digestEmpty;
using workshop::statuslite::digestEqual;

constexpr char kNamespace[] = "workshop-sec";
constexpr char kDigestKey[] = "code_sha";

ReadLimiter g_limiter;
CodeApprovalFlow g_flow;
std::uint8_t g_digest[kDigestBytes] = {};
bool g_digestLoaded = false;
char g_bootId[kBootIdLength + 1] = {};

void secureZero(void* p, size_t n) {
  volatile std::uint8_t* b = static_cast<volatile std::uint8_t*>(p);
  while (n--) *b++ = 0;
}

bool sha256Text(const char* text, std::uint8_t out[kDigestBytes]) {
  mbedtls_sha256_context sha;
  mbedtls_sha256_init(&sha);
  const bool ok = mbedtls_sha256_starts_ret(&sha, 0) == 0 &&
                  mbedtls_sha256_update_ret(&sha, reinterpret_cast<const unsigned char*>(text), strlen(text)) == 0 &&
                  mbedtls_sha256_finish_ret(&sha, out) == 0;
  mbedtls_sha256_free(&sha);
  return ok;
}

void loadDigest() {
  if (g_digestLoaded) return;
  secureZero(g_digest, sizeof(g_digest));
  Preferences prefs;
  if (prefs.begin(kNamespace, true)) {
    if (prefs.getBytesLength(kDigestKey) == kDigestBytes) prefs.getBytes(kDigestKey, g_digest, kDigestBytes);
    prefs.end();
  }
  g_digestLoaded = true;
}

bool storeDigest(const std::uint8_t digest[kDigestBytes]) {
  Preferences prefs;
  if (!prefs.begin(kNamespace, false)) return false;
  const size_t written = prefs.putBytes(kDigestKey, digest, kDigestBytes);
  prefs.end();
  if (written != kDigestBytes) return false;
  memcpy(g_digest, digest, kDigestBytes);
  g_digestLoaded = true;
  return true;
}

void clearDigest() {
  Preferences prefs;
  if (prefs.begin(kNamespace, false)) {
    prefs.remove(kDigestKey);
    prefs.end();
  }
  secureZero(g_digest, sizeof(g_digest));
  g_digestLoaded = true;
}

bool keyConfigured() {
  loadDigest();
  return !digestEmpty(g_digest);
}

// Chosen once per boot, like the portal code itself.
const char* bootId() {
  while (!bootIdWellFormed(g_bootId)) formatBootId(esp_random(), esp_random(), g_bootId);
  return g_bootId;
}

uint32_t clientKey(WebServer& server) {
  const auto ip = server.client().remoteIP();
  return (static_cast<uint32_t>(ip[0]) << 24) | (static_cast<uint32_t>(ip[1]) << 16) |
         (static_cast<uint32_t>(ip[2]) << 8) | static_cast<uint32_t>(ip[3]);
}

void sendJson(WebServer& server, int code, const char* body) {
  server.sendHeader("Cache-Control", "no-store");
  server.sendHeader("X-Content-Type-Options", "nosniff");
  server.send(code, "application/json", body);
}

void sendRetry(WebServer& server, uint32_t seconds) {
  server.sendHeader("Retry-After", String(seconds ? seconds : 1));
  sendJson(server, 429, "{\"status\":\"error\",\"message\":\"Too many requests\"}");
}

}  // namespace

void workshopPortalCodeHandleRead(WebServer& server) {
  // Station Wi-Fi only; the setup/recovery AP never serves it.
  if (isAPMode()) {
    sendJson(server, 404, "{\"status\":\"error\",\"message\":\"Not available\"}");
    return;
  }

  // A client that is locked out of sign-in is locked out here too: this route
  // discloses the sign-in code, so it must not become a way around the
  // login back-off.
  const uint32_t lockedFor = securityLoginRetryAfter(server);
  if (lockedFor > 0) {
    sendRetry(server, lockedFor);
    return;
  }

  const uint32_t now = millis();
  const uint32_t client = clientKey(server);
  const ReadDecision gate = g_limiter.admit(client, now);
  if (!gate.allowed) {
    sendRetry(server, gate.retryAfterSeconds);
    return;
  }

  char presented[kTokenTextLength + 1] = {};
  std::uint8_t digest[kDigestBytes] = {};
  const String header = server.header("Authorization");
  const bool parsed = parseCodeBearer(header.c_str(), presented);
  const bool hashed = parsed && sha256Text(presented, digest);
  secureZero(presented, sizeof(presented));
  const bool valid = hashed && keyConfigured() && digestEqual(digest, g_digest);
  secureZero(digest, sizeof(digest));
  if (!valid) {
    // A wrong key is a failed sign-in attempt for this client.
    g_limiter.noteFailure(client, now);
    securityNoteLoginFailure(server);
    server.sendHeader("WWW-Authenticate", "Bearer realm=\"workshop-os-code\"");
    sendJson(server, 401, "{\"status\":\"error\",\"message\":\"A valid sign-in code key is required\"}");
    return;
  }
  g_limiter.noteSuccess(client, now);

  char body[kResponseBytes];
  const size_t length = serializePortalCode(securityPortalCode(), bootId(), body, sizeof(body));
  if (length == 0) {
    sendJson(server, 503, "{\"status\":\"error\",\"message\":\"Sign-in code unavailable\"}");
    return;
  }
  sendJson(server, 200, body);
  secureZero(body, sizeof(body));
}

void workshopCodeTokenHandleState(WebServer& server) {
  const uint32_t now = millis();
  String out = "{\"configured\":";
  out += keyConfigured() ? "true" : "false";
  out += ",\"phase\":\"";
  out += approvalPhaseName(g_flow.phase(now));
  out += "\",\"secondsLeft\":";
  out += String(g_flow.secondsLeft(now));
  out += ",\"route\":\"/api/portal-code\"}";
  sendJson(server, 200, out.c_str());
}

void workshopCodeTokenHandleCreate(WebServer& server) {
  // One question on the display at a time.
  if (workshopStatusTokenPromptVisible()) {
    sendJson(server, 409, "{\"status\":\"error\",\"message\":\"Another Local AI request is waiting on the display. Answer it first.\"}");
    return;
  }
  // The consent prompt lives on the touchscreen hub. Bring it forward (this
  // also wakes a sleeping panel); without the hub there is nobody to ask.
  if (!smartHubShowPage("home")) {
    sendJson(server, 409, "{\"status\":\"error\",\"message\":\"The touchscreen is not available to approve this request.\"}");
    return;
  }
  uint32_t requestId = esp_random();
  if (requestId == 0) requestId = 1;
  g_flow.start(requestId, millis());
  Serial.println("Code key: waiting for Allow on the touchscreen");
  String out = "{\"status\":\"pending\",\"requestId\":";
  out += String(requestId);
  out += ",\"secondsLeft\":";
  out += String(ApprovalFlow::kPromptMs / 1000U);
  out += "}";
  sendJson(server, 202, out.c_str());
}

void workshopCodeTokenHandleClaim(WebServer& server) {
  const uint32_t requestId = static_cast<uint32_t>(strtoul(server.arg("requestId").c_str(), nullptr, 10));
  char key[kTokenTextLength + 1] = {};
  if (!g_flow.claim(requestId, millis(), key)) {
    sendJson(server, 409, "{\"status\":\"error\",\"message\":\"No approved key is waiting for this request.\"}");
    return;
  }
  char body[96];
  snprintf(body, sizeof(body), "{\"status\":\"ok\",\"token\":\"%s\"}", key);
  secureZero(key, sizeof(key));
  sendJson(server, 200, body);
  secureZero(body, sizeof(body));
}

void workshopCodeTokenHandleRevoke(WebServer& server) {
  g_flow.cancel();
  clearDigest();
  g_limiter.reset();
  Serial.println("Code key: revoked");
  sendJson(server, 200, "{\"status\":\"ok\",\"configured\":false}");
}

bool workshopCodeTokenPromptVisible() {
  return g_flow.promptVisible(millis());
}

uint32_t workshopCodeTokenPromptSecondsLeft() {
  return g_flow.promptVisible(millis()) ? g_flow.secondsLeft(millis()) : 0;
}

bool workshopCodeTokenAllow() {
  const uint32_t now = millis();
  if (!g_flow.promptVisible(now)) return false;

  std::uint8_t random[kTokenRandomBytes];
  for (size_t i = 0; i < sizeof(random); i += 4) {
    const uint32_t r = esp_random();
    memcpy(random + i, &r, 4);
  }
  char key[kTokenTextLength + 1];
  encodeCodeToken(random, key);
  secureZero(random, sizeof(random));

  std::uint8_t digest[kDigestBytes];
  // Persist the new digest first: it replaces (revokes) any previous key.
  const bool ok = sha256Text(key, digest) && storeDigest(digest) && g_flow.approve(key, now);
  secureZero(digest, sizeof(digest));
  secureZero(key, sizeof(key));
  if (!ok) {
    g_flow.deny(now);
    Serial.println("Code key: could not be created");
    return false;
  }
  g_limiter.reset();
  Serial.println("Code key: approved on the touchscreen");
  return true;
}

void workshopCodeTokenDeny() {
  if (g_flow.deny(millis())) Serial.println("Code key: denied on the touchscreen");
}

bool workshopCodeTokenConfigured() {
  return keyConfigured();
}

void workshopCodeTokenFactoryReset() {
  g_flow.cancel();
  clearDigest();
}
