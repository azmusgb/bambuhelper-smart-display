# Upstream BambuHelper sync policy

Workshop OS v11.19.1 is reproducibly based on BambuHelper commit `8cb1cbbb6d3c175af91989e8ebe1bbdcbe848ac4`.

As of 2026-09-03, upstream `Keralots/BambuHelper` `main` is `f86555c4e050ccee73d8005ac5dfc77baa101b5c`, **9 commits ahead** of the accepted pin. The upstream delta touches display/UI state, smart-plug control, MQTT state handling, touch behavior, settings and browser code — all areas that overlap Workshop OS behavior.

The pin is therefore deliberate, not forgotten dependency drift. The accepted v11.19.1 source and its 22-view physical acceptance describe behavior against this exact baseline.

## Sync rule

Never silently repin `main` or the reusable firmware gate. An upstream update is a dedicated firmware candidate because a clean compile does not prove UI, power-control or touch equivalence.

A repin must pass:

1. complete Workshop OS patch-stack reconstruction against the proposed upstream SHA;
2. explicit review of every upstream-changed file that overlaps Workshop OS patches;
3. browser JavaScript validation;
4. native `ws_lcd_350` build;
5. shared `jc3248w535` 320×480 regression build;
6. existing device/safety/visual/rendered-fit contracts;
7. physical checks for touch, display retention, printer-off state, power-confirm geometry, Light/Pause/Resume/Stop/Power, Speaker/MIC ECHO, settings persistence, OTA and recovery;
8. authenticated WS350 framebuffer recapture when the upstream delta touches display/rendering behavior;
9. update of the pinned SHA only after the candidate is accepted.

The current upstream delta includes a newer printer-off hold-to-power-on interaction. That may be useful, but it overlaps Workshop OS power UX and must be evaluated through the sync gate rather than copied opportunistically.
