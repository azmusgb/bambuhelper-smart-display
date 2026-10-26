#pragma once

// 26 Oct 2026: the stepped Judge it sheet on the Workshop display (pure state, payload and layout).
//
// The same sheet as the phone's (Local AI app/public/print-lab.js, Judge it), one strip per screen: for each strip
// (variant tab) x criterion a chip from the criterion's choices, or "–" (not judged, sent as null); on the last page an
// optional inconclusive reason and Send. Send queues, through Local AI's POST /api/display/lab/verdict, the very
// verdict request the phone queues (lighting "diagnostic", no note), so judging here records exactly what the phone
// would. The sheet comes from GET /api/display/lab/judge?run=<run> (docs: LocalAI docs/WORKSHOP-DISPLAY.md).
//
// Plain C++11, no Arduino: tests/workshop_os12_lab_judge_smoke.cpp checks it on the host. Everything from Local AI is
// untrusted text: the reader below is bounded (size, nesting, every field's length) and never leaves half a UTF-8
// character. Names sent back to Local AI (strips, criterion keys, choices) must come through exactly; a sheet with more
// than the display keeps, or a name it would have to cut, is judged on the phone instead of sent half-right.
//
// The firmware (lab_judge.cppfrag) keeps one LabJudge in static storage, never on the 8 KB loop stack.

#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

