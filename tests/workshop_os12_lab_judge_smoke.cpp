// Host smoke test for firmware/platform/ui/lab_judge.hpp (26 Oct 2026): the stepped Judge it sheet on the Workshop
// display. The same sheet as the phone's (Local AI app/public/print-lab.js), one strip per screen: paging, chip
// selection, "–" sent as null, the inconclusive reasons, the Send payload Local AI's POST /api/display/lab/verdict
// takes, the states (Waiting for the Mac, Done, the Mac's refusal, already judged with Change it), bounded parsing of
// GET /api/display/lab/judge, and the layout at 480x320 and 320x480 with 44 px targets.
#include "../firmware/platform/ui/lab_judge.hpp"

#include <cstdio>
#include <cstring>
#include <string>

using namespace workshop::lab;
static int failures = 0, checks = 0;
#define CHECK(c, what) do { ++checks; if (!(c)) { ++failures; std::printf("FAIL %s\n", what); } } while (0)

static const char* kThree =
    "{\"experiment\":\"E-021\",\"run\":\"PR-021-01\",\"judgeOn\":\"seam\",\"tabs\":[\"21A\",\"21B\",\"21C\"],"
    "\"criteria\":[{\"key\":\"print\",\"label\":\"Print\",\"choices\":[\"clean\",\"flawed\",\"failed\"]},"
    "{\"key\":\"apart\",\"label\":\"Comes apart\",\"choices\":[\"yes\",\"hard\",\"no\"]}],\"judged\":null,\"pending\":null}";

static bool load(LabJudge& j, const char* json) {
  j.clear();
  return j.load(json, strlen(json));
}

static bool contains(const char* s, const char* part) { return s && strstr(s, part) != nullptr; }

static bool validUtf8(const char* s) {
  const unsigned char* p = reinterpret_cast<const unsigned char*>(s);
  while (*p) {
    const unsigned char c = *p;
    const int n = c < 0x80 ? 0 : (c & 0xE0) == 0xC0 ? 1 : (c & 0xF0) == 0xE0 ? 2 : (c & 0xF8) == 0xF0 ? 3 : -1;
    if (n < 0) return false;
    ++p;
    for (int k = 0; k < n; ++k, ++p)
      if ((*p & 0xC0) != 0x80) return false;
  }
  return true;
}

static void gradeAll(LabJudge& j, int8_t choice) {
  for (uint8_t t = 0; t < j.s.tabCount; ++t)
    for (uint8_t c = 0; c < j.s.criterionCount; ++c) j.select(t, c, choice);
}

static void pagesAreTabsPlusSend() {
  LabJudge j;
  CHECK(load(j, kThree), "pages_are_tabs_plus_send: the sheet loads");
  CHECK(j.s.ok && !j.s.phoneOnly && j.s.tabCount == 3 && j.s.criterionCount == 2, "pages_are_tabs_plus_send: three strips, two criteria");
  CHECK(!strcmp(j.s.experiment, "E-021") && !strcmp(j.s.run, "PR-021-01") && !strcmp(j.s.judgeOn, "seam"), "pages_are_tabs_plus_send: ids kept");
  CHECK(j.pages() == 4, "pages_are_tabs_plus_send: one page per strip plus Send");
  CHECK(!j.sendPage(0) && !j.sendPage(2) && j.sendPage(3), "pages_are_tabs_plus_send: the last page is Send");
  CHECK(j.state() == State::Draft && j.startPage() == 0, "pages_are_tabs_plus_send: a new sheet opens on strip 1");
  CHECK(!strcmp(j.tabOf(1), "21B"), "pages_are_tabs_plus_send: page 2 is strip 21B");
  CHECK(j.select(1, 0, 2) && j.selected(1, 0) == 2, "pages_are_tabs_plus_send: a chip is selected");
  CHECK(j.select(1, 0, kNotJudged) && j.selected(1, 0) == kNotJudged, "pages_are_tabs_plus_send: \"–\" is selected");
  CHECK(!j.select(3, 0, 0), "pages_are_tabs_plus_send: the Send page has no strip");
  CHECK(!j.select(0, 2, 0), "pages_are_tabs_plus_send: no third criterion");
  CHECK(!j.select(0, 0, 3), "pages_are_tabs_plus_send: no fourth choice");
  CHECK(!j.select(0, 0, -3), "pages_are_tabs_plus_send: no negative choice");
  CHECK(!j.complete() && !j.canSend(), "pages_are_tabs_plus_send: Send waits for every strip on every criterion");
  gradeAll(j, 0);
  CHECK(j.complete() && j.canSend(), "pages_are_tabs_plus_send: all graded: Send");
  char title[64];
  j.title(title, sizeof(title), 1);
  CHECK(!strcmp(title, "Judge it \xC2\xB7 E-021 \xC2\xB7 Strip 21B (2 of 3)"), "pages_are_tabs_plus_send: header for strip 2");
  j.title(title, sizeof(title), 3);
  CHECK(!strcmp(title, "Judge it \xC2\xB7 E-021 \xC2\xB7 Send"), "pages_are_tabs_plus_send: header for Send");
}

