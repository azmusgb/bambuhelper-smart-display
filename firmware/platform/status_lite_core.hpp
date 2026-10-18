#pragma once

// Workshop OS read-only status token: pure, host-testable core.
//
// One route, GET /api/status/lite, answers with a minimal printer summary to a
// client that presents a device-issued bearer token. This header holds every
// decision that does not need ESP-IDF: token text format, strict Authorization
// parsing, constant-time digest comparison, the per-client read limiter, the
// on-device approval flow, and the JSON serializer with its field allowlist.
// tests/workshop_os12_status_lite_smoke.cpp proves it on a host compiler.
//
// The token grants nothing else: securityAuthorize() never reads it, and the
// lite route never reads the portal session.

#include "workshop_state.hpp"

#include <cstddef>
#include <cstdint>
#include <cstring>

namespace workshop {
namespace statuslite {

using workshop::platform::Connectivity;
using workshop::platform::Freshness;
using workshop::platform::PrinterActivity;

// ---------------------------------------------------------------------------
// Token text
// ---------------------------------------------------------------------------

constexpr char kTokenAlphabet[] = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789";
constexpr char kTokenPrefix[] = "wsl_";
constexpr std::size_t kTokenPrefixLength = sizeof(kTokenPrefix) - 1;
constexpr std::size_t kTokenRandomBytes = 16;  // 128 bits from esp_random()
constexpr std::size_t kTokenBodyLength = 26;   // ceil(128 / 5)
constexpr std::size_t kTokenTextLength = kTokenPrefixLength + kTokenBodyLength;
constexpr std::size_t kDigestBytes = 32;       // SHA-256

inline bool tokenAlphabetChar(char c) {
    for (std::size_t i = 0; i + 1 < sizeof(kTokenAlphabet); ++i) {
        if (kTokenAlphabet[i] == c) return true;
    }
    return false;
}

// Encodes 16 random bytes as "wsl_" + 26 base32 characters (5 bits each).
inline void encodeToken(const std::uint8_t random[kTokenRandomBytes], char out[kTokenTextLength + 1]) {
    std::memcpy(out, kTokenPrefix, kTokenPrefixLength);
    std::uint32_t buffer = 0;
    unsigned bits = 0;
    std::size_t byteIndex = 0;
    for (std::size_t i = 0; i < kTokenBodyLength; ++i) {
        if (bits < 5) {
            const std::uint8_t next = byteIndex < kTokenRandomBytes ? random[byteIndex] : 0;
            ++byteIndex;
            buffer = (buffer << 8) | next;
            bits += 8;
        }
        const unsigned index = (buffer >> (bits - 5)) & 0x1FU;
        bits -= 5;
        out[kTokenPrefixLength + i] = kTokenAlphabet[index];
    }
    out[kTokenTextLength] = '\0';
}

inline bool wellFormedToken(const char* token) {
    if (token == nullptr || std::strlen(token) != kTokenTextLength) return false;
    if (std::strncmp(token, kTokenPrefix, kTokenPrefixLength) != 0) return false;
    for (std::size_t i = kTokenPrefixLength; i < kTokenTextLength; ++i) {
        if (!tokenAlphabetChar(token[i])) return false;
    }
    return true;
}

// Strict "Authorization: Bearer <token>" parsing. The scheme is
// case-insensitive; exactly the token follows, optionally surrounded by spaces.
// Anything else (Basic, query strings, cookies, extra words) is rejected.
inline bool parseBearer(const char* header, char out[kTokenTextLength + 1]) {
    if (header == nullptr) return false;
    while (*header == ' ' || *header == '\t') ++header;
    static const char kScheme[] = "bearer";
    for (std::size_t i = 0; i < sizeof(kScheme) - 1; ++i) {
        char c = header[i];
        if (c >= 'A' && c <= 'Z') c = static_cast<char>(c - 'A' + 'a');
        if (c != kScheme[i]) return false;
    }
    header += sizeof(kScheme) - 1;
    if (*header != ' ' && *header != '\t') return false;
    while (*header == ' ' || *header == '\t') ++header;
    std::size_t len = 0;
    while (header[len] != '\0' && header[len] != ' ' && header[len] != '\t') {
        if (len >= kTokenTextLength) return false;
        ++len;
    }
    for (std::size_t i = len; header[i] != '\0'; ++i) {
        if (header[i] != ' ' && header[i] != '\t') return false;
    }
    if (len != kTokenTextLength) return false;
    std::memcpy(out, header, len);
    out[len] = '\0';
    return wellFormedToken(out);
}

inline bool digestEqual(const std::uint8_t a[kDigestBytes], const std::uint8_t b[kDigestBytes]) {
    std::uint8_t diff = 0;
    for (std::size_t i = 0; i < kDigestBytes; ++i) diff = static_cast<std::uint8_t>(diff | (a[i] ^ b[i]));
    return diff == 0;
}

inline bool digestEmpty(const std::uint8_t a[kDigestBytes]) {
    std::uint8_t any = 0;
    for (std::size_t i = 0; i < kDigestBytes; ++i) any = static_cast<std::uint8_t>(any | a[i]);
    return any == 0;
}

// ---------------------------------------------------------------------------
// Per-client read limiter: one answer every 2 s; after two bad tokens an
// exponential block (1 s, 2 s, ... capped at 60 s), like portal login.
// ---------------------------------------------------------------------------

inline bool deadlinePending(std::uint32_t now, std::uint32_t deadline) {
    return static_cast<std::int32_t>(deadline - now) > 0;
}

struct ReadDecision {
    bool allowed;
    std::uint32_t retryAfterSeconds;
};

class ReadLimiter {
public:
    static constexpr std::size_t kBuckets = 8;
    static constexpr std::uint32_t kMinIntervalMs = 2000;
    static constexpr std::uint8_t kFreeFailures = 2;
    static constexpr std::uint32_t kMaxBackoffMs = 60000;

