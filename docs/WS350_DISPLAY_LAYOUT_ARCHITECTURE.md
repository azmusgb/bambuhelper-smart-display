# WS350 Display Layout Architecture

## Goal

Prevent firmware releases from rendering controls outside the physical display bounds.

## Rules

- No screen may use hard-coded coordinates without bounds validation.
- Every screen receives display dimensions, rotation, and safe-area information.
- Recovery screens must remain usable even when normal UI rendering fails.

## Display Profile

The WS350 profile defines:

- width
- height
- orientation
- touch transform
- safe margins

Example:

```json
{
  "device": "WS350",
  "width": 320,
  "height": 480,
  "orientation": "portrait"
}
```

## Validation

Required automated checks:

- all elements fit within framebuffer bounds
- touch targets remain reachable
- screenshot regression passes
- recovery screen is visible after failed updates

## Release Gate

A firmware release requires physical validation before promotion.