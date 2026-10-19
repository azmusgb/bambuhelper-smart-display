// Host test for firmware/platform/media/recording_dsp.hpp (12.3.6 recorder
// playback on the WS350).
//
// Builds synthetic 16 kHz stereo clips the way the ES8311 delivers them (the
// microphone in one slot, a DC offset, and noise or zeros in the other) and
// checks that playback picks the microphone slot, removes the DC offset,
// caps the gain at 16x, starts and ends at silence, never clips, and writes
// the same sample to both slots.
//
//   g++ -std=c++11 -Wall -Wextra -Werror -pedantic tests/workshop_os12_recording_dsp_smoke.cpp -o /tmp/recording-dsp-smoke

#include "../firmware/platform/media/recording_dsp.hpp"

#include <math.h>
#include <stdio.h>
#include <stdlib.h>

using namespace workshop::media::dsp;

namespace {

int g_failures = 0;
int g_checks = 0;

void check(bool ok, const char* what, long a = 0, long b = 0) {
  ++g_checks;
  if (ok) return;
  ++g_failures;
  if (g_failures <= 40) printf("FAIL %s (%ld, %ld)\n", what, a, b);
}

const size_t kFrames = 16000 * 5;  // five seconds
int16_t g_clip[kFrames * 2];
int16_t g_out[256 * 2];

// Mic slot: a 440 Hz tone of `amp` on top of `dc`. Other slot: `otherDc`
// plus small noise.
void makeClip(int micSlot, int amp, int dc, int otherDc, int otherNoise) {
  srand(7);
  for (size_t i = 0; i < kFrames; ++i) {
    const double t = static_cast<double>(i) / 16000.0;
    const int mic = dc + static_cast<int>(lround(amp * sin(2.0 * 3.14159265358979 * 440.0 * t)));
    const int other = otherDc + (otherNoise ? (rand() % (2 * otherNoise + 1)) - otherNoise : 0);
    g_clip[i * 2 + micSlot] = saturate16(mic);
    g_clip[i * 2 + (1 - micSlot)] = saturate16(other);
  }
}

// Renders the whole clip and returns max |out|, checking both slots match.
int renderAll(const ClipAnalysis& a, int& firstAbs, int& lastAbs, double& outMean) {
  int maxAbs = 0;
  double sum = 0;
  for (size_t start = 0; start < kFrames; start += 128) {
    const size_t n = kFrames - start < 128 ? kFrames - start : 128;
    renderChunk(g_clip, start, n, kFrames, a, g_out);
    for (size_t i = 0; i < n; ++i) {
      check(g_out[i * 2] == g_out[i * 2 + 1], "both slots carry the microphone", static_cast<long>(start + i));
      const int v = g_out[i * 2] < 0 ? -g_out[i * 2] : g_out[i * 2];
      if (v > maxAbs) maxAbs = v;
      sum += g_out[i * 2];
      if (start + i == 0) firstAbs = v;
      if (start + i == kFrames - 1) lastAbs = v;
    }
  }
  outMean = sum / static_cast<double>(kFrames);
  return maxAbs;
}

}  // namespace

int main() {
  // Quiet mic on the right slot with a big DC offset; left slot noisy DC.
  makeClip(1, 400, -900, 120, 30);
  ClipAnalysis a = analyzeStereoClip(g_clip, kFrames);
  check(a.channel == 1, "picks the slot with the microphone (right)", a.channel);
  check(abs(a.dc + 900) <= 2, "DC offset measured", a.dc);
  check(abs(static_cast<int>(a.peak) - 400) <= 2, "peak measured without the DC offset", a.peak);
  check(a.gainQ8 == kPlaybackMaxGainQ8, "gain capped at 16x for a quiet clip", static_cast<long>(a.gainQ8));
  int first = 0, last = 0;
  double mean = 0;
  int peak = renderAll(a, first, last, mean);
  check(peak <= 32767, "no overflow");
  check(peak >= 400 * 16 - 64 && peak <= 400 * 16 + 64, "quiet clip amplified 16x", peak);
  check(first == 0 && last == 0, "playback starts and ends at silence", first, last);
  check(fabs(mean) < 20.0, "no DC offset left in playback", static_cast<long>(mean));

  // 12.3.5 would have used the raw peak (|-900 - 400| = 1300) and played the
  // left slot: check the old behaviour really was wrong for this clip.
  int16_t rawPeak = 0;
  for (size_t i = 0; i < kFrames * 2; ++i) {
    const int v = g_clip[i] < 0 ? -g_clip[i] : g_clip[i];
    if (v > rawPeak) rawPeak = static_cast<int16_t>(v);
  }
  check(rawPeak >= 1290, "the raw peak includes the DC offset", rawPeak);

  // Loud mic on the left slot, zeros on the right: unity-ish gain, no clipping.
  makeClip(0, 20000, 300, 0, 0);
  a = analyzeStereoClip(g_clip, kFrames);
  check(a.channel == 0, "picks the left slot when the microphone is there", a.channel);
  check(a.gainQ8 == 256U, "a loud clip is not amplified", static_cast<long>(a.gainQ8));
  peak = renderAll(a, first, last, mean);
  check(peak <= 20000 + 8, "a loud clip is not boosted", peak);

  // Medium clip: brought to the target peak.
  makeClip(1, 3000, 0, 0, 0);
  a = analyzeStereoClip(g_clip, kFrames);
  check(a.gainQ8 == (static_cast<uint32_t>(kPlaybackTargetPeak) * 256U) / 3000U, "medium clip gain to target",
        static_cast<long>(a.gainQ8));
  peak = renderAll(a, first, last, mean);
  check(abs(peak - kPlaybackTargetPeak) <= 64, "medium clip peaks at the target", peak);

  // Saturation: a DC-free full-scale square with gain forced high stays in range.
  for (size_t i = 0; i < kFrames; ++i) { g_clip[i * 2] = (i & 64) ? 32000 : -32000; g_clip[i * 2 + 1] = 0; }
  a = analyzeStereoClip(g_clip, kFrames);
  a.gainQ8 = 16U * 256U;
  peak = renderAll(a, first, last, mean);
  check(peak <= 32768, "saturates instead of wrapping", peak);

  // Fades and gains.
  check(fadeQ8(0, 1000) == 0 && fadeQ8(500, 1000) == 256 && fadeQ8(999, 1000) == 0, "fade shape");
  check(fadeQ8(80, 1000) == 128, "fade is linear", static_cast<long>(fadeQ8(80, 1000)));
  check(fadeQ8(3, 4) <= 256 && fadeQ8(0, 1) == 256, "tiny clips do not divide by zero");
  check(gainForPeak(0, 12000, 4096) == 256 && gainForPeak(13000, 12000, 4096) == 256, "gain bounds");
  check(analyzeStereoClip(nullptr, 0).gainQ8 == 256, "empty clip is unity");

  // Meter scale matches the firmware's -60..0 dBFS map.
  check(levelPercentFromPeak(0) == 0 && levelPercentFromPeak(32767) == 100, "meter ends");
  check(levelPercentFromPeak(33) == 0, "-60 dBFS is 0%", levelPercentFromPeak(33));
  check(levelPercentFromPeak(395) == 36, "the 12.3.5 baseline peak 395 reads 36%", levelPercentFromPeak(395));

  if (g_failures) {
    printf("recording-dsp smoke: %d of %d checks failed\n", g_failures, g_checks);
    return 1;
  }
  printf("recording-dsp smoke: PASS (%d checks)\n", g_checks);
  return 0;
}
