# Workshop OS v11.23 RC2 — WS350 Touch UX

## Status

**Hardware candidate only.** Workshop OS v11.22 remains the physically accepted source baseline until v11.23 RC2 passes exact-head CI and real-device touch/network/display acceptance.

RC1 validated the underlying Network / Locale / Layout behavior and 32-view capture surface, but physical testing exposed a usability problem: too many actions depended on dense cards and hidden short-press/long-press semantics. RC2 treats that as an acceptance failure rather than normalizing it as technical debt.

## Interaction principles

RC2 applies the following rules to the 480×320 WS350 touch surface:

1. **Common actions are visible.** Back, Next, Prev, increment, decrement, Discard, and Review are explicit controls.
2. **Large targets first.** Primary controls are designed around roughly 40–56 px high reference targets rather than small text affordances.
3. **Long press is reserved for guarded actions.** Ordinary navigation no longer depends on hidden hold gestures. Network Apply and display Rotation remain hold-guarded.
4. **Staged state is unmistakable.** Network edits show `STAGED — NOT APPLIED` until a deliberate Review/Apply action.
5. **Cancel paths do not persist staged addressing.** Back navigates without saving; Discard reloads persisted network values.
6. **Direction is discoverable.** Display Expert uses left/right interaction semantics instead of “tap next / hold previous”.
7. **Touch ownership stays local.** Custom Workshop OS pages continue consuming their own touch events so stock printer-control screens keep their established behavior.

## Network Expert RC2

### 1 / 4 — Essentials

- large Startup IP card
- large Clock Format card
- large Date Format card
- large mDNS card
- explicit Back / Next

### 2 / 4 — Time & Locale

- full-width timezone presentation
- explicit `< PREV` and `NEXT >` timezone controls
- Clock Format and Date Format cards
- explicit Back / Next
- timezone changes remain immediate because they are non-network-disruptive and easily reversible

### 3 / 4 — Address Editor

The page prominently shows:

`STAGED — NOT APPLIED`

Controls:

- DHCP / Static mode
- previous / next field
- four selectable IPv4 octets
- `-10`, `-1`, `+1`, `+10`
- Back / Review

Editing this page changes only the in-memory staged buffer. It does not write `netSettings` and does not restart the device.

### 4 / 4 — Review

The page separates three actions:

- **Back** — return to editor
- **Discard** — reload persisted settings and abandon staged values
- **HOLD APPLY + RESTART** — validate, persist the complete addressing set atomically, then restart

A short tap on Apply is intentionally insufficient.

## Display Expert RC2

For reversible expert values, RC2 removes the hidden “hold to reverse” convention. Within the setting card interaction surface:

- left side = previous / decrement
- right side = next / increment

Copy is updated to make the direction explicit.

Display rotation remains different by design: rotation can change both orientation and touch mapping, so it remains a deliberate hold-only action and is labeled accordingly.

## Temporary trusted-LAN mode

At the user's request, RC2 temporarily bypasses the normal-Wi-Fi portal-code challenge during hardware iteration.

The implementation deliberately preserves the security architecture instead of deleting it:

- the inherited v11.20 authentication baseline is reconstructed and validated first;
- RC2 then applies a small build-gated `WORKSHOP_OS_TEMP_LAN_OPEN` delta;
- station-mode management access does not require a session cookie while that flag is enabled;
- same-origin protection remains mandatory for mutating requests;
- AP/setup/recovery authorization remains route-scoped;
- blanket `isAPMode()` authorization remains forbidden;
- the browser displays a visible temporary trusted-LAN warning;
- the capture helper tries the no-code path first and retains credential-safe authenticated fallback for older builds.

This mode is intended only for a trusted/private LAN during development. It is not the target security posture for a hardened release.

## Physical acceptance gates

RC2 must pass all of the following before source promotion:

- exact-head Validate, Release Gate, and v11.23 RC2 native firmware gate;
- `ws_lcd_350` native build;
- `jc3248w535` shared-target regression;
- RC2 touch UX contract and settings parity;
- device boots `safeMode=false`, `webReady=true`, touch responsive;
- no portal code required from normal Wi-Fi for portal/capture access;
- all 32 framebuffer views captured successfully;
- no clipping or hit-target ambiguity on Network Expert pages;
- timezone Prev/Next works and can be restored;
- staged address editing does not persist before Apply;
- Back and Discard behave distinctly and safely;
- short-tap Apply does nothing destructive;
- hold Apply works only when deliberately tested under safe conditions;
- Display Expert left/right direction is intuitive;
- rotation remains guarded and touch mapping remains aligned after rotation;
- existing printer-control safety is unchanged.

## Non-goals

RC2 does not introduce speed, fan, temperature, AMS, or other speculative printer commands. Wi-Fi credentials and hostname remain browser-input settings rather than touchscreen free-text entry.
