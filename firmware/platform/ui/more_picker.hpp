// The More pages' Picker (display-kit K9, rollout step 5): a setting that is a named choice, a colour or a clock time
// is chosen from a full screen of rows, not stepped with - and +. This is the session around the kit's ui::Picker: it
// opens with the current choice in view, applies a tap through the caller's setter, reads the setting back, and only
// then closes; when the setting is not kept the Picker stays open and the row says so (a failed save never closes it,
// and the previous choice keeps its check mark). Back changes nothing. It knows nothing about the settings: the firmware
// builds the options and supplies apply and read, and tests/workshop_os12_more_picker_smoke.cpp drives the same session
// on a host. Header-only C++17, no graphics library. Installed as include/workshop_kit/more_picker.hpp.
#pragma once

#include "kit_screen.hpp"

namespace wkit {

class PickerSession {
 public:
  enum class Outcome : uint8_t {
    None,     // nothing changed on screen
    Redraw,   // draw it again (a page turn, a failure shown or cleared)
    Closed,   // the Picker closed (a choice kept, or Back): show the page it came from
  };
  // Apply the choice: null when it was kept, else why it was not ("The device did not keep it").
  using Apply = const char* (*)(int index);
  // The index of the choice now in effect, -1 when it cannot be read.
  using Read = int (*)();

  static constexpr const char* kNotKept = "The device did not keep it";

  // `options` stays alive while the Picker is open. `current` is -1 when the setting cannot be read: nothing is checked
  // and the Picker's title line says "Current setting unknown". False (and nothing opens) for an empty list.
  // `tabBar`: the height of the tab bar under the screen (the device's is 54 px; the kit's own is 48).
  bool open(const char* title, const ::ui::PickerOption* options, int count, int current, int tabBar = ::ui::kTabBarH) {
    if (!options || count < 1) return false;
    picker_ = ::ui::Picker(title, options, count, current, tabBar);
    open_ = true;
    return true;
  }
  bool isOpen() const { return open_; }
  void close() { open_ = false; }
  const ::ui::Picker& picker() const { return picker_; }
  ::ui::Picker& picker() { return picker_; }

  void draw(UiCanvas& c) {
    if (open_) picker_.draw(c);
  }

  Outcome tap(UiCanvas& c, int x, int y, Apply apply, Read read) {
    if (!open_) return Outcome::None;
    const bool hadFailure = picker_.hasFailure();
    const ::ui::PickerResult r = picker_.tap(c, x, y);
    switch (r.event) {
      case ::ui::PickerEvent::Back: open_ = false; return Outcome::Closed;
      case ::ui::PickerEvent::Scrolled: return Outcome::Redraw;
      case ::ui::PickerEvent::Chose: {
        const char* why = apply ? apply(r.index) : kNotKept;
        if (!why && read && read() != r.index) why = kNotKept;  // saved, but not what was asked: say so
        if (why) {
          picker_.failed(r.index, why);
          return Outcome::Redraw;
        }
        open_ = false;
        return Outcome::Closed;
      }
      case ::ui::PickerEvent::None:
      default: return hadFailure != picker_.hasFailure() ? Outcome::Redraw : Outcome::None;
    }
  }

 private:
  ::ui::Picker picker_{"", nullptr, 0, -1, ::ui::kTabBarH};
  bool open_ = false;
};

}  // namespace wkit
