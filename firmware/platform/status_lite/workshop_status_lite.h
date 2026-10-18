#pragma once

// Workshop OS read-only status token (device glue).
//
// GET /api/status/lite is answered only to a client presenting the current
// device-issued bearer token. The token is created from the signed-in Local
// Portal, must be approved by a tap on "Allow" on the touchscreen, is shown
// once, and only its SHA-256 digest is stored (NVS namespace "workshop-sec").
// Creating a new token replaces (revokes) the previous one. The token is not
// accepted by securityAuthorize() or any other route.

#include <Arduino.h>

class WebServer;

// Token-checked, rate-limited, read-only summary. Registered with plain
// server.on(); never wrap it in SECURE_GET.
void workshopStatusLiteHandleRead(WebServer& server);

// Management. Register only behind SECURE_GET / SECURE_POST (session + same-origin).
void workshopStatusTokenHandleState(WebServer& server);
void workshopStatusTokenHandleCreate(WebServer& server);
void workshopStatusTokenHandleClaim(WebServer& server);
void workshopStatusTokenHandleRevoke(WebServer& server);

// Touchscreen consent prompt.
bool workshopStatusTokenPromptVisible();
uint32_t workshopStatusTokenPromptSecondsLeft();
bool workshopStatusTokenAllow();
void workshopStatusTokenDeny();

// Factory reset clears the stored digest.
void workshopStatusTokenFactoryReset();
