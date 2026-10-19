# Workshop OS 12.2.0 — Sign-in code key for Local AI

Stacked on 12.1.4 (More overhaul) and the 12.1.0 read-only status token (`docs/status-lite-token-12-1-0.md`).

## Purpose

The Local Portal sign-in code changes on every restart and is shown only on the touchscreen (More → Local Portal). The owner wants Local AI's web page to show it, so they never have to walk to the display to sign in.

This is a **second, separate key** with a separate scope. The status token (`wsl_…`) reads printer status and nothing else; the sign-in code key (`wsc_…`) reads the sign-in code and nothing else.

## Security trade-off

Anyone who holds this key can read the current sign-in code and therefore sign in to the Local Portal, which includes printer controls and settings. In effect the key is a standing sign-in credential. It is:

- created only after a tap on **Allow** on the touchscreen;
- kept by Local AI only (the device keeps just its SHA-256);
- revocable at any time from the Local Portal, and replaced whenever a new one is created;
- limited to one route that is rate-limited and has its own lock-out (12.3.8; up to 12.3.7 it shared the sign-in lock-out).

If Local AI's host or its `stack.env` is compromised, revoke the key.

## The route

`GET /api/portal-code` with `Authorization: Bearer wsc_…` (never a query string or cookie).

```http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store
X-Content-Type-Options: nosniff

{"code":"ABCDEFGHJK","bootId":"0123456789abcdef"}
```

- `code`: the current sign-in code, exactly 10 characters of `ABCDEFGHJKLMNPQRSTUVWXYZ23456789` (no I, O, 0 or 1). The touchscreen shows it as `ABCDE FGHJK`; the route sends it without the space. Submit it to `POST /login` as `code=…`.
- `bootId`: 16 lower-case hex characters, chosen at random once per boot. The code is also chosen once per boot, so when `bootId` changes the display has restarted and the old code no longer works. Compare it for equality only.
- Exactly these two fields. No other field is ever added by this version.

Other answers (all JSON, all `Cache-Control: no-store`):

| Status | When | Notes |
| --- | --- | --- |
| `401` | no key, malformed key, wrong key, a status token, or no key set up | `WWW-Authenticate: Bearer realm="workshop-os-code"`. Counts as a failed sign-in for this client address. |
| `429` | more than one answer in 2 s from this client, or this client is backing off after wrong keys | `Retry-After: <seconds>`. Wait that long. |
| `404` | the display is in setup/recovery AP mode | Station Wi-Fi only. |
| `503` | the code is not available | Should not happen on a running device. |

### Limits

- Same per-client limiter as `/api/status/lite`: one answer every 2 s; after two bad keys the client is blocked for 1, 2, 4 … s, capped at 60 s.
- **Its own lock-out (12.3.8).** Only a well-formed `wsc_` key that does not match counts, toward this route's own per-client back-off (two free, then 1 s doubling to 60 s). A request with no key, a malformed key or a `wsl_` key never counts, and the route neither reads nor adds to the sign-in lock-out. Up to 12.3.7 every request without the right key, including one with no `Authorization` header, counted as a failed `POST /login`, so any web page open in the owner's browser could lock the owner out of sign-in. A 130-bit key cannot be guessed, so a separate counter is not a way around the sign-in back-off. A successful key read resets this route's count.
- A signed-in portal session does **not** open this route; only the key does.

## The key

- 128 bits from `esp_random()`, written as `wsc_` followed by 26 characters of the portal-code alphabet. The status token is `wsl_` + 26; neither is well-formed for the other's route.
- The device stores **only** SHA-256(key), in NVS `workshop-sec/code_sha` (the status token uses `workshop-sec/lite_sha`). Comparison is constant-time.
- One slot. Approving a new key replaces the stored digest, so **the old key stops working at that moment**. **Revoke** clears it, and so does factory reset. Cancel on the display leaves the existing key in place.
- Neither the key nor the code is written to Serial, logs, settings export, `/debug`, framebuffer captures or evidence bundles. The portal shows the key **once**. The prompt on the display draws neither.
- It opens nothing else. `securityAuthorize()` never reads `Authorization`, the status route only accepts `wsl_` tokens, and no other route reads the header.

## Creating it (owner, once)

1. Sign in to the Local Portal and open **More**. Under **Sign-in code access** (next to Read-only status access), choose **Create**.
2. The display wakes and shows **"Allow Local AI to show the sign-in code?"** with **Cancel** and **Allow** and a 60 s countdown in the header. While it is up, no other touch does anything.
3. Tap **Allow**. The portal shows the key once. Give it to Local AI (for example `LOCALAI_WORKSHOP_CODE_TOKEN=…` in `C:\LocalAI\stack\stack.env`).
4. If the key isn't collected within 60 s of Allow, the portal never sees it. The old key is already revoked by then, so create it again.

