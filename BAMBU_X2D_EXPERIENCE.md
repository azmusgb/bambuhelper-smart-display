# Bambu X2D Experience Upgrade Plan

## Goal

Make Bambu printer support the primary reason to use the display. The device should behave like a dedicated printer companion, not a generic telemetry screen.

## Printer Operating Modes

### Idle

Show:
- printer name
- online state
- last print
- loaded material
- readiness

### Printing

Prioritize:
- progress percentage
- remaining time
- layer information
- nozzle temperature
- bed temperature
- material
- AMS state

The display should automatically become printer-focused while a print is active.

### Complete

Show:
- completed model
- duration
- material used
- next actions

Recommended actions:
- update filament usage
- start cleanup timer
- review status

### Error / HMS

Error state overrides normal display.

Show:
- error severity
- printer message
- recommended action
- recovery path

## Data Model

Normalized printer state:

```json
{
  "printer": {
    "connected": true,
    "state": "printing",
    "progress": 82,
    "etaMinutes": 23,
    "model": "Example",
    "material": "PLA",
    "nozzleC": 220,
    "bedC": 60,
    "ams": []
  }
}
```

## UX Rules

1. Printer activity has priority over informational cards.
2. Errors override all other states.
3. Missing printer data must show a clear offline state.
4. Never display stale telemetry without an age indicator.
5. Touch targets must remain usable while printing.

## Validation

Before release:

- verify live telemetry refresh
- verify progress updates
- verify AMS rendering
- verify temperature updates
- verify offline behavior
- verify error priority
- verify no redraw regression