namespace workshop {
namespace lab {

static const uint8_t kMaxTabs = 6;
static const uint8_t kMaxCriteria = 6;
static const uint8_t kMaxChoices = 6;
static const uint8_t kMaxChips = kMaxChoices + 1;  // the choices and "–"
static const size_t kTabLen = 16;
static const size_t kKeyLen = 24;
static const size_t kLabelLen = 40;
static const size_t kChoiceLen = 24;
static const size_t kMaxJudgeJson = 6144;  // the judge answer the display reads at most
static const size_t kMaxPayload = 4096;    // Local AI's verdict body limit
static const uint8_t kMaxDepth = 8;
static const int8_t kUnset = -1;      // not chosen yet
static const int8_t kNotJudged = -2;  // "–": sent as null
static const uint32_t kIdleMs = 600000UL;    // the draft is kept in RAM until Send or 10 min idle
static const uint32_t kLaterMs = 7200000UL;  // Later hides the judge card on the display for 2 h
static const uint32_t kPollMs = 3000UL;      // while Waiting for the Mac
static const uint32_t kSlowMs = 120000UL;    // then the phone's "The Mac hasn't picked this up" line

// The inconclusive reasons the display offers, sent as these words (the phone takes free text).
static const uint8_t kReasonCount = 3;
static const char* const kReasons[kReasonCount] = {"It didn't finish printing", "I can't tell from this print", "The wrong thing printed"};
static const char kTooBig[] = "This test has more than the display can show. Judge it on your phone.";

// A run id as Local AI's judge card carries it ("PR-021-01"): capital letters, digits and '-', at most 15.
inline bool validRun(const char* r) {
  if (!r || !r[0] || strlen(r) > 15) return false;
  for (const char* p = r; *p; ++p)
    if (!((*p >= 'A' && *p <= 'Z') || (*p >= '0' && *p <= '9') || *p == '-')) return false;
  return true;
}

// "rq-" and 16 lowercase hex digits, as the phone's requests.
inline bool validRequestId(const char* id) {
  if (!id || strlen(id) != 19 || strncmp(id, "rq-", 3) != 0) return false;
  for (const char* p = id + 3; *p; ++p)
    if (!((*p >= '0' && *p <= '9') || (*p >= 'a' && *p <= 'f'))) return false;
  return true;
}

inline void makeRequestId(char out[20], uint32_t hi, uint32_t lo) {
  snprintf(out, 20, "rq-%08x%08x", (unsigned)hi, (unsigned)lo);
}

// ---------------------------------------------------------------------------
// A bounded JSON reader: one pass over at most kMaxJudgeJson bytes, nesting at most kMaxDepth.
// ---------------------------------------------------------------------------

struct JsonIn {
  const char* p;
  const char* e;
  uint8_t depth;
  bool bad;
  JsonIn(const char* s, size_t n) : p(s), e(s + n), depth(0), bad(false) {}
  bool fail() { bad = true; return false; }
  void ws() { while (p < e && (*p == ' ' || *p == '\n' || *p == '\r' || *p == '\t')) ++p; }
  bool at(char c) { ws(); return p < e && *p == c; }
  bool eat(char c) { if (!at(c)) return false; ++p; return true; }
  bool lit(const char* w) {
    ws();
    const size_t n = strlen(w);
    if ((size_t)(e - p) < n || memcmp(p, w, n) != 0) return false;
    p += n;
    return true;
  }
  static int hex(char c) { return c >= '0' && c <= '9' ? c - '0' : c >= 'a' && c <= 'f' ? c - 'a' + 10 : c >= 'A' && c <= 'F' ? c - 'A' + 10 : -1; }
  bool hex4(uint32_t& v) {
    if (e - p < 4) return false;
    v = 0;
    for (int i = 0; i < 4; ++i) { const int h = hex(p[i]); if (h < 0) return false; v = (v << 4) | (uint32_t)h; }
    p += 4;
    return true;
  }
  static size_t utf8(uint32_t cp, char* b) {
    if (cp < 0x80) { b[0] = (char)cp; return 1; }
    if (cp < 0x800) { b[0] = (char)(0xC0 | (cp >> 6)); b[1] = (char)(0x80 | (cp & 0x3F)); return 2; }
    if (cp < 0x10000) { b[0] = (char)(0xE0 | (cp >> 12)); b[1] = (char)(0x80 | ((cp >> 6) & 0x3F)); b[2] = (char)(0x80 | (cp & 0x3F)); return 3; }
    b[0] = (char)(0xF0 | (cp >> 18)); b[1] = (char)(0x80 | ((cp >> 12) & 0x3F)); b[2] = (char)(0x80 | ((cp >> 6) & 0x3F)); b[3] = (char)(0x80 | (cp & 0x3F));
    return 4;
  }
  // A string into out[len] (out may be null: skip it), whole characters only. `exact` says it came through unchanged:
  // not cut, no control character shown as a space, no broken UTF-8 shown as '?'.
  bool str(char* out, size_t len, bool* exact) {
    if (!at('"')) return fail();
    ++p;
    size_t o = 0;
    bool ex = true, full = false;
    for (;;) {
      if (p >= e) return fail();
      const unsigned char c = (unsigned char)*p;
      if (c == '"') { ++p; break; }
      if (c < 0x20) return fail();
      char b[4];
      size_t n = 0;
      if (c == '\\') {
        if (++p >= e) return fail();
        const char x = *p++;
        uint32_t cp = 0;
        switch (x) {
          case '"': cp = '"'; break;
          case '\\': cp = '\\'; break;
          case '/': cp = '/'; break;
          case 'b': case 'f': case 'n': case 'r': case 't': cp = ' '; ex = false; break;
          case 'u': {
            if (!hex4(cp)) return fail();
            if (cp >= 0xD800 && cp <= 0xDBFF) {
              uint32_t lo = 0;
              if (e - p >= 6 && p[0] == '\\' && p[1] == 'u') {
                p += 2;
                if (!hex4(lo)) return fail();
              }
              if (lo >= 0xDC00 && lo <= 0xDFFF) cp = 0x10000 + ((cp - 0xD800) << 10) + (lo - 0xDC00);
              else { cp = 0xFFFD; ex = false; }
            } else if (cp >= 0xDC00 && cp <= 0xDFFF) {
              cp = 0xFFFD;
              ex = false;
            }
            if (cp < 0x20) { cp = ' '; ex = false; }
            break;
          }
          default: return fail();
        }
        n = utf8(cp, b);
      } else if (c < 0x80) {
        b[0] = (char)c;
        n = 1;
        ++p;
      } else {
        const size_t want = (c & 0xE0) == 0xC0 ? 2 : (c & 0xF0) == 0xE0 ? 3 : (c & 0xF8) == 0xF0 ? 4 : 0;
        bool whole = want && (size_t)(e - p) >= want;
        for (size_t k = 1; whole && k < want; ++k) whole = ((unsigned char)p[k] & 0xC0) == 0x80;
        if (whole) { memcpy(b, p, want); n = want; p += want; }
        else { b[0] = '?'; n = 1; ++p; ex = false; }
      }
      if (out && len) {
        if (!full && o + n < len) { memcpy(out + o, b, n); o += n; }
        else { full = true; ex = false; }
      }
    }
    if (out && len) out[o] = 0;
    if (exact) *exact = ex;
    return true;
  }
  bool number() {
    ws();
    if (p < e && *p == '-') ++p;
    const char* d = p;
    while (p < e && *p >= '0' && *p <= '9') ++p;
    if (p == d) return fail();
    if (p < e && *p == '.') { ++p; d = p; while (p < e && *p >= '0' && *p <= '9') ++p; if (p == d) return fail(); }
    if (p < e && (*p == 'e' || *p == 'E')) {
      ++p;
      if (p < e && (*p == '+' || *p == '-')) ++p;
      d = p;
      while (p < e && *p >= '0' && *p <= '9') ++p;
      if (p == d) return fail();
    }
    return true;
  }
  // Any value, checked and passed over.
  bool skip() {
    ws();
    if (p >= e) return fail();
    const char c = *p;
    if (c == '"') return str(nullptr, 0, nullptr);
    if (c == '{' || c == '[') {
      if (++depth > kMaxDepth) return fail();
      ++p;
      const char close = c == '{' ? '}' : ']';
      if (eat(close)) { --depth; return true; }
      for (;;) {
        if (c == '{' && (!str(nullptr, 0, nullptr) || !eat(':'))) return fail();
        if (!skip()) return false;
        if (eat(',')) continue;
        if (eat(close)) { --depth; return true; }
        return fail();
      }
    }
    if (lit("true") || lit("false") || lit("null")) return true;
    return number();
  }
  // A string field, or null (""); another type is passed over (""). False only for broken JSON.
  bool text(char* out, size_t len, bool* exact = nullptr) {
    out[0] = 0;
    if (exact) *exact = true;
    if (at('"')) return str(out, len, exact);
    if (lit("null")) return true;
    return skip();
  }
  bool boolean(bool& v) {
    if (lit("true")) { v = true; return true; }
    if (lit("false")) { v = false; return true; }
    return skip();
  }
  // Calls each(key) for every member of an object; each reads the value. False for broken JSON.
  template <typename F>
  bool members(F each) {
    if (!eat('{')) return fail();
    if (++depth > kMaxDepth) return fail();
    if (eat('}')) { --depth; return true; }
    for (;;) {
      char key[24];
      if (!str(key, sizeof(key), nullptr) || !eat(':')) return fail();
      if (!each(key)) return false;
      if (eat(',')) continue;
      if (eat('}')) { --depth; return true; }
      return fail();
    }
  }
  template <typename F>
  bool items(F each) {
    if (!eat('[')) return fail();
    if (++depth > kMaxDepth) return fail();
    if (eat(']')) { --depth; return true; }
    for (;;) {
      if (!each()) return false;
      if (eat(',')) continue;
      if (eat(']')) { --depth; return true; }
      return fail();
    }
  }
};

// True when `json` is one well-formed JSON value (the host test checks the payload with it).
inline bool jsonValid(const char* json, size_t len) {
  if (!json) return false;
  JsonIn in(json, len);
  if (!in.skip()) return false;
  in.ws();
  return in.p == in.e;
}

// ---------------------------------------------------------------------------
// The sheet Local AI sends
// ---------------------------------------------------------------------------

struct Criterion {
  char key[kKeyLen];
  char label[kLabelLen];
  uint8_t choiceCount;
  char choices[kMaxChoices][kChoiceLen];
};

struct Sheet {
  bool ok;         // a sheet for a run (judgeable, or judged on the phone)
  bool phoneOnly;  // judged on the phone: Local AI's reason, or more than the display keeps
  char experiment[16];
  char run[16];
  char judgeOn[112];
  char reason[112];
  uint8_t tabCount;
  char tabs[kMaxTabs][kTabLen];
  uint8_t criterionCount;
  Criterion criteria[kMaxCriteria];
  bool judged;  // a verdict, or a verdict request still waiting
  char judgedAt[32];
  char judgedBy[16];
  bool pending;  // the newest verdict request for the run
  char pendingId[24];
  char pendingStatus[12];    // pending, applied, refused, duplicate
  char pendingMessage[124];  // the Mac's words when it refused
};

namespace detail {
struct SheetReader {
  JsonIn& in;
  Sheet& s;
  bool& big;  // something the display would have to cut or drop: judged on the phone
  bool exactText(char* out, size_t len) {
    bool ex = true;
    if (!in.at('"')) { big = true; return in.skip(); }
    if (!in.str(out, len, &ex)) return false;
    if (!ex || !out[0]) big = true;
    return true;
  }
  bool criterion(Criterion& c) {
    return in.members([&](const char* k) -> bool {
      if (!strcmp(k, "key")) return exactText(c.key, sizeof(c.key));
      if (!strcmp(k, "label")) return in.text(c.label, sizeof(c.label));
      if (!strcmp(k, "choices")) {
        if (!in.at('[')) { big = true; return in.skip(); }
        return in.items([&]() -> bool {
          if (c.choiceCount >= kMaxChoices) { big = true; return in.skip(); }
          return exactText(c.choices[c.choiceCount++], kChoiceLen);
        });
      }
      return in.skip();
    });
  }
  bool member(const char* k) {
    if (!strcmp(k, "experiment")) return in.text(s.experiment, sizeof(s.experiment));
    if (!strcmp(k, "run")) return in.text(s.run, sizeof(s.run));
    if (!strcmp(k, "judgeOn")) return in.text(s.judgeOn, sizeof(s.judgeOn));
    if (!strcmp(k, "reason")) return in.text(s.reason, sizeof(s.reason));
    if (!strcmp(k, "phoneOnly")) return in.boolean(s.phoneOnly);
    if (!strcmp(k, "tabs")) {
      if (!in.at('[')) return in.skip();
      return in.items([&]() -> bool {
        if (s.tabCount >= kMaxTabs) { big = true; return in.skip(); }
        return exactText(s.tabs[s.tabCount++], kTabLen);
      });
    }
    if (!strcmp(k, "criteria")) {
      if (!in.at('[')) return in.skip();
      return in.items([&]() -> bool {
        if (s.criterionCount >= kMaxCriteria || !in.at('{')) { big = true; return in.skip(); }
        Criterion& c = s.criteria[s.criterionCount++];
        if (!criterion(c)) return false;
        if (!c.key[0] || !c.choiceCount) big = true;
        return true;
      });
    }
    if (!strcmp(k, "judged")) {
      if (!in.at('{')) return in.skip();
      s.judged = true;
      return in.members([&](const char* m) -> bool {
        if (!strcmp(m, "at")) return in.text(s.judgedAt, sizeof(s.judgedAt));
        if (!strcmp(m, "by")) return in.text(s.judgedBy, sizeof(s.judgedBy));
        return in.skip();
      });
    }
    if (!strcmp(k, "pending")) {
      if (!in.at('{')) return in.skip();
      s.pending = true;
      return in.members([&](const char* m) -> bool {
        if (!strcmp(m, "id")) return in.text(s.pendingId, sizeof(s.pendingId));
        if (!strcmp(m, "status")) return in.text(s.pendingStatus, sizeof(s.pendingStatus));
        if (!strcmp(m, "message")) return in.text(s.pendingMessage, sizeof(s.pendingMessage));
        return in.skip();
      });
    }
    return in.skip();
  }
};
}  // namespace detail

// Reads Local AI's judge answer into `out` (cleared first). False when it isn't one: broken or too large JSON, no run.
inline bool parseSheet(const char* json, size_t len, Sheet& out) {
  memset(&out, 0, sizeof(out));
  if (!json || !len || len > kMaxJudgeJson) return false;
  JsonIn in(json, len);
  bool big = false;
  detail::SheetReader r = {in, out, big};
  if (!in.at('{') || !in.members([&](const char* k) { return r.member(k); })) { memset(&out, 0, sizeof(out)); return false; }
  in.ws();
  if (in.p != in.e || !validRun(out.run)) { memset(&out, 0, sizeof(out)); return false; }
  if (big && !out.phoneOnly) {
    out.phoneOnly = true;
    snprintf(out.reason, sizeof(out.reason), "%s", kTooBig);
  }
  if (out.phoneOnly) {
    out.tabCount = 0;
    out.criterionCount = 0;
    if (!out.reason[0]) snprintf(out.reason, sizeof(out.reason), "Judge it on your phone.");
  }
  out.ok = out.phoneOnly || (out.tabCount > 0 && out.criterionCount > 0);
  if (!out.ok) memset(&out, 0, sizeof(out));
  return out.ok;
}

// "2026-10-26T18:32:05Z" (fraction, offset or none: UTC) as seconds since 1970. False when it isn't one.
inline bool isoToEpoch(const char* s, long& out) {
  if (!s) return false;
  int v[6] = {0, 0, 0, 0, 0, 0};
  const int widths[6] = {4, 2, 2, 2, 2, 2};
  const char seps[6] = {'-', '-', 'T', ':', ':', 0};
  const char* p = s;
  for (int f = 0; f < 6; ++f) {
    for (int k = 0; k < widths[f]; ++k, ++p) {
      if (*p < '0' || *p > '9') return false;
      v[f] = v[f] * 10 + (*p - '0');
    }
    if (f < 5) {
      if (*p != seps[f] && !(f == 2 && *p == ' ')) return false;
      ++p;
    }
  }
  if (v[1] < 1 || v[1] > 12 || v[2] < 1 || v[2] > 31 || v[3] > 23 || v[4] > 59 || v[5] > 60) return false;
  if (*p == '.') { ++p; while (*p >= '0' && *p <= '9') ++p; }
  long offset = 0;
  if (*p == 'Z') ++p;
  else if (*p == '+' || *p == '-') {
    const int sign = *p == '-' ? -1 : 1;
    ++p;
    int hh = 0, mm = 0;
    for (int k = 0; k < 2; ++k, ++p) { if (*p < '0' || *p > '9') return false; hh = hh * 10 + (*p - '0'); }
    if (*p == ':') ++p;
    for (int k = 0; k < 2; ++k, ++p) { if (*p < '0' || *p > '9') return false; mm = mm * 10 + (*p - '0'); }
    offset = sign * (hh * 3600L + mm * 60L);
  }
  if (*p) return false;
  // Days from 1970-01-01 (Howard Hinnant's days_from_civil).
  const int y = v[0] - (v[1] <= 2);
  const int era = (y >= 0 ? y : y - 399) / 400;
  const unsigned yoe = (unsigned)(y - era * 400);
  const unsigned doy = (unsigned)((153 * (v[1] + (v[1] > 2 ? -3 : 9)) + 2) / 5 + v[2] - 1);
  const unsigned doe = yoe * 365 + yoe / 4 - yoe / 100 + doy;
  const long days = (long)era * 146097L + (long)doe - 719468L;
  out = days * 86400L + v[3] * 3600L + v[4] * 60L + v[5] - offset;
  return true;
}

// ---------------------------------------------------------------------------
// The sheet and its draft
// ---------------------------------------------------------------------------

enum class State : uint8_t {
  Empty,      // no sheet (loading, nothing to judge, or Local AI didn't answer)
  PhoneOnly,  // judged on the phone
  Draft,      // choosing; Send when every strip is graded (or a reason is given)
  Sending,    // the request is on its way to Local AI
  Waiting,    // Local AI queued it: Waiting for the Mac
  Done,       // the Mac applied it: Done ✓
  Refused,    // the Mac refused it, in its words: Change it
  Judged,     // already judged (a verdict, or a request waiting): Change it
};

namespace detail {
inline void writeJson(char* out, size_t len, size_t& o, bool& ok, const char* s) {
  for (const unsigned char* p = reinterpret_cast<const unsigned char*>(s); ok && *p; ++p) {
    char b[8];
    size_t n = 0;
    if (*p == '"' || *p == '\\') { b[0] = '\\'; b[1] = (char)*p; n = 2; }
    else if (*p < 0x20) n = (size_t)snprintf(b, sizeof(b), "\\u%04x", (unsigned)*p);
    else { b[0] = (char)*p; n = 1; }
    if (o + n >= len) { ok = false; return; }
    memcpy(out + o, b, n);
    o += n;
  }
}
inline void raw(char* out, size_t len, size_t& o, bool& ok, const char* s) {
  const size_t n = strlen(s);
  if (!ok || o + n >= len) { ok = false; return; }
  memcpy(out + o, s, n);
  o += n;
}
inline void quoted(char* out, size_t len, size_t& o, bool& ok, const char* s) {
  raw(out, len, o, ok, "\"");
  writeJson(out, len, o, ok, s);
  raw(out, len, o, ok, "\"");
}
inline uint32_t fnv(uint32_t h, const char* s) {
  for (const unsigned char* p = reinterpret_cast<const unsigned char*>(s); *p; ++p) h = (h ^ *p) * 16777619UL;
  return (h ^ 0xFFu) * 16777619UL;  // a separator, so "ab"+"c" differs from "a"+"bc"
}
}  // namespace detail

struct LabJudge {
  Sheet s;
  int8_t sel[kMaxTabs][kMaxCriteria];  // a choice index, kNotJudged ("–") or kUnset
  int8_t reason;                       // inconclusive: an index into kReasons, or -1
  bool replace;                        // Change it: sent with replace: true (the phone's Replace)
  bool changing;                       // after Change it: the draft, not the earlier verdict
  bool sending;
  char requestId[20];  // the draft's id: the same while the same draft is resent, new after any change
  char sentId[20];     // the request Local AI accepted