    ReadDecision admit(std::uint32_t client, std::uint32_t now) {
        Bucket& b = bucketFor(client, now);
        if (b.blocked) {
            if (deadlinePending(now, b.blockedUntilMs)) return {false, secondsUntil(now, b.blockedUntilMs)};
            b.blocked = false;
        }
        if (b.answered && deadlinePending(now, b.lastAnswerMs + kMinIntervalMs)) {
            return {false, secondsUntil(now, b.lastAnswerMs + kMinIntervalMs)};
        }
        b.answered = true;
        b.lastAnswerMs = now;
        return {true, 0};
    }

    void noteFailure(std::uint32_t client, std::uint32_t now) {
        Bucket& b = bucketFor(client, now);
        if (b.failures < 15) ++b.failures;
        if (b.failures <= kFreeFailures) return;
        unsigned shift = static_cast<unsigned>(b.failures - kFreeFailures - 1);
        if (shift > 6) shift = 6;
        std::uint32_t backoff = 1000UL << shift;
        if (backoff > kMaxBackoffMs) backoff = kMaxBackoffMs;
        b.blockedUntilMs = now + backoff;
        b.blocked = true;
    }

    void noteSuccess(std::uint32_t client, std::uint32_t now) {
        Bucket& b = bucketFor(client, now);
        (void)now;
        b.failures = 0;
        b.blocked = false;
    }

    void reset() {
        for (std::size_t i = 0; i < kBuckets; ++i) buckets_[i] = Bucket();
    }

private:
    struct Bucket {
        std::uint32_t client{0};
        std::uint32_t lastSeenMs{0};
        std::uint32_t lastAnswerMs{0};
        std::uint32_t blockedUntilMs{0};
        std::uint8_t failures{0};
        bool blocked{false};  // explicit flag: a zero deadline is not "not blocked" after millis() passes 2^31
        bool answered{false};
        bool active{false};
    };

    static std::uint32_t secondsUntil(std::uint32_t now, std::uint32_t deadline) {
        return (deadline - now + 999U) / 1000U;
    }

    Bucket& bucketFor(std::uint32_t client, std::uint32_t now) {
        Bucket* oldest = &buckets_[0];
        for (std::size_t i = 0; i < kBuckets; ++i) {
            Bucket& b = buckets_[i];
            if (b.active && b.client == client) {
                b.lastSeenMs = now;
                return b;
            }
        }
        for (std::size_t i = 0; i < kBuckets; ++i) {
            Bucket& b = buckets_[i];
            if (!b.active) {
                oldest = &b;
                break;
            }
            if (now - b.lastSeenMs > now - oldest->lastSeenMs) oldest = &b;
        }
        *oldest = Bucket();
        oldest->active = true;
        oldest->client = client;
        oldest->lastSeenMs = now;
        return *oldest;
    }

    Bucket buckets_[kBuckets];
};

// ---------------------------------------------------------------------------
// Creation flow: portal request -> touchscreen Allow within 60 s -> the token
// is shown once to the requesting portal tab within 60 s, then forgotten.
// ---------------------------------------------------------------------------

enum class ApprovalPhase : std::uint8_t { Idle = 0, Pending, Approved, Denied, Expired };

class ApprovalFlow {
public:
    static constexpr std::uint32_t kPromptMs = 60000;
    static constexpr std::uint32_t kClaimMs = 60000;

    void start(std::uint32_t requestId, std::uint32_t now) {
        wipe();
        phase_ = ApprovalPhase::Pending;
        requestId_ = requestId;
        deadlineMs_ = now + kPromptMs;
    }

