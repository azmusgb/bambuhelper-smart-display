# Workshop OS v11.26 Workshop Companion Web RC1

This is a stacked hardware candidate on top of v11.25 Workshop Companion BLE RC1. It does not replace the accepted v11.22 source baseline and cannot be promoted independently of the v11.23 → v11.24 → v11.25 candidate chain.

## Goal

Make an iPhone useful with Workshop OS immediately through Safari or an installed Home Screen web app, without requiring the native BLE companion for ordinary operation.

The Waveshare itself hosts the Companion page at:

```text
http://<waveshare-host>/companion
```

The first implementation uses authenticated local HTTP synchronization instead of introducing a second socket/networking library into the ESP32 firmware.

## Connection model

```text
iPhone Safari / PWA
       ⇅
authenticated local HTTP
       ⇅
Waveshare Workshop OS
       ⇅
existing MQTT / smart-plug command paths
       ⇅
P1S / AMS / mapped power
```

No cloud relay is required for the phone ↔ Waveshare relationship. Both devices only need to be able to reach each other on the local network.

## Authentication

`/companion` does not create another authorization model.

- It uses the existing boot-scoped Workshop OS portal session.
- An unauthenticated visit redirects to `/login?next=/companion`.
- The login continuation is allowlisted to the literal `/companion` path; arbitrary redirect targets are not accepted.
- Companion mutations pass through the existing session and same-origin checks.
- No portal code, session cookie, printer access code, Wi-Fi credential, or inventory credential is embedded in the page.

## Phone → device

The page reuses already-proven guarded Workshop OS routes instead of issuing printer protocol packets directly:

- chamber light → `POST /light/set`;
- pause/resume/stop → `POST /printer/control`;
- printer power status → `GET /printer/power/status`;
- mapped smart-plug power → `POST /printer/power`.

Existing safety semantics remain authoritative:

- stop requires the explicit `STOP` confirmation and is exposed as a hold action;
- power-off is a hold action;
- power-off during an active print uses the stronger `POWER OFF DURING PRINT` confirmation;
- stale/offline state disables commands;
- the command backend remains the same deferred MQTT/smart-plug path used by the device and existing browser UI.

## Device → phone

While the page is visible it refreshes current Workshop OS state approximately every 1.2 seconds. When the page is hidden it backs off to approximately every 5 seconds.

This makes printer state, progress, temperatures, layer information, chamber-light state, and power state flow back from the Waveshare to the phone without a cloud intermediary.

The first release deliberately uses this bounded HTTP live-sync model rather than WebSocket so that functionality can be validated on the existing synchronous ESP32 `WebServer` stack before adding another transport dependency.

## Phone presence

The page sends an authenticated heartbeat to:

```text
POST /companion/heartbeat
```

The Waveshare considers the web phone present for 15 seconds after the last heartbeat.

The v11.25 BLE `phone` state is extended so that either:

- a connected BLE companion; or
- a recently active authenticated Companion Web session

can satisfy phone presence. This is transport-neutral presence only; it does not move command authorization into BLE.

## iPhone camera

Web v1 exposes the iPhone rear-camera capture affordance through Safari/PWA file capture.

The resulting image is previewed locally on the phone and is **not uploaded** in this candidate. Authenticated photo upload is intentionally deferred until a bounded storage/size/lifetime contract is defined and physically accepted.

## Home Screen use

The page includes iPhone web-app metadata and a manifest so it can be used as a dedicated Home Screen experience after opening it in Safari. The canonical application remains hosted by the Waveshare; there is no separately deployed web copy required for normal local operation.

## Native Companion relationship

The native Workshop Companion app remains the enhanced layer for BLE discovery/presence and Apple-specific functionality. The web experience is the primary zero-install local control surface.

Both are designed to converge on the same Workshop OS state and authenticated LAN command authority.

## Software validation

The firmware gate must prove:

- deterministic reconstruction through v11.25;
- v11.25 BLE/security contract still passes before the web delta;
- v11.26 Companion Web applicator and contract validator pass;
- embedded Companion JavaScript parses successfully;
- no generic login open redirect exists;
- portal/session and same-origin security remain present;
- no speculative speed/fan/temperature/AMS commands are added;
- native `ws_lcd_350` build passes;
- BLE-neutral/shared `jc3248w535` regression build passes;
- Full + OTA candidate artifacts are generated.

## Physical acceptance

Before promotion, verify on the real WS350 and iPhone:

1. Open `/companion` in iPhone Safari while unauthenticated.
2. Confirm portal-code login returns directly to `/companion`.
3. Confirm Add to Home Screen launches the Companion page correctly.
4. Confirm live printer state updates without manual refresh.
5. Toggle chamber light and observe the printer-reported state return to the phone.
6. Pause and resume an actual print.
7. Confirm a short stop tap cannot cancel a print; hold-to-stop must work only after deliberate completion.
8. Confirm printer power-on works for the mapped plug.
9. Confirm power-off requires a hold and active-print power-off retains the stronger warning/confirmation path.
10. Confirm losing Wi-Fi/stale state disables controls and recovery occurs after reconnect.
11. Confirm switching Safari to background reduces request cadence and returning foreground restores fast state refresh.
12. Confirm the camera capture opens on iPhone and remains local in this candidate.
13. Confirm Companion heartbeat makes the device report phone presence and expires after the phone is absent.
14. Verify simultaneous BLE + Companion Web + Wi-Fi + MQTT + Audio Console operation does not destabilize the device.
15. Observe heap/memory during an extended Companion session.
16. Confirm normal Workshop OS management still requires the portal/session boundary.

CI success is not physical acceptance. This candidate remains draft until its base candidates and these real-device checks are accepted.
