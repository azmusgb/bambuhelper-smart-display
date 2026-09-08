# Workshop OS v11.25 UI Source of Truth

## Current implementation authority

Workshop OS firmware remains owned by `azmusgb/bambuhelper-smart-display`. The pinned upstream BambuHelper commit supplies the base firmware implementation; this repository supplies the Workshop OS product behavior, safety hardening and WS350 presentation layer.

For v11.25, the **final native UI presentation authority remains the RC5 fragment set**:

- `firmware/ui-v11.25-rc5/shared.cppfrag`
- `firmware/ui-v11.25-rc5/home.cppfrag`
- `firmware/ui-v11.25-rc5/printer.cppfrag`
- `firmware/ui-v11.25-rc5/workshop.cppfrag`
- `firmware/ui-v11.25-rc5/more_system.cppfrag`

`apply_workshop_os_ui_overhaul_v11_25_rc5.py` injects those final renderer functions into reconstructed `src/smart_hub.cpp`. Earlier RC1-RC4 UI patchers remain reconstruction lineage; they are not competing final presentation authorities once RC5 has been applied.

## RC6 secure acceptance overlay

`apply_workshop_os_secure_acceptance_v11_25_rc6.py` is deliberately **not** a new visual-authority branch. It applies after RC5 and owns only the secure-acceptance delta needed to turn the successful RC5 physical-test runtime into the candidate that can be promoted:

- removes `WORKSHOP_OS_TEMP_NO_CODE_LAN` from the build;
- restores boot-scoped portal-code authentication on normal station LAN;
- fails the secure build if the temporary no-code marker is reintroduced;
- keeps mutating same-origin protection;
- preserves route-scoped AP/setup/recovery exceptions;
- changes native no-code disclosure to secure portal-code disclosure;
- shows the actual `securityPortalCode()` on the physical System screen in both supported layouts;
- refreshes the inline login surface as `Workshop OS Secure Sign In` with touch/focus/accessibility treatment;
- adds non-secret runtime observability (`authMode`, `apMode`, `stationConnected`, `stationIp`, `softApIp`) to `/recovery/status`.

This separation prevents a security release step from silently forking the accepted UI geometry or creating a second firmware authority.

## Browser portal authority

The local browser portal is compiled from:

- reconstructed `web/app.js`;
- reconstructed `web/app.css`;
- final RC5 presentation override `assets/v11_25_rc5_portal.css`;
- the RC6 inline secure-login/recovery-status changes applied to generated `src/web_server.cpp`.

Browser CSS is not the source of native LCD appearance.

## Predominant runtime files

On the built device, most native 480×320 display behavior resides in generated `src/smart_hub.cpp`. It owns screen routing, native draw functions, touch mapping, header/navigation, status/AMS/control presentation, System access-code display and guarded action feedback.

`src/security_manager.cpp` owns the portal-code/session and same-origin authorization boundary. `src/web_server.cpp` owns the local HTTP routing, secure sign-in page and recovery/status exposure.

## Renderer proof

The visible UI5 fingerprint remains mandatory:

- Home: `UI5-H`
- Printer: `UI5-P`
- Workshop: `UI5-W`
- More: `UI5-M`
- System: `UI5-S`

RC6 must retain these fingerprints because it keeps RC5 as the presentation authority. A physical capture missing a fingerprint is a renderer/routing defect, not permission to infer that the intended UI ran.

## Compiled-binary proof

`scripts/verify_ui_binary_v11_25_rc6.py` validates shipped bytes, not only source text. It requires:

1. Full image contains the exact application/OTA image at `0x10000`.
2. RC6 secure build identity and UI5 renderer markers are present in the application.
3. Inventory authority markers (`Inventory: Unknown`, `Printer telemetry only`) and guarded Stop marker remain compiled in.
4. Secure portal/login and runtime-auth-observability markers are present.
5. `TEST / NO CODE` and the RC5 physical-test compile-guard message are absent.
6. The exact RC5 portal CSS presentation layer remains embedded inside the application gzip assets.

This closes both the presentation-evidence gap and the risk of accidentally packaging the RC5 test-only authentication boundary as RC6.

## Generated source snapshot

The source-snapshot workflow reconstructs the entire pinned lineage through RC5, applies RC6 last, runs the RC6 contract validator, and retains the resulting generated source plus hashes. The snapshot therefore represents the code that the RC6 build gate is intended to compile, while keeping the checked-in RC5 fragment set identifiable as the final presentation input.

## Physical capture

Use `scripts/capture-ws350-ui5.zsh <device-ip>`.

For a secure RC6 build the helper:

- detects that authentication is required;
- reads the portal code without terminal echo;
- submits it through stdin and stores only a temporary session cookie;
- enumerates `/hub/views` and captures `/hub/frame.ppm`;
- requires 480×320 frames and rejects obviously blank frames;
- records expected UI5 fingerprints and hashes;
- redacts the System access-code region before retaining PPM/PNG output;
- excludes printer configuration/settings exports.

The live portal code is authentication material and must not be retained in screenshots or logs.

## Release boundary

RC5 has real-device runtime evidence for exact build identity and the temporary no-code station-LAN behavior. That evidence is valuable but RC5 remains test-only and is not promotable.

RC6 may reach `implemented -> built -> tested` through exact-head automated gates. It may reach `runtime validated` only after the exact RC6 artifact runs on the WS350 and the secure runtime checks pass. It may reach `physically validated` only after the full real-device checklist in `docs/PHYSICAL_ACCEPTANCE_V11_25_RC6.md` passes.

Do not mark v11.25 `accepted` or `stable` until the secure RC6 artifact has passed the required physical UI/touch, authentication, controls, audio/mic, Wi-Fi, OTA, recovery and rollback acceptance gates.

## Post-acceptance cleanup target

After the secure v11.25 line is physically accepted, collapse the accepted generated source into a canonical Workshop OS source tree and retire superseded patch layers only after replacement source is proven behavior-equivalent and the rollback/recovery path is preserved. Do not perform destructive consolidation before secure physical acceptance.
