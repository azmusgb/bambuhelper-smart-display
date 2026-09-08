# Workshop OS v11.25 RC4 — Physical Acceptance

This checklist applies to the RC4 Product Polish physical-test candidate. Automated build/test evidence does **not** satisfy this hardware gate.

## Candidate identity

Before testing, record:

- exact PR head SHA;
- Full-image SHA-256;
- OTA-image SHA-256;
- image actually flashed and flash method;
- WS350 hardware identity;
- date/time of test.

For a cross-line migration from Waveshare Home, use the approved **Full image at `0x0`**. OTA is only for a compatible Workshop OS partition layout.

## Immediate visual acceptance

RC4 must be unmistakably different from the rejected legacy/RC1 treatment:

- graphite surfaces with restrained mint interaction accent form one coherent product system;
- blue/info, green/success, amber/warning and red/destructive states are semantic rather than decorative;
- Home reads as an operational command center rather than a collection of generic cards;
- typography clearly separates section label, current state, key value, action and supporting detail;
- `Home / Printer / Workshop / More` is obvious at a glance;
- primary information remains legible at normal workshop viewing distance;
- no clipped, overlapping or edge-crowded content at 480×320;
- routine controls have clear visible boundaries and reliable finger-sized targets;
- selected, disabled, offline, warning, destructive and loading states are distinguishable without relying on color alone.

Reject RC4 if it still feels like a reskinned developer dashboard rather than a purpose-built workshop appliance UI.

## Home

Verify configured and unconfigured states plus idle, active-print, paused and offline conditions.

- printer state and printer name dominate appropriately;
- active job progress and time/layer summary are readable while printing;
- material and network are secondary to printer state;
- Workshop Status/attention is separate from printer telemetry;
- printer-reported material does not imply Filament Inventory identity;
- temporary access state is explicitly visible as `NO CODE / TEST BUILD ONLY`;
- visible Home cards match their touch zones; there are no invisible routine targets.

## Printer

### Status

- `Status / AMS / Control` segmented navigation is obvious and one-tap;
- active segment is clear without relying on accent color alone;
- job/status card and live telemetry are structurally distinct;
- nozzle, bed, chamber and fan values are easy to scan;
- disconnected, paused, failed and attention states remain unambiguous;
- unknown/unreported telemetry never displays as a fabricated value.

### AMS

- four slot surfaces fit without crowding or clipped text;
- active slot is distinguishable by structure/border, not filament color alone;
- printer-reported slot, remaining percentage, material and color are readable;
- `INVENTORY IDENTITY / Unknown` is explicit when no authoritative inventory link exists;
- the explanatory text makes clear that printer telemetry does not infer spool identity;
- no physical spool placement is invented from matching color/material.

### Control

- Light, Pause/Resume, mapped Printer Power and Stop are immediately understandable;
- enabled and disabled states are visually different;
- Pause becomes Resume when appropriate;
- Stop requires deliberate hold, shows hold progress, and cannot fire on a normal tap;
- mapped printer power retains its existing guard/warning behavior;
- no routine navigation or ordinary command depends on a hidden hold gesture.

## Workshop

- timer hierarchy is immediately readable;
- timer ready/running/done states are distinct;
- note content is legible without competing with the timer;
- Material Path preserves `Unknown` inventory identity unless authoritative data exists;
- Light / Tools / System / Printer actions are reliably tappable;
- no action is presented as enabled when its underlying capability/state is unavailable.

## More / System

- More exposes only high-level destinations and avoids a dense settings wall;
- Custom / System / Display / Tools have clear differentiation;
- System separates device health, audio, network and temporary access state;
- Wi-Fi/offline state is readable;
- speaker test, mic echo and event sound controls work;
- recovery availability remains visible and functional.

## Existing expert-flow regression

Re-run the v11.23 Network / Locale / Layout acceptance paths:

- explicit Back / Next / Cancel behavior;
- timezone selection;
- DHCP/static staging;
- IPv4 editing;
- review/discard;
- guarded Apply + Restart;
- display rotation preview and guarded commit.

RC4 polish must not reintroduce hidden navigation gestures or reduce touch-target reliability in these inherited flows.

## Portal UI / UX / CSS

Test the local portal on desktop, tablet and phone widths.

- shell, top bar, side navigation and selected state form a clear hierarchy;
- graphite/mint dark mode is visually coherent and light mode remains fully usable;
- cards are flatter and quieter than RC3; decorative shadows/gradients do not dominate;
- forms and buttons are visually consistent;
- coarse-pointer controls are at least 48 px high where the CSS contract applies;
- Workshop command center, telemetry, progress and material cards remain readable at narrow widths;
- keyboard `:focus-visible` treatment is obvious;
- reduced-motion preference removes nonessential transitions/animation;
- forced-colors mode preserves visible focus/state boundaries;
- there is no horizontal overflow or clipped primary content at supported phone widths.

## Temporary no-code test boundary

For this RC4 physical-test build only:

- station-mode portal opens without entering the boot/device code;
- mutating actions still obey same-origin protection;
- AP/setup/recovery behavior remains available;
- the device and portal make the test-only open-access state visible.

**Promotion blocker:** `WORKSHOP_OS_TEMP_NO_CODE_LAN` must be removed and a secure candidate rebuilt and retested before acceptance or stable promotion.

## Control, persistence and recovery regression

Verify on the real device:

- chamber light ON/OFF;
- Pause -> Resume;
- guarded Stop;
- mapped smart-plug power ON/OFF and active-print warning;
- timers/tools;
- speaker test;
- MIC ECHO;
- event sounds;
- ambient/standby behavior;
- settings survive reboot;
- Wi-Fi reconnect;
- printer configuration survives reboot;
- OTA upgrade from a compatible Workshop OS line;
- approved full-image recovery path remains functional;
- known-good rollback procedure/artifact remains available.

## Exit gate

Do not mark RC4 `physically validated`, `accepted`, or `stable` until all applicable real-device checks pass and the exact candidate SHA/artifact hashes are recorded. Even after the visual/physical UX passes, remove the temporary no-code mode and rebuild/retest the secure candidate before promotion.