static void dashIsNullInPayload() {
  LabJudge j;
  load(j, kThree);
  gradeAll(j, 0);
  j.select(1, 1, kNotJudged);
  char out[kMaxPayload];
  CHECK(j.payload(out, sizeof(out), "rq-0123456789abcdef", false), "dash_is_null_in_payload: payload written");
  CHECK(!strcmp(out, "{\"run\":\"PR-021-01\",\"requestId\":\"rq-0123456789abcdef\",\"grades\":{"
                     "\"21A\":{\"print\":\"clean\",\"apart\":\"yes\"},\"21B\":{\"print\":\"clean\",\"apart\":null},"
                     "\"21C\":{\"print\":\"clean\",\"apart\":\"yes\"}},\"inconclusive\":null,\"replace\":false}"),
        "dash_is_null_in_payload: the exact body Local AI takes, \"–\" as null");
  CHECK(jsonValid(out, strlen(out)), "dash_is_null_in_payload: valid JSON");
  CHECK(!j.payload(out, sizeof(out), "rq-xyz", false), "dash_is_null_in_payload: a bad request id is refused");
  CHECK(!j.payload(out, 40, "rq-0123456789abcdef", false) && out[0] == 0, "dash_is_null_in_payload: too small a buffer: nothing half-written");
}

static void payloadFits4k() {
  // Three strips, six criteria of four choices, every name as long as the display keeps it, with characters JSON
  // must escape.
  std::string json = "{\"experiment\":\"E-021\",\"run\":\"PR-021-01\",\"judgeOn\":\"x\",\"tabs\":[";
  for (int t = 0; t < 3; ++t) json += std::string(t ? "," : "") + "\"strip-" + char('A' + t) + "-123456\"";
  json += "],\"criteria\":[";
  for (int c = 0; c < 6; ++c) {
    json += std::string(c ? "," : "") + "{\"key\":\"criterion_key_" + char('a' + c) + "_123456\",\"label\":\"A long label\",\"choices\":[";
    for (int k = 0; k < 4; ++k) json += std::string(k ? "," : "") + "\"ch\\\"oice " + char('0' + k) + " 1234567890\"";
    json += "]}";
  }
  json += "],\"judged\":null,\"pending\":null}";
  LabJudge j;
  CHECK(load(j, json.c_str()) && j.s.tabCount == 3 && j.s.criterionCount == 6 && !j.s.phoneOnly,
        "payload_fits_4k_with_3_tabs_6_criteria: the sheet loads whole");
  CHECK(!strcmp(j.s.criteria[2].choices[1], "ch\"oice 1 1234567890"), "payload_fits_4k_with_3_tabs_6_criteria: escapes decoded");
  gradeAll(j, 3);
  j.select(2, 5, kNotJudged);
  char out[kMaxPayload];
  CHECK(j.payload(out, sizeof(out), "rq-ffffffffffffffff", true), "payload_fits_4k_with_3_tabs_6_criteria: fits in 4 KB");
  CHECK(strlen(out) < kMaxPayload && jsonValid(out, strlen(out)), "payload_fits_4k_with_3_tabs_6_criteria: valid JSON under Local AI's limit");
  CHECK(contains(out, "\"ch\\\"oice 3 1234567890\"") && contains(out, "\"replace\":true"),
        "payload_fits_4k_with_3_tabs_6_criteria: choices escaped back as sent, replace kept");
  char small[600];
  CHECK(!j.payload(small, sizeof(small), "rq-ffffffffffffffff", true) && small[0] == 0, "payload_fits_4k_with_3_tabs_6_criteria: never cut");
}

static void inconclusiveReasonSent() {
  CHECK(kReasonCount == 3 && !strcmp(kReasons[0], "It didn't finish printing") && !strcmp(kReasons[1], "I can't tell from this print") &&
            !strcmp(kReasons[2], "The wrong thing printed"),
        "inconclusive_reason_sent: the three reasons, word for word");
  LabJudge j;
  load(j, kThree);
  j.select(0, 0, 1);
  j.select(0, 1, kNotJudged);
  CHECK(!j.canSend(), "inconclusive_reason_sent: incomplete without a reason");
  CHECK(j.setReason(1) && j.reason == 1 && j.canSend(), "inconclusive_reason_sent: a reason makes it sendable");
  char out[kMaxPayload];
  CHECK(j.payload(out, sizeof(out), "rq-0000000000000001", false), "inconclusive_reason_sent: payload");
  CHECK(!strcmp(out, "{\"run\":\"PR-021-01\",\"requestId\":\"rq-0000000000000001\",\"grades\":{\"21A\":{\"print\":\"flawed\",\"apart\":null}},"
                     "\"inconclusive\":\"I can't tell from this print\",\"replace\":false}"),
        "inconclusive_reason_sent: the reason's words, ungraded strips left out");
  CHECK(j.setReason(-1) && !j.canSend(), "inconclusive_reason_sent: the reason can be taken back");
  CHECK(!j.setReason(3), "inconclusive_reason_sent: only the three reasons");
}

