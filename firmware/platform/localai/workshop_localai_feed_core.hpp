#pragma once

// Workshop OS 12.3.10: rules for the Local AI cards on the calm idle screen.
//
// Plain C++11, no Arduino, so tests/workshop_os12_localai_feed_smoke.cpp checks them on the host. The service
// (workshop_localai_feed.cpp) fetches GET /api/display/feed from Local AI (docs: LocalAI docs/WORKSHOP-DISPLAY.md ›
// Local AI cards); the calm screen draws one card at a time from what these functions say.

#include <stddef.h>
#include <stdint.h>
#include <string.h>

namespace workshop {
namespace localai {

static const uint8_t kMaxCards = 6;
static const uint32_t kPollMs = 60000UL;           // one request a minute while it answers
static const uint32_t kMaxBackoffMs = 600000UL;     // 10 minutes when it doesn't (Local AI down, PC off)
static const uint32_t kFreshMs = 600000UL;          // cards older than this are not shown
static const uint32_t kRotateMs = 8000UL;           // one card at a time, 8 s each
static const size_t kTitleLen = 28;                 // Local AI cuts titles to 24 characters (UTF-8 can be longer)
static const size_t kTextLen = 112;                 // and lines to 90

enum class Tone : uint8_t { Info = 0, Ok, Attention, Warning, Busy };

struct Card {
  char kind[12];
  char title[kTitleLen];
  char text[kTextLen];
  Tone tone;
};

inline Tone toneFrom(const char* s) {
  if (!s) return Tone::Info;
  if (!strcmp(s, "ok")) return Tone::Ok;
  if (!strcmp(s, "attention")) return Tone::Attention;
  if (!strcmp(s, "warning")) return Tone::Warning;
  if (!strcmp(s, "busy")) return Tone::Busy;
  return Tone::Info;
}

// Cards the calm screen can draw: text only (the image card needs a picture this screen does not have room for).
inline bool shownKind(const char* kind) {
  return kind && (!strcmp(kind, "needs") || !strcmp(kind, "watch") || !strcmp(kind, "running") || !strcmp(kind, "weather"));
}

// Wait before the next request: a minute after an answer; after failures 2, 4, 8 minutes, then 10.
inline uint32_t nextDelayMs(uint8_t failures) {
  if (!failures) return kPollMs;
  uint32_t d = kPollMs;
  for (uint8_t i = 0; i < failures && d < kMaxBackoffMs; ++i) d *= 2;
  return d > kMaxBackoffMs ? kMaxBackoffMs : d;
}

inline bool fresh(uint32_t nowMs, uint32_t fetchedAtMs) {
  return fetchedAtMs != 0 && (uint32_t)(nowMs - fetchedAtMs) <= kFreshMs;
}

inline uint8_t rotationIndex(uint32_t nowMs, uint8_t count) {
  return count ? (uint8_t)((nowMs / kRotateMs) % count) : 0;
}

// The display key Local AI's host/workshop-display/set-key.sh makes: "wsd_" and 48 lowercase hex digits.
inline bool validKey(const char* k) {
  if (!k || strncmp(k, "wsd_", 4) != 0 || strlen(k) != 52) return false;
  for (const char* p = k + 4; *p; ++p)
    if (!((*p >= '0' && *p <= '9') || (*p >= 'a' && *p <= 'f'))) return false;
  return true;
}

// A dotted IPv4 address on a private network (10/8, 172.16/12, 192.168/16): Local AI's address on the home network.
inline bool validPrivateIp(const char* s) {
  if (!s) return false;
  unsigned a[4] = {0, 0, 0, 0};
  int part = 0, digits = 0;
  for (const char* p = s;; ++p) {
    if (*p >= '0' && *p <= '9') {
      a[part] = a[part] * 10 + (unsigned)(*p - '0');
      if (++digits > 3 || a[part] > 255) return false;
    } else if (*p == '.' || *p == 0) {
      if (!digits) return false;
      if (*p == 0) break;
      if (++part > 3) return false;
      digits = 0;
    } else {
      return false;
    }
  }
  if (part != 3) return false;
  return a[0] == 10 || (a[0] == 172 && a[1] >= 16 && a[1] <= 31) || (a[0] == 192 && a[1] == 168);
}

// The TLS name Local AI's certificate carries (Caddy issues one per name): letters, digits, '-' and '.', e.g.
// "localai.home.arpa". The display connects to the IP address and checks the certificate against this name, since
// the ESP32's TLS library can't match an IP address in a certificate.
inline bool validTlsName(const char* s) {
  if (!s || !*s || strlen(s) > 63 || s[0] == '.' || s[0] == '-') return false;
  bool dot = false;
  for (const char* p = s; *p; ++p) {
    const char c = *p;
    if (c == '.') { dot = true; continue; }
    if (!((c >= 'a' && c <= 'z') || (c >= '0' && c <= '9') || c == '-')) return false;
  }
  return dot;
}

}  // namespace localai
}  // namespace workshop
