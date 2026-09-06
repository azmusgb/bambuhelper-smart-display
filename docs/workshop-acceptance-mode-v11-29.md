# Workshop OS v11.29 Acceptance Open LAN RC1

## Why this candidate exists

Physical testing exposed an iPhone/Safari portal-login defect: the rotating code shown by the WS350 was valid, but Safari rejected the login field locally with **Match the requested format** before Workshop OS received the form.

For the current development and physical-acceptance phase, portal-code authentication is intentionally disabled by default on normal station-mode Wi-Fi. This removes login friction while preserving meaningful browser mutation safeguards and Recovery/AP scoping.

## Normal-LAN policy

- no portal code is required for normal Workshop OS pages;
- the WS350 does not display the rotating portal credential;
- boot does not generate a portal credential solely for normal-LAN use;
- read-only normal-LAN pages are open;
- mutating browser requests still require same-origin Origin/Referer provenance;
- the `X-BambuHelper-Client` header alone is **not** accepted as mutation provenance while login is disabled;
- sensitive `/settings/export` and `/debug` access is blocked in Acceptance Mode;
- OTA from the Workshop OS browser remains available through the normal same-origin path;
- printer control, power, light, Companion capture and other mutations still pass their existing domain-specific guards after the browser-origin check.

This is not intended to be the final production security policy. It is a named, compile-time candidate mode for physical iteration.

## AP / Recovery policy

The v11.20 scoped AP policy remains intact:

- ordinary setup/fallback AP exposes onboarding essentials only;
- ordinary AP does not inherit the normal-LAN open policy;
- deliberate Recovery Safe Mode keeps its dedicated recovery/OTA/reset paths;
- unrelated privileged routes do not become public merely because the radio is in AP mode.

## Safari login repair retained for later

The portal implementation is not deleted. When authentication is re-enabled later, the login page no longer uses the brittle HTML `pattern='[A-HJ-NP-Z2-9]{10}'` constraint that triggered the observed iPhone failure.

Instead:

- the field is capped at 10 characters;
- iOS gets text input + Go semantics;
- firmware remains authoritative: trim, uppercase, then constant-time compare against the generated code.

## Physical System screen

The former **PORTAL ACCESS** card becomes:

- **LOCAL ACCESS**
- **OPEN**
- **No sign-in required**

The live rotating portal code is not rendered in this candidate.

## Included enhancement stack

v11.29 reconstructs through:

1. v11.27 Companion Link — single state envelope + volatile phone-photo upload;
2. v11.28 Physical Companion Viewer — explicit **Show on Waveshare** phone-photo display;
3. v11.29 Acceptance Mode — open normal LAN, Safari auth repair for future use, physical portal-code suppression, tighter open-mode mutation provenance.

## Physical acceptance

Validate on the actual WS350 before promotion:

- opening `http://<device-ip>/` from iPhone Safari goes directly to Workshop OS with no login prompt;
- `/companion` opens directly;
- OTA upload from Safari succeeds using the v11.29 OTA binary;
- unauthenticated cross-origin/state-changing requests remain rejected;
- normal same-origin Light, Pause/Resume, guarded Stop and mapped Power work;
- `/settings/export` and `/debug` are blocked in Acceptance Mode;
- System screen shows **LOCAL ACCESS / OPEN** and no rotating credential;
- ordinary AP fallback remains onboarding-only;
- deliberate Recovery Safe Mode still provides intended recovery/OTA access;
- photo upload + **Show on Waveshare** works, upload alone never steals the display, and normal chamber-camera fallback remains intact;
- settings, Wi-Fi and printer configuration survive reboot/OTA as expected;
- touch, audio, BLE, MQTT, power polling and display behavior remain stable.

## Promotion boundary

This remains a hardware candidate. CI proves reconstruction, security contracts and native builds; it does not replace real-device acceptance.