Only one Local AI question is on the display at a time: **Create** answers 409 while the status-token prompt is up. (If a status-token request arrives while this prompt is up, the status prompt is shown first and this one continues afterwards, if its 60 s have not run out.)

Management routes, all behind the session and same-origin checks: `GET /api/code-token` (`{"configured":bool,"phase":"idle|pending|approved|denied|expired","secondsLeft":n,"route":"/api/portal-code"}`), `POST /api/code-token/create` (202 with `requestId`), `POST /api/code-token/claim` (`requestId=…`, returns the key once), `POST /api/code-token/revoke`.

## Touchscreen

- The prompt uses the 12.1 More layout: a 44 px header (title and a countdown chip, no Back because the prompt is modal), the More dialog card, and Cancel/Allow inside the card. The tab-bar band is left empty: nothing is drawn on it and it does not respond, because the prompt is modal.
- **More → Local Portal** has a new row, **Local AI code access**: *Set up* or *Not set up*. It replaces the "The code changes when the display restarts." note row, which is now what tapping the access code says. The page still has five rows and does not scroll, and the access-code row is still at 89–133 px for the capture redaction.

## Tests

- `tests/workshop_os12_code_token_smoke.cpp` (Validate): key format; the same random bytes give `wsl_` and `wsc_` keys that are not interchangeable; strict Bearer parsing in both directions; the code-key approval flow (Allow, Cancel, 60 s expiry, show-once claim, request binding, new request wipes an unclaimed key, a status token cannot be handed over); code and boot-id checks; the exact response; malformed input and overflow fail closed; the shared limiter; the key cannot satisfy the portal policy.
- `scripts/validate_os12_code_token.py` (OS12 UX), need/forbid on the reconstructed source, run right after the overlay and again (`--final`) on the finished tree: one `GET` registration, not `SECURE_GET`; management only behind `SECURE_*`; own rate limit, key check, only a wrong well-formed key counted, in that order (12.3.8); hash-only storage in `code_sha`; Allow required to mint; nothing reaches Serial, export or diagnostics; neither the portal policy nor the status route accepts it; prompt touch before the tab bar; the Local Portal row and the video guard.
- The 12.0.1 route-table audit is re-run after this overlay with `/api/status/lite` and `/api/portal-code` as the only added public routes, and the status-token validator is re-run on the finished tree.
- `scripts/accept_os12_code_token_runtime.py` (GET-only, non-destructive) checks the real device; `scripts/test_os12_code_token_runtime.py` proves it against a fake device, including that it catches devices that are open, over-broad, leaking, unlimited, cacheable or accept a status token.

## Physical acceptance on WS350

Install the exact CI artifact for this head (signed-in OTA, as for 12.1.x). Then:

1. **Prompt.** In the Local Portal, More → Sign-in code access → **Create**. The display wakes and shows the prompt in landscape: header, card, Cancel and Allow inside the card, nothing on the tab-bar band. Text fits, the countdown runs, both buttons are easy to tap. Tapping the empty tab-bar band and the card does nothing.
2. **Cancel.** Tap **Cancel**. The portal says nothing changed; More → Local Portal still shows *Not set up*.
3. **Allow.** Create again and tap **Allow**. The portal shows a `wsc_…` key once. Reload the page: it is gone. The display never shows the key or the code on the prompt.
4. **Row.** More → Local Portal shows **Local AI code access: Set up**, five rows, no scrolling. Tapping the access code says the code changes when the display restarts.
5. **Route.** Save the key to an owner-only file and run `WORKSHOP_OS_CODE_TOKEN_FILE=<file> python3 scripts/accept_os12_code_token_runtime.py`. It should report PASS. (It uses wrong keys on purpose; wait a minute before signing in from the same computer, or sign in successfully to reset the count.)
6. **Match.** Compare the code from the route with the one on the display (they match, without the space). Restart the display: the old code and `bootId` change on the next read.
7. **One scope each.** The status token still reads `/api/status/lite` and gets 401 from `/api/portal-code`; the code key gets 401 from `/api/status/lite`.
8. **Revoke and replace.** **Revoke**, then confirm the old key gets 401 and the row says *Not set up*. Create again and confirm the previous key gets 401 once the new one is allowed.
9. **Video test.** Start Sound & Alerts → Video test, then Create from the portal: the video stops and the prompt is drawn cleanly.
10. Other More pages and touch elsewhere behave normally once the prompt is gone.
