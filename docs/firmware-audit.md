# Firmware Security Audit

Date: 2026-09-25
Scope: upstream/src/web_server.cpp, upstream/src/web_template.cpp, upstream/src/smart_hub.cpp, upstream/src/bambu_mqtt.cpp

## Findings

### ✅ String handling
Zero uses of strcpy, strcat, sprintf, gets, or scanf. Fixed-size buffers exist but are populated via snprintf/strncpy with size limits.

### ✅ Recovery route authentication
Every POST handler for /recovery/* begins with `if(!recoveryMutationAllowed())return;`. Verified via grep at lines 3005-3011. The recovery page itself uses SECURE_GET.

### ✅ OTA task pointer transfer
web_server.cpp:2575 `String* urlHeap = new String(url)` transfers ownership to otaAutoTaskFn via xTaskCreatePinnedToCore. Standard FreeRTOS pattern; not a leak.

### ✅ MQTT JSON parsing
All 6 deserializeJson calls in bambu_mqtt.cpp are error-checked (either assigned to DeserializationError or wrapped in if(!...)).

## Remaining checks
- [ ] Audit the 11 other deserializeJson calls across other .cpp files
- [ ] Verify otaAutoTaskFn frees its String* parameter
