# Physical Settings Parity

This document is the implementation contract for moving BambuHelper / Workshop OS configuration onto the WS350 touchscreen without turning the normal Home / Printer / Workshop surfaces into an expert settings form.

## Principle

A writable browser setting should end in one of four states:

- **PHYSICAL** — directly editable on the WS350 with a touch-appropriate control.
- **PHYSICAL-EXPERT** — directly editable on a deeper on-device expert page because it is low-frequency, layout-specific, or visually dense.
- **PORTAL-INPUT** — the device can launch/route to the local portal because the value requires substantial free text, secrets, URLs, or a full keyboard.
- **BOARD-N/A** — the setting is not applicable to WS350 hardware and must not be surfaced as though it were.

No setting should remain accidentally browser-only. Any intentional portal boundary must be explicit here.

## Display & power

| Browser field / authority | Physical status | Surface |
| --- | --- | --- |
| `brightness` / `bright` | PHYSICAL | Display → Quick → Main Brightness |
| `dpSettings.screensaverBrightness` / `ssbright` | PHYSICAL | Display → Quick → Standby Brightness |
| `dpSettings.nightModeEnabled` / `nighten` | PHYSICAL | Display → Quick → Night Mode |
| `dpSettings.keepDisplayOn` + `showClockAfterFinish` | PHYSICAL | Display → Quick → After Print |
| `dpSettings.nightBrightness` / `nbright` | PHYSICAL | Display → Schedule → Night Brightness |
| `dpSettings.nightStartHour` / `nstart` | PHYSICAL | Display → Schedule → Night Start |
| `dpSettings.nightEndHour` / `nend` | PHYSICAL | Display → Schedule → Night End |
| `dpSettings.finishDisplayMins` / `fmins` | PHYSICAL | Display → Schedule → Finish Timeout |
| `dpSettings.doorAckEnabled` / `dack` | PHYSICAL | Display → Behavior → Door Ack |
| `dpSettings.keepPrintScreen` / `kps` | PHYSICAL | Display → Behavior → Keep Print Screen |
| `dpSettings.finishShowTime` / `fintm` | PHYSICAL | Display → Behavior → Finish Timestamp |
| `dispSettings.timeDisplayMode` / `timem` | PHYSICAL | Display → Behavior → Time Display |
| `dispSettings.animatedBar` / `abar` | PHYSICAL-NEXT | Display → Visual |
| `dispSettings.smallLabels` / `slbl` | PHYSICAL-NEXT | Display → Visual |
| `dispSettings.fanMatchPrinter` / `fanmp` | PHYSICAL-NEXT | Display → Visual |
| `dispSettings.hideStatusReadout` / `hidelp` | PHYSICAL-NEXT | Display → Visual |
| `dispSettings.pongClock` / `pong` | PHYSICAL-NEXT | Display → Clock |
| `dispSettings.clockTimeSize` / `clk_size` | PHYSICAL-NEXT | Display → Clock |
| `dispSettings.clockDateSize` / `clk_dsize` | PHYSICAL-NEXT | Display → Clock |
| `dispSettings.hideClockDate` / `clk_hidedate` / `clkhd` | PHYSICAL-NEXT | Display → Clock |
| `dispSettings.showClockInfo` / `clkinfo` | PHYSICAL-NEXT | Display → Clock |
| `netSettings.use24h` / `use24h` | PHYSICAL-NEXT | Display → Clock |
| `netSettings.dateFormat` / `datefmt` | PHYSICAL-NEXT | Display → Clock |
| timezone / `tz` | PHYSICAL-EXPERT | Device → Time & Locale |
| display rotation / `rotation` | PHYSICAL-EXPERT | Display → Layout; guarded because touch mapping changes with it |

## Visual theme and gauge rendering

The browser exposes many direct RGB565 color fields. These are valid physical settings, but a raw color picker is not appropriate for the primary touchscreen flow.

### Theme colors — PHYSICAL-EXPERT

- Background: `clr_bg`
- Track: `clr_track`
- Progress: `clr_pbar`
- ETA: `clr_eta`
- Finish: `clr_fin`
- Status OK: `clr_stok`
- Printer name: `clr_pname`
- Text: `clr_txt`
- Dim text: `clr_txtd`
- Door closed/open: `clr_dorc`, `clr_doro`
- Clock time/date: `clk_time`, `clk_date`
- Warning color: `warn_clr`
- Glow color: `glow_clr`

Physical implementation target: curated palettes first, with an Expert color editor only if the panel interaction remains usable. Every mutation continues through the existing `dispSettings` + `saveSettings()` authority.

