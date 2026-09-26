# Home Hub Architecture

## Purpose

Workshop OS is a **home/workshop command center**, not a printer companion with extra screens.

The device keeps its existing printer, workshop, hardware, media, automation, and system capabilities, but the product shell no longer treats the printer as the center of the experience. Printer becomes one major domain among several.

The Home Hub should answer:

> What is happening around me, what needs attention, and what can I control from here?

This document defines the product and navigation architecture. It intentionally does not define implementation code.

## Product model

The device is a **local-first command center** for the home and workshop.

It should remain useful when:

- the printer is idle
- the printer is powered off
- no printer has been configured
- the network is unavailable
- optional smart-home devices are not configured

The product can support:

- printer and fabrication status
- workshop utilities
- smart-home control
- environmental and weather information
- clocks, timers, reminders, and lightweight productivity
- media and audio
- local device control
- diagnostics and system administration
- standalone utilities such as Sky Radar

## Physical-use assumption

The primary design target is a **480 × 320 touchscreen viewed at arm's length on a desk, counter, shelf, or workshop surface**.

The interface must therefore favor:

- glanceability over density
- large, stable touch targets
- short labels
- strong state hierarchy
- useful local/offline behavior
- minimal navigation depth for frequent tasks

The shell must not assume that the device lives directly beside a printer.

## Home tile model

Home is a glanceable dashboard of **six stable tiles** arranged in a 3-column × 2-row grid.

The six tiles are:

1. Now
2. Smart Home
3. Workshop
4. Printer
5. Apps
6. System

Each tile is both:

1. a compact summary, and
2. a one-tap entry point.

### Tile anatomy

The 480 × 320 geometry constrains each tile to roughly **149 × 112 px** once the header, bottom navigation, outer margins, and gutters are reserved.

Therefore a tile may contain only:

- icon
- short title
- one primary value/state
- **one** compact supporting line when useful

Attention state must be integrated into the icon, title, or supporting line. It must not add a separate badge plus separate status text.

Tiles are not miniature dashboards.

### Shared tile states

- **Normal** — available; no intervention required
- **Active** — meaningful work is in progress
- **Attention** — user action may be useful
- **Unavailable** — a dependency cannot currently be reached
- **Setup** — the capability exists but has not been configured
- **Unknown** — state cannot currently be resolved

Color is supplemental. Text or iconography must communicate the same state.

## The six Home tiles

### 1. Now

**Primary purpose:** orient the user to the current moment.

Default content:

- primary: local time
- supporting line: date or cached weather summary

If a timer, alarm, or urgent local condition is active, it may temporarily replace the supporting line.

Now must not become a new catch-all status tile.

### 2. Smart Home

**Primary purpose:** room- and home-level control.

Examples:

- smart plugs
- lights
- environmental sensors
- room temperature/humidity
- power state
- automation shortcuts

Existing Tasmota support belongs here when it controls home/workshop devices. Printer-specific power behavior can still be exposed in Printer where context requires it.

### 3. Workshop

**Primary purpose:** workshop-wide operational state and utilities.

Examples:

- active equipment
- bench status
- material readiness
- filament inventory
- workshop timers
- maintenance reminders
- quick utility actions

Printer functionality may be linked from Workshop, but Workshop is not a synonym for Printer.

### 4. Printer

**Primary purpose:** preserve the complete printer experience as one major domain.

Home summary may show:

- printer readiness
- active job
- progress
- attention/fault state

Opening the tile enters the existing printer experience.

### 5. Apps

**Primary purpose:** launch built-in standalone utilities that do not belong to a larger operational domain.

Initial examples:

- Sky Radar
- Weather
- World Clock
- Timers
- Notes / message board
- media utilities

#### Definition of “app”

“App” is a **user-facing product term**, not a plugin runtime.

For this architecture, an app is a registered built-in utility consisting of:

- a route/view identifier exposed through `/hub/views`
- a `ScreenState` or equivalent screen registration
- a draw/render function
- optional local state and/or data-fetch logic

