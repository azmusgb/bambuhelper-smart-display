# Workshop OS v11.25 RC3 — Physical Acceptance

This checklist applies to the premium RC3 physical-test candidate. Automated build/test evidence does not satisfy this gate.

## Immediate visual acceptance

On first boot, verify that RC3 is unmistakably different from the previously rejected RC1 treatment:

- compact Workshop header and restrained orange accent are visible;
- Home reads as a command center, not a collection of legacy rounded cards;
- bottom navigation clearly shows `Home / Printer / Workshop / More` with a strong active state;
- typography hierarchy is readable at normal viewing distance;
- no important label/value is clipped at 480×320;
- no primary surface appears visually crowded or ambiguous.

## Home

- printer state and printer name are obvious;
- active job, progress and time/layer summary are readable when printing;
- next action is visually separate from printer state;
- material data is clearly printer telemetry and does not imply inventory identity;
- temporary local access state reads `OPEN / TEST` in this test artifact;
- touch zones map to the visible surfaces.

## Printer

### Status
- `Status / AMS / Control` segmented navigation is obvious and finger-sized;
- job card and live telemetry are visually distinct;
- nozzle, bed, chamber and fan metrics are readable without hunting;
- disconnected/paused/error states remain clear.

### AMS
- all four visible slots fit cleanly;
- active slot is distinguishable without relying on color alone;
- material/color/remain are readable;
- `Inventory ID: Unknown` is explicit when no authoritative inventory link exists;
- no spool identity is inferred from printer color/material.

### Control
- Light, Pause/Resume, Printer Power and Stop are obvious;
- disabled controls look disabled;
- Stop still requires deliberate hold and displays hold progress;
- mapped power remains separately guarded;
- no routine navigation requires hidden long-press behavior.

## Workshop / More / System

- Workshop timer, note and material path are easy to scan;
- Workshop quick actions are at least 48 px and reliably tappable;
- More exposes only high-level destinations and avoids dense settings presentation;
- System health, audio/events, network and access status are visually separated;
- speaker test, mic echo and events controls still work;
- recovery status remains visible.

## Portal CSS / browser UX

From a phone and a desktop browser on the local network:

- portal shell, top bar and navigation render correctly;
- selected navigation state is obvious;
- buttons and form controls have large consistent hit areas;
- Workshop status/progress/material cards read clearly;
- responsive layout does not overflow at narrow widths;
- focus-visible treatment is present with keyboard navigation;
- reduced-motion preference does not rely on animation for state communication.

## Temporary no-code test boundary

For this RC3 physical-test build only:

- station-mode portal opens without entering the boot/device code;
- mutating actions still obey same-origin protection;
- AP/setup/recovery behavior remains available;
- the UI clearly indicates this is an open/test access state.

**Promotion blocker:** `WORKSHOP_OS_TEMP_NO_CODE_LAN` must be removed and the secure candidate rebuilt/retested before acceptance or stable promotion.

## Required control and recovery regression

- chamber light ON/OFF;
- Pause -> Resume;
- guarded Stop;
- mapped smart-plug power ON/OFF and active-print warning;
- timers/tools;
- settings survive reboot;
- Wi-Fi reconnect;
- printer configuration survives reboot;
- OTA from a compatible Workshop OS line;
- approved recovery/full-image path remains functional.

## Acceptance record

Record exact candidate SHA, firmware artifact hash, flash method, device result, any defects, and final disposition. Do not mark `physically validated`, `accepted`, or `stable` until the corresponding real-device checks pass.
