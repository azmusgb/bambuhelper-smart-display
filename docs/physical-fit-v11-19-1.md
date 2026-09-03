# Workshop OS v11.19.1 — Physical Fit RC2

This release is intentionally limited to the two remaining physical text-fit defects found by the real v11.19 22-view WS350 framebuffer capture.

## Corrections

1. Workshop loaded-material empty state changes from the physically clipped `NO ACTIVE T...` rendering to `AMS IDLE`, with `External spool or idle` retained as context.
2. System Audio Lab action changes from the physically clipped `EVENTS...` rendering to `EVENTS`. Current state remains visible in the Audio Lab status text and button accent.
3. Adds a rendered-fit CI contract with conservative pixel envelopes for the exact controls that overflowed in v11.19.
4. Explicitly bans the known v11.19 overflow strings from the generated firmware source.

## Preserved behavior

- v11.19 portal code + IP on System
- AMS unknown/sentinel guard
- configured-but-inactive card styling
- `CUSTOM` persisted-value handling
- Power / Auto-Off consistency
- Home two-line hero
- simplified More summary
- authenticated 22-view framebuffer capture
- v11.17 fail-closed printer controls and stale-state behavior
- existing smart-plug slot mapping

No new feature family is introduced.

`physical_acceptance=REQUIRED`: recapture all 22 WS350 views after flashing RC2 before promotion.
