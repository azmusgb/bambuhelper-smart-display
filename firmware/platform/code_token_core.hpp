#pragma once

// Workshop OS sign-in code key: pure, host-testable core.
//
// A second device-issued key, separate from the read-only status token. Its
// only power is one route, GET /api/portal-code, which answers the current
// Local Portal sign-in code so Local AI can show it to the owner:
//
//   {"code":"ABCDEFGHJK","bootId":"0123456789abcdef"}
//
// The key text is "wsc_" + 26 characters (the status token is "wsl_" + 26), so
// neither key is ever well-formed for the other's route. Token encoding,
// strict Bearer parsing, constant-time digest comparison, the per-client read
// limiter and the touchscreen approval flow are shared with
// status_lite_core.hpp; this header adds the scope prefix, the portal-code and
// boot-id checks and the response serializer.
// tests/workshop_os12_code_token_smoke.cpp proves it on a host compiler.

#include "status_lite_core.hpp"

#include <cstddef>
#include <cstdint>
#include <cstring>

namespace workshop {
namespace codetoken {

using statuslite::kDigestBytes;
using statuslite::kTokenAlphabet;
using statuslite::kTokenRandomBytes;
using statuslite::kTokenTextLength;

constexpr char kCodeTokenPrefix[] = "wsc_";
static_assert(sizeof(kCodeTokenPrefix) == sizeof(statuslite::kTokenPrefix),
              "scope prefixes must have the same length");

constexpr std::size_t kPortalCodeLength = 10;   // security_manager.cpp kCodeLen
constexpr std::size_t kBootIdLength = 16;       // 64 bits as lower-case hex
constexpr std::size_t kResponseBytes = 64;      // {"code":"<10>","bootId":"<16>"} is 41

inline void encodeCodeToken(const std::uint8_t random[kTokenRandomBytes], char out[kTokenTextLength + 1]) {
    statuslite::encodeToken(random, out, kCodeTokenPrefix);
}

inline bool wellFormedCodeToken(const char* token) {
    return statuslite::wellFormedToken(token, kCodeTokenPrefix);
}

// Strict "Authorization: Bearer wsc_..." parsing. A status token ("wsl_...")
// is rejected here exactly like any other wrong token.
inline bool parseCodeBearer(const char* header, char out[kTokenTextLength + 1]) {
    return statuslite::parseBearer(header, out, kCodeTokenPrefix);
}

// Approval flow whose hand-over only accepts "wsc_" keys.
class CodeApprovalFlow : public statuslite::ApprovalFlow {
public:
    CodeApprovalFlow() : statuslite::ApprovalFlow(kCodeTokenPrefix) {}
};

// The Local Portal code: exactly 10 characters of the portal alphabet.
inline bool portalCodeWellFormed(const char* code) {
    if (code == nullptr || std::strlen(code) != kPortalCodeLength) return false;
    for (std::size_t i = 0; i < kPortalCodeLength; ++i) {
        if (!statuslite::tokenAlphabetChar(code[i])) return false;
    }
    return true;
}

// Boot id: chosen at random once per boot. The portal code is also chosen
// once per boot, so a new boot id means the code has (probably) changed and
// an old one is no longer worth showing. Clients compare it for equality only.
inline void formatBootId(std::uint32_t high, std::uint32_t low, char out[kBootIdLength + 1]) {
    static const char kHex[] = "0123456789abcdef";
    for (std::size_t i = 0; i < 8; ++i) {
        out[i] = kHex[(high >> (28 - 4 * i)) & 0xFU];
        out[8 + i] = kHex[(low >> (28 - 4 * i)) & 0xFU];
    }
    out[kBootIdLength] = '\0';
}

inline bool bootIdWellFormed(const char* bootId) {
    if (bootId == nullptr || std::strlen(bootId) != kBootIdLength) return false;
    bool any = false;
    for (std::size_t i = 0; i < kBootIdLength; ++i) {
        const char c = bootId[i];
        if (!((c >= '0' && c <= '9') || (c >= 'a' && c <= 'f'))) return false;
        if (c != '0') any = true;
    }
    return any;
}

// The whole response. Exactly two fields; nothing else is an input, so
// nothing else can leak. Returns the JSON length, or 0 when the code or boot
// id is malformed or the buffer is too small (the caller answers 503/500).
inline std::size_t serializePortalCode(const char* code, const char* bootId, char* out, std::size_t outSize) {
    if (!portalCodeWellFormed(code) || !bootIdWellFormed(bootId)) {
        if (out != nullptr && outSize > 0) out[0] = '\0';
        return 0;
    }
    statuslite::JsonWriter w(out, outSize);
    w.raw("{\"code\":\"");
    w.raw(code);
    w.raw("\",\"bootId\":\"");
    w.raw(bootId);
    w.raw("\"}");
    return w.ok() ? w.length() : 0;
}

}  // namespace codetoken
}  // namespace workshop