static void phoneOnlyShowsReason() {
  LabJudge j;
  CHECK(load(j, "{\"experiment\":\"E-022\",\"run\":\"PR-022-01\",\"judgeOn\":\"\",\"phoneOnly\":true,"
                "\"reason\":\"Judge it on your phone: this test compares A and B\"}"),
        "phone_only_shows_reason: loads");
  CHECK(j.s.phoneOnly && j.state() == State::PhoneOnly && j.pages() == 1, "phone_only_shows_reason: one page, phone only");
  CHECK(!strcmp(j.s.reason, "Judge it on your phone: this test compares A and B"), "phone_only_shows_reason: Local AI's words");
  bool on = false;
  CHECK(!strcmp(j.action(on), "Close") && on, "phone_only_shows_reason: Close");
  char out[kMaxPayload];
  CHECK(!j.canSend() && !j.payload(out, sizeof(out), "rq-0000000000000001", false), "phone_only_shows_reason: nothing to send");
  // More strips or choices than the display keeps: never a partial sheet; judged on the phone.
  std::string many = "{\"experiment\":\"E-023\",\"run\":\"PR-023-01\",\"tabs\":[\"A\",\"B\",\"C\",\"D\",\"E\",\"F\",\"G\"],"
                     "\"criteria\":[{\"key\":\"k\",\"label\":\"L\",\"choices\":[\"a\"]}],\"judged\":null,\"pending\":null}";
  CHECK(load(j, many.c_str()) && j.s.phoneOnly && j.pages() == 1 && contains(j.s.reason, "phone"), "phone_only_shows_reason: too many strips");
  std::string longChoice = "{\"experiment\":\"E-023\",\"run\":\"PR-023-01\",\"tabs\":[\"A\"],\"criteria\":[{\"key\":\"k\",\"label\":\"L\","
                           "\"choices\":[\"a choice far longer than the display keeps\"]}],\"judged\":null,\"pending\":null}";
  CHECK(load(j, longChoice.c_str()) && j.s.phoneOnly, "phone_only_shows_reason: a choice that would be cut");
}

static void judgedOpensOnChangeIt() {
  LabJudge j;
  CHECK(load(j, "{\"experiment\":\"E-021\",\"run\":\"PR-021-01\",\"judgeOn\":\"seam\",\"tabs\":[\"21A\",\"21B\",\"21C\"],"
                "\"criteria\":[{\"key\":\"print\",\"label\":\"Print\",\"choices\":[\"clean\",\"flawed\",\"failed\"]}],"
                "\"judged\":{\"at\":\"2026-10-26T18:32:05Z\",\"by\":\"phone\"},\"pending\":null}"),
        "judged_opens_on_change_it: loads");
  CHECK(j.s.judged && !strcmp(j.s.judgedBy, "phone") && !strcmp(j.s.judgedAt, "2026-10-26T18:32:05Z"), "judged_opens_on_change_it: who and when");
  CHECK(j.state() == State::Judged && j.startPage() == 3, "judged_opens_on_change_it: opens on the last page");
  bool on = false;
  CHECK(!strcmp(j.action(on), "Change it") && on, "judged_opens_on_change_it: Change it");
  CHECK(!j.select(0, 0, 0), "judged_opens_on_change_it: no changes before Change it");
  j.changeIt();
  CHECK(j.state() == State::Draft && j.startPage() == 0 && j.replace, "judged_opens_on_change_it: Change it starts a replacing draft");
  gradeAll(j, 1);
  char out[kMaxPayload];
  CHECK(j.beginSend(out, sizeof(out), 0x01234567UL, 0x89abcdefUL) && contains(out, "\"replace\":true") &&
            contains(out, "\"requestId\":\"rq-0123456789abcdef\""),
        "judged_opens_on_change_it: sends with replace: true");
  CHECK(j.state() == State::Sending, "judged_opens_on_change_it: sending");
  long t = 0;
  CHECK(isoToEpoch("2026-10-26T18:32:05Z", t) && t == 1793039525L, "iso time Z");
  CHECK(isoToEpoch("2026-10-26T20:32:05.123+02:00", t) && t == 1793039525L, "iso time with offset and fraction");
  CHECK(isoToEpoch("2000-02-29T23:59:59", t) && t == 951868799L, "iso time leap day, no zone (UTC)");
  CHECK(!isoToEpoch("yesterday", t) && !isoToEpoch("2026-13-01T00:00:00Z", t), "iso time refuses junk");
}

