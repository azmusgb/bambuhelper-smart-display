// Host test for firmware/platform/ui/frame_diff.hpp (12.3.6 changed-row
// pushes on the WS350).
//
// Checks that an unchanged frame pushes nothing, that one changed row pushes
// exactly that row, that a tapped 44 px row pushes only its band, that nearby
// bands merge, that too many bands collapse to one first-to-last band, and
// that every changed row is always covered.
//
//   g++ -std=c++11 -Wall -Wextra -Werror -pedantic tests/workshop_os12_frame_diff_smoke.cpp -o /tmp/frame-diff-smoke

#include "../firmware/platform/ui/frame_diff.hpp"

#include <stdio.h>
#include <string.h>

using namespace workshop::ui::frame;

namespace {

int g_failures = 0;
int g_checks = 0;

void check(bool ok, const char* what, int a = 0, int b = 0) {
  ++g_checks;
  if (ok) return;
  ++g_failures;
  if (g_failures <= 40) printf("FAIL %s (%d, %d)\n", what, a, b);
}

const int kW = 480;
const int kH = 320;
uint16_t g_a[kH][kW];
uint16_t g_b[kH][kW];
uint32_t g_ha[kH];
uint32_t g_hb[kH];

void hashAll() {
  for (int y = 0; y < kH; ++y) {
    g_ha[y] = rowHash(g_a[y], kW);
    g_hb[y] = rowHash(g_b[y], kW);
  }
}

bool covered(const Band* bands, uint8_t n, int y) {
  for (uint8_t i = 0; i < n; ++i)
    if (y >= bands[i].y && y < bands[i].y + bands[i].h) return true;
  return false;
}

void checkCoverage(const Band* bands, uint8_t n, const char* what) {
  for (int y = 0; y < kH; ++y)
    if (g_ha[y] != g_hb[y]) check(covered(bands, n, y), what, y);
  for (uint8_t i = 0; i < n; ++i) {
    check(bands[i].h > 0 && bands[i].y >= 0 && bands[i].y + bands[i].h <= kH, "band on screen", bands[i].y, bands[i].h);
    if (i) check(bands[i].y > bands[i - 1].y + bands[i - 1].h, "bands ordered and apart", i);
  }
}

}  // namespace

int main() {
  for (int y = 0; y < kH; ++y)
    for (int x = 0; x < kW; ++x) g_a[y][x] = static_cast<uint16_t>((x * 7 + y * 13) & 0xFFFF);
  memcpy(g_b, g_a, sizeof(g_a));
  Band bands[6];

  hashAll();
  check(diffBands(g_ha, g_hb, kH, 8, bands, 6) == 0, "an unchanged frame pushes nothing");

  // One pixel in one row.
  g_b[100][240] ^= 0x0101;
  hashAll();
  uint8_t n = diffBands(g_ha, g_hb, kH, 8, bands, 6);
  check(n == 1 && bands[0].y == 100 && bands[0].h == 1, "one changed row pushes that row", n, bands[0].y);
  checkCoverage(bands, n, "one row covered");

  // A tapped toggle row (y 89..132) redrawn: only its band.
  memcpy(g_b, g_a, sizeof(g_a));
  for (int y = 90; y < 132; ++y)
    for (int x = 400; x < 460; ++x) g_b[y][x] = 0xFFFF;
  hashAll();
  n = diffBands(g_ha, g_hb, kH, 8, bands, 6);
  check(n == 1 && bands[0].y == 90 && bands[0].h == 42, "a tapped row pushes only its band", bands[0].y, bands[0].h);
  check(bandRows(bands, n) * 100 / kH < 15, "a row tap pushes under 15% of the frame", bandRows(bands, n));
  checkCoverage(bands, n, "row covered");

  // Header toast + one row: two bands; close changes merge.
  memcpy(g_b, g_a, sizeof(g_a));
  g_b[10][10] ^= 1;
  g_b[200][10] ^= 1;
  g_b[205][10] ^= 1;
  hashAll();
  n = diffBands(g_ha, g_hb, kH, 8, bands, 6);
  check(n == 2, "two separate areas give two bands", n);
  check(n == 2 && bands[1].y == 200 && bands[1].h == 6, "rows 5 apart merge into one band", bands[1].y, bands[1].h);
  checkCoverage(bands, n, "two areas covered");

  // Too many bands: one band from the first to the last change.
  memcpy(g_b, g_a, sizeof(g_a));
  for (int y = 0; y < kH; y += 20) g_b[y][0] ^= 1;
  hashAll();
  n = diffBands(g_ha, g_hb, kH, 8, bands, 6);
  check(n == 1 && bands[0].y == 0 && bands[0].h == 301, "overflow collapses to first..last", bands[0].y, bands[0].h);
  checkCoverage(bands, n, "overflow covered");

  // Full change: one band, the whole frame.
  for (int y = 0; y < kH; ++y) g_b[y][1] ^= 1;
  hashAll();
  n = diffBands(g_ha, g_hb, kH, 8, bands, 6);
  check(n == 1 && bands[0].y == 0 && bands[0].h == kH, "full change is one full band", bands[0].y, bands[0].h);

  // Every single-row and every pair of rows is covered, with any merge gap.
  for (int gap = 0; gap <= 16; gap += 4) {
    for (int y1 = 0; y1 < kH; y1 += 7) {
      for (int y2 = y1; y2 < kH; y2 += 29) {
        memcpy(g_b, g_a, sizeof(g_a));
        g_b[y1][3] ^= 1;
        g_b[y2][5] ^= 1;
        hashAll();
        n = diffBands(g_ha, g_hb, kH, gap, bands, 6);
        check(n >= 1, "a change gives at least one band", y1, y2);
        checkCoverage(bands, n, "pair covered");
      }
    }
  }

  check(diffBands(nullptr, g_hb, kH, 8, bands, 6) == 0, "null input pushes nothing");
  check(rowHash(g_a[0], kW) != rowHash(g_a[1], kW), "different rows hash differently");

  if (g_failures) {
    printf("frame-diff smoke: %d of %d checks failed\n", g_failures, g_checks);
    return 1;
  }
  printf("frame-diff smoke: PASS (%d checks)\n", g_checks);
  return 0;
}
