#include "../firmware/platform/code_token_core.hpp"
#include "../firmware/platform/security/portal_access_policy.hpp"

#include <cassert>
#include <cstring>

using namespace workshop::codetoken;
using workshop::statuslite::ApprovalFlow;
using workshop::statuslite::ApprovalPhase;
using workshop::statuslite::kTokenPrefixLength;

namespace {

const char* kGoodKey = "wsc_ABCDEFGHJKLMNPQRSTUVWXYZ23";
const char* kStatusToken = "wsl_ABCDEFGHJKLMNPQRSTUVWXYZ23";

void keyText() {
    std::uint8_t zeros[kTokenRandomBytes] = {};
    std::uint8_t ones[kTokenRandomBytes];
    std::memset(ones, 0xFF, sizeof(ones));
    char a[kTokenTextLength + 1];
    char b[kTokenTextLength + 1];
    encodeCodeToken(zeros, a);
    encodeCodeToken(ones, b);
    assert(std::strcmp(a, "wsc_AAAAAAAAAAAAAAAAAAAAAAAAAA") == 0);
    assert(std::strncmp(b, "wsc_9999999999999999999999999", 29) == 0);
    assert(wellFormedCodeToken(a) && wellFormedCodeToken(b));

    // Same random bytes, different scope: the bodies match, the prefixes do not,
    // and neither key is well-formed for the other scope.
    char lite[kTokenTextLength + 1];
    workshop::statuslite::encodeToken(ones, lite);
    assert(std::strncmp(lite, "wsl_", kTokenPrefixLength) == 0);
    assert(std::strcmp(lite + kTokenPrefixLength, b + kTokenPrefixLength) == 0);
    assert(!wellFormedCodeToken(lite));
    assert(!workshop::statuslite::wellFormedToken(b));
    assert(std::strcmp(kCodeTokenPrefix, workshop::statuslite::kTokenPrefix) != 0);

    // A bad scope prefix falls back to the status prefix rather than overrunning.
    char odd[kTokenTextLength + 1];
    workshop::statuslite::encodeToken(zeros, odd, "toolong_");
    assert(std::strncmp(odd, "wsl_", 4) == 0 && std::strlen(odd) == kTokenTextLength);
    assert(!workshop::statuslite::wellFormedToken(kGoodKey, nullptr));
    assert(!workshop::statuslite::wellFormedToken(kGoodKey, "ws"));
}

void bearerParsing() {
    char out[kTokenTextLength + 1];
    assert(parseCodeBearer("Bearer wsc_ABCDEFGHJKLMNPQRSTUVWXYZ23", out) && std::strcmp(out, kGoodKey) == 0);
    assert(parseCodeBearer("bearer   wsc_ABCDEFGHJKLMNPQRSTUVWXYZ23  ", out));
    assert(!parseCodeBearer(nullptr, out));
    assert(!parseCodeBearer("", out));
    assert(!parseCodeBearer("Bearer", out));
    assert(!parseCodeBearer("Basic wsc_ABCDEFGHJKLMNPQRSTUVWXYZ23", out));
    assert(!parseCodeBearer("Bearer wsc_ABCDEFGHJKLMNPQRSTUVWXYZ23 extra", out));
    assert(!parseCodeBearer("Bearer wsc_ABCDEFGHJKLMNPQRSTUVWXYZ2", out));
    assert(!parseCodeBearer("Bearer wsc_abcdefghjklmnpqrstuvwxyz23", out));
    // The status token never opens the code route, and the code key never
    // opens the status route.
    assert(!parseCodeBearer("Bearer wsl_ABCDEFGHJKLMNPQRSTUVWXYZ23", out));
    assert(!workshop::statuslite::parseBearer("Bearer wsc_ABCDEFGHJKLMNPQRSTUVWXYZ23", out));
    assert(workshop::statuslite::parseBearer("Bearer wsl_ABCDEFGHJKLMNPQRSTUVWXYZ23", out) &&
           std::strcmp(out, kStatusToken) == 0);
    // The portal code itself is not a key.
    assert(!parseCodeBearer("Bearer ABCDEFGHJK", out));
}

void approvalFlow() {
    CodeApprovalFlow flow;
    char out[kTokenTextLength + 1];
    std::uint32_t t = 5000;
    flow.start(77, t);
    assert(flow.promptVisible(t) && flow.secondsLeft(t) == 60);
    // A status token cannot be handed over by the code key's flow.
    assert(!flow.approve(kStatusToken, t + 1000));
    assert(flow.phase(t + 1000) == ApprovalPhase::Pending);
    assert(flow.approve(kGoodKey, t + 2000));
    assert(flow.phase(t + 2000) == ApprovalPhase::Approved && flow.holdsPlaintext());
    assert(!flow.claim(78, t + 3000, out));   // other request
    assert(flow.claim(77, t + 3000, out) && std::strcmp(out, kGoodKey) == 0);
    assert(!flow.holdsPlaintext() && !flow.claim(77, t + 3100, out));  // shown once

    // Cancel on the display.
    flow.start(80, t);
    assert(flow.deny(t + 100) && flow.phase(t + 100) == ApprovalPhase::Denied && !flow.promptVisible(t + 100));
    // 60 s expiry without a tap.
    flow.start(81, t);
    assert(flow.promptVisible(t + 59999) && !flow.promptVisible(t + 60000));
    assert(flow.phase(t + 60000) == ApprovalPhase::Expired);
    // An approved key not collected within 60 s is forgotten.
    flow.start(82, t);
    assert(flow.approve(kGoodKey, t + 1000));
    assert(flow.phase(t + 61000) == ApprovalPhase::Expired && !flow.holdsPlaintext());
    // A new request wipes an unclaimed key.
    flow.start(83, t);
    assert(flow.approve(kGoodKey, t + 1000));
    flow.start(84, t + 2000);
    assert(!flow.holdsPlaintext() && !flow.claim(83, t + 2100, out));

    // The status flow still only hands over status tokens.
    ApprovalFlow lite;
    lite.start(9, t);
    assert(!lite.approve(kGoodKey, t + 1));
    assert(lite.approve(kStatusToken, t + 2));
}

void portalCode() {
    assert(portalCodeWellFormed("ABCDEFGHJK"));
    assert(portalCodeWellFormed("2345678923"));
    assert(!portalCodeWellFormed(nullptr));
    assert(!portalCodeWellFormed(""));
    assert(!portalCodeWellFormed("ABCDEFGHJ"));     // short
    assert(!portalCodeWellFormed("ABCDEFGHJKL"));   // long
    assert(!portalCodeWellFormed("ABCDEFGHIK"));    // I
    assert(!portalCodeWellFormed("abcdefghjk"));    // lower case
    assert(!portalCodeWellFormed("ABCDE\"GHJK"));   // quote
}

void bootIds() {
    char id[kBootIdLength + 1];
    formatBootId(0x0123ABCDU, 0x89ef4567U, id);
    assert(std::strcmp(id, "0123abcd89ef4567") == 0 && bootIdWellFormed(id));
    formatBootId(0, 0, id);
    assert(std::strcmp(id, "0000000000000000") == 0 && !bootIdWellFormed(id));  // never all zero
    assert(!bootIdWellFormed(nullptr));
    assert(!bootIdWellFormed("0123ABCD89EF4567"));
    assert(!bootIdWellFormed("0123abcd89ef456"));
    assert(!bootIdWellFormed("0123abcd89ef45678"));
}

void serializer() {
    char out[kResponseBytes];
    const std::size_t n = serializePortalCode("ABCDEFGHJK", "0123abcd89ef4567", out, sizeof(out));
    assert(n == std::strlen(out));
    assert(std::strcmp(out, "{\"code\":\"ABCDEFGHJK\",\"bootId\":\"0123abcd89ef4567\"}") == 0);
    // Malformed inputs are never served.
    assert(serializePortalCode("", "0123abcd89ef4567", out, sizeof(out)) == 0 && out[0] == '\0');
    assert(serializePortalCode(nullptr, "0123abcd89ef4567", out, sizeof(out)) == 0);
    assert(serializePortalCode("ABCDE\"GHJK", "0123abcd89ef4567", out, sizeof(out)) == 0);
    assert(serializePortalCode("ABCDEFGHJK", "0000000000000000", out, sizeof(out)) == 0);
    assert(serializePortalCode("ABCDEFGHJK", "zz", out, sizeof(out)) == 0);
    // Overflow fails closed.
    char small[20];
    assert(serializePortalCode("ABCDEFGHJK", "0123abcd89ef4567", small, sizeof(small)) == 0);
    assert(serializePortalCode("ABCDEFGHJK", "0123abcd89ef4567", nullptr, 0) == 0);
}

void sharedLimiter() {
    // Same limiter as /api/status/lite: one answer every 2 s, back-off after
    // the third bad key, capped at 60 s.
    workshop::statuslite::ReadLimiter limiter;
    const std::uint32_t client = 0x0A000032;
    std::uint32_t t = 1000;
    assert(limiter.admit(client, t).allowed);
    assert(!limiter.admit(client, t + 1999).allowed);
    t += 2000;
    for (int i = 0; i < 2; ++i) {
        assert(limiter.admit(client, t).allowed);
        limiter.noteFailure(client, t);
        t += 2000;
    }
    assert(limiter.admit(client, t).allowed);
    limiter.noteFailure(client, t);  // third bad key: blocked
    assert(!limiter.admit(client, t + 500).allowed);
}

void keyCannotSatisfyPortalPolicy() {
    // The portal policy has no input for a bearer key: a request carrying only
    // the key (no session) to any protected route is refused.
    workshop::security::PortalRequestFacts facts;
    facts.uri = "/printer/access-code";
    facts.mutating = false;
    facts.apMode = false;
    facts.recoverySafeMode = false;
    facts.sameOrigin = false;
    facts.sessionValid = false;
    facts.portalLocked = true;
    assert(workshop::security::decidePortalAccess(facts) != workshop::security::PortalAccess::Allow);
    facts.uri = "/api/code-token";
    assert(workshop::security::decidePortalAccess(facts) != workshop::security::PortalAccess::Allow);
    facts.uri = "/settings/export";
    facts.portalLocked = false;  // even with "Require access code" off
    assert(workshop::security::decidePortalAccess(facts) != workshop::security::PortalAccess::Allow);
}

}  // namespace

int main() {
    keyText();
    bearerParsing();
    approvalFlow();
    portalCode();
    bootIds();
    serializer();
    sharedLimiter();
    keyCannotSatisfyPortalPolicy();
    return 0;
}
