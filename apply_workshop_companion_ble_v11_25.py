#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
from pathlib import Path

MARKER = "Workshop OS v11.25 Workshop Companion BLE RC1"
FLAG = "WORKSHOP_COMPANION_BLE=1"

SERVICE_UUID = "A3D10000-7A4B-4B82-9C52-57534F533530"
BOOTSTRAP_UUID = "A3D10001-7A4B-4B82-9C52-57534F533530"
DEVICE_EVENT_UUID = "A3D10002-7A4B-4B82-9C52-57534F533530"
PHONE_COMMAND_UUID = "A3D10003-7A4B-4B82-9C52-57534F533530"
DEVICE_STATE_UUID = "A3D10004-7A4B-4B82-9C52-57534F533530"


class PatchError(RuntimeError):
    pass


def load(root: Path, rel: str) -> str:
    path = root / rel
    if not path.exists():
        raise PatchError(f"missing reconstructed source: {rel}")
    return path.read_text(encoding="utf-8")


def save(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise PatchError(f"{label}: expected exactly one anchor, found {count}")
    return text.replace(old, new, 1)


HEADER = r'''#pragma once

#include <Arduino.h>

#if defined(WORKSHOP_COMPANION_BLE) && defined(BOARD_IS_WS350)
void initWorkshopCompanionBle();
void workshopCompanionBleTick();
bool workshopCompanionBleConnected();
bool workshopCompanionBleNotify(const char* type, const char* correlationId, const char* payloadJson = nullptr);
#else
inline void initWorkshopCompanionBle() {}
inline void workshopCompanionBleTick() {}
inline bool workshopCompanionBleConnected() { return false; }
inline bool workshopCompanionBleNotify(const char*, const char*, const char* = nullptr) { return false; }
#endif
'''


SOURCE = r'''#include "workshop_companion_ble.h"

#if defined(WORKSHOP_COMPANION_BLE) && defined(BOARD_IS_WS350)

#include <WiFi.h>
#include <BLEDevice.h>
#include <BLEServer.h>
#include <BLEUtils.h>
#include <BLE2902.h>
#include <ctype.h>

namespace {
constexpr uint8_t kProtocolVersion = 1;
constexpr const char* kServiceUuid = "A3D10000-7A4B-4B82-9C52-57534F533530";
constexpr const char* kBootstrapUuid = "A3D10001-7A4B-4B82-9C52-57534F533530";
constexpr const char* kDeviceEventUuid = "A3D10002-7A4B-4B82-9C52-57534F533530";
constexpr const char* kPhoneCommandUuid = "A3D10003-7A4B-4B82-9C52-57534F533530";
constexpr const char* kDeviceStateUuid = "A3D10004-7A4B-4B82-9C52-57534F533530";
constexpr uint32_t kStateRefreshMs = 1000;
constexpr uint32_t kHelloDelayMs = 350;
constexpr size_t kBlePayloadTarget = 180;

BLEServer* g_server = nullptr;
BLECharacteristic* g_bootstrap = nullptr;
BLECharacteristic* g_deviceEvent = nullptr;
BLECharacteristic* g_phoneCommand = nullptr;
BLECharacteristic* g_deviceState = nullptr;
volatile bool g_phoneConnected = false;
volatile bool g_restartAdvertising = false;
volatile bool g_helloPending = false;
uint32_t g_connectedAtMs = 0;
uint32_t g_lastStateMs = 0;
uint32_t g_lastPhoneRxMs = 0;
String g_lastBootstrap;
String g_lastState;
char g_deviceId[24] = {0};
char g_localName[24] = {0};

bool safeToken(const char* value) {
  if (!value || !*value) return false;
  for (const char* p = value; *p; ++p) {
    const char c = *p;
    if (!(isalnum(static_cast<unsigned char>(c)) || c == '.' || c == '-' || c == '_' || c == ':')) return false;
  }
  return true;
}

String bootstrapJson() {
  String host = WiFi.status() == WL_CONNECTED ? WiFi.localIP().toString() : "0.0.0.0";
  String out;
  out.reserve(150);
  out += "{\"v\":1,\"device\":\"";
  out += g_deviceId;
  out += "\",\"name\":\"Workshop OS\",\"host\":\"";
  out += host;
  out += "\",\"port\":80,\"tls\":false,\"auth\":\"portal-session\"}";
  return out;
}

String stateJson() {
  const bool lan = WiFi.status() == WL_CONNECTED;
  String out;
  out.reserve(80);
  out += "{\"v\":1,\"online\":true,\"phone\":";
  out += g_phoneConnected ? "true" : "false";
  out += ",\"lan\":";
  out += lan ? "true" : "false";
  // BLE never receives or exposes the portal session cookie. The phone can
  // report authenticated LAN state later through lan.ready, but the device
  // state characteristic cannot assert that itself.
  out += ",\"session\":false}";
  return out;
}

void updateBootstrap(bool force = false) {
  if (!g_bootstrap) return;
  const String value = bootstrapJson();
  if (!force && value == g_lastBootstrap) return;
  g_lastBootstrap = value;
  g_bootstrap->setValue(value.c_str());
}

void updateState(bool force = false) {
  if (!g_deviceState) return;
  const String value = stateJson();
  if (!force && value == g_lastState) return;
  g_lastState = value;
  g_deviceState->setValue(value.c_str());
  if (g_phoneConnected) g_deviceState->notify();
}

class ServerCallbacks final : public BLEServerCallbacks {
 public:
  void onConnect(BLEServer*) override {
    g_phoneConnected = true;
    g_connectedAtMs = millis();
    g_helloPending = true;
    updateState(true);
  }

  void onDisconnect(BLEServer*) override {
    g_phoneConnected = false;
    g_helloPending = false;
    g_restartAdvertising = true;
    updateState(true);
  }
};

class PhoneCommandCallbacks final : public BLECharacteristicCallbacks {
 public:
  void onWrite(BLECharacteristic* characteristic) override {
    const std::string raw = characteristic->getValue();
    if (raw.empty() || raw.size() > kBlePayloadTarget) return;
    // v1 is deliberately response-only. No BLE message maps to printer,
    // power, light, settings, authentication, or recovery mutations.
    if (raw.find("\"v\":1") == std::string::npos) return;
    if (raw.find("\"t\":") == std::string::npos) return;
    g_lastPhoneRxMs = millis();
  }
};

ServerCallbacks g_serverCallbacks;
PhoneCommandCallbacks g_phoneCommandCallbacks;
}  // namespace

bool workshopCompanionBleNotify(const char* type, const char* correlationId, const char* payloadJson) {
  if (!g_phoneConnected || !g_deviceEvent || !safeToken(type) || !safeToken(correlationId)) return false;
  String out;
  out.reserve(kBlePayloadTarget);
  out += "{\"v\":1,\"id\":\"";
  out += correlationId;
  out += "\",\"t\":\"";
  out += type;
  out += "\"";
  if (payloadJson && *payloadJson) {
    if (*payloadJson != '{') return false;
    out += ",\"p\":";
    out += payloadJson;
  }
  out += "}";
  if (out.length() > kBlePayloadTarget) return false;
  g_deviceEvent->setValue(out.c_str());
  g_deviceEvent->notify();
  return true;
}

bool workshopCompanionBleConnected() {
  return g_phoneConnected;
}

void initWorkshopCompanionBle() {
  if (g_server) return;

  const uint64_t mac = ESP.getEfuseMac();
  snprintf(g_deviceId, sizeof(g_deviceId), "ws350-%04X", static_cast<unsigned>(mac & 0xFFFFU));
  snprintf(g_localName, sizeof(g_localName), "Workshop-%04X", static_cast<unsigned>(mac & 0xFFFFU));

  Serial.printf("[COMPANION] BLE init %s heap=%u\n", g_localName, static_cast<unsigned>(ESP.getFreeHeap()));
  BLEDevice::init(g_localName);
  g_server = BLEDevice::createServer();
  g_server->setCallbacks(&g_serverCallbacks);

  BLEService* service = g_server->createService(kServiceUuid);
  g_bootstrap = service->createCharacteristic(kBootstrapUuid, BLECharacteristic::PROPERTY_READ);
  g_deviceEvent = service->createCharacteristic(kDeviceEventUuid, BLECharacteristic::PROPERTY_NOTIFY);
  g_phoneCommand = service->createCharacteristic(kPhoneCommandUuid, BLECharacteristic::PROPERTY_WRITE);
  g_deviceState = service->createCharacteristic(kDeviceStateUuid,
      BLECharacteristic::PROPERTY_READ | BLECharacteristic::PROPERTY_NOTIFY);

  g_deviceEvent->addDescriptor(new BLE2902());
  g_deviceState->addDescriptor(new BLE2902());
  g_phoneCommand->setCallbacks(&g_phoneCommandCallbacks);

  updateBootstrap(true);
  updateState(true);
  service->start();

  BLEAdvertising* advertising = BLEDevice::getAdvertising();
  advertising->addServiceUUID(kServiceUuid);
  advertising->setScanResponse(true);
  advertising->start();
  Serial.println("[COMPANION] BLE advertising started; auth remains portal-session over LAN");
}

void workshopCompanionBleTick() {
  if (!g_server) return;

  if (g_restartAdvertising) {
    g_restartAdvertising = false;
    delay(2);
    BLEDevice::startAdvertising();
  }

  const uint32_t now = millis();
  if (now - g_lastStateMs >= kStateRefreshMs) {
    g_lastStateMs = now;
    updateBootstrap();
    updateState();
  }

  if (g_phoneConnected && g_helloPending && now - g_connectedAtMs >= kHelloDelayMs) {
    if (workshopCompanionBleNotify(
          "hello", "boot",
          "{\"caps\":[\"camera-request\",\"tts-request\",\"notify\",\"lan-handoff\"]}")) {
      g_helloPending = false;
    }
  }

  (void)g_lastPhoneRxMs;
}

#endif  // WORKSHOP_COMPANION_BLE && BOARD_IS_WS350
'''


def patch_main(root: Path) -> None:
    rel = "src/main.cpp"
    text = load(root, rel)
    if '#include "workshop_companion_ble.h"' not in text:
        text = replace_once(
            text,
            '#include "web_server.h"',
            '#include "web_server.h"\n#include "workshop_companion_ble.h"',
            "main companion include",
        )
    if "initWorkshopCompanionBle();" not in text:
        text = replace_once(
            text,
            "    tasmotaInit();",
            "    tasmotaInit();\n    initWorkshopCompanionBle();",
            "companion startup hook",
        )
    if "workshopCompanionBleTick();" not in text:
        text = replace_once(
            text,
            "  handleWebServer();",
            "  handleWebServer();\n  workshopCompanionBleTick();",
            "companion loop hook",
        )
    save(root, rel, text)


def patch_board(root: Path) -> None:
    rel = "boards/ws_lcd_350.ini"
    text = load(root, rel)
    if FLAG not in text:
        text = replace_once(
            text,
            "    -D BOARD_IS_WS350=1",
            "    -D BOARD_IS_WS350=1\n    -D WORKSHOP_COMPANION_BLE=1",
            "WS350 companion build flag",
        )
    save(root, rel, text)


def patch_build(root: Path) -> None:
    rel = "include/smart_home_build.h"
    text = load(root, rel)
    if MARKER in text:
        return
    text, n = re.subn(r'#define SMART_HOME_VERSION\s+"v11\.24"', '#define SMART_HOME_VERSION "v11.25"', text, count=1)
    if n != 1:
        raise PatchError("build version v11.24 anchor missing")
    text, n = re.subn(r'#define SMART_HOME_PROFILE\s+"[^"]+"', '#define SMART_HOME_PROFILE "workshop-companion"', text, count=1)
    if n != 1:
        raise PatchError("build profile anchor missing")
    text = replace_once(
        text,
        "Smart Home v11.24 Audio Console RC1",
        "Smart Home v11.25 Workshop Companion BLE RC1",
        "build label",
    )
    text += f"\n// {MARKER}\n"
    save(root, rel, text)


def apply(root: Path) -> None:
    if not root.exists():
        raise PatchError(f"repository path not found: {root}")
    build = load(root, "include/smart_home_build.h")
    if MARKER in build:
        print(f"{MARKER} already applied")
        return
    if 'SMART_HOME_VERSION "v11.24"' not in build:
        raise PatchError("v11.24 Audio Console base is required")

    save(root, "src/workshop_companion_ble.h", HEADER)
    save(root, "src/workshop_companion_ble.cpp", SOURCE)
    patch_main(root)
    patch_board(root)
    patch_build(root)

    checks = {
        "src/workshop_companion_ble.cpp": [
            SERVICE_UUID, BOOTSTRAP_UUID, DEVICE_EVENT_UUID, PHONE_COMMAND_UUID, DEVICE_STATE_UUID,
            "portal-session", "hello", "camera-request", "tts-request", "lan-handoff",
        ],
        "src/main.cpp": ["initWorkshopCompanionBle();", "workshopCompanionBleTick();"],
        "boards/ws_lcd_350.ini": [FLAG],
        "include/smart_home_build.h": [
            'SMART_HOME_VERSION "v11.25"',
            'SMART_HOME_PROFILE "workshop-companion"',
            "Smart Home v11.25 Workshop Companion BLE RC1",
        ],
    }
    for rel, needles in checks.items():
        body = load(root, rel)
        for needle in needles:
            if needle not in body:
                raise PatchError(f"{rel}: missing {needle}")

    print(f"{MARKER} applied")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    if not args.apply:
        raise SystemExit("refusing to mutate without --apply")
    apply(Path(args.repo))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
