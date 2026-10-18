#pragma once

// Triple-reset entry to Recovery Safe Mode.
//
// The count lives in NVS (bh_recovery/rapid), not in RTC memory: RTC_DATA_ATTR
// variables are re-initialised on every reset other than a deep-sleep wake,
// so the old in-RTC counter never got past 1 and Safe Mode was unreachable.
// NVS survives every kind of reset (EN button, USB reset, power cycle).
//
// A boot counts as "rapid" until it has been up for kRapidWindowMs; then the
// stored count is cleared. The third rapid boot in a row enters Safe Mode and
// starts the count again. Plain C++11 so it is tested on the host.

#include <stdint.h>

namespace workshop {
namespace recovery {

static const uint8_t kRapidResetLimit = 3;
static const uint32_t kRapidWindowMs = 15000;

// Called once per boot with the stored count. Returns the count to store and
// sets safeMode when this boot completes a triple reset.
inline uint8_t rapidResetOnBoot(uint8_t stored, bool& safeMode) {
  const uint8_t count = static_cast<uint8_t>(stored >= kRapidResetLimit ? kRapidResetLimit : stored + 1);
  safeMode = count >= kRapidResetLimit;
  return safeMode ? 0 : count;
}

// True once per boot, when the stored count should be cleared.
inline bool rapidResetWindowClosed(uint32_t uptimeMs, bool alreadyCleared) {
  return !alreadyCleared && uptimeMs >= kRapidWindowMs;
}

}  // namespace recovery
}  // namespace workshop
