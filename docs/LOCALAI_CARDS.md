# Local AI cards

**Where they show (12.4.0):**
- **Local AI tab** (third tab, sparkle icon): every card, one row each, then the workshop tools (filament, timer,
  note).
- **Home (printing):** the first row is the workshop timer while it runs, else the **Print lab card** while a lab
  run prints ("Lab · E-021", since 26 Oct 2026), else the first "Needs you" item; it opens the Local AI tab.
- **Idle Home, at a glance (since the Home redesign after 12.8.0; two rows since 26 Oct 2026):** one screen, no
  scrolling. The header shows the time and the weather card's temperature and sky ("66° Sunny"). Then **two "Needs
  you" rows** (title and one line each, "+N more" on the second): the top two of Pi Hub's one list (the feed's
  `needs`, in Pi Hub's order, the same list Pi Hub and the Print lab page show; an empty list is All clear). Without `needs` (Pi Hub not
  answering) they are Local AI's cards ranked bad, attention, warning, work under way, All clear, and the second
  row says "Pi Hub isn't answering" when there is only one. A tap opens the Local AI tab at that item. Then the
  **printer card**: its state in large type ("Finished 1:21 PM", "Ready", "Offline") and one line of detail (the
  last job, or nozzle and bed temperatures). Then the timer. Information cards (disks, music, finished work) are on
  the Local AI tab only. `homeSummaryTop`, `printingExtraIndex` and `weatherShort` in
  `workshop_localai_feed_core.hpp` decide what shows; `copyUtf8` cuts every title and line on a character boundary.
- **Lab cards** (kind `lab`): "Lab · E-021" (busy) while a lab run prints, and "Judge E-021" (attention, `ask:
  "lab-judge"`, `run: "PR-021-01"`) when it finished without a verdict. The display keeps the card's `run` for the
  Judge it sheet.
- **Judge it (26 Oct 2026):** a tap on the "Judge E-021" row (idle Home or the Local AI tab) opens the same Judge it
  sheet as the phone, one strip per screen. The header says `Judge it · E-021 · Strip 21B (2 of 3)` and has **Later**.
  Each criterion is a row: its label, a chip per choice and "–" (not judged, sent as null). Chips wrap to two lines;
  a strip with more criteria than fit scrolls inside the sheet (the arrows between Back and Next). The last page has
  **Inconclusive** (optional: "It didn't finish printing", "I can't tell from this print", "The wrong thing printed",
  sent as those words), the state and **Send**, and says "Add photos from your phone". Send needs every strip graded
  on every criterion, or a reason. It goes to Local AI's `POST /api/display/lab/verdict`, which queues the very
  verdict request the phone sends (lighting diagnostic, no note); the sheet then says "Waiting for the Mac" (it reads
  the sheet again every 3 s; after 2 minutes, as the phone: "The Mac hasn't picked this up. It runs when the Mac is
  awake."), then "Done ✓" or the Mac's refusal in its words: with **Change it** when it says the print "already has
  a verdict" (as the phone's Replace), else with Close. A resent id is accepted whatever its status. Already judged
  (a verdict, or a request waiting): it opens on "Judged on the phone at 6:32 PM" with **Change it**, which sends
  with `replace: true`. A test without criteria says "Judge it on your phone: …". The same draft resent keeps its
  `rq-` id (Local AI counts it once); any change, or Change it, makes a new one. The draft stays in RAM until Send or
  10 minutes without a touch. **Later** hides the judge card on this display for 2 hours: idle Home's rows, the calm
  screen's rotation and opening by itself (the Local AI tab still lists it as a row; Pi Hub and the phone still show
  it). Once per judge card, the sheet also opens by itself when a
  tap wakes the calm screen. The sheet is up only while you're on it: any navigation away (a tab, another page,
  `/hub/show` of another view, waking the calm screen) closes it, and "Nothing to judge right now." closes itself
  after 5 s or at the next feed update; the draft is kept for 10 minutes, so reopening restores the choices. The rules are `firmware/platform/ui/lab_judge.hpp` (host-tested by
  `tests/workshop_os12_lab_judge_smoke.cpp`); the screens are `lab_judge.cppfrag`.
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

**Since 12.7: pair.** In Local AI, open **Services › Workshop display › Pair display**; it shows a 6-digit code for
10 minutes. Type it on the display (**Local AI tab › Local AI connection**) or in the Local Portal (**More › Local AI
on the display**). The display reads Local AI's CA over plain HTTP, sends the code over HTTPS pinned to it, and saves
the new display key with the CA. Pairing again replaces the key (Local AI stops recognising the old one at once; while its sign-in is report-only, an unrecognised caller is still only reported); **Unpair** in the
portal forgets it on the display.

The Mac way, from before pairing, still works. On the Mac:

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

### 12.6: Local AI feed v2 on the display

- **Live.** While nothing else waits, the display keeps a long poll open (`GET /api/display/events`, 30 s); news (a new
  card, a message) comes in about 2 s. A question, a picture or an approval interrupts it at once. With an older Local
  AI it falls back to the minute poll.
- **Messages.** Local AI's messages (`POST /api/display/notify`, and the notification kinds picked in
  `/api/display/alerts`) show as a banner over the header for 12 s (20 s when it needs you), with a chime when asked;
  they wake the calm screen. A tap does the message's action: start the workshop timer, or open the Local AI tab, the
  latest picture, the camera or the printer.
- **Cards** carry the question a tap asks; finished work (`done`) and the fullest disk (`disk`) are new kinds.
- **Ask** has six questions: Needs me?, Running?, All OK?, Today?, Next?, Weather?.
- **Gallery.** Latest image shows the last 6 pictures: tap the left or right edge for the previous or next one.
- **Approvals.** A row on the Local AI tab opens what waits. Approve and Reject show only where Local AI allows it from
  the display (low risk by default; never code changes or deploys) and need a second tap within 4 s.
- **Heartbeat.** Every 5 minutes the display tells Local AI its version, uptime, Wi-Fi and memory (`GET /api/watch`).
- **Home after a print.** A finished print keeps the big card for 30 minutes, then Home goes back to Local AI with
  "X2D · Finished 9:33 AM" on the printer row.

Captures: `/hub/show localai-ask-<needs|running|health|today|next|weather>`, `localai-image[-<0-5>]`,
`localai-approvals`; Judge it: `lab-judge` (strip 1), `lab-judge-<n>` (page n), `lab-judge-send` (the last page). With
no judge card the sheet says "Nothing to judge right now."

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


## Household ownership and action results — 28 October server integration

Pi Hub owns the combined household **Needs you** list. It reads LocalAI's own `/api/attention` cards, and LocalAI
forwards the combined list to this display. The aggregate display feed is not an input to the household list.
Agent World's printer summary uses Pi Hub's designated Bambuddy record; immediate firmware controls and direct
printer telemetry remain Workshop OS responsibilities.

LocalAI's plate-confirmation route now stops before clearing printer errors if confirming the plate failed. When
only error clearing fails, it preserves the accepted plate confirmation. It also sends a quiet result through the
existing message/banner channel: **Plate confirmed**, **Check printer errors**, or **Plate not confirmed**.
This changes the server response/feedback behavior without changing the WS350 firmware protocol. Message delivery
is best effort; it does not prove the plate is physically empty.

These changes require a LocalAI server release; this note does not claim installation, a new firmware candidate or
physical acceptance. Direct display-to-Pi routine commands and linked cross-system task identities remain future work.
