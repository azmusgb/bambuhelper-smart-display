#pragma once

// Workshop OS 12.3.10: rules for the Local AI cards on the calm idle screen.
//
// Plain C++11, no Arduino, so tests/workshop_os12_localai_feed_smoke.cpp checks them on the host. The service
// (workshop_localai_feed.cpp) fetches GET /api/display/feed from Local AI (docs: LocalAI docs/WORKSHOP-DISPLAY.md ›
// Local AI cards); the calm screen draws one card at a time from what these functions say.

#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
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

// 12.4.2: the Local AI tab's ask buttons (GET /api/display/ask?q=...). Local AI answers in at most 200 characters.
static const size_t kAnswerLen = 208;
inline bool validQuestion(const char* q) {
  return q && (!strcmp(q, "needs") || !strcmp(q, "running") || !strcmp(q, "health"));
}

// 12.4.2: the latest image. The display fetches only Local AI's own image route, as a JPEG of at most this size.
static const size_t kMaxImageBytes = 600UL * 1024UL;
static const size_t kImagePathLen = 256;
inline bool validImagePath(const char* p) {
  static const char kPrefix[] = "/api/images/view?";
  if (!p || strncmp(p, kPrefix, sizeof(kPrefix) - 1) != 0 || strlen(p) >= kImagePathLen) return false;
  for (const char* c = p; *c; ++c)
    if ((unsigned char)*c <= ' ' || (unsigned char)*c >= 127) return false;  // one request line: no spaces or CR/LF
  return true;
}

// A baseline JPEG's size, from its SOF0 marker (progressive SOF2 is refused: the display's decoder can't draw it).
inline bool jpegSize(const uint8_t* d, size_t n, uint16_t& w, uint16_t& h) {
  if (!d || n < 4 || d[0] != 0xFF || d[1] != 0xD8) return false;
  size_t i = 2;
  while (i + 4 <= n) {
    if (d[i] != 0xFF) return false;
    const uint8_t m = d[i + 1];
    if (m == 0xFF) { ++i; continue; }  // fill byte
    const size_t len = ((size_t)d[i + 2] << 8) | d[i + 3];
    if (len < 2) return false;
    if (m == 0xC0 || m == 0xC1) {
      if (i + 9 > n) return false;
      h = (uint16_t)((d[i + 5] << 8) | d[i + 6]);
      w = (uint16_t)((d[i + 7] << 8) | d[i + 8]);
      return w && h;
    }
    if (m == 0xC2 || m == 0xDA || m == 0xD9) return false;  // progressive, or image data before any SOF
    i += 2 + len;
  }
  return false;
}

// The scale that fits a w x h picture in areaW x areaH, never above 1 (a small picture is not blown up).
inline float fitScale(uint16_t w, uint16_t h, int areaW, int areaH) {
  if (!w || !h || areaW <= 0 || areaH <= 0) return 0.0f;
  float s = (float)areaW / (float)w;
  const float sh = (float)areaH / (float)h;
  if (sh < s) s = sh;
  return s > 1.0f ? 1.0f : s;
}

// 12.4.3: how long ago, for the latest image: "just now", "12 min ago", "3 h ago", "yesterday", "4 days ago".
// Empty when either time is unknown (0) or the clock is behind.
inline void agoText(char* out, size_t len, uint32_t nowEpoch, uint32_t atEpoch) {
  if (!out || !len) return;
  out[0] = 0;
  if (!nowEpoch || !atEpoch || nowEpoch + 120 < atEpoch) return;
  const uint32_t s = nowEpoch > atEpoch ? nowEpoch - atEpoch : 0;
  if (s < 90) snprintf(out, len, "just now");
  else if (s < 3600) snprintf(out, len, "%lu min ago", (unsigned long)((s + 30) / 60));
  else if (s < 86400) snprintf(out, len, "%lu h ago", (unsigned long)(s / 3600));
  else if (s < 2 * 86400) snprintf(out, len, "yesterday");
  else snprintf(out, len, "%lu days ago", (unsigned long)(s / 86400));
}

}  // namespace localai
}  // namespace workshop