  void clearDraft() {
    for (uint8_t t = 0; t < kMaxTabs; ++t)
      for (uint8_t c = 0; c < kMaxCriteria; ++c) sel[t][c] = kUnset;
    reason = -1;
    replace = changing = sending = false;
    requestId[0] = sentId[0] = 0;
  }
  void clear() {
    memset(&s, 0, sizeof(s));
    clearDraft();
  }

  // What the draft depends on: the run, the strips, the criteria and their choices.
  uint32_t signature() const {
    uint32_t h = detail::fnv(2166136261UL, s.run);
    for (uint8_t t = 0; t < s.tabCount; ++t) h = detail::fnv(h, s.tabs[t]);
    h = detail::fnv(h, "|");
    for (uint8_t c = 0; c < s.criterionCount; ++c) {
      h = detail::fnv(h, s.criteria[c].key);
      for (uint8_t k = 0; k < s.criteria[c].choiceCount; ++k) h = detail::fnv(h, s.criteria[c].choices[k]);
      h = detail::fnv(h, "/");
    }
    return h;
  }
  // After `s` was replaced: the draft stays only when the sheet is the same one it was made on.
  void reconcile(uint32_t before) {
    if (signature() != before) clearDraft();
  }
  bool load(const char* json, size_t len) {
    const uint32_t before = signature();
    const bool ok = parseSheet(json, len, s);
    reconcile(before);
    return ok;
  }

