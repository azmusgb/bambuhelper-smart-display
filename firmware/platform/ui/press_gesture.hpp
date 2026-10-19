#pragma once

// Workshop OS 12.3.8: one press on the WS350 hub touchscreen, from touch-down
// to release. Pure and host-tested (tests/workshop_os12_press_gesture_smoke.cpp).
//
// Up to 12.3.7 the hub dispatched a tap at the point where the finger was
// lifted, whatever it went down on, and the touch-down outline (12.3.6)
// stayed on the control the finger first touched. So the outline could show
// one control while another one ran, a press that slid off a button still
// fired whatever it was released over, and a finger already on the panel
// when a Local AI approval prompt appeared could answer it on release.
//
// The rules here:
// - Tracker: a press acts only on the target it went down on, on the screen it
//   went down on (a standard button). Lifting outside that target, or after
//   the screen changed, does nothing. The outline is shown only while the
//   finger is still on that target, so it always shows what a release would
//   do. A press with no target (empty space, the calm idle screen, the Stop
//   button, which tracks its own hold) keeps the old dispatch, so a release
//   over no target behaves as before and a release over a target does nothing.
// - PromptArm: an approval prompt's Allow and Cancel answer only a press that
//   went down on that button at least kPromptArmMs after the prompt was first
//   drawn, and was released on it.

#include <cstdint>

namespace workshop {
namespace ui {
namespace press {

struct Box {
    std::int16_t x;
    std::int16_t y;
    std::int16_t w;
    std::int16_t h;
    bool empty() const { return w <= 0 || h <= 0; }
    bool contains(int px, int py) const {
        return !empty() && px >= x && py >= y && px < x + w && py < y + h;
    }
};

inline Box makeBox(int x, int y, int w, int h) {
    Box b;
    b.x = static_cast<std::int16_t>(x);
    b.y = static_cast<std::int16_t>(y);
    b.w = static_cast<std::int16_t>(w);
    b.h = static_cast<std::int16_t>(h);
    return b;
}

inline Box noBox() { return makeBox(0, 0, 0, 0); }

// Two targets are the same when both are empty, or both are the same rectangle.
inline bool sameBox(const Box& a, const Box& b) {
    if (a.empty() || b.empty()) return a.empty() && b.empty();
    return a.x == b.x && a.y == b.y && a.w == b.w && a.h == b.h;
}

class Tracker {
public:
    void down(std::int16_t x, std::int16_t y, std::uint32_t nowMs, std::uint8_t screen, const Box& target) {
        active_ = true;
        x_ = x;
        y_ = y;
        downMs_ = nowMs;
        screen_ = screen;
        target_ = target;
    }

    void cancel() { active_ = false; }

    bool active() const { return active_; }
    std::int16_t downX() const { return x_; }
    std::int16_t downY() const { return y_; }
    std::uint32_t downMs() const { return downMs_; }
    std::uint8_t screen() const { return screen_; }
    const Box& target() const { return target_; }

    // The outline is drawn only while the finger is on the target it went
    // down on, on the same screen.
    bool outlineVisible(std::uint8_t screen, int x, int y) const {
        return active_ && screen == screen_ && target_.contains(x, y);
    }

    // Whether the action under the release point may run. `releaseTarget` is
    // the target under the release point (empty when there is none).
    bool releaseFires(std::uint8_t screen, const Box& releaseTarget) const {
        if (!active_) return releaseTarget.empty();
        if (screen != screen_) return false;
        return sameBox(target_, releaseTarget);
    }

private:
    bool active_{false};
    std::int16_t x_{0};
    std::int16_t y_{0};
    std::uint32_t downMs_{0};
    std::uint8_t screen_{0};
    Box target_{0, 0, 0, 0};
};

// Taps are ignored for this long after a prompt first appears.
constexpr std::uint32_t kPromptArmMs = 500;

class PromptArm {
public:
    // Call whenever the prompt is drawn; only the first call after it was
    // hidden starts the arming time.
    void shown(std::uint32_t nowMs) {
        if (visible_) return;
        visible_ = true;
        shownMs_ = nowMs;
    }

    void hidden() { visible_ = false; }

    bool visible() const { return visible_; }

    // True when the press went down on `button` no earlier than kPromptArmMs
    // after the prompt was first drawn, and was released on it.
    bool tapAccepted(const Tracker& press, const Box& button, int upX, int upY) const {
        if (!visible_ || !press.active()) return false;
        const std::int32_t sinceShown = static_cast<std::int32_t>(press.downMs() - shownMs_);
        if (sinceShown < static_cast<std::int32_t>(kPromptArmMs)) return false;
        return button.contains(press.downX(), press.downY()) && button.contains(upX, upY);
    }

private:
    bool visible_{false};
    std::uint32_t shownMs_{0};
};

}  // namespace press
}  // namespace ui
}  // namespace workshop
