// When the X2D camera page's Video row must be drawn again because a picture arrived (or went away). The row says
// "Waiting for picture" until the backend has drawn a frame, so it has to be redrawn when that changes. The change is
// against what the row LAST SHOWED, not against what the service last saw: a first frame that arrives between the page's
// first draw and the service's first look made both reads "not waiting", saw no change, and left the row on "Waiting for
// picture" beside a live picture. Header-only, no graphics library, host-tested by
// tests/workshop_os12_picture_redraw_smoke.cpp. Installed as include/workshop_kit/picture_redraw.hpp.
#pragma once

namespace wkit {

class PictureRedraw {
 public:
  // The row was drawn saying `waiting` (true: "Waiting for picture").
  void drew(bool waiting) { shown_ = waiting; known_ = true; }
  // The page left the screen: the next draw is a fresh one.
  void left() { known_ = false; }
  // True when the row on screen no longer matches `waiting`. Never before the row has been drawn: the first draw is
  // already in the page's own dirty flag.
  bool stale(bool waiting) const { return known_ && waiting != shown_; }

 private:
  bool shown_ = false;
  bool known_ = false;
};

}  // namespace wkit
