# Display on Pi Hub, step 2: the firmware's Pi Hub connection — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Workshop OS can pair with Pi Hub (`home.home.arpa`, 10.0.0.30) instead of Local AI and run everything it
runs today (feed v2, long poll, Clear plate, Judge it, approvals, Ask, pictures, heartbeat) over that one connection,
with Local AI kept as the rollback choice.

**Architecture:** The feed service (`firmware/platform/localai/`) stays one service with one saved connection. The
connection gains a `backend` (Local AI or Pi Hub) that picks the key header, the CA path, the default address and
name, the key format and the words in errors. Pairing with one backend replaces the other. The card rules learn Pi
Hub's `printer` and `ai` kinds and its picture paths; the card cap grows from 6 to 8 so the seven household cards and
the "AI unavailable — PC asleep" line all fit. The touchscreen and portal pairing get a Pi Hub / Local AI choice.

**Tech Stack:** C++ ESP32 (PlatformIO, ArduinoJson 7, LittleFS), g++ host smoke tests (`-std=c++11 -Werror`), Python
validators and `apply_*` patch scripts.

**Spec:** `~/dev/pi-hub/docs/superpowers/specs/2026-10-31-display-on-pi-hub-design.md` (approved; §1 pairing and
connection, §4 testing and rollout step 2). Pi Hub's side is live at pi-hub `main` `1a2b061`.

## Global Constraints

- Pi Hub's contract (live): `POST /api/display/pair {code}` → `{key, tlsName: "home.home.arpa"}`; key is
  `"hubd_"` + 32 URL-safe base64 characters (`A–Z a–z 0–9 - _`), 37 in all; sent as `X-Hub-Display-Key`; CA at
  `http://10.0.0.30/home-ca.crt`; pictures at `/api/display/images/<0–5>` and `/api/display/images/poster`.
- Every other route and body is the same as Local AI's (`/api/display/feed|events|ask|approvals|approvals/decide|
  printer/clear|lab/judge|lab/verdict|heartbeat`); the parser does not change (spec D5).
- Pi Hub's feed cards, in order: `needs, printer, lab, home, playing, materials, weather`, then Local AI's
  `watch, running, done, disk` (and `image`, which becomes a picture) or one `ai` card
  `{kind:"ai", id:"ai-off", title:"AI unavailable — PC asleep", tone:"info"}`.
- One connection at a time. Saved settings without `backend` are Local AI (today's displays keep working unchanged).
- Settings, key and CA stay in `/localai.json` on LittleFS; nothing new in NVS (it is nearly full).
- Never send the key or CA back out (portal status, logs). Wipe key copies after use (`memset`, as today).
- A 401/403 never clears the saved key and is never retried faster than `nextDelayMs` back-off.
- Screen words: "Pi Hub", "Local AI", "Pair with Pi Hub", "Paired with Pi Hub.", "AI unavailable — PC asleep".
  No other screen changes (spec: not goals).
- OTA/flash only through the normal candidate → CI → physical acceptance process; flashing during a print is fine
  (`--allow-active-print`), but check `runningSourceCommit` and open PRs first.

## Review Focus

1. A display saved before this change (no `backend` field) boots → still Local AI, same header and key rules
   (Task 2, validator `legacy settings are Local AI`; Task 1 `backend_from_settings`).
2. PC asleep: 7 household cards + the `ai` card → all 8 kept, in feed order (Task 1 `pihub_sample_all_kept`).
3. PC awake: 7 household + 4 AI cards → household first, the cap drops only AI cards (Task 1 `cap_drops_tail`).
4. A `wsd_` key offered for Pi Hub, or a `hubd_` key for Local AI → refused, nothing saved (Task 1 `key_per_backend`).
5. A picture path outside `/api/display/images/<digit>|poster` (or with a space/CRLF) → refused (Task 1 `hub_image_paths`).

---

### Task 1: Card and connection rules (core header, host-tested)

**Files:**
- Modify: `firmware/platform/localai/workshop_localai_feed_core.hpp`
- Test: `tests/workshop_os12_localai_feed_smoke.cpp`
- Create: `tests/fixtures/pihub_feed_v2_pc_asleep.json`, `tests/fixtures/pihub_feed_v2_pc_awake.json`

**Interfaces:**
- Produces (namespace `workshop::localai`):
  - `enum class Backend : uint8_t { LocalAi = 0, PiHub = 1 };`
  - `struct BackendInfo { const char* label; const char* keyHeader; const char* caPath; const char* defaultAddress; const char* defaultName; };`
  - `inline const BackendInfo& backendInfo(Backend b);` — LocalAi: `"Local AI"`, `"X-LocalAI-Display-Key"`,
    `"/localai-ca.crt"`, `"10.0.0.21"`, `"localai.home.arpa"`; PiHub: `"Pi Hub"`, `"X-Hub-Display-Key"`,
    `"/home-ca.crt"`, `"10.0.0.30"`, `"home.home.arpa"`.
  - `inline Backend backendFrom(const char* s);` — `"pihub"` → PiHub, anything else (incl. null/"") → LocalAi.
  - `inline const char* backendId(Backend b);` — `"localai"` / `"pihub"`.
  - `inline bool validHubKey(const char* k);` and `inline bool validKeyFor(Backend b, const char* k);`
    (`validKey` stays as is for Local AI).
  - `kMaxCards` = 8; `shownKind` also accepts `"printer"` and `"ai"`; `askFor`: `printer` → `"health"`, `ai` → nullptr.
  - `validImagePath` also accepts `/api/display/images/` followed by exactly one digit `0`–`5` or `poster`, nothing after.
  - `inline uint8_t keepCards(const char* const* kinds, uint8_t n, uint8_t* outIndex);` — indexes of the cards
    `fetch` keeps, in order: skips `image` and kinds `shownKind` refuses, stops at `kMaxCards`. `fetch` (Task 2) uses it.

- [ ] **Step 1: Write the fixtures.** Generate both from Pi Hub's real builder so they are the contract, not a guess:
  in `~/dev/pi-hub` run `python -c` over `hub.display_feed.build(...)` with seven household inputs filled
  (needs with 2 items, printer printing, a lab judge card, home issue, Plex playing, spools, weather) and
  `ai={"available": False, ...}` for `_pc_asleep`, and four AI cards plus one image for `_pc_awake`. Save the JSON
  (2-space indent). Each file must be under 12288 bytes (`kMaxBodyBytes`).

- [ ] **Step 2: Write failing tests** in `tests/workshop_os12_localai_feed_smoke.cpp`:

```cpp
// backend_from_settings
check(lai::backendFrom(nullptr) == lai::Backend::LocalAi && lai::backendFrom("") == lai::Backend::LocalAi &&
      lai::backendFrom("pihub") == lai::Backend::PiHub && lai::backendFrom("PiHub") == lai::Backend::LocalAi, "backend ids");
