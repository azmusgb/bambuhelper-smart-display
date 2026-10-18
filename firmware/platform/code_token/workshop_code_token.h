#pragma once

// Workshop OS sign-in code key (device glue).
//
// A second device-issued key, separate from the read-only status token.
// GET /api/portal-code answers the current Local Portal sign-in code only to a
// client presenting this key ("wsc_..."). The key is created from the
// signed-in Local Portal, must be approved by a tap on "Allow" on the
// touchscreen, is shown once, and only its SHA-256 digest is stored (NVS
// namespace "workshop-sec", key "code_sha"). Creating a new key replaces
// (revokes) the previous one. No other route accepts it, and the status token
// does not open /api/portal-code.

#include <Arduino.h>

class WebServer;

// Key-checked, rate-limited read of the sign-in code. Registered with plain
// server.on(); never wrap it in SECURE_GET.
void workshopPortalCodeHandleRead(WebServer& server);

// Management. Register only behind SECURE_GET / SECURE_POST (session + same-origin).
void workshopCodeTokenHandleState(WebServer& server);
void workshopCodeTokenHandleCreate(WebServer& server);
void workshopCodeTokenHandleClaim(WebServer& server);
void workshopCodeTokenHandleRevoke(WebServer& server);

// Touchscreen consent prompt.
bool workshopCodeTokenPromptVisible();
uint32_t workshopCodeTokenPromptSecondsLeft();
bool workshopCodeTokenAllow();
void workshopCodeTokenDeny();

// Local Portal page: is a key set up? (Never the key itself.)
bool workshopCodeTokenConfigured();

// Factory reset clears the stored digest.
void workshopCodeTokenFactoryReset();
