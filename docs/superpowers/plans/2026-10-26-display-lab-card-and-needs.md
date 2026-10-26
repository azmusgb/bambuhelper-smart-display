# Display: one Needs you list, Print lab card, Judge it — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The display, Pi Hub and the Print lab page show the same Needs you list and the same Judge it, and a lab
print can be judged on the display with the same result as on the phone.

**Architecture:** Pi Hub builds the one list (`/api/needs`, now with stable ids). Local AI reads it and adds it to the
display feed as `needs`, adds `lab` cards, and offers two display-key routes for the stepped Judge it sheet; the
verdict is queued as the identical `verdict` request the phone sends. The firmware draws two needs rows on idle Home,
a lab row on the printing Home, and the stepped sheet.

**Tech Stack:** Python 3 / FastAPI / pytest (Pi Hub); Node 22, node:test, Playwright (Local AI); C++ ESP32
(PlatformIO), g++ host smoke tests, Python validators (firmware).

**Spec:** `docs/superpowers/specs/2026-10-26-display-lab-card-and-needs-design.md` (this repo, branch `docs/lab-card-needs`).

## Global Constraints

- Same words everywhere: "Needs you", "Judge it", "Later", "Change it", "Waiting for the Mac", "Done ✓"; tones
  ok / warn / bad / attention; ids `E-021`, run ids `PR-021-01`.