There is no install/uninstall lifecycle, sandbox, manifest system, package manager, or independent process model implied by the term.

### 6. System

**Primary purpose:** control and maintain the WS350 device itself.

Examples:

- Wi-Fi/network
- display
- audio
- LEDs
- device behavior
- date/time
- software/runtime state
- diagnostics
- updates
- maintenance
- recovery

System must not become the replacement for More. Application features do not belong here simply because they lack another home.

## Empty-state policy

A tile must remain meaningful with **no data, no network, and no configured dependency**.

An unavailable tile must offer a useful next action rather than only reporting failure.

| Tile | Empty/offline behavior |
| --- | --- |
| **Now** | Never blank. Show local/cached time when valid. If wall-clock time is not yet established, show **Time not set** with a route to setup. Cached weather may be used but is never required. |
| **Smart Home** | If no devices are configured, show **Set up first device** and open device setup. If configured devices are offline, show the affected state and a troubleshooting/action route. |
| **Workshop** | If no workshop equipment or resources are configured, show **Set up workshop**. Local utilities such as timers remain available. |
| **Printer** | If no printer is configured, show **Add printer**. If configured but offline, show **Printer offline** with reconnect/status action. |
| **Apps** | Never empty. Built-in utilities remain listed even when individual network-backed utilities cannot fetch data. |
| **System** | Always populated from local device state. Network failure is itself useful System status. |

### First boot

On first boot with no network, printer, or optional integrations configured:

- **Now** shows local setup state rather than blank data.
- **Smart Home** shows **Set up first device**.
- **Workshop** shows **Set up workshop**.
- **Printer** shows **Add printer**.
- **Apps** shows built-in utilities.
- **System** shows device/network setup and health.

The Home screen must therefore look intentional before any external service is connected.

## Navigation restructure

The root information architecture becomes:

```text
Home
├── Now
├── Smart Home
├── Workshop
├── Printer
├── Apps
│   ├── Sky Radar
│   ├── Weather
│   ├── Timers
│   └── future built-in utilities
└── System
```

### Persistent navigation

The persistent bottom navigation is:

```text
Home · Apps · Printer · System
```

This is an explicit decision.

**Printer remains one tap away** because print monitoring and printer interaction are established, high-frequency workflows. Workshop remains a Home tile until the Workshop domain has enough real content to justify a persistent navigation slot.

The Home → Printer tile is also fixed in position and remains a large one-tap target.

### Navigation rules

1. Printer is a domain, not the product shell.
2. Home remains useful with the printer idle, disconnected, or unconfigured.
3. New features must first be classified as Smart Home, Workshop, Printer, Apps, or System.
4. Built-in standalone utilities belong in Apps.
5. Device configuration belongs in System.
6. Workshop may aggregate multiple tools and devices.
7. Home tiles summarize; detail screens interact.
8. Every child screen has deterministic navigation to its parent and to Home.
9. No new feature may be added to More.
10. New utilities must not require root-navigation expansion.
11. Root navigation does not use swipe-only or horizontally scrolling navigation. All primary destinations remain visibly reachable by touch.

## More is transitional

**More is not a permanent architectural category.**

During migration it may remain only as a compatibility bridge.

It receives no new features.

Once all existing views have explicit destinations, More is removed.

## Existing-screen migration

The current capture inventory contains roughly forty screens. They are not deleted merely because the Home shell becomes simpler; they are **re-homed and consolidated** behind the new domains.

