#!/usr/bin/env python3
"""Add persistent location caching to Sky Radar's fetchUserLocation()."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from scripts.smart_home_patch_utils import PatchError, fail, replace_once, replace_braced_block


NEW_FN = '''#include <Preferences.h>

Preferences g_radarPrefs;

void fetchUserLocation() {
    if (g_location_fetched) return;
    Serial.println("[radar] fetch started");

    g_radarPrefs.begin("radar", false);
    float cached_lat = g_radarPrefs.getFloat("lat", 0.0f);
    float cached_lon = g_radarPrefs.getFloat("lon", 0.0f);
    if (cached_lat != 0.0f && cached_lon != 0.0f) {
        g_user_lat = cached_lat;
        g_user_lon = cached_lon;
        g_location_fetched = true;
        g_radar_no_signal = false;
        g_radarPrefs.end();
        Serial.print("[radar] location from cache ");
        Serial.print(g_user_lat, 4);
        Serial.print(",");
        Serial.println(g_user_lon, 4);
        return;
    }
    g_radarPrefs.end();

    Serial.println("[radar] connecting ip-api.com:80");
    WiFiClient client;
    client.setTimeout(5000);
    if (!client.connect("ip-api.com", 80)) {
        Serial.println("[radar] ip-api.com connect FAILED");
        g_last_radar_fetch = millis();
        return;
    }
    Serial.println("[radar] ip-api.com connected");
    client.print("GET /json HTTP/1.1\\r\\nHost: ip-api.com\\r\\nConnection: close\\r\\n\\r\\n");
    String body = client.readString();
    client.stop();

    Serial.print("[radar] body len=");
    Serial.println(body.length());

    int brace = body.indexOf('{');
    if (brace < 0) {
        Serial.println("[radar] no JSON in body");
        g_last_radar_fetch = millis();
        return;
    }
    body = body.substring(brace);

    DynamicJsonDocument doc(1024);
    DeserializationError error = deserializeJson(doc, body);
    if (error) {
        Serial.print("[radar] json parse failed: ");
        Serial.println(error.c_str());
        g_last_radar_fetch = millis();
        return;
    }

    g_user_lat = doc["lat"] | 0.0f;
    g_user_lon = doc["lon"] | 0.0f;
    if (g_user_lat != 0.0f && g_user_lon != 0.0f) {
        g_location_fetched = true;
        g_radar_no_signal = false;
        g_radarPrefs.begin("radar", false);
        g_radarPrefs.putFloat("lat", g_user_lat);
        g_radarPrefs.putFloat("lon", g_user_lon);
        g_radarPrefs.end();
        Serial.print("[radar] location OK ");
        Serial.print(g_user_lat, 4);
        Serial.print(",");
        Serial.println(g_user_lon, 4);
    } else {
        Serial.println("[radar] location returned 0,0");
        g_last_radar_fetch = millis();
    }
}
'''


def apply(repo: Path) -> None:
    hub = repo / "src" / "smart_hub.cpp"
    if not hub.is_file():
        raise PatchError(f"smart_hub.cpp not found at {hub}")
    src = hub.read_text(encoding="utf-8")

    if "g_radarPrefs" in src and "location from cache" in src:
        print("already applied, skipping.")
        return

    anchor = "void fetchUserLocation() {"
    if anchor not in src:
        raise PatchError("fetchUserLocation not found — apply the Sky Radar patch first")

    src = replace_braced_block(src, anchor, NEW_FN.rstrip("\n"), "fetchUserLocation cache")
    hub.write_text(src, encoding="utf-8")
    print("Applied persistent location caching to Sky Radar")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    if not args.apply:
        raise SystemExit("refusing to modify source without --apply")
    try:
        apply(Path(args.repo).resolve())
    except PatchError as exc:
        raise SystemExit(str(exc)) from exc
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
