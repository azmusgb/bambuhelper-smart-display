#pragma once

#include <Arduino.h>

class WebServer;

// Smart Home v8.3 RC3 portal protection.
// AP/captive-portal onboarding remains open. In normal station mode the user
// enters the short-lived on-device portal code once, then uses a RAM-only
// session cookie. This avoids browser Digest nonce churn and repeated prompts.
void securityInit();
const char* securityUsername();
const char* securityPortalCode();
bool securitySessionValid(WebServer& server);
bool securityLogin(WebServer& server, const String& submittedCode);
void securityLogout(WebServer& server);
bool securityAuthorize(WebServer& server, bool mutating);