  uint8_t pages() const { return s.ok && !s.phoneOnly ? (uint8_t)(s.tabCount + 1) : 1; }
  bool sendPage(uint8_t page) const { return page + 1 == pages(); }
  const char* tabOf(uint8_t page) const { return page < s.tabCount ? s.tabs[page] : ""; }

  State state() const {
    if (!s.ok) return State::Empty;
    if (s.phoneOnly) return State::PhoneOnly;
    if (sending) return State::Sending;
    if (sentId[0]) {
      if (s.pending && !strcmp(s.pendingId, sentId)) {
        if (!strcmp(s.pendingStatus, "applied") || !strcmp(s.pendingStatus, "duplicate")) return State::Done;
        if (!strcmp(s.pendingStatus, "refused")) return State::Refused;
      }
      return State::Waiting;
    }
    if (changing) return State::Draft;
    if (s.pending && !strcmp(s.pendingStatus, "refused")) return State::Refused;
    if (s.judged) return State::Judged;
    return State::Draft;
  }
  bool editable() const { return state() == State::Draft; }
  // Where the sheet opens: strip 1 for a new draft, else the last page with its state.
  uint8_t startPage() const { return state() == State::Draft ? 0 : (uint8_t)(pages() - 1); }

  bool select(uint8_t page, uint8_t criterion, int8_t choice) {
    if (!editable() || page >= s.tabCount || criterion >= s.criterionCount) return false;
    if (choice != kUnset && choice != kNotJudged && (choice < 0 || choice >= (int8_t)s.criteria[criterion].choiceCount)) return false;
    if (sel[page][criterion] != choice) requestId[0] = 0;  // a changed draft is a new request
    sel[page][criterion] = choice;
    return true;
  }
  int8_t selected(uint8_t page, uint8_t criterion) const {
    return page < kMaxTabs && criterion < kMaxCriteria ? sel[page][criterion] : kUnset;
  }
  bool setReason(int8_t r) {
    if (!editable() || r < -1 || r >= (int8_t)kReasonCount) return false;
    if (reason != r) requestId[0] = 0;
    reason = r;
    return true;
  }
  bool complete() const {
    for (uint8_t t = 0; t < s.tabCount; ++t)
      for (uint8_t c = 0; c < s.criterionCount; ++c)
        if (sel[t][c] == kUnset) return false;
    return s.tabCount > 0;
  }
  bool canSend() const { return s.ok && !s.phoneOnly && (reason >= 0 || complete()); }

