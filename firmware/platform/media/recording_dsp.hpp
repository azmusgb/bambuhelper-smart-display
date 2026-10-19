#pragma once

// Workshop OS 12.3.6: playback processing for the WS350 five-second recorder.
//
// Plain C++11, no Arduino. The ES8311 has one (mono) ADC, but the I2S bus
// runs 16-bit stereo frames, so a recording holds the microphone in one slot
// and something else (a copy, noise or zeros) in the other. Up to 12.3.5 the
// recorder played the raw stereo frames back, amplified up to 96x from the
// clip's raw peak, which includes the ADC's DC offset. The ES8311 DAC plays
// one slot, so the speaker could get the wrong one, and the DC offset times
// the gain became a thump at the start and end of playback.
//
// Now the clip is analysed once before playback: the slot with the most AC
// energy is the microphone, its mean is the DC offset, and the gain comes
// from the DC-free peak, capped at 16x. Each played chunk takes that slot,
// removes the offset, applies the gain with saturation, fades the first and
// last 10 ms, and writes the same sample to both slots.
// tests/workshop_os12_recording_dsp_smoke.cpp checks these functions.

#include <math.h>
#include <stddef.h>
#include <stdint.h>

namespace workshop {
namespace media {
namespace dsp {

static const uint16_t kPlaybackTargetPeak = 12000U;
static const uint32_t kPlaybackMaxGainQ8 = 16U * 256U;  // 24 dB
static const size_t kPlaybackFadeFrames = 160U;          // 10 ms at 16 kHz

struct ClipAnalysis {
  uint8_t channel;   // 0 = left slot, 1 = right slot
  int16_t dc;        // mean of the chosen slot
  uint16_t peak;     // largest |sample - dc| on the chosen slot
  uint32_t gainQ8;   // playback gain, 256 = 1x
};

inline int16_t saturate16(int32_t v) {
  if (v > 32767) return 32767;
  if (v < -32768) return -32768;
  return static_cast<int16_t>(v);
}

// Gain that brings `peak` to `target`, never below 1x, never above maxGainQ8.
inline uint32_t gainForPeak(uint16_t peak, uint16_t target, uint32_t maxGainQ8) {
  if (peak == 0U || peak >= target) return 256U;
  uint32_t g = (static_cast<uint32_t>(target) * 256U) / peak;
  if (g > maxGainQ8) g = maxGainQ8;
  if (g < 256U) g = 256U;
  return g;
}

// `samples` is interleaved L/R; `frames` stereo frames.
inline ClipAnalysis analyzeStereoClip(const int16_t* samples, size_t frames, uint16_t target = kPlaybackTargetPeak,
                                      uint32_t maxGainQ8 = kPlaybackMaxGainQ8) {
  ClipAnalysis a;
  a.channel = 0;
  a.dc = 0;
  a.peak = 0;
  a.gainQ8 = 256U;
  if (!samples || frames == 0) return a;
  int64_t sum[2] = {0, 0};
  uint64_t sumSq[2] = {0, 0};
  for (size_t i = 0; i < frames; ++i) {
    for (int c = 0; c < 2; ++c) {
      const int32_t v = samples[i * 2 + c];
      sum[c] += v;
      sumSq[c] += static_cast<uint64_t>(static_cast<int64_t>(v) * v);
    }
  }
  double var[2];
  double mean[2];
  for (int c = 0; c < 2; ++c) {
    mean[c] = static_cast<double>(sum[c]) / static_cast<double>(frames);
    var[c] = static_cast<double>(sumSq[c]) / static_cast<double>(frames) - mean[c] * mean[c];
  }
  a.channel = var[1] > var[0] ? 1 : 0;
  const double m = mean[a.channel];
  a.dc = saturate16(static_cast<int32_t>(m >= 0 ? m + 0.5 : m - 0.5));
  int32_t peak = 0;
  for (size_t i = 0; i < frames; ++i) {
    int32_t v = static_cast<int32_t>(samples[i * 2 + a.channel]) - a.dc;
    if (v < 0) v = -v;
    if (v > peak) peak = v;
  }
  a.peak = static_cast<uint16_t>(peak > 65535 ? 65535 : peak);
  a.gainQ8 = gainForPeak(a.peak, target, maxGainQ8);
  return a;
}

// Fade weight (0..256) of stereo frame `frame` in a clip of `total` frames.
inline uint32_t fadeQ8(size_t frame, size_t total, size_t fadeFrames = kPlaybackFadeFrames) {
  if (fadeFrames == 0 || total == 0) return 256U;
  if (fadeFrames * 2 > total) fadeFrames = total / 2;
  if (fadeFrames == 0) return 256U;
  if (frame < fadeFrames) return static_cast<uint32_t>((frame * 256U) / fadeFrames);
  if (frame >= total) return 0U;
  const size_t fromEnd = total - 1 - frame;
  if (fromEnd < fadeFrames) return static_cast<uint32_t>((fromEnd * 256U) / fadeFrames);
  return 256U;
}

// One played sample: the chosen slot, DC removed, gain, fade, saturated.
inline int16_t renderSample(int16_t raw, const ClipAnalysis& a, uint32_t fade) {
  const int64_t centred = static_cast<int32_t>(raw) - a.dc;
  int64_t scaled = (centred * static_cast<int64_t>(a.gainQ8) * static_cast<int64_t>(fade)) / 65536;
  if (scaled > 32767) scaled = 32767;
  if (scaled < -32768) scaled = -32768;
  return static_cast<int16_t>(scaled);
}

// Renders `frames` stereo frames starting at clip frame `start` into `dst`
// (interleaved, both slots carry the microphone).
inline void renderChunk(const int16_t* clip, size_t start, size_t frames, size_t total, const ClipAnalysis& a,
                        int16_t* dst) {
  for (size_t i = 0; i < frames; ++i) {
    const size_t f = start + i;
    const int16_t out = f < total ? renderSample(clip[f * 2 + a.channel], a, fadeQ8(f, total)) : 0;
    dst[i * 2] = out;
    dst[i * 2 + 1] = out;
  }
}

// Microphone meter: -60..0 dBFS of a peak mapped to 0..100 (the same scale
// as /os12/media/status microphoneLevelPercent).
inline uint8_t levelPercentFromPeak(uint32_t peak) {
  if (peak == 0U) return 0U;
  if (peak > 32767U) peak = 32767U;
  const float dbfs = 20.0f * log10f(static_cast<float>(peak) / 32767.0f);
  const long level = lroundf(((dbfs + 60.0f) * 100.0f) / 60.0f);
  return static_cast<uint8_t>(level < 0 ? 0 : (level > 100 ? 100 : level));
}

}  // namespace dsp
}  // namespace media
}  // namespace workshop
