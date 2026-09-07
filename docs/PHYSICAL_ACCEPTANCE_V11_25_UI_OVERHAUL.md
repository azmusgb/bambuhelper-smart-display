# Workshop OS v11.25 — Full Device UI Overhaul Physical Acceptance

This checklist is the hardware gate for v11.25. Automated build/test success does not satisfy this checklist.

## Device identity

Record:

- candidate commit SHA
- full-image SHA-256
- OTA-image SHA-256
- flashed image type and offset
- WS350 hardware identity
- date/time of test

## Primary-screen visual pass

Inspect Home, Printer Status, Printer AMS, Printer Control, Workshop and More on the physical 480×320 display.

For every screen verify:

- no clipped or overlapping text
- no controls touching the display edge
- title/value hierarchy is readable at arm's length
- neutral surfaces dominate; semantic color is not decorative
- selected, disabled, loading, offline, warning and destructive states are visually distinct
- minimum routine touch target is at least 48 px in the reference layout
- adjacent targets do not activate accidentally
- important values remain legible under bright workshop lighting

## Navigation

Verify Home / Printer / Workshop / More from every primary screen.

- one tap navigates
- active destination is obvious
- no hidden hold gesture is needed
- Back/Next/Cancel are explicit on staged subflows

## Home

Verify at minimum:

- unconfigured printer state
- configured but offline state
- connected idle state
- active print state
- paused state
- active timer state
- completed timer/attention state
- note present / note absent

No unobserved physical or inventory state may be fabricated.

## Printer — Status / AMS / Control

Verify:

- STATUS, AMS and CONTROL mode switching
- job title, progress, time remaining, layer and temperature layout
- unknown or unreported values do not render as fake percentages or identities
- AMS telemetry does not claim Filament Inventory spool identity unless linked by authoritative inventory data
- where no authoritative inventory link exists, `Inventory spool: Unknown` is visible when identity context is shown
- chamber light toggle
- Pause -> Resume
- guarded Stop: tap alone does not stop; intended hold path provides feedback and stops only after guard completion
- disabled controls when offline/idle are visibly unavailable
- mapped smart-plug power state, if configured
- active-print power-off warning/guard, if power control is configured

## Workshop

Verify timer creation/use, timer completion, note visibility and all quick shortcuts. Confirm Workshop remains a workbench surface rather than a dense settings menu.

## More / Settings

Verify Custom, System, Display and Tools entry points. Re-run the v11.23 Network / Locale / Layout acceptance paths to ensure the full-device overhaul did not regress:

- timezone selection
- DHCP/static staging
- IPv4 editing
- Review / Discard / guarded Apply + Restart
- display rotation preview / guarded commit
- authenticated portal/session boundary

## Reliability and recovery

Verify:

- settings survive reboot
- Wi-Fi reconnect
- printer configuration survives reboot
- OTA upgrade path from compatible Workshop OS
- approved full-image recovery at `0x0`
- known-good rollback artifact/procedure remains available

## Exit gate

Do not mark v11.25 physically validated, accepted or stable until every applicable item above passes on the real WS350 and the candidate SHA/artifact hashes are recorded.
