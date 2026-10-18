#include "../firmware/platform/security/portal_access_policy.hpp"

#include <cassert>

using workshop::security::PortalAccess;
using workshop::security::PortalRequestFacts;
using workshop::security::decidePortalAccess;
using workshop::security::sameOriginHeaders;
using workshop::security::openReadRoute;

namespace {

PortalRequestFacts lan(const char* uri, bool mutating) {
    PortalRequestFacts r;
    r.uri = uri;
    r.mutating = mutating;
    r.apMode = false;
    r.recoverySafeMode = false;
    r.sessionValid = false;
    r.sameOrigin = false;
    r.portalLocked = true;
    return r;
}

void sameOriginRequiresRealBrowserHeaders() {
    // Exact Origin, either scheme, case-insensitive.
    assert(sameOriginHeaders("10.0.0.50", "http://10.0.0.50", ""));
    assert(sameOriginHeaders("bambuhelper.local", "HTTP://BambuHelper.local", ""));
    assert(sameOriginHeaders("10.0.0.50", "https://10.0.0.50", ""));
    // Referer fallback only when Origin is absent, and only with a path separator.
    assert(sameOriginHeaders("10.0.0.50", "", "http://10.0.0.50/recovery"));
    assert(!sameOriginHeaders("10.0.0.50", "", "http://10.0.0.50.evil.example/"));
    // Foreign, opaque and missing provenance is rejected.
    assert(!sameOriginHeaders("10.0.0.50", "http://evil.example", ""));
    assert(!sameOriginHeaders("10.0.0.50", "null", ""));
    assert(!sameOriginHeaders("10.0.0.50", "http://10.0.0.50:8080", ""));
    assert(!sameOriginHeaders("10.0.0.50", "", ""));
    assert(!sameOriginHeaders("10.0.0.50", nullptr, nullptr));
    assert(!sameOriginHeaders("", "http://10.0.0.50", ""));
    // A present-but-foreign Origin is not rescued by a matching Referer.
    assert(!sameOriginHeaders("10.0.0.50", "http://evil.example", "http://10.0.0.50/"));
    // Oversized Host is rejected rather than truncated.
    assert(!sameOriginHeaders(
        "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        "http://aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        ""));
}

void unauthenticatedStatusIs401() {
    // GET /status without a session must answer 401, never data.
    assert(decidePortalAccess(lan("/status", false)) == PortalAccess::SignInRequired);
    // Same for the other read routes Local AI and capture tooling touch.
    assert(decidePortalAccess(lan("/hardware/health", false)) == PortalAccess::SignInRequired);
    assert(decidePortalAccess(lan("/os12/update/status", false)) == PortalAccess::SignInRequired);
    assert(decidePortalAccess(lan("/hub/frame.ppm", false)) == PortalAccess::SignInRequired);
    assert(decidePortalAccess(lan("/printer/access-code", false)) == PortalAccess::SignInRequired);
    assert(decidePortalAccess(lan("/settings/export", false)) == PortalAccess::SignInRequired);
    assert(decidePortalAccess(lan("/debug", false)) == PortalAccess::SignInRequired);
    // Page navigations go to the sign-in page.
    assert(decidePortalAccess(lan("/", false)) == PortalAccess::SignInRedirect);
    assert(decidePortalAccess(lan("/recovery", false)) == PortalAccess::SignInRedirect);
}

void unauthenticatedControlIsRefused() {
    // A non-browser client that only adds X-BambuHelper-Client: 1 carries no
    // Origin/Referer, so it is not same-origin: 403.
    PortalRequestFacts stop = lan("/printer/control", true);
    assert(decidePortalAccess(stop) == PortalAccess::RejectCrossOrigin);
    // Even a forged, matching Origin is not a credential: 401.
    stop.sameOrigin = true;
    assert(decidePortalAccess(stop) == PortalAccess::SignInRequired);
    // Every other mutation follows the same rule.
    const char* const mutations[] = {"/printer/power", "/power/control", "/light/set", "/hub/show",
                                     "/os12/update/install", "/ota/upload", "/reset", "/reboot",
                                     "/recovery/reset-wifi", "/api/portal-security", "/save/printer"};
    for (const char* uri : mutations) {
        PortalRequestFacts r = lan(uri, true);
        assert(decidePortalAccess(r) == PortalAccess::RejectCrossOrigin);
        r.sameOrigin = true;
        assert(decidePortalAccess(r) == PortalAccess::SignInRequired);
    }
}

void signedInBrowserIsAllowedButStillOriginBound() {
    PortalRequestFacts read = lan("/status", false);
    read.sessionValid = true;
    assert(decidePortalAccess(read) == PortalAccess::Allow);

    PortalRequestFacts stop = lan("/printer/control", true);
    stop.sessionValid = true;
    stop.sameOrigin = false;  // valid cookie, cross-site form post
    assert(decidePortalAccess(stop) == PortalAccess::RejectCrossOrigin);
    stop.sameOrigin = true;
    assert(decidePortalAccess(stop) == PortalAccess::Allow);
}

void openReadSettingIsNarrowAndOptIn() {
    // Locked is the default in PortalRequestFacts.
    PortalRequestFacts defaults;
    assert(defaults.portalLocked);

    PortalRequestFacts status = lan("/status", false);
    status.portalLocked = false;
    assert(decidePortalAccess(status) == PortalAccess::Allow);

    // Never: credentials, capture, settings, diagnostics, Recovery, inventory key.
    const char* const neverOpen[] = {"/printer/access-code", "/printer/config", "/settings/export",
                                     "/hub/frame.ppm", "/hub/views", "/debug", "/recovery",
                                     "/cloud/printers", "/os12/inventory/status", "/power/config",
                                     "/lan/scan", "/api/status/lite", "/status/", "/STATUS"};
    for (const char* uri : neverOpen) {
        assert(!openReadRoute(uri));
        PortalRequestFacts r = lan(uri, false);
        r.portalLocked = false;
        assert(decidePortalAccess(r) != PortalAccess::Allow);
    }

    // Mutations are never opened by the setting.
    PortalRequestFacts stop = lan("/printer/control", true);
    stop.portalLocked = false;
    stop.sameOrigin = true;
    assert(decidePortalAccess(stop) == PortalAccess::SignInRequired);

    // The setting does not apply in AP mode.
    PortalRequestFacts apStatus = lan("/status", false);
    apStatus.portalLocked = false;
    apStatus.apMode = true;
    assert(decidePortalAccess(apStatus) == PortalAccess::SignInRequired);
}

void captiveOnboardingStaysMinimal() {
    PortalRequestFacts r = lan("/", false);
    r.apMode = true;
    assert(decidePortalAccess(r) == PortalAccess::Allow);

    PortalRequestFacts wifi = lan("/save/wifi", true);
    wifi.apMode = true;
    assert(decidePortalAccess(wifi) == PortalAccess::RejectCrossOrigin);
    wifi.sameOrigin = true;
    assert(decidePortalAccess(wifi) == PortalAccess::Allow);

    // AP mode is not an authorization credential.
    const char* const protectedRoutes[] = {"/printer/control", "/printer/power", "/settings/export",
                                           "/debug", "/recovery", "/ota/upload", "/reset", "/status"};
    for (const char* uri : protectedRoutes) {
        PortalRequestFacts p = lan(uri, false);
        p.apMode = true;
        assert(decidePortalAccess(p) != PortalAccess::Allow);
        p.mutating = true;
        p.sameOrigin = true;
        assert(decidePortalAccess(p) == PortalAccess::SignInRequired);
    }
}

void recoverySafeModeStaysIndependent() {
    const char* const rescue[] = {"/recovery", "/recovery/status", "/recovery/touch", "/recovery/rollback",
                                  "/ota/upload", "/reset"};
    for (const char* uri : rescue) {
        PortalRequestFacts r = lan(uri, false);
        r.apMode = true;
        r.recoverySafeMode = true;
        assert(decidePortalAccess(r) == PortalAccess::Allow);
        r.mutating = true;
        assert(decidePortalAccess(r) == PortalAccess::RejectCrossOrigin);
        r.sameOrigin = true;
        assert(decidePortalAccess(r) == PortalAccess::Allow);
    }

    // Unrelated privileged routes stay protected in Recovery Safe Mode.
    const char* const unrelated[] = {"/printer/control", "/printer/power", "/settings/export", "/debug",
                                     "/printer/access-code", "/hub/frame.ppm"};
    for (const char* uri : unrelated) {
        PortalRequestFacts r = lan(uri, true);
        r.apMode = true;
        r.recoverySafeMode = true;
        r.sameOrigin = true;
        assert(decidePortalAccess(r) == PortalAccess::SignInRequired);
    }

    // On normal LAN the recovery page and its actions need the session.
    assert(decidePortalAccess(lan("/recovery", false)) == PortalAccess::SignInRedirect);
    PortalRequestFacts lanRollback = lan("/recovery/rollback", true);
    lanRollback.sameOrigin = true;
    assert(decidePortalAccess(lanRollback) == PortalAccess::SignInRequired);
    lanRollback.sessionValid = true;
    assert(decidePortalAccess(lanRollback) == PortalAccess::Allow);
}

void nullUriFailsClosed() {
    PortalRequestFacts r = lan(nullptr, false);
    assert(decidePortalAccess(r) == PortalAccess::SignInRequired);
    r.apMode = true;
    assert(decidePortalAccess(r) == PortalAccess::SignInRequired);
}

}  // namespace

int main() {
    sameOriginRequiresRealBrowserHeaders();
    unauthenticatedStatusIs401();
    unauthenticatedControlIsRefused();
    signedInBrowserIsAllowedButStillOriginBound();
    openReadSettingIsNarrowAndOptIn();
    captiveOnboardingStaysMinimal();
    recoverySafeModeStaysIndependent();
    nullUriFailsClosed();
    return 0;
}
