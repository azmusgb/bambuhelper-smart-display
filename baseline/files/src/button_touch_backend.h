#ifndef BUTTON_TOUCH_BACKEND_H
#define BUTTON_TOUCH_BACKEND_H

#include <Arduino.h>

// Touch-driver backend interface. Exactly one .cpp compiles a body, selected by
// whole-file guards (mirrors buzzer_backend_*.cpp): button_touch_<driver>.cpp for
// each explicit USE_* driver, and button_touch_none.cpp when none is selected
// (which itself provides the LovyanGFX TOUCH_CS fallback or a true no-op). All
// files are compiled; the guards make only one define the symbols.
//
// At most one EXPLICIT driver may be selected. Zero is valid (no-touch boards -
// esp32s3, esp32c3, the round/DIY envs). More than one is a build error.
#if (defined(USE_XPT2046) + defined(USE_CST816) + defined(USE_CST328) \
     + defined(USE_FT5X06) + defined(USE_FT6336) + defined(USE_AXS_TOUCH)) > 1
#error "button_touch: more than one explicit touch driver (USE_*) selected"
#endif

// Default AXS touch INT GPIO. Defined here (not just in the backend .cpp) because
// sanitizeButtonPin() in button.cpp also needs it to reject a conflicting pin.
#if defined(USE_AXS_TOUCH) && !defined(AXS_TOUCH_INT)
#define AXS_TOUCH_INT 3
#endif

enum class TouchEvent : uint8_t {
  None,         // no edge this tick; `isDown` carries the current level
  Pressed,      // edge-managed backends only: press edge
  Released,     // edge-managed backends only: release edge
  Unavailable,  // bus/read failure - caller must leave debounce/hold state untouched
};

struct TouchPoll {
  TouchEvent ev;
  bool isDown;  // meaningful for level backends (ev == None); raw finger-down
  uint16_t x;
  uint16_t y;
  bool hasPosition;

  TouchPoll(TouchEvent e = TouchEvent::None, bool down = false,
            uint16_t px = 0, uint16_t py = 0, bool positioned = false)
      : ev(e), isDown(down), x(px), y(py), hasPosition(positioned) {}
};

// Bring up the touch bus/pins + first probe (all logging inside). Called from
// initButton() only when the configured button type is a touchscreen.
void touchInit();

// Poll the touch controller once. Level backends return {None, level} or
// {Unavailable,false}; the edge-managed backend returns {Pressed|Released|None,...}.
TouchPoll touchPoll();

#if defined(USE_FT6336)
// WS350/FT6336 health counters. These distinguish a configured touchscreen
// from a controller that is actually answering runtime polls.
uint32_t touchReadFailureCount();
uint32_t touchRecoveryCount();
uint32_t touchLastGoodPollMs();
#endif

#endif  // BUTTON_TOUCH_BACKEND_H