check(!strcmp(lai::backendInfo(lai::Backend::PiHub).keyHeader, "X-Hub-Display-Key") &&
      !strcmp(lai::backendInfo(lai::Backend::PiHub).caPath, "/home-ca.crt") &&
      !strcmp(lai::backendInfo(lai::Backend::PiHub).defaultName, "home.home.arpa"), "pi hub connection");
// key_per_backend
const char* hub = "hubd_AbC-_0123456789abcdefghijklmnopq";            // 5 + 32
check(lai::validKeyFor(lai::Backend::PiHub, hub), "hub key ok");
check(!lai::validKeyFor(lai::Backend::LocalAi, hub), "hub key not for Local AI");
check(!lai::validKeyFor(lai::Backend::PiHub, "wsd_" "0123456789abcdef0123456789abcdef0123456789abcdef"), "wsd key not for hub");
check(!lai::validHubKey("hubd_AbC-_0123456789abcdefghijklmnop"), "31 chars");
check(!lai::validHubKey("hubd_AbC-_0123456789abcdefghijklmno+q"), "not url-safe");
check(!lai::validHubKey("hubd_AbC-_0123456789abcdefghijklmnopqr"), "33 chars");
// hub_image_paths
check(lai::validImagePath("/api/display/images/0") && lai::validImagePath("/api/display/images/5") &&
      lai::validImagePath("/api/display/images/poster"), "hub pictures");
check(!lai::validImagePath("/api/display/images/6") && !lai::validImagePath("/api/display/images/12") &&
      !lai::validImagePath("/api/display/images/0?x") && !lai::validImagePath("/api/display/images/") &&
      !lai::validImagePath("/api/display/images/poster2"), "only hub's own picture paths");
