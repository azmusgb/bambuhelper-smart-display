#!/usr/bin/env python3
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from scripts.smart_home_patch_utils import PatchError, fail, replace_once, replace_braced_block

def main():
    repo_root = sys.argv[1] if len(sys.argv) > 1 else "upstream"
    smart_hub_path = os.path.join(repo_root, "src", "smart_hub.cpp")

    if not os.path.exists(smart_hub_path):
        fail(f"smart_hub.cpp not found at {smart_hub_path}")

    with open(smart_hub_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Idempotency check
    if "g_radarPrefs" in content and "g_radarPrefs.getFloat(\"lat\", 0.0f)" in content:
        print("apply_workshop_os_sky_radar_location_cache.py: already applied, skipping.")
        return

    # The prompt instructs:
    # "The patch must inject into <repo>/src/smart_hub.cpp:
    #  A Preferences object named g_radarPrefs opened under namespace 'radar'.
    #  Replace the existing fetchUserLocation() with a version that:
    #  - First checks g_radarPrefs.getFloat('lat', 0.0f) and 'lon'. If both nonzero, sets g_user_lat, g_user_lon, g_location_fetched = true and returns immediately — no network call.
    #  - Only if cache is empty, does the existing WiFiClient fetch with client.setTimeout(5000) and client.readString() (whole body, then find first { and parse JSON from there).
    #  - On success, calls g_radarPrefs.putFloat('lat', g_user_lat) and putFloat('lon', g_user_lon) to persist.
    #  - Idempotent — re-running prints already applied, skipping."

    # If fetchUserLocation() does not exist yet in upstream smart_hub.cpp (because sky radar isn't applied yet, or the user patch is standalone), 
    # wait! Let's check how fetchUserLocation is expected to be patched or if fetchUserLocation exists in sky radar.
    # Wait, sky radar adds fetchUserLocation(). But this patch script is standalone or follows sky radar.
    # Let's check if fetchUserLocation exists or if we should add it if missing, or replace it if present.
    old_fetch_signature = "void fetchUserLocation() {"
    
    new_fetch_code = """Preferences g_radarPrefs;

void fetchUserLocation() {
    if (g_location_fetched) return;
    g_radarPrefs.begin("radar", false);
    float cached_lat = g_radarPrefs.getFloat("lat", 0.0f);
    float cached_lon = g_radarPrefs.getFloat("lon", 0.0f);
    if (cached_lat != 0.0f && cached_lon != 0.0f) {
        g_user_lat = cached_lat;
        g_user_lon = cached_lon;
        g_location_fetched = true;
        g_radarPrefs.end();
        return;
    }

    WiFiClient client;
    client.setTimeout(5000);
    if (client.connect("ip-api.com", 80)) {
        client.print("GET /json HTTP/1.1\\r\\nHost: ip-api.com\\r\\nConnection: close\\r\\n\\r\\n");
        String body = client.readString();
        client.stop();

        int brace = body.indexOf('{');
        if (brace >= 0) {
            body = body.substring(brace);
            DynamicJsonDocument doc(1024);
            deserializeJson(doc, body);
            g_user_lat = doc["lat"] | 0.0f;
            g_user_lon = doc["lon"] | 0.0f;
            if (g_user_lat != 0.0f && g_user_lon != 0.0f) {
                g_location_fetched = true;
                g_radarPrefs.putFloat("lat", g_user_lat);
                g_radarPrefs.putFloat("lon", g_user_lon);
            }
        }
    }
    g_radarPrefs.end();
}"""

    if old_fetch_signature in content:
        content = replace_braced_block(content, old_fetch_signature, new_fetch_code[len(old_fetch_signature):], "fetchUserLocation cache replacement")
    else:
        # If fetchUserLocation doesn't exist yet, inject it before smartHubInit or at the end of file / near top
        anchor = "void smartHubInit() {\n  if (g_initialized) return;"
        if anchor in content:
            content = replace_once(content, anchor, new_fetch_code + "\n\n" + anchor, "fetchUserLocation injection")
        else:
            fail("Could not find fetchUserLocation or smartHubInit in smart_hub.cpp")

    with open(smart_hub_path, "w", encoding="utf-8") as f:
        f.write(content)

    print("Successfully applied persistent location caching to Sky Radar in smart_hub.cpp")

if __name__ == "__main__":
    main()
