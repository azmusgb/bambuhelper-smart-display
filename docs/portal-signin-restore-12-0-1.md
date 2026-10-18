# Workshop OS 12.0.1 — Local Portal sign-in restore (security candidate)

## Purpose

Restore the documented Local Portal authentication model (`docs/portal-auth-v11-20.md`, `SECURITY.md`) on the OS12 line. The 12.0.0 build that is installed on the WS350 (`48ddd58`) does not have it.

## What 12.0.0 does

The OS12 UX recipe applied `apply_workshop_os12_code_free_portal.py` as its final layer (added 2026-09-21 in PR #122, commit `542e6c3`, made final in `bbb98a4`). That overlay:

- replaced `securityAuthorize()` with "mutations need `sameOrigin()`, everything else is allowed";
- stopped generating the portal code, redirected `/login` to `/`, and removed the "Require access code" setting;
- left `sameOrigin()` starting with `if (server.header("X-BambuHelper-Client") == "1") return true;`.

On the trusted-LAN assumption this meant:

- every GET is anonymous on the LAN. That includes `/status`, `/hardware/health`, `/hub/frame.ppm` (screen capture), `/settings/export`, `/debug`, and `/printer/access-code`, which returns the printer's LAN access code. That code can control the printer over MQTT;
- any non-browser LAN client could POST any mutation, including `/printer/control` (Stop), `/printer/power`, `/os12/update/install`, `/ota/upload` and `/reset`, by adding `X-BambuHelper-Client: 1`. A browser can't send that header cross-site without a CORS preflight, which the device never approves, so drive-by web pages were blocked. LAN programs were not;
- in AP mode, the captive-onboarding and Recovery Safe Mode allowlists no longer limited anything.

On 2026-10-18 an unauthenticated `GET /status?slot=0` to the real WS350 returned full live printer status (HTTP 200). The control POST was deliberately not tried because a print was running. The finding about it comes from reading the source.

## Why the login was removed

PR #122's comment says: *"The product requirement is that the WS350 web portal must not prompt for a device code."* The commits and acceptance tooling show two goals:

1. **Owner convenience.** No code to read off the display and type into the browser.
2. **Unattended acceptance.** `RELEASE_PROCESS.md` requires machine-verifiable acceptance with no operator prompts. The helpers (`accept_os12_unattended.py`, capture, media, update) were rewritten to drive the portal anonymously with `X-BambuHelper-Client: 1`.

No kiosk, display or third-party integration depended on it.

## How each goal is kept, safely

| Goal | 12.0.1 behaviour |
| --- | --- |
| Fewer code prompts | Sessions last 8 hours per browser (unchanged v11.20 contract). The control-plane v4 owner setting **Require access code** is back and **on by default**. Turning it off only opens an explicit list of read-only status routes on station Wi-Fi: `/`, `/status`, `/hardware/health`, `/hub/timer/status`, `/os12/update/status`, `/api/portal-security`. It never opens controls, settings, credentials, capture, diagnostics, inventory or Recovery, and it never applies in AP mode. Changing it needs a signed-in, same-origin request. Factory reset turns it back on. |
| Unattended acceptance | The wrapper scripts ask for the code once per run at a hidden prompt. The code is not echoed, not passed as an argument, and not stored. Only the session cookie is kept, in an owner-only (0600) jar in the run's private temp directory, and it is revoked on exit. After that the whole run is unattended. Running identity (`releaseVersion`, `runningSourceCommit`) is now on the public `/recovery/status` readiness probe, so identity checks across reboots (install, recovery round-trip) need no session. The update-runtime helper asks for the new code after its reboot, because the code changes on every boot. |

## Security delta

- `securityAuthorize()` delegates to one host-tested pure policy, `firmware/platform/security/portal_access_policy.hpp`. It is installed as `include/workshop_portal_access_policy.hpp` and proven by `tests/workshop_os12_portal_access_smoke.cpp`.
- Normal-LAN routes need the boot-scoped portal-code session. An unauthenticated API, status, control or capture request gets **401 JSON**. An unauthenticated navigation to `/` or `/recovery` gets **303 → /login**.
- Every mutation needs real same-origin provenance: `Origin`, or `Referer` when `Origin` is absent. Opaque (`null`) or foreign origins are refused with 403. `X-BambuHelper-Client` is no longer trusted or even collected.
- AP captive onboarding (`/`, `/save/wifi`, `/app.css`, `/app.js`) and the Recovery Safe Mode routes (`/recovery*`, `/ota/upload`, `/reset`) are exactly as v11.20 specifies.
- The portal code is generated at boot, shown only on **System → Local Portal**, and never printed to Serial.
- Login backoff bug fixed. It treated a zero deadline as "not blocked", but `deadlinePending(now, 0)` is true once `millis()` passes 2^31, about 24.8 days of uptime. From then on every new browser would have been rate-limited until the counter wrapped. That was harmless while 12.0.0 had no login, but would bite as soon as sign-in came back.
- A route-table audit (`scripts/validate_os12_portal_signin.py`) fails the build if any route is registered without the `SECURE_*` wrappers and isn't on a reviewed public list.

## Not changed

- Printer, power and update command semantics, guards and fail-closed checks.
- The touchscreen. It never used the HTTP portal. The Local Portal view shows the real code again; on 12.0.0 it showed an empty code.
- Recovery Safe Mode, rollback and the Force Touchscreen paths.
- `/recovery/status` stays public, as accepted in v11.20. It gains release version and source commit, and still carries no secrets.

## Integration impact

LAN clients that read `/status` or `/hardware/health` without signing in (for example Local AI's Workshop card) will get **401** after this update. They need a session or the separate read-only status token route that comes in the next candidate.

## CI acceptance

- [ ] `Validate`: portal access policy smoke test (unauthenticated `/status` → 401; control POST with the marker header → 403, with a forged Origin → 401; AP and Recovery Safe Mode scoping; the open-read setting stays narrow).
- [ ] `Workshop OS 12 UX Architecture`: reconstruction with `validate_os12_portal_signin.py`, native `ws_lcd_350` build, `jc3248w535` cross-board build, exact artifact `os12-ux-ws350-<sha>`.
- [ ] `Workshop OS 12 Tooling Checks`: `test_os12_portal_session_client.py` (the acceptance client keeps the code out of storage, sends a real Origin, never sends the marker header, and detects code-free or marker-trusting firmware), plus the existing physical-acceptance and recovery-helper validators.
- [ ] `Release Gate` / `merge-gate`.

## Physical acceptance on WS350

Use only the exact CI artifact for this head. Install it with the printer idle (not preparing, printing or paused).

1. **Install**
   - `bash scripts/install_accept_os12_candidate_macos.sh --artifact-zip ~/Downloads/os12-ux-ws350-<sha>.zip --confirm-printer-idle --full-backup`. The device still runs 12.0.0, so the OTA upload itself needs no code.
   - When asked, type the code shown on the WS350 under **System → Local Portal**. The rest of the run is unattended: identity, whole-device acceptance, 15-view capture and the evidence bundle.
   - Confirm the device returns to Home and printer configuration persists.
2. **Signed-out boundary** (browser, private window, or `python3 scripts/accept_os12_portal_runtime.py --probe-only`)
   - opening the device URL lands on the custom `/login` page with no browser auth dialog;
   - `GET /status?slot=0` and `/hardware/health` answer 401;
   - a wrong code is rejected, and repeated wrong codes are rate-limited.
3. **Sign-in and session**
   - sign in with the code from **System → Local Portal**;
   - Home, Printer, Workshop, More and Recovery render;
   - Light and Pause/Resume work when applicable. Stop stays hold-guarded;
   - Logout gates access again. After a reboot the old session is refused and the code on the display has changed.
4. **Touchscreen**
   - **System → Local Portal** shows a 10-character code that is readable and fits;
   - the other System, Settings and Printer screens have not regressed.
5. **Recovery**
   - signed out, `/recovery` redirects to `/login`; signed in, it renders and its actions need the session;
   - deliberate Recovery Safe Mode: `/recovery`, `/recovery/*`, `/ota/upload` and `/reset` are reachable without the session; printer control, settings export and debug are not.
6. **Optional setting**
   - turning **Require access code** off lets a private window read `/status` without signing in, while `/printer/access-code`, `/hub/frame.ppm` and every POST still need sign-in;
   - turn it back on.
7. **Credential hygiene**
   - the code is not in Serial output, evidence bundles or retained captures. The Local Portal view must stay redacted or excluded.

## Promotion gate

Merge records `merged-unaccepted`. Accepted/stable promotion needs the physical steps above plus the OS12 sensory checks still pending from 12.0.0.
