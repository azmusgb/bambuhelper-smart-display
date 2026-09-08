# Workshop OS v11.25 RC6 — Secure Physical Acceptance

RC6 is the secure follow-up to the RC5 UI5 runtime-validation build. RC5 proved the intended renderer, Full-image install path, station-LAN no-code test path, and basic runtime identity on the real WS350. RC6 removes that temporary bypass and is the candidate that must be physically validated before v11.25 can be accepted.

Automated CI may establish `implemented -> built -> tested`. It does not establish physical validation, acceptance, or stable promotion.

## Candidate identity

Record before testing:

- exact PR head SHA;
- artifact ID and artifact digest;
- Full BIN SHA-256 and size;
- OTA/app BIN SHA-256 and size;
- image actually flashed and flash method;
- WS350 hardware identity;
- test date/time.

For a device already on the compatible Workshop OS partition layout, OTA/app update is permitted. For a cross-line migration from legacy Waveshare Home, use the Full image at `0x0`; never use OTA across incompatible partition layouts.

## Pre-flash build evidence

The exact artifact under test must come from a successful RC6 exact-head workflow that proves:

- `ws_lcd_350` build passed;
- `jc3248w535` regression build passed;
- compiled secure binary verification passed;
- the Full image contains the exact app image at `0x10000`;
- retained RC5 portal CSS is embedded exactly;
- temporary no-code runtime markers are absent;
- reconstructed `settings.cpp` contains no embedded NUL byte and the historical `null character(s) preserved in literal` compiler warning is absent.

A binary from an older head remains superseded even when its firmware SHA happens to match the current candidate; exact-head artifact identity is part of the acceptance evidence.

## Mandatory runtime identity

After boot, `GET /recovery/status` must report:

- `build = Workshop OS v11.25 RC6 Secure Physical Acceptance`;
- `safeMode = false` during normal acceptance;
- `authMode = portal-code` on normal station LAN;
- `apMode = false` on normal station LAN;
- `stationConnected = true`;
- a non-empty `stationIp`;
- `webReady = true`;
- responsive touch health.

The status payload must also expose `softApIp` explicitly rather than making the primary IP field carry hidden mode semantics.

## Secure access — mandatory

Before login on normal station LAN:

1. `GET /login` returns the Workshop OS secure sign-in page (`200`).
2. `GET /` redirects to `/login` (`303`).
3. System on the WS350 visibly shows the current 10-character portal code.
4. The code displayed on System is the code accepted by `/login`.
5. Invalid code submission is rejected and does not create an authenticated session.
6. Valid code submission redirects to `/` and creates the boot-scoped session.
7. Authenticated `GET /` returns `200`.
8. Authenticated protected GET routes succeed.
9. Unauthenticated protected mutations remain rejected.
10. Authenticated mutating browser/API requests without accepted same-origin provenance remain rejected.

Reboot the WS350 and prove:

- the physical portal code changes;
- the previous boot's session cookie no longer authorizes access;
- the new code is required for the new boot.

Do not retain or publish an unredacted System framebuffer that contains the live portal code.

## Recovery / AP boundary

Prove that secure station-LAN behavior did not break recovery:

- ordinary AP/setup mode does not become a blanket authorization bypass;
- only the intended setup routes remain public in ordinary AP mode;
- deliberate Recovery Safe Mode keeps its intended recovery-route exception;
- settings export and other secret-bearing surfaces do not become public merely because AP mode is active;
- recovery page, touch recovery, reboot, rollback path, and application firmware recovery remain reachable according to the established policy.

## Renderer proof

Every primary screen must retain its RC5/UI5 renderer fingerprint:

- Home `UI5-H`
- Printer `UI5-P`
- Workshop `UI5-W`
- More `UI5-M`
- System `UI5-S`

RC6 is a security/acceptance overlay, not a new visual-authority branch. If a fingerprint disappears, stop acceptance and resolve the active renderer before changing styling.

## Home

- printer state remains dominant;
- job/progress appears only when evidence exists;
- material/network remain secondary;
- attention and next action remain clear;
- inventory remains `Unknown` unless authoritative Filament Inventory linkage exists;
- no label/value clipping at 480×320;
- access disclosure no longer claims `TEST / NO CODE`.

## Printer

### Status

- `STATUS / AMS / CONTROL` is obvious and finger-sized;
- printer state outranks telemetry;
- job, percent, remaining time, layer and temperatures remain readable;
- unavailable telemetry remains unavailable rather than being fabricated.

### AMS

- all bays fit cleanly;
- active bay is structural, not inferred from color;
- printer-reported material/color/remain are readable;
- inventory identity remains `Unknown` unless an authoritative device contract supplies linkage;
- no firmware-side color/material spool matching is present.

### Control

- Light, Pause/Resume, mapped Power and Stop remain explicit;
- disabled actions look disabled;
- normal Stop tap does not stop a print;
- hold progress is visible and deliberate;
- mapped power retains the active-print warning/guard.

## Workshop / More / System

- timer hierarchy remains clear;
- More remains a launcher, not a dense settings wall;
- System separates Device Health, Audio, Network and Access;
- System Access card shows the actual current portal code legibly;
- `PORTAL CODE` language is used consistently;
- speaker, mic echo and event controls still function;
- network/touch/recovery state remains visible.

## Touch / layout

- routine targets remain at least 48 px where geometry permits;
- no hidden long-press is needed for routine navigation;
- guarded/destructive holds show progress;
- pressed feedback appears promptly;
- small finger drift does not trigger adjacent actions;
- no clipping, overlap, illegible density, or touch/display offset is present.

## Automated framebuffer capture

Use:

```text
scripts/capture-ws350-ui5.zsh <device-ip>
```

For RC6 the helper should detect authentication, prompt for the portal code without echoing it, authenticate with a temporary cookie, and redact the System access-code region before retained image output.

Review all retained PNGs for:

- 480×320 dimensions;
- expected UI5 fingerprint;
- no blank/stale frame;
- no clipping/overlap;
- readable hierarchy;
- semantic state distinction;
- correct redaction on System.

## Portal UI

At desktop and phone widths verify:

- secure sign-in page uses Workshop OS branding;
- code field and Sign In control are at least 52 px high;
- keyboard focus is visible;
- invalid-code error is clear;
- primary portal navigation/selected state is clear after login;
- coarse-pointer controls remain finger-sized;
- no horizontal overflow;
- reduced-motion and forced-colors retain state/focus communication.

## Exit gate

Do not mark RC6 `physically validated` until this complete checklist runs against the exact artifact and passes.

Do not mark v11.25 `accepted` or `stable` from CI alone. Promotion requires the exact secure RC6 artifact to pass real-device security, UI/touch, printer-control, audio/mic, Wi-Fi/reconnect, OTA, recovery, and rollback acceptance with hashes and artifact identity recorded.
