# Workshop OS v11.25 — Full Device UI Overhaul

## RC3 premium physical-test candidate

RC3 is the first candidate in this line that treats the WS350 display and the local web portal as one visual product rather than a set of individually improved screens.

### Device UI

The 480×320 device keeps the primary information architecture:

`Home · Printer · Workshop · More`

and Printer modes:

`Status · AMS · Control`

RC3 applies a coherent premium instrument-panel language across the complete primary path:

- compact Workshop identity header with explicit connection/health state;
- restrained orange interaction accent instead of broad cyan decoration;
- flatter, tighter cards with clearer edge hierarchy and less ornamental chrome;
- stronger typography hierarchy between section label, state, value and supporting detail;
- Home organized as a printer command center plus a separate next-action / material / access rail;
- Printer Status with a dominant job card and a structured 2×2 live-telemetry matrix;
- AMS cards that prioritize slot, remaining amount, material and printer-reported color while keeping inventory identity explicitly `Unknown` unless authoritative linkage exists;
- Printer Control using large guarded action surfaces with destructive Stop visually separated;
- Workshop centered on timer, note, material path and explicit quick actions;
- More presented as a small set of high-level destinations instead of a dense settings page;
- System presents health, audio/events, network and temporary local-access state as distinct operational cards;
- routine touch targets remain at least 48 px with 52–60 px preferred where geometry permits.

The candidate still preserves the durable source-of-truth rule: printer telemetry is not inventory identity. Color/material similarity must never be used to manufacture spool identity or placement.

## Local portal CSS

RC3 also adds a dedicated final CSS layer for the on-device/local portal. It tightens the shell, hierarchy and interaction design without changing API semantics:

- stronger top bar and navigation hierarchy;
- clearer selected navigation state;
- refined dark surfaces and orange interaction accent;
- larger, more consistent controls and focus states;
- redesigned Workshop workspace cards, telemetry, progress, material slots and utility dock;
- responsive behavior for tablet and phone widths;
- explicit reduced-motion handling;
- visible keyboard focus treatment.

## Temporary physical-test access mode

At the user's request, the RC3 physical-test artifact continues the RC2 temporary station-LAN no-code mode. Normal station-mode LAN browsing does not require the device/boot code during this test build.

This does **not** redefine the stable security policy. The following remain preserved:

- mutating requests retain same-origin protection;
- AP/setup/recovery routing remains on its existing authorization path;
- printer command boundaries remain unchanged;
- recovery remains available.

The temporary bypass is marked with `WORKSHOP_OS_TEMP_NO_CODE_LAN` and blocks promotion. Before any accepted/stable release, it must be removed and the secure candidate must be rebuilt and retested.

## Release discipline

RC1 was rejected for insufficient visual delta. RC2 established the stronger visual reset. RC3 is the premium polish pass requested after physical review.

Release states remain distinct:

`implemented -> built -> tested -> runtime validated -> production validated -> physically validated -> accepted -> stable`

A green CI build is not physical acceptance. Do not merge/promote this draft candidate until the actual WS350 passes physical UX and control acceptance, and do not promote any artifact while the temporary no-code marker is enabled.
