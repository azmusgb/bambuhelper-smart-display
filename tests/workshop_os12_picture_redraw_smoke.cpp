// Host test for firmware/platform/ui/picture_redraw.hpp (the camera page's Video row after the first frame).
//
//   g++ -std=c++11 -Wall -Wextra -Werror -pedantic tests/workshop_os12_picture_redraw_smoke.cpp -o picture-redraw-smoke
#include "../firmware/platform/ui/picture_redraw.hpp"

#include <stdio.h>

namespace {
int g_failures = 0;
void check(bool ok, const char* what) {
  if (ok) return;
  ++g_failures;
  printf("FAIL %s\n", what);
}

// The loop of the device: draw (when asked), the media backend draws a frame, then the service looks. `frameAfterDraw`
// is the case from the device: the first frame lands between the page's first draw and the service's first look.
struct Sim {
  bool framesDrawn = false;
  bool rowDrewWaiting = false;  // what the screen shows
  bool dirty = false;
  wkit::PictureRedraw redraw;
  bool oldWasWaiting = false;  // the previous service's memory (kept to show the old rule misses the change)
  bool oldDirty = false;

  void draw() { rowDrewWaiting = !framesDrawn; redraw.drew(rowDrewWaiting); dirty = false; oldDirty = false; }
  void service() {
    const bool waiting = !framesDrawn;
    if (redraw.stale(waiting)) dirty = true;
    if (waiting != oldWasWaiting) { oldWasWaiting = waiting; oldDirty = true; }  // the rule this replaces
  }
};
}  // namespace

int main() {
  {  // a frame lands after the first draw, before the service's first look
    Sim s;
    s.draw();
    check(s.rowDrewWaiting, "first draw says waiting");
    s.framesDrawn = true;
    s.service();
    check(s.dirty, "the row is redrawn when the first frame arrives before the service first looked");
    check(!s.oldDirty, "(the old rule saw no change here: the stuck row on the device)");
    s.draw();
    check(!s.rowDrewWaiting, "and then says playing");
    s.service();
    check(!s.dirty, "no redraw once it matches");
  }
  {  // a frame lands after the service had already seen waiting
    Sim s;
    s.draw();
    s.service();
    check(!s.dirty, "waiting and still waiting: no redraw");
    s.framesDrawn = true;
    s.service();
    check(s.dirty, "frame arrives: redraw");
  }
  {  // the session restarts (counter back to zero) while the page is open
    Sim s;
    s.framesDrawn = true;
    s.draw();
    s.framesDrawn = false;
    s.service();
    check(s.dirty, "a restart is shown as waiting again");
  }
  {  // before the first draw nothing is stale; after leaving the page nothing is stale
    wkit::PictureRedraw r;
    check(!r.stale(true) && !r.stale(false), "nothing to redraw before a draw");
    r.drew(true);
    r.left();
    check(!r.stale(false), "nothing to redraw after the page is left");
  }
  if (g_failures) { printf("%d check(s) failed\n", g_failures); return 1; }
  printf("PASS: camera row is redrawn when the first frame arrives, whatever order the draw and the service run in\n");
  return 0;
}