static void sendStates() {
  LabJudge j;
  load(j, kThree);
  gradeAll(j, 0);
  char out[kMaxPayload], first[24];
  CHECK(j.beginSend(out, sizeof(out), 1, 2), "send: begins");
  strcpy(first, j.requestId);
  CHECK(validRequestId(first) && !strcmp(first, "rq-0000000100000002"), "send: rq- and 16 hex digits");
  j.sendFailed();
  CHECK(j.state() == State::Draft, "send: a failed send is a draft again");
  CHECK(j.beginSend(out, sizeof(out), 7, 8) && !strcmp(j.requestId, first), "send: the same draft resent keeps its id (idempotent)");
  j.sendFailed();
  j.select(0, 0, 1);
  CHECK(j.beginSend(out, sizeof(out), 7, 8) && strcmp(j.requestId, first) != 0, "send: a changed draft gets a new id");
  j.sendAccepted();
  CHECK(j.state() == State::Waiting && !strcmp(j.sentId, j.requestId), "send: accepted: Waiting for the Mac");
  CHECK(!j.select(0, 0, 2), "send: no changes while waiting");
  std::string body = std::string("{\"experiment\":\"E-021\",\"run\":\"PR-021-01\",\"judgeOn\":\"seam\",\"tabs\":[\"21A\",\"21B\",\"21C\"],"
                                 "\"criteria\":[{\"key\":\"print\",\"label\":\"Print\",\"choices\":[\"clean\",\"flawed\",\"failed\"]},"
                                 "{\"key\":\"apart\",\"label\":\"Comes apart\",\"choices\":[\"yes\",\"hard\",\"no\"]}],"
                                 "\"judged\":{\"at\":\"2026-10-26T18:32:05Z\",\"by\":\"display\"},\"pending\":{\"id\":\"") + j.requestId + "\",\"status\":\"";
  const std::string pending = body + "pending\",\"message\":null}}";
  CHECK(j.load(pending.c_str(), pending.size()) && j.state() == State::Waiting,
        "send: still pending: Waiting");
  CHECK(j.selected(0, 0) == 1, "send: the same sheet again keeps the draft");
  const std::string applied = body + "applied\",\"message\":null}}";
  CHECK(j.load(applied.c_str(), applied.size()) && j.state() == State::Done, "send: applied: Done");
  bool on = false;
  CHECK(!strcmp(j.action(on), "Close") && on, "send: Done closes");
  // The Mac's refusal, in its words, cut whole-character to the buffer.
  std::string words;
  for (int i = 0; i < 80; ++i) words += "\xC3\xA9";  // 160 bytes of é
  const std::string refused = body + "refused\",\"message\":\"" + words + "\"}}";
  CHECK(j.load(refused.c_str(), refused.size()) && j.state() == State::Refused, "send: refused");
  CHECK(validUtf8(j.s.pendingMessage) && strlen(j.s.pendingMessage) == 122, "send: the Mac's words cut on a character boundary");
  CHECK(!strcmp(j.action(on), "Close") && on, "send: a refusal other than \"already has a verdict\" closes (no Change it)");
  // A different sheet (criteria edited) clears the draft.
  load(j, kThree);
  j.select(0, 0, 2);
  const char* edited = "{\"experiment\":\"E-021\",\"run\":\"PR-021-01\",\"judgeOn\":\"seam\",\"tabs\":[\"21A\",\"21B\",\"21C\"],"
                       "\"criteria\":[{\"key\":\"print\",\"label\":\"Print\",\"choices\":[\"clean\",\"rough\",\"failed\"]},"
                       "{\"key\":\"apart\",\"label\":\"Comes apart\",\"choices\":[\"yes\",\"hard\",\"no\"]}],\"judged\":null,\"pending\":null}";
  CHECK(j.load(edited, strlen(edited)) && j.selected(0, 0) == kUnset, "send: a changed sheet clears the draft");
}