### Gauge behavior — PHYSICAL-EXPERT

- Nozzle scale max: `noz_max`
- Bed scale max: `bed_max`
- Chamber scale max: `cht_max`
- Power scale max: `pwr_max`
- Gauge smoothing: `gsmooth`
- Warning threshold: `warn_thr`
- Glow mode/style/duration: `glowm`, `glows`, `glowd`
- Extended WS350/portrait slot modes where applicable
- AMS tray type display where applicable

Custom gauge labels are text-input values and therefore fall under **PORTAL-INPUT** unless an on-device keyboard is intentionally added.

## HMS / alert presentation — PHYSICAL-NEXT

- HMS enabled: `hmsen`
- All severity levels: `hmssev`
- Auto-present behavior: `hmsauto`
- Alert mask: `hmsmask`
- Online lookup: `hmsonl`

Target: Device → Alerts, with large toggles and bounded enum selectors.

## Printer controls already physical

- Chamber light — guarded, fail-closed.
- Pause / Resume — selected-printer scoped and revalidated.
- Stop — hold-to-confirm on the dedicated Printer surface.
- Mapped smart-plug Printer Power — guarded confirmation, stronger active-print warning.

Unproven speed/fan MQTT payloads remain intentionally absent until the pinned backend provides an evidence-backed command path.

## Workshop / local device controls already physical

- Timer presets and cancellation/dismissal.
- Ambient mode.
- Speaker test.
- MIC ECHO.
- System health / recovery entry.
- Network state visibility.
- Custom dashboard widget editing by long-press.

## Network and identity

| Setting type | Status | Reason / target |
| --- | --- | --- |
| DHCP/static mode, IP, gateway, subnet, DNS | PHYSICAL-EXPERT | Device → Network → Advanced; numeric segmented entry is feasible |
| Hostname | PORTAL-INPUT | Free text |
| Wi-Fi SSID/password | PORTAL-INPUT | Secret/free-text entry; local captive portal remains the safer input surface |
| mDNS toggle | PHYSICAL-NEXT | Device → Network |
| Show IP at startup | PHYSICAL-NEXT | Device → Network |
| Wi-Fi TX workaround / board radio flags | PHYSICAL-EXPERT | Diagnostics only |

## Audio / buzzer / status LED

### PHYSICAL-NEXT

- Buzzer enabled
- Button click
- Quiet-hours start/end
- Bed cooldown alert + threshold
- Status LED enabled
- LED brightness
- Finish effect/mode/duration
- State-driven LED behaviors

Pin numbers, RGB driver wiring, common-anode mode and other wiring topology settings are **PHYSICAL-EXPERT** because an incorrect value can make hardware appear broken.

## Smart plug configuration

Power execution is already physical. Plug discovery/configuration and printer-to-plug mapping remain **PHYSICAL-EXPERT** targets. IP/host values that require free text may route through **PORTAL-INPUT**, but mapping, outlet selection, auto-off, delay, and cancel-on-door are suitable for device editing.

## Recovery / OTA

Recovery actions are already directly reachable from the physical OS. Firmware upload itself remains a portal/file-transfer operation; the touchscreen should select/check/reboot/rollback/recover, not pretend to provide a file picker it cannot support.

## Board-specific controls

The browser includes controls for CYD, round panels and other display families (`invcol`, `cydcls`, `cyd32e`, `rskin`, etc.). On WS350 these are **BOARD-N/A** and must remain hidden. Shared-build regression must continue proving that WS350 evolution does not break those targets.

## Release progression

- **v11.8** — Display Quick page.
- **v11.9** — Display Schedule page.
- **v11.10** — Display Behavior page.
- **Next** — Display Visual + Clock pages.
- **Then** — HMS/Alerts, Network toggles/advanced numeric settings, Audio/LED, smart-plug configuration/mapping.
- **Final parity pass** — compare all browser mutation keys/routes against this matrix and fail CI if an applicable writable setting is neither PHYSICAL, PHYSICAL-EXPERT, PORTAL-INPUT, nor BOARD-N/A.

## Non-negotiable contracts

1. Existing settings objects remain authoritative; do not create a second touchscreen-only settings model.
2. Every physical mutation persists through the existing save path.
3. Selected-printer commands remain fail-closed and printer-scoped.
4. Destructive actions require deliberate confirmation/hold semantics.
5. Board-specific settings are capability-gated, not merely visually hidden.
6. Both `ws_lcd_350` and the shared `jc3248w535` regression build remain release gates.
7. Physical acceptance is required before promotion to `main`.
