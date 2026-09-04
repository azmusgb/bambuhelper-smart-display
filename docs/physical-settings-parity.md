# Physical Settings Parity

This document is the human-readable contract for moving BambuHelper / Workshop OS configuration onto the WS350 touchscreen without turning the normal Home / Printer / Workshop surfaces into an expert settings form.

The **machine-authoritative inventory** lives under [`docs/settings-capability-registry/`](settings-capability-registry/). `scripts/validate_settings_parity.py` validates that registry statically on every normal `Validate` run and, in the firmware gate, compares it against the fully reconstructed browser mutation surface and physical `smart_hub.cpp` evidence.

## Classification contract

Every writable browser setting applicable to WS350 must be classified as exactly one of:

- **PHYSICAL** — directly editable on the WS350 normal settings surfaces.
- **PHYSICAL-EXPERT** — directly editable on a deeper physical expert surface, or explicitly planned there with a reason and release target.
- **PORTAL-INPUT** — intentionally remains in the local portal because it requires free text, secrets, URLs, or keyboard-quality input.
- **BOARD-N/A** — not applicable to the WS350 hardware/build shape.

`PHYSICAL-NEXT` is retired. CI now requires source evidence for both implemented **PHYSICAL** and implemented **PHYSICAL-EXPERT** claims.

## What CI enforces

The parity validator fails when:

1. a browser POST mutation route appears without classification as a settings route or documented non-setting command/auth/recovery route;
2. a writable field appears or disappears from a tracked settings route without a registry update;
3. a logical setting has an invalid or duplicate classification/binding;
4. an implemented physical or physical-expert setting lacks implementation evidence in reconstructed `smart_hub.cpp`;
5. an unimplemented physical-expert setting lacks an explicit reason and planned release;
6. a portal-input or board-not-applicable entry violates its boundary.

The reconstructed-source check accepts Workshop OS v11.20 and later so the same registry contract advances with new candidate layers.

## Existing PHYSICAL surfaces

### Display

- Main Brightness
- Standby Brightness
- Night Mode
- Night Brightness / Start / End
- Finish Timeout
- After Print behavior
- Door Ack
- Keep Print Screen
- Finish Timestamp
- ETA / Remaining / Both time display
- Animated Progress
- Small Labels
- Fan Display precision
- Status Readout
- Pong Clock
- Clock time/date size
- Date visibility

### Alerts, locale, and network essentials

- HMS / alert controls exposed by Alerts and Signals
- 12/24-hour time
- date format
- Show IP at startup
- mDNS enable/disable

### Audio / LED / power

- Event sounds
- Button clicks
- Quiet start/end
- Bed cooldown alert + threshold
- LED enable/brightness
- Finish LED effect/duration/brightness
- printing/pause/error LED behavior
- Plug Enabled
- Poll Interval
- Status Display
- Button Power
- Auto Off
- Auto Off Delay
- Cancel On Door

### Workshop / printer operation

- Ambient mode
- timer presets and timer actions
- Chamber Light command
- guarded Pause / Resume
- hold-to-confirm Stop
- guarded mapped smart-plug Printer Power

Printer commands remain fail-closed and selected-printer scoped. Unproven speed/fan/temperature/AMS payloads remain intentionally absent.

## v11.22 Display Expert RC1

The v11.22 candidate implements the previously planned display-expert family as seven additional physical pages under **Display**. The capture catalog expands from **22 to 29 deterministic views**.

### Theme

- curated palettes: Factory, Workshop, Ocean, Mono;
- independent curated clock time color;
- independent curated clock date color;
- one-tap factory palette reset.

Theme presets mutate only already-authoritative user-configurable theme fields. Alarm semantics remain fixed: ERROR red, PAUSED/CANCELED yellow, and other safety-state colors are not converted into theme choices.

### Gauge Colors

- select any of the 12 existing gauge color groups;
- edit arc color;
- edit label color;
- edit value color;
- long press moves backward through the curated palette.

