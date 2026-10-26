// Host smoke test for firmware/platform/localai/workshop_localai_feed_core.hpp (Workshop OS 12.3.10): backoff,
// freshness, rotation, which cards the calm screen shows, and what settings are accepted.
#include "../firmware/platform/localai/workshop_localai_feed_core.hpp"

#include <cstdio>
#include <cstring>

using namespace workshop::localai;
static int failures = 0, checks = 0;
#define CHECK(c, what) do { ++checks; if (!(c)) { ++failures; std::printf("FAIL %s\n", what); } } while (0)

// Whole UTF-8 characters only: no lead byte without all its continuation bytes, no stray continuation byte.
static bool validUtf8(const char* s) {
  const unsigned char* p = reinterpret_cast<const unsigned char*>(s);
  while (*p) {
    const unsigned char c = *p;
    const int n = c < 0x80 ? 0 : (c & 0xE0) == 0xC0 ? 1 : (c & 0xF0) == 0xE0 ? 2 : (c & 0xF8) == 0xF0 ? 3 : -1;
    if (n < 0) return false;
    ++p;
    for (int k = 0; k < n; ++k, ++p)
      if ((*p & 0xC0) != 0x80) return false;
  }
  return true;
}

static Need need(const char* id, Tone tone, const char* title) {
  Need n{};
  setNeed(n, id, tone, title, "", "pi");
  return n;
}

