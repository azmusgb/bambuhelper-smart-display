#ifndef SMART_HUB_H
#define SMART_HUB_H

#include <Arduino.h>
#include "display_ui.h"

struct SmartHubConfig {
  bool enabled;
  uint16_t refreshSeconds;
  uint16_t returnSeconds;
  char customUrl[192];
};

void smartHubInit();
void smartHubService();

bool smartHubAvailable();
bool smartHubEnabled();
bool smartHubIsScreen(ScreenState screen);
bool smartHubShouldYieldToPrinter(bool printing);

void smartHubEnter();
// Enter HOME as an idle/screensaver destination. Unlike a user navigation tap,
// this does not start the return-to-printer hold window, so a new print can
// immediately preempt HOME and restore the Printer dashboard.
void smartHubEnterIdleHome();
void smartHubAdvance();
void smartHubReturnToPrinter();
bool smartHubShowPage(const char* pageName);

void smartHubDraw(ScreenState screen, bool forceRedraw);

const SmartHubConfig& smartHubGetConfig();
bool smartHubSaveConfig(bool enabled, const char* customUrl,
                        uint16_t refreshSeconds, uint16_t returnSeconds);

const char* smartHubCustomStatus();
bool smartHubCustomHealthy();

// v9.7 coordinate-driven interaction. rawX/rawY are native FT6336 portrait
// coordinates; Smart Home maps them through the current display rotation.
bool smartHubHandleTouch(uint16_t rawX, uint16_t rawY, bool longPress);
// Live guarded-action feedback. holdMs comes from buttonHoldDurationMs() and
// uses the same 650 ms threshold as smartHubHandleTouch long-press dispatch.
void smartHubUpdateHoldProgress(uint16_t rawX, uint16_t rawY, uint32_t holdMs);
bool smartHubIsNativePrinterScreen(ScreenState screen);

#endif // SMART_HUB_H

// BambuHelper smart home navigation evolution v7
