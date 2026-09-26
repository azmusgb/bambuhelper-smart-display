# Home Hub Architecture

## Purpose

Workshop OS should be framed as a **home/workshop command center**, not a printer companion with extra screens.

The device can retain all existing printer, workshop, hardware, media, automation, and system functionality, but the information architecture should stop treating the printer as the center of the product. The printer becomes one capability among several.

The Home Hub should answer a broader question:

> What is happening around me, what needs attention, and what can I control from here?

This document defines the intended product architecture only. No implementation work is included in this change.

## Product model

The device is a **local-first command center** for the workshop and home environment.

It should support several classes of capability:

- printer and fabrication status
- workshop utilities
- smart-home control
- environmental and weather information
- timers, clocks, reminders, and lightweight productivity
- media and audio
- local device control
- diagnostics and system administration
- standalone utility apps such as Sky Radar

The product should feel useful even when no printer is running.

## Home tile model

Home becomes a **glanceable dashboard of six primary tiles**.

Each tile is both:

1. a compact live summary, and
2. an entry point into a functional domain or app.

Tiles must remain simple. They are not miniature full applications.

### Tile anatomy

Each tile contains:

- icon
- short title
- one primary value or state
- optional secondary text
- optional attention indicator
- full-tile touch target

Shared tile states:

- **Normal** — available, nothing requires attention
- **Active** — something is currently happening
- **Attention** — user action may be useful
- **Unavailable** — dependency or hardware is unavailable
- **Unknown** — state cannot currently be resolved

Color is supplemental only. State must also be communicated with text or iconography.

## The six Home tiles

### 1. Now

A general-purpose glance tile for the current moment.

Examples:

- local time and date
- weather summary
- next calendar item
- timer/alarm state
- brief contextual status

This becomes the human-centered anchor of Home rather than Printer.

### 2. Home

Smart-home and room-level control.

Examples:

- smart plugs
- lights
- environmental sensors
- room temperature/humidity
- power state
- automation shortcuts

This domain should be protocol-agnostic where practical. Existing Tasmota support fits here rather than being treated only as printer power control.

### 3. Workshop

Workshop-wide status and utilities.

Examples:

- active equipment
- bench status
- material readiness
- filament inventory
- workshop timers
- maintenance reminders
- quick utility actions

Printer-specific functionality can be linked from here but should not define the entire domain.

### 4. Printer

The existing printer experience remains intact, but becomes one first-class app/domain among several.

The Home tile may summarize:

- printer readiness
- active job
- progress
- fault/attention state

Opening the tile enters the full printer experience.

### 5. Apps

A gateway to standalone utilities and expandable features.

Initial examples:

- Sky Radar
- Weather
- World Clock
- Timers
- Notes / message board
- media utilities
- future lightweight tools

Sky Radar should live here as a first-class app, not as a special case hidden under More.

### 6. System

Device-level and administrative functions.

Examples:

- Wi-Fi/network
- display
- audio
- LEDs
- device behavior
- software/runtime state
- diagnostics
- maintenance
- updates
- recovery

System owns the device itself. It should not become another catch-all for application features.

## Navigation restructure

The root navigation becomes:

```text
Home
├── Now
├── Home
├── Workshop
├── Printer
├── Apps
│   ├── Sky Radar
│   ├── Weather
│   ├── Timers
│   └── future apps
└── System
```

The six Home tiles are the primary entry points. The persistent navigation should be simplified around a small number of stable destinations rather than exposing every feature as a peer.

Recommended persistent navigation:

```text
Home · Apps · Workshop · System
```

Printer remains reachable directly from its Home tile and from Workshop. If hardware ergonomics or usage testing show that Printer deserves a persistent slot, it can replace Workshop in the nav without changing the domain architecture.

## More is transitional

**More should not survive as a permanent architectural category.**

Anything currently in More should be reassigned to one of:

- Home
- Workshop
- Printer
- Apps
- System

If More remains temporarily during migration, it exists only as a compatibility bridge and should receive no new features.

## Architecture rules

1. Printer is a domain, not the product shell.
2. Home must remain useful when the printer is idle or disconnected.
3. New features should first be classified as Home, Workshop, Printer, Apps, or System.
4. Standalone utilities belong in Apps rather than becoming new root-level categories.
5. Device configuration belongs in System.
6. Workshop capabilities may aggregate multiple devices and tools.
7. Home tiles summarize; detail screens interact.
8. Child screens must have deterministic navigation back to their parent and to Home.
9. No new feature should be added to More.
10. The architecture should support future integrations without forcing a navigation redesign.

## Design constraints

The command-center experience should be calmer and broader than the current printer-centric UI.

- six primary tiles on Home
- stable tile positions
- 44 px minimum touch targets
- readable at 480 × 320
- no horizontal root navigation
- no status conveyed by color alone
- clear focus/pressed/disabled states
- reduced-motion support
- strong offline/failure states
- local-first behavior where possible
- network services must degrade gracefully
- no dense telemetry on Home
- detail belongs on secondary screens

## Initial migration intent

The reframe should begin by changing architecture before adding more features.

Recommended sequence:

1. Replace the current printer-centered Home with the six-tile Home Hub shell.
2. Reclassify existing screens into Home, Workshop, Printer, Apps, or System.
3. Move Sky Radar into Apps.
4. Preserve the current Printer experience behind the Printer tile.
5. Retire More once all existing functions have clear homes.
6. Add one non-printer app to validate the new model before expanding further.

The first new app should ideally be something useful without the printer, such as Weather or Clock/Timers.

## Success criteria

The reframe is successful when:

- the device is useful with the printer powered off
- a new user can understand the product from the Home screen
- printer functionality is still easy to reach
- no feature depends on a generic More bucket
- new apps can be added without changing root navigation
- the interface feels like a command center rather than a printer accessory

---

**Decision:** Workshop OS evolves into a general home/workshop command center. Printer support remains a major capability, but it no longer defines the product architecture.
