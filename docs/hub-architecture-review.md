# Review: hub-architecture.md

## Verdict
The reframe is correct and the doc is executable. Two blocking gaps:
the Home tile collides with the root Home screen, and empty-state
design is missing. Both need fixing before this becomes an
implementation target.

## Critical gaps

### 1. Tile named "Home" collides with root screen "Home"
Rename the smart-home tile. Options: Smart Home / Rooms / House /
Environment. Nav tree shows `Home -> Home`, which is incoherent.

### 2. Empty-state policy missing (highest risk)
Six tiles, most of which may be empty if no devices are configured.
The device must be useful on first boot with no network, no printer,
no plugs. Suggested policy per tile:
- Now: always populated from local time / cached state
- Smart Home: empty state = "set up first device" with shortcut
- Workshop: empty state = shortcut to add equipment
- Printer: empty state = "add first printer" tile
- Apps: never empty - always shows built-in apps
- System: always populated from local state
Rule: an unavailable tile must offer an action, not just a status.

### 3. "Apps" implies a runtime that does not exist
Current architecture has screens, not apps. Define explicitly:
an "app" = ScreenState + catalog entry + draw function. No
lifecycle, no manifest, no sandbox. Or drop the word.

### 4. No migration plan for existing ~44 screens
What happens to the 14 Display categories, 7 Hardware categories,
System sub-pages, etc.? Suggested reassignment:
- Printer-domain -> Printer
- Display/audio/LED -> System -> Appearance
- Network -> System -> Network
- Updates/diagnostics -> System -> Maintenance
- Local portal / admin -> System
- Collapse 14 Display + 7 Hardware into 3 System sub-pages:
  Appearance, Hardware, Advanced

### 5. Dropping Printer from nav is a user regression
For a workshop device, Printer at Home -> tap twice is worse than
Printer at one tap. Pick one: keep Printer in nav (replace
Workshop which is aspirational), or anchor the Printer tile at a
known position so Home -> Printer is one tap.

## Medium issues
- "Now" is overloaded (time + date + weather + calendar + timer)
- No physical-location grounding (kitchen vs workbench)
- No first-boot experience described
- "No horizontal root navigation" asserted without reason

## Geometry check
480x320 with 6 tiles: 480 / 3 cols = 160 px per tile; 320 - 50 nav
- 20 header = 250 / 2 rows = 125 px per tile. 160x125 fits icon +
title + ONE value. The tile anatomy section lists six things
(icon, title, value, secondary, attention, status). Only 3 fit.
Sketch 480x320 before committing to six tiles.

## Recommended next step
Rewrite the doc with: empty-state policy, migration table, tile
rename, app definition, and a 480x320 sketch. No code yet.
Then build ONLY the Now tile as proof - it needs no network, no
config, only NTP. If Now renders cleanly at 160x125, the tile
model works. If not, revise the doc before rewriting the UI.
