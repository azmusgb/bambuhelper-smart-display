#pragma once

#include "workshop_platform/workshop_state.hpp"

void workshopPlatformBegin();
void workshopPlatformPoll();
const workshop::platform::WorkshopState& workshopPlatformState();
