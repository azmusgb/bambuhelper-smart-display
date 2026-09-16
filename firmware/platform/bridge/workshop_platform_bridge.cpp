#include "workshop_platform_bridge.h"

#include "bambu_mqtt.h"
#include "bambu_state.h"
#include "config.h"
#include "settings.h"
#include "wifi_manager.h"
#include "workshop_platform/runtime_adapter.hpp"
#include "workshop_platform/service_contracts.hpp"

#include <Arduino.h>
#include <WiFi.h>

namespace {

workshop::platform::StateStore g_workshopStateStore;

workshop::platform::PrinterActivity mapPrinterActivity(PrinterGcodeState state) {
    using workshop::platform::PrinterActivity;
    switch (state) {
        case GCODE_IDLE: return PrinterActivity::Idle;
        case GCODE_PREPARE: return PrinterActivity::Preparing;
        case GCODE_RUNNING: return PrinterActivity::Printing;
        case GCODE_PAUSE: return PrinterActivity::Paused;
        case GCODE_FINISH: return PrinterActivity::Finished;
        case GCODE_FAILED: return PrinterActivity::Error;
        case GCODE_UNKNOWN:
        case GCODE_OTHER:
        default: return PrinterActivity::Unknown;
    }
}

std::int16_t clampTemperature(float value) {
    if (value > 32767.0f) return 32767;
    if (value < -32768.0f) return -32768;
    return static_cast<std::int16_t>(value);
}

std::uint32_t staleThresholdForSlot(std::size_t slot) {
    if (slot >= MAX_PRINTERS || !isPrinterConfigured(static_cast<uint8_t>(slot))) {
        return static_cast<std::uint32_t>(BAMBU_STALE_TIMEOUT);
    }
    return isCloudMode(printers[slot].config.mode)
        ? static_cast<std::uint32_t>(BAMBU_STALE_TIMEOUT) * 5U
        : static_cast<std::uint32_t>(BAMBU_STALE_TIMEOUT);
}

workshop::platform::PrinterState observePrinter(std::size_t slot, std::uint32_t nowMs) {
    using namespace workshop::platform;

    LegacyPrinterObservation observation;
    if (slot >= MAX_PRINTERS || !isPrinterConfigured(static_cast<uint8_t>(slot))) {
        return normalizePrinterObservation(observation, nowMs, BAMBU_STALE_TIMEOUT);
    }

    const BambuState& source = printers[slot].state;
    observation.configured = true;
    observation.connected = source.connected;
    observation.activity = mapPrinterActivity(source.gcodeStateId);
    observation.lastTelemetryAtMs = static_cast<std::uint32_t>(source.lastUpdate);
    observation.nozzleCelsius = clampTemperature(source.nozzleTemp);
    observation.bedCelsius = clampTemperature(source.bedTemp);
    observation.progressPercent = source.progress;

    return normalizePrinterObservation(observation, nowMs, staleThresholdForSlot(slot));
}

workshop::platform::NetworkState observeNetwork(std::uint32_t nowMs) {
    using namespace workshop::platform;

    const bool connected = isWiFiConnected();
    const bool accessPoint = isAPMode();
    String localAddress;
    if (connected || accessPoint) localAddress = WiFi.localIP().toString();

    LegacyNetworkObservation observation;
    observation.connected = connected;
    observation.connecting = !connected && !accessPoint;
    observation.accessPointMode = accessPoint;
    observation.localPortal = (connected || accessPoint) ? Connectivity::Online : Connectivity::Unknown;
    // Wi-Fi reachability is not proof of cloud reachability. Preserve Unknown
    // until a dedicated cloud-health observation exists.
    observation.cloud = Connectivity::Unknown;
    observation.observedAtMs = nowMs;
    observation.rssiDbm = connected ? static_cast<std::int16_t>(WiFi.RSSI()) : 0;
    observation.localAddress = localAddress.length() ? localAddress.c_str() : nullptr;
    return normalizeNetworkObservation(observation);
}

}  // namespace

void workshopPlatformBegin() {
    workshopPlatformPoll();
}

void workshopPlatformPoll() {
    const std::uint32_t nowMs = static_cast<std::uint32_t>(millis());
    g_workshopStateStore.publishNetworkState(observeNetwork(nowMs));

    for (std::size_t slot = 0; slot < workshop::platform::kMaxPrinterSlots; ++slot) {
        g_workshopStateStore.publishPrinterState(slot, observePrinter(slot, nowMs));
    }

    if (activePrinterIndex < MAX_PRINTERS) {
        g_workshopStateStore.setActivePrinter(activePrinterIndex);
    }
}

const workshop::platform::WorkshopState& workshopPlatformState() {
    return g_workshopStateStore.snapshot();
}