  // The button on the last page, and whether it can be pressed now.
  const char* action(bool& enabled) const {
    const State st = state();
    enabled = true;
    switch (st) {
      case State::Draft: enabled = canSend(); return "Send";
      case State::Sending:
      case State::Waiting: enabled = false; return "Send";
      case State::Refused:
      case State::Judged: return "Change it";
      default: return "Close";
    }
  }
  // "Judge it · E-021 · Strip 21B (2 of 3)", "Judge it · E-021 · Send".
  void title(char* out, size_t len, uint8_t page) const {
    if (!out || !len) return;
    int n;
    if (!s.ok || !s.experiment[0]) n = snprintf(out, len, "Judge it");
    else if (page < s.tabCount && !s.phoneOnly)
      n = snprintf(out, len, "Judge it \xC2\xB7 %s \xC2\xB7 Strip %s (%u of %u)", s.experiment, s.tabs[page], (unsigned)(page + 1), (unsigned)s.tabCount);
    else if (!s.phoneOnly) n = snprintf(out, len, "Judge it \xC2\xB7 %s \xC2\xB7 Send", s.experiment);
    else n = snprintf(out, len, "Judge it \xC2\xB7 %s", s.experiment);
    if (n < 0) out[0] = 0;  // (a long title is cut; the header fits it to its width)
  }

