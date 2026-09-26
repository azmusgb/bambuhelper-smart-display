# Home Hub Architecture

## Purpose

Workshop OS is a home/workshop command center, not a printer companion with extra screens. The printer is one capability among several.

The Home Hub answers: *What is happening around me, what needs attention, and what can I control from here?*

This document is architecture, not implementation.

## Product model

Local-first command center for a workshop and home environment.

Capability classes: printer status, workshop utilities, smart-home control, weather, timers/clocks, media/audio, device control, diagnostics, standalone apps.

The product must feel useful when no printer is running.

## Home tile model

Home is a glanceable dashboard of six primary tiles. Each tile is both a compact live summary and an entry point to a domain.

Tile anatomy (fits 160 x 125 px):

1. icon (24 px)
2. short title (10 px uppercase, muted)
3. one primary value or state (18-22 px semibold)

Secondary text optional. Attention state via icon and value color, never color alone.

Tile states: Normal, Active, Attention, Unavailable, Unknown.

Rule: any tile showing Unavailable or Unknown must offer an action, not just a status.

### Empty-state policy (first boot: no network, no printer, no plugs)

| Tile | Empty-state behavior |
|---|---|
| Now | Always populated from local time; weather shows dash if no network |
| Home | "Set up first device" opens System -> Devices |
| Workshop | "No equipment configured" shortcut to add |
| Printer | "Add first printer" opens Printer setup |
| Apps | Never empty; shows built-in apps |
| System | Always populated from local state |

## The six Home tiles

1. **Now** — local time + date primary; weather or next timer secondary
2. **Home (Smart Home)** — plugs, lights, sensors, temperature
3. **Workshop** — equipment, bench state, filament, workshop timers
4. **Printer** — existing printer experience, unchanged
5. **Apps** — standalone utilities (see below)
6. **System** — network, display, audio, LEDs, diagnostics, updates

App = ScreenState entry + /hub/views catalog entry + draw function in smartHubDraw(). No lifecycle, no manifest, no sandbox.

Initial apps: Sky Radar, Weather, Timers, World Clock, Notes.

## Navigation

Root nav: Home - Apps - Workshop - Printer

Printer keeps a permanent nav slot. Workshop is reachable via its Home tile until it has enough content to justify promotion.

## Migration plan for existing screens

| Current location | New home |
|---|---|
| Printer-domain screens | Printer |
| Display categories (14) | System -> Appearance |
| Hardware categories (7) | System -> Hardware |
| Network pages (4) | System -> Network |
| Updates/diagnostics | System -> Maintenance |
| Local Portal, recovery, admin | System |
| Custom dashboard | Home -> Home tile |

Display + Hardware collapse into 3 System sub-pages: Appearance, Hardware, Advanced. No features removed.

More is retired. Unrehomed content stays behind "More (transitional)" with no new features.

## Architecture rules

1. Printer is a domain, not the product shell.
2. Home is useful when the printer is idle or disconnected.
3. New features classified as Home, Workshop, Printer, Apps, or System.
4. Standalone utilities belong in Apps.
5. Device configuration belongs in System.
6. Workshop may aggregate multiple devices and tools.
7. Home tiles summarize; detail screens interact.
8. Child screens have deterministic back navigation.
9. No new features in More.
10. Future integrations must not force navigation redesign.

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

1. Build only the Now tile as proof. No network, no config, only NTP. If it renders cleanly at 160 x 125, the model works.
2. Once Now renders, add Weather (single HTTPS GET, no API key).
3. Move Sky Radar into Apps.
4. Reclassify remaining screens per the migration table.
5. Retire More.

## Success criteria

- device is useful with the printer powered off
- a new user understands the product from Home
- printer functionality is still one tap from Home
- no feature depends on a generic More bucket
- new apps can be added without changing navigation
- it feels like a command center, not a printer accessory

---

**Decision:** Workshop OS is a home/workshop command center. Printer support is a first-class capability, not the product architecture.