// Fix round 1: a resent request id answers 202 with that request's current status; the refusal that offers Change
// it is the phone's "already has a verdict" one only; the phone's slow-wait words; real-record lengths.
static void fixRound1() {
  CHECK(verdictAccepted(202, "rq-0000000100000002", "rq-0000000100000002") &&
            verdictAccepted(200, "rq-0000000100000002", "rq-0000000100000002"),
        "resend_after_applied: any 2xx naming the sent id is accepted, whatever its status");
  CHECK(!verdictAccepted(202, "rq-0000000100000002", "rq-0000000100000003") && !verdictAccepted(400, "rq-0000000100000002", "rq-0000000100000002") &&
            !verdictAccepted(202, "", "") && !verdictAccepted(202, "rq-0000000100000002", nullptr),
        "resend_after_applied: another id, an error, or no id is not");
  LabJudge j;
  load(j, kThree);
  gradeAll(j, 0);
  char out[kMaxPayload], id[20];
  CHECK(j.beginSend(out, sizeof(out), 1, 2), "resend_after_applied: first send");
  strcpy(id, j.requestId);
  j.sendFailed();  // its answer was lost, but Local AI queued it and the Mac applied it
  CHECK(j.beginSend(out, sizeof(out), 9, 9) && !strcmp(j.requestId, id), "resend_after_applied: the same id again");
  CHECK(verdictAccepted(202, j.requestId, id), "resend_after_applied: 202 {id, status: applied} is accepted");
  j.sendAccepted();
  std::string applied = std::string("{\"experiment\":\"E-021\",\"run\":\"PR-021-01\",\"judgeOn\":\"seam\",\"tabs\":[\"21A\",\"21B\",\"21C\"],"
                                    "\"criteria\":[{\"key\":\"print\",\"label\":\"Print\",\"choices\":[\"clean\",\"flawed\",\"failed\"]},"
                                    "{\"key\":\"apart\",\"label\":\"Comes apart\",\"choices\":[\"yes\",\"hard\",\"no\"]}],"
                                    "\"judged\":{\"at\":\"2026-10-26T18:32:05Z\",\"by\":\"display\"},\"pending\":{\"id\":\"") + id + "\",\"status\":\"";
  const std::string done = applied + "applied\",\"message\":null}}";
  CHECK(j.load(done.c_str(), done.size()) && j.state() == State::Done, "resend_after_applied: reaches Done");
  // Change it only for the Mac's "already has a verdict" refusal, as the phone's Replace.
  const std::string already = applied + "refused\",\"message\":\"E-021 already has a verdict; send replace to change it\"}}";
  bool on = false;
  CHECK(j.load(already.c_str(), already.size()) && j.state() == State::Refused && j.alreadyJudged() && !strcmp(j.action(on), "Change it") && on,
        "refusal_change_it: already has a verdict: Change it");
  const std::string other = applied + "refused\",\"message\":\"PR-021-01 is not a run of E-021\"}}";
  CHECK(j.load(other.c_str(), other.size()) && j.state() == State::Refused && !j.alreadyJudged() && !strcmp(j.action(on), "Close") && on,
        "refusal_change_it: any other refusal: the Mac's words and Close");
  CHECK(!strcmp(kPickup, "The Mac hasn't picked this up. It runs when the Mac is awake.") && kSlowMs == 120000UL,
        "slow_wait: the phone's words after 2 minutes");
  // Real records: labels up to 24 bytes, keys and choices up to 6, strips up to 7.
  CHECK(load(j, "{\"experiment\":\"E-012\",\"run\":\"PR-012-01\",\"tabs\":[\"12A-xyz\",\"12B-xyz\"],\"criteria\":["
                "{\"key\":\"print\",\"label\":\"Seam visible from 1 m ok\",\"choices\":[\"clean\",\"flawed\",\"failed\"]}],"
                "\"judged\":null,\"pending\":null}") &&
            !j.s.phoneOnly && strlen(j.s.criteria[0].label) == 24 && !strcmp(j.s.criteria[0].label, "Seam visible from 1 m ok") &&
            !strcmp(j.s.tabs[0], "12A-xyz"),
        "real_record_lengths: a 24-byte label and 7-byte strips fit whole");
}

