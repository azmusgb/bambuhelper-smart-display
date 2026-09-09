# Workshop OS v11.25 RC10 — Cupertino UI

## Purpose

RC10 is a native TFT visual refinement for the Waveshare ESP32-S3 3.5-inch
WS350 display. The on-device interface is rendered in C++ through the TFT
drawing stack in `src/smart_hub.cpp`; the repository's HTML/CSS/JavaScript
assets are the browser portal and are not the primary physical-screen UI.

RC10 intentionally changes presentation only. It inherits the RC8/RC9 touch,
security, printer-control, recovery, network, and inventory-authority contracts.

## Visual direction

The target is not a literal copy of iOS. It applies the interaction and visual
principles that make Apple interfaces feel calm and legible on a small display:

- near-black canvas with grouped elevated surfaces;
- one system-like blue accent (`#0A84FF`) instead of pervasive orange chrome;
- title case rather than dashboard-style all caps;
- restrained semantic green/orange/red only when state requires it;
- borderless rounded groups with separators instead of outlined cards;
- a segmented Printer control with a filled selected segment, not an underline;
- a tab bar with icon + label state, matching mobile navigation conventions;
- one dominant information hierarchy per screen;
- secondary copy rendered in a consistent muted hierarchy;
- destructive actions remain red and guarded rather than visually normalized.

## Native design tokens

| Token | RGB | RGB565 | Role |
| --- | --- | --- | --- |
| `C10_BG` | `#000000` | `0x0000` | OLED-like canvas |
| `C10_SURFACE` | `#1C1C1E` | `0x18E3` | grouped surface |
| `C10_SURFACE_2` | `#2C2C2E` | `0x2965` | elevated/hero surface |
| `C10_SURFACE_3` | `#3A3A3C` | `0x39C7` | selected segment |
| `C10_MUTED` | `#8E8E93` | `0x8C72` | secondary text |
| `C10_ACCENT` | `#0A84FF` | `0x0C3F` | primary action/selection |
| `C10_GREEN` | `#30D158` | `0x368B` | healthy/connected |
| `C10_ORANGE` | `#FF9F0A` | `0xFCE1` | active/warning |
| `C10_RED` | `#FF453A` | `0xFA27` | error/destructive |

## Screen changes

### Home
- Replaces several competing cards with one dominant printer hero and one
  grouped summary surface.
- Summary consolidates Attention, Material, and Network into a single scan path.
- Keeps printer material identity explicit; it never infers inventory spool
  identity from AMS color or material.

### Printer / Status
- Keeps the RC8 touch geometry.
- Uses a quieter job hero plus grouped temperature rows.
- Progress uses the primary blue accent while printer state remains semantic.

### Printer / AMS
- Keeps four large physical slot targets.
- Active slot uses a selected surface and blue state marker.
- AMS telemetry remains distinct from inventory authority.

### Printer / Control
- Keeps the existing command and hit-test path.
- Actions become borderless system-like controls.
- Stop remains destructive and continues to require the inherited hold guard.

### Workshop
- Keeps the timer as the visual anchor.
- Consolidates Note and Material into one grouped context surface.
- Keeps the four existing touch targets and command behavior.

### Settings / System
- Reduces decorative icon containers and border noise.
- Uses grouped surfaces, restrained chevrons, muted secondary copy, and a
  system-blue navigation accent.
- Local Access continues to show the secure reboot-rotating portal code.

## Explicitly preserved

RC10 must not alter:

- `hubHeaderH() == 36`;
- `hubNavH() == 54`;
- the seven-page network workflow;
- RC8 physical touch rectangles;
- hold-to-stop / hold-to-apply semantics;
- portal-code authentication;
- same-origin checks for mutating browser requests;
- recovery and diagnostics behavior;
- printer capability/state authorization;
- inventory authority boundaries;
- the rule that color/material resemblance cannot assign an inventory spool.

## Validation

The RC10 workflow reconstructs the pinned upstream source, applies the complete
patch chain through RC9, then RC10, and builds:

1. `ws_lcd_350` — physical WS350 target;
2. `jc3248w535` — shared 320×480 regression target.

The workflow also verifies the UI10 fingerprints, build profile/schema,
security invariants, browser runtime guards, touch geometry, and forbidden
inventory-inference symbols.

## Physical acceptance

A successful CI build is necessary but not sufficient. Before promoting RC10:

- inspect every screen at 480×320 for clipping and text fit;
- verify Home / Printer / Workshop / Settings navigation;
- verify Status / AMS / Control segmented switching;
- exercise Light, Pause/Resume, printer power, and guarded Stop;
- verify the stop hold-progress feedback remains visible and cancellable;
- verify Network navigation and static-IP hold-to-apply;
- verify Local Access code rotation and authenticated portal flow;
- verify recovery, reboot, Wi-Fi reconnect, and settings persistence;
- verify touch behavior with a finger, not only screenshots.

RC10 should be promoted only if the physical screen feels quieter than RC9
without reducing glanceability or making safety state less obvious.
