# Workshop OS v11.30 — Unified Web + Companion RC1

## Purpose

v11.30 makes the two browser surfaces feel like parts of one Workshop OS instead of separate utilities:

- the full Workshop OS portal remains the deep control/configuration surface;
- Companion remains the fast, phone-first operational surface;
- both expose the same live state vocabulary and obvious handoffs between them.

This candidate is stacked on v11.29 Acceptance Open LAN and inherits its temporary WS350-only no-portal-code policy for physical acceptance.

## Full Workshop OS improvements

### Persistent live status rail

The standard portal gains a compact live rail sourced from `/companion/state` with:

- workshop freshness / reconnect state;
- printer state, progress and active job;
- mapped printer power state and watts;
- Companion presence / photo-ready state;
- device Wi-Fi RSSI and stale-state warning.

The rail is intentionally supplemental. Existing section-specific status APIs remain authoritative for the controls already on those pages.

### Attention model

The standard portal surfaces only a small set of deterministic issues:

- stale Workshop OS state;
- configured printer offline;
- active print while mapped power reports off;
- very weak Wi-Fi RSSI.

It does not invent printer faults or infer safety conditions from missing telemetry.

### Navigation and mobile ergonomics

Desktop/tablet gains direct actions for:

- Home;
- Workshop;
- Open Companion;
- Updates.

Phone-sized layouts gain a fixed four-target bottom dock:

- Home;
- Printer;
- Companion;
- More / Workshop.

The Companion handoff is a real `/companion` link rather than another nested configuration section.

### OTA coexistence

The supplemental `/companion/state` poll runs approximately every 3.2 seconds while visible and every 7 seconds while hidden.

When OTA starts, the v11.30 poll explicitly pauses before the firmware XHR begins. On failed uploads it resumes from `loadend`. A successful upload remains quiet while the device reboots. This preserves the single-long-running-connection assumptions already built into the OTA path.

## Companion improvements

### Attention summary

Companion gains a compact, deterministic status summary at the top of the page. It reports:

- reconnecting / stale state;
- Waveshare online but printer offline;
- print paused;
- print in progress with percent and remaining time;
- workshop ready.

The summary is derived from the existing Companion DOM, which is already updated by the one-second authenticated state loop. v11.30 does **not** add a second Companion state poll.

### Jump navigation

A sticky phone-friendly navigation strip jumps directly to:

1. Overview
2. Controls
3. Photo
4. System

This keeps the page useful one-handed without turning it into a second copy of the full portal.

### Visual refinement

- stronger sticky header hierarchy;
- larger action targets;
- improved section scroll offsets;
- better photo preview height;
- compact mini status cells for Printer / Power / Photo;
- clearer Workshop Companion branding.

## Inherited v11.28 photo behavior

v11.30 preserves the full Physical Companion Viewer contract:

- upload JPEG to volatile PSRAM;
- upload alone never changes the physical screen;
- explicit **Show on Waveshare** action;
- contain-fit render through the fullscreen JPEG surface;
- normal chamber-camera fallback when phone viewer is inactive;
- tap physical screen to exit;
- no flash persistence.

## Inherited v11.29 acceptance security boundary

On the WS350 acceptance build:

- normal-LAN portal code remains disabled by default;
- normal-LAN browser reads are open;
- browser mutations still require same-origin provenance;
- header-only mutation provenance remains disabled;
- `/settings/export` and `/debug` remain blocked;
- AP/recovery scoping remains intact;
- legacy portal-code implementation remains present for later re-enable, with the Safari format bug fixed.

## Physical acceptance additions for v11.30

In addition to the existing hardware acceptance matrix, verify:

- standard portal live rail remains current without visible layout overlap;
- standard portal works at iPhone width and desktop width;
- mobile dock targets are finger-sized and do not cover critical content;
- Companion link opens directly;
- Companion jump nav lands on the correct four sections;
- Companion Attention copy tracks printing / paused / offline transitions correctly;
- v11.30 supplemental full-web polling does not interfere with OTA;
- failed OTA resumes normal web status activity;
- successful OTA reboots and reconnects normally;
- photo upload / Show on Waveshare / tap-to-exit still work;
- normal chamber camera still returns after leaving phone-photo viewer.
