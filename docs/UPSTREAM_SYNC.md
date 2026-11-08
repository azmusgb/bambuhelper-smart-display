# Upstream BambuHelper sync policy

## The baseline and the pinned upstream (from 7 Nov 2026)

The WS350 image is built from two things: the pinned upstream `Keralots/BambuHelper` commit
`8cb1cbbb6d3c175af91989e8ebe1bbdcbe848ac4` and `baseline/`, the checked-in changes Workshop OS made to it
(32 files: 25 changed upstream files and 7 added ones, in `baseline/files/`; `baseline/UPSTREAM` names the repository
and commit; `baseline/MANIFEST.sha256` checks the files; `baseline/deleted.txt` lists upstream files removed, none today).
`scripts/baseline.py apply` clones the pin and lays the baseline over it; `scripts/run_os12_platform_local.sh` does that
where it used to run the v8 to v11.28 layers. The newer layers (Workshop OS 12 platform, More, tabs, display kit) still
apply on top of the baseline as before.

The v8 to v11.28 layers that used to rebuild the baseline (about 90 `apply_smart_home_*` and `apply_workshop_os_*`
scripts, their runners, `vendor/` and `firmware/ui-v11.*`) are deleted. They were proven equal to the baseline when it was
checked in: same built tree and same `firmware.bin` for the same source SHA and checkout path (PR 274). The history has
them if you need to read how a change got in.

**The baseline is Workshop OS's source.** It is edited directly, in normal PRs, like any other file in the repository. It
is not regenerated from anything. Upstream
BambuHelper is the pin's history, not a live dependency.

**Taking an upstream update** is still a dedicated candidate (the sync rule below). With the baseline it is a three-way
merge instead of a layer replay:

1. `git fetch` upstream and take the diff `PIN..NEW` (`git diff 8cb1cbb..NEW`).
2. For each changed file that is also in `baseline/files/`, merge the upstream change into the baseline copy by hand (the
   baseline copy is the "ours", the old pin is the base). Files not in the baseline come from the new pin untouched.
3. Set `baseline/UPSTREAM` to the new commit, run `python3 scripts/baseline.py manifest`, and update `deleted.txt` if upstream
   file removals matter.
4. Run the whole sync gate below (build both boards, validators, captures, physical checks).

Workshop OS **v11.22 Display Expert RC1** is the physically accepted source baseline and is reproducibly reconstructed from BambuHelper commit `8cb1cbbb6d3c175af91989e8ebe1bbdcbe848ac4` plus the accepted Workshop OS evolution stack. The active v11.23 hardware candidate and stacked v11.24 Audio Console candidate continue from that same deliberate pin.

As of **2026-09-04**, upstream `Keralots/BambuHelper` `main` is `95597e4d633950bc00bb1cd50ce59da5c375a1fa`, **11 commits ahead** of the Workshop OS pin. The upstream comparison overlaps areas Workshop OS actively modifies, including display/rendering, touch behavior, MQTT/HMS state, settings, browser UI, smart-plug behavior, and printer-power interaction.

Notable overlapping upstream changes include:

- **Printer Off hold-to-power-on** — a direct hold gesture reuses the existing power-confirm path. This overlaps Workshop OS mapped-power and guarded-control UX.
- **True night blackout + wake override** — night brightness `0` can now fully blank the display with a temporary wake override, plus an option to keep the status LED dark during the night window. This overlaps Workshop OS display, input, backlight, LED, and settings behavior.
- **AMS auto-refill HMS alert suppression** — known self-resolving/normal auto-refill notices are excluded from persistent alert surfaces while remaining visible in detailed HMS/status output. This overlaps Workshop OS alert presentation and HMS-derived state.

Earlier upstream commits between the pin and current head also touch `include/bambu_state.h`, `include/tasmota.h`, `include/web_pages.h`, `src/bambu_mqtt.cpp`, `src/button_touch_axs.cpp`, `src/clock_mode.cpp`, `src/display_split.cpp`, `src/display_ui.cpp`, `src/main.cpp`, `src/settings.cpp/.h`, `src/tasmota.cpp`, `src/web_server.cpp`, `src/web_template.cpp`, and `web/app.js`, among other files.

The pin is deliberate, not forgotten dependency drift. A newer upstream SHA is **not** automatically safer merely because it is newer: these changes intersect the exact touch, display, alert, settings, authentication, and power behavior currently under Workshop OS physical acceptance.

## Sync rule

Never silently repin `main`, the direct hardware candidate, a stacked candidate, or the reusable firmware gate. An upstream update is a dedicated firmware candidate because a clean compile does not prove UI, authentication, power-control, HMS, audio, or touch equivalence.

A repin must pass:

1. complete Workshop OS patch-stack reconstruction against the proposed upstream SHA;
2. explicit review of every upstream-changed file that overlaps Workshop OS patches;
3. portal-auth/security contract validation when `web_server`, web pages, settings, or session paths overlap;
4. browser JavaScript validation;
5. native `ws_lcd_350` build;
6. shared `jc3248w535` 320×480 regression build;
7. existing device, safety, visual, rendered-fit, settings-parity, and fail-closed control contracts;
8. physical checks for touch, display retention, night/wake behavior when relevant, printer-off state, power-confirm geometry, Light/Pause/Resume/Stop/Power, Speaker/MIC ECHO, settings persistence, login/session behavior, OTA and recovery;
9. HMS/alert behavior review when the upstream delta changes printer-state or alert classification;
10. authenticated WS350 framebuffer recapture when the upstream delta touches display/rendering behavior;
11. update of the pinned SHA only after the dedicated sync candidate is physically accepted.

## Active candidate interaction

PR **#76** (v11.23 RC2) and PR **#77** (stacked v11.24 Audio Console) are already changing touch, network/layout, display-rotation, and audio behavior. Repinning either candidate in place would confound two independent acceptance deltas. Finish or deliberately replace that candidate stack before introducing an upstream-sync candidate.

Until the sync gate is run, `8cb1cbbb6d3c175af91989e8ebe1bbdcbe848ac4` remains a **reproducibility boundary**, not a claim that Workshop OS is synchronized to upstream `main`.
