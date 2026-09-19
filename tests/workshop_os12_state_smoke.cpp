#include "../firmware/platform/runtime_adapter.hpp"
#include "../firmware/platform/service_contracts.hpp"

#include <cassert>
#include <cstring>
#include <limits>

using namespace workshop::platform;

namespace {

class FakePrinterService final : public IPrinterService {
public:
    void begin(IStateSink& sink) override {
        sink_ = &sink;
        for (std::size_t slot = 0; slot < kMaxPrinterSlots; ++slot) publish(slot);
    }

    void poll(std::uint32_t nowMs) override {
        for (std::size_t slot = 0; slot < kMaxPrinterSlots; ++slot) {
            states_[slot].observedAtMs = nowMs;
            publish(slot);
        }
    }

    PrinterState snapshot(std::size_t slot) const override {
        return validPrinterSlot(slot) ? states_[slot] : PrinterState{};
    }

    CommandResult dispatch(std::size_t slot, PrinterCommand command, bool guardSatisfied) override {
        if (!validPrinterSlot(slot)) return CommandResult::RejectedInvalidSlot;
        return validatePrinterCommand(states_[slot], command, guardSatisfied);
    }

    void setState(std::size_t slot, const PrinterState& state) {
        if (!validPrinterSlot(slot)) return;
        states_[slot] = state;
        publish(slot);
    }

private:
    void publish(std::size_t slot) {
        if (sink_ != nullptr && validPrinterSlot(slot)) sink_->publishPrinterState(slot, states_[slot]);
    }

    IStateSink* sink_{nullptr};
    PrinterState states_[kMaxPrinterSlots]{};
};

class FakeNetworkService final : public INetworkService {
public:
    void begin(IStateSink& sink) override { sink_ = &sink; publish(); }
    void poll(std::uint32_t nowMs) override { state_.observedAtMs = nowMs; publish(); }
    NetworkState snapshot() const override { return state_; }
    void requestReconnect() override { state_.wifi = Connectivity::Connecting; publish(); }
    void setState(const NetworkState& state) { state_ = state; publish(); }

private:
    void publish() { if (sink_ != nullptr) sink_->publishNetworkState(state_); }
    IStateSink* sink_{nullptr};
    NetworkState state_{};
};

}  // namespace

