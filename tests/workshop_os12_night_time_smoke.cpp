// Host test for firmware/platform/ui/night_time.hpp: night-mode times in 15-minute steps.
//
//   g++ -std=c++11 -Wall -Wextra -Werror -pedantic tests/workshop_os12_night_time_smoke.cpp -o night-time-smoke

#include "../firmware/platform/ui/night_time.hpp"

#include <stdio.h>
#include <string.h>

using namespace wnight;

namespace {

int g_failures = 0;

void check(bool ok, const char* what) {
  if (ok) return;
  ++g_failures;
  printf("FAIL %s\n", what);
}

unsigned at(unsigned h, unsigned m) { return h * 60U + m; }

bool text(uint16_t minutes, bool use24h, const char* want) {
  char buf[16];
  format(buf, sizeof(buf), minutes, use24h);
  if (!strcmp(buf, want)) return true;
  printf("  got '%s', want '%s'\n", buf, want);
  return false;
}

// What a portal page posts for option i, the way web_template writes it: the minutes as the option's value.
void optionValue(int i, char* out, size_t len) { snprintf(out, len, "%d", minutesOf(i)); }

}  // namespace

int main() {
  // The option list: 96 times, 15 minutes apart, each its own index back.
  check(kOptionCount == 96, "96 options");
  for (int i = 0; i < kOptionCount; ++i) {
    const int m = minutesOf(i);
    check(m == i * 15, "option minutes");
    check(valid(m), "option is valid");
    check(indexOf((uint16_t)m) == i, "option index round trip");
  }
  check(minutesOf(-1) == -1 && minutesOf(kOptionCount) == -1, "no option outside the list");
  check(indexOf(7) == -1 && indexOf(1440) == -1 && indexOf(1425 + 1) == -1, "off-step and out-of-day times are not options");
  check(valid(0) && valid(1425) && !valid(1440) && !valid(-15) && !valid(10), "valid times");

  // Migration: a stored whole hour h becomes h * 60 and nothing else; minutes already stored win; nothing stored gives the default.
  for (unsigned h = 0; h < 24; ++h) {
    check(resolveStored(false, 0, (uint8_t)h, kDefaultStart) == h * 60U, "stored hour h becomes h * 60");
    check(indexOf(resolveStored(false, 0, (uint8_t)h, kDefaultStart)) == (int)(h * 4U), "migrated hour is an option");
  }
  check(resolveStored(false, 0, 22, kDefaultStart) == 1320 && resolveStored(false, 0, 7, kDefaultEnd) == 420, "22 and 7 migrate to 1320 and 420");
  check(resolveStored(true, 1335, 22, kDefaultStart) == 1335, "stored minutes win over a leftover hour");
  check(resolveStored(true, 1335, 6, kDefaultStart) == 360, "a downgrade that changed the hour: the hour wins");
  check(resolveStored(true, 1320, 22, kDefaultStart) == 1320 && resolveStored(true, 1439 - 14, 255, kDefaultStart) == 1425,
        "hour and minutes agree, or no hour: minutes");
  check(resolveStored(true, 1337, 22, kDefaultStart) == 1320, "stored minutes that are not a step fall back to the hour");
  check(resolveStored(true, 1500, 255, kDefaultStart) == kDefaultStart, "stored minutes outside the day fall back to the default");
  check(resolveStored(false, 0, 255, kDefaultStart) == 1320, "never saved: 22:00");
  check(resolveStored(false, 0, 255, kDefaultEnd) == 420, "never saved: 07:00");
  check(resolveStored(false, 0, 24, kDefaultEnd) == kDefaultEnd, "an hour outside the day is ignored");

  // The test for night: same-day window.
  check(!isNight(at(0, 59), 60, 420) && isNight(at(1, 0), 60, 420) && isNight(at(6, 59), 60, 420) && !isNight(at(7, 0), 60, 420),
        "01:00 to 07:00: start in, end out");
  // Crossing midnight, 22:15 to 07:00.
  const uint16_t s = at(22, 15), e = at(7, 0);
  check(!isNight(at(22, 14), s, e), "22:14 is before 22:15");
  check(isNight(at(22, 15), s, e), "22:15 starts the night");
  check(isNight(at(23, 59), s, e), "23:59 is night");
  check(isNight(at(0, 0), s, e), "midnight is night");
  check(isNight(at(6, 59), s, e), "06:59 is night");
  check(!isNight(at(7, 0), s, e), "07:00 ends it");
  check(!isNight(at(12, 0), s, e), "noon is day");
  // A 15-minute window and equal times.
  check(isNight(at(5, 30), at(5, 30), at(5, 45)) && isNight(at(5, 44), at(5, 30), at(5, 45)) && !isNight(at(5, 45), at(5, 30), at(5, 45)),
        "a 15-minute window");
  for (unsigned m = 0; m < 1440; m += 15) check(!isNight(m, 600, 600), "equal times: off all day");
  // A window ending exactly at midnight and one starting there.
  check(isNight(at(23, 45), at(22, 0), 0) && !isNight(0, at(22, 0), 0) && isNight(at(22, 0), at(22, 0), 0), "22:00 to midnight");
  check(isNight(0, 0, at(6, 0)) && isNight(at(5, 59), 0, at(6, 0)) && !isNight(at(6, 0), 0, at(6, 0)) && !isNight(at(23, 59), 0, at(6, 0)),
        "midnight to 06:00");
  // The wrapped window and its opposite never overlap and cover the day.
  for (unsigned m = 0; m < 1440; ++m) check(isNight(m, s, e) != isNight(m, e, s), "a window and its complement");

  // One step, either way, wrapping at midnight.
  check(step(1320, false) == 1335 && step(1320, true) == 1305 && step(1425, false) == 0 && step(0, true) == 1425, "step wraps at midnight");
  check(step(1337, false) == 1335, "a bad time steps from the default start");
  {
    uint16_t t = 0;
    for (int i = 0; i < kOptionCount; ++i) t = step(t, false);
    check(t == 0, "96 steps make a day");
  }

  // Labels.
  check(text(0, true, "00:00") && text(1335, true, "22:15") && text(1425, true, "23:45") && text(450, true, "07:30"), "24-hour labels");
  check(text(0, false, "12:00 AM") && text(1335, false, "10:15 PM") && text(720, false, "12:00 PM") && text(60, false, "1:00 AM") &&
            text(1425, false, "11:45 PM"),
        "12-hour labels");
  {
    char tiny[4];
    format(tiny, sizeof(tiny), 1335, true);
    check(strlen(tiny) < sizeof(tiny), "a short buffer is cut, not overrun");
    format(nullptr, 0, 0, true);  // must not crash
  }

  // The portal round trip. A page built from the 96 options posts each option's value back and the device keeps it.
  for (int i = 0; i < kOptionCount; ++i) {
    char v[8];
    optionValue(i, v, sizeof(v));
    uint16_t kept = 1;
    check(importTimeText(v, nullptr, kept) && kept == minutesOf(i), "form: an option's value is kept");
  }
  {
    uint16_t t = 1320;
    check(!importTimeText(nullptr, nullptr, t) && t == 1320, "form: no field leaves the time");
    check(!importTimeText("1337", nullptr, t) && t == 1320, "form: a time off the step is refused");
    check(!importTimeText("1440", nullptr, t) && t == 1320, "form: 1440 is refused");
    check(!importTimeText("-15", nullptr, t) && t == 1320, "form: negative is refused");
    check(!importTimeText("7abc", nullptr, t) && t == 1320, "form: text after the number is refused");
    check(!importTimeText("", nullptr, t) && t == 1320, "form: empty is refused");
    check(!importTimeText("abc", "7", t) && t == 1320, "form: a bad minutes field is not replaced by the hour");
    check(importTimeText(nullptr, "7", t) && t == 420, "form: a page from before sends hour 7, kept as 07:00");
    check(importTimeText("1335", "7", t) && t == 1335, "form: minutes win when both come");
    check(!importTimeText(nullptr, "24", t) && t == 1335, "form: hour 24 is refused");
    check(!importTimeText(nullptr, "-1", t) && t == 1335, "form: hour -1 is refused");
  }
  // The settings export / restore: the export holds minutes; an export from before this change holds hours.
  {
    uint16_t t = 1320;
    check(importTime(true, 1335, false, 0, t) && t == 1335, "restore: minutes");
    check(importTime(false, 0, true, 6, t) && t == 360, "restore: an older export's hour 6 is 06:00");
    check(!importTime(true, 99999, true, 6, t) && t == 360, "restore: bad minutes are not replaced by the hour");
    check(!importTime(false, 0, false, 0, t) && t == 360, "restore: neither field leaves the time");
    // export then restore gives back every option
    for (int i = 0; i < kOptionCount; ++i) {
      uint16_t back = 0;
      check(importTime(true, minutesOf(i), false, 0, back) && indexOf(back) == i, "export then restore");
    }
  }

  if (g_failures) {
    printf("%d check(s) failed\n", g_failures);
    return 1;
  }
  printf("PASS: night-mode times - 96 options, hour migration, midnight crossing, labels, portal round trip\n");
  return 0;
}
