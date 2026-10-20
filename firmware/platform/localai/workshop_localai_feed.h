#pragma once

// Workshop OS 12.3.10: Local AI cards for the calm idle screen (rules: workshop_localai_feed_core.hpp).

#include "workshop_localai_feed_core.hpp"

#include <cstddef>
#include <cstdint>

struct WorkshopLocalAiFeedSnapshot {
    workshop::localai::Card cards[workshop::localai::kMaxCards]{};
    std::uint8_t count{0};
    bool configured{false};
    bool busy{false};
    std::uint32_t lastSuccessAtMs{0};
    std::uint32_t lastAttemptAtMs{0};
    std::uint8_t failures{0};
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
    bool imageBusy{false};
    bool imageReady{false};   // a JPEG is in the buffer (workshopLocalAiFeedImage)
    std::uint32_t imageSeq{0};  // counts finished downloads
    char imageStatus[96]{};
};

void workshopLocalAiFeedBegin();
void workshopLocalAiFeedLoop();
// address: Local AI's IPv4 address; tlsName: the name on its certificate; key: the wsd_ display key; caPem: Local
// AI's CA certificate (PEM). False when any is not acceptable; nothing is saved then.
bool workshopLocalAiFeedConfigure(const char* address, const char* tlsName, const char* key, const char* caPem);
void workshopLocalAiFeedClear();
WorkshopLocalAiFeedSnapshot workshopLocalAiFeedSnapshot();
// Asks one of the fixed questions (needs, running, health); false when not set up, busy, or not a question.
bool workshopLocalAiFeedAsk(const char* question);
// Downloads the feed's latest image (a JPEG); false when there is none or a download is running.
bool workshopLocalAiFeedFetchImage();
WorkshopLocalAiExtras workshopLocalAiFeedExtras();
// The downloaded JPEG, valid until the next workshopLocalAiFeedFetchImage(); false while one is running.
bool workshopLocalAiFeedImage(const std::uint8_t** data, std::size_t* len);
// Free entries in the default NVS partition (32 bytes each), for the portal's status.
std::size_t workshopLocalAiFeedNvsFreeEntries();
