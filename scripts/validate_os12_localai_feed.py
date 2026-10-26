#!/usr/bin/env python3
"""Validate the 12.3.10 Local AI cards in a reconstructed WS350 tree (apply_workshop_os12_localai_feed.py).

Checks the host smoke test, that the service is started and polled, that the portal routes exist once and never
send the key or CA back, that the fetch pins Local AI's CA and certificate name and backs off, and that the calm
screen draws the card only from fresh cards and stays one wake target.
"""
from __future__ import annotations

import argparse
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEST = ROOT / "tests/workshop_os12_localai_feed_smoke.cpp"
LAB_TEST = ROOT / "tests/workshop_os12_lab_judge_smoke.cpp"


class ValidationError(Exception):
    pass


def need(text: str, needle: str, label: str) -> None:
    if needle not in text:
        raise ValidationError(f"missing: {label} ({needle!r})")


def forbid(text: str, needle: str, label: str) -> None:
    if needle in text:
        raise ValidationError(f"forbidden: {label} ({needle!r})")


def block(text: str, signature: str) -> str:
    start = text.find(signature)
    if start < 0:
        raise ValidationError(f"missing function: {signature}")
    depth, i = 0, text.find("{", start)
    while i < len(text):
        depth += {"{": 1, "}": -1}.get(text[i], 0)
        if depth == 0:
            return text[start:i + 1]
        i += 1
    raise ValidationError(f"unterminated function: {signature}")


def smoke() -> None:
    for name, test in (("localai-feed-smoke", TEST), ("lab-judge-smoke", LAB_TEST)):
        with tempfile.TemporaryDirectory() as td:
            binary = Path(td) / name
            subprocess.run(["c++", "-std=c++11", "-O1", "-Wall", "-Wextra", "-Werror", "-pedantic", "-o", str(binary), str(test)], check=True)
            out = subprocess.run([str(binary)], check=False, capture_output=True, text=True)
            if out.returncode != 0:
                raise ValidationError(f"{name} failed:\n" + out.stdout)


