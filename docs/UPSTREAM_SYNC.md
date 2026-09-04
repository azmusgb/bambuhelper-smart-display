# Upstream BambuHelper sync policy

Workshop OS v11.19.1 is reproducibly based on BambuHelper commit `8cb1cbbb6d3c175af91989e8ebe1bbdcbe848ac4`. Workshop OS v11.20 on `main` is reconstructed from that same pinned baseline plus the accepted Workshop OS evolution stack and the v11.20 portal-auth delta.

As of **2026-09-04**, upstream `Keralots/BambuHelper` `main` is `f86555c4e050ccee73d8005ac5dfc77baa101b5c`, **9 commits ahead** of the Workshop OS pin. The upstream comparison changes `include/bambu_state.h`, `include/tasmota.h`, `include/web_pages.h`, `src/bambu_mqtt.cpp`, `src/button_touch_axs.cpp`, `src/clock_mode.cpp`, `src/display_split.cpp`, `src/display_ui.cpp`, `src/main.cpp`, `src/settings.cpp/.h`, `src/tasmota.cpp`, `src/web_server.cpp`, `src/web_template.cpp`, and `web/app.js` in addition to README changes. Those areas overlap Workshop OS display state, touch behavior, MQTT state, settings, web UI and printer-power behavior.

The newest upstream head includes a Printer Off interaction that allows a direct hold-to-power-on gesture. That is potentially useful, but it overlaps Workshop OS mapped-power UX and therefore belongs in a dedicated upstream-sync candidate rather than an opportunistic cherry-pick.

The pin is deliberate, not forgotten dependency drift. The accepted v11.19.1 hardware baseline and the current v11.20 reconstruction are both defined against this exact upstream pin.

## Sync rule

Never silently repin `main` or the reusable firmware gate. An upstream update is a dedicated firmware candidate because a clean compile does not prove UI, authentication, power-control or touch equivalence.

A repin must pass:

1. complete Workshop OS patch-stack reconstruction against the proposed upstream SHA;
2. explicit review of every upstream-changed file that overlaps Workshop OS patches;
3. portal-auth/security contract validation when `web_server`, web pages or settings paths overlap;
4. browser JavaScript validation;
5. native `ws_lcd_350` build;
6. shared `jc3248w535` 320×480 regression build;
7. existing device/safety/visual/rendered-fit contracts;
8. physical checks for touch, display retention, printer-off state, power-confirm geometry, Light/Pause/Resume/Stop/Power, Speaker/MIC ECHO, settings persistence, login/session behavior, OTA and recovery;
9. authenticated WS350 framebuffer recapture when the upstream delta touches display/rendering behavior;
10. update of the pinned SHA only after the candidate is accepted.

Until that gate is run, the older SHA is a **reproducibility boundary**, not a claim that Workshop OS is synchronized to upstream `main`.
