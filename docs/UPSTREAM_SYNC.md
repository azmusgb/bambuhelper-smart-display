# Upstream BambuHelper sync policy

Workshop OS is currently pinned to BambuHelper commit `8cb1cbbb6d3c175af91989e8ebe1bbdcbe848ac4` for deterministic v11.5 reconstruction and physical acceptance.

As of 2026-09-03, upstream `Keralots/BambuHelper` `main` is at `f50507d609c644ccf355dc89f385ddf1dc34f2b1`, seven commits ahead of the pin. Those commits include changes in display state/rendering, smart-plug status/control, AXS touch release handling, MQTT state parsing, and print-substage presentation.

The pin is deliberate. Do not silently repin an active physical-acceptance candidate: upstream changes in these areas can alter the exact behavior being accepted even when compilation succeeds.

## Next sync gate

After v11.5 physical acceptance (or before promotion if explicitly chosen), create a dedicated upstream-sync candidate and require:

1. complete Workshop OS patch-stack reconstruction against the new upstream SHA;
2. `ws_lcd_350` native build;
3. shared `jc3248w535` regression build;
4. browser JavaScript validation;
5. diff review for overlapping Workshop OS modifications;
6. physical checks for touch, display retention, printer-off state, power-confirm geometry, Light/Pause/Resume/Stop/Power, Speaker/MIC ECHO, settings persistence, OTA and recovery;
7. update of the pinned SHA only after those gates pass.

This file exists so dependency freshness is explicit and auditable rather than inferred from an old SHA in CI.
