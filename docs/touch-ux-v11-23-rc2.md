# Workshop OS v11.23 RC2 — WS350 Touch UX

## Status

**Hardware candidate only.** Workshop OS v11.22 remains the physically accepted source baseline until v11.23 RC2 passes exact-head CI and real-device touch/network/display acceptance.

RC1 validated the underlying Network / Locale / Layout behavior and 32-view capture surface, but physical testing exposed a usability problem: too many actions depended on dense cards and hidden short-press/long-press semantics. RC2 treats that as an acceptance failure rather than normalizing it as technical debt.

## Interaction principles

RC2 applies the following rules to the 480×320 WS350 touch surface:

1. **Common actions are visible.** Back, Next, Prev, increment, decrement, Discard, Review, and rotation staging are explicit controls.
2. **Large targets first.** Primary controls target roughly **52–60 px high** reference hit areas where the 480×320 layout permits it. Status-only banners and secondary informational cards may be smaller, but primary navigation and numeric edit actions must not depend on tiny text targets.
3. **Long press is reserved for guarded commits.** Ordinary navigation no longer depends on hidden hold gestures. Network Apply and rotation Commit remain hold-guarded.
4. **Staged state is unmistakable.** Network edits show `STAGED — NOT APPLIED` until a deliberate Review/Apply action.
5. **Cancel paths do not persist staged addressing.** Back navigates without saving; Discard reloads persisted network values.
6. **Direction is discoverable.** Display Expert uses left/right interaction semantics instead of “tap next / hold previous”.
7. **Touch ownership stays local.** Custom Workshop OS pages continue consuming their own touch events so stock printer-control screens keep their established behavior.
8. **A guarded action must expose a safe pre-commit state.** Rotation is previewed before commit; network addressing is reviewed before Apply.

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

The physical-touch finalization enlarges the octet and delta controls to 52 px reference hit areas and enlarges primary page navigation. Editing this page changes only the in-memory staged buffer. It does not write `netSettings` and does not restart the device.

### 4 / 4 — Review

The page separates three actions:

- **Back** — return to editor
- **Discard** — reload persisted settings and abandon staged values
- **HOLD APPLY + RESTART** — validate, persist the complete addressing set atomically, then restart

A short tap on Apply is intentionally insufficient.

Network Apply is disruptive to the display connection because the display restarts and may reconnect on a different address. It does **not** command or stop the printer. Physical acceptance must therefore keep Apply unexecuted unless a deliberate network-change test is being performed under safe conditions.

## Display Expert RC2

For reversible expert values, RC2 removes the hidden “hold to reverse” convention. Within the setting card interaction surface:

- left side = previous / decrement
- right side = next / increment

Copy is updated to make the direction explicit.

### Dedicated rotation preview

Rotation is no longer committed directly from **Display → Extras**.

A normal tap on the Rotation card opens a dedicated full-screen guarded interaction containing:

- **CURRENT** orientation
- **PREVIEW** orientation
- explicit **Prev / Next** staging controls
- **Cancel**
- **HOLD TO COMMIT ROTATION**

Changing Preview does not persist orientation. A short tap on Commit does not persist orientation. Only the deliberate hold commits the staged rotation through the normal display-settings persistence path, which also updates the display/touch mapping.

The rotation preview is a modal interaction rather than an additional deterministic capture page, so the established 32-view framebuffer catalog remains unchanged.

## Temporary trusted-LAN mode

At the user's request, RC2 temporarily bypasses the normal-Wi-Fi portal-code challenge during hardware iteration.

The implementation deliberately preserves the security architecture instead of deleting it:

- the inherited v11.20 authentication baseline is reconstructed and validated first;
- RC2 then applies a small build-gated `WORKSHOP_OS_TEMP_LAN_OPEN` delta;
- station-mode management access does not require a session cookie while that flag is enabled;
- same-origin protection remains mandatory for mutating requests;
- AP/setup/recovery authorization remains route-scoped;
- blanket `isAPMode()` authorization remains forbidden;
- the browser displays a visible temporary trusted-LAN warning.

For RC2 acceptance, both the framebuffer capture helper and the physical acceptance helper are **no-code only**. They deliberately do not prompt for, accept, or fall back to a portal code. If normal station-mode no-code access is not active, the helper fails so the regression is visible.

This mode is intended only for a trusted/private LAN during development. It is not the target security posture for a hardened release.

## Physical acceptance gates

RC2 must pass all of the following before source promotion:

- exact-head Validate, Release Gate, and v11.23 RC2 native firmware gate;
- `ws_lcd_350` native build;
- `jc3248w535` shared-target regression;
- RC2 touch UX contract, physical-touch finalization contract, and settings parity;
- device boots `safeMode=false`, `webReady=true`, touch responsive;
- no portal code required from normal Wi-Fi for portal/capture/acceptance access;
- no RC2 helper contains a portal-code login fallback;
- all 32 deterministic framebuffer views captured successfully;
- no clipping or hit-target ambiguity on Network Expert pages;
- primary Network navigation and numeric edit controls are comfortably finger-sized;
- timezone Prev/Next works and can be restored;
- staged address editing does not persist before Apply;
- Back and Discard behave distinctly and safely;
- short-tap Apply does nothing destructive;
- rotation opens a dedicated preview instead of rotating directly from Extras;
- changing rotation Preview does not persist;
- short-tap rotation Commit does not persist;
- deliberate hold Commit changes orientation and touch mapping together;
- rotation can be restored to the original orientation with touch still aligned;
- existing printer-control safety is unchanged.

## Non-goals

RC2 does not introduce speed, fan, temperature, AMS, or other speculative printer commands. Wi-Fi credentials and hostname remain browser-input settings rather than touchscreen free-text entry.
