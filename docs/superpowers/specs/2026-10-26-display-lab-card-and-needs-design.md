# Workshop display: Print lab card and "Needs you" on idle Home

Written 26 Oct 2026 for the owner's review. **Status: draft, not started.** The owner picked items 1 and 3 from the
display ideas list (26 Oct): a Print lab card with a judge prompt after a lab print, and Pi Hub's "Needs you" items on
idle Home.

## What exists

- The display reads one feed: Local AI's `GET /api/display/feed` over pinned TLS with the display key
  (`X-LocalAI-Display-Key`), every 60 s plus a ~2 s long poll (`/api/display/events`). Cards have `kind, title[28],
  text[112], tone, id, ask, at, percent`; at most 6 (`firmware/platform/localai/workshop_localai_feed_core.hpp`).
- Idle Home (#227) shows one house card: `homeSummaryIndex()` picks the most urgent card (attention → warning → busy →
  ok) and says "+N more" (`firmware/platform/ui/tabs_pages.cppfrag` `wtDrawHomeHouse`).
- The display already sends taps to Local AI through its one-job-at-a-time queue: approvals decide (two taps within
  4 s) and clear printer (`workshop_localai_feed.cpp` `runDecide`).
- Local AI's feed already includes the Pi's live issues (kind `home`, from Pi `GET /api/now`) and Local AI's own
  attention items. Pi Hub's "Needs you" list (`/api/needs`) is built from those same two sources plus the newest print
  event, which the display already knows from the printer itself.
- The print lab lives behind `/api/lab/*` (paired-phone cookie or the Mac key). Nothing the display can read says "a
  lab experiment is printing". A lab verdict is structured (per-strip criteria grades, or A-vs-B rank and strength),
  recorded on the Mac by `lab pull` (`record_verdict`).

## Decisions (recommended)

1. **One feed.** The display keeps reading only Local AI's feed. Both features arrive as feed cards; the display
   never calls Pi Hub or `/api/lab/*` directly. Reason: one key, one TLS pin, one poll loop; the Pi's lock (step 6)
   doesn't have to open new paths.
2. **Judging stays on the phone.** A real verdict needs per-strip grades and photos, which don't fit 480×320 or a
   gloved finger. The display's job is the nudge at the right moment: **"Send to my phone"** (Local AI sends the phone
   a notification that opens the Judge it sheet for that run) or **"Later"** (hides the card for 2 h on the display
   only). No Good/Not good buttons, so the display can never record a wrong verdict.
3. **"Needs you" = the feed's top two.** Instead of reading Pi Hub's list (which already merges Local AI's cards: the
   two would echo each other), idle Home shows the two most urgent feed cards. Pi issues are already in the feed.

## Design

### Local AI: two new feed cards (kind `lab`)

Built in `app/display-feed.js` from the print-lab index Local AI already stores (no new data from the Mac):

| When | Card | Tone |
| --- | --- | --- |
| An experiment's latest run is printing | title `Lab · E-021`, text = `judge_on` (else `question_text`), cut to 112 | busy |
| Its run finished and it has no verdict yet (from the Workshop status: printer finished, matched as in the print-lab plan's `live` block) | title `Judge E-021`, text `Look at: <judge_on>`, `ask: "lab-judge"`, `id: <run id>` | attention |

- Two experiments claiming to be printing → no lab card (same rule as the Print lab page's live block).
- The judge card disappears when a verdict arrives (`lab sync`) or after 24 h.
- `POST /api/display/lab/nudge {run}` (display key, in `routeKeys` and `GUARDED`): checks the run is the one on the
  judge card, then sends the phone notification "E-021 is ready to judge" linking `#printLab?e=E-021&judge=1`. At most
  one per run per 10 min. Nothing is written to the lab.

### Display: Print lab card

- **Printing Home:** while a `lab` busy card is present, the printing Home's extra row (`wtHomeExtra`) shows it
  instead of the next house card: `Lab · E-021  Look at: front face seams`.
- **Judge prompt:** a `lab-judge` card opens a sheet over Home once (and again after "Later" expires): title
  `Judge E-021`, the look-at line, buttons **Send to my phone** and **Later**. Send uses the existing job queue
  (new job `LabNudge`, like `runDecide`); the button shows "Sent ✓" or the server's reason. One tap, no confirm: it
  only sends a notification.
- The card is also reachable from the Local AI tab like any other card.

### Display: idle Home shows two

- `homeSummaryIndex()` becomes `homeSummaryTop(cards, n, out[2], others)`: the two most urgent (same order), "+N more"
  counting the rest. The house card draws two rows (title + one line each) when there are two; one row as today
  otherwise. It must still fit without scrolling (`workshop_os12_tabs_layout_smoke.cpp`).
- Tap a row → the Local AI tab, scrolled to that card.

### Pi Hub (small fix found while reading)

`hub/needs.py` keeps only Local AI cards whose tone is in `bad/attention/warn`, but Local AI says `warning`, so Local
AI's warnings never reach Pi Hub's "Needs you". Map `warning` → `warn`. Test in `tests/test_needs.py`.

## Errors

- Feed down or stale (>10 min): no lab card, house card as today ("Local AI unreachable").
- Nudge fails (no paired phone, rate limit, Local AI down): the button shows the plain reason; the card stays.
- Display key missing: the sheet shows "Pair the display with Local AI" (existing pairing flow).

## Testing

- Local AI: `buildFeed` unit tests for both cards, the two-printing rule, verdict-arrives and 24 h expiry; nudge
  route: display key required, wrong run refused, rate limit, notification sent with the deep link; no lab text other
  than id/judge_on/question reaches the feed.
- Firmware host smoke tests: `homeSummaryTop` ordering and "+N", lab card picked for the printing Home's extra row,
  idle Home with two rows fits (layout smoke). Fake-device test for the judge sheet → `LabNudge` job.
- Device captures: `home` idle with two items, printing Home with a lab row, the judge sheet (captured via
  `/hub/show`).

## Delivery

1. Local AI: lab cards + nudge route (one PR, after the print-lab page work merges, since it reuses its `live` match).
2. Firmware: idle Home two rows + lab row + judge sheet (one PR; OTA after the owner's OK).
3. Pi Hub: the `warning` → `warn` fix (tiny, can go any time).

## Open questions for the owner

1. **Judging stays on the phone; the display only nudges** ("Send to my phone" / "Later")? Recommended: yes. The
   alternative is a quick Good / Not good on the display recorded as an overall verdict, which the lab's per-strip
   grades don't support today.
2. **Idle Home shows the top two items** (instead of one plus "+N more")? Recommended: yes.