// 26 Oct 2026: the feed's `needs` (Pi Hub's one list) and the Print lab cards.
static void checkNeedsAndLab() {
  {  // home_top_two_in_order: Pi Hub's order, as sent (it already ranks bad > attention > warn)
    const Need n[3] = {need("pi:disk", Tone::Bad, "Disk full"), need("printer:plate", Tone::Warning, "Clear the plate"),
                       need("localai:approval:7", Tone::Attention, "Approve the update")};
    int8_t out[2] = {9, 9};
    bool fromNeeds = false;
    uint8_t others = 9;
    CHECK(homeSummaryTop(n, 3, nullptr, 0, out, fromNeeds, others) == 2 && out[0] == 0 && out[1] == 1 && fromNeeds,
          "home_top_two_in_order: the first two needs, in Pi Hub's order");
    CHECK(others == 1, "home_top_two_in_order: one more");
  }
  {  // home_top_falls_back_to_cards: no needs (Pi Hub not answering) -> cards, ranked bad > attention > warning > busy > ok
    Card c[5] = {};
    c[0].tone = Tone::Ok; c[1].tone = Tone::Warning; c[2].tone = Tone::Busy; c[3].tone = Tone::Attention; c[4].tone = Tone::Info;
    int8_t out[2] = {9, 9};
    bool fromNeeds = true;
    uint8_t others = 9;
    CHECK(homeSummaryTop(nullptr, 0, c, 5, out, fromNeeds, others) == 2 && out[0] == 3 && out[1] == 1 && !fromNeeds && others == 0,
          "home_top_falls_back_to_cards: attention, then the warning");
    c[2].tone = Tone::Bad;
    CHECK(homeSummaryTop(nullptr, 0, c, 5, out, fromNeeds, others) == 2 && out[0] == 2 && out[1] == 3 && others == 1,
          "home_top_falls_back_to_cards: bad first; the warning left over is one more");
    c[1].tone = Tone::Info; c[2].tone = Tone::Busy; c[3].tone = Tone::Info;
    CHECK(homeSummaryTop(nullptr, 0, c, 5, out, fromNeeds, others) == 1 && out[0] == 2 && out[1] == -1 && others == 0,
          "home_top_falls_back_to_cards: work under way beats All clear, and All clear is never a second row");
    c[2].tone = Tone::Info;
    CHECK(homeSummaryTop(nullptr, 0, c, 5, out, fromNeeds, others) == 1 && out[0] == 0 && out[1] == -1,
          "home_top_falls_back_to_cards: nothing wrong: All clear");
    c[0].tone = Tone::Info;
    CHECK(homeSummaryTop(nullptr, 0, c, 5, out, fromNeeds, others) == 0 && out[0] == -1 && out[1] == -1,
          "home_top_falls_back_to_cards: information only: nothing");
    CHECK(homeSummaryTop(nullptr, 0, nullptr, 0, out, fromNeeds, others) == 0 && out[0] == -1 && !fromNeeds, "no needs, no cards");
  }
  {  // others_counts_the_rest
    Need n[kMaxNeeds];
    for (uint8_t i = 0; i < kMaxNeeds; ++i) n[i] = need("pi:x", Tone::Warning, "Something");
    int8_t out[2];
    bool fromNeeds = false;
    uint8_t others = 0;
    CHECK(homeSummaryTop(n, kMaxNeeds, nullptr, 0, out, fromNeeds, others) == 2 && others == kMaxNeeds - 2, "others_counts_the_rest: six needs, +4 more");
    CHECK(homeSummaryTop(n, 1, nullptr, 0, out, fromNeeds, others) == 1 && out[0] == 0 && out[1] == -1 && others == 0, "others_counts_the_rest: one need, no second row");
    Card c[4] = {};
    c[0].tone = Tone::Attention; c[1].tone = Tone::Warning; c[2].tone = Tone::Warning; c[3].tone = Tone::Busy;
    CHECK(homeSummaryTop(n, 0, c, 4, out, fromNeeds, others) == 2 && out[0] == 0 && out[1] == 1 && others == 1,
          "others_counts_the_rest: cards: the problems not shown");
  }
  {  // needs_utf8_cut: six needs with long UTF-8 titles and details; each copy ends on a character boundary
    struct Guarded { Need n[kMaxNeeds]; unsigned char tail[8]; } g;
    memset(&g, 0, sizeof(g));
    memset(g.tail, 0xA5, sizeof(g.tail));
    char title[128] = "", detail[512] = "", id[80] = "";
    for (int i = 0; i < 24; ++i) strcat(title, "\xC3\xA9");          // 24 x "e acute": 48 bytes
    strcat(title, "\xE2\x80\xA6");                                   // and the cut mark
    for (int i = 0; i < 90; ++i) strcat(detail, "\xF0\x9F\x94\xA5");  // 90 x a 4-byte emoji: 360 bytes
    for (int i = 0; i < 70; ++i) strcat(id, "a");
    for (uint8_t i = 0; i < kMaxNeeds; ++i) setNeed(g.n[i], id, toneFrom("bad"), title, detail, "localai-long-source");
    bool ok = true;
    for (uint8_t i = 0; i < kMaxNeeds; ++i) {
      ok = ok && strlen(g.n[i].title) < sizeof(g.n[i].title) && validUtf8(g.n[i].title);
      ok = ok && strlen(g.n[i].detail) < sizeof(g.n[i].detail) && validUtf8(g.n[i].detail);
      ok = ok && strlen(g.n[i].id) < sizeof(g.n[i].id) && strlen(g.n[i].source) < sizeof(g.n[i].source);
      ok = ok && g.n[i].tone == Tone::Bad;
    }
    CHECK(ok, "needs_utf8_cut: every field fits and is whole UTF-8");
    CHECK(strlen(g.n[0].title) == 26 && strlen(g.n[0].detail) == 108, "needs_utf8_cut: as many whole characters as fit");
    bool tail = true;
    for (size_t i = 0; i < sizeof(g.tail); ++i) tail = tail && g.tail[i] == 0xA5;
    CHECK(tail, "needs_utf8_cut: nothing written past the list");
    char small[4];
    copyUtf8(small, sizeof(small), "ab\xC3\xA9");
    CHECK(!strcmp(small, "ab"), "needs_utf8_cut: a 2-byte character that does not fit is left out whole");
    copyUtf8(small, sizeof(small), "abc");
    CHECK(!strcmp(small, "abc"), "needs_utf8_cut: ASCII fills the buffer");
    copyUtf8(small, sizeof(small), nullptr);
    CHECK(!small[0], "needs_utf8_cut: nothing in, nothing out");
    CHECK(toneFrom("warn") == Tone::Warning && toneFrom("warning") == Tone::Warning, "Pi Hub's warn is a warning");
  }
  {  // lab_card_takes_printing_extra_row
    CHECK(shownKind("lab"), "lab cards are shown");
    Card c[3] = {};
    strcpy(c[0].kind, "needs"); c[0].tone = Tone::Attention;
    strcpy(c[1].kind, "lab"); c[1].tone = Tone::Attention; strcpy(c[1].ask, "lab-judge"); strcpy(c[1].run, "PR-021-01");
    strcpy(c[2].kind, "lab"); c[2].tone = Tone::Busy; strcpy(c[2].title, "Lab \xC2\xB7 E-021");
    CHECK(sizeof(c[1].run) >= 16 && !strcmp(c[1].run, "PR-021-01") && !strcmp(c[1].ask, "lab-judge"), "the judge card keeps its run and ask");
    CHECK(printingExtraIndex(c, 3) == 2, "lab_card_takes_printing_extra_row: the busy lab card");
    c[2].tone = Tone::Ok;
    CHECK(printingExtraIndex(c, 3) == -1, "lab_card_takes_printing_extra_row: no busy lab card, no lab row");
    CHECK(printingExtraIndex(c, 0) == -1 && printingExtraIndex(nullptr, 3) == -1, "no cards, no lab row");
  }
}