| Current area | New destination | Migration intent |
| --- | --- | --- |
| Printer status, job, filament/AMS, printer actions | **Printer** | Preserve capability; simplify entry hierarchy where practical. |
| Workshop utilities and shared fabrication resources | **Workshop** | Keep workshop-wide functions outside the printer domain. |
| Sky Radar | **Apps → Sky Radar** | First-class built-in utility. |
| Other standalone utilities | **Apps** | Register as built-in utility screens. |
| Display: Quick, Schedule, Behavior, Visual, Clock, Alerts, Signals, Theme, Gauge Colors, Gauge Scales, Gauge Behavior, Glow, Layout, Extras | **System → Appearance** plus **System → Advanced** where required | Collapse the current 14-category presentation surface into a smaller task-oriented hierarchy. Preserve advanced controls without exposing every category at root level. |
| Hardware: Sound, Cooldown, LED, Finish, Error, Power, Auto Off | **System → Hardware** | Consolidate hardware-facing controls into one System sub-area. |
| Network essentials / connectivity | **System → Network** | One location for Wi-Fi and network state/configuration. |
| Update, diagnostics, runtime/software state | **System → Maintenance** | Consolidate maintenance, update, diagnostics, and recovery. |
| Local Portal / administrative controls | **System → Advanced** | Keep administrative controls available but out of the primary path. |
| Legacy More entries | Reassign individually to **Smart Home**, **Workshop**, **Printer**, **Apps**, or **System** | No legacy item remains solely because More exists. |

### Consolidation target

The fourteen Display categories and seven Hardware categories should not survive as twenty-one peer destinations.

Initial target:

```text
System
├── Appearance
├── Hardware
├── Network
├── Maintenance
└── Advanced
```

This is a navigation consolidation, not permission to silently remove existing functionality.

## 480 × 320 geometry

The working layout budget is:

- display: **480 × 320**
- top header/status region: **24 px**
- bottom persistent navigation: **48 px**
- outer grid margin: **8 px**
- tile gutters: **8 px**

Approximate tile size:

- width: **149 px**
- height: **112 px**

That is sufficient for:

- one icon
- one short title
- one primary value/state
- one optional short supporting line

It is **not** sufficient for simultaneous icon + title + value + secondary value + separate attention badge + additional status text.

See the attached wireframe:

`docs/hub-architecture-sketch.png`

## Design constraints

- exactly six primary Home tiles for the first implementation
- stable tile positions
- minimum 44 px touch targets
- readable at 480 × 320
- no swipe-only or horizontally scrolling root navigation
- no status conveyed by color alone
- clear focus, pressed, disabled, setup, and unavailable states
- reduced-motion support
- strong offline/failure states
- local-first behavior where possible
- network services degrade gracefully
- no dense telemetry on Home
- detail interaction belongs on secondary screens

## Initial migration intent

Architecture is changed before feature expansion.

Recommended implementation sequence:

1. Establish the new Home shell and persistent navigation.
2. Build **only the Now tile** on real hardware as the geometry proof.
3. Validate typography, touch area, glance distance, and the 149 × 112 tile budget.
4. If the tile does not fit cleanly, revise the six-tile model before continuing.
5. Reclassify existing screens into the new domains.
6. Move Sky Radar into Apps.
7. Preserve the existing Printer experience behind Printer.
8. Consolidate System screens into Appearance, Hardware, Network, Maintenance, and Advanced.
9. Remove More after all legacy entries have explicit homes.
10. Add additional non-printer capabilities only after the shell is proven.

## First implementation proof

The first coded tile is **Now**.

It should prove:

- tile geometry
- typography
- icon/title/value hierarchy
- touch target behavior
- local state rendering
- setup/offline treatment
- interaction on physical hardware

The proof should not introduce a new network dependency. NTP may populate time when available, but the UI must still render a valid setup state without it.

## Success criteria

The reframe succeeds when:

- the device is useful with the printer powered off
- first boot looks intentional before integrations are configured
- a new user can understand the product from Home
- Printer remains one-tap accessible
- no feature depends on a generic More bucket
- new utilities can be added without changing root navigation
- existing advanced controls remain reachable without dominating the shell
- the interface feels like a command center rather than a printer accessory

---

**Decision:** Workshop OS evolves into a general home/workshop command center. Printer support remains a major capability, but it no longer defines the product architecture.
