// Host test for firmware/platform/ui/press_gesture.hpp (12.3.8).
//
// Checks that a press fires only on the target it went down on and on the
// same screen, that the outline is shown only while the finger is on that
// target, that a press with no target keeps the old dispatch, and that an
// approval prompt ignores a finger that was already down, a press in its first
// 500 ms, and a press that slid onto or off its button. It also scans every
// down/up pair over a 480x320 grid with two buttons, and checks the outline
// and the release always agree.
//
//   g++ -std=c++11 -Wall -Wextra -Werror -pedantic tests/workshop_os12_press_gesture_smoke.cpp -o /tmp/press-gesture-smoke

#include "../firmware/platform/ui/press_gesture.hpp"

#include <stdio.h>

using namespace workshop::ui::press;

namespace {

int g_failures = 0;
long g_checks = 0;

void check(bool ok, const char* what, long a = 0, long b = 0) {
  ++g_checks;
  if (ok) return;
  ++g_failures;
  if (g_failures <= 40) printf("FAIL %s (%ld, %ld)\n", what, a, b);
}

const std::uint8_t kHome = 1;
const std::uint8_t kMore = 4;

void boxes() {
  check(noBox().empty(), "empty box");
  check(!noBox().contains(0, 0), "empty box contains nothing");
  const Box a = makeBox(10, 20, 100, 44);
  check(a.contains(10, 20) && a.contains(109, 63), "box corners inside");
  check(!a.contains(110, 20) && !a.contains(10, 64), "box edges outside");
  check(sameBox(noBox(), makeBox(5, 5, 0, 10)), "two empty boxes are the same target");
  check(!sameBox(a, noBox()) && !sameBox(noBox(), a), "a target is not no target");
  check(sameBox(a, makeBox(10, 20, 100, 44)), "same rectangle");
  check(!sameBox(a, makeBox(10, 20, 100, 45)), "different rectangle");
}

void tracker() {
  const Box button = makeBox(100, 100, 120, 44);
  const Box other = makeBox(100, 160, 120, 44);
  Tracker t;
  check(!t.active(), "starts idle");
  check(t.releaseFires(kHome, noBox()), "no press, release over nothing: old dispatch");
  check(!t.releaseFires(kHome, button), "no recorded press never fires a target");

  t.down(150, 120, 1000, kHome, button);
  check(t.active() && t.downX() == 150 && t.downY() == 120 && t.downMs() == 1000, "press recorded");
  check(t.outlineVisible(kHome, 150, 120), "outline on the pressed target");
  check(t.outlineVisible(kHome, 219, 143), "outline anywhere on the pressed target");
  check(!t.outlineVisible(kHome, 150, 170), "no outline once the finger is on another control");
  check(!t.outlineVisible(kMore, 150, 120), "no outline on another screen");
  check(t.releaseFires(kHome, button), "release on the pressed target fires");
  check(!t.releaseFires(kHome, other), "release on another target is cancelled");
  check(!t.releaseFires(kHome, noBox()), "release on empty space is cancelled");
  check(!t.releaseFires(kMore, button), "release after the screen changed is cancelled");
  t.cancel();
  check(!t.active() && !t.outlineVisible(kHome, 150, 120), "cancel ends the press and its outline");

  // A press with no target (empty space, calm screen, the Stop hold).
  t.down(5, 5, 2000, kHome, noBox());
  check(!t.outlineVisible(kHome, 5, 5), "no target, no outline");
  check(t.releaseFires(kHome, noBox()), "no target to no target keeps the old dispatch (wake, Stop)");
  check(!t.releaseFires(kHome, button), "sliding from empty space onto a control does not fire it");
}

void promptArm() {
  const Box allow = makeBox(250, 200, 200, 52);
  const Box cancel = makeBox(30, 200, 200, 52);
  PromptArm arm;
  Tracker t;
  t.down(300, 220, 5000, kHome, noBox());
  check(!arm.tapAccepted(t, allow, 300, 220), "no prompt drawn, nothing accepted");

  // A finger already down when the prompt appears answers nothing.
  arm.shown(5100);
  check(arm.visible(), "prompt visible");
  check(!arm.tapAccepted(t, allow, 300, 220), "press that started before the prompt");
  arm.shown(9000);  // redraws do not move the arming time
  t.down(300, 220, 5100, kHome, noBox());
  check(!arm.tapAccepted(t, allow, 300, 220), "press at the moment the prompt appeared");
  t.down(300, 220, 5100 + kPromptArmMs - 1, kHome, noBox());
  check(!arm.tapAccepted(t, allow, 300, 220), "press inside the 500 ms guard");
  t.down(300, 220, 5100 + kPromptArmMs, kHome, noBox());
  check(arm.tapAccepted(t, allow, 300, 220), "press after the guard on Allow, released on Allow");
  check(!arm.tapAccepted(t, cancel, 300, 220), "Allow press does not answer Cancel");
  check(!arm.tapAccepted(t, allow, 100, 220), "slid off Allow onto Cancel: nothing");
  t.down(100, 220, 6000, kHome, noBox());
  check(!arm.tapAccepted(t, allow, 300, 220), "slid from Cancel onto Allow: no Allow");
  check(!arm.tapAccepted(t, cancel, 300, 220), "slid from Cancel onto Allow: no Cancel either");
  check(arm.tapAccepted(t, cancel, 110, 230), "Cancel press released on Cancel");
  t.cancel();
  check(!arm.tapAccepted(t, cancel, 110, 230), "an ended press answers nothing");

  // Hidden and shown again: the next prompt arms afresh.
  arm.hidden();
  check(!arm.visible(), "prompt hidden");
  arm.shown(20000);
  t.down(300, 220, 20000 + 100, kHome, noBox());
  check(!arm.tapAccepted(t, allow, 300, 220), "second prompt has its own guard");
  t.down(300, 220, 20000 + 600, kHome, noBox());
  check(arm.tapAccepted(t, allow, 300, 220), "second prompt armed after 500 ms");

  // millis() wraps.
  PromptArm wrap;
  wrap.shown(0xFFFFFF00u);
  t.down(300, 220, 0x00000010u, kHome, noBox());
  check(!wrap.tapAccepted(t, allow, 300, 220), "guard across the millis() wrap");
  t.down(300, 220, 0xFFFFFF00u + kPromptArmMs, kHome, noBox());
  check(wrap.tapAccepted(t, allow, 300, 220), "armed across the millis() wrap");
}

// Two buttons on a 480x320 screen. For every pair of points, the outline at
// the release point (finger still down there) is shown exactly when the
// release would fire a target, and a release never fires a target other than
// the one pressed.
Box targetAt(int x, int y) {
  static const Box a = makeBox(16, 60, 220, 44);
  static const Box b = makeBox(244, 60, 220, 44);
  if (a.contains(x, y)) return a;
  if (b.contains(x, y)) return b;
  return noBox();
}

void scan() {
  for (int dy = 0; dy < 320; dy += 8) {
    for (int dx = 0; dx < 480; dx += 8) {
      Tracker t;
      const Box down = targetAt(dx, dy);
      t.down(static_cast<std::int16_t>(dx), static_cast<std::int16_t>(dy), 100, kMore, down);
      for (int uy = 0; uy < 320; uy += 16) {
        for (int ux = 0; ux < 480; ux += 16) {
          const Box up = targetAt(ux, uy);
          const bool fires = t.releaseFires(kMore, up);
          const bool outline = t.outlineVisible(kMore, ux, uy);
          if (!up.empty()) {
            check(fires == outline, "outline shows exactly what a release fires", dx * 1000 + dy, ux * 1000 + uy);
            check(!fires || sameBox(up, down), "a release fires only the pressed target", dx, ux);
          } else {
            check(!outline, "no outline over empty space", dx, ux);
          }
        }
      }
    }
  }
}

}  // namespace

int main() {
  boxes();
  tracker();
  promptArm();
  scan();
  if (g_failures) {
    printf("press-gesture smoke: %d of %ld checks failed\n", g_failures, g_checks);
    return 1;
  }
  printf("press-gesture smoke: PASS (%ld checks)\n", g_checks);
  return 0;
}