int main() {
  CHECK(nextDelayMs(0) == 60000UL, "a minute after an answer");
  CHECK(nextDelayMs(1) == 120000UL && nextDelayMs(2) == 240000UL && nextDelayMs(3) == 480000UL, "doubling backoff");
  CHECK(nextDelayMs(4) == kMaxBackoffMs && nextDelayMs(200) == kMaxBackoffMs, "capped at 10 minutes");

  CHECK(!fresh(1000, 0), "never fetched is not fresh");
  CHECK(fresh(600000UL + 5, 5) && !fresh(600000UL + 6, 5), "10 minutes fresh");
  CHECK(fresh(10, 0xFFFFFFF0UL), "fresh across millis() wrap");

  CHECK(rotationIndex(0, 3) == 0 && rotationIndex(8000, 3) == 1 && rotationIndex(24000, 3) == 0, "8 s per card");
  CHECK(rotationIndex(12345, 0) == 0, "no cards, index 0");

  CHECK(shownKind("needs") && shownKind("watch") && shownKind("running") && shownKind("weather") && shownKind("materials"), "text cards shown");
  CHECK(!shownKind("image") && !shownKind("") && !shownKind(nullptr) && !shownKind("other"), "image and unknown cards skipped");
  CHECK(toneFrom("attention") == Tone::Attention && toneFrom("ok") == Tone::Ok && toneFrom("nope") == Tone::Info && toneFrom(nullptr) == Tone::Info, "tones");

  CHECK(validKey("wsd_0123456789abcdef0123456789abcdef0123456789abcdef"), "a display key");
  CHECK(!validKey("wsd_0123456789ABCDEF0123456789abcdef0123456789abcdef"), "uppercase refused");
  CHECK(!validKey("wsc_0123456789abcdef0123456789abcdef0123456789abcdef"), "other key kinds refused");
  CHECK(!validKey("wsd_0123") && !validKey(nullptr), "short or missing refused");

  CHECK(validPrivateIp("10.0.0.21") && validPrivateIp("192.168.1.2") && validPrivateIp("172.16.0.1") && validPrivateIp("172.31.255.254"), "private IPs");
  CHECK(!validPrivateIp("8.8.8.8") && !validPrivateIp("172.32.0.1") && !validPrivateIp("10.0.0") && !validPrivateIp("10.0.0.256"), "public or malformed refused");
  CHECK(!validPrivateIp("10.0.0.21x") && !validPrivateIp("") && !validPrivateIp(nullptr) && !validPrivateIp("10..0.1"), "junk refused");

  CHECK(validTlsName("localai.home.arpa"), "the certificate name");
  CHECK(!validTlsName("localhost") && !validTlsName("LocalAI.home.arpa") && !validTlsName("a b.c") && !validTlsName(".x.y") && !validTlsName(""), "names refused");

  // 12.4.2: ask buttons and the latest image.
  CHECK(validQuestion("needs") && validQuestion("running") && validQuestion("health"), "the three questions");
  CHECK(!validQuestion("delete") && !validQuestion("") && !validQuestion(nullptr), "other questions refused");
  CHECK(validImagePath("/api/images/view?filename=a.png&type=output&preview=jpeg%3B80"), "Local AI's image route");
  CHECK(!validImagePath("/api/display/feed") && !validImagePath("https://x/api/images/view?a=1") && !validImagePath(nullptr), "other paths refused");
  CHECK(!validImagePath("/api/images/view?a=1 HTTP/1.0\r\nX: y") && !validImagePath("/api/images/view?a=b c"), "no spaces or line breaks");
  {
    const uint8_t sof0[] = {0xFF, 0xD8, 0xFF, 0xE0, 0x00, 0x04, 0x00, 0x00, 0xFF, 0xC0, 0x00, 0x11, 0x08, 0x02, 0x00, 0x04, 0x00, 0x03};
    uint16_t w = 0, h = 0;
    CHECK(jpegSize(sof0, sizeof(sof0), w, h) && w == 1024 && h == 512, "baseline size from SOF0 after APP0");
    const uint8_t sof2[] = {0xFF, 0xD8, 0xFF, 0xC2, 0x00, 0x11, 0x08, 0x02, 0x00, 0x04, 0x00};
    CHECK(!jpegSize(sof2, sizeof(sof2), w, h), "progressive refused");
    const uint8_t png[] = {0x89, 'P', 'N', 'G', 0, 0, 0, 0};
    CHECK(!jpegSize(png, sizeof(png), w, h) && !jpegSize(sof0, 12, w, h), "not a JPEG, or cut short");
  }
  CHECK(fitScale(1024, 1024, 480, 292) > 0.285f && fitScale(1024, 1024, 480, 292) < 0.286f, "fit by height");
  CHECK(fitScale(1920, 1080, 480, 292) == 0.25f, "fit by width");
  CHECK(fitScale(200, 100, 480, 292) == 1.0f && fitScale(0, 10, 480, 292) == 0.0f, "never upscaled; no size, no scale");

  {
    char t[24];
    const uint32_t now = 1792500000UL;
    agoText(t, sizeof(t), now, now - 30); CHECK(!strcmp(t, "just now"), "just now");
    agoText(t, sizeof(t), now, now - 12 * 60); CHECK(!strcmp(t, "12 min ago"), "minutes");
    agoText(t, sizeof(t), now, now - 3 * 3600 - 5); CHECK(!strcmp(t, "3 h ago"), "hours");
    agoText(t, sizeof(t), now, now - 30 * 3600); CHECK(!strcmp(t, "yesterday"), "yesterday");
    agoText(t, sizeof(t), now, now - 4 * 86400); CHECK(!strcmp(t, "4 days ago"), "days");
    agoText(t, sizeof(t), now, 0); CHECK(!t[0], "unknown time: nothing");
    agoText(t, sizeof(t), 0, now); CHECK(!t[0], "clock not set: nothing");
    agoText(t, sizeof(t), now, now + 3600); CHECK(!t[0], "made in the future: nothing");
  }
  {  // 12.6
    CHECK(shownKind("done") && shownKind("disk"), "finished work and the disk are shown");
    CHECK(shownKind("playing") && shownKind("home"), "12.8: Now playing and the Pi hub's issue are shown");
    CHECK(validImagePath("/api/display/poster?n=0") && !validImagePath("/api/display/posterx") && !validImagePath("/api/display/poster?n=0 x"), "12.8: the poster route");
    CHECK(validQuestion("today") && validQuestion("next") && validQuestion("weather"), "the new questions");
    Card c{};
    strcpy(c.kind, "running");
    CHECK(!strcmp(askFor(c), "running"), "a card asks by its kind");
    strcpy(c.ask, "today");
    CHECK(!strcmp(askFor(c), "today"), "or by what Local AI says");
    strcpy(c.ask, "delete");
    strcpy(c.kind, "image");
    CHECK(askFor(c) == nullptr, "a bad ask and no kind: nothing");
    strcpy(c.kind, "disk"); c.ask[0] = 0;
    CHECK(!strcmp(askFor(c), "health"), "the disk asks about health");
    CHECK(validPage("image") && validPage("camera") && !validPage("settings") && !validPage(nullptr), "pages a message may open");
    CHECK(messageIsNew(5, 4, 0, 0) && !messageIsNew(4, 4, 0, 0), "newer than the last shown");
    CHECK(messageIsNew(9, 0, 1000, 1100) && !messageIsNew(9, 0, 1000, 1200) && !messageIsNew(9, 0, 0, 1100), "after a restart: the last 2 minutes only");
  }
  // Home at a glance: the house line and the header's weather.
  {
    Card c[4] = {};
    c[0].tone = Tone::Ok; c[1].tone = Tone::Warning; c[2].tone = Tone::Info; c[3].tone = Tone::Busy;
    uint8_t others = 9;
    CHECK(homeSummaryIndex(c, 4, others) == 1 && others == 0, "a warning beats All clear and work under way");
    c[3].tone = Tone::Attention;
    CHECK(homeSummaryIndex(c, 4, others) == 3 && others == 1, "attention first, the warning counted as one more");
    c[1].tone = Tone::Info; c[3].tone = Tone::Info;
    CHECK(homeSummaryIndex(c, 4, others) == 0 && others == 0, "nothing wrong: All clear");
    c[0].tone = Tone::Info;
    CHECK(homeSummaryIndex(c, 4, others) == -1, "information only: no house line");
    CHECK(homeSummaryIndex(c, 0, others) == -1, "no cards");
    char w[24];
    weatherShort(w, sizeof(w), "Right now in Lake Wylie: 66 degrees and sunny.");
    CHECK(!strcmp(w, "66\xC2\xB0 Sunny"), "66 degrees and sunny");
    weatherShort(w, sizeof(w), "Right now in Lake Wylie: -3 degrees and light snow.");
    CHECK(!strcmp(w, "-3\xC2\xB0 Light snow"), "below zero, two words");
    weatherShort(w, sizeof(w), "It is 71 degrees.");
    CHECK(!strcmp(w, "71\xC2\xB0"), "no sky");
    weatherShort(w, sizeof(w), "Weather is not set up.");
    CHECK(w[0] == 0, "no number: nothing");
    weatherShort(w, sizeof(w), nullptr);
    CHECK(w[0] == 0, "no text");
  }
  checkNeedsAndLab();
  std::printf("localai-feed smoke: %s (%d checks)\n", failures ? "FAIL" : "PASS", checks);
  return failures ? 1 : 0;
}
