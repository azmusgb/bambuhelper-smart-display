# Workshop OS v11.25 RC7 — Touch-First UX Overhaul

RC7 is a presentation and interaction-language overhaul for the Waveshare 3.5-inch 480×320 target. It is intentionally layered after RC6 security hardening and must not weaken authentication, recovery, command guards, persistence, or printer authority boundaries.

## Product principles

1. **One glance, one decision.** Every screen leads with current state and the next useful action.
2. **Touch first.** Normal actions use obvious controls and generous hit areas. Hidden tap/hold navigation is not acceptable.
3. **Guard only dangerous actions.** Hold is reserved for destructive or restart/apply operations such as Stop and network Apply.
4. **No desktop density.** Secondary explanation is removed before primary labels or values are shrunk.
5. **State is semantic.** Accent, success, warning, and danger communicate different meanings; selection and warning must not look interchangeable.
6. **Operational language, not implementation language.** Driver/build/internals belong in System/diagnostics, not primary workflow screens.
7. **Fail clearly.** Empty, offline, unavailable, disabled, and pending states must look deliberate and say what the user can do next.
8. **Security stays visible.** The boot-scoped portal code remains available on the System screen.

## Native 480×320 hierarchy

- Header: identity + page title + compact connection/context state.
- Main content: state first, then only the telemetry needed to act.
- Bottom navigation: HOME / PRINTER / WORKSHOP / MORE; persistent, explicit, large.
- Cards: 10 px radius, low-chrome surface, optional 4 px semantic rail.
- Action controls: entire rectangle is the affordance; destructive state is explicit.
- Printer secondary navigation: STATUS / AMS / CONTROL with a filled selected segment.

## Primary screen changes

### Home
- Printer state is the hero.
- Empty printer state becomes `SET UP PRINTER` rather than a passive zero-data dashboard.
- Material/network become compact status cards.
- Right rail becomes `ATTENTION` + `NEXT ACTION`; test/build metadata is removed.

### Printer
- No-printer state explains what configuration unlocks.
- Status prioritizes job, progress, time, layer, and three temperatures.
- Fan telemetry is removed from the primary temperature card to reduce noise.
- AMS cards prioritize slot, remaining amount, spool, and material.
- Control labels describe outcomes (`PRINTER POWER`, `HOLD TO STOP`) rather than implementation details.

### Workshop
- Timer is the dominant state.
- Note and material are secondary.
- LIGHT / TOOLS / SYSTEM / PRINTER remain explicit finger-sized actions.

### More
- Four destination cards only: DASHBOARD / SYSTEM / DISPLAY / TOOLS.
- Build/IP/test metadata is removed from the navigation hub and remains available in System diagnostics.

### System
- Health, sound, network, and portal access are the four concepts.
- Portal code remains visible and boot-scoped.
- Runtime UI fingerprint moves to the device/version diagnostic line instead of consuming global header space.

## Settings-wide cleanup

RC7 normalizes inherited pages without altering their state machines:

- `< BACK` → `BACK`
- `< PREV` → `PREV`
- `NEXT >` → `NEXT`
- `REVIEW >` → `REVIEW`
- `HOLD APPLY + RESTART` → `HOLD TO APPLY`
- `STAGED - NOT APPLIED` → `CHANGES NOT APPLIED`
- long header contexts are shortened intentionally (`TIME`, `ADDRESS`, `COLORS`, `SCALES`, `AUTO OFF`, etc.) instead of shrinking/truncating labels.

Network remains a four-step flow: BASICS → TIME → ADDRESS → REVIEW. Apply remains hold-guarded and restart semantics are unchanged.

## Portal layer

The RC7 portal CSS layer establishes:

- 48 px minimum interactive control height
- stronger keyboard focus indicators
- less border-heavy card treatment
- larger table row padding
- responsive one-column cards on narrow screens
- `prefers-reduced-motion` handling

## Non-negotiable regression boundaries

RC7 must retain:

- portal-code authentication and SameSite/HttpOnly session behavior
- same-origin protection for mutations
- RC6 recovery behavior and runtime observability
- guarded Stop
- guarded network Apply/restart
- no cross-private/inferred filament inventory identity
- no temporary `TEST / NO CODE` access mode
- both WS350 and shared 320×480 compilation

## Physical acceptance after CI

CI validates structure and compilation. Final acceptance still requires the real WS350:

1. Traverse all 32 capture views by touch.
2. Verify every normal navigation/action target with a finger.
3. Verify Stop and network Apply require hold and show progress/feedback.
4. Configure a real printer and validate telemetry, AMS, light, pause/resume, Stop, and mapped power.
5. Reboot and verify settings persistence, Wi-Fi reconnect, portal-code rotation, and login.
6. Run OTA and recovery-path acceptance.
7. Capture a new 32-frame RC7 evidence ZIP and compare against the RC6 baseline.