def validate(repo: Path) -> None:
    smoke()
    for rel in ("include/workshop_localai_feed_core.hpp", "include/workshop_localai_feed.h", "src/workshop_localai_feed.cpp",
                "include/workshop_lab_judge.hpp"):
        if not (repo / rel).is_file():
            raise ValidationError(f"missing {rel}")
    main = (repo / "src/main.cpp").read_text(encoding="utf-8")
    web = (repo / "src/web_server.cpp").read_text(encoding="utf-8")
    hub = (repo / "src/smart_hub.cpp").read_text(encoding="utf-8")
    feed = (repo / "src/workshop_localai_feed.cpp").read_text(encoding="utf-8")
    need(main, "workshopLocalAiFeedBegin();", "service started")
    need(main, "workshopLocalAiFeedLoop();", "service polled")
    for route in ('SECURE_GET("/os12/localai/status"', 'SECURE_POST("/os12/localai/config"', 'SECURE_POST("/os12/localai/clear"'):
        if web.count(route) != 1:
            raise ValidationError(f"route must be registered once: {route}")
    status = block(web, "static void sendWorkshopLocalAiStatus(int httpCode = 200)")
    for secret in ('doc["key"]', 'doc["ca"]', "g_key", "caPem"):
        forbid(status, secret, "the status route never sends the key or CA")
    fetch = block(feed, "bool openRequestTo(WiFiClientSecure& client, const char* address, const char* name, const char* ca, char* key, const char* method,")
    need(fetch, "client.connect(ip, 443, name, ca, nullptr, nullptr)", "TLS to Local AI's address, pinned to its CA and certificate name")
    need(fetch, "%s %s HTTP/1.0", "one HTTP/1.0 request (no chunked body)")
    need(fetch, "while (!client.available() && client.connected() && millis() - sentAt < waitMs) {",
         "waits for the answer before reading it (12.3.11: a read straight away gave HTTP 0)")
    need(fetch, "if (yieldToPerson && somethingWaits())", "12.6: the long poll gives way to a person at once")
    need(fetch, "X-LocalAI-Display-Key: %s", "the display key signs the request in")
    need(fetch, "memset(key, 0, 56);", "the key copy is wiped after the request")
    need(block(feed, "bool fetch(FeedResult& r, char* error, size_t errorLen)"), '"/api/display/feed"', "the feed route")
    # 12.4.2 ask buttons and pictures; 12.6 feed v2: messages, approvals, heartbeat, long poll.
    need(block(feed, "bool ask(const char* question, char* answer, size_t answerLen)"), '"/api/display/ask?q=%s"', "the ask route")
    need(feed, "if (!lai::validQuestion(question)) return false;", "only the fixed questions are asked")
    need(feed, "strcmp(g_imageWant, g_imageLoaded) != 0", "a new picture is fetched in the background, once")
    need(feed, "lai::messageIsNew(seq, lastSeq,", "12.6: a message shows once, and a restart doesn't replay old ones")
    need(feed, "lai::validPage(m[\"action\"][\"page\"] | \"\")", "12.6: a message may open only known pages")
    need(feed, "minutes >= 1 && minutes <= 240", "12.6: a message's timer is bounded")
    need(block(feed, "bool workshopLocalAiFeedDecide(const char* id, bool approve)"), "decidable = g_approvals[i].decidable;",
         "12.6: only an approval Local AI marked decidable is sent")
    need(feed, '"/api/display/approvals/decide"', "12.6: the decide route")
    need(feed, '"/api/display/events?since=%s"', "12.6: the long poll")
    need(feed, '"/api/display/heartbeat"', "12.6: the heartbeat")
    forbid(feed, 'beat["key"]', "the heartbeat never carries the key")
    pair = block(feed, "void runPair()")
    need(pair, "fetchCa(address, ca, sizeof(ca), error, sizeof(error))", "12.7: pairing reads Local AI's CA first")
    need(pair, 'openRequestTo(client, address, name, ca, nullptr, "POST", "/api/display/pair"', "12.7: the code goes over HTTPS pinned to that CA, with no key")
    need(pair, "lai::validKey(key)", "12.7: only a display key is saved")
    need(pair, "workshopLocalAiFeedConfigure(address, name, key, ca)", "12.7: saved as by the portal")
    need(pair, "memset(key, 0, sizeof(key));", "12.7: the key copy is wiped")
    image = block(feed, "bool downloadImage(const char* path, char* error, size_t errorLen)")
    need(image, "contentLength > lai::kMaxImageBytes", "the picture is size-capped")
    need(image, "if (got >= limit) { tooLarge = true; break; }", "a picture without a length is capped too")
    need(image, 'strncmp(type, "image/jpeg", 10)', "only JPEG is downloaded")
    need(image, "lai::jpegSize(g_image, got, w, h)", "a baseline JPEG the display can draw")
    need(feed, 'lai::validImagePath(c["imageUrl"] | "")', "only Local AI's own image route is fetched (the card)")
    need(feed, 'lai::validImagePath(i["imageUrl"] | "")', "only Local AI's own image route is fetched (the gallery)")
    forbid(feed, "setInsecure", "certificate checks are never skipped")
    need(feed, 'LittleFS.rename("/localai.tmp", kSettingsPath)', "settings saved whole (temp file, then rename)")
    forbid(feed, "Preferences", "settings are not kept in NVS (it is nearly full on the WS350)")
    need(block(feed, "void runFeed(std::uint32_t generation)"), "lai::nextDelayMs(g_snap.failures)", "backs off while Local AI doesn't answer")
    need(block(feed, "void runFeed(std::uint32_t generation)"), "generation == g_generation", "cards fetched under old settings are dropped")
    calm = block(hub, "static void wtDrawCalm(const WtPrint& w)")
    need(calm, "workshop::localai::fresh(millis(), ai.lastSuccessAtMs)", "only fresh cards are shown")
    need(calm, "wtl::calmLayout(s, aiShown)", "layout makes room only when a card is shown")
    card = block(hub, "static void wtDrawCalmAiCard(const wsm::Rect& r, const workshop::localai::Card& card)")
    for control in ("uiBottomNav(", "wsDrawRowBody(", "hubV1125Action(", "wsDrawChevronRight("):
        forbid(card, control, "the card is display only")
    # 12.4.0: Local AI is the third tab, leads the calm screen and takes Home's bottom row.
    need(hub, 'labels[4]={"Home","Printer","Local AI","More"}', "the third tab is Local AI")
    need(web, '{"id":"workshop","label":"Local AI"', "the catalog names the third tab Local AI")
    need(calm, "if (aiFirst) wtDrawCalmAiCard(c.status, wtCalmCard(rot, hid, shown));", "Local AI's card leads the calm screen")
    need(calm, "const int8_t hid = wtJudgeHiddenIndex();", "26 Oct 2026: Later hides the judge card from the calm rotation too")
    need(calm, "printerBusy", "the printer's line only while it is doing something")
    need(block(hub, "static const char* wtHomeExtra(WsRowView& v)"), "wtHomeSummary(others)", "Home's Local AI row is the card that matters most")
    # 26 Oct 2026: Pi Hub's one "Needs you" list and the Print lab card.
    fetch_fn = block(feed, "bool fetch(FeedResult& r, char* error, size_t errorLen)")
    need(fetch_fn, 'doc["needs"].as<JsonArray>()', "the feed's needs list is read")
    need(fetch_fn, "r.needsFromPi = !needs.isNull();", "a feed without needs (Pi Hub not answering) falls back to the cards")
    need(fetch_fn, "lai::setNeed(r.needs[r.needCount++]", "needs are copied whole-character (UTF-8 safe)")
    need(fetch_fn, 'copyText(out.run, sizeof(out.run), c["run"] | "");', "a lab card keeps its run")
    need(block(feed, "void runFeed(std::uint32_t generation)"), "g_snap.needsFromPi = r.needsFromPi;", "needs reach the snapshot")
    top = block(hub, "static __attribute__((noinline)) uint8_t wtHomeTop(const WorkshopLocalAiFeedSnapshot& ai, WtHomeRow out[2], uint8_t& others)")
    need(top, "const bool needsPresent = fresh && ai.needsFromPi;", "Pi Hub's list wins whenever the feed carried it, even empty")
    need(top, "workshop::localai::homeSummaryTop(ai.needs, nn, needsPresent, ai.cards, nc, idx, fromNeeds, others, wtJudgeHidden())",
         "idle Home's two rows: needs first, else cards (less the judge card Later hid here)")
    forbid(top, "workshopLocalAiFeedSnapshot()", "wtHomeTop uses the caller's one snapshot")
    need(block(hub, "static __attribute__((noinline)) uint8_t wtHomeRows(WtHomeRow rows[2], uint8_t& others, char* weather, size_t weatherLen)"),
         "workshopLocalAiFeedSnapshot()", "one snapshot per Home frame or touch, in a leaf")
    forbid(block(hub, "static void wtDrawHomeIdle(const WtPrint& w)"), "workshopLocalAiFeedSnapshot()", "no snapshot held while idle Home draws its rows")
    for fn in ("static uint8_t wtAiCount()", "static workshop::localai::Card wtAiCard(uint8_t i)", "static int8_t wtLabExtraIndex()",
               "static void wtDrawCalm(const WtPrint& w)"):
        forbid(block(hub, fn), "workshopLocalAiFeedSnapshot()", "small reads in hot draw paths (8 KB loop stack)")
    need(top, '"Pi Hub isn\'t answering"', "says when Pi Hub's list is missing")
    need(block(hub, "static void wtDrawHomeIdle(const WtPrint& w)"), "wtl::homeNeedRow(v, i)", "idle Home draws two need rows")
    need(block(hub, "static const char* wtHomeExtra(WsRowView& v)"), "wtLabExtraIndex()", "the Print lab card takes the printing Home's extra row")
    # 26 Oct 2026: Judge it on the display.
    need(hub, '#include "workshop_lab_judge.hpp"', "the Judge it rules are included")
    need(hub, "static wlab::LabJudge g_wtJudge;", "the sheet and its draft live in static storage")
    for fn in ("static __attribute__((noinline)) void wtDrawJudge(const wsm::Screen& s) {",
               "static __attribute__((noinline)) bool wtJudgeTouch(const wsm::Screen& s, int16_t x, int16_t y) {",
               "static __attribute__((noinline)) bool wtJudgePressRect(const wsm::Screen& s, int16_t x, int16_t y, wsm::Rect& out) {",
               "static __attribute__((noinline)) void wtJudgeTick() {"):
        body = block(hub, fn)
        forbid(body, "workshopLocalAiFeedSnapshot()", "Judge it never copies the whole feed snapshot (8 KB loop stack)")
        forbid(body, "wlab::LabJudge ", "Judge it keeps no sheet on the stack")
    need(block(hub, "static void wtDrawWorkshop(bool full) {"), "if (g_wtAiOverlay == 5) { wtDrawJudge(s); return; }", "the sheet is the Local AI tab's overlay 5")
    need(block(hub, "static bool wtWorkshopTouch(int16_t x, int16_t y) {"), "if (g_wtAiOverlay == 5) return wtJudgeTouch(s, x, y);", "the sheet owns its touches")
    need(block(hub, "static bool hubPressRect(int16_t x, int16_t y, wsm::Rect& out) {"), "if (g_wtAiOverlay == 5) return wtJudgePressRect(s, x, y, out);",
         "a press on the sheet outlines only its live targets")
    need(block(hub, "static void wtJudgeSend() {"), "g_wtJudge.beginSend(g_wtJudgeBody, wlab::kMaxPayload, esp_random(), esp_random())",
         "the verdict's request id is random, kept while the same draft is resent")
    need(block(hub, "static bool wtShowPrinterView(const char* name) {"), "return wtJudgeShow(name);", "/hub/show lab-judge pages")
    need(web, '{"id":"lab-judge","label":"Judge it","group":"Primary"}', "/hub/views lists the Judge it sheet")
    need(web, '{"id":"lab-judge-send","label":"Judge it - Send","group":"Primary"}', "/hub/views lists the Judge it Send page")
    judge = block(feed, "void runJudgeLoad() {")
    need(judge, '"/api/display/lab/judge?run=%s"', "the judge route")
    need(judge, "workshop::lab::validRun(run)", "only a run id goes into the path")
    need(judge, "readBody(client, contentLength, body, cap, got, error, sizeof(error))", "the sheet is read whole, bounded")
    need(judge, "workshop::lab::parseSheet(body, got, g_judgeSheet)", "the bounded reader parses it")
    verdict = block(feed, "void runVerdict() {")
    need(verdict, 'workshop::lab::verdictAccepted(g_lastCode, g_verdictId, doc["id"] | "")', "a 2xx naming the sent id is accepted, whatever its status")
    forbid(verdict, '"pending")', "a resent id's applied/refused status is not an error")
    need(verdict, '"/api/display/lab/verdict"', "the verdict route")
    need(verdict, "DeserializationOption::Filter(filter)", "only id and status are read from the answer")
    need(block(feed, "bool somethingWaits() {"), "g_judgeLoadPending || g_verdictPending", "the long poll gives way to Judge it")
    need(fetch, "if (code < 200 || code > 299) {", "the verdict route's 202 is a success")
    need(fetch, 'lai::copyUtf8(error, errorLen, why["error"] | "");', "Local AI's words are cut whole-character")
    print("PASS: OS12 Local AI cards (smoke test, service, routes without secrets, pinned TLS with backoff, calm card, Judge it)")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True)
    args = parser.parse_args()
    try:
        validate(Path(args.repo).resolve())
    except (ValidationError, subprocess.CalledProcessError) as exc:
        raise SystemExit(f"FAIL: {exc}") from exc
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
