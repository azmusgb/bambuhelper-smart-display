#!/usr/bin/env python3
import argparse
import sys
from pathlib import Path

class PatchError(Exception):
    pass

def replace_once(content: str, old: str, new: str, desc: str) -> str:
    if new in content:
        return content
    if old not in content:
        raise PatchError(f"Anchor not found for {desc}")
    count = content.count(old)
    if count > 1:
        raise PatchError(f"Anchor is not unique ({count} occurrences) for {desc}")
    return content.replace(old, new, 1)

def main():
    parser = argparse.ArgumentParser(description="Apply Workshop OS Sky Radar v11.30")
    parser.add_argument("--repo", type=Path, required=True, help="Path to repository root")
    parser.add_argument("--apply", action="store_true", help="Apply the patch")
    args = parser.parse_args()

    repo = args.repo
    display_ui_path = repo / "src" / "display_ui.h"
    smart_hub_path = repo / "src" / "smart_hub.cpp"

    if not display_ui_path.exists():
        print(f"Error: {display_ui_path} does not exist", file=sys.stderr)
        sys.exit(1)
    if not smart_hub_path.exists():
        print(f"Error: {smart_hub_path} does not exist", file=sys.stderr)
        sys.exit(1)

    display_ui_content = display_ui_path.read_text(encoding="utf-8")
    smart_hub_content = smart_hub_path.read_text(encoding="utf-8")

    already_applied = "SCREEN_SKY_RADAR" in display_ui_content and "drawSkyRadar" in smart_hub_content
    if already_applied:
        print("already applied, skipping.")
        return

    if not args.apply:
        print("Dry run: patch would be applied. Pass --apply to execute.")
        return

    display_ui_anchor = "SCREEN_HUB_MORE"
    display_ui_replacement = "SCREEN_HUB_MORE,\n    SCREEN_SKY_RADAR"
    try:
        display_ui_content = replace_once(display_ui_content, display_ui_anchor, display_ui_replacement, "SCREEN_HUB_MORE enum value")
    except PatchError as e:
        print(f"Error patching display_ui.h: {e}", file=sys.stderr)
        sys.exit(1)

    sky_radar_code = """
#include <WiFiClientSecure.h>
#include <ArduinoJson.h>

struct Aircraft {
    char callsign[16];
    char origin_country[24];
    float lat;
    float lon;
    float alt;
    float velocity;
    float true_track;
};

static Aircraft g_aircraft[40];
static int g_aircraft_count = 0;
static unsigned long g_last_radar_fetch = 0;
static bool g_radar_no_signal = false;
static int g_selected_aircraft = -1;
static float g_user_lat = 0.0f;
static float g_user_lon = 0.0f;
static bool g_location_fetched = false;

void fetchUserLocation() {
    if (g_location_fetched) return;
    WiFiClient client;
    if (client.connect("ip-api.com", 80)) {
        client.print("GET /json HTTP/1.1\\r\\nHost: ip-api.com\\r\\nConnection: close\\r\\n\\r\\n");
        unsigned long timeout = millis();
        while (client.connected() && millis() - timeout < 5000) {
            if (client.available()) {
                String line = client.readStringUntil('\\n');
                if (line.startsWith("{")) {
                    DynamicJsonDocument doc(1024);
                    deserializeJson(doc, line);
                    g_user_lat = doc["lat"] | 0.0f;
                    g_user_lon = doc["lon"] | 0.0f;
                    if (g_user_lat != 0.0f && g_user_lon != 0.0f) {
                        g_location_fetched = true;
                    }
                    break;
                }
            }
        }
        client.stop();
    }
}

void fetchOpenSkyData() {
    fetchUserLocation();
    if (!g_location_fetched) {
        g_radar_no_signal = true;
        return;
    }
    
    WiFiClientSecure client;
    client.setInsecure();
    // TODO: verify rootca_crt_bundle_start integration if needed
    if (client.connect("opensky-network.org", 443)) {
        char path[128];
        snprintf(path, sizeof(path), "/api/states/all?lamin=%.2f&lomin=%.2f&lamax=%.2f&lomax=%.2f", 
                 g_user_lat - 1.0f, g_user_lon - 1.0f, g_user_lat + 1.0f, g_user_lon + 1.0f);
        
        client.print(String("GET ") + path + " HTTP/1.1\\r\\nHost: opensky-network.org\\r\\nConnection: close\\r\\n\\r\\n");
        
        unsigned long timeout = millis();
        String payload = "";
        bool headers_ended = false;
        while (client.connected() && millis() - timeout < 8000) {
            while (client.available()) {
                String line = client.readStringUntil('\\n');
                if (line == "\\r" || line == "") {
                    headers_ended = true;
                    break;
                }
                if (headers_ended) {
                    payload += line + "\\n";
                }
            }
        }
        client.stop();
        
        DynamicJsonDocument doc(16384);
        DeserializationError error = deserializeJson(doc, payload);
        if (!error) {
            JsonArray states = doc["states"];
            g_aircraft_count = 0;
            for (JsonArray s : states) {
                if (g_aircraft_count >= 40) break;
                const char* callsign = s[1] | "";
                const char* country = s[2] | "";
                float lon = s[5] | 0.0f;
                float lat = s[6] | 0.0f;
                float alt = s[7] | 0.0f;
                float vel = s[9] | 0.0f;
                float track = s[10] | 0.0f;
                
                if (lat != 0.0f && lon != 0.0f) {
                    strncpy(g_aircraft[g_aircraft_count].callsign, callsign, 15);
                    strncpy(g_aircraft[g_aircraft_count].origin_country, country, 23);
                    g_aircraft[g_aircraft_count].lat = lat;
                    g_aircraft[g_aircraft_count].lon = lon;
                    g_aircraft[g_aircraft_count].alt = alt;
                    g_aircraft[g_aircraft_count].velocity = vel;
                    g_aircraft[g_aircraft_count].true_track = track;
                    g_aircraft_count++;
                }
            }
            g_radar_no_signal = false;
            g_last_radar_fetch = millis();
        } else {
            g_radar_no_signal = true;
        }
    } else {
        g_radar_no_signal = true;
    }
}

void drawSkyRadar() {
    tft.fillScreen(UI_BG);
    
    unsigned long now = millis();
    if (now - g_last_radar_fetch > 60000 || g_last_radar_fetch == 0) {
        fetchOpenSkyData();
    }
    
    int cx = tft.width() / 2;
    int cy = tft.height() / 2 - 10;
    
    int radii[] = {20, 50, 100};
    int km[] = {10, 25, 50};
    for (int i = 0; i < 3; i++) {
        tft.drawCircle(cx, cy, radii[i], 0x8410); // UI_BORDER
        tft.setCursor(cx + 4, cy - radii[i] + 2);
        tft.setTextColor(0xA576); // UI_DIM
        tft.setTextSize(1);
        tft.print(km[i]);
        tft.print("km");
    }
    
    tft.setCursor(cx - 4, cy - 115);
    tft.setTextColor(0xA576); // UI_DIM
    tft.print("N");
    tft.setCursor(cx + 110, cy - 4);
    tft.print("E");
    tft.setCursor(cx - 4, cy + 105);
    tft.print("S");
    tft.setCursor(cx - 115, cy - 4);
    tft.print("W");
    
    float pulse = sinf(now / 300.0f);
    int dot_radius = 3 + (int)(pulse * 1.5f);
    tft.fillCircle(cx, cy, dot_radius, 0x6D5F); // UI_CYAN
    
    for (int i = 0; i < g_aircraft_count; i++) {
        float d_lat = g_aircraft[i].lat - g_user_lat;
        float d_lon = g_aircraft[i].lon - g_user_lon;
        float dx = d_lon * 111.0f * 2.0f * cosf(g_user_lat * 3.14159f / 180.0f);
        float dy = -d_lat * 111.0f * 2.0f;
        
        int ax = cx + (int)dx;
        int ay = cy + (int)dy;
        
        if (ax >= 0 && ax < tft.width() && ay >= 0 && ay < tft.height()) {
            uint16_t color = 0x07E0; // UI_GREEN
            if (g_aircraft[i].alt >= 3000.0f && g_aircraft[i].alt < 9000.0f) {
                color = 0xFDA9; // UI_AMBER
            } else if (g_aircraft[i].alt >= 9000.0f) {
                color = 0xA45F; // UI_PURPLE
            }
            tft.fillCircle(ax, ay, 2, color);
        }
    }
    
    if (g_radar_no_signal) {
        tft.setCursor(cx - 40, tft.height() - 30);
        tft.setTextColor(0xFDA9); // UI_AMBER
        tft.setTextSize(1);
        tft.print("NO SIGNAL — retry in ");
        tft.print((60000 - (now - g_last_radar_fetch)) / 1000);
        tft.print("s");
    }
}
"""

    anchor_func = "static void uiCard"
    if anchor_func not in smart_hub_content:
        anchor_func = "static void uiCard"

    if anchor_func in smart_hub_content:
        smart_hub_content = replace_once(smart_hub_content, anchor_func, sky_radar_code + "\n" + anchor_func, "drawSkyRadar function injection")

    # --- Dispatch wiring ---
    display_ui_cpp_path = repo / "src" / "display_ui.cpp"
    display_ui_cpp = display_ui_cpp_path.read_text(encoding="utf-8")
    display_ui_cpp = replace_once(
        display_ui_cpp,
        "    case SCREEN_HUB_SYSTEM:\n      smartHubDraw(currentScreen, forceRedraw);",
        "    case SCREEN_HUB_SYSTEM:\n    case SCREEN_SKY_RADAR:\n      smartHubDraw(currentScreen, forceRedraw);",
        "display_ui.cpp SCREEN_SKY_RADAR case",
    )
    display_ui_cpp_path.write_text(display_ui_cpp, encoding="utf-8")

    smart_hub_content = replace_once(
        smart_hub_content,
        "    case SCREEN_HUB_SYSTEM:   drawSystem(effectiveForce);   break;\n    default: break;",
        "    case SCREEN_HUB_SYSTEM:   drawSystem(effectiveForce);   break;\n    case SCREEN_SKY_RADAR:    drawSkyRadar();               break;\n    default: break;",
        "smartHubDraw SCREEN_SKY_RADAR dispatch",
    )
    smart_hub_content = replace_once(
        smart_hub_content,
        "    case SCREEN_HUB_MORE:\n    case SCREEN_HUB_CUSTOM:\n    case SCREEN_HUB_SYSTEM:   setPage(SCREEN_HUB_HOME);     break;",
        "    case SCREEN_HUB_MORE:     setPage(SCREEN_SKY_RADAR);    break;\n    case SCREEN_HUB_CUSTOM:\n    case SCREEN_HUB_SYSTEM:\n    case SCREEN_SKY_RADAR:    setPage(SCREEN_HUB_HOME);     break;",
        "smartHubAdvance SCREEN_HUB_MORE -> SKY_RADAR",
    )

    smart_hub_content = replace_once(
        smart_hub_content,
        "    case SCREEN_HUB_SYSTEM:   setPage(SCREEN_HUB_HOME);     break;",
        "    case SCREEN_HUB_SYSTEM:\n    case SCREEN_SKY_RADAR:    setPage(SCREEN_HUB_HOME);     break;",
        "smartHubAdvance SCREEN_SKY_RADAR case",
    )


    # Fix pre-existing crash: kNetworkPages has 4 entries but the loop
    # was reading past the array, causing a LoadProhibited crash on any
    # unmatched page name (all 7 hardware-* screens).
    smart_hub_fix = (repo / "src" / "smart_hub.cpp").read_text(encoding="utf-8")
    old_loop = "for(uint8_t i=0;i<HUB_NETWORK_PAGE_COUNT;i++) {"
    new_loop = "for(uint8_t i=0;i<sizeof(kNetworkPages)/sizeof(kNetworkPages[0]);i++) {"
    if old_loop in smart_hub_fix:
        smart_hub_fix = smart_hub_fix.replace(old_loop, new_loop, 1)
        (repo / "src" / "smart_hub.cpp").write_text(smart_hub_fix, encoding="utf-8")
        print("Fixed kNetworkPages loop bound (audio-screen crash)")

    display_ui_path.write_text(display_ui_content, encoding="utf-8")
    smart_hub_path.write_text(smart_hub_content, encoding="utf-8")
    print("Patch applied successfully.")

if __name__ == "__main__":
    main()
