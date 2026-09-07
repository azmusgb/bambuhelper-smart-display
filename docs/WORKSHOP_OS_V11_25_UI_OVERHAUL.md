# Workshop OS v11.25 — Full Device UI Overhaul

Status: **design/implementation candidate only**. This document does not claim physical acceptance.

## Product intent

v11.25 is the first whole-device visual and interaction pass after the v11.23 Network / Locale / Layout RC2 work. It applies one coherent 480×320 workshop UI system across the primary device experience instead of limiting the redesign to settings flows.

## Primary navigation

The persistent device navigation is:

- Home
- Printer
- Workshop
- More

Primary navigation must remain explicit and finger-sized. Routine navigation must never depend on hidden long-press gestures.

## Visual system

- Neutral dark workshop surfaces with restrained depth.
- Cyan/blue is the ordinary interaction accent.
- Green is success/ready only.
- Amber is caution/staged/attention only.
- Red is destructive/error only.
- Avoid rainbow-coded cards when color does not carry semantics.
- Use a consistent header, card, status rail, action-bar and bottom-navigation grammar.
- Prefer large values, short labels, one-line state explanations and arm's-length legibility.
- No clipped text, overlapping controls or tiny tertiary metadata on primary screens.

## Touch contract

- 48 px is the hard minimum target dimension for routine controls.
- Aim for approximately 52–60 px on primary actions where the layout permits.
- Explicit Back / Next / Cancel controls on staged flows.
- Long press is reserved for guarded destructive/commit actions such as Stop, power-off during an active print, Apply/Restart and rotation commit.
- Disabled actions remain visible with a clear unavailable state rather than disappearing.

## Home

Home is a workshop dashboard, not a menu. It should answer at a glance:

1. What is the printer doing?
2. Is anything asking for attention?
3. What is the most useful next action?
4. Is there an active timer or note?

The default landscape hierarchy is one dominant printer/workshop status hero plus compact attention and utility cards. When the printer is offline or unconfigured, that state is explicit and no device state is invented.

## Printer

Printer uses explicit internal modes:

- STATUS
- AMS
- CONTROL

STATUS prioritizes current job, progress, remaining time, layer and temperatures. AMS shows printer telemetry only; telemetry must not be presented as authoritative Filament Inventory spool identity. CONTROL groups light, pause/resume, guarded stop and mapped power actions using the existing safety boundaries.

Where inventory integration has not authoritatively linked a physical spool, the device must say `Inventory spool: Unknown` rather than infer identity from color/material.

## Workshop

Workshop is the fast physical workbench surface: timers, note, quick attention items and safe shortcuts. It should not become another settings page.

## More

More is the launcher for secondary tools and device configuration. Keep the top-level choices shallow and contextual. System, Display, Tools and Custom remain reachable without crowding the primary navigation.

## State vocabulary

Physical and inventory-facing UI should consistently distinguish:

- Known
- Estimated
- Stale
- Conflicting
- Unknown

Unknown values remain unknown. Visual similarity is never enough to claim spool identity, owner, quantity or AMS placement.

## Release discipline

The implementation state progression remains:

`implemented -> built -> tested -> runtime validated -> production validated -> physically validated -> accepted -> stable`

v11.25 must not be merged/promoted as stable solely because CI or native builds pass. The WS350 physical acceptance pass must cover every changed primary screen and all guarded control paths.