// Fix round 2 (device): the sheet never stays stuck over the Local AI tab. Leaving closes it; an empty sheet
// ("Nothing to judge right now.") closes itself; a draft survives closing and reopening for 10 minutes.
static void fixRound2() {
  SheetGate g = {};
  CHECK(!g.frame(1000, false, 0), "sheet_closes_on_leave: closed until shown");
  g.show(1000);
  CHECK(g.open && g.frame(1250, false, 7) && g.frame(1500, false, 7), "sheet_closes_on_leave: drawn every frame while shown");
  g.leave();
  CHECK(!g.open && !g.frame(1750, false, 7), "sheet_closes_on_leave: any navigation away closes it");
  g.show(2000);
  CHECK(g.frame(2250, false, 7) && !g.frame(2250 + kAwayMs + 1, false, 7) && !g.open,
        "sheet_closes_on_leave: no frame for a while (another screen, the display off): closed when it comes back");
  g.show(10000);
  CHECK(g.frame(10000, true, 7) && g.frame(10000 + kEmptyCloseMs - 1, true, 7), "empty_sheet_closes_itself: says so for a moment");
  CHECK(!g.frame(10000 + kEmptyCloseMs, true, 7) && !g.open, "empty_sheet_closes_itself: then closes");
  g.show(20000);
  CHECK(g.frame(20000, true, 7) && !g.frame(20250, true, 8) && !g.open, "empty_sheet_closes_itself: or on the next feed update");
  g.show(30000);
  CHECK(g.frame(30000, true, 7) && g.frame(30250, false, 7) && g.frame(30000 + kEmptyCloseMs + 10, false, 8) && g.open,
        "empty_sheet_closes_itself: a sheet that arrived stays open");
  g.show(0xFFFFFF00UL);
  CHECK(g.frame((uint32_t)(0xFFFFFF00UL + 300UL), false, 7), "sheet_closes_on_leave: millis() wrapping is fine");
  // The draft: closed mid-judgement and reopened for the same print within 10 minutes, the choices are still there.
  CHECK(draftKept(true, 5000, 1000) && draftKept(true, 1000 + kIdleMs - 1, 1000), "draft_kept: same print, within 10 min");
  CHECK(!draftKept(true, 1000 + kIdleMs, 1000) && !draftKept(false, 2000, 1000), "draft_kept: not after 10 min, nor for another print");
  LabJudge j;
  load(j, kThree);
  j.select(0, 0, 2);
  j.select(1, 1, kNotJudged);
  g.show(0);
  g.leave();  // the LabJudge is untouched by closing
  CHECK(j.selected(0, 0) == 2 && j.selected(1, 1) == kNotJudged && j.state() == State::Draft, "draft_kept: closing keeps the choices");
}

static void boundedParsing() {
  LabJudge j;
  CHECK(!load(j, "") && !j.s.ok, "parse: empty");
  CHECK(!load(j, "{\"run\":\"PR-021-01\",\"tabs\":[\"21A\"") && !j.s.ok, "parse: cut short");
  CHECK(!load(j, "[1,2,3]"), "parse: not an object");
  CHECK(!load(j, "{\"run\":\"PR-021-01\",\"x\":[[[[[[[[[[[[1]]]]]]]]]]]]}"), "parse: nesting is bounded");
  CHECK(!load(j, "{\"run\":\"pr 21\",\"tabs\":[\"A\"],\"criteria\":[{\"key\":\"k\",\"label\":\"L\",\"choices\":[\"a\"]}]}"), "parse: a run id that isn't one");
  CHECK(!load(j, "{\"run\":\"PR-021-01\",\"tabs\":[\"A\"],\"criteria\":[]}"), "parse: nothing to judge");
  CHECK(!load(j, "{\"run\":\"PR-021-01\",\"tabs\":[\"A\x01\"],\"criteria\":[{\"key\":\"k\",\"label\":\"L\",\"choices\":[\"a\"]}]}"),
        "parse: a raw control character");
  CHECK(load(j, "{\"unknown\":{\"a\":[1,-2.5e3,true,false,null,\"\\u00e9\"]},\"experiment\":\"E-1\",\"run\":\"PR-001-01\","
                "\"tabs\":[\"\\u00c9\"],\"criteria\":[{\"key\":\"k\",\"label\":\"L\\n2\",\"choices\":[\"a\",\"\\ud83d\\ude00\"]}],\"judged\":null,\"pending\":null}"),
        "parse: unknown keys skipped, escapes decoded");
  CHECK(!strcmp(j.s.tabs[0], "\xC3\x89") && !strcmp(j.s.criteria[0].choices[1], "\xF0\x9F\x98\x80") && !strcmp(j.s.criteria[0].label, "L 2"),
        "parse: \\u escapes and surrogate pairs to UTF-8, a newline shown as a space");
  std::string big(kMaxJudgeJson + 1, ' ');
  CHECK(!j.load(big.c_str(), big.size()), "parse: too large");
  // An over-long judgeOn is cut whole-character; that text is shown, never sent back.
  std::string longText = "{\"experiment\":\"E-021\",\"run\":\"PR-021-01\",\"judgeOn\":\"";
  for (int i = 0; i < 60; ++i) longText += "\xE2\x82\xAC";  // 180 bytes of €
  longText += "\",\"tabs\":[\"A\"],\"criteria\":[{\"key\":\"k\",\"label\":\"L\",\"choices\":[\"a\"]}],\"judged\":null,\"pending\":null}";
  CHECK(load(j, longText.c_str()) && !j.s.phoneOnly && validUtf8(j.s.judgeOn) && strlen(j.s.judgeOn) == 111, "parse: judgeOn cut whole-character");
  CHECK(validRun("PR-021-01") && validRun("E-1") && !validRun("") && !validRun("pr-021") && !validRun("PR-021-01&x=1") &&
            !validRun("PR-0000000000000000"),
        "run ids: letters, digits and '-' only, short");
}

