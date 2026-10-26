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

enum class Tone : uint8_t { Info = 0, Ok, Attention, Warning, Busy, Bad };  // Bad: 26 Oct 2026, Pi Hub's needs

struct Card {
  char kind[12];
  char title[kTitleLen];
  char text[kTextLen];
  Tone tone;
  char id[32];    // 12.6 (feed v2): the same while the card means the same thing
  char ask[10];   // the question a tap asks ("" for none)
  uint32_t at;    // epoch seconds, 0 when not known
  uint8_t percent;  // 12.8: how far a "playing" card is in (or how full a disk is), 0-100; 255 when not given
  char run[16];   // 26 Oct 2026: a lab card's run ("PR-021-01"); the Judge it sheet asks Local AI about it
};

// 26 Oct 2026: one item of the feed's `needs` list: Pi Hub's one "Needs you" list (Pi issues, Local AI's attention
// cards, the newest print event), ranked bad > attention > warn and passed on by Local AI as it is. Absent when Pi
// Hub doesn't answer; the display then falls back to the cards.
static const uint8_t kMaxNeeds = 6;
struct Need {
  char id[32];      // stable while the item means the same thing ("printer:plate", "localai:<card id>")
  char title[kTitleLen];
  char detail[kTextLen];
  char source[12];  // "pi", "localai", "printer"
  Tone tone;
};

// Copies `in` into out[len], cut on a UTF-8 character boundary: Local AI cuts in characters, so a title of 24
// two-byte characters is 48 bytes and must lose whole characters, never half of one. Always terminates.
inline void copyUtf8(char* out, size_t len, const char* in) {
  if (!out || !len) return;
  out[0] = 0;
  if (!in) return;
  size_t i = 0;
  while (in[i]) {
    const unsigned char c = (unsigned char)in[i];
    const size_t n = c < 0x80 ? 1 : (c & 0xE0) == 0xC0 ? 2 : (c & 0xF0) == 0xE0 ? 3 : (c & 0xF8) == 0xF0 ? 4 : 0;
    if (!n) break;  // a stray continuation byte or not UTF-8: stop here
    size_t k = 1;
    while (k < n && ((unsigned char)in[i + k] & 0xC0) == 0x80) ++k;
    if (k < n || i + n >= len) break;  // cut short in the input, or doesn't fit whole
    memcpy(out + i, in + i, n);
    i += n;
  }
  out[i] = 0;
}

inline void setNeed(Need& n, const char* id, Tone tone, const char* title, const char* detail, const char* source) {
  copyUtf8(n.id, sizeof(n.id), id);
  copyUtf8(n.title, sizeof(n.title), title);
  copyUtf8(n.detail, sizeof(n.detail), detail);
  copyUtf8(n.source, sizeof(n.source), source);
  n.tone = tone;
}

inline Tone toneFrom(const char* s) {
  if (!s) return Tone::Info;
  if (!strcmp(s, "ok")) return Tone::Ok;
  if (!strcmp(s, "attention")) return Tone::Attention;
  if (!strcmp(s, "warning")) return Tone::Warning;
  if (!strcmp(s, "busy")) return Tone::Busy;
  if (!strcmp(s, "bad")) return Tone::Bad;       // 26 Oct 2026: Pi Hub's tones
  if (!strcmp(s, "warn")) return Tone::Warning;
  return Tone::Info;
}

// Cards the calm screen can draw: text only (the image card needs a picture this screen does not have room for).
inline bool shownKind(const char* kind) {
  return kind && (!strcmp(kind, "needs") || !strcmp(kind, "watch") || !strcmp(kind, "running") || !strcmp(kind, "weather") ||
                  !strcmp(kind, "done") || !strcmp(kind, "disk") ||  // 12.6: finished work and the fullest disk
                  !strcmp(kind, "playing") || !strcmp(kind, "home") ||  // 12.8: Plex on the Pi, and the Pi hub's issue
                  !strcmp(kind, "materials") ||  // LocalAI Materials: active spools & inventory health
                  !strcmp(kind, "lab"));  // 26 Oct 2026: the Print lab card (printing) and its Judge it nudge
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
  return q && (!strcmp(q, "needs") || !strcmp(q, "running") || !strcmp(q, "health") ||
               !strcmp(q, "today") || !strcmp(q, "next") || !strcmp(q, "weather"));  // 12.6
}

// 12.6: the question a tap on a card asks: the card's own (feed v2), else by its kind; nullptr for none.
inline const char* askFor(const Card& c) {
  if (validQuestion(c.ask)) return c.ask;
  if (!strcmp(c.kind, "needs")) return "needs";
  if (!strcmp(c.kind, "running")) return "running";
  if (!strcmp(c.kind, "watch") || !strcmp(c.kind, "disk") || !strcmp(c.kind, "materials")) return "health";
  if (!strcmp(c.kind, "done")) return "today";
  if (!strcmp(c.kind, "weather")) return "weather";
  return nullptr;
}

