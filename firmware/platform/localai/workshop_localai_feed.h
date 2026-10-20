#pragma once

// Workshop OS 12.3.10: Local AI cards for the calm idle screen (rules: workshop_localai_feed_core.hpp).

#include "workshop_localai_feed_core.hpp"

#include <cstddef>
#include <cstdint>

struct WorkshopLocalAiFeedSnapshot {
    workshop::localai::Card cards[workshop::localai::kMaxCards]{};
    std::uint8_t count{0};
    bool configured{false};
    bool busy{false};
    std::uint32_t lastSuccessAtMs{0};
    std::uint32_t lastAttemptAtMs{0};
    std::uint8_t failures{0};
    char status[96]{};
};

void workshopLocalAiFeedBegin();
void workshopLocalAiFeedLoop();
// address: Local AI's IPv4 address; tlsName: the name on its certificate; key: the wsd_ display key; caPem: Local
// AI's CA certificate (PEM). False when any is not acceptable; nothing is saved then.
bool workshopLocalAiFeedConfigure(const char* address, const char* tlsName, const char* key, const char* caPem);
void workshopLocalAiFeedClear();
WorkshopLocalAiFeedSnapshot workshopLocalAiFeedSnapshot();
// Free entries in the default NVS partition (32 bytes each), for the portal's status.
std::size_t workshopLocalAiFeedNvsFreeEntries();