  // {run, requestId, grades: {strip: {criterion: choice|null}}, inconclusive: reason|null, replace}: the body Local AI
  // checks against the record and queues as the phone's verdict request. Ungraded strips are left out (only with a
  // reason). False, with out empty, when it can't be sent or doesn't fit whole.
  bool payload(char* out, size_t len, const char* id, bool rep) const {
    if (!out || !len) return false;
    out[0] = 0;
    if (!canSend() || !validRequestId(id) || !validRun(s.run)) return false;
    size_t o = 0;
    bool ok = true;
    detail::raw(out, len, o, ok, "{\"run\":");
    detail::quoted(out, len, o, ok, s.run);
    detail::raw(out, len, o, ok, ",\"requestId\":");
    detail::quoted(out, len, o, ok, id);
    detail::raw(out, len, o, ok, ",\"grades\":{");
    bool firstTab = true;
    for (uint8_t t = 0; t < s.tabCount; ++t) {
      bool any = false;
      for (uint8_t c = 0; c < s.criterionCount; ++c) any = any || sel[t][c] != kUnset;
      if (!any) continue;
      if (!firstTab) detail::raw(out, len, o, ok, ",");
      firstTab = false;
      detail::quoted(out, len, o, ok, s.tabs[t]);
      detail::raw(out, len, o, ok, ":{");
      bool firstC = true;
      for (uint8_t c = 0; c < s.criterionCount; ++c) {
        const int8_t v = sel[t][c];
        if (v == kUnset) continue;
        if (!firstC) detail::raw(out, len, o, ok, ",");
        firstC = false;
        detail::quoted(out, len, o, ok, s.criteria[c].key);
        detail::raw(out, len, o, ok, ":");
        if (v == kNotJudged) detail::raw(out, len, o, ok, "null");
        else detail::quoted(out, len, o, ok, s.criteria[c].choices[v]);
      }
      detail::raw(out, len, o, ok, "}");
    }
    detail::raw(out, len, o, ok, "},\"inconclusive\":");
    if (reason >= 0) detail::quoted(out, len, o, ok, kReasons[reason]);
    else detail::raw(out, len, o, ok, "null");
    detail::raw(out, len, o, ok, rep ? ",\"replace\":true}" : ",\"replace\":false}");
    if (!ok) { out[0] = 0; return false; }
    out[o] = 0;
    return true;
  }

