# Workshop OS v11.30 — Unified Web + Companion RC2

v11.30 evolves the two browser surfaces as one product while keeping their jobs distinct:

- **Workshop OS web** is the complete local control/configuration surface.
- **Workshop Companion** is the phone-first operational surface for live state, guarded controls, photos and device context.

## Standard Workshop OS web

The full web UI adds a persistent live rail showing:

- workshop freshness;
- printer state and active job;
- mapped power state / watts;
- Companion presence and phone-photo state;
- device RSSI.

It also adds deterministic attention warnings for stale state, printer offline, impossible active-print/power combinations, and very weak Wi-Fi.

On phones, a four-target bottom dock keeps **Home / Printer / Companion / More** reachable without forcing the user back through the desktop navigation hierarchy.

The supplemental live-state poll is intentionally paused during firmware upload so it cannot compete with OTA for the ESP32 web connection.

## Workshop Companion

Companion stays a focused, one-page control surface rather than duplicating the complete portal.

It adds:

- sticky jump navigation for **Overview / Controls / Photo / System**;
- a compact Attention summary derived from the existing live DOM/state loop;
- larger phone targets and improved scroll offsets;
- clearer photo-state presentation;
- first-class handoff back to the full Workshop OS.

No extra Companion state poll is introduced by the Attention summary.

## RC2 — Physical phone-photo viewer reliability

Physical acceptance exposed a real state-machine defect in the inherited v11.28 viewer.

`Show on Waveshare` placed the display into the existing `SCREEN_CAMERA` surface. The core state machine treated that surface as valid only while the displayed Bambu printer itself could stream its chamber camera. A phone JPEG therefore appeared to activate successfully, but the next state-machine pass could immediately leave `SCREEN_CAMERA` and clear the phone-viewer flag.

RC2 makes the phone photo a **sticky explicit display override** while retaining the proven camera renderer:

- the viewer remains active independently of printer camera availability;
- it also remains valid if the printer is offline or no printer is configured;
- auto-OTA may still preempt the viewer;
- one physical tap exits to the exact screen that was active before `Show on Waveshare`;
- the normal chamber-camera path remains unchanged whenever the phone override is inactive;
- Companion no longer announces success merely because the POST returned HTTP 200 — it refreshes state and requires `capture.viewer=true` before saying the photo is actually displaying;
- both the full web rail and Companion expose whether the photo is merely stored or **Displaying**.

The JPEG itself remains volatile PSRAM-only and is never written to flash.

## v11.29 Acceptance Mode inherited

For WS350 physical acceptance only, normal-LAN portal-code authentication remains disabled by default. Same-origin mutation protection remains active, the historical header-only mutation provenance shortcut remains disabled, sensitive export/debug routes remain blocked, and AP/recovery scoping remains preserved.

## Promotion boundary

v11.30 RC2 remains a hardware candidate until physical WS350 acceptance verifies:

- standard web layout on desktop and phone;
- Companion jump navigation and controls;
- `Show on Waveshare` actually produces the physical photo viewer;
- physical tap returns to the prior screen;
- chamber camera still works when the phone viewer is inactive;
- OTA remains stable with supplemental polling paused;
- printer, power, audio, BLE, Wi-Fi, persistence and recovery behavior remain stable.
