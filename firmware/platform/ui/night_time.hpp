// Night-mode times (display-kit K9: a Picker of times in 15-minute steps). The schedule used to keep whole hours
// (nightStartHour, nightEndHour, NVS dp_nstart / dp_nend); it keeps minutes after midnight, multiples of 15, in
// nightStartMin / nightEndMin (NVS dp_nstartm / dp_nendm). This header is everything about those numbers that does not
// need the device: the migration from the stored hour, the night test (crossing midnight), the 96 options, the label,
// and reading the portal's form and settings export. tests/workshop_os12_night_time_smoke.cpp drives it on a host.
// Header-only, C++11, no Arduino. Installed as include/workshop_night_time.hpp.
#pragma once

#include <stddef.h>
#include <stdint.h>
#include <stdio.h>

namespace wnight {

constexpr unsigned kStepMinutes = 15;
constexpr unsigned kMinutesPerDay = 24U * 60U;
constexpr int kOptionCount = (int)(kMinutesPerDay / kStepMinutes);  // 96
constexpr uint16_t kDefaultStart = 22U * 60U;                       // 22:00, what the whole-hour setting defaulted to
constexpr uint16_t kDefaultEnd = 7U * 60U;                          // 07:00

// A time the schedule can hold: inside the day, on a 15-minute step.
inline bool valid(long minutes) { return minutes >= 0 && minutes < (long)kMinutesPerDay && minutes % (long)kStepMinutes == 0; }

inline bool validHour(long hour) { return hour >= 0 && hour < 24; }

// The stored value to use at boot. `hasMinutes`: the minutes key exists in NVS. `legacyHour`: the old whole-hour key,
// 255 when it was never saved. The minutes win, since each save writes both (the hour is the one the minutes fall in);
// when the hour no longer agrees the schedule was changed by older firmware after a downgrade, and that hour wins. With
// no minutes an existing hour h becomes h * 60; with neither the default is used.
inline uint16_t resolveStored(bool hasMinutes, uint16_t minutes, uint8_t legacyHour, uint16_t fallback) {
  if (hasMinutes && valid(minutes)) return validHour(legacyHour) && legacyHour != minutes / 60U ? (uint16_t)(legacyHour * 60U) : minutes;
  if (validHour(legacyHour)) return (uint16_t)((unsigned)legacyHour * 60U);
  return fallback;
}

// Whether `minuteOfDay` is inside the schedule. Equal times mean the schedule is off. Start earlier than end is a
// same-day window (01:00 to 07:00); start later than end crosses midnight (22:15 to 07:00). The end minute is outside.
inline bool isNight(unsigned minuteOfDay, uint16_t start, uint16_t end) {
  if (start == end) return false;
  if (start < end) return minuteOfDay >= start && minuteOfDay < end;
  return minuteOfDay >= start || minuteOfDay < end;
}

// Picker option i <-> minutes. -1 when the value is not an option (a time a newer firmware kept, say).
inline int indexOf(uint16_t minutes) { return valid(minutes) ? (int)(minutes / kStepMinutes) : -1; }
inline int minutesOf(int index) { return index >= 0 && index < kOptionCount ? index * (int)kStepMinutes : -1; }

// One step later or earlier, wrapping around midnight. A value that is not a valid time starts from the default start.
inline uint16_t step(uint16_t minutes, bool reverse) {
  const unsigned from = valid(minutes) ? minutes : kDefaultStart;
  return (uint16_t)(reverse ? (from + kMinutesPerDay - kStepMinutes) % kMinutesPerDay : (from + kStepMinutes) % kMinutesPerDay);
}

// "22:15" on a 24-hour clock, "10:15 PM" on a 12-hour one. `len` of at least 9 holds either.
inline void format(char* out, size_t len, uint16_t minutes, bool use24h) {
  if (!out || len == 0) return;
  const unsigned m = (unsigned)minutes % kMinutesPerDay;
  const unsigned h = m / 60U, mm = m % 60U;
  if (use24h) { snprintf(out, len, "%02u:%02u", h, mm); return; }
  const unsigned h12 = h % 12U ? h % 12U : 12U;
  snprintf(out, len, "%u:%02u %s", h12, mm, h < 12U ? "AM" : "PM");
}

// A whole decimal number, nothing else around it (the portal's text arrives as strings; toInt() would read "7abc" as 7).
inline bool parseLong(const char* s, long& out) {
  if (!s || !*s) return false;
  bool neg = false;
  if (*s == '-') { neg = true; ++s; }
  if (!*s) return false;
  long v = 0;
  for (; *s; ++s) {
    if (*s < '0' || *s > '9') return false;
    v = v * 10 + (*s - '0');
    if (v > 100000L) return false;
  }
  out = neg ? -v : v;
  return true;
}

// One time from the portal, either as a form argument or a settings-export field. The minutes field wins; the old
// whole-hour field (a portal page or an export from before this change) is read as h * 60. A field that is absent
// leaves `inOut`; so does one that is not a valid time. Returns true when `inOut` was set.
inline bool importTime(bool hasMinutes, long minutes, bool hasHour, long hour, uint16_t& inOut) {
  if (hasMinutes) {
    if (!valid(minutes)) return false;
    inOut = (uint16_t)minutes;
    return true;
  }
  if (hasHour) {
    if (!validHour(hour)) return false;
    inOut = (uint16_t)(hour * 60);
    return true;
  }
  return false;
}

// The same for form arguments given as text (null: the argument is absent).
inline bool importTimeText(const char* minutesArg, const char* hourArg, uint16_t& inOut) {
  long m = 0, h = 0;
  const bool hasM = minutesArg != nullptr;
  const bool hasH = hourArg != nullptr;
  if (hasM && !parseLong(minutesArg, m)) m = -1;  // present but not a number: not valid, and the hour must not stand in
  if (hasH && !parseLong(hourArg, h)) h = -1;
  return importTime(hasM, m, hasH, h, inOut);
}

}  // namespace wnight
