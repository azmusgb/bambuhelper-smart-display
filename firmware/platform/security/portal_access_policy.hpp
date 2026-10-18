#pragma once

// Workshop OS local portal access policy.
//
// This header is the single, host-testable decision table for every request
// that reaches securityAuthorize(). It deliberately has no Arduino/WebServer
// dependency so tests/workshop_os12_portal_access_smoke.cpp can prove the
// policy on a normal C++ compiler.
//
// Contract (docs/portal-auth-v11-20.md, SECURITY.md):
//   * normal LAN routes require the boot-scoped portal-code session;
//   * every mutation additionally requires a real same-origin browser request
//     (Origin, or Referer when Origin is absent). No client-supplied marker
//     header is accepted as proof of origin;
//   * ordinary setup/fallback AP exposes only the captive onboarding surface;
//   * deliberate Recovery Safe Mode exposes only recovery, application OTA and
//     factory reset;
//   * the optional owner setting "Require access code = off" opens a short,
//     explicit list of read-only status routes on station Wi-Fi. It never opens
//     controls, settings, credentials, capture, diagnostics or Recovery, and it
//     never applies while the device is in AP mode. It defaults to locked.

#include <cstddef>
#include <cstdint>
#include <cstring>

namespace workshop {
namespace security {

enum class PortalAccess : std::uint8_t {
    Allow = 0,
    RejectCrossOrigin,  // HTTP 403: mutation without a same-origin browser context
    SignInRedirect,     // HTTP 303 -> /login: unauthenticated page navigation
    SignInRequired,     // HTTP 401 JSON: unauthenticated API/status/control request
};

struct PortalRequestFacts {
    const char* uri{""};
    bool mutating{false};
    bool apMode{false};
    bool recoverySafeMode{false};
    bool sessionValid{false};
    bool sameOrigin{false};
    bool portalLocked{true};
};

namespace detail {

inline bool equalsIgnoreCase(const char* a, const char* b) {
    if (a == nullptr || b == nullptr) return false;
    while (*a != '\0' && *b != '\0') {
        char ca = *a;
        char cb = *b;
        if (ca >= 'A' && ca <= 'Z') ca = static_cast<char>(ca - 'A' + 'a');
        if (cb >= 'A' && cb <= 'Z') cb = static_cast<char>(cb - 'A' + 'a');
        if (ca != cb) return false;
        ++a;
        ++b;
    }
    return *a == '\0' && *b == '\0';
}

inline bool same(const char* a, const char* b) {
    return a != nullptr && b != nullptr && std::strcmp(a, b) == 0;
}

inline bool startsWith(const char* text, const char* prefix) {
    if (text == nullptr || prefix == nullptr) return false;
    return std::strncmp(text, prefix, std::strlen(prefix)) == 0;
}

inline bool empty(const char* text) {
    return text == nullptr || text[0] == '\0';
}

// Builds "<scheme><host><suffix>" into out. Returns false when it cannot fit.
inline bool compose(char* out, std::size_t outSize, const char* scheme, const char* host, const char* suffix) {
    const std::size_t a = std::strlen(scheme);
    const std::size_t b = std::strlen(host);
    const std::size_t c = std::strlen(suffix);
    if (a + b + c + 1 > outSize) return false;
    std::memcpy(out, scheme, a);
    std::memcpy(out + a, host, b);
    std::memcpy(out + a + b, suffix, c);
    out[a + b + c] = '\0';
    return true;
}

}  // namespace detail

constexpr std::size_t kMaxOriginHostLength = 96;

// Same-origin check for a mutating request. Inputs are the trimmed Host,
// Origin and Referer header values. A missing Host, an opaque "null" Origin,
// or a request with neither Origin nor Referer is not same-origin.
inline bool sameOriginHeaders(const char* host, const char* origin, const char* referer) {
    if (detail::empty(host) || std::strlen(host) > kMaxOriginHostLength) return false;
    char expected[kMaxOriginHostLength + 16];

    if (!detail::empty(origin)) {
        if (detail::compose(expected, sizeof(expected), "http://", host, "") &&
            detail::equalsIgnoreCase(origin, expected)) return true;
        if (detail::compose(expected, sizeof(expected), "https://", host, "") &&
            detail::equalsIgnoreCase(origin, expected)) return true;
        return false;
    }

    if (!detail::empty(referer)) {
        if (detail::compose(expected, sizeof(expected), "http://", host, "/") &&
            detail::startsWith(referer, expected)) return true;
        if (detail::compose(expected, sizeof(expected), "https://", host, "/") &&
            detail::startsWith(referer, expected)) return true;
    }
    return false;
}

// Ordinary first-boot/fallback AP: captive onboarding essentials only.
inline bool captiveOnboardingRoute(const char* uri) {
    return detail::same(uri, "/") || detail::same(uri, "/save/wifi") ||
           detail::same(uri, "/app.css") || detail::same(uri, "/app.js");
}

// Deliberate Recovery Safe Mode: dedicated recovery, application OTA, reset.
inline bool recoverySafeModeRoute(const char* uri) {
    return detail::same(uri, "/recovery") || detail::startsWith(uri, "/recovery/") ||
           detail::same(uri, "/ota/upload") || detail::same(uri, "/reset");
}

inline bool apPublicRoute(const char* uri, bool apMode, bool recoverySafeMode) {
    if (!apMode) return false;
    if (captiveOnboardingRoute(uri)) return true;
    return recoverySafeMode && recoverySafeModeRoute(uri);
}

// Read-only routes that the owner may open on station Wi-Fi by turning
// "Require access code" off. Exact matches only; nothing that can reveal a
// credential, a framebuffer, settings, diagnostics or Recovery belongs here.
inline bool openReadRoute(const char* uri) {
    static const char* const kRoutes[] = {
        "/",
        "/status",
        "/hardware/health",
        "/hub/timer/status",
        "/os12/update/status",
        "/api/portal-security",
    };
    for (std::size_t i = 0; i < sizeof(kRoutes) / sizeof(kRoutes[0]); ++i) {
        if (detail::same(uri, kRoutes[i])) return true;
    }
    return false;
}

// Unauthenticated navigations that should land on the sign-in page instead of
// a bare 401 JSON body.
inline bool signInNavigationRoute(const char* uri) {
    return detail::same(uri, "/") || detail::same(uri, "/recovery");
}

inline PortalAccess decidePortalAccess(const PortalRequestFacts& r) {
    const char* uri = r.uri != nullptr ? r.uri : "";

    if (apPublicRoute(uri, r.apMode, r.recoverySafeMode)) {
        if (r.mutating && !r.sameOrigin) return PortalAccess::RejectCrossOrigin;
        return PortalAccess::Allow;
    }

    if (r.mutating && !r.sameOrigin) return PortalAccess::RejectCrossOrigin;
    if (r.sessionValid) return PortalAccess::Allow;

    if (!r.mutating && !r.portalLocked && !r.apMode && openReadRoute(uri)) {
        return PortalAccess::Allow;
    }

    if (!r.mutating && signInNavigationRoute(uri)) return PortalAccess::SignInRedirect;
    return PortalAccess::SignInRequired;
}

}  // namespace security
}  // namespace workshop
