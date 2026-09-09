# Workshop OS v11.25 RC9 — Premium Appliance UI

RC9 is a presentation-only refinement stacked directly on the RC8 physical-polish candidate. It targets the WS350 480×320 landscape display and deliberately keeps RC8's touch geometry, guarded control semantics, network workflow, authentication boundary, recovery behavior, printer authority, and inventory-isolation rules.

## Product intent

The physical display should feel like a purpose-built consumer appliance rather than a compact web dashboard. RC9 therefore prioritizes restraint, hierarchy, typography, state clarity, and low visual noise over decorative chrome.

The governing rule is: **one dominant decision per screen**.

## Locked RC9 changes

1. **Border-light visual system** — primary cards and actions become filled soft surfaces rather than outlined panels with colored rails.
2. **Calmer header** — the boxed `W` mark and header pill are removed. Screen title and a small health/status indicator carry the hierarchy.
3. **Premium bottom navigation** — visible navigation becomes **Home / Printer / Workshop / Settings**. The selected destination uses a restrained raised surface plus a small orange indicator rather than a full orange block.
4. **Title-case copy** — primary navigation and major physical screens stop shouting in all caps. Deep network wizard headings are normalized where RC9 can do so without changing behavior.
5. **Home hierarchy** — current printer state remains dominant; progress metadata is reduced to percent and time remaining. Layer-count detail leaves the primary Home surface.
6. **Truthful material language** — Home and Workshop label AMS-derived state as **Printer material**. This does not claim canonical inventory identity.
7. **Printer refinement** — Status, AMS, and Control remain separate modes, but cards, tabs, telemetry, and controls use the calmer visual system. Stop remains guarded.
8. **Settings replaces More** — the existing page index and touch routing stay intact, but the visible destination is renamed **Settings**. Existing destinations remain Home customization, System, Display, and Tools.
9. **System simplification** — Device, Network, and Local Access remain the normal physical-device view; advanced diagnostics stay in the portal.
10. **Guarded-action semantics preserved** — RC8 network Apply/restart, rotation Apply, and Stop long-press behavior remain intact. RC9 only normalizes their visible copy.

## Explicit non-goals

RC9 does **not**:

- add or infer spool identity;
- infer AMS placement from color/material;
- change printer commands or power authorization;
- weaken portal-code authentication or same-origin mutation protection;
- alter OTA, partition, recovery, or rollback behavior;
- redesign the network address editor into a numeric keypad;
- introduce animation that could reduce touch responsiveness or complicate reduced-motion behavior.

The address editor remains an intentional follow-up because replacing the existing +/- editor with a keypad changes touch/state behavior and deserves its own physically validated change.

## Visual principles

- Near-black background, charcoal surfaces, white/gray typography, one orange accent.
- Green, amber, and red are reserved for health, warning, and destructive/error meaning.
- Spacing and surface elevation replace most borders.
- Primary values dominate; supporting text stays secondary.
- Large routine touch targets remain at least RC8's 48 px floor.
- Hidden gestures are not introduced. Long press stays limited to existing guarded actions.
- Unknown, stale, offline, and conflicting states must remain explicit rather than cosmetically smoothed over.

## Physical acceptance

RC9 must not be promoted stable until the real WS350 confirms:

- first-tap traversal through Home → Printer → Workshop → Settings;
- Settings retains working Home/System/Display/Tools routing;
- no clipping or overlap at 480×320 rotation 1;
- no regression of the RC8 touch-target floor;
- Status / AMS / Control mode tabs are obvious and finger-friendly;
- Stop still requires the existing guarded hold and shows progress before execution;
- network review/apply remains guarded and restart behavior is unchanged;
- the current boot-scoped portal code remains visible on System;
- AMS/material presentation never implies authoritative inventory identity;
- RC8 portal-code authentication, same-origin protection, Safari login fix, recovery, OTA, and inventory-isolation behavior remain intact.

## Release boundary

RC9 is a visual and copy layer only. Passing CI means **implemented / built / tested / software validated**. It is not physical acceptance. The exact RC9 artifact must be exercised on the WS350 before promotion.
