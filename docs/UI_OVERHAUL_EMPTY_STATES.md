# v11.25 empty/offline states

Primary surfaces must explain why information is absent.

- No printer configured: show setup-required state; do not populate sample telemetry.
- Printer configured but offline: preserve last-known details only where explicitly labeled stale; otherwise show current values as unavailable.
- AMS absent/unreported: show no AMS telemetry; do not imply a loaded inventory spool.
- No active timer/note: use quiet empty state rather than placeholder content.
- Recovery/network startup: show starting/loading state distinctly from healthy and failed.
