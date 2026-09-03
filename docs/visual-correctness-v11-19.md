# Workshop OS v11.19 — Visual Correctness RC1

This release is intentionally constrained to physical UI correctness discovered by the deterministic v11.18 22-view capture baseline. It adds no new feature family.

## Scope

1. Restore the current 10-character portal code and device IP to the physical System screen.
2. Prevent AMS remaining-value sentinels (`-1`) from rendering as percentages.
3. Add a configured-but-inactive visual state for child settings whose parent feature is disabled.
4. Mark browser-persisted percentage values outside the physical preset set as `CUSTOM` without mutating them.
5. Shorten physical copy that visibly truncated in the v11.18 capture.
6. Present Power and Auto Off plug identity/configuration state consistently, including `IP REQUIRED`.
7. Reduce the Home hero to a two-line state/context treatment.
8. Simplify the More device/recovery summary and tile subtitles.
9. Replace `NO AMS TRAY` with the semantically accurate `NO ACTIVE TRAY` / `No active AMS tray` wording.
10. Add static visual-contract checks for the above plus preservation of all 22 authenticated capture views.

## Non-goals / invariants

- No new printer commands.
- No relaxation of v11.17 stale-state or fail-closed command behavior.
- No change to smart-plug slot mapping.
- No change to portal/input boundaries for Wi-Fi credentials, static addressing, plug IP/type/outlet, LED wiring, or arbitrary text.
- v11.18 authenticated framebuffer capture remains installed for physical recapture and visual comparison.
- Physical acceptance remains required before promotion/merge.
