# Workshop display: Print lab card, Judge it, and "Needs you" on idle Home

Written 26 Oct 2026 for the owner's review. **Status: draft, not started.** The owner picked items 1 and 3 from the
display ideas list (26 Oct): a Print lab card with judging after a lab print, and Pi Hub's "Needs you" items on idle
Home. Owner's rule (26 Oct): **"I want the experience to be consistent across devices."** Owner's choice (26 Oct):
the display gets **the same Judge it sheet as the phone, stepped one strip per screen**.

## Consistency rule

The Print lab page (phone/desktop), Pi Hub and the display show the same things the same way:

- **Same list:** "Needs you" is one list, built once, in one order. Every screen shows it from the top; a small screen
  shows fewer rows, never different ones.
- **Same words:** titles, button names ("Judge it", "Later"), tones (ok / warn / bad / attention) and the run and
  experiment ids are identical everywhere.
- **Same action, same result:** judging on the display records exactly the verdict the phone would, through the same
  request queue the Mac applies.
- **Same state:** acting on one screen clears or updates the item on the others within a poll (≤ 60 s; the display's
  long poll makes it ~2 s).

## What exists

- The display reads one feed: Local AI's `GET /api/display/feed` (pinned TLS, display key `X-LocalAI-Display-Key`),
  every 60 s plus a ~2 s long poll (`/api/display/events`). Cards: `kind, title[28], text[112], tone, id, ask, at,
  percent`, at most 6 (`firmware/platform/localai/workshop_localai_feed_core.hpp`).
- Idle Home (#227) shows one house card, the most urgent feed card plus "+N more" (`homeSummaryIndex`,
  `firmware/platform/ui/tabs_pages.cppfrag` `wtDrawHomeHouse`).
- The display already sends taps to Local AI through a one-job-at-a-time queue (approvals decide, clear printer).
- **Two "Needs you" lists exist today:** Pi Hub's `/api/needs` (Pi issues + Local AI's attention cards + the newest
  print event, ranked bad → attention → warn, printer rows collapsed) and Local AI's feed cards (Local AI items + Pi
  issues as kind `home`). They differ, which breaks the rule above.
- Judging on the phone (`app/public/print-lab.js`, Judge it sheet): for each strip (variant tab) × criterion, a chip
  from the criterion's `choices` or "–" (not judged → null); optional inconclusive reason, lighting, note. It queues a
  `verdict` request `{grades:{tab:{criterion:choice|null}}, lighting, note, inconclusive, replace}` that `lab pull`
  applies with `record_verdict`.

## Design

### 1. One "Needs you" list (Pi Hub builds it, everyone shows it)

- Pi Hub's `hub/needs.py` stays the single builder: it already merges all three sources and ranks them.
- Local AI fetches Pi Hub's `GET /api/needs` (30 s cache, like `app/pi-hub.js` does for `/api/now`) and adds it to the
  display feed as a new top-level field `needs: [{id, tone, title, detail, source}]` (max 6, titles cut to 28, detail
  to 112). Pi Hub never reads `needs`, so there is no loop.
- Each item gets a stable `id` in Pi Hub (`source:kind:key`, e.g. `printer:plate`, `localai:approval:<id>`) so screens
  can match and clear the same item.
- Pi Hub down: the feed's `needs` is absent and the display falls back to today's cards with a small "Pi Hub isn't
  answering" line.
- Fix found while reading: Pi Hub drops Local AI's `warning` cards (it expects `warn`). Map `warning` → `warn`.
- The Step 6 lock: `/api/needs` is read by Local AI from 10.0.0.21; add it to the Caddy machine paths
  (`@machine`) on branch `step6-lock`.

### 2. Idle Home shows the top two

`homeSummaryIndex()` becomes `homeSummaryTop(items, n, out[2], others)` over `needs` (fallback: cards): two rows (title
+ one line each), "+N more" for the rest, same order as Pi Hub. Must fit without scrolling (layout smoke test). Tap a
row → the Local AI tab at that item.

### 3. Print lab card

From the print-lab index Local AI already stores, built in `app/display-feed.js` (no new data from the Mac):

