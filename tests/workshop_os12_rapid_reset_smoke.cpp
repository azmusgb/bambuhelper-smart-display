// Host test for firmware/platform/recovery/rapid_reset_policy.hpp.
//
//   g++ -std=c++11 -Wall -Wextra -Werror -pedantic tests/workshop_os12_rapid_reset_smoke.cpp -o rapid-reset-smoke

#include "../firmware/platform/recovery/rapid_reset_policy.hpp"

#include <stdio.h>

using namespace workshop::recovery;

namespace {

int g_failures = 0;

void check(bool ok, const char* what) {
  if (ok) return;
  ++g_failures;
  printf("FAIL %s\n", what);
}

// Simulated NVS cell and one boot that lasts `uptimeMs` before the next reset.
struct Device {
  uint8_t nvs;
  Device() : nvs(0) {}
  bool boot(uint32_t uptimeMs) {
    bool safe = false;
    nvs = rapidResetOnBoot(nvs, safe);
    bool cleared = false;
    for (uint32_t t = 0; t <= uptimeMs; t += 500) {
      if (rapidResetWindowClosed(t, cleared)) { nvs = 0; cleared = true; }
    }
    return safe;
  }
};

}  // namespace

int main() {
  {
    Device d;  // three resets 4 s apart (the case that failed on the device)
    check(!d.boot(4000), "first quick boot is normal");
    check(!d.boot(4000), "second quick boot is normal");
    check(d.boot(4000), "third quick boot enters Safe Mode");
    check(d.nvs == 0, "count restarts after Safe Mode");
  }
  {
    Device d;  // a healthy boot in between breaks the sequence
    check(!d.boot(4000), "quick boot");
    check(!d.boot(20000), "healthy boot");
    check(!d.boot(4000), "quick boot after healthy boot");
    check(!d.boot(4000), "second quick boot after healthy boot");
    check(d.boot(4000), "third quick boot after healthy boot");
  }
  {
    Device d;  // normal power-ups never accumulate
    for (int i = 0; i < 10; ++i) check(!d.boot(60000), "normal boots never enter Safe Mode");
    check(d.nvs == 0, "normal boot clears the count");
  }
  {
    bool safe = true;
    check(rapidResetOnBoot(0xFF, safe) == 0 && safe, "corrupt stored count fails safe");
    check(rapidResetOnBoot(1, safe) == 2 && !safe, "count increments");
    check(!rapidResetWindowClosed(14999, false), "window open before 15 s");
    check(rapidResetWindowClosed(15000, false), "window closes at 15 s");
    check(!rapidResetWindowClosed(30000, true), "window closes once");
  }
  if (g_failures) {
    printf("rapid-reset smoke: %d failures\n", g_failures);
    return 1;
  }
  printf("rapid-reset smoke: PASS\n");
  return 0;
}