    ApprovalPhase phase(std::uint32_t now) {
        if ((phase_ == ApprovalPhase::Pending || phase_ == ApprovalPhase::Approved) &&
            !deadlinePending(now, deadlineMs_)) {
            wipe();
            phase_ = ApprovalPhase::Expired;
        }
        return phase_;
    }

    bool promptVisible(std::uint32_t now) { return phase(now) == ApprovalPhase::Pending; }

    std::uint32_t secondsLeft(std::uint32_t now) {
        const ApprovalPhase p = phase(now);
        if (p != ApprovalPhase::Pending && p != ApprovalPhase::Approved) return 0;
        return (deadlineMs_ - now + 999U) / 1000U;
    }

    // Called by the touchscreen Allow handler after the new token's digest has
    // been persisted. Holds the plaintext only until claimed or expired.
    bool approve(const char* token, std::uint32_t now) {
        if (phase(now) != ApprovalPhase::Pending || !wellFormedToken(token)) return false;
        std::memcpy(token_, token, kTokenTextLength + 1);
        phase_ = ApprovalPhase::Approved;
        deadlineMs_ = now + kClaimMs;
        return true;
    }

    bool deny(std::uint32_t now) {
        if (phase(now) != ApprovalPhase::Pending) return false;
        wipe();
        phase_ = ApprovalPhase::Denied;
        return true;
    }

    // One-time hand-over to the portal tab that started the request.
    bool claim(std::uint32_t requestId, std::uint32_t now, char out[kTokenTextLength + 1]) {
        if (phase(now) != ApprovalPhase::Approved || requestId != requestId_ || requestId == 0) return false;
        std::memcpy(out, token_, kTokenTextLength + 1);
        wipe();
        phase_ = ApprovalPhase::Idle;
        return true;
    }

    void cancel() {
        wipe();
        phase_ = ApprovalPhase::Idle;
    }

    bool holdsPlaintext() const { return token_[0] != '\0'; }

private:
    void wipe() {
        volatile char* p = token_;
        for (std::size_t i = 0; i < sizeof(token_); ++i) p[i] = '\0';
        requestId_ = 0;
    }

    ApprovalPhase phase_{ApprovalPhase::Idle};
    std::uint32_t requestId_{0};
    std::uint32_t deadlineMs_{0};
    char token_[kTokenTextLength + 1]{};
};

inline const char* approvalPhaseName(ApprovalPhase p) {
    switch (p) {
        case ApprovalPhase::Pending: return "pending";
        case ApprovalPhase::Approved: return "approved";
        case ApprovalPhase::Denied: return "denied";
        case ApprovalPhase::Expired: return "expired";
        case ApprovalPhase::Idle:
        default: return "idle";
    }
}

// ---------------------------------------------------------------------------
// Serializer. Only these fields exist; the printer name, job/file name, IP,
// MAC, serial, RSSI, AMS and temperatures are not inputs, so they cannot leak.
// ---------------------------------------------------------------------------

struct PrinterSummary {
    std::uint8_t slot{0};
    Connectivity connection{Connectivity::Unknown};
    PrinterActivity activity{PrinterActivity::Unknown};
    Freshness freshness{Freshness::Unknown};
    bool ageKnown{false};
    std::uint32_t ageSeconds{0};
    std::uint8_t progressPercent{0};
    std::uint16_t remainingMinutes{0};
    std::uint32_t printErrorCode{0};
    const char* errorCode{nullptr};  // printer-formatted code, e.g. "0300_400C"
    const char* errorText{nullptr};  // board wording, or nullptr when none
    bool canceled{false};
};

inline const char* connectionName(Connectivity c) {
    switch (c) {
        case Connectivity::Online: return "online";
        case Connectivity::Connecting: return "connecting";
        case Connectivity::Offline: return "offline";
        case Connectivity::Degraded: return "degraded";
        case Connectivity::Unknown:
        default: return "unknown";
    }
}

inline const char* activityName(PrinterActivity a) {
    switch (a) {
        case PrinterActivity::Idle: return "idle";
        case PrinterActivity::Preparing: return "preparing";
        case PrinterActivity::Printing: return "printing";
        case PrinterActivity::Paused: return "paused";
        case PrinterActivity::Finished: return "finished";
        case PrinterActivity::Error: return "error";
        case PrinterActivity::Unknown:
        default: return "unknown";
    }
}

inline const char* freshnessName(Freshness f) {
    switch (f) {
        case Freshness::Fresh: return "fresh";
        case Freshness::Stale: return "stale";
        case Freshness::Conflicting:  // never guessed into fresh or stale
        case Freshness::Unknown:
        default: return "unknown";
    }
}

// Telemetry is only reported as current when the printer is online and the
// last report is inside the platform's freshness window.
inline bool current(const PrinterSummary& p) {
    return p.connection == Connectivity::Online && p.freshness == Freshness::Fresh;
}

inline bool reportsProgress(const PrinterSummary& p) {
    return current(p) && (p.activity == PrinterActivity::Preparing || p.activity == PrinterActivity::Printing ||
                          p.activity == PrinterActivity::Paused);
}

inline bool reportsError(const PrinterSummary& p) {
    return current(p) && (p.printErrorCode != 0 || p.activity == PrinterActivity::Error);
}

class JsonWriter {
public:
    JsonWriter(char* out, std::size_t size) : out_(out), size_(size) {
        if (out_ != nullptr && size_ > 0) out_[0] = '\0';
    }