// How much a card's tone matters on Home: bad, attention (needs you), warning (worth a look), busy (work under way),
// ok (All clear); information cards (weather, disks, music, finished work) 0: they stay on the Local AI tab.
inline uint8_t toneRank(Tone t) {
  return t == Tone::Bad ? 5 : t == Tone::Attention ? 4 : t == Tone::Warning ? 3 : t == Tone::Busy ? 2 : t == Tone::Ok ? 1 : 0;
}

// Home at a glance: Home's house line. Of the cards, the one that matters most. -1 when no card qualifies. `others`
// counts the remaining problem cards (bad, attention, warning), for "+1 more".
inline int8_t homeSummaryIndex(const Card* cards, uint8_t n, uint8_t& others) {
  others = 0;
  int8_t best = -1;
  uint8_t bestRank = 0, problems = 0;
  for (uint8_t i = 0; i < n; ++i) {
    const uint8_t rank = toneRank(cards[i].tone);
    if (rank >= 3) ++problems;
    if (rank > bestRank) { bestRank = rank; best = (int8_t)i; }
  }
  if (bestRank >= 3) others = (uint8_t)(problems - 1);
  return best;
}

// 26 Oct 2026: idle Home's two "Needs you" rows. With Pi Hub's list (`needsPresent`: the feed had `needs`): its first
// two items in its order (every screen shows the same list from the top), `others` = the rest; an empty list means
// nothing needs you (0 rows, fromNeeds true: All clear, never Local AI's cards). Without it: the cards, best first (bad > attention >
// warning > busy > ok; the earlier card on a tie); the second row only for work under way or worse (All clear is
// never under a problem), `others` = the problem cards not shown. Returns how many rows (0-2); unused out[] are -1.
// `hiddenCardId` (Later on the Judge it sheet): that Local AI card, and Pi Hub's "localai:<id>" item for it, are left
// out on this display only; the rest of the list moves up. `needsTotal` (the feed's needsCount: Pi Hub's whole list,
// of which at most six are sent) makes "+N more" count the items not sent too; 0 when the feed didn't say.
inline bool hiddenItem(const char* id, const char* hidden, bool fromPi) {
  if (!hidden || !hidden[0] || !id) return false;
  if (fromPi) return !strncmp(id, "localai:", 8) && !strcmp(id + 8, hidden);
  return !strcmp(id, hidden);
}

inline uint8_t homeSummaryTop(const Need* needs, uint8_t n, bool needsPresent, const Card* cards, uint8_t nc, int8_t out[2],
                              bool& fromNeeds, uint8_t& others, const char* hiddenCardId = nullptr, uint16_t needsTotal = 0) {
  out[0] = out[1] = -1;
  others = 0;
  fromNeeds = needsPresent;
  if (fromNeeds) {
    if (!needs || !n) return 0;
    uint8_t shown = 0, total = 0;
    for (uint8_t i = 0; i < n; ++i) {
      if (hiddenItem(needs[i].id, hiddenCardId, true)) continue;
      ++total;
      if (shown < 2) out[shown++] = (int8_t)i;
    }
    const unsigned unsent = needsTotal > n ? (unsigned)(needsTotal - n) : 0U;
    others = (uint8_t)(total - shown + unsent > 255U ? 255U : total - shown + unsent);
    return shown;
  }
  if (!cards) return 0;
  uint8_t ranks[2] = {0, 0}, problems = 0;
  for (uint8_t i = 0; i < nc; ++i) {
    if (hiddenItem(cards[i].id, hiddenCardId, false)) continue;
    const uint8_t r = toneRank(cards[i].tone);
    if (r >= 3) ++problems;
    if (r > ranks[0]) { out[1] = out[0]; ranks[1] = ranks[0]; out[0] = (int8_t)i; ranks[0] = r; }
    else if (r > ranks[1]) { out[1] = (int8_t)i; ranks[1] = r; }
  }
  if (ranks[1] < 2) { out[1] = -1; ranks[1] = 0; }
  const uint8_t shown = (uint8_t)((ranks[0] >= 3) + (ranks[1] >= 3));
  others = (uint8_t)(problems - shown);
  return (uint8_t)((out[0] >= 0) + (out[1] >= 0));
}

