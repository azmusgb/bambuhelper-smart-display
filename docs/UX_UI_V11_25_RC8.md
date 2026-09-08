# Workshop OS v11.25 RC8 — Physical UI Polish

RC8 is the post-RC7 physical-screen refinement for the Waveshare WS350 (480×320 landscape). It preserves RC7 authentication, printer-control semantics, inventory isolation, OTA/recovery behavior, and portal runtime fixes.

## Locked RC8 changes

1. **Touch targets ≥48 px** — remaining physical helper targets are raised to at least 48 px, including tool presets/actions, display pager, and System sub-navigation.
2. **Focused settings wizard** — Network/System settings are split into focused pages: Startup, Clock, Date, Local Name, Timezone, Address, Review. Each normal page presents one primary concept with Back/Next navigation.
3. **Home reduced further** — Home is simplified to printer state, compact Material/Network cards, and a concise Status rail. Secondary explanatory copy is removed.
4. **Stronger selected navigation** — the active bottom-navigation destination uses a filled accent treatment rather than a subtle line-only state.
5. **Shorter header** — physical header height drops from 40 px to 36 px and uses a smaller brand mark/status pill.
6. **User-facing language** — implementation wording is removed from ordinary paths. Engineering metadata belongs in diagnostics, not routine controls.
7. **Workshop timer dominance** — the timer becomes the full-width primary surface; Note and Material become secondary strips.
8. **Simplified System** — the normal System screen contains Device, Network, and Local Access only. Advanced details are explicitly directed to Portal > Diagnostics.
9. **Stronger guarded actions** — Stop, network apply, and rotation apply use a clearer KEEP HOLDING state and thicker five-segment progress feedback tied to the same 650 ms action threshold.
10. **Normalized empty states** — routine empty/error states use the pattern **problem → explanation → action/destination**, e.g. NO PRINTER → Connect a printer to begin → OPEN LOCAL PORTAL.

## Physical acceptance

RC8 must not be promoted stable until the WS350 confirms:

- HOME → PRINTER → WORKSHOP → MORE → SYSTEM traversal with first-tap response.
- No clipped headings or overlap at 480×320 rotation 1.
- All routine controls are comfortably finger-sized; no hidden action depends on a long press.
- STOP visibly enters KEEP HOLDING and displays the full progress treatment before execution.
- Network wizard Back/Next and address controls are usable without precision tapping.
- System shows the current boot-scoped portal code but no firmware slot/fingerprint/runtime internals.
- Printer, material, network, and AMS empty states are understandable without implementation terminology.
- RC7 portal-code authentication, same-origin mutation guard, Safari pattern fix, JS boot guards, recovery, and inventory isolation remain intact.

## Release boundary

RC8 changes presentation and touch interaction only. It must not add spool identity inference, cross-profile inventory lookup, weakened authentication, altered printer-command authorization, or automatic power/stop behavior.