| When | Card | Tone |
| --- | --- | --- |
| An experiment's latest run is printing (the `live` match from the Print lab page work, PR #403) | `Lab · E-021`, text = `judge_on` (else `question_text`) | busy |
| The run finished and has no verdict | `Judge E-021`, text `Look at: <judge_on>`, `ask: "lab-judge"`, `id: <run id>` | attention |

Two experiments printing → no lab card (same rule as the page). The judge card leaves when a verdict arrives or after
24 h. On the printing Home the busy card takes the extra row (`wtHomeExtra`). The attention card also appears in Pi
Hub's "Needs you" (it comes through Local AI's feed), so all three screens show "Judge E-021" at the same moment.

### 4. Judge it on the display (stepped)

- `GET /api/display/lab/judge?run=<id>` (display key): the sheet's content, built from the stored experiment record:
  `{experiment, run, judgeOn, tabs:[...], criteria:[{key, label, choices:[...]}], pending: <request status or null>}`.
  Only experiments with `criteria` are judged on the display; others show "Judge it on your phone: this test compares
  A and B" (the same rule the phone sheet uses).
- **Screens** (480×320): one per strip. Header `Judge it · E-021 · Strip B (2 of 3)`; one row per criterion: label +
  its choice chips + "–" (44 px targets); Back / Next. A last screen: **Inconclusive** (with the same reasons list as
  the phone) and **Send**. Lighting is sent as `diagnostic` (the phone's default); no note on the display.
- **Send** → `POST /api/display/lab/verdict {run, requestId, grades, inconclusive}` (display key, `GUARDED`,
  `routeKeys`): Local AI checks the run is the judge card's, the tabs/criteria/choices match the record, then queues
  the **same** `verdict` request the phone would (same 4 KB / 20-pending limits, idempotent `requestId`). The sheet
  shows "Waiting for the Mac", then "Done ✓" or the Mac's refusal in its words — the same states as the phone.
- **Already judged** (a verdict or a pending verdict request exists): the sheet opens on "Judged on <device> at
  <time>" with **Change it** (sends with `replace: true`, as the phone's Replace does).
- **Later** hides the judge card on the display for 2 h only; it stays on the other screens.
- **Photos** are still added from the phone (the display has no camera of its own); the last screen says "Add photos
  from your phone".
- Draft: the display keeps the in-progress choices in RAM until Send or 10 min idle; no cross-device draft.

## Errors

- Feed down or stale (> 10 min): no lab card, no judge sheet; house card as today ("Local AI unreachable").
- Record changed since the sheet opened (new run, criteria edited): the verdict route refuses with "This print has
  changed. Open it again." and the sheet reloads.
- Mac refusal (e.g. "already has a verdict"): shown in the Mac's words, with Change it.
- Display key missing: "Pair the display with Local AI" (existing pairing flow).

## Testing

- Pi Hub: `needs` ids are stable; `warning` cards included; `/api/needs` shape.
- Local AI: `buildFeed` adds `needs` from Pi Hub (cut lengths, absent when Pi Hub is down), lab busy/attention cards,
  two-printing rule, 24 h expiry; judge route returns only the record's tabs/criteria; verdict route: display key
  required, run must match, choices validated against the record, queues the identical request body the phone sends
  (a test compares the two), idempotent request id, limits.
- Firmware host smoke tests: `homeSummaryTop` ordering and "+N"; idle Home with two rows fits; judge screens: paging,
  chip selection, "–" → null, Send payload; layout fits at 480×320 with 44 px targets. Fake-device test for the
  `LabVerdict` job.
- Device captures via `/hub/show`: idle Home with two items, printing Home with the lab row, each judge screen, the
  Waiting / Done / refused states.

## Delivery

1. Pi Hub: stable need ids, `warning` fix, machine path on `step6-lock`.
2. Local AI: `needs` in the feed, lab cards, judge + verdict routes (after #403 merges, since it reuses its `live`
   match).
3. Firmware: idle Home two rows, lab row, the stepped Judge it sheet (OTA after the owner's OK).

## Open question for the owner

1. **Pi Hub builds the one list** (recommended: it's the house-wide app and already merges everything), and Local AI's
   own Home "Needs you" follows it in a later step — or Local AI builds it instead?