- The display reads only Local AI's feed and display-key routes; it never calls Pi Hub or `/api/lab/*`.
- A display verdict body equals the phone's: `{kind:"verdict", experiment, run, payload:{grades:{tab:{criterion:
  choice|null}}, lighting:"diagnostic", note:null, inconclusive:<reason>|null, replace:bool}}`, same 4 KB / 20-pending
  limits, idempotent `rq-<16 hex>` id.
- Feed `needs`: at most 6 items, title ≤ 24 chars, detail ≤ 90 (Local AI's `cut`); absent when Pi Hub doesn't answer.
- 480×320, 44 px touch targets, idle Home never scrolls.
- Local AI: no new npm runtime deps; `--ds-*` tokens; display routes go in `routeKeys` and `GUARDED`. Firmware: OTA
  only after the owner's OK. Pi Hub: release with `git push pi main` only after Local AI's part is live.
- Untrusted text (titles from Pi Hub, lab text from the Mac) is data: escaped in Local AI, length-checked in firmware.

## Review Focus

1. Pi Hub answers but slowly (> 3 s) → the feed is still served on time without `needs` (Task 2, `test_needs_timeout_omits`).
2. The experiment's record changed between opening the sheet and Send (new run, criteria edited) → 409 "This print has changed. Open it again." (Task 3, `verdict refused when the record moved`).
3. A choice not in the criterion's `choices` (or a tab not in the record) arrives from the display → 400, nothing queued (Task 3).
4. Six needs with long UTF-8 titles → firmware copies cut on a character boundary, no overflow (Task 4, `needs_utf8_cut`).
5. Two experiments printing → no lab card and no judge card on the display (Task 2, `two printing, no lab card`).

---

### Task 1 (Pi Hub): stable need ids, Local AI warnings kept

**Files:** Modify `~/dev/pi-hub/hub/needs.py`; Test `~/dev/pi-hub/tests/test_needs.py`. Worktree `~/dev/pi-hub-needs`, branch `feat/needs-ids` off main.

**Interfaces:** Produces `GET /api/needs` items `{id, source, tone, title, detail, link}`; `id` stable while the item
means the same thing: `pi:<what>`, `localai:<card id>`, `printer:plate`, `printer:failed`.

- [ ] Tests: `test_ids_are_stable` (two builds of the same inputs → same ids; ids unique within a build),
  `test_local_ai_warning_is_kept` (a feed card with `tone:"warning"` → item tone `warn`),
  `test_local_ai_home_cards_not_echoed` (feed cards of kind `home` — the Pi's own issues coming back — are skipped).
- [ ] Run `.venv/bin/python -m pytest -q tests/test_needs.py` → FAIL.
- [ ] Implement: map `warning`→`warn` before the `ORDER` check; skip `kind == "home"`; add `id` in each builder.
- [ ] Run full `pytest -q` and `node --test tests/*.mjs` → pass. Commit.
- [ ] On `step6-lock` (worktree `~/dev/pi-hub`, branch `step6-lock`): add `/api/needs` to `@machine` in
  `deploy/caddy/Caddyfile` and to `MACHINE_PATHS` in `tests/test_caddy_lock.py`; run that test; commit.

### Task 2 (Local AI): `needs` and `lab` cards in the feed

**Files:** Modify `app/pi-hub.js` (add `needs()`), `app/display-feed.js` (`buildFeed({..., piNeeds, lab})`),
`app/server/voice.js` (`apiDisplayFeed` gathers them), `app/print-lab.js` (export `labCards(index, live, now)`);
Test `tests/display-feed.test.cjs`, `tests/print-lab.test.cjs`. Worktree off main after #403 ships, branch `feat/display-needs-lab`.

**Interfaces:**
- Consumes: Task 1's `/api/needs` items; #403's `live(index)` → `{experiment, run, state, ...}|{conflict:true}|null`.
- Produces: feed `needs: [{id, tone, title, detail, source}]`; cards `{kind:"lab", id:"lab-<run>", title:"Lab · E-021",
  text:<judge_on|question_text>, tone:"busy"}` and `{kind:"lab", id:"judge-<run>", title:"Judge E-021", text:"Look
  at: <judge_on>", tone:"attention", ask:"lab-judge", run:"PR-021-01"}`.

- [ ] Tests: `needs from Pi Hub are cut and capped at 6`; `test_needs_timeout_omits` (Pi Hub stub sleeps 5 s → feed in < 3.5 s
  without `needs`); `printing lab run → busy lab card`; `finished, no verdict → judge card with run`; `verdict
  arrived → no judge card`; `judge card gone after 24 h`; `two printing, no lab card`.
- [ ] Run `node --test tests/display-feed.test.cjs tests/print-lab.test.cjs` → FAIL.
- [ ] Implement. `needs()` uses `fetchWithTimeout` 3 s and a 30 s cache like `read()`; the judge card shows while
  the run's printer state is finished (idle/stopped/ended, the same rule #403 uses for Judge it) and the experiment has
  no `owner_verdict`, for 24 h after the run's end.
- [ ] `npm test` → pass. Commit.

### Task 3 (Local AI): judge and verdict routes for the display

**Files:** Create `app/display-lab.js` (`createDisplayLab({storage, labStore, now})` → `{judge(req,res,url), verdict(req,res)}`);
modify `app/server.js` (routes `GET /api/display/lab/judge`, `POST /api/display/lab/verdict`, add both to the display
key paths), `app/signin.js` (`GUARDED` += the POST), `app/print-lab.js` (export `queueRequest(project, body, from)`
used by both the phone route and this one). Test `tests/display-lab.test.cjs`.

**Interfaces:**
- Produces `GET /api/display/lab/judge?run=PR-021-01` → `200 {experiment, run, judgeOn, tabs:[..], criteria:[{key,label,choices}],
  judged:{at, by}|null, pending:{id,status,message}|null}`; `{phoneOnly:true, reason}` for experiments without
  `criteria`. `POST /api/display/lab/verdict {run, requestId, grades, inconclusive, replace}` → `202 {id, status:"pending"}`.

- [ ] Tests: `display key required` (401 without); `judge returns only the record's tabs and criteria`; `no
  criteria → phoneOnly`; `verdict queues the same body the phone does` (deep-equal with the phone route's stored
  request, apart from `from`); `bad choice → 400, nothing queued`; `unknown tab → 400`; `verdict refused when the
  record moved` (run not the judge card's → 409 "This print has changed. Open it again."); `same requestId twice →
  one request`; `20 pending → 429`.
- [ ] Run → FAIL. Implement. Run `npm test` → pass.
- [ ] Docs: `docs/WORKSHOP-DISPLAY.md` › Local AI cards gains `needs`, `lab`, and the two routes. Commit; open PR.

### Task 4 (Firmware): parse `needs` and `lab`, two rows on idle Home, lab row on printing Home

**Files:** Modify `firmware/platform/localai/workshop_localai_feed_core.hpp` (`struct Need`, `Tone::Bad`,
`toneFrom("bad"|"warn")`, `homeSummaryTop`, `shownKind("lab")`), `workshop_localai_feed.h` (snapshot `needs[6]`,
`needCount`, `needsFromPi`), `workshop_localai_feed.cpp` (`fetch()` parses `needs[]` and card `run`),
`firmware/platform/ui/tabs_layout.hpp` (`kHomeIdleItems` two rows), `firmware/platform/ui/tabs_pages.cppfrag`
(`wtDrawHomeHouse`, `wtHomeExtra`, `wtHomeTouch`); the matching `apply_workshop_os12_*.py` splice if a file is
patched rather than copied. Tests `tests/workshop_os12_localai_feed_smoke.cpp`, `tests/workshop_os12_tabs_layout_smoke.cpp`.
Worktree `~/dev/bh-lab-card`, new branch `feat/needs-lab-judge` off main.

**Interfaces:**
- Produces `struct Need { char id[32]; char title[kTitleLen]; char detail[kTextLen]; char source[12]; Tone tone; }`;
  `uint8_t homeSummaryTop(const Need* needs, uint8_t n, const Card* cards, uint8_t nc, int8_t out[2], bool& fromNeeds, uint8_t& others)`
  (uses `needs` when `n > 0`, else cards with today's ranking; Bad > Attention > Warning > Busy > Ok).

- [ ] Tests: `home_top_two_in_order`, `home_top_falls_back_to_cards`, `others_counts_the_rest`, `needs_utf8_cut`,
  `lab_card_takes_printing_extra_row`, layout smoke `idle_home_two_rows_fit`.
- [ ] Run the Validate workflow's g++ smoke commands locally (`.github/workflows/validate.yml:73-104`) → FAIL.
- [ ] Implement. Re-run → pass; `scripts/validate_os12_localai_feed.py` → ok. Commit.

### Task 5 (Firmware): the stepped Judge it sheet

**Files:** Create `firmware/platform/ui/lab_judge.hpp` (pure state: pages, selection, payload) and
`firmware/platform/ui/lab_judge.cppfrag` (drawing, touch); modify `workshop_localai_feed.cpp/.h` (jobs `LabJudgeLoad`,
`LabVerdict`; `WorkshopLocalAiExtras` gains `judge*` status fields and seq counters, like approvals),
`tabs_pages.cppfrag` (open the sheet once per judge card; Later = 2 h hide), the `/hub/views` catalog (`lab-judge`,
`lab-judge-send`) and `scripts/run_os12_ux_local.sh` if a new apply script is needed. Test `tests/workshop_os12_lab_judge_smoke.cpp`.

**Interfaces:**
- Consumes Task 3's judge/verdict JSON and Task 4's lab card `run`.
- Produces `struct LabJudge` with `load(json)`, `pages()` (= tabs + 1), `select(page, criterion, choiceIndex|kNotJudged)`,
  `bool payload(char* out, size_t len, const char* requestId, bool replace)` writing `{run, requestId, grades,
  inconclusive, replace}`.

- [ ] Tests: `pages_are_tabs_plus_send`; `dash_is_null_in_payload`; `payload_fits_4k_with_3_tabs_6_criteria`;
  `inconclusive_reason_sent`; `phone_only_shows_reason`; `judged_opens_on_change_it`; layout smoke
  `judge_page_fits_480x320_44px` for 6 criteria × 4 choices (chips wrap to two lines; more than fits → the page
  scrolls inside the sheet, never the Home).
- [ ] Run → FAIL. Implement: header `Judge it · E-021 · Strip B (2 of 3)`; Back / Next; last page Inconclusive (the
  phone's reasons list) and Send; states Waiting for the Mac / Done ✓ / the Mac's words; RAM draft cleared after 10 min idle.
- [ ] Re-run smoke tests → pass. Build `scripts/run_os12_ux_local.sh --build` → both envs compile. Commit, push, open PR.
- [ ] Device captures (after the owner's OTA OK): `/hub/show` home (two needs), printer (lab row), `lab-judge`
  pages 1..n, `lab-judge-send` in each state.

### Task 6: end-to-end check (after all three ship)

- [ ] With a printing lab experiment: Pi Hub, Local AI's Print lab page and the display all show the same top items
  and "Lab · E-0nn"; after it finishes all three show "Judge E-0nn"; judging on the display → `lab pull` on the Mac
  applies it → the item clears on all three within a minute. Record the result in the spec's status line.
