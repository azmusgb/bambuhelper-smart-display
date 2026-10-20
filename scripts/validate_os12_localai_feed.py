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
    with tempfile.TemporaryDirectory() as td:
        binary = Path(td) / "localai-feed-smoke"
        subprocess.run(["c++", "-std=c++11", "-O1", "-Wall", "-Wextra", "-Werror", "-pedantic", "-o", str(binary), str(TEST)], check=True)
        out = subprocess.run([str(binary)], check=False, capture_output=True, text=True)
        if out.returncode != 0:
            raise ValidationError("localai feed smoke test failed:\n" + out.stdout)


def validate(repo: Path) -> None:
    smoke()
    for rel in ("include/workshop_localai_feed_core.hpp", "include/workshop_localai_feed.h", "src/workshop_localai_feed.cpp"):
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
    fetch = block(feed, "bool openGet(WiFiClientSecure& client, const char* path, const char* accept, size_t& contentLength, char* contentType,")
    need(fetch, "client.connect(ip, 443, name, ca, nullptr, nullptr)", "TLS to Local AI's address, pinned to its CA and certificate name")
    need(fetch, "GET %s HTTP/1.0", "one HTTP/1.0 request (no chunked body)")
    need(fetch, "while (!client.available() && client.connected() && millis() - sentAt < 8000UL) delay(10);",
         "waits for the answer before reading it (12.3.11: a read straight away gave HTTP 0)")
    need(fetch, "X-LocalAI-Display-Key: %s", "the display key signs the request in")
    need(fetch, "memset(key, 0, sizeof(key));", "the key copy is wiped after the request")
    need(block(feed, "bool fetch(Card* cards, std::uint8_t& count, char* imagePath, char* imageTitle, char* imageText, char* error, size_t errorLen)"),
         'openGet(client, "/api/display/feed"', "the feed route")
    # 12.4.2: ask buttons and the latest image.
    need(block(feed, "bool ask(const char* question, char* answer, size_t answerLen)"), '"/api/display/ask?q=%s"', "the ask route")
    need(feed, "if (!lai::validQuestion(question)) return false;", "only the three questions are asked")
    image = block(feed, "bool downloadImage(const char* path, char* error, size_t errorLen)")
    need(image, "contentLength > lai::kMaxImageBytes", "the picture is size-capped")
    need(image, "if (got >= limit) { tooLarge = true; break; }", "a picture without a length is capped too")
    need(image, 'strncmp(type, "image/jpeg", 10)', "only JPEG is downloaded")
    need(image, "lai::jpegSize(g_image, got, w, h)", "a baseline JPEG the display can draw")
    need(feed, 'lai::validImagePath(c["imageUrl"] | "")', "only Local AI's own image route is fetched")
    forbid(feed, "setInsecure", "certificate checks are never skipped")
    need(feed, 'LittleFS.rename("/localai.tmp", kSettingsPath)', "settings saved whole (temp file, then rename)")
    forbid(feed, "Preferences", "settings are not kept in NVS (it is nearly full on the WS350)")
    need(block(feed, "void fetchTask(void* arg)"), "lai::nextDelayMs(g_snap.failures)", "backs off while Local AI doesn't answer")
    need(block(feed, "void fetchTask(void* arg)"), "generation == g_generation", "cards fetched under old settings are dropped")
    calm = block(hub, "static void wtDrawCalm(const WtPrint& w)")
    need(calm, "workshop::localai::fresh(millis(), ai.lastSuccessAtMs)", "only fresh cards are shown")
    need(calm, "wtl::calmLayout(s, aiShown)", "layout makes room only when a card is shown")
    card = block(hub, "static void wtDrawCalmAiCard(const wsm::Rect& r, const workshop::localai::Card& card)")
    for control in ("uiBottomNav(", "wsDrawRowBody(", "hubV1125Action(", "wsDrawChevronRight("):
        forbid(card, control, "the card is display only")
    # 12.4.0: Local AI is the third tab, leads the calm screen and takes Home's bottom row.
    need(hub, 'labels[4]={"Home","Printer","Local AI","More"}', "the third tab is Local AI")
    need(web, '{"id":"workshop","label":"Local AI"', "the catalog names the third tab Local AI")
    need(calm, "if (aiFirst) wtDrawCalmAiCard(c.status, wtAiCard(rot));", "Local AI's card leads the calm screen")
    need(calm, "printerBusy", "the printer's line only while it is doing something")
    need(block(hub, "static const char* wtHomeExtra(WsRowView& v)"), "wtAiCard(0)", "Home's bottom row is Local AI")
    print("PASS: OS12 Local AI cards (smoke test, service, routes without secrets, pinned TLS with backoff, calm card)")


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
