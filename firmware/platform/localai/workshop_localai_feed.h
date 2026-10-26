#pragma once

// Workshop OS 12.3.10: Local AI cards for the calm idle screen (rules: workshop_localai_feed_core.hpp).

#include "workshop_localai_feed_core.hpp"

#include <cstddef>
#include <cstdint>

namespace workshop {
namespace lab {
struct Sheet;  // the Judge it sheet (workshop_lab_judge.hpp)
}
}  // namespace workshop

struct WorkshopLocalAiFeedSnapshot {
    workshop::localai::Card cards[workshop::localai::kMaxCards]{};
    std::uint8_t count{0};
    // 26 Oct 2026: Pi Hub's one "Needs you" list as Local AI passes it on (feed `needs`); needsFromPi is false when
    // the feed came without it (Pi Hub not answering), and Home falls back to the cards.
    workshop::localai::Need needs[workshop::localai::kMaxNeeds]{};
    std::uint8_t needCount{0};
    bool needsFromPi{false};
    bool configured{false};
    bool busy{false};
    std::uint32_t lastSuccessAtMs{0};
    std::uint32_t lastAttemptAtMs{0};
    std::uint8_t failures{0};
    char status[96]{};
};

// 26 Oct 2026: the snapshot's small fields, for the UI's many "is it set up / fresh / how many" questions; the whole
// snapshot (about 2.6 KB with the needs) is copied only where the cards or needs themselves are read.
struct WorkshopLocalAiFeedStatus {
    bool configured{false};
    std::uint32_t lastSuccessAtMs{0};
    std::uint8_t count{0};
    std::uint8_t needCount{0};
    bool needsFromPi{false};
    char status[96]{};
};

// 12.4.2: the Local AI tab's ask buttons and its latest image. One request at a time runs on the feed's task.
struct WorkshopLocalAiExtras {
    bool askBusy{false};
    bool askOk{false};
    std::uint32_t askSeq{0};  // counts finished answers
    char askQuestion[12]{};
    char askAnswer[workshop::localai::kAnswerLen]{};
    bool hasImage{false};     // the feed has a latest-image card
    char imageTitle[workshop::localai::kTitleLen]{};
    char imageText[workshop::localai::kTextLen]{};
    std::uint32_t imageAt{0};  // when Local AI made it (epoch seconds), 0 when it didn't say
    bool imageBusy{false};
    bool imageReady{false};   // a JPEG is in the buffer (workshopLocalAiFeedImage)
    std::uint32_t imageSeq{0};  // counts finished downloads
    char imageStatus[96]{};
    // 12.6 (feed v2)
    std::uint8_t imageCount{0};  // pictures in the gallery (up to 6, newest first)
    std::uint8_t imageIndex{0};  // the one imageText/imageAt describe and the download is for
    bool live{false};            // the long poll is working (news in about 2 s)
    std::uint8_t approvalCount{0};  // listed (up to 4)
    std::uint8_t approvalTotal{0};  // waiting in all
    bool approvalsBusy{false};
    std::uint32_t approvalSeq{0};   // counts list reads
    char approvalStatus[96]{};
    // 12.7: pairing from the touchscreen
    bool pairBusy{false};
    bool pairOk{false};
    std::uint32_t pairSeq{0};
    char pairStatus[96]{};
    // 26 Oct 2026: the Judge it sheet (GET /api/display/lab/judge, POST /api/display/lab/verdict), like approvals: a
    // flag while one runs, a counter of finished ones, the HTTP status and Local AI's words when it said no.
    bool judgeBusy{false};
    bool judgeOk{false};
    std::uint16_t judgeCode{0};
    std::uint32_t judgeSeq{0};
    bool verdictBusy{false};
    bool verdictOk{false};
    std::uint16_t verdictCode{0};
    std::uint32_t verdictSeq{0};
    char judgeStatus[96]{};  // the last judge or verdict request's error, whole characters
};

void workshopLocalAiFeedBegin();
void workshopLocalAiFeedLoop();
// address: Local AI's IPv4 address; tlsName: the name on its certificate; key: the wsd_ display key; caPem: Local
// AI's CA certificate (PEM). False when any is not acceptable; nothing is saved then.
bool workshopLocalAiFeedConfigure(const char* address, const char* tlsName, const char* key, const char* caPem);
void workshopLocalAiFeedClear();
WorkshopLocalAiFeedSnapshot workshopLocalAiFeedSnapshot();
WorkshopLocalAiFeedStatus workshopLocalAiFeedStatus();
// Card `i` of the last feed into *out; false when there is no such card.
bool workshopLocalAiFeedCard(std::uint8_t i, workshop::localai::Card* out);
// Asks one of the fixed questions (needs, running, health; 12.6: today, next, weather); false when not set up, busy,
// or not a question.
bool workshopLocalAiFeedAsk(const char* question);
// Makes sure the feed's latest image is downloaded (a JPEG; 12.4.3: kept until the feed names another, which is
// fetched in the background). False when there is none or a download is already running.
bool workshopLocalAiFeedFetchImage();
WorkshopLocalAiExtras workshopLocalAiFeedExtras();
// 12.6: picture `index` of the gallery (0 = newest): selects it and downloads it unless it's already here.
bool workshopLocalAiFeedShowImage(std::uint8_t index);
// 12.6: the oldest message Local AI left that the UI hasn't taken; false when there is none.
bool workshopLocalAiFeedTakeMessage(workshop::localai::Message* out);
// 12.6: approvals: read the list again; copy it out (returns how many); decide one Local AI marked decidable.
bool workshopLocalAiFeedRefreshApprovals();
std::uint8_t workshopLocalAiFeedApprovals(workshop::localai::Approval* out, std::uint8_t max);
bool workshopLocalAiFeedDecide(const char* id, bool approve);
// 26 Oct 2026: Judge it. Asks Local AI for the sheet of the judge card's `run` (false when not set up, busy, or not a
// run id); copies the last sheet read into *out (false while a read runs or none came); sends a verdict body made by
// workshop::lab::LabJudge::beginSend under its `requestId` (at most 4 KB; false when busy). Accepted means Local AI
// answered 2xx naming that id, whatever the request's status (a resent id answers with its current one).
bool workshopLocalAiFeedJudgeLoad(const char* run);
bool workshopLocalAiFeedJudgeSheet(workshop::lab::Sheet* out);
bool workshopLocalAiFeedJudgeSend(const char* body, const char* requestId);
// Clear plate through Local AI (which clears the plate and printer errors in Bambuddy); false when Local AI isn't set up.
bool workshopLocalAiFeedClearPrinter();
// 12.7: pairs with Local AI at `address` with the 6-digit code it shows (Services › Workshop display › Pair display);
// on success the settings are saved as by the portal. False when the address or code is not acceptable, or busy.
bool workshopLocalAiFeedPair(const char* address, const char* code);
// The saved Local AI address ("" when not set up).
void workshopLocalAiFeedAddress(char* out, std::size_t len);
// The downloaded JPEG, valid until the next workshopLocalAiFeedFetchImage(); false while one is running.
bool workshopLocalAiFeedImage(const std::uint8_t** data, std::size_t* len);
// Free entries in the default NVS partition (32 bytes each), for the portal's status.
std::size_t workshopLocalAiFeedNvsFreeEntries();