// The calm screen's rotation without the card Later hid (`hidden`, its index; -1 for none): shown position k is card
// calmIndex(k, hidden).
inline uint8_t calmIndex(uint8_t k, int8_t hidden) {
  return hidden >= 0 && k >= (uint8_t)hidden ? (uint8_t)(k + 1) : k;
}

// 26 Oct 2026: the Print lab card's Judge it nudge ("Judge E-021", ask "lab-judge", its run): a tap opens the stepped
// Judge it sheet (firmware/platform/ui/lab_judge.hpp).
inline bool isJudgeCard(const Card& c) {
  return !strcmp(c.kind, "lab") && !strcmp(c.ask, "lab-judge") && c.run[0];
}

// 26 Oct 2026: the printing Home's extra row: the Print lab card while its run prints (busy), else -1 (the row shows
// the top need as before).
inline int8_t printingExtraIndex(const Card* cards, uint8_t n) {
  if (!cards) return -1;
  for (uint8_t i = 0; i < n; ++i)
    if (!strcmp(cards[i].kind, "lab") && cards[i].tone == Tone::Busy) return (int8_t)i;
  return -1;
}

// Home at a glance: the header's weather from the weather card's sentence ("Right now in Lake Wylie: 66 degrees and sunny.")
// as "66° Sunny". Empty when the sentence has no "<number> degrees".
inline void weatherShort(char* out, size_t len, const char* text) {
  if (!out || !len) return;
  out[0] = 0;
  if (!text) return;
  const char* deg = strstr(text, " degrees");
  if (!deg) return;
  const char* num = deg;
  while (num > text && ((num[-1] >= '0' && num[-1] <= '9') || num[-1] == '-')) --num;
  if (num == deg) return;
  char sky[24] = "";
  const char* and_ = strstr(deg, " and ");
  if (and_) {
    size_t k = 0;
    for (const char* p = and_ + 5; *p && *p != '.' && *p != ',' && k + 1 < sizeof(sky); ++p) sky[k++] = *p;
    sky[k] = 0;
    if (sky[0] >= 'a' && sky[0] <= 'z') sky[0] = (char)(sky[0] - 'a' + 'A');
  }
  snprintf(out, len, sky[0] ? "%.*s\xC2\xB0 %s" : "%.*s\xC2\xB0", (int)(deg - num), num, sky);
}

// 12.6: messages Local AI leaves for the display (feed v2 `messages`): a banner, maybe a chime, maybe one action.
static const uint8_t kMaxMessages = 4;
static const size_t kMessageTextLen = 124;
enum class Action : uint8_t { None = 0, Timer, Show };
struct Message {
  uint64_t seq;   // only grows (Local AI's milliseconds)
  char title[kTitleLen];
  char text[kMessageTextLen];
  Tone tone;
  bool chime;
  Action action;
  uint16_t minutes;  // Timer
  char page[10];     // Show: localai, image, camera, printer
};
inline bool validPage(const char* p) {
  return p && (!strcmp(p, "localai") || !strcmp(p, "image") || !strcmp(p, "camera") || !strcmp(p, "printer"));
}
// Whether a message is new enough to show: newer than the last shown, and (just after a restart, when nothing has been
// shown yet) made in the last 2 minutes, so a restart doesn't replay a quarter of an hour of banners.
inline bool messageIsNew(uint64_t seq, uint64_t lastShown, uint32_t atEpoch, uint32_t nowEpoch) {
  if (seq <= lastShown) return false;
  if (lastShown) return true;
  return atEpoch && nowEpoch && nowEpoch >= atEpoch && nowEpoch - atEpoch <= 120;
}

// 12.6: approvals the display lists, and may decide when Local AI says so.
static const uint8_t kMaxApprovals = 4;
struct Approval {
  char id[40];
  char title[64];
  char risk[8];
  bool decidable;
};

// 12.6: the last 6 pictures (feed v2 `images`).
static const uint8_t kMaxImages = 6;
// 12.6: the display's heartbeat to Local AI, and how long a long poll may wait.
static const uint32_t kHeartbeatMs = 300000UL;
static const uint32_t kEventsHoldMs = 30000UL;

// 12.4.2: the latest image. The display fetches only Local AI's own image route, as a JPEG of at most this size.
static const size_t kMaxImageBytes = 600UL * 1024UL;
static const size_t kImagePathLen = 256;
inline bool validImagePath(const char* p) {
  static const char kPrefix[] = "/api/images/view?";
  static const char kPoster[] = "/api/display/poster?";  // 12.8: what Plex on the Pi is playing, through Local AI
  if (!p || strlen(p) >= kImagePathLen) return false;
  if (strncmp(p, kPrefix, sizeof(kPrefix) - 1) != 0 && strncmp(p, kPoster, sizeof(kPoster) - 1) != 0) return false;
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
