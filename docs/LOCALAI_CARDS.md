# Local AI cards

**Where they show (12.4.0):**
- **Local AI tab** (third tab, sparkle icon): every card, one row each, then the workshop tools (filament, timer,
  note).
- **Home:** the first row is Local AI's most important card, or the workshop timer while it runs; it opens the Local
  AI tab.
- **Calm screen:** Local AI's card comes first. The printer's line shows only while the printer is doing something;
  otherwise a second Local AI card shows there.

The rest of this page started with 12.3.10, when the cards were only on the calm screen.


Since Workshop OS 12.3.10, the calm idle screen (what the display shows while nobody is using it, printing or not)
shows one card from Local AI under its print status line, and a different card every 8 seconds:

| Card | When |
|---|---|
| **All clear** / **Needs you** | always; Needs you says what waits (approvals, failed runs) |
| A problem (Heads up / Worth a look) | the Local AI watchdog found one: a full disk, the display or printer, the camera bridge |
| **Working on** | Local AI is running something |
| **Weather** | Local AI's home location is set (Local AI › Health › Home location) |

Without cards (Local AI not set up, or nothing heard from it for 10 minutes) the calm screen is exactly as before.
The cards are display only: tapping anywhere still just wakes the screen.

## Set up (once)

On the Mac:

1. In the LocalAI repo, run `host/workshop-display/set-key.sh`. It makes the display key in the Mac's login Keychain
   (`localai-display-key`) and registers its fingerprint with Local AI.
2. Here, with a signed-in portal session, run:

   ```
   WORKSHOP_OS_COOKIE_JAR=<jar> python3 scripts/configure_localai_feed.py
   ```

   It sends the display Local AI's address (`10.0.0.21`), the name on its certificate (`localai.home.arpa`), the key
   and Local AI's CA (`~/.claude/localai-chat/localai-ca.crt`), then waits for the first card:
   `PASS: 1 card(s): All clear: Nothing needs you right now.`

`--clear` forgets the settings on the display. Since 12.3.12 the settings live in `/localai.json` on LittleFS (the
flash's spare `spiffs` partition), so restarts and updates keep them. The WS350's NVS has no room for the CA.

## How it works

- Once a minute, a background task fetches `GET /api/display/feed` from Local AI (see LocalAI
  `docs/WORKSHOP-DISPLAY.md` › Local AI cards). While Local AI doesn't answer, it waits 2, then 4, then 8, then 10
  minutes between tries.
- The connection goes to Local AI's IP address. The certificate is checked against Local AI's CA and the name
  `localai.home.arpa`, because the ESP32's TLS library can't match an IP address in a certificate. It never skips the
  check.
- The request is HTTP/1.0, because Local AI's HTTPS front answers HTTP/1.1 in chunks. It carries the display key
  (`X-LocalAI-Display-Key`), which signs the display in for that one route.

Portal routes:

| Route | What it does |
|---|---|
| `GET /os12/localai/status` | the cards the display last got, when, and why not |
| `POST /os12/localai/config` | form fields `address`, `name`, `key`, `ca` |
| `POST /os12/localai/clear` | forgets the settings |

The status route never sends the key or the CA back.

For captures, `/hub/show calm` opens the calm screen when it is turned on.

## Code

- `firmware/platform/localai/workshop_localai_feed_core.hpp`: the rules. Host-tested by
  `tests/workshop_os12_localai_feed_smoke.cpp`.
- `firmware/platform/localai/workshop_localai_feed.{h,cpp}`: the fetch task and its settings.
- `firmware/platform/ui/tabs_layout.hpp` `calmLayout(s, withAi)`, and `tabs_pages.cppfrag` `wtDrawCalmAiCard`: the
  card on the calm screen.
- `apply_workshop_os12_localai_feed.py` and `scripts/validate_os12_localai_feed.py`: the build step and its checks.

## Troubleshooting

Read `GET /os12/localai/status` and look at `status`:

| `status` | Meaning and fix |
|---|---|
| "Local AI isn't answering, or its certificate didn't match." | Local AI is down (the watchdog's Mac notice says so), or the CA changed: re-run `configure_localai_feed.py`. |
| "Local AI turned the display key down (HTTP 401/403)." | Local AI's sign-in is enforced and the key fingerprint is missing: re-run `set-key.sh`, then `configure_localai_feed.py`. |
| "Waiting for Wi-Fi." | The display is off Wi-Fi. |
| "Local AI cards are not set up." after a restart | Firmware 12.3.10 or 12.3.11 kept the settings only until a restart: update to 12.3.12, then re-run `configure_localai_feed.py`. |
