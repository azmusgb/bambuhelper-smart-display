# Workshop OS candidate stack — 2026-09-06

This snapshot records the current hardware/software candidate chain without redefining the accepted Workshop OS baseline.

## Authoritative accepted baseline

- Repository: `azmusgb/bambuhelper-smart-display`
- Accepted source line: **Workshop OS v11.22 Display Expert RC1**
- Accepted source commit: `b6ff19e8617a8cceb380ea3c3621c54ea0048f11`
- Physical acceptance: **passed on real WS350 hardware**
- Accepted date: 2026-09-04
- Static installer remains intentionally more conservative at v11.19.1.

`releases/current.json` remains authoritative for accepted source, direct candidate, `main`, and static download-channel state.

## Direct physical gate

### PR #76 — v11.23 Network / Locale / Layout Expert RC2

- Branch: `feature/v11-23-network-locale-layout`
- Direct-to-`main` candidate
- Status: **physical acceptance required**
- Purpose: explicit touch-safe timezone/network/rotation flows, larger targets, visible staged state, guarded apply/commit semantics, and authenticated capture/security preservation.

This remains the first hardware gate that must be physically resolved before the stacked chain can be promoted.

## Stacked follow-on chain

These candidates contain substantial implementation, but they are not independently promotable while their base chain remains physically unaccepted.

| PR | Candidate | Relationship | Current meaning |
| --- | --- | --- | --- |
| #77 | v11.24 Audio Console RC1 | stacked on #76 | Audio/mic controls implemented; physical speaker/mic acceptance still required. |
| #83 | v11.25 Workshop Companion BLE RC1 | stacked on #77 | BLE orchestration-only Companion path implemented; no printer/power authority moves into BLE. |
| #87 | v11.26 Workshop Companion Web RC1 | stacked on #83 | iPhone-first device-hosted web Companion implemented over guarded existing control routes. |
| #88 | v11.27 Workshop Companion Link RC1 | stacked on #87 | Consolidated state envelope, volatile phone photo transfer, and tighter mobile interaction handling. |
| #91 | v11.29 Companion Viewer + Acceptance Open LAN RC1 | later stacked candidate | Adds physical viewer work plus WS350-only open-LAN acceptance policy for testing. Candidate-only security decision; not stable authority. |
| #92 | v11.30 Unified Web + Companion RC2 | stacked on #91 | Unifies standard web + Companion and fixes phone-photo viewer state-machine reliability. Exact-head CI is green; physical acceptance still required. |

### v11.30 exact-head software evidence

PR #92 head `eb8bb8f9f8787ad6b4bcc9ce5e6e308af515a3c0` passed both:

- repository `Validate` workflow;
- `Workshop OS Firmware Gate — v11.30 Unified Web + Companion RC2`.

That proves the candidate built and passed its software-side contract checks. It does **not** prove WS350 physical acceptance.

## Independent intelligence work

### PR #90 — Workshop Intelligence v1

PR #90 adds an iPhone/on-device intelligence foundation with strict advisory-only behavior, structured output, deterministic grounding, and safety tests.

Important boundary:

- it does not change Workshop OS firmware bytes;
- it does not move printer, smart-plug, OTA, recovery, settings, or inventory authority into the model path;
- it is not a substitute for Filament Inventory's authoritative grounded Assistant or device contract;
- any later product integration must preserve the single inventory authority and explicit trust boundary.

## Security note on the open-LAN acceptance branch

PRs #91/#92 intentionally experiment with a WS350-only normal-LAN acceptance mode where portal-code login is disabled by default while same-origin mutation guards and other safety boundaries remain.

Treat this as **candidate-only test policy**, not an accepted permanent security architecture. Before any stable promotion, explicitly decide and record the intended production authentication model, then physically validate it. Do not let temporary acceptance convenience silently become stable security policy.

## Promotion rule

Keep the release states distinct:

`implemented -> built -> tested -> runtime validated -> physically validated -> accepted -> stable`

The current stack demonstrates significant implementation beyond v11.23. That implementation must remain labeled as stacked candidate work until the dependency chain is physically accepted and recovery/migration evidence is recorded.

## Recommended next sequence

1. Resolve PR #76 physical WS350 acceptance first.
2. Physically validate dependent audio behavior from #77.
3. Decide whether the later Companion chain should be accepted incrementally or consolidated into one new physical candidate from the accepted base.
4. Reconcile the normal-LAN authentication policy before stable promotion.
5. Record exact candidate SHA, Full/OTA artifact hashes, recovery path, and physical acceptance result.
6. Only then advance `releases/current.json` and stable release metadata.
