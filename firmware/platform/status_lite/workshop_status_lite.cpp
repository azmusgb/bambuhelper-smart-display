#include "workshop_status_lite.h"

#include "workshop_platform/status_lite_core.hpp"
#include "workshop_platform_bridge.h"
#include "bambu_state.h"
#include "config.h"
#include "hms_lookup.h"
#include "smart_home_build.h"
#include "smart_hub.h"
#include "wifi_manager.h"

#include <Preferences.h>
#include <WebServer.h>
#include <esp_system.h>
#include <mbedtls/sha256.h>

#include <cstring>

#ifndef WORKSHOP_OS_RELEASE_VERSION
#define WORKSHOP_OS_RELEASE_VERSION "unknown"
#endif
#ifndef WORKSHOP_OS_SOURCE_SHA
#define WORKSHOP_OS_SOURCE_SHA "unknown"
#endif

namespace {

using namespace workshop::statuslite;

constexpr char kNamespace[] = "workshop-sec";
constexpr char kDigestKey[] = "lite_sha";

ReadLimiter g_limiter;
ApprovalFlow g_flow;
std::uint8_t g_digest[kDigestBytes] = {};
bool g_digestLoaded = false;

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

bool tokenConfigured() {
  loadDigest();
  return !digestEmpty(g_digest);
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

PrinterSummary summarize(std::size_t slot, uint32_t nowMs, char* codeBuf, size_t codeBufSize) {
  const workshop::platform::PrinterState& state = workshopPlatformPrinterState(slot);
  PrinterSummary p;
  p.slot = static_cast<std::uint8_t>(slot);
  p.connection = state.connection;
  p.activity = state.activity;
  p.freshness = state.telemetryFreshness;
  p.ageKnown = state.observedAtMs != 0;
  p.ageSeconds = p.ageKnown ? (nowMs - state.observedAtMs) / 1000U : 0;
  p.progressPercent = state.progressPercent;
  if (slot < MAX_PRINTERS) {
    const BambuState& source = printers[slot].state;
    p.remainingMinutes = source.remainingMinutes;
#if HAS_HMS_UI
    p.printErrorCode = source.printError;
    if (source.printError != 0) {
      printErrorFormatCode(source.printError, codeBuf, codeBufSize);
      p.errorCode = codeBuf;
      p.errorText = printErrorLookupText(source.printError);  // nullptr when this board has no wording
      p.canceled = printErrorIsCancel(source.printError);
    }
#else
    (void)codeBuf;
    (void)codeBufSize;
#endif
  }
  return p;
}

}  // namespace

void workshopStatusLiteHandleRead(WebServer& server) {
  // Station Wi-Fi only; the setup/recovery AP never serves it.
  if (isAPMode()) {
    sendJson(server, 404, "{\"status\":\"error\",\"message\":\"Not available\"}");
    return;
  }

  const uint32_t now = millis();
  const uint32_t client = clientKey(server);
  const ReadDecision gate = g_limiter.admit(client, now);
  if (!gate.allowed) {
    server.sendHeader("Retry-After", String(gate.retryAfterSeconds ? gate.retryAfterSeconds : 1));
    sendJson(server, 429, "{\"status\":\"error\",\"message\":\"Too many requests\"}");
    return;
  }

  char presented[kTokenTextLength + 1] = {};
  std::uint8_t digest[kDigestBytes] = {};
  const String header = server.header("Authorization");
  const bool parsed = parseBearer(header.c_str(), presented);
  const bool hashed = parsed && sha256Text(presented, digest);
  secureZero(presented, sizeof(presented));
  const bool valid = hashed && tokenConfigured() && digestEqual(digest, g_digest);
  secureZero(digest, sizeof(digest));
  if (!valid) {
    g_limiter.noteFailure(client, now);
    server.sendHeader("WWW-Authenticate", "Bearer realm=\"workshop-os-status\"");
    sendJson(server, 401, "{\"status\":\"error\",\"message\":\"A valid read-only status token is required\"}");
    return;
  }
  g_limiter.noteSuccess(client, now);

  PrinterSummary list[workshop::platform::kMaxPrinterSlots];
  char codes[workshop::platform::kMaxPrinterSlots][kMaxErrorCodeBytes] = {};
  std::size_t count = 0;
  for (std::size_t slot = 0; slot < workshop::platform::kMaxPrinterSlots; ++slot) {
    if (!workshopPlatformPrinterConfigured(slot)) continue;
    list[count] = summarize(slot, now, codes[count], sizeof(codes[count]));
    ++count;
  }

  static char body[2048];
  const size_t length = serializeStatusLite(WORKSHOP_OS_RELEASE_VERSION, WORKSHOP_OS_SOURCE_SHA, list, count,
                                            body, sizeof(body));
  if (length == 0) {
    sendJson(server, 500, "{\"status\":\"error\",\"message\":\"Status summary unavailable\"}");
    return;
  }
  sendJson(server, 200, body);
}

void workshopStatusTokenHandleState(WebServer& server) {
  const uint32_t now = millis();
  String out = "{\"configured\":";
  out += tokenConfigured() ? "true" : "false";
  out += ",\"phase\":\"";
  out += approvalPhaseName(g_flow.phase(now));
  out += "\",\"secondsLeft\":";
  out += String(g_flow.secondsLeft(now));
  out += ",\"route\":\"/api/status/lite\"}";
  sendJson(server, 200, out.c_str());
}

void workshopStatusTokenHandleCreate(WebServer& server) {
  // The consent prompt lives on the touchscreen hub. Bring it forward (this
  // also wakes a sleeping panel); without the hub there is nobody to ask.
  if (!smartHubShowPage("home")) {
    sendJson(server, 409, "{\"status\":\"error\",\"message\":\"The touchscreen is not available to approve this request.\"}");
    return;
  }
  uint32_t requestId = esp_random();
  if (requestId == 0) requestId = 1;
  g_flow.start(requestId, millis());
  Serial.println("Status token: waiting for Allow on the touchscreen");
  String out = "{\"status\":\"pending\",\"requestId\":";
  out += String(requestId);
  out += ",\"secondsLeft\":";
  out += String(ApprovalFlow::kPromptMs / 1000U);
  out += "}";
  sendJson(server, 202, out.c_str());
}

void workshopStatusTokenHandleClaim(WebServer& server) {
  const uint32_t requestId = static_cast<uint32_t>(strtoul(server.arg("requestId").c_str(), nullptr, 10));
  char token[kTokenTextLength + 1] = {};
  if (!g_flow.claim(requestId, millis(), token)) {
    sendJson(server, 409, "{\"status\":\"error\",\"message\":\"No approved token is waiting for this request.\"}");
    return;
  }
  char body[96];
  snprintf(body, sizeof(body), "{\"status\":\"ok\",\"token\":\"%s\"}", token);
  secureZero(token, sizeof(token));
  sendJson(server, 200, body);
  secureZero(body, sizeof(body));
}

void workshopStatusTokenHandleRevoke(WebServer& server) {
  g_flow.cancel();
  clearDigest();
  g_limiter.reset();
  Serial.println("Status token: revoked");
  sendJson(server, 200, "{\"status\":\"ok\",\"configured\":false}");
}

bool workshopStatusTokenPromptVisible() {
  return g_flow.promptVisible(millis());
}

uint32_t workshopStatusTokenPromptSecondsLeft() {
  return g_flow.promptVisible(millis()) ? g_flow.secondsLeft(millis()) : 0;
}

bool workshopStatusTokenAllow() {
  const uint32_t now = millis();
  if (!g_flow.promptVisible(now)) return false;

  std::uint8_t random[kTokenRandomBytes];
  for (size_t i = 0; i < sizeof(random); i += 4) {
    const uint32_t r = esp_random();
    memcpy(random + i, &r, 4);
  }
  char token[kTokenTextLength + 1];
  encodeToken(random, token);
  secureZero(random, sizeof(random));

  std::uint8_t digest[kDigestBytes];
  // Persist the new digest first: it replaces (revokes) any previous token.
  const bool ok = sha256Text(token, digest) && storeDigest(digest) && g_flow.approve(token, now);
  secureZero(digest, sizeof(digest));
  secureZero(token, sizeof(token));
  if (!ok) {
    g_flow.deny(now);
    Serial.println("Status token: could not be created");
    return false;
  }
  g_limiter.reset();
  Serial.println("Status token: approved on the touchscreen");
  return true;
}

void workshopStatusTokenDeny() {
  if (g_flow.deny(millis())) Serial.println("Status token: denied on the touchscreen");
}

void workshopStatusTokenFactoryReset() {
  g_flow.cancel();
  clearDigest();
}
