# Workshop OS v11.25 UI Source of Truth

## Current implementation authority

Workshop OS firmware remains owned by `azmusgb/bambuhelper-smart-display`.
The pinned upstream BambuHelper commit supplies the base firmware implementation;
this repository supplies the Workshop OS product behavior, safety hardening and
WS350 presentation layer.

For the v11.25 physical-acceptance line, the **final native UI presentation** is
owned by the RC5 fragment set:

- `firmware/ui-v11.25-rc5/shared.cppfrag`
- `firmware/ui-v11.25-rc5/home.cppfrag`
- `firmware/ui-v11.25-rc5/printer.cppfrag`
- `firmware/ui-v11.25-rc5/workshop.cppfrag`
- `firmware/ui-v11.25-rc5/more_system.cppfrag`

`apply_workshop_os_ui_overhaul_v11_25_rc5.py` injects those final renderer
functions into the reconstructed `src/smart_hub.cpp`. Earlier RC1-RC4 UI patchers
remain lineage/migration history for this candidate; they are not the final
presentation authority once RC5 has been applied.

The local browser portal is ultimately compiled from:

- reconstructed `web/app.js`
- reconstructed `web/app.css`
- final override `assets/v11_25_rc5_portal.css`

## Predominant runtime files

On the built device, most native 480x320 display behavior resides in the generated
`src/smart_hub.cpp`. It owns screen routing, native draw functions, touch mapping,
header/navigation, status/AMS/control presentation and guarded action feedback.

The browser portal is separate. `web/app.js` owns portal interaction/state while
`web/app.css` owns browser presentation. Do not treat browser CSS as the source of
the native LCD appearance.

## RC5 runtime proof

RC5 adds a visible test fingerprint to each primary renderer:

- Home: `UI5-H`
- Printer: `UI5-P`
- Workshop: `UI5-W`
- More: `UI5-M`
- System: `UI5-S`

A physical acceptance capture must show the expected fingerprint on each screen.
That proves the captured framebuffer came from the intended RC5 renderer rather
than a retained or legacy path.

## Compiled-binary proof

`scripts/verify_ui_binary_v11_25_rc5.py` validates the built bytes, not only
source text. It requires:

1. Full image contains the exact application/OTA image at `0x10000`.
2. RC5 native screen markers and fingerprints are present in the application.
3. The exact final RC5 CSS layer appears inside the gzip-compressed web assets
   embedded in the application image.

This gate closes the previous evidence gap where source validation could pass
without proving that the intended UI reached the shipped binary.

## Physical capture

Use `scripts/capture-ws350-ui5.zsh <device-ip>`.

The script:

- works with the temporary no-code physical-test build;
- falls back to portal-code authentication when a secure build requires it;
- enumerates the device's `/hub/views` catalog;
- switches views through `/hub/show`;
- captures `/hub/frame.ppm`;
- requires 480x320 frames;
- rejects obviously blank framebuffers;
- writes per-frame SHA-256 values and expected UI5 fingerprints;
- redacts the System access-code region on authenticated/secure captures before
  retaining PPM/PNG output.

## Release boundary

RC5 may reach `implemented -> built -> tested` through automated gates. It is not
`physically validated`, `accepted`, or `stable` until real WS350 capture and touch
acceptance pass.

The temporary `WORKSHOP_OS_TEMP_NO_CODE_LAN` mode remains a promotion blocker.
After physical UX acceptance, remove that bypass, rebuild an exact-head secure
candidate, rerun the binary gate and physically validate the secure build before
promotion.

## Post-acceptance cleanup target

After RC5 is physically accepted, collapse the accepted generated source into a
canonical Workshop OS source tree and retire superseded UI patch layers. Do not
perform that destructive cleanup before the replacement source is proven
bit-equivalent/behavior-equivalent and the rollback path is preserved.
