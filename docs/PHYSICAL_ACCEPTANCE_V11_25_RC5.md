# Workshop OS v11.25 RC5 — Physical UI Acceptance

Automated CI may establish `implemented -> built -> tested`. It does not establish
physical validation or acceptance.

## Candidate identity

Record before testing:

- exact PR head SHA;
- Full BIN SHA-256;
- OTA BIN SHA-256;
- image actually flashed and flash method;
- WS350 hardware identity;
- date/time.

For a Waveshare Home cross-line migration, use the Full image at `0x0`. OTA is
only valid on a compatible Workshop OS partition layout.

## Renderer proof — mandatory first check

Every primary screen must visibly show its RC5 fingerprint:

- Home `UI5-H`
- Printer `UI5-P`
- Workshop `UI5-W`
- More `UI5-M`
- System `UI5-S`

If a screen does not show the expected fingerprint, stop acceptance and treat it
as a runtime routing/renderer defect. Do not iterate styling until the active
renderer is resolved.

## Home

- printer state is the dominant information (`PRINTING`, `PAUSED`, `READY`,
  `OFFLINE`, or `NO PRINTER`);
- current job/progress appears only when evidence exists;
- material and network remain secondary;
- attention state is distinct from printer telemetry;
- `NEXT` gives an obvious destination without inventing printer capability;
- inventory remains `Unknown` unless authoritative linkage exists;
- visible cards and touch zones align;
- no primary label/value is clipped at 480x320.

## Printer

### Status

- `STATUS / AMS / CONTROL` is obvious and finger-sized;
- printer state outranks telemetry visually;
- active job, percent, remaining time and layer data are legible;
- nozzle/bed/chamber/fan are grouped as secondary telemetry;
- offline/unavailable data does not become fabricated values.

### AMS

- all four bays fit cleanly;
- active bay is indicated structurally, not by filament color alone;
- printer-reported material/color/remain are readable;
- inventory identity remains `Unknown` without an authoritative contract;
- no spool identity is inferred from color/material similarity.

### Control

- Light, Pause/Resume, mapped Power and Stop are explicit;
- disabled actions look disabled;
- Stop does not fire on a normal tap;
- Stop hold-progress is visible and deliberate;
- mapped power retains its active-print warning/guard behavior.

## Workshop

- timer is the primary hierarchy;
- Ready / Running / Done states are clear;
- note remains secondary;
- material is concise and explicitly separates printer telemetry from inventory;
- Light / Tools / System / Printer actions are reliably tappable.

## More / System

- More is a launcher, not a settings wall;
- Dashboard / System / Display / Tools are visually differentiated;
- System separates Device Health, Audio, Network and Access;
- network/touch/recovery health are visible;
- speaker, mic echo and event controls still work;
- no-code test state is visibly identified in this physical-test candidate.

## Touch and interaction

- routine targets are at least 48 px;
- primary targets feel closer to 52-64 px where layout permits;
- no hidden long-press is required for routine navigation;
- destructive holds are deliberate and show progress;
- visible pressed/feedback state appears promptly;
- small finger drift does not select an adjacent control.

## Automated framebuffer capture

Run:

```text
scripts/capture-ws350-ui5.zsh <device-ip>
```

Review every generated PNG. The capture must:

- be 480x320;
- not be blank or obviously stale;
- show the expected UI5 fingerprint;
- have no clipping/overlap;
- retain readable hierarchy at normal viewing distance;
- preserve semantic success/warning/error/destructive distinctions.

## Portal UI

Test desktop and phone widths:

- clear navigation/selected state;
- consistent 48 px coarse-pointer controls;
- no horizontal overflow;
- keyboard focus is visible;
- reduced-motion does not remove state communication;
- forced-colors retains boundaries/focus;
- Workshop command center remains readable and operational.

## Temporary no-code boundary

For this test build only:

- station-mode portal opens without the boot/device code;
- explicitly opening `/login` does not leave the user on a code form;
- mutating requests still require same-origin provenance;
- AP/setup/recovery behavior remains available.

`WORKSHOP_OS_TEMP_NO_CODE_LAN` is a promotion blocker.

## Exit gate

Do not mark RC5 `physically validated` until the full real-device checklist has
been run and passed against the exact artifact hash.

Even after UI acceptance, do not mark the no-code artifact `accepted` or `stable`.
Remove the temporary bypass, rebuild/retest the secure candidate, and physically
validate that secure build first.
