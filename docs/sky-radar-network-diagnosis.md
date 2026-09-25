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