int main() {
    StateStore store;
    FakePrinterService printer;
    FakeNetworkService network;

    printer.begin(store);
    network.begin(store);
    assert(store.snapshot().revision == kMaxPrinterSlots + 1);
    assert(store.snapshot().configuredPrinterCount == 0);
    assert(!canDispatchPrinterCommand(store.snapshot(), 0));
    assert(!canDispatchPrinterCommand(store.snapshot(), kMaxPrinterSlots));
    assert(!canDispatchPowerCommand(store.snapshot(), 0));

    CommandOperationState pending = pendingCommandOperation();
    assert(pending.phase == OperationPhase::Pending);
    assert(!pending.retryable);
    CommandOperationState success = commandOperationFromResult(CommandResult::Accepted);
    assert(success.phase == OperationPhase::Success);
    assert(!success.retryable);
    CommandOperationState staleFeedback = commandOperationFromResult(CommandResult::RejectedStaleState);
    assert(staleFeedback.phase == OperationPhase::RecoverableError);
    assert(staleFeedback.retryable);
    CommandOperationState invalidStateFeedback = commandOperationFromResult(CommandResult::RejectedInvalidState);
    assert(invalidStateFeedback.phase == OperationPhase::RecoverableError);
    assert(!invalidStateFeedback.retryable);

    LegacyNetworkObservation networkObservation;
    networkObservation.connected = true;
    networkObservation.observedAtMs = 1000;
    networkObservation.rssiDbm = -55;
    networkObservation.localAddress = "192.0.2.10";
    networkObservation.localPortal = Connectivity::Online;
    NetworkState connectedNetwork = normalizeNetworkObservation(networkObservation);
    network.setState(connectedNetwork);
    assert(isConnected(store.snapshot().network.wifi));
    assert(store.snapshot().network.localPortal == Connectivity::Online);
    assert(store.snapshot().network.cloud == Connectivity::Unknown);
    assert(std::strcmp(store.snapshot().network.localAddress, "192.0.2.10") == 0);

    LegacyPrinterObservation firstObservation;
    firstObservation.configured = true;
    firstObservation.connected = true;
    firstObservation.activity = PrinterActivity::Idle;
    firstObservation.lastTelemetryAtMs = 1000;
    firstObservation.nozzleCelsius = 215;
    firstObservation.bedCelsius = 55;
    firstObservation.progressPercent = 101;
    PrinterState firstPrinter = normalizePrinterObservation(firstObservation, 1500, 1000);
    assert(firstPrinter.telemetryFreshness == Freshness::Fresh);
    assert(firstPrinter.progressPercent == 100);
    printer.setState(0, firstPrinter);
    assert(store.snapshot().configuredPrinterCount == 1);
    assert(canDispatchPrinterCommand(store.snapshot(), 0));

    // Light control is valid while idle; print-state commands are not.
    assert(printer.dispatch(0, PrinterCommand::ChamberLightOn, false) == CommandResult::Accepted);
    assert(printer.dispatch(0, PrinterCommand::Pause, false) == CommandResult::RejectedInvalidState);
    assert(printer.dispatch(0, PrinterCommand::Resume, false) == CommandResult::RejectedInvalidState);
    assert(printer.dispatch(0, PrinterCommand::Stop, true) == CommandResult::RejectedInvalidState);

    PrinterState noCommandChannel = firstPrinter;
    noCommandChannel.commandChannelReady = false;
    printer.setState(0, noCommandChannel);
    assert(printer.dispatch(0, PrinterCommand::ChamberLightOn, false) == CommandResult::RejectedCommandChannelUnavailable);
    assert(commandOperationFromResult(CommandResult::RejectedCommandChannelUnavailable).retryable);
    printer.setState(0, firstPrinter);

    // Power has its own authoritative state. Mapping without a ready/fresh
    // channel is never sufficient to authorize a command.
    PowerState power;
    power.mapped = true;
    power.channelReady = true;
    power.freshness = Freshness::Fresh;
    power.stateKnown = true;
    power.on = true;
    store.publishPowerState(0, power);
    assert(store.snapshot().capabilities.power);
    assert(canDispatchPowerCommand(store.snapshot(), 0));
    assert(validatePowerCommand(power, firstPrinter, PowerCommand::On, false, false) == CommandResult::Accepted);
    assert(validatePowerCommand(power, firstPrinter, PowerCommand::Off, false, false) == CommandResult::RejectedGuardRequired);
    assert(validatePowerCommand(power, firstPrinter, PowerCommand::Off, true, false) == CommandResult::Accepted);

    firstObservation.activity = PrinterActivity::Printing;
    firstPrinter = normalizePrinterObservation(firstObservation, 1500, 1000);
    printer.setState(0, firstPrinter);
    assert(printer.dispatch(0, PrinterCommand::Pause, false) == CommandResult::Accepted);
    assert(printer.dispatch(0, PrinterCommand::Resume, false) == CommandResult::RejectedInvalidState);
    assert(printer.dispatch(0, PrinterCommand::Stop, false) == CommandResult::RejectedGuardRequired);
    assert(printer.dispatch(0, PrinterCommand::Stop, true) == CommandResult::Accepted);
    assert(validatePowerCommand(power, firstPrinter, PowerCommand::Off, true, false) == CommandResult::RejectedStrongGuardRequired);
    assert(validatePowerCommand(power, firstPrinter, PowerCommand::Off, true, true) == CommandResult::Accepted);

    firstObservation.activity = PrinterActivity::Paused;
    firstPrinter = normalizePrinterObservation(firstObservation, 1500, 1000);
    printer.setState(0, firstPrinter);
    assert(printer.dispatch(0, PrinterCommand::Resume, false) == CommandResult::Accepted);
    assert(printer.dispatch(0, PrinterCommand::Pause, false) == CommandResult::RejectedInvalidState);

    LegacyPrinterObservation secondObservation = firstObservation;
    secondObservation.activity = PrinterActivity::Printing;
    printer.setState(1, normalizePrinterObservation(secondObservation, 1500, 1000));
    assert(store.snapshot().configuredPrinterCount == 2);
    assert(store.setActivePrinter(1));
    assert(store.snapshot().activePrinterIndex == 1);
    assert(shouldSuspendDecorativeMedia(store.snapshot()));

    PrinterState stalePrinter = normalizePrinterObservation(firstObservation, 5000, 1000);
    printer.setState(0, stalePrinter);
    assert(!isUsable(store.snapshot().printers[0].telemetryFreshness));
    assert(printer.dispatch(0, PrinterCommand::Resume, false) == CommandResult::RejectedStaleState);
    assert(validatePowerCommand(power, stalePrinter, PowerCommand::Off, true, false) == CommandResult::RejectedStrongGuardRequired);
    assert(validatePowerCommand(power, stalePrinter, PowerCommand::Off, true, true) == CommandResult::Accepted);
    assert(validatePowerCommand(power, stalePrinter, PowerCommand::On, false, false) == CommandResult::Accepted);

    PowerState stalePower = power;
    stalePower.freshness = Freshness::Stale;
    assert(validatePowerCommand(stalePower, firstPrinter, PowerCommand::On, false, false) == CommandResult::RejectedStaleState);
    stalePower.freshness = Freshness::Fresh;
    stalePower.channelReady = false;
    assert(validatePowerCommand(stalePower, firstPrinter, PowerCommand::On, false, false) == CommandResult::RejectedCommandChannelUnavailable);

    assert(freshnessFromAge(0, 5000, 1000) == Freshness::Unknown);
    const std::uint32_t nearWrap = std::numeric_limits<std::uint32_t>::max() - 25U;
    assert(freshnessFromAge(nearWrap, 25U, 100U) == Freshness::Fresh);
    assert(freshnessFromAge(nearWrap, 200U, 100U) == Freshness::Stale);
    assert(shouldPreempt(EventPriority::Critical, EventPriority::Decorative));
    assert(!shouldPreempt(EventPriority::Decorative, EventPriority::Critical));

    network.requestReconnect();
    assert(store.snapshot().network.wifi == Connectivity::Connecting);

    InventoryProjectionState inventory;
    inventory.available = false;
    inventory.freshness = Freshness::Unknown;
    store.publishInventoryProjectionState(inventory);
    assert(store.snapshot().inventory.freshness == Freshness::Unknown);
    assert(store.snapshot().inventory.profileId[0] == '\0');

    UpdateState update;
    update.channel = UpdateChannel::Candidate;
    update.phase = UpdatePhase::Available;
    update.manifestFreshness = Freshness::Fresh;
    update.otaSupported = true;
    update.recoveryFullImageSupported = true;
    update.artifactIdentityVerified = true;
    update.rollbackAvailable = true;
    store.publishUpdateState(update);
    assert(store.snapshot().capabilities.update);
    assert(store.snapshot().update.recoveryFullImageSupported);

    // Decorative media must yield to local control health even while printers
    // are otherwise idle.
    firstObservation.activity = PrinterActivity::Idle;
    firstPrinter = normalizePrinterObservation(firstObservation, 1500, 1000);
    printer.setState(0, firstPrinter);
    secondObservation.activity = PrinterActivity::Idle;
    printer.setState(1, normalizePrinterObservation(secondObservation, 1500, 1000));
    HealthState health;
    health.touchResponsive = false;
    store.publishHealthState(health);
    assert(shouldSuspendDecorativeMedia(store.snapshot()));

    return 0;
}