  // Change it: the draft (kept, if any) is sent again as a new request that replaces the verdict.
  void changeIt() {
    replace = true;
    changing = true;
    sending = false;
    requestId[0] = sentId[0] = 0;
  }
  // Send: the payload for the draft, under its id (made from two random words the first time). The same draft sent
  // again keeps its id, so Local AI counts it once.
  bool beginSend(char* out, size_t len, uint32_t r1, uint32_t r2) {
    if (state() != State::Draft || !canSend()) return false;
    if (!requestId[0]) makeRequestId(requestId, r1, r2);
    if (!payload(out, len, requestId, replace)) return false;
    sending = true;
    return true;
  }
  void sendAccepted() {
    sending = false;
    if (requestId[0]) memcpy(sentId, requestId, sizeof(sentId));
  }
  void sendFailed() { sending = false; }
};

// ---------------------------------------------------------------------------
// Layout: one page of the sheet on a w x h screen. Header (title, Later), the body (criteria rows: label and chips,
// chips on at most two lines; scrolled by whole rows when they don't all fit), the footer (Back or Close, the scroll
// arrows when the page scrolls, Next or the last page's button). The Send page: the Inconclusive reasons (while
// choosing) and the state with "Add photos from your phone". Every target is at least 44 x 44 and none overlap.
// ---------------------------------------------------------------------------

struct Box {
  int16_t x, y, w, h;
  bool contains(int px, int py) const { return w > 0 && h > 0 && px >= x && px < x + w && py >= y && py < y + h; }
  bool empty() const { return w <= 0 || h <= 0; }
};
inline Box box(int x, int y, int w, int h) { Box b = {(int16_t)x, (int16_t)y, (int16_t)w, (int16_t)h}; return b; }

typedef int (*MeasureFn)(const char* text, void* ctx);

static const int16_t kHeaderH = 44;
static const int16_t kTarget = 44;
static const int16_t kChipGap = 6;
static const int16_t kLinePitch = kTarget + kChipGap;
static const int16_t kMargin = 8;
static const int16_t kLabelColumn = 132;  // landscape: the criterion's label left of its chips
static const int16_t kLabelLine = 22;     // portrait: above them
static const int16_t kChipMinW = 52;
static const int16_t kChipPad = 28;
static const int16_t kStatusMinH = 54;

struct ChipRow {
  Box label;  // where the label is drawn (not a target)
  Box chips[kMaxChips];
  uint8_t chipCount;
  uint8_t lines;
  int16_t h;
  bool shown;
};

struct SheetLayout {
  Box title, later, back, next, up, down, body, status;
  bool hasBack, scrolls, reasons;
  uint8_t first, maxFirst, rowCount;
  ChipRow rows[kMaxCriteria];  // a strip page: one per criterion; the Send page: rows[0] is the reasons
};

namespace detail {
// Chips for one row in the area [x0, x1): left to right, wrapping; more than two lines -> equal widths, two lines.
inline void placeChips(ChipRow& r, int x0, int x1, int y, const char* const* texts, uint8_t n, MeasureFn m, void* ctx) {
  r.chipCount = n;
  const int area = x1 - x0;
  int x = x0, line = 0;
  for (uint8_t i = 0; i < n; ++i) {
    int w = (texts[i] ? (m ? m(texts[i], ctx) : 0) : 0) + kChipPad;
    if (w < kChipMinW) w = kChipMinW;
    if (w > area) w = area;
    if (x > x0 && x + w > x1) { x = x0; ++line; }
    r.chips[i] = box(x, y + line * kLinePitch, w, kTarget);
    x += w + kChipGap;
  }
  r.lines = (uint8_t)(n ? line + 1 : 0);
  if (r.lines > 2) {
    const uint8_t per = (uint8_t)((n + 1) / 2);
    const int w = (area - kChipGap * (per - 1)) / per;
    for (uint8_t i = 0; i < n; ++i) r.chips[i] = box(x0 + (i % per) * (w + kChipGap), y + (i / per) * kLinePitch, w, kTarget);
    r.lines = 2;
  }
}
}  // namespace detail

inline void sheetLayout(int w, int h, const LabJudge& j, uint8_t page, uint8_t first, MeasureFn m, void* ctx, SheetLayout& L) {
  memset(&L, 0, sizeof(L));
  const bool wide = w >= 400;
  const int laterW = 100, backW = wide ? 120 : 92, nextW = wide ? 140 : 92, footY = h - kTarget - 6;
  L.later = box(w - kMargin - laterW, 0, laterW, kHeaderH);
  L.title = box(kMargin, 0, L.later.x - 2 * kMargin, kHeaderH);
  L.body = box(0, kHeaderH + 4, w, footY - 4 - (kHeaderH + 4));
  L.next = box(w - kMargin - nextW, footY, nextW, kTarget);
  const uint8_t pages = j.pages();
  if (page >= pages) page = (uint8_t)(pages - 1);
  L.hasBack = pages > 1;
  if (L.hasBack) L.back = box(kMargin, footY, backW, kTarget);
  L.up = box(w / 2 - 54, footY, 52, kTarget);
  L.down = box(w / 2 + 2, footY, 52, kTarget);
  const int labelW = wide ? kLabelColumn : w - 2 * kMargin;
  const int chipX0 = wide ? kMargin + kLabelColumn + kMargin : kMargin, chipX1 = w - kMargin;
  const int labelH = wide ? 0 : kLabelLine;
  if (j.sendPage(page) || !j.s.ok || j.s.phoneOnly) {
    L.status = L.body;
    if (j.sendPage(page) && j.state() == State::Draft) {
      L.reasons = true;
      L.rowCount = 1;
      ChipRow& r = L.rows[0];
      const int y = L.body.y;
      for (uint8_t i = 0; i < kReasonCount; ++i) r.chips[i] = box(chipX0, y + labelH + i * kLinePitch, chipX1 - chipX0, kTarget);
      r.chipCount = kReasonCount;
      r.lines = kReasonCount;
      r.h = (int16_t)(labelH + kReasonCount * kLinePitch);
      r.label = box(kMargin, y, labelW, wide ? kTarget : labelH);
      r.shown = true;
      L.status = box(0, y + r.h, w, L.body.y + L.body.h - (y + r.h));
    }
    return;
  }
  // A strip page: one row per criterion, chips "choices..., –".
  const uint8_t n = j.s.criterionCount;
  L.rowCount = n;
  int16_t heights[kMaxCriteria];
  for (uint8_t c = 0; c < n; ++c) {
    const Criterion& cr = j.s.criteria[c];
    const char* texts[kMaxChips];
    for (uint8_t k = 0; k < cr.choiceCount; ++k) texts[k] = cr.choices[k];
    texts[cr.choiceCount] = nullptr;  // "–": drawn as a dash, the narrowest chip
    detail::placeChips(L.rows[c], chipX0, chipX1, labelH, texts, (uint8_t)(cr.choiceCount + 1), m, ctx);
    L.rows[c].h = heights[c] = (int16_t)(labelH + L.rows[c].lines * kLinePitch);
  }
  // Scrolled by whole rows: maxFirst is the first row from which the rest fit.
  int tail = 0;
  L.maxFirst = n;
  for (int c = n - 1; c >= 0; --c) {
    tail += heights[c];
    if (tail > L.body.h) break;
    L.maxFirst = (uint8_t)c;
  }
  if (L.maxFirst >= n) L.maxFirst = n ? (uint8_t)(n - 1) : 0;
  L.first = first > L.maxFirst ? L.maxFirst : first;
  L.scrolls = L.maxFirst > 0;
  int y = L.body.y;
  for (uint8_t c = 0; c < n; ++c) {
    ChipRow& r = L.rows[c];
    const bool fits = c >= L.first && y + heights[c] <= L.body.y + L.body.h;
    if (!fits) {
      r.shown = false;
      for (uint8_t k = 0; k < r.chipCount; ++k) r.chips[k] = box(0, 0, 0, 0);
      r.label = box(0, 0, 0, 0);
      continue;
    }
    for (uint8_t k = 0; k < r.chipCount; ++k) r.chips[k].y = (int16_t)(r.chips[k].y + y);
    r.label = box(kMargin, y, labelW, wide ? kTarget : labelH);
    r.shown = true;
    y += heights[c];
  }
}

enum class HitKind : uint8_t { None, Later, Back, Next, ScrollUp, ScrollDown, Chip, Reason };
struct Hit {
  HitKind kind;
  uint8_t row;    // the criterion (Chip)
  uint8_t index;  // the choice (== choiceCount: "–"), or the reason
  Box box;        // what a press outlines
};

inline Hit hitTest(const SheetLayout& L, int x, int y) {
  Hit h = {HitKind::None, 0, 0, box(0, 0, 0, 0)};
  if (L.later.contains(x, y)) { h.kind = HitKind::Later; h.box = L.later; return h; }
  if (L.next.contains(x, y)) { h.kind = HitKind::Next; h.box = L.next; return h; }
  if (L.hasBack && L.back.contains(x, y)) { h.kind = HitKind::Back; h.box = L.back; return h; }
  if (L.scrolls && L.up.contains(x, y)) { h.kind = HitKind::ScrollUp; h.box = L.up; return h; }
  if (L.scrolls && L.down.contains(x, y)) { h.kind = HitKind::ScrollDown; h.box = L.down; return h; }
  for (uint8_t r = 0; r < L.rowCount; ++r) {
    if (!L.rows[r].shown) continue;
    for (uint8_t k = 0; k < L.rows[r].chipCount; ++k)
      if (L.rows[r].chips[k].contains(x, y)) {
        h.kind = L.reasons ? HitKind::Reason : HitKind::Chip;
        h.row = r;
        h.index = k;
        h.box = L.rows[r].chips[k];
        return h;
      }
  }
  return h;
}

}  // namespace lab
}  // namespace workshop
