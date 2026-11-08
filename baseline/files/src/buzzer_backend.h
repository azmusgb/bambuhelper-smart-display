#ifndef BUZZER_BACKEND_H
#define BUZZER_BACKEND_H

#include <Arduino.h>

void buzzerBackendInit();
void buzzerBackendApplyStep(uint16_t freq);
void buzzerBackendStop();
void buzzerBackendTick();
void buzzerBackendShutdown();

#if defined(BOARD_HAS_MICROPHONE)
int buzzerBackendMicLevel(uint16_t sampleMs);
int buzzerBackendMicEcho(uint16_t recordMs);
#endif

#endif // BUZZER_BACKEND_H