    void raw(const char* s) {
        while (s != nullptr && *s != '\0') put(*s++);
    }

    void uint(std::uint32_t v) {
        char digits[11];
        std::size_t n = 0;
        do {
            digits[n++] = static_cast<char>('0' + (v % 10U));
            v /= 10U;
        } while (v != 0 && n < sizeof(digits));
        while (n > 0) put(digits[--n]);
    }

    // JSON string with escaping; truncated at maxBytes on a UTF-8 boundary.
    void str(const char* s, std::size_t maxBytes) {
        if (s == nullptr) {
            raw("null");
            return;
        }
        std::size_t len = std::strlen(s);
        if (len > maxBytes) {
            len = maxBytes;
            while (len > 0 && (static_cast<unsigned char>(s[len]) & 0xC0U) == 0x80U) --len;
        }
        put('"');
        for (std::size_t i = 0; i < len; ++i) {
            const unsigned char c = static_cast<unsigned char>(s[i]);
            if (c == '"' || c == '\\') {
                put('\\');
                put(static_cast<char>(c));
            } else if (c < 0x20U) {
                static const char kHex[] = "0123456789abcdef";
                raw("\\u00");
                put(kHex[(c >> 4) & 0xFU]);
                put(kHex[c & 0xFU]);
            } else {
                put(static_cast<char>(c));
            }
        }
        put('"');
    }

    bool ok() const { return !overflow_ && out_ != nullptr && size_ > 0; }
    std::size_t length() const { return length_; }

private:
    void put(char c) {
        if (out_ == nullptr || length_ + 1 >= size_) {
            overflow_ = true;
            return;
        }
        out_[length_++] = c;
        out_[length_] = '\0';
    }

    char* out_;
    std::size_t size_;
    std::size_t length_{0};
    bool overflow_{false};
};

constexpr std::size_t kMaxErrorTextBytes = 160;
constexpr std::size_t kMaxErrorCodeBytes = 24;

// Returns the JSON length, or 0 if it did not fit (the caller answers 500).
inline std::size_t serializeStatusLite(const char* version, const char* sourceCommit,
                                       const PrinterSummary* printers, std::size_t count,
                                       char* out, std::size_t outSize) {
    JsonWriter w(out, outSize);
    w.raw("{\"schema\":1,\"firmware\":{\"version\":");
    w.str(version, 24);
    w.raw(",\"sourceCommit\":");
    w.str(sourceCommit, 40);
    w.raw("},\"printers\":[");
    for (std::size_t i = 0; i < count; ++i) {
        const PrinterSummary& p = printers[i];
        const bool live = current(p);
        if (i > 0) w.raw(",");
        w.raw("{\"slot\":");
        w.uint(p.slot);
        w.raw(",\"connection\":\"");
        w.raw(connectionName(p.connection));
        w.raw("\",\"activity\":\"");
        w.raw(live ? activityName(p.activity) : "unknown");
        w.raw("\",\"freshness\":\"");
        w.raw(freshnessName(p.freshness));
        w.raw("\",\"ageSeconds\":");
        if (p.ageKnown) w.uint(p.ageSeconds); else w.raw("null");
        w.raw(",\"progressPercent\":");
        if (reportsProgress(p)) w.uint(p.progressPercent > 100 ? 100U : p.progressPercent); else w.raw("null");
        w.raw(",\"remainingMinutes\":");
        if (reportsProgress(p)) w.uint(p.remainingMinutes); else w.raw("null");
        w.raw(",\"error\":");
        if (reportsError(p)) {
            w.raw("{\"code\":");
            w.str(p.errorCode, kMaxErrorCodeBytes);
            w.raw(",\"text\":");
            w.str(p.errorText, kMaxErrorTextBytes);
            w.raw(",\"canceled\":");
            w.raw(p.canceled ? "true" : "false");
            w.raw("}");
        } else {
            w.raw("null");
        }
        w.raw("}");
    }
    w.raw("]}");
    return w.ok() ? w.length() : 0;
}

}  // namespace statuslite
}  // namespace workshop
