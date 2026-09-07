# Workshop OS v11.23 RC2 — Physical Acceptance

Use the authenticated `scripts/capture-ws350-views.zsh` helper for framebuffer evidence. Do not disable or bypass the portal session during acceptance.

CI, framebuffer capture, and native builds are prerequisites; none of them substitute for hands-on acceptance on the actual 480×320 WS350.

## Preconditions

- device reports `Smart Home v11.23 Network Locale Layout RC2`;
- `safeMode=false`, `webReady=true`, touch responsive;
- normal station-mode management routes require a valid portal session;
- printer is in a safe state for UI testing;
- record the candidate source SHA and firmware artifact hash before starting.

## Product visual hierarchy checks

Evaluate these on the physical screen at normal arm's-length viewing distance, not only from enlarged framebuffer captures.

1. Neutral cards and panels read as the primary structure; arbitrary fields do not form a rainbow of competing colors.
2. Cyan/blue is used for ordinary interaction/navigation. Green indicates healthy/success state, amber indicates staged/caution/guarded state, and red indicates destructive/error/unsafe state.
3. Semantic state is never communicated by color alone: labels such as `STAGED`, `NOT APPLIED`, `PRINTER ACTIVE`, `DISCARD`, and `HOLD` remain readable.
4. Card title, value, supporting detail, and action hierarchy are visually distinct at 480×320 without requiring squinting.
5. The narrow semantic rail on RC2 information cards remains visible but does not overpower the value text.
6. No label, value, progress indicator, button, or footer is clipped, overlapped, or rendered outside its intended region in any of the deterministic views.
7. Selected, disabled, staged, warning, and error states are visibly distinguishable from ordinary controls.
8. Dense Network/Display pages remain scannable: the next action is obvious within a few seconds without knowledge of hidden gestures.
9. View the device under normal room light and a brighter workshop-light condition; primary text and action boundaries remain legible in both.

## Touch / network checks

1. Network Expert pages expose obvious Back / Next controls.
2. Primary navigation and edit controls use the RC2 finger-sized geometry (approximately 52 px reference height where the 480×320 layout permits it).
3. Time & Locale exposes explicit Prev / Next timezone controls; change once and restore.
4. Address Editor visibly states `STAGED — NOT APPLIED`.
5. Select and alter an IPv4 octet, move to Review, then use Discard; persisted addressing must remain unchanged.
6. IPv4 decrement/increment controls are visibly grouped as one editing mechanism rather than four unrelated color-coded actions.
7. Short-tapping Apply must not persist or restart.
8. When holding a guarded Apply action, the five-segment progress feedback is visible and tracks the 650 ms commit threshold.
9. If deliberately testing Apply, use a known-safe network configuration and expect the display to restart/reconnect; the printer must not receive a print-control command.
10. Repeatedly tap near the boundaries between adjacent controls. The intended target should activate consistently without accidental neighboring activation.

## Rotation checks

1. Open Display → Extras → Rotation.
2. Confirm Current and Preview are distinct staged values.
3. Prev / Next changes Preview only.
4. Short-tap Commit must not persist.
5. Deliberate hold shows progress and commits orientation and touch mapping together.
6. Restore the original rotation and verify touch alignment across the full panel, including all four corners.

## Accessibility / recovery checks

1. Ordinary navigation requires no long-press or undocumented left/right tap convention.
2. Guarded long-press remains limited to actions whose consequence warrants it, such as Apply/Restart and Rotation Commit.
3. Warning and destructive controls remain understandable when viewed without relying on their color names.
4. After a settings change or restart, the device returns to a comprehensible state; there is no dead-end screen that requires an undocumented gesture.
5. If Wi-Fi becomes unavailable during the flow, recovery/reconnect state is explicit and the device does not present stale connectivity as current.

## Security / capture checks

1. Opening a protected route without a session must not provide normal-LAN management access.
2. Authenticate with the rotating physical portal code.
3. Run `scripts/capture-ws350-views.zsh <device-host-or-ip>`.
4. Capture all 32 deterministic views.
5. Verify the retained System image has the portal-code region redacted.
6. Verify no printer configuration/settings export exists in the capture bundle.
7. Review all 32 captures for clipping, overlap, stale text, inconsistent semantic color use, and missing selected/disabled/error state presentation.

## Required result

The candidate may be marked **physically validated** only when all applicable checks above actually ran and passed on the target device. Record failures rather than treating them as cosmetic follow-ups.

- touch affordances fit and respond reliably on the 480×320 physical screen;
- visual hierarchy is calm, legible, and semantically consistent rather than decorative/rainbow-coded;
- staged addressing is non-destructive before guarded Apply;
- rotation preview/commit is guarded and recoverable;
- portal/session authentication remains intact;
- no Light/Pause/Resume/Stop/Power regressions;
- Speaker/MIC ECHO, recovery, settings persistence, and OTA remain healthy.

Physical validation does not itself promote the release to `stable`; acceptance/promotion still follows the project release gate and must retain the exact source/artifact evidence.
