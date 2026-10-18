#include "../firmware/platform/status_lite_core.hpp"
#include "../firmware/platform/security/portal_access_policy.hpp"

#include <cassert>
#include <cstring>

using namespace workshop::statuslite;
using workshop::platform::Connectivity;
using workshop::platform::Freshness;
using workshop::platform::PrinterActivity;

namespace {

bool contains(const char* haystack, const char* needle) { return std::strstr(haystack, needle) != nullptr; }

void tokenText() {
    std::uint8_t zeros[kTokenRandomBytes] = {};
    std::uint8_t ones[kTokenRandomBytes];
    std::memset(ones, 0xFF, sizeof(ones));
    char a[kTokenTextLength + 1];
    char b[kTokenTextLength + 1];
    encodeToken(zeros, a);
    encodeToken(ones, b);
    assert(std::strlen(a) == kTokenTextLength && std::strlen(b) == kTokenTextLength);
    assert(std::strcmp(a, "wsl_AAAAAAAAAAAAAAAAAAAAAAAAAA") == 0);
    assert(std::strncmp(b, "wsl_9999999999999999999999999", 29) == 0);
    assert(wellFormedToken(a) && wellFormedToken(b));
    // 128 bits: the last character carries the final 3 bits padded with zeros.
    assert(b[kTokenTextLength - 1] == kTokenAlphabet[0x1C]);

    std::uint8_t mixed[kTokenRandomBytes] = {0x01, 0x23, 0x45, 0x67, 0x89, 0xAB, 0xCD, 0xEF,
                                             0x10, 0x32, 0x54, 0x76, 0x98, 0xBA, 0xDC, 0xFE};
    char c[kTokenTextLength + 1];
    encodeToken(mixed, c);
    assert(wellFormedToken(c) && std::strcmp(a, c) != 0);
    for (std::size_t i = kTokenPrefixLength; i < kTokenTextLength; ++i) {
        assert(c[i] != 'I' && c[i] != 'O' && c[i] != '0' && c[i] != '1');
    }
}

void bearerParsing() {
    const char* good = "wsl_ABCDEFGHJKLMNPQRSTUVWXYZ23";
    char out[kTokenTextLength + 1];
    assert(parseBearer("Bearer wsl_ABCDEFGHJKLMNPQRSTUVWXYZ23", out) && std::strcmp(out, good) == 0);
    assert(parseBearer("bearer   wsl_ABCDEFGHJKLMNPQRSTUVWXYZ23  ", out));
    assert(parseBearer("BEARER\twsl_ABCDEFGHJKLMNPQRSTUVWXYZ23", out));
    assert(!parseBearer(nullptr, out));
    assert(!parseBearer("", out));
    assert(!parseBearer("Bearer", out));
    assert(!parseBearer("Bearer ", out));
    assert(!parseBearer("Basic wsl_ABCDEFGHJKLMNPQRSTUVWXYZ23", out));
    assert(!parseBearer("Bearerwsl_ABCDEFGHJKLMNPQRSTUVWXYZ23", out));
    assert(!parseBearer("Bearer wsl_ABCDEFGHJKLMNPQRSTUVWXYZ23 extra", out));
    assert(!parseBearer("Bearer wsl_ABCDEFGHJKLMNPQRSTUVWXYZ2", out));   // short
    assert(!parseBearer("Bearer wsl_ABCDEFGHJKLMNPQRSTUVWXYZ234", out)); // long
    assert(!parseBearer("Bearer wsl_abcdefghjklmnpqrstuvwxyz23", out));  // lower case
    assert(!parseBearer("Bearer wsl_ABCDEFGHIKLMNPQRSTUVWXYZ23", out));  // I not in alphabet
    assert(!parseBearer("Bearer wsl_ABCDEFGH0KLMNPQRSTUVWXYZ23", out));  // 0 not in alphabet
    assert(!parseBearer("Bearer abc_ABCDEFGHJKLMNPQRSTUVWXYZ23", out));  // prefix
    assert(!parseBearer("Bearer BHSESSION=0123456789abcdef0123456789abcdef", out));
}

void digests() {
    std::uint8_t a[kDigestBytes] = {};
    std::uint8_t b[kDigestBytes] = {};
    assert(digestEmpty(a) && digestEqual(a, b));
    b[31] = 1;
    assert(!digestEqual(a, b) && !digestEmpty(b));
    a[31] = 1;
    assert(digestEqual(a, b));
    a[0] = 0x80;
    assert(!digestEqual(a, b));
}

void rateLimit() {
    ReadLimiter limiter;
    const std::uint32_t client = 0x0A000032;
    const std::uint32_t other = 0x0A000033;
    std::uint32_t t = 1000;

    ReadDecision d = limiter.admit(client, t);
    assert(d.allowed);
    d = limiter.admit(client, t + 500);
    assert(!d.allowed && d.retryAfterSeconds >= 1 && d.retryAfterSeconds <= 2);
    assert(limiter.admit(other, t + 500).allowed);  // per client
    d = limiter.admit(client, t + 2000);
    assert(d.allowed);

    // Bad tokens: two are free, then 1 s, 2 s, 4 s ... capped at 60 s.
    t += 10000;
    assert(limiter.admit(client, t).allowed);
    limiter.noteFailure(client, t);
    t += 2000;
    assert(limiter.admit(client, t).allowed);
    limiter.noteFailure(client, t);
    t += 2000;
    assert(limiter.admit(client, t).allowed);
    limiter.noteFailure(client, t);  // third failure -> 1 s block (inside the 2 s interval)
    t += 2000;
    assert(limiter.admit(client, t).allowed);
    limiter.noteFailure(client, t);  // fourth -> 2 s
    d = limiter.admit(client, t + 1500);
    assert(!d.allowed);
    for (int i = 0; i < 12; ++i) limiter.noteFailure(client, t);
    d = limiter.admit(client, t + 100);
    assert(!d.allowed && d.retryAfterSeconds <= 60 && d.retryAfterSeconds >= 59);
    assert(!limiter.admit(client, t + 59000).allowed);
    assert(limiter.admit(client, t + 60001).allowed);
    limiter.noteSuccess(client, t + 60001);
    assert(limiter.admit(client, t + 62002).allowed);

    // Millisecond wrap-around does not unblock or lock forever.
    ReadLimiter wrap;
    const std::uint32_t nearWrap = 0xFFFFFF00U;
    assert(wrap.admit(client, nearWrap).allowed);
    assert(!wrap.admit(client, nearWrap + 1000U).allowed);
    assert(wrap.admit(client, nearWrap + 2100U).allowed);

    // More clients than buckets still answers every newcomer once.
    ReadLimiter many;
    for (std::uint32_t c = 1; c <= 3 * ReadLimiter::kBuckets; ++c) assert(many.admit(c, 5000 + c).allowed);
}

void approvalFlow() {
    const char* token = "wsl_ABCDEFGHJKLMNPQRSTUVWXYZ23";
    char out[kTokenTextLength + 1];
    ApprovalFlow flow;
    std::uint32_t t = 5000;

    assert(flow.phase(t) == ApprovalPhase::Idle && !flow.promptVisible(t));
    assert(!flow.approve(token, t));          // nothing pending
    assert(!flow.claim(42, t, out));

    flow.start(42, t);
    assert(flow.promptVisible(t) && flow.secondsLeft(t) == 60);
    assert(!flow.claim(42, t + 1, out));      // not approved yet
    assert(!flow.approve("not-a-token", t + 1));
    assert(flow.approve(token, t + 10000));
    assert(!flow.promptVisible(t + 10000) && flow.holdsPlaintext());
    assert(!flow.claim(41, t + 10001, out));  // other request id
    assert(flow.claim(42, t + 10002, out) && std::strcmp(out, token) == 0);
    assert(!flow.holdsPlaintext());
    assert(!flow.claim(42, t + 10003, out));  // shown once

    // No tap within 60 s: the prompt expires and Allow no longer works.
    flow.start(7, t);
    assert(flow.promptVisible(t + 59999));
    assert(!flow.promptVisible(t + 60000) && flow.phase(t + 60000) == ApprovalPhase::Expired);
    assert(!flow.approve(token, t + 60001));

    // Deny.
    flow.start(8, t);
    assert(flow.deny(t + 1) && flow.phase(t + 1) == ApprovalPhase::Denied);
    assert(!flow.approve(token, t + 2) && !flow.claim(8, t + 2, out));

    // Approved but never claimed: plaintext is wiped after 60 s.
    flow.start(9, t);
    assert(flow.approve(token, t + 1000));
    assert(flow.phase(t + 1000 + 60000) == ApprovalPhase::Expired && !flow.holdsPlaintext());
    assert(!flow.claim(9, t + 1000 + 60001, out));

    // A new request wipes an unclaimed token from the previous one.
    flow.start(10, t);
    assert(flow.approve(token, t + 1));
    flow.start(11, t + 2);
    assert(!flow.holdsPlaintext() && !flow.claim(10, t + 3, out));
    flow.cancel();
    assert(flow.phase(t + 4) == ApprovalPhase::Idle);
}

PrinterSummary printing() {
    PrinterSummary p;
    p.slot = 0;
    p.connection = Connectivity::Online;
    p.activity = PrinterActivity::Printing;
    p.freshness = Freshness::Fresh;
    p.ageKnown = true;
    p.ageSeconds = 3;
    p.progressPercent = 62;
    p.remainingMinutes = 41;
    return p;
}

void serializer() {
    char out[2048];
    PrinterSummary p = printing();
    std::size_t n = serializeStatusLite("12.1.0", "0123456789abcdef0123456789abcdef01234567", &p, 1, out, sizeof(out));
    assert(n > 0 && n == std::strlen(out));
    assert(std::strcmp(out,
        "{\"schema\":1,\"firmware\":{\"version\":\"12.1.0\",\"sourceCommit\":\"0123456789abcdef0123456789abcdef01234567\"},"
        "\"printers\":[{\"slot\":0,\"connection\":\"online\",\"activity\":\"printing\",\"freshness\":\"fresh\","
        "\"ageSeconds\":3,\"progressPercent\":62,\"remainingMinutes\":41,\"error\":null}]}") == 0);

    // Field allowlist: nothing identifying or unrelated can appear.
    const char* const forbidden[] = {"name", "subtask", "job", "file", "\"ip\"", "mac", "serial", "rssi",
                                     "nozzle", "bed", "ams", "token", "code\":\"wsl_"};
    for (const char* key : forbidden) assert(!contains(out, key));

    // Stale telemetry is never shown as current.
    p.freshness = Freshness::Stale;
    p.ageSeconds = 75;
    n = serializeStatusLite("12.1.0", "x", &p, 1, out, sizeof(out));
    assert(n > 0);
    assert(contains(out, "\"activity\":\"unknown\"") && contains(out, "\"freshness\":\"stale\""));
    assert(contains(out, "\"ageSeconds\":75") && contains(out, "\"progressPercent\":null"));
    assert(contains(out, "\"remainingMinutes\":null") && contains(out, "\"error\":null"));

    // Offline but recently heard from: still not current.
    p = printing();
    p.connection = Connectivity::Offline;
    serializeStatusLite("12.1.0", "x", &p, 1, out, sizeof(out));
    assert(contains(out, "\"connection\":\"offline\"") && contains(out, "\"activity\":\"unknown\""));
    assert(contains(out, "\"progressPercent\":null"));

    // Unknown age and conflicting freshness pass through as unknown.
    p = printing();
    p.freshness = Freshness::Conflicting;
    p.ageKnown = false;
    serializeStatusLite("12.1.0", "x", &p, 1, out, sizeof(out));
    assert(contains(out, "\"freshness\":\"unknown\"") && contains(out, "\"ageSeconds\":null"));

    // Idle and finished never report progress or time left.
    p = printing();
    p.activity = PrinterActivity::Idle;
    serializeStatusLite("12.1.0", "x", &p, 1, out, sizeof(out));
    assert(contains(out, "\"activity\":\"idle\"") && contains(out, "\"progressPercent\":null"));
    p.activity = PrinterActivity::Finished;
    serializeStatusLite("12.1.0", "x", &p, 1, out, sizeof(out));
    assert(contains(out, "\"activity\":\"finished\"") && contains(out, "\"remainingMinutes\":null"));

    // Preparing and paused do.
    p.activity = PrinterActivity::Paused;
    serializeStatusLite("12.1.0", "x", &p, 1, out, sizeof(out));
    assert(contains(out, "\"activity\":\"paused\"") && contains(out, "\"progressPercent\":62"));

    // Error with board wording; wording is escaped, never invented.
    p = printing();
    p.activity = PrinterActivity::Error;
    p.printErrorCode = 0x0300400C;
    p.errorCode = "0300_400C";
    p.errorText = "Nozzle \"clog\"\\detected\n";
    serializeStatusLite("12.1.0", "x", &p, 1, out, sizeof(out));
    assert(contains(out, "\"error\":{\"code\":\"0300_400C\",\"text\":\"Nozzle \\\"clog\\\"\\\\detected\\u000a\",\"canceled\":false}"));
    assert(contains(out, "\"progressPercent\":null"));

    // No wording on this board: text is null.
    p.errorText = nullptr;
    p.canceled = true;
    serializeStatusLite("12.1.0", "x", &p, 1, out, sizeof(out));
    assert(contains(out, "\"text\":null,\"canceled\":true"));

    // A print error while still printing is reported alongside progress.
    p = printing();
    p.printErrorCode = 0x07008011;
    p.errorCode = "0700_8011";
    serializeStatusLite("12.1.0", "x", &p, 1, out, sizeof(out));
    assert(contains(out, "\"progressPercent\":62") && contains(out, "\"code\":\"0700_8011\""));

    // A stale error is not reported as current.
    p.freshness = Freshness::Stale;
    serializeStatusLite("12.1.0", "x", &p, 1, out, sizeof(out));
    assert(contains(out, "\"error\":null"));

    // Long text is truncated on a UTF-8 boundary.
    char longText[400];
    std::memset(longText, 'a', sizeof(longText));
    longText[158] = static_cast<char>(0xC3);
    longText[159] = static_cast<char>(0xA9);
    longText[160] = static_cast<char>(0xC3);
    longText[161] = static_cast<char>(0xA9);
    longText[sizeof(longText) - 1] = '\0';
    p = printing();
    p.activity = PrinterActivity::Error;
    p.errorText = longText;
    n = serializeStatusLite("12.1.0", "x", &p, 1, out, sizeof(out));
    assert(n > 0 && !contains(out, "\xC3\""));

    // Several printers, and an empty list.
    PrinterSummary two[2] = {printing(), printing()};
    two[1].slot = 2;
    two[1].activity = PrinterActivity::Idle;
    serializeStatusLite("12.1.0", "x", two, 2, out, sizeof(out));
    assert(contains(out, "{\"slot\":0,") && contains(out, "},{\"slot\":2,"));
    serializeStatusLite("12.1.0", "x", nullptr, 0, out, sizeof(out));
    assert(contains(out, "\"printers\":[]}"));

    // Overflow fails closed.
    char tiny[32];
    assert(serializeStatusLite("12.1.0", "x", &p, 1, tiny, sizeof(tiny)) == 0);
}

void tokenOpensNothingElse() {
    using workshop::security::PortalAccess;
    using workshop::security::PortalRequestFacts;
    using workshop::security::decidePortalAccess;
    // The portal policy has no token input at all, so a bearer token cannot
    // satisfy it. Unauthenticated requests to token management and to every
    // other route stay refused.
    const char* const routes[] = {"/status", "/hardware/health", "/api/status-token", "/printer/access-code",
                                  "/hub/frame.ppm", "/settings/export"};
    for (const char* uri : routes) {
        PortalRequestFacts r;
        r.uri = uri;
        assert(decidePortalAccess(r) == PortalAccess::SignInRequired);
    }
    const char* const mutations[] = {"/api/status-token/create", "/api/status-token/claim",
                                     "/api/status-token/revoke", "/printer/control"};
    for (const char* uri : mutations) {
        PortalRequestFacts r;
        r.uri = uri;
        r.mutating = true;
        r.sameOrigin = true;
        assert(decidePortalAccess(r) == PortalAccess::SignInRequired);
    }
    assert(!workshop::security::openReadRoute("/api/status/lite"));
    assert(!workshop::security::openReadRoute("/api/status-token"));
}

}  // namespace

int main() {
    tokenText();
    bearerParsing();
    digests();
    rateLimit();
    approvalFlow();
    serializer();
    tokenOpensNothingElse();
    return 0;
}
