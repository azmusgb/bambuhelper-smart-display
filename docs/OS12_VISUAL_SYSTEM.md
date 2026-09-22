# Workshop OS 12 — WS350 Visual System

Status: **implemented source / CI + physical acceptance required**

This document defines the final 480×320 product presentation for Workshop OS. It is a presentation contract only. It does not change inventory, printer, update, recovery, media, or security authority.

## Product intent

Workshop OS should read as a purpose-built workshop appliance: glanceable, finger-first, calm under normal conditions, explicit under degraded conditions, and honest about Unknown state.

Primary navigation remains:

- Home
- Printer
- Workshop
- More

## Palette

The active native UI uses an industrial graphite palette with orange as the primary interaction/selection color and cyan reserved for informational emphasis:

| Token | Role |
| --- | --- |
| `OS12V_BG` | page background |
| `OS12V_SURFACE` | cards and rows |
| `OS12V_SURFACE2` | selected / raised controls |
| `OS12V_LINE` | quiet separators and outlines |
| `OS12V_TEXT` | primary text |
| `OS12V_MUTED` | secondary text / Unknown |
| `OS12V_ACCENT` | primary interaction / selected state (orange) |
| `OS12V_GREEN` | ready / healthy |
| `OS12V_AMBER` | attention / unavailable / degraded |
| `OS12V_RED` | destructive / fault |
| `OS12V_BLUE` | informational emphasis (cyan) |

Color is semantic, not decorative. Orange is reserved for selected/primary interaction, cyan for informational emphasis, green for healthy/ready, amber for degraded/attention, and red for destructive/fault. Unknown remains muted; printer connectivity is not inventory truth.

## Geometry and interaction

- landscape target: 480×320
- routine interaction target: at least 44 px
- persistent primary bottom navigation
- explicit Back / Done / Stop / Pause / Resume actions
- shallow settings hierarchy
- no hidden hold gesture for ordinary navigation
- destructive Stop remains guarded
- card radius and spacing are consistent across primary and child views
- primary actions use filled treatment; Back/Cancel remain secondary; destructive actions use red
- selected bottom-navigation and printer-mode states are visually explicit

## Home

Home is the glanceable operational summary:

- printer state hero
- current print
- Filament Inventory authority state

No printer telemetry may create inventory identity, quantity, ownership, or placement.

## Printer

Printer is the operational machine view:

- Status / AMS / Control segmented modes with explicit selected state
- current printer state and job
- temperatures
- printer-reported AMS telemetry
- safe controls with guarded destructive Stop

AMS telemetry is explicitly observational and does not become canonical inventory.

## Workshop

Workshop answers whether authoritative workshop evidence is available:

- Print Readiness
- Loaded Spools
- Attention

When required inventory/print evidence is absent, the UI says `Unknown` / `Undetermined`. It does not synthesize certainty.

## More and System

More contains everyday device settings:

- Display & Appearance
- Sound & Media
- Network
- System

System contains:

- Device Health
- Printer & Power
- Date & Time
- Software Update
- Local Portal

The structure is intentionally shallow and finger-first.

## Media

Media, Recorder and Video use the same component and palette system. Runtime lifecycle evidence remains distinct from human-observable speaker, microphone and LCD quality.

## Software Update

The screen must show installed/candidate state truthfully and must not imply unsupported promotion or recovery behavior.

Accepted/stable state is never inferred from a successful build or runtime test.

## Required states

The final UI must remain coherent for:

- ready
- printing
- paused
- offline
- unavailable
- Unknown
- Undetermined
- attention/fault
- no printer configured
- no authoritative inventory evidence
- update candidate / physical acceptance required
- media capability unavailable

## Validation boundary

Automated checks validate:

- exact source identity
- deterministic native routes
- 480×320 geometry
- content/non-degenerate framebuffer
- visual-system markers
- navigation hierarchy
- touch component geometry
- media lifecycle
- renderer motion counters
- authority boundaries

Physical acceptance still owns:

- real LCD readability/color/artifacts
- finger touch comfort/responsiveness
- audible speaker quality
- microphone intelligibility
- recovery/rollback when due

Release state remains:

`implemented -> built -> tested -> runtime validated -> production validated -> physically validated -> accepted -> stable`

## One-command candidate install + unattended acceptance

For exact CI candidates on macOS, use the repository-owned orchestrator after downloading the UX Architecture artifact and updating the local checkout to that exact source SHA:

```bash
bash scripts/install_accept_os12_candidate_macos.sh \
  --artifact-zip ~/Downloads/os12-ux-ws350-<source-sha>.zip \
  --confirm-printer-idle \
  --full-backup \
  --base-url http://10.0.0.124
```

The orchestrator derives the exact source and firmware hashes from `candidate.json`, refuses source mismatch, delegates to the guarded installer, verifies the post-reboot source identity, and runs unattended acceptance. It does not rebuild firmware locally and does not waive the residual physical sensory/recovery gates.
