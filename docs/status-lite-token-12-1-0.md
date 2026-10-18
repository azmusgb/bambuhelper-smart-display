# Workshop OS 12.1.0 — Read-only status token for Local AI

Stacked on the 12.0.1 Local Portal sign-in restore (`docs/portal-signin-restore-12-0-1.md`).

## Purpose

Local AI's Home screen shows one printer line, for example `Printer · Printing · 62% · 41 min left`. It needs a small, current, read-only status summary. It must not hold a portal session, a printer access code, or any control credential.

## The route

`GET /api/status/lite` with `Authorization: Bearer wsl_…` (never a query string or cookie).

```json
{"schema":1,"firmware":{"version":"12.1.0","sourceCommit":"<40-hex>"},
 "printers":[{"slot":0,"connection":"online","activity":"printing","freshness":"fresh",
   "ageSeconds":3,"progressPercent":62,"remainingMinutes":41,
   "error":null}]}
```

- Only configured slots are listed. The data comes from the normalized `WorkshopState`: connection, activity, freshness, age and progress. `remainingMinutes` and the error code come from the same printer state the display uses.
- When the printer isn't `online` and `fresh` (inside the platform's 60 s window, 5× in cloud mode), `activity` is `unknown` and `progressPercent`, `remainingMinutes` and `error` are `null`. `ageSeconds` still says how old the last report is. Nothing stale is presented as current.
- `progressPercent` and `remainingMinutes` are only present while preparing, printing or paused.
- `error` is present when the printer reports `print_error ≠ 0` or the activity is `error`. It carries `code` (printer-formatted), `text`, and `canceled` (the cancel code). `text` is the board's own wording, or `null` when the board has none; it is never made up.
- Deliberately absent: printer name, job/file name, IP, MAC, serial, RSSI, AMS, temperatures. The serializer has no inputs for them.
- Station Wi-Fi only: in AP mode the route answers 404.
- Rate limit per client IP: one answer every 2 s, otherwise `429` with `Retry-After`. A missing or wrong token gets `401` with `WWW-Authenticate: Bearer`. After two bad tokens the client is blocked for 1, 2, 4 … seconds, capped at 60 s, like portal login.
- Responses carry `Cache-Control: no-store`.

## The token

- It is 128 bits from `esp_random()`, written as `wsl_` followed by 26 characters of the portal-code alphabet (no I, O, 0 or 1).
- The device stores **only** SHA-256(token), in NVS `workshop-sec/lite_sha`. Comparison is constant-time.
- There is one slot. Approving a new token replaces the stored digest, so **the old token stops working at that moment**. **Revoke** in the Local Portal clears it, and so does factory reset.
- The token never appears on the touchscreen, in Serial output, settings export, `/debug`, framebuffer captures or evidence bundles. The portal shows it **once**.
- It opens nothing else. `securityAuthorize()` never reads `Authorization`, and the lite route never reads the portal session. Presenting the token to `/status`, `/hardware/health` or any control route still gets 401. A signed-in portal session does not open `/api/status/lite` either.

## Creating it (owner, once)

1. Sign in to the Local Portal and open **More → Read-only status access** (the panel above Filament Inventory). Choose **Create access**.
2. The WS350 wakes and shows **"Allow Local AI to read printer status?"** with **Cancel** and **Allow**. While the prompt is up, no other touch does anything. It lasts 60 s.
3. Tap **Allow**. The portal shows the token once. Copy it into Local AI's `C:\LocalAI\stack\stack.env` as `LOCALAI_WORKSHOP_STATUS_TOKEN=…`, then restart the appliance container.
4. If the token isn't collected within 60 s of Allow, the portal never sees it. The old token is already revoked by then, so create access again.

Management routes, all behind the session and same-origin checks: `GET /api/status-token`, `POST /api/status-token/create`, `POST /api/status-token/claim`, `POST /api/status-token/revoke`.

## Tests

- `tests/workshop_os12_status_lite_smoke.cpp` (Validate):
  - token format and alphabet;
  - strict Bearer parsing;
  - constant-time digest compare;
  - limiter: interval, backoff, cap, wrap-around and many clients;
  - approval flow: Allow, Cancel, 60 s expiry, show-once claim, request binding, a new request wiping an unclaimed token;
  - serializer: exact output, null and unknown rules, stale and offline handling, error escaping and truncation, field allowlist, overflow fail-closed;
  - the token cannot satisfy the portal policy.
- `scripts/validate_os12_status_lite.py` (OS12 UX), need/forbid on the reconstructed source:
  - exactly one `GET` registration, not `SECURE_GET`;
  - management only behind `SECURE_*`;
  - no `Authorization` in the portal policy, no session in the lite handler, no control path in the module;
  - digest-only persistence and constant-time compare;
  - the Allow tap is required to mint a token;
  - no token material in Serial, export or diagnostics, and none drawn on the touchscreen;
  - the field allowlist;
  - factory reset clears the token.
- The 12.0.1 route-table audit is re-run after this overlay with `/api/status/lite` as the only added public route.
- `scripts/accept_os12_status_lite_runtime.py` (GET-only, non-destructive) checks against the real device:
  - no token gives 401, a wrong token gives 401, and repeated wrong tokens back off with 429;
  - the valid token gives 200 with the allowed fields only;
  - an immediate second read gives 429;
  - the token opens no other route.

  `scripts/test_os12_status_lite_runtime.py` proves the helper itself against a fake device, including that it catches devices that are open, leaking, unlimited or over-broad.

## Physical acceptance on WS350

After 12.0.1 is accepted or installed, use the exact CI artifact for this head with the printer idle:

1. Install and run unattended acceptance as for 12.0.1: `install_accept_os12_candidate_macos.sh … --confirm-printer-idle --full-backup`, one code prompt.
2. In the Local Portal, **Create access**. Check that the prompt on the WS350 is readable and fits, and that both buttons are comfortable to tap. **Cancel** first and confirm the portal says nothing changed.
3. **Create access** again and tap **Allow**. The token appears once in the portal. Reload the page and confirm it is gone. Confirm it never appears on the display.
4. Save the token to an owner-only file and run `WORKSHOP_OS_STATUS_TOKEN_FILE=<file> python3 scripts/accept_os12_status_lite_runtime.py` (GET-only). It should report PASS.
5. During a print, a wait of more than 2 s between reads shows `printing`, the progress and the time left. Unplug the printer from the network and within about 60 s the route shows `unknown` with null progress.
6. **Revoke**, then confirm the old token gets 401. Create again and confirm the previous token gets 401 once the new one is allowed.
7. The System screens have not regressed, and touch elsewhere works normally once the prompt is gone.
