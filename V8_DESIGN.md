# BambuHelper Smart Home v8 Design

## Goal

Evolve the current installer and firmware project into a calmer local command surface while preserving the validated v7.2 display behavior.

## Primary navigation

- Home
- Workshop
- Printer
- System
- Custom

The display should optimize for operational decisions rather than exposing every capability at once.

## Home dashboard

The home view becomes context-aware:

- Idle: workshop health and quick actions
- Printing: progress, ETA, temperatures, AMS state
- Warning: attention items first

## Component model

Reusable information cards:

- Workshop status
- Printer status
- AMS/materials
- Environment
- Attention queue
- System health
- Quick actions

## State model

All views should consume a single normalized state object:

```js
{
  workshop: {},
  printer: {},
  materials: {},
  environment: {},
  attention: [],
  system: {}
}
```

## UX principles

- Keep critical information visible.
- Hide diagnostics until needed.
- Avoid full-screen redraws.
- Preserve stable header/footer regions.
- Prefer touch-friendly controls.

## Release gate

v8 work must retain:

- v7.2 refresh stability improvements
- existing printer telemetry
- AMS presentation
- recovery/install workflow
- physical device validation process
