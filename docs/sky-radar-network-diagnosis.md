# Sky Radar: Network Fetch Diagnosis

## Symptom
Radar renders correctly. Bottom shows "NO SIGNAL" — no aircraft load.

## Trace (serial monitor)
[radar] fetch started
[radar] connecting ip-api.com:80
[radar] ip-api.com connected
[radar] ip-api.com FAILED

DNS resolves. TCP connects. Body parse fails.

## Root cause
fetchUserLocation() uses raw WiFiClient + readStringUntil('\n'),
which has a 1000ms default timeout and returns partial lines when
TCP fragments arrive between header and body. Truncated JSON fails
deserializeJson -> returns lat=lon=0 -> NO SIGNAL.

## Fix to implement
Replace with ESP32 HTTPClient:
  HTTPClient http;
  http.setTimeout(5000);
  http.begin("http://ip-api.com/json");
  int code = http.GET();
  String body = http.getString();
  deserializeJson(doc, body);

Must be hand-edited, not regex-substituted — the previous attempt
broke a string literal at lines 720-738 in smart_hub.cpp.

## Retry counter bug
Shows 4294300s because g_last_radar_fetch stays 0 on failure and
60000 - now underflows to unsigned. Fix: set g_last_radar_fetch =
millis() on every failure path, and clamp to [0, 60] in draw code.


## Attempted fix #1: HTTPClient (FAILED)

Replaced fetchUserLocation() with ESP32 HTTPClient. Result: compile
OK, flash OK, then immediate `Guru Meditation Error: LoadProhibited`
with EXCVADDR=0x0f0a0501 - a wild pointer dereference. Device
boot-looped.

Cause unknown. Likely HTTPClient + already-running WebServer conflict
on the same WiFi stack, or ArduinoJson 7 heap allocation in a
fragmented heap. Do not retry without deeper investigation.

## Safer alternatives to try next session

1. Bump the WiFiClient timeout (3-line change):
   WiFiClient client;
   client.setTimeout(5000);   // was effectively 1000ms

2. Read whole body, then parse (avoids per-line reads):
   String body = client.readString();
   int brace = body.indexOf('{');
   if (brace >= 0) body = body.substring(brace);
   deserializeJson(doc, body);

3. Cache location in settings - fetch once, persist, skip on later
   boots. Even a broken fetch only needs to work once.
