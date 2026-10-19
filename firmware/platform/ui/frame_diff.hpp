#pragma once

// Workshop OS 12.3.6: push only the rows of the WS350 frame that changed.
//
// Plain C++11, no Arduino. The Home, Printer, Workshop and More pages are
// composed into a 480x320 16-bit PSRAM sprite every display tick (250 ms) and
// after every tap. Up to 12.3.5 every tick pushed the whole sprite to the
// ST7796 (307,200 bytes at 40 MHz SPI: at least 61 ms with the main loop
// blocked, so the FT6336 was not read and short taps were lost). The firmware
// now hashes each row of the composed frame, compares it with the hashes of
// the frame already on the panel, and pushes only the bands that differ.
// tests/workshop_os12_frame_diff_smoke.cpp checks these functions on the host.

#include <stddef.h>
#include <stdint.h>

namespace workshop {
namespace ui {
namespace frame {

struct Band {
  int16_t y;
  int16_t h;
};

// FNV-1a over one row of 16-bit pixels.
inline uint32_t rowHash(const uint16_t* row, int width) {
  uint32_t h = 2166136261u;
  for (int x = 0; x < width; ++x) {
    h ^= row[x];
    h *= 16777619u;
  }
  return h;
}

// Changed-row bands between the frame on the panel (`shown`) and the new one
// (`next`), both one hash per row. Bands closer than `mergeGap` rows are
// joined (one SPI transaction is cheaper than two short ones). Returns the
// number of bands written to `out`; when there would be more than `maxBands`,
// one band from the first to the last changed row is returned instead.
inline uint8_t diffBands(const uint32_t* shown, const uint32_t* next, int rows, int mergeGap, Band* out,
                         uint8_t maxBands) {
  if (!shown || !next || !out || rows <= 0 || maxBands == 0) return 0;
  uint8_t n = 0;
  bool overflow = false;
  int first = -1, last = -1;
  int start = -1, end = -1;  // current band, inclusive
  for (int y = 0; y < rows; ++y) {
    if (shown[y] == next[y]) continue;
    if (first < 0) first = y;
    last = y;
    if (start >= 0 && y - end - 1 <= mergeGap) {
      end = y;
      continue;
    }
    if (start >= 0) {
      if (n < maxBands) { out[n].y = static_cast<int16_t>(start); out[n].h = static_cast<int16_t>(end - start + 1); ++n; }
      else overflow = true;
    }
    start = end = y;
  }
  if (start >= 0) {
    if (n < maxBands) { out[n].y = static_cast<int16_t>(start); out[n].h = static_cast<int16_t>(end - start + 1); ++n; }
    else overflow = true;
  }
  if (overflow) {
    out[0].y = static_cast<int16_t>(first);
    out[0].h = static_cast<int16_t>(last - first + 1);
    return 1;
  }
  return n;
}

// Rows the bands cover.
inline int bandRows(const Band* bands, uint8_t n) {
  int total = 0;
  for (uint8_t i = 0; i < n; ++i) total += bands[i].h;
  return total;
}

}  // namespace frame
}  // namespace ui
}  // namespace workshop