### Gauge Scales

- nozzle: 100–400 °C presets;
- bed: 40–150 °C presets;
- chamber: 30–120 °C presets;
- power: 100–5000 W presets.

These use the existing persisted scale fields and remain within the upstream-supported ranges.

### Gauge Behavior

- smoothing: Off / Slow / Normal / Fast;
- warning threshold: Off or 50–100% presets;
- warning color: curated palette;
- restore gauge behavior defaults.

### Edge Glow

- mode: Off / Single / Rainbow;
- style: Sweep / Pulse / Storm;
- duration: Burst / Until Dismissed / Reminder;
- single-color accent selection.

### Layout

- 8-slot landscape mode;
- 9-slot portrait mode;
- split view;
- force split.

### Extras

- Clock Info toggle;
- AMS Tray Types toggle;
- explicit read-only reminder that Gauge Labels remain **PORTAL-INPUT**;
- explicit read-only reminder that Display Rotation is deferred to **v11.23**.

## Intentional v11.22 boundaries

- **Gauge labels stay PORTAL-INPUT.** They are arbitrary UTF-8 free text and there is no on-device keyboard.
- **Display rotation stays unimplemented physically until v11.23.** Rotation changes touch mapping and needs a guarded remap/rollback flow.
- **Wi-Fi credentials and hostname remain PORTAL-INPUT.**
- **No printer command family is added.** Speed/fan/temperature/AMS command payloads remain absent unless independently evidenced and safety-reviewed.
- v11.22 is a hardware-facing UI/settings change, so green CI does **not** make it physically accepted.

## v11.23 — Network / Locale / Layout Expert

Planned physical-expert work:

- timezone;
- coordinated DHCP/static mode;
- IP / gateway / subnet / DNS segmented entry;
- guarded display rotation;
- printer rotation policy and deeper network diagnostics.

Wi-Fi credentials and hostname remain **PORTAL-INPUT**.

## v11.24 — Printer / Workshop / Power Configuration

Planned physical-expert work:

- light start/finish/failure automation and off delay;
- printer connection mode and region;
- PSRAM multi-printer expert enablement;
- custom dashboard enable/refresh/return behavior;
- plug type/outlet;
- power tariff/currency.

Printer name/IP/serial/access credentials, custom dashboard URL, Workshop note, and plug IP/hostname remain **PORTAL-INPUT**.

## v11.25 — Hardware Expert

Planned capability-gated work:

- buzzer pin/wiring controls;
- battery/PMIC presentation tied to AXP2101 work;
- LED driver, pins, common-anode mode and state colors.

Incorrect wiring values can make hardware appear broken, so these stay below normal operational surfaces.

## BOARD-N/A on WS350

The registry explicitly marks incompatible browser settings rather than merely hiding them:

- CYD / round-panel settings such as inversion/classic/round-skin controls;
- low-RAM dual-printer toggle;
- configurable GPIO button wiring (FT6336 touch is forced on for WS350);
- low-RAM one-plug `assignedSlot` mapping. Full-RAM WS350 uses the existing same-slot `visiblePlugForSlot()` mapping.

## Recovery / OTA

Recovery actions are physically reachable. Firmware upload remains a portal/file-transfer operation; the touchscreen should inspect/select/check/reboot/rollback/recover, not pretend to provide a file picker it cannot support.

## Non-negotiable contracts

1. Existing settings objects remain authoritative; no touchscreen-only shadow settings model.
2. Physical mutations persist through the existing save authority.
3. Selected-printer commands remain fail-closed and printer-scoped.
4. Destructive actions require deliberate confirmation/hold semantics.
5. Board-specific settings are capability-gated, not merely visually hidden.
6. `ws_lcd_350` and shared `jc3248w535` regression builds remain firmware gates.
7. New writable browser settings must update the capability registry in the same change.
8. Real-device acceptance remains mandatory whenever touch, display, audio, recovery, authentication, or control behavior changes.
