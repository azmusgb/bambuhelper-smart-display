#pragma once

// Workshop OS 12.3.8: microphone meter without DC, and safe hand-over of the
// recording buffer between the main loop and the audio task. Pure and
// host-tested (tests/workshop_os12_mic_meter_smoke.cpp).
//
// Meter. The ES8311 ADC has a DC offset, and 12.3.6's meter took the peak of
// the raw samples, so a silent room read as the offset (and a sound that
// swung against the offset read lower than one that swung with it).
// DcMeter keeps a running DC estimate for each of the two I2S slots and
// returns the peak of the samples with that estimate removed. The first chunk
// seeds the estimate with its own mean; after that it follows each chunk's
// mean with a time constant of kDcShiftChunks (2^5 = 32 chunks of 8 ms, about
// a quarter of a second), slow enough that speech is not removed with it.
//
// Buffer gate. The main loop frees and replaces the PSRAM recording while the
// audio task may be copying into it or playing it. BufferGate is a counted
// gate: the audio task enter()s before touching the buffer and leave()s
// after; the main loop close()s it, waits until idle(), frees or replaces the
// buffer, and open()s it again. With sequentially consistent atomics a task
// that entered before close() is waited for, and one that comes later sees
// the gate closed and leaves the buffer alone.

#include <atomic>
#include <cstddef>
#include <cstdint>

namespace workshop {
namespace media {
namespace meter {

constexpr unsigned kDcShiftChunks = 5;

class DcMeter {
public:
    // Peak of |sample - DC| over one chunk of interleaved stereo samples
    // (`count` int16 values, two per frame). Updates the DC estimate.
    std::uint16_t chunkPeak(const std::int16_t* samples, std::size_t count) {
        if (samples == nullptr || count < 2) return 0;
        const std::size_t frames = count / 2;
        std::int64_t sum[2] = {0, 0};
        for (std::size_t i = 0; i < frames; ++i) {
            sum[0] += samples[i * 2];
            sum[1] += samples[i * 2 + 1];
        }
        for (int s = 0; s < 2; ++s) {
            const std::int32_t mean = static_cast<std::int32_t>(sum[s] / static_cast<std::int64_t>(frames));
            if (!seeded_) {
                dcQ8_[s] = mean * 256;
            } else {
                // dc += (mean - dc) / 2^kDcShiftChunks, in Q8 so a slow
                // drift still moves it.
                dcQ8_[s] += (mean * 256 - dcQ8_[s]) / (1 << kDcShiftChunks);
            }
        }
        seeded_ = true;
        std::int32_t peak = 0;
        for (std::size_t i = 0; i < frames * 2; ++i) {
            std::int32_t v = static_cast<std::int32_t>(samples[i]) - dc(static_cast<int>(i & 1U));
            if (v < 0) v = -v;
            if (v > peak) peak = v;
        }
        return static_cast<std::uint16_t>(peak > 65535 ? 65535 : peak);
    }

    std::int32_t dc(int slot) const { return dcQ8_[slot & 1] / 256; }
    bool seeded() const { return seeded_; }
    void reset() {
        seeded_ = false;
        dcQ8_[0] = 0;
        dcQ8_[1] = 0;
    }

private:
    bool seeded_{false};
    std::int32_t dcQ8_[2] = {0, 0};
};

class BufferGate {
public:
    // Audio task: true when it may touch the buffer; then leave() when done.
    bool enter() {
        users_.fetch_add(1);
        if (closed_.load()) {
            users_.fetch_sub(1);
            return false;
        }
        return true;
    }
    void leave() { users_.fetch_sub(1); }

    // Main loop: close, wait for idle(), change the buffer, open.
    void close() { closed_.store(true); }
    bool idle() const { return users_.load() == 0; }
    void open() { closed_.store(false); }
    bool closed() const { return closed_.load(); }

private:
    std::atomic<int> users_{0};
    std::atomic<bool> closed_{false};
};

}  // namespace meter
}  // namespace media
}  // namespace workshop