// Layout: 44 px targets, nothing overlapping, inside the screen; chips wrap to at most two lines; a page with more
// than fits scrolls inside the sheet.
static int measure(const char* text, void*) {
  int n = 0;
  for (const unsigned char* p = reinterpret_cast<const unsigned char*>(text); *p; ++p)
    if ((*p & 0xC0) != 0x80) ++n;
  return n * 9;  // about FONT_BODY's width
}

static bool inside(const Box& b, int w, int h) { return b.x >= 0 && b.y >= 0 && b.x + b.w <= w && b.y + b.h <= h; }
static bool overlap(const Box& a, const Box& b) { return a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h; }

static void checkTargets(const SheetLayout& L, int w, int h, const char* what) {
  Box t[64];
  int n = 0;
  t[n++] = L.later;
  t[n++] = L.next;
  if (L.hasBack) t[n++] = L.back;
  if (L.scrolls) { t[n++] = L.up; t[n++] = L.down; }
  for (uint8_t r = 0; r < L.rowCount; ++r) {
    if (!L.rows[r].shown) continue;
    for (uint8_t c = 0; c < L.rows[r].chipCount; ++c) t[n++] = L.rows[r].chips[c];
    char m[96];
    std::snprintf(m, sizeof(m), "%s: row %u inside the sheet's body", what, (unsigned)r);
    CHECK(L.rows[r].label.y >= L.body.y && L.rows[r].label.y + L.rows[r].h <= L.body.y + L.body.h, m);
    std::snprintf(m, sizeof(m), "%s: row %u chips on at most two lines", what, (unsigned)r);
    CHECK(L.rows[r].lines <= (L.reasons && r == 0 ? kReasonCount : 2), m);
  }
  for (int i = 0; i < n; ++i) {
    char m[96];
    std::snprintf(m, sizeof(m), "%s: target %d is 44 px", what, i);
    CHECK(t[i].w >= 44 && t[i].h >= 44, m);
    std::snprintf(m, sizeof(m), "%s: target %d on screen", what, i);
    CHECK(inside(t[i], w, h), m);
    for (int k = i + 1; k < n; ++k) {
      std::snprintf(m, sizeof(m), "%s: targets %d and %d apart", what, i, k);
      CHECK(!overlap(t[i], t[k]), m);
    }
    const Hit hit = hitTest(L, t[i].x + t[i].w / 2, t[i].y + t[i].h / 2);
    std::snprintf(m, sizeof(m), "%s: target %d hit where drawn", what, i);
    CHECK(hit.kind != HitKind::None && hit.box.x == t[i].x && hit.box.y == t[i].y && hit.box.w == t[i].w, m);
  }
  CHECK(hitTest(L, L.body.x + 2, L.body.y + 1).kind == HitKind::None || L.reasons, "nothing tappable in the gutters");
}

static void judgePageFits() {
  std::string json = "{\"experiment\":\"E-021\",\"run\":\"PR-021-01\",\"judgeOn\":\"seam\",\"tabs\":[\"21A\",\"21B\",\"21C\"],\"criteria\":[";
  const char* labels[6] = {"Print", "Comes apart", "Seam visible from a metre", "Warp", "Stringing", "Overall"};
  for (int c = 0; c < 6; ++c) {
    json += std::string(c ? "," : "") + "{\"key\":\"k" + char('0' + c) + "\",\"label\":\"" + labels[c] + "\",\"choices\":[";
    if (c == 2) json += "\"not at all\",\"barely visible\",\"clearly visible\",\"obvious\"";
    else json += "\"clean\",\"flawed\",\"failed\",\"worse\"";
    json += "]}";
  }
  json += "],\"judged\":null,\"pending\":null}";
  LabJudge j;
  CHECK(load(j, json.c_str()) && j.s.criterionCount == 6, "judge_page_fits_480x320_44px: 6 criteria x 4 choices");
  const int sizes[2][2] = {{480, 320}, {320, 480}};
  for (int o = 0; o < 2; ++o) {
    const int w = sizes[o][0], h = sizes[o][1];
    SheetLayout L;
    bool wrapped = false;
    for (uint8_t page = 0; page < j.pages(); ++page) {
      sheetLayout(w, h, j, page, 0, measure, nullptr, L);
      bool seen[kMaxCriteria] = {false, false, false, false, false, false};
      for (uint8_t first = 0; first <= L.maxFirst; ++first) {
        sheetLayout(w, h, j, page, first, measure, nullptr, L);
        char what[64];
        std::snprintf(what, sizeof(what), "judge_page_fits %dx%d page %u first %u", w, h, (unsigned)page, (unsigned)first);
        checkTargets(L, w, h, what);
        for (uint8_t r = 0; r < L.rowCount; ++r) {
          if (L.rows[r].shown) seen[r] = true;
          if (L.rows[r].lines == 2) wrapped = true;
        }
      }
      if (!j.sendPage(page)) {
        bool all = true;
        for (uint8_t r = 0; r < 6; ++r) all = all && seen[r];
        CHECK(all, "judge_page_fits_480x320_44px: every criterion can be scrolled to");
        CHECK(L.rowCount == 6 && L.rows[0].chipCount == 5, "judge_page_fits_480x320_44px: four choices and \"–\"");
      } else {
        CHECK(L.reasons && L.rows[0].chipCount == kReasonCount && !L.scrolls, "judge_page_fits_480x320_44px: Send page: three reasons, no scrolling");
        CHECK(L.status.y >= L.rows[0].label.y + L.rows[0].h && L.status.h >= 54 && inside(L.status, w, h), "judge_page_fits_480x320_44px: room for the state and the photos line");
      }
    }
    sheetLayout(w, h, j, 0, 0, measure, nullptr, L);
    CHECK(L.scrolls && L.maxFirst > 0, "judge_page_fits_480x320_44px: more than fits scrolls inside the sheet");
    CHECK(wrapped, "judge_page_fits_480x320_44px: long chips wrap to a second line");
    CHECK(L.hasBack && hitTest(L, L.back.x + 4, L.back.y + 4).kind == HitKind::Back, "judge_page_fits_480x320_44px: page 1 Back closes");
    sheetLayout(w, h, j, 0, 200, measure, nullptr, L);
    CHECK(L.first == L.maxFirst, "judge_page_fits_480x320_44px: scroll clamped");
    // Single-page states (phone only, nothing to judge): Later and Close only.
    LabJudge p;
    load(p, "{\"experiment\":\"E-022\",\"run\":\"PR-022-01\",\"phoneOnly\":true,\"reason\":\"Judge it on your phone\"}");
    sheetLayout(w, h, p, 0, 0, measure, nullptr, L);
    checkTargets(L, w, h, "phone only");
    CHECK(!L.hasBack && !L.reasons && L.rowCount == 0, "phone only: Close and Later only");
  }
}

