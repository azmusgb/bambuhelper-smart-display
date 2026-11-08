#ifndef BUTTON_H
#define BUTTON_H

#include <Arduino.h>

void initButton();
bool wasButtonPressed();  // returns true once per press (edge-detected, debounced)
void sanitizeButtonPin();  // zero buttonPin if it conflicts with a reserved
                           // subsystem (backlight, touch bus, buzzer). No-op
                           // for touchscreen type.

// Hold-state polling. Pure getters - they reflect whatever the most recent
// wasButtonPressed() call observed and do NOT consume edge events. The main
// loop calls wasButtonPressed() once per iteration, so these stay fresh.
bool isButtonHeld();              // post-debounce stable pressed state
uint32_t buttonHoldDurationMs();  // 0 if not held, else millis() - press start

// Monotonic press-edge counter since boot. Primarily used by the Hardware
// commissioning page to prove that the configured input path really reaches
// BambuHelper. It counts whichever input type is configured; the health API
// also reports buttonType so the browser can distinguish touchscreen from GPIO.
uint32_t buttonPressCount();

// Last valid capacitive-touch position observed by wasButtonPressed().
// Coordinates are raw controller/native-portrait coordinates; callers that
// care about display rotation must map them to the active canvas.
bool buttonGetTouchPosition(uint16_t* x, uint16_t* y);

#if defined(USE_FT6336)
uint32_t buttonTouchReadFailures();
uint32_t buttonTouchRecoveryCount();
uint32_t buttonTouchLastGoodPollMs();
#endif

#endif // BUTTON_H
