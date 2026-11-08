#pragma once
#include <Arduino.h>
void recoveryBootProbe();
void recoveryTick();
void recoveryMarkWebReady();
bool recoveryWebReady();
void recoveryArmCandidateBoot();
bool recoverySafeModeActive();
void recoveryRequestSafeModeNextBoot();
void recoveryClearSafeMode();
uint8_t recoveryRapidBootCount();
uint8_t recoveryCandidateAttempts();
bool recoveryCandidatePending();
String recoveryCurrentSlot();
String recoveryKnownGoodSlot();
String recoveryFallbackSlot();
bool recoveryRollbackNow(String& message);
