// Host test for firmware/platform/media/mic_meter.hpp (12.3.8).
//
// Meter: silence with an ADC offset reads near zero, a tone reads its own
// amplitude whatever the offset and whichever slot carries it, and the DC
// estimate follows a slow drift. Gate: the main loop's free waits for an
// audio task that is inside, a task never enters a closed gate, and with a
// real second thread a buffer that is freed and replaced is never touched
// after its free.
//
//   g++ -std=c++11 -Wall -Wextra -Werror -pedantic -pthread tests/workshop_os12_mic_meter_smoke.cpp -o /tmp/mic-meter-smoke

#include "../firmware/platform/media/mic_meter.hpp"

#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include <atomic>
#include <thread>

using namespace workshop::media::meter;

namespace {

int g_failures = 0;
long g_checks = 0;

void check(bool ok, const char* what, long a = 0, long b = 0) {
  ++g_checks;
  if (ok) return;
  ++g_failures;
  if (g_failures <= 40) printf("FAIL %s (%ld, %ld)\n", what, a, b);
}

const int kFrames = 128;  // one 8 ms chunk at 16 kHz
std::int16_t g_chunk[kFrames * 2];

// Interleaved stereo chunk: `slot` carries offset + amplitude * sin, the
// other slot carries `otherDc`.
void fill(int slot, int offset, int amplitude, int otherDc, double hz, long& phase) {
  for (int i = 0; i < kFrames; ++i) {
    const double v = offset + amplitude * sin(2.0 * 3.14159265358979 * hz * (phase + i) / 16000.0);
    g_chunk[i * 2 + slot] = static_cast<std::int16_t>(lround(v));
    g_chunk[i * 2 + (1 - slot)] = static_cast<std::int16_t>(otherDc);
  }
  phase += kFrames;
}

void meter() {
  // 12.3.5/12.3.6 symptom: the raw peak of a quiet room is the ADC offset.
  for (int offset = -1200; offset <= 1200; offset += 300) {
    for (int slot = 0; slot < 2; ++slot) {
      DcMeter m;
      long phase = 0;
      std::uint16_t peak = 0;
      for (int c = 0; c < 40; ++c) {
        fill(slot, offset, 0, offset / 2, 440.0, phase);
        peak = m.chunkPeak(g_chunk, kFrames * 2);
      }
      check(peak <= 1, "silence with an offset reads near zero", offset, peak);
      check(m.dc(slot) == offset, "DC estimate is the offset", offset, m.dc(slot));
    }
  }
  // A tone reads its amplitude, with or without an offset, in either slot.
  for (int amplitude = 200; amplitude <= 12000; amplitude *= 3) {
    for (int offset = -900; offset <= 900; offset += 900) {
      for (int slot = 0; slot < 2; ++slot) {
        DcMeter m;
        long phase = 0;
        std::uint16_t peak = 0;
        for (int c = 0; c < 64; ++c) {
          fill(slot, offset, amplitude, 0, 300.0, phase);
          peak = m.chunkPeak(g_chunk, kFrames * 2);
        }
        const int err = abs(static_cast<int>(peak) - amplitude);
        check(err <= amplitude / 10 + 2, "tone peak is its amplitude, not amplitude + offset", amplitude * 10 + slot, peak);
      }
    }
  }
  // A slow drift of the offset is followed.
  DcMeter drift;
  long phase = 0;
  for (int c = 0; c < 400; ++c) {
    fill(0, c, 0, 0, 0.0, phase);  // offset rises 1 count per chunk
    drift.chunkPeak(g_chunk, kFrames * 2);
  }
  check(abs(drift.dc(0) - 399) <= 40, "DC estimate follows a slow drift", drift.dc(0));
  check(drift.seeded(), "seeded");
  drift.reset();
  check(!drift.seeded() && drift.dc(0) == 0, "reset");
  check(drift.chunkPeak(nullptr, 0) == 0 && drift.chunkPeak(g_chunk, 1) == 0, "empty chunk");
}

void gateSingleThread() {
  BufferGate g;
  check(g.idle() && !g.closed(), "gate starts open and idle");
  check(g.enter(), "task enters an open gate");
  check(!g.idle(), "a task inside: not idle");
  g.close();
  check(!g.idle(), "closing does not pretend the task left");
  check(!g.enter(), "no new entry once closed");
  check(!g.idle(), "refused entry leaves the count as it was");
  g.leave();
  check(g.idle(), "idle once the task leaves");
  g.open();
  check(g.enter(), "open again");
  g.leave();
  check(g.idle(), "idle");
}

// Main loop frees and reallocates a buffer while a "task" thread keeps
// writing into it through the gate. The writer checks a canary that the
// freeing side poisons before release; a write after the free would see it.
struct Shared {
  BufferGate gate;
  std::atomic<std::uint8_t*> data{nullptr};
  std::atomic<bool> stop{false};
  std::atomic<long> writes{0};
  std::atomic<long> violations{0};
};

void writer(Shared* s) {
  while (!s->stop.load()) {
    if (!s->gate.enter()) continue;
    std::uint8_t* d = s->data.load();
    if (d != nullptr) {
      if (d[0] != 0xA5) s->violations.fetch_add(1);  // poisoned: touched after free
      memset(d + 1, 0x5A, 255);
      s->writes.fetch_add(1);
    }
    s->gate.leave();
  }
}

void gateThreads() {
  Shared s;
  std::uint8_t* first = static_cast<std::uint8_t*>(malloc(256));
  first[0] = 0xA5;
  s.data.store(first);
  std::thread t(writer, &s);
  for (int i = 0; i < 3000; ++i) {
    s.gate.close();
    while (!s.gate.idle()) std::this_thread::yield();
    std::uint8_t* old = s.data.exchange(nullptr);
    if (old != nullptr) {
      old[0] = 0x00;  // poison: any later write through this pointer is a violation
      free(old);
    }
    std::uint8_t* next = static_cast<std::uint8_t*>(malloc(256));
    next[0] = 0xA5;
    s.data.store(next);
    s.gate.open();
    for (int spin = 0; spin < 50; ++spin) std::this_thread::yield();
  }
  s.stop.store(true);
  t.join();
  free(s.data.exchange(nullptr));
  check(s.violations.load() == 0, "no write after a free", s.violations.load());
  check(s.writes.load() > 0, "the writer ran", s.writes.load());
}

}  // namespace

int main() {
  meter();
  gateSingleThread();
  gateThreads();
  if (g_failures) {
    printf("mic-meter smoke: %d of %ld checks failed\n", g_failures, g_checks);
    return 1;
  }
  printf("mic-meter smoke: PASS (%ld checks)\n", g_checks);
  return 0;
}
