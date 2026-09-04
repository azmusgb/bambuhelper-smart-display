# Physical Settings Parity

This document is the human-readable contract for moving BambuHelper / Workshop OS configuration onto the WS350 touchscreen without turning the normal Home / Printer / Workshop surfaces into an expert settings form.

The **machine-authoritative inventory** now lives under [`docs/settings-capability-registry/`](settings-capability-registry/). `scripts/validate_settings_parity.py` validates that registry statically on every normal `Validate` run and, in the firmware gate, compares it against the fully reconstructed v11.20 `web_server.cpp` mutation surface and physical `smart_hub.cpp` evidence.

## Classification contract

Every writable browser setting applicable to WS350 must be classified as exactly one of:

- **PHYSICAL** — directly editable on the WS350 today.
- **PHYSICAL-EXPERT** — applicable to WS350 and assigned to a deeper physical expert surface; an unimplemented entry must have a planned release and explicit reason.
- **PORTAL-INPUT** — intentionally remains in the local portal because it requires free text, secrets, URLs, or a keyboard-quality input experience.
- **BOARD-N/A** — not applicable to WS350 hardware/build shape and must not be surfaced as though it were.

The old `PHYSICAL-NEXT` state is retired. Future work is represented explicitly as `PHYSICAL-EXPERT` + `implementedOnDevice=false` + `plannedRelease`.

## What CI now enforces

The v11.21 parity validator fails when:

1. a browser POST mutation route appears without being classified as a settings route or explicitly documented non-setting command/auth/recovery route;
2. a writable field appears or disappears from a tracked settings route without a registry update;
3. a logical setting has an invalid or duplicate classification/binding;
4. `PHYSICAL` is claimed without physical implementation evidence in reconstructed `smart_hub.cpp`;
5. `PHYSICAL-EXPERT`, `PORTAL-INPUT`, or `BOARD-N/A` lacks the required planning/reason evidence.

This turns parity from a prose checklist into a regression contract.

## Already PHYSICAL on WS350

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

- HMS / alert controls exposed by the Alerts and Signals pages
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

## v11.22 — Display Expert

Planned `PHYSICAL-EXPERT` work:

- curated theme palettes and clock colors;
- gauge colors;
- gauge full-scale values;
- gauge smoothing and warning threshold/color;
- glow mode/style/duration/color;
- gauge layout / extended slot modes;
- clock-info toggle;
- AMS tray-type presentation.

Custom gauge labels remain **PORTAL-INPUT** because they are free text.

## v11.23 — Network / Locale / Layout Expert

Planned `PHYSICAL-EXPERT` work:

- timezone;
- coordinated DHCP/static mode;
- IP / gateway / subnet / DNS segmented entry;
- guarded display rotation;
- printer rotation/split policy.

Wi-Fi credentials and hostname remain **PORTAL-INPUT**.

## v11.24 — Printer / Workshop / Power Configuration

Planned `PHYSICAL-EXPERT` work:

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
