# Workshop OS UI Review Contract

Workshop OS UI review is intentionally split into artifact review and project-level system review. A correct HTML/CSS/JS review is necessary, but it cannot by itself establish command safety, recovery integrity, authority boundaries, or physical acceptance.

The machine-readable contract is `contracts/workshop-ui-review-v1.json` and is validated in CI by `scripts/validate_workshop_ui_review_contract.py`.

## Review layers

### 1. Artifact

Review the concrete UI artifact for:

- valid markup and deterministic initial DOM state;
- fail-safe initialization: privileged and capability-dependent controls start disabled or hidden until validated state enables them;
- accessible navigation, keyboard/focus behavior, live-region boundaries, loading/empty/error states, and reduced-motion behavior;
- no optimistic visual state that contradicts the authoritative device state.

Artifact review can identify HTML/CSS/JS defects. It must not claim device acceptance.

### 2. Control plane

Every mutation must pass the control boundary rather than calling printer/device transport directly.

Before a printer command is eligible, the system must account for:

- printer configured;
- connection/channel readiness;
- telemetry freshness;
- command validity for the current printer state;
- the action's safety class.

The normalized UI vocabulary is:

- `Fresh`
- `Stale`
- `Unavailable`
- `Connecting`
- `CommandChannelUnavailable`
- `InvalidForCurrentState`

Actions are classified as:

- `ordinary`
- `guarded`
- `destructive`
- `recovery-impacting`

Routine controls should not inherit long-press behavior. Long-press or an equivalent deliberate guard is reserved primarily for destructive or recovery-impacting actions.

### 3. Recovery

Recovery is a product rail, not a single page or button. Review:

- OTA structure validation;
- exact board/hardware compatibility;
- artifact byte count and SHA-256 verification;
- inactive-partition/update policy;
- rollback or known-good recovery path;
- interrupted upload/update behavior;
- invalid network configuration and reconnect behavior;
- exact firmware/source identity after reboot.

Full-image flashing at offset `0x0` remains recovery/cross-line migration behavior, not normal device-native OTA.

### 4. Architecture

The UI must preserve authority boundaries:

- Filament Inventory is authoritative for inventory identity, ownership, quantity evidence, location, and placement semantics.
- Workshop OS is authoritative for WS350 firmware, touchscreen UX, device controls, networking, OTA/recovery, and physical acceptance.
- Unknown remains `Unknown`.
- Workshop OS must not create AMS placement from color/material resemblance.
- Provider/user cloud secrets do not belong on the WS350.
- Assistant-enabled stable firmware requires least-authority, revocable device credentials.

Printer model/serial identity may be used to resolve capabilities. Feature code must consume a normalized capability set rather than scattering direct model-string checks through the UI. Unknown capabilities fail closed.

### 5. Acceptance

Keep these states distinct:

`implemented -> built -> tested -> runtime-validated -> production-validated -> physically-validated -> accepted -> stable`

No review, CI run, static image inspection, or HTML cleanup may skip states. Record exact source SHA and artifact identity with the evidence used for each promotion.

## Operation feedback model

Substantial operations should expose an explicit state machine rather than relying on a spinner or `aria-live` alone:

- `Idle`
- `Pending`
- `Success`
- `RecoverableError`
- `FatalError`

For OTA/update work, user-visible progress should distinguish validation, transfer, verification, write, reboot, reconnect, and post-reboot identity verification where those stages are observable.

## Priority order

When review findings compete, fix in this order:

1. fail-safe markup and initialization;
2. control semantics and stale-state guards;
3. accessibility architecture;
4. privileged API hardening;
5. recovery and OTA behavior;
6. maintainability/refactoring;
7. polish.

SPA/hash routing is not a WS350 requirement. Predictable Back behavior and safe workspace persistence are more important on the 480x320 appliance surface.

## Review scope rule

A reviewer should state which evidence was available.

- If only HTML/CSS/JS is supplied, report artifact defects and clearly identify project-level checks that cannot be established from the artifact.
- If the roadmap/contracts/runtime source are supplied, apply the full system review.
- Missing project context is a scope gap, not proof that the artifact satisfies or violates an unseen invariant.

This distinction prevents both false confidence and unfair review findings while preserving the product's safety and acceptance requirements.
