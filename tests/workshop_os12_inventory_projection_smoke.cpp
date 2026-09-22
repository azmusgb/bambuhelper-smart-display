#include "../firmware/platform/runtime_adapter.hpp"
#include "../firmware/platform/service_contracts.hpp"

#include <cassert>
#include <cstring>

using namespace workshop::platform;

int main() {
    InventoryFeedObservation unavailable;
    InventoryProjectionState missing = normalizeInventoryFeedObservation(unavailable);
    assert(!missing.available);
    assert(missing.freshness == Freshness::Unknown);
    assert(missing.quantityState == InventoryQuantityState::Unknown);
    assert(missing.readiness == InventoryReadinessState::Undetermined);
    assert(missing.quantityVerificationRequired);
    assert(missing.placementState == InventoryPlacementState::Unknown);
    assert(missing.placementVerificationRequired);
    assert(!inventoryQuantityUsable(missing));
    assert(!inventoryPlacementUsable(missing));
    assert(!inventoryReadinessClean(missing));

    InventoryFeedObservation clean;
    std::strncpy(clean.profileId, "profile-bill", sizeof(clean.profileId) - 1);
    clean.observedAtMs = 1000;
    clean.spoolCount = 8;
    clean.loadedCount = 2;
    clean.lowCount = 1;
    clean.readiness = InventoryReadinessState::Ready;
    clean.available = true;
    clean.feedStale = false;

    InventoryProjectionState current = normalizeInventoryFeedObservation(clean);
    assert(current.available);
    assert(current.freshness == Freshness::Fresh);
    assert(current.quantityState == InventoryQuantityState::Current);
    assert(current.readiness == InventoryReadinessState::Ready);
    assert(!current.quantityVerificationRequired);
    assert(current.placementState == InventoryPlacementState::Current);
    assert(!current.placementVerificationRequired);
    assert(current.spoolCount == 8);
    assert(current.loadedCount == 2);
    assert(current.lowCount == 1);
    assert(std::strcmp(current.profileId, "profile-bill") == 0);
    assert(inventoryQuantityUsable(current));
    assert(inventoryPlacementUsable(current));
    assert(inventoryReadinessClean(current));

    InventoryFeedObservation conflict = clean;
    conflict.conflictCount = 2;
    InventoryProjectionState conflicting = normalizeInventoryFeedObservation(conflict);
    assert(conflicting.freshness == Freshness::Conflicting);
    assert(conflicting.quantityState == InventoryQuantityState::Conflict);
    assert(conflicting.quantityVerificationRequired);
    assert(!inventoryQuantityUsable(conflicting));
    assert(!inventoryReadinessClean(conflicting));

    InventoryFeedObservation badLineage = clean;
    badLineage.invalidLineageCount = 1;
    InventoryProjectionState invalid = normalizeInventoryFeedObservation(badLineage);
    assert(invalid.quantityState == InventoryQuantityState::InvalidLineage);
    assert(invalid.quantityVerificationRequired);
    assert(!inventoryQuantityUsable(invalid));

    InventoryFeedObservation staleQuantity = clean;
    staleQuantity.staleQuantityCount = 1;
    InventoryProjectionState staleEvidence = normalizeInventoryFeedObservation(staleQuantity);
    assert(staleEvidence.quantityState == InventoryQuantityState::Stale);
    assert(staleEvidence.quantityVerificationRequired);
    assert(!inventoryQuantityUsable(staleEvidence));

    InventoryFeedObservation staleFeed = clean;
    staleFeed.feedStale = true;
    InventoryProjectionState staleSource = normalizeInventoryFeedObservation(staleFeed);
    assert(staleSource.freshness == Freshness::Stale);
    assert(staleSource.quantityState == InventoryQuantityState::Stale);
    assert(staleSource.quantityVerificationRequired);

    InventoryFeedObservation unknownQuantity = clean;
    unknownQuantity.unknownQuantityCount = 3;
    InventoryProjectionState unknown = normalizeInventoryFeedObservation(unknownQuantity);
    assert(unknown.quantityState == InventoryQuantityState::Unknown);
    assert(unknown.quantityVerificationRequired);

    // Quantity evidence can remain fully usable while print readiness is
    // Undetermined because no requirement has been supplied.
    InventoryFeedObservation placementConflict = clean;
    placementConflict.placementConflictCount = 1;
    InventoryProjectionState badPlacement = normalizeInventoryFeedObservation(placementConflict);
    assert(badPlacement.placementState == InventoryPlacementState::Conflict);
    assert(badPlacement.placementVerificationRequired);
    assert(!inventoryPlacementUsable(badPlacement));
    assert(inventoryQuantityUsable(badPlacement));

    InventoryFeedObservation placementStale = clean;
    placementStale.stalePlacementCount = 1;
    InventoryProjectionState stalePlacement = normalizeInventoryFeedObservation(placementStale);
    assert(stalePlacement.placementState == InventoryPlacementState::Stale);
    assert(stalePlacement.placementVerificationRequired);
    assert(!inventoryPlacementUsable(stalePlacement));

    InventoryFeedObservation placementUnknown = clean;
    placementUnknown.unknownPlacementCount = 2;
    InventoryProjectionState unknownPlacement = normalizeInventoryFeedObservation(placementUnknown);
    assert(unknownPlacement.placementState == InventoryPlacementState::Unknown);
    assert(unknownPlacement.placementVerificationRequired);
    assert(!inventoryPlacementUsable(unknownPlacement));

    InventoryFeedObservation undetermined = clean;
    undetermined.readiness = InventoryReadinessState::Undetermined;
    InventoryProjectionState noRequirement = normalizeInventoryFeedObservation(undetermined);
    assert(noRequirement.quantityState == InventoryQuantityState::Current);
    assert(!noRequirement.quantityVerificationRequired);
    assert(inventoryQuantityUsable(noRequirement));
    assert(!inventoryReadinessClean(noRequirement));

    InventoryFeedObservation needsLoad = clean;
    needsLoad.readiness = InventoryReadinessState::NeedsLoad;
    InventoryProjectionState loadRequired = normalizeInventoryFeedObservation(needsLoad);
    assert(loadRequired.quantityState == InventoryQuantityState::Current);
    assert(!loadRequired.quantityVerificationRequired);
    assert(inventoryQuantityUsable(loadRequired));
    assert(!inventoryReadinessClean(loadRequired));

    StateStore store;
    store.publishInventoryProjectionState(conflicting);
    assert(store.snapshot().capabilities.inventory);
    assert(store.snapshot().inventory.conflictCount == 2);
    assert(store.snapshot().inventory.quantityState == InventoryQuantityState::Conflict);

    return 0;
}
