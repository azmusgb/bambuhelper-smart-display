# Release Process

Workshop OS deliberately separates **accepted source baseline**, **current `main` state**, **active candidate**, and **static firmware download** state. Do not collapse these into one ambiguous version label.

## 1. Accepted source baseline

`releases/current.json` records the last firmware source that passed required real-device acceptance:

- accepted Workshop OS version;
- the firmware commit that was physically accepted;
- acceptance state/evidence;
- whether an active candidate exists;
- any unaccepted firmware delta already present on `main`;
- the separately managed static download channel.

The accepted firmware commit is the hardware baseline even when later documentation commits—or, exceptionally, an unaccepted firmware delta—exist on `main`.

## 2. Candidate creation

For firmware work:

1. branch from current `main`;
2. open one candidate PR to `main`;
3. update the reusable `.github/workflows/firmware-candidate.yml` only when the reconstruction recipe/baseline changes;
4. update `releases/current.json` to describe the candidate when a formal candidate is established;
5. do not create version-named workflow files.

Keep candidate binaries in Actions artifacts.

## 3. CI acceptance

Firmware candidates must pass the gates appropriate to their scope. The normal hardware gate includes:

- deterministic reconstruction from the pinned upstream baseline;
- device/safety contracts;
- current visual/rendered-fit contracts;
- browser JavaScript validation;
- native `ws_lcd_350` build;
- shared `jc3248w535` regression build;
- Full-image merge;
- OTA/full artifact packaging.

Failures in a contract gate are release blockers until explained and intentionally changed.

## 4. Runtime, unattended hardware, and physical acceptance

Hardware-facing work uses two deliberately different evidence classes.

**Required before candidate merge when applicable:**

- exact-head CI and deterministic reconstruction;
- exact artifact identity and hash capture;
- guarded installation of the exact candidate;
- runtime source-identity verification;
- machine-verifiable 480×320 route/framebuffer checks;
- machine-verifiable control, media lifecycle, health, freshness, and fail-closed checks that can be observed deterministically;
- recovery capture when the installation procedure requires it.

These checks must be unattended after the guarded invocation. Routine candidate/merge testing must not require the operator to answer interactive `y/n/u` prompts.

**Reserved for physical acceptance/promotion:**

- real LCD readability, color, and panel artifacts;
- finger touch comfort and responsiveness;
- audible speaker quality/distortion;
- microphone intelligibility/acoustic quality;
- recovery/rollback exercises when due for the release. A same-state full-image recovery round-trip may prove the `0x0` recovery/write/boot mechanism without claiming a historical-version rollback; those evidence types must remain distinct.

Interactive physical scripts may be used as optional diagnostic/audit tools, but they are not ordinary merge gates. Automation must not convert sensory observations into fabricated physical truth.

Record unattended objective evidence separately from sensory/recovery evidence. A successful unattended hardware run may advance a candidate through runtime validation and support merge, but it does not by itself establish `physically validated`, `accepted`, or `stable`.

## 5. Source merge and promotion

A hardware-facing candidate may merge to `main` after its required exact-head CI and applicable unattended objective hardware gates pass. Merge is not acceptance.

If physical acceptance has not yet passed, immediately record the merged source as **merged-unaccepted**:

- keep the last physically accepted version/commit in `source`;
- set `candidate` to `null` if there is no longer an open candidate PR;
- record the code currently present on `main` in `mainState` with `status: merged-unaccepted`;
- record the originating PR/branch and exact merge commit;
- preserve the exact tested candidate commit and artifact identity;
- record CI, install, runtime, and unattended acceptance separately from `physicalAcceptance: pending`;
- do not promote its binaries into `release.json`, the stable device channel, or Netlify;
- complete required sensory/recovery evidence before accepted/stable promotion, or intentionally revert the unaccepted delta.

When physical acceptance is explicitly completed and accepted-source promotion is approved, update `releases/current.json` so:

- `channel` remains `accepted-source`;
- `version` is the accepted source version;
- `source.acceptedFirmwareCommit` identifies the exact physically accepted firmware commit;
- `source.physicalAcceptance` is `passed`;
- `candidate` is `null`;
- `mainState` is cleared only when the accepted-source metadata fully represents the code being promoted.

The lifecycle remains explicit:

`implemented -> built -> tested -> runtime validated -> merged-unaccepted -> physically validated -> accepted -> stable`

`merged-unaccepted` is a valid repository state, not an accepted release state.

## 6. Static download promotion

`release.json` / Netlify are a separate distribution decision. Do **not** automatically promote the newest accepted source into the static installer.

When intentionally promoting the download channel:

1. use binaries produced from an accepted exact head;
2. verify SHA-256/integrity metadata;
3. update Full and OTA paths together;
4. retain exactly one immediately previous physically accepted Full + OTA rollback pair;
5. remove older tracked binary generations in the same maintenance change;
6. run the static portal integrity gate.

## 7. Repository protection

`main` should use GitHub branch protection/rulesets so repository policy is enforced by the platform rather than documentation alone. Recommended minimums:

- require a pull request before merging;
- require the stable `merge-gate` status, which coordinates `Release Gate`, `Validate`, and the applicable firmware/static-installer workflows;
- keep the path classification current when adding canonical source or new build inputs, so firmware-facing changes cannot evade the reusable firmware gate;
- require branches to be up to date before merge;
- block force pushes and branch deletion;
- do not allow bypass of required checks for routine firmware promotion.

Physical acceptance remains a hardware promotion gate. CI and unattended runtime checks can prove objective machine-observable behavior, but they cannot prove sensory observations such as LCD appearance, finger feel, speaker quality, or microphone intelligibility. Record those claims only when actually observed.

## 8. Upstream synchronization

Repinning BambuHelper is its own candidate. Follow `docs/UPSTREAM_SYNC.md`; never mix a silent upstream repin into an unrelated feature or cleanup PR.

## 9. Emergency recovery

Recovery actions may temporarily bypass normal release cadence, but they do not erase the audit trail. Record what was flashed, why, the exact binary/hash when available, and restore the accepted metadata/workflow state after the emergency.