// Fix round 3: a newer verdict request (the phone's) that replaced the display's settles Waiting with its outcome; an
// older request the last read showed never does (the display's own is the newest once Local AI accepted it).
static void fixRound3() {
  const std::string head = "{\"experiment\":\"E-021\",\"run\":\"PR-021-01\",\"judgeOn\":\"seam\",\"tabs\":[\"21A\",\"21B\",\"21C\"],"
                           "\"criteria\":[{\"key\":\"print\",\"label\":\"Print\",\"choices\":[\"clean\",\"flawed\",\"failed\"]},"
                           "{\"key\":\"apart\",\"label\":\"Comes apart\",\"choices\":[\"yes\",\"hard\",\"no\"]}],"
                           "\"judged\":null,\"pending\":{\"id\":\"";
  LabJudge j;
  j.clear();
  const std::string earlier = head + "rq-00000000000000aa\",\"status\":\"refused\",\"message\":\"E-021 already has a verdict; send replace to change it\"}}";
  CHECK(j.load(earlier.c_str(), earlier.size()) && j.state() == State::Refused, "replaced_by_newer: an earlier refusal shows");
  j.changeIt();
  gradeAll(j, 0);
  char out[kMaxPayload];
  CHECK(j.beginSend(out, sizeof(out), 1, 2), "replaced_by_newer: Change it sends");
  j.sendAccepted();
  CHECK(j.state() == State::Waiting, "replaced_by_newer: the earlier refusal the last read showed doesn't settle the new send");
  const std::string newer = head + "rq-00000000000000bb\",\"status\":\"";
  const std::string pend = newer + "pending\",\"message\":null}}";
  CHECK(j.load(pend.c_str(), pend.size()) && j.state() == State::Waiting, "replaced_by_newer: a newer request still pending: Waiting");
  const std::string applied = newer + "applied\",\"message\":null}}";
  CHECK(j.load(applied.c_str(), applied.size()) && j.state() == State::Done, "replaced_by_newer: the newer request applied: Done");
  const std::string refused = newer + "refused\",\"message\":\"PR-021-01 is not a run of E-021\"}}";
  CHECK(j.load(refused.c_str(), refused.size()) && j.state() == State::Refused && !strcmp(j.s.pendingMessage, "PR-021-01 is not a run of E-021"),
        "replaced_by_newer: the newer request refused: the Mac's words");
}

int main() {
  pagesAreTabsPlusSend();
  dashIsNullInPayload();
  payloadFits4k();
  inconclusiveReasonSent();
  phoneOnlyShowsReason();
  judgedOpensOnChangeIt();
  sendStates();
  boundedParsing();
  fixRound1();
  fixRound2();
  fixRound3();
  judgePageFits();
  if (failures) {
    std::printf("lab-judge smoke: %d of %d checks FAILED\n", failures, checks);
    return 1;
  }
  std::printf("lab-judge smoke: PASS (%d checks)\n", checks);
  return 0;
}
