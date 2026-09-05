# Workshop OS v11.25 Workshop Companion BLE RC1

This is a stacked hardware candidate on top of v11.24 Audio Console RC1. It is preparation only until the v11.23/v11.24 base stack is physically accepted.

## Purpose

Add the ESP32-S3 half of Workshop Companion v1 without turning BLE into a second management or printer-control authority.

## WS350 BLE service

The WS350 advertises the versioned Workshop Companion service and exposes:

- Bootstrap — read-only non-secret LAN endpoint metadata;
- Device event — notify-only compact device→phone events;
- Phone command — write-with-response compact phone→device responses;
- Device state — read/notify connectivity state.

UUIDs match the Workshop Companion v1 protocol.

## Runtime behavior

- BLE initializes only when both `WORKSHOP_COMPANION_BLE` and `BOARD_IS_WS350` are defined.
- The WS350 board profile enables the capability; shared `jc3248w535` remains BLE-neutral.
- Startup publishes a short non-identifying local name derived from the ESP32 efuse MAC suffix.
- Bootstrap exposes local IP/port plus `auth=portal-session`; it exposes no credential.
- Device state reports BLE/LAN presence but never contains an authenticated cookie/token.
- A phone connection receives a `hello` event advertising camera-request/TTS/notification/LAN-handoff capability names.
- `ping`/response and other phone messages are treated only as companion protocol traffic.
- Disconnect restarts advertising.
- BLE failure or absence does not block Wi-Fi, MQTT, display, printer, audio, or power behavior.

## Explicit security boundary

BLE v1 does **not**:

- pause, resume or stop a print;
- change chamber light state;
- change smart-plug power;
- change Workshop OS settings;
- authorize recovery or OTA;
- carry Wi-Fi credentials;
- carry printer access codes;
- carry portal codes or session cookies;
- carry inventory credentials.

Protected operations remain on the existing authenticated Workshop OS LAN/session and guarded command paths.

## Payload boundary

BLE events/commands target <= 180 bytes. Images, microphone recordings, TTS audio, historical telemetry and other larger payloads belong on the Wi-Fi/LAN plane.

## Acceptance gate

Promotion requires, at minimum:

- exact-head deterministic reconstruction;
- protocol/security validator pass;
- native `ws_lcd_350` build;
- BLE-neutral `jc3248w535` regression build;
- Full + OTA candidate artifacts;
- real iPhone discovery/connect/disconnect/reconnect;
- bootstrap/state/event characteristic validation;
- iPhone camera/TTS/notification request round trip;
- Wi-Fi/MQTT/printer telemetry stability while BLE connected and disconnected;
- heap/memory observation with BLE + Wi-Fi + MQTT + audio active;
- confirmation that normal station-mode management still requires the portal/session boundary.

No physical-acceptance claim is made by this source preparation.
