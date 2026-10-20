// Host smoke test for firmware/platform/localai/workshop_localai_feed_core.hpp (Workshop OS 12.3.10): backoff,
// freshness, rotation, which cards the calm screen shows, and what settings are accepted.
#include "../firmware/platform/localai/workshop_localai_feed_core.hpp"

#include <cstdio>

using namespace workshop::localai;
static int failures = 0, checks = 0;
#define CHECK(c, what) do { ++checks; if (!(c)) { ++failures; std::printf("FAIL %s\n", what); } } while (0)

int main() {
  CHECK(nextDelayMs(0) == 60000UL, "a minute after an answer");
  CHECK(nextDelayMs(1) == 120000UL && nextDelayMs(2) == 240000UL && nextDelayMs(3) == 480000UL, "doubling backoff");
  CHECK(nextDelayMs(4) == kMaxBackoffMs && nextDelayMs(200) == kMaxBackoffMs, "capped at 10 minutes");

  CHECK(!fresh(1000, 0), "never fetched is not fresh");
  CHECK(fresh(600000UL + 5, 5) && !fresh(600000UL + 6, 5), "10 minutes fresh");
  CHECK(fresh(10, 0xFFFFFFF0UL), "fresh across millis() wrap");

  CHECK(rotationIndex(0, 3) == 0 && rotationIndex(8000, 3) == 1 && rotationIndex(24000, 3) == 0, "8 s per card");
  CHECK(rotationIndex(12345, 0) == 0, "no cards, index 0");

  CHECK(shownKind("needs") && shownKind("watch") && shownKind("running") && shownKind("weather"), "text cards shown");
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
  CHECK(!validQuestion("weather") && !validQuestion("") && !validQuestion(nullptr), "other questions refused");
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

  std::printf("localai-feed smoke: %s (%d checks)\n", failures ? "FAIL" : "PASS", checks);
  return failures ? 1 : 0;
}
