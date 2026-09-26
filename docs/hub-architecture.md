# Home Hub Architecture

## Purpose

Workshop OS is a **home/workshop command center**, not a printer companion with extra screens. The printer is one capability among several.

The Home Hub answers: *What is happening around me, what needs attention, and what can I control from here?*

This document is architecture, not implementation.

## Product model

Local-first command center for a workshop and home environment. Capability classes:

- printer and fabrication status
- workshop utilities
- smart-home control
- environmental and weather information
- timers, clocks, reminders, productivity
- media and audio
- local device control
- diagnostics and system administration
- standalone utility apps (Sky Radar, Weather, etc.)

The product must feel useful when no printer is running.

## Home tile model

Home is a glanceable dashboard of six primary tiles. Each tile is both a compact live summary and an entry point to a domain.

Tile anatomy (fits 160 x 125 px). Only three elements fit per tile:

1. icon (24 px)
2. short title (10 px uppercase, muted)
3. one primary value or state (18-22 px semibold)

Secondary text is optional. Attention state is shown via icon and value color, never color alone.

Tile states: Normal, Active, Attention, Unavailable, Unknown.

**Rule: any tile showing Unavailable or Unknown must offer an action, not just a status.**

### Empty-state policy (first boot: no network, no printer, no plugs)

| Tile | Empty-state behavior |
|---|---|
| Now | Always populated from local time; weather shows dash if no network |
| Home | "Set up first device" -> opens System -> Devices |
| Workshop | "No equipment configured" -> shortcut to add |
| Printer | "Add first printer" -> opens Printer setup |
| Apps | Never empty; shows built-in apps (Sky Radar, Weather, Timers) |
| System | Always populated from local state |

## The six Home tiles

### 1. Now
Human-centered anchor. Local time + date primary. Weather or next timer as secondary when available. Never requires network.

### 2. Home (Smart Home)
Room-level control: smart plugs, lights, sensors, temperature. Protocol-agnostic. Existing Tasmota support lives here rather than being printer-power-only.

### 3. Workshop
Workshop-wide status: active equipment, bench state, filament inventory, timers, maintenance reminders. Printer-specific content lives under Printer, not here.

### 4. Printer
Existing printer experience, unchanged. Home tile summarizes readiness/progress/fault; tapping enters full experience.

### 5. Apps
Standalone utilities. **"App" in this architecture means exactly three things:** a ScreenState entry, a /hub/views catalog entry, and a draw function wired into smartHubDraw(). No lifecycle, no manifest, no sandbox, no install/uninstall.

Initial apps: Sky Radar, Weather, Timers, World Clock, Notes.

### 6. System
Device administration: network, display, audio, LEDs, behavior, diagnostics, maintenance, updates, recovery.

## Navigation

Root nav: **Home - Apps - Workshop - Printer**

Printer keeps a permanent nav slot because for a workshop device Home -> Printer (two taps) is worse than Printer (one tap). Workshop is reachable via its Home tile until it has enough content to justify promotion.

Tree:

cat >> ~/dev/bambuhelper-smart-display/docs/hub-architecture.md <<'EOF'

## Migration plan for existing ~44 screens

| Current location | New home |
|---|---|
| Printer-domain screens (10) | Printer |
| Display categories (14) | System -> Appearance |
| Hardware categories (7) | System -> Hardware |
| Network pages (4) | System -> Network |
| Updates/diagnostics (4) | System -> Maintenance |
| Local Portal, recovery, admin | System |
| Custom dashboard | Home -> Home tile |

The 14 Display and 7 Hardware categories collapse into 3 System sub-pages: Appearance, Hardware, Advanced. No features are removed; only the IA changes.

More is retired. Any content not yet rehomed stays behind a temporary "More (transitional)" entry that receives no new features.

## Architecture rules

1. Printer is a domain, not the product shell.
2. Home must be useful when the printer is idle or disconnected.
3. New features are classified as Home, Workshop, Printer, Apps, or System.
4. Standalone utilities belong in Apps.
5. Device configuration belongs in System.
6. Workshop may aggregate multiple devices and tools.
7. Home tiles summarize; detail screens interact.
8. Child screens have deterministic back navigation.
9. No new features in More.
10. Future integrations must not force a navigation redesign.

## Design constraints

- six primary tiles on Home at 480 x 320
- stable tile positions
- 44 px minimum touch targets
- no status conveyed by color alone
- clear focus / pressed / disabled states
- reduced-motion support
- strong offline and failure states
- local-first behavior where possible
- network services degrade gracefully
- no dense telemetry on Home

## Implementation sequence

1. Rewrite this doc with the empty-state policy, migration table, tile rename, app definition, and a 480x320 sketch.
2. Build only the Now tile as proof of the tile model. It needs no network, no config, only NTP. If it renders cleanly at 160 x 125, the model works.
3. Once Now renders, add Weather (single HTTPS GET, no API key).
4. Move Sky Radar into Apps.
5. Reclassify remaining screens per the migration table.
6. Retire More.

## Success criteria

- device is useful with the printer powered off
- a new user understands the product from the Home screen
- printer functionality is still one tap from Home
- no feature depends on a generic More bucket
- new apps can be added without changing root navigation
- it feels like a command center, not a printer accessory

---

**Decision:** Workshop OS is a home/workshop command center. Printer support is a first-class capability, not the product architecture.

## Architecture rules

1. Printer is a domain, not the product shell.
2. Home must be useful when the printer is idle or disconnected.
3. New features are classified as Home, Workshop, Printer, Apps, or System.
4. Standalone utilities belong in Apps.
5. Device configuration belongs in System.
6. Workshop may aggregate multiple devices and tools.
7. Home tiles summarize; detail screens interact.
8. Child screens have deterministic back navigation.
9. No new features in More.
10. Future integrations must not force a navigation redesign.

## Design constraints

- six primary tiles on Home at 480 x 320
- stable tile positions
- 44 px minimum touch targets
- no status conveyed by color alone
- clear focus / pressed / disabled states
- reduced-motion support
- strong offline and failure states
- local-first behavior where possible
- network services degrade gracefully
- no dense telemetry on Home

## Implementation sequence

1. Rewrite this doc with the empty-state policy, migration table, tile rename, app definition, and a 480x320 sketch.
2. Build only the Now tile as proof of the tile model. It needs no network, no config, only NTP. If it renders cleanly at 160 x 125, the model works.
3. Once Now renders, add Weather (single HTTPS GET, no API key).
4. Move Sky Radar into Apps.
5. Reclassify remaining screens per the migration table.
6. Retire More.

## Success criteria

- device is useful with the printer powered off
- a new user understands the product from the Home screen
- printer functionality is still one tap from Home
- no feature depends on a generic More bucket
- new apps can be added without changing root navigation
- it feels like a command center, not a printer accessory

---

**Decision:** Workshop OS is a home/workshop command center. Printer support is a first-class capability, not the product architecture.