// pihub_sample_all_kept: kinds from tests/fixtures/pihub_feed_v2_pc_asleep.json, in order
const char* asleep[] = {"needs", "printer", "lab", "home", "playing", "materials", "weather", "ai"};
uint8_t idx[16];
check(lai::keepCards(asleep, 8, idx) == 8 && idx[1] == 1 && idx[7] == 7, "asleep: all eight kept");
// cap_drops_tail: pc_awake order
const char* awake[] = {"needs", "printer", "lab", "home", "playing", "materials", "weather", "watch", "image", "running", "done", "disk"};
check(lai::keepCards(awake, 12, idx) == 8 && idx[7] == 7, "awake: household first, then one AI card, image skipped");
check(lai::askFor(card("printer")) && !strcmp(lai::askFor(card("printer")), "health") && !lai::askFor(card("ai")), "asks");
static_assert(sizeof(lai::Card) * lai::kMaxCards <= 1900, "eight cards stay in the snapshot budget");
```

  (`card(kind)` is a tiny helper in the test returning a zeroed `Card` with that kind; use the file's existing
  `check` helper.) Also add a test that reads both fixture files' `"kind"` values in order with a plain string scan
  (no JSON library in host tests) and asserts the arrays above match them, so the fixtures and the test can't drift.

- [ ] **Step 3: Run, expect compile failure:**
  `g++ -std=c++11 -O1 -Wall -Wextra -Werror -pedantic tests/workshop_os12_localai_feed_smoke.cpp -o /tmp/lai && /tmp/lai`

- [ ] **Step 4: Implement** the Interfaces above in `workshop_localai_feed_core.hpp`. Update the file's comments where
  they say "Local AI" for rules both backends share. Run any other smoke test that includes this header
  (`grep -l workshop_localai_feed_core tests/*.cpp`) — `tabs_layout` likely does; 8 cards must still lay out.

- [ ] **Step 5: Run** the command from Step 3 and every smoke test from Step 4. Expected: all pass, no warnings.

- [ ] **Step 6: Commit** `feat(localai): Pi Hub backend rules, printer/ai cards, 8-card cap`.

### Task 2: The feed service talks to either backend

**Files:**
- Modify: `firmware/platform/localai/workshop_localai_feed.cpp`, `firmware/platform/localai/workshop_localai_feed.h`
- Modify: `scripts/validate_os12_localai_feed.py`

**Interfaces:**
- Consumes: Task 1's `Backend`, `backendInfo`, `backendFrom`, `backendId`, `validKeyFor`, `keepCards`.
- Produces (header):
  - `bool workshopLocalAiFeedConfigure(const char* address, const char* tlsName, const char* key, const char* caPem, workshop::localai::Backend backend = workshop::localai::Backend::LocalAi);`
  - `bool workshopLocalAiFeedPair(const char* address, const char* code, workshop::localai::Backend backend = workshop::localai::Backend::LocalAi);`
  - `workshop::localai::Backend workshopLocalAiFeedBackend();` — the saved one (LocalAi when not set up).
  - `WorkshopLocalAiFeedStatus` and `WorkshopLocalAiFeedSnapshot` gain `workshop::localai::Backend backend` and
    `int8_t aiAvailable` (−1 the feed didn't say — Local AI; 0 false; 1 true) from the feed's `ai.available`.

- [ ] **Step 1: Write failing validator checks** in `scripts/validate_os12_localai_feed.py` (replace the checks that
  pin `X-LocalAI-Display-Key` and `lai::validKey(key)`):
  - `need(fetch, '"%s: %s\\r\\n", info.keyHeader', "the backend's key header signs the request in")`
  - `forbid(fetch, "X-LocalAI-Display-Key: %s", "no hard-coded key header")`
  - `need(pair, "lai::validKeyFor(backend, key)", "only that backend's key is saved")`
  - `need(pair, "workshopLocalAiFeedConfigure(address, name, key, ca, backend)", "saved as by the portal")`
  - `need(begin, 'lai::backendFrom(doc["backend"] | "")', "legacy settings are Local AI")`
  - `need(configure, 'doc["backend"] = lai::backendId(backend)', "the backend is saved")`
  - `need(fetchCaBlock, "info.caPath", "the CA comes from the backend's own path")`
  - `need(fetchBlock, "lai::keepCards(", "the cards kept follow the core rule")`
  - `need(feed, 'doc["ai"]["available"]', "the AI line follows the feed's ai.available")`
  - `forbid(runFeedFailBranch, "workshopLocalAiFeedClear", "a failure (even 401) never forgets the key")`
  Run `python3 scripts/validate_os12_localai_feed.py`; expect failures on exactly these.

- [ ] **Step 2: Implement.**
  - A `g_backend` beside `g_address`/`g_tlsName`/`g_key`, under `g_mux`, loaded from `/localai.json` `backend`, saved by
    Configure, reset by Clear, bumped `g_generation` on change (as the other settings do).
  - `openRequestTo` takes the backend and sends `backendInfo(b).keyHeader`; every "Local AI" in its error strings
    uses `info.label` (`"%s isn't answering, or its certificate didn't match."`, `"%s turned the display key down
    (HTTP %d)."`, `"%s answered HTTP %d."`, `"%s's answer was too large."`, `"%s's answer was not valid JSON."`).
    Status strings in `runFeed`/`Begin` likewise (`"%s cards are current."`, `"Waiting for the first %s cards."`,
    `"Cards are not set up."`).
  - `fetchCa` takes the backend and GETs `info.caPath`; `runPair` starts from `info.defaultName`, checks
    `validKeyFor(backend, key)`, saves with the backend; success words `"Paired with %s."`.
  - `configuredLocked` uses `validKeyFor(g_backend, g_key)`.
  - `fetch` gathers the cards' kinds and calls `lai::keepCards`; reads `doc["ai"]["available"]` into `aiAvailable`
    (absent → −1).
  - Key buffers: Pi Hub keys are 37 characters; the 56-byte buffers and `memset(key, 0, 56)` stay.

- [ ] **Step 3: Run** `python3 scripts/validate_os12_localai_feed.py` → PASS, and Task 1's smoke test → PASS.

- [ ] **Step 4: Commit** `feat(localai): one connection to Local AI or Pi Hub`.

### Task 3: Choosing Pi Hub when pairing (touchscreen, portal, script)

**Files:**
- Modify: `firmware/platform/ui/tabs_pages.cppfrag` (pairing overlay 4, `wtPairAddress`, captures `localai-pair-…`)
- Modify: `apply_workshop_os12_localai_feed.py` (portal handlers and the pairing form)
- Modify: `scripts/configure_localai_feed.py`
- Modify: the layout source that defines `wtl::pairInfoRect`/`pairKeyRect` and its smoke test, only if the choice
  needs a rect (find with `grep -rn pairInfoRect firmware tests`)

**Interfaces:**
- Consumes: Task 2's `workshopLocalAiFeedPair(address, code, backend)`, `workshopLocalAiFeedBackend()`,
  `workshopLocalAiFeedConfigure(..., backend)`, `backendInfo`, `backendId`, `backendFrom`.

- [ ] **Step 1: Write failing checks** (in `scripts/validate_os12_localai_feed.py`, which already reads these files):
  - the pair overlay draws two choices labelled `"Pi Hub"` and `"Local AI"` (44 px tall), Pi Hub chosen first time;
  - header `"Pair with %s"` from `backendInfo(...).label`; info line for Pi Hub:
    `"In Pi Hub: System, Workshop display, Pair display. Then type its code here."` (Local AI's line unchanged);
  - `wtPairAddress` uses the saved address only when the saved backend is the chosen one, else
    `backendInfo(chosen).defaultAddress`;
  - capture names: `localai-pair-…` stays Local AI; `localai-pairhub-123456-go` pairs with Pi Hub;
  - portal: `/os12/localai/pair` and `/os12/localai/config` take an optional `backend` field (`backendFrom`), status JSON
    gains `"backend": backendId(...)` and `"aiAvailable"`; the portal pairing form gets a Pi Hub / Local AI `<select>`
    that also fills the address (10.0.0.30 / 10.0.0.21);
  - `configure_localai_feed.py` gains `--backend {localai,pihub}` (default `localai`), which sets the address and name
    defaults and sends `backend`.
  If a choice rect is added, extend the tabs layout smoke test: both choice rects ≥ 44 px tall, inside the screen, not
  overlapping the keypad or `pairInfoRect`.

- [ ] **Step 2: Implement** to pass. The Local AI tab, Home and every other screen keep their words; only the pairing
  overlay and portal change. The `ai` card renders as an ordinary card row (title "AI unavailable — PC asleep",
  info tone) — that is the spec's one quiet line; no new drawing code.

- [ ] **Step 3: Run** the full local gate: `bash scripts/run_os12_ux_local.sh` and `bash scripts/run_os12_platform_local.sh`
  (both already run the validators and smoke tests CI runs). Expected: all PASS.

- [ ] **Step 4: Commit** `feat(display): pair with Pi Hub from the screen or the portal`.

### Task 4: Docs, candidate build, CI

**Files:**
- Modify: `docs/LOCALAI_CARDS.md` (Pi Hub connection: pairing, rollback, the `ai` line, the 8-card cap)
- Modify: release notes / version file the repo uses for candidates (find with `git log -5 --stat -- '*RELEASE*' '*version*'`)

- [ ] **Step 1: Docs** — a "Pi Hub connection" section: how to pair (Pi Hub System › Workshop display › Pair display,
  then the display's pairing screen, choose Pi Hub), what changes (one key, AI line when the PC sleeps), rollback
  (pair with Local AI again), and that step 3 (switch) and step 4 (retire) follow.
- [ ] **Step 2: Candidate build** with the repo's usual PlatformIO build (sandbox off). Expected: builds; RAM/flash
  report within the previous build's margins (record both).
- [ ] **Step 3: PR** to `main`; wait for CI (`validate.yml`, `os12-ux-architecture.yml`, `release-gate.yml`) green.
- [ ] **Step 4: Commit/PR body** lists the physical acceptance checks for step 3 (spec §4): pair; PC asleep → printer,
  Needs you, Clear plate, Judge it, now playing work and the AI line shows; PC awake → AI cards return, no pairing;
  Pi reboot → display recovers alone.

Physical acceptance and the switch itself are step 3 (own plan): flashing the candidate, pairing with Pi Hub and the
PC-asleep test happen there.
