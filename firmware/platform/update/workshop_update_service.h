#pragma once

#include "workshop_platform/workshop_state.hpp"

#include <Arduino.h>
#include <cstdint>

struct WorkshopUpdateRuntimeSnapshot {
    workshop::platform::UpdateChannel channel{workshop::platform::UpdateChannel::Stable};
    workshop::platform::UpdatePhase phase{workshop::platform::UpdatePhase::Idle};
    workshop::platform::Freshness manifestFreshness{workshop::platform::Freshness::Unknown};
    std::uint8_t progressPercent{0};
    bool busy{false};
    bool updateAvailable{false};
    bool artifactIdentityVerified{false};
    char runningVersion[workshop::platform::kVersionLabelLength]{};
    char availableVersion[workshop::platform::kVersionLabelLength]{};
    char availableLabel[80]{};
    char statusMessage[112]{};
    char sourceCommit[41]{};
    char artifactSha256[65]{};
    std::uint32_t artifactSize{0};
};

// Device-native update service for a WS350 already running the compatible
// Workshop OS partition layout. Stable is always the default channel.
void workshopUpdateServiceBegin();
void workshopUpdateServiceLoop();

bool workshopUpdateSetChannel(workshop::platform::UpdateChannel channel);
bool workshopUpdateRequestCheck();
bool workshopUpdateRequestInstall();
WorkshopUpdateRuntimeSnapshot workshopUpdateSnapshot();

const char* workshopUpdateChannelName(workshop::platform::UpdateChannel channel);
const char* workshopUpdatePhaseName(workshop::platform::UpdatePhase phase);
