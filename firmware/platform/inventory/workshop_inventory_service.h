#pragma once

#include "workshop_platform/service_contracts.hpp"

#include <cstdint>

struct WorkshopInventoryRuntimeSnapshot {
    workshop::platform::InventoryProjectionState state{};
    char statusMessage[112]{};
    bool credentialConfigured{false};
    bool busy{false};
    std::uint32_t lastAttemptAtMs{0};
    std::uint32_t lastSuccessAtMs{0};
};

void workshopInventoryServiceBegin();
void workshopInventoryServiceLoop();
bool workshopInventoryRequestRefresh();
bool workshopInventorySetDeviceCredential(const char* token);
void workshopInventoryClearDeviceCredential();
bool workshopInventoryCredentialConfigured();
WorkshopInventoryRuntimeSnapshot workshopInventorySnapshot();
