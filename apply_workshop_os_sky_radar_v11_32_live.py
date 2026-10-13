void fetchUserLocation() {
    if (g_location_fetched) return;
    // Skip ip-api.com — hardcode Amsterdam. Change these two values
    // if you move. Getting the network fetch working is the priority.
    g_user_lat = 52.3676f;
    g_user_lon = 4.9041f;
    g_location_fetched = true;
    Serial.println("[radar] using hardcoded Amsterdam coords");
}

void fetchOpenSkyData() {
    if (!g_location_fetched) fetchUserLocation();

    Serial.println("[radar] fetch started");
    WiFiClientSecure client;
    client.setTimeout(10000);
    client.setInsecure();

    if (!client.connect("opensky-network.org", 443)) {
        Serial.println("[radar] OpenSky connect FAILED");
        g_radar_no_signal = true;
        g_last_radar_fetch = millis();
        return;
    }
    Serial.println("[radar] OpenSky connected");

    char path[160];
    snprintf(path, sizeof(path),
        "/api/states/all?lamin=%.3f&lomin=%.3f&lamax=%.3f&lomax=%.3f",
        g_user_lat - 1.0f, g_user_lon - 1.0f,
        g_user_lat + 1.0f, g_user_lon + 1.0f);
    Serial.print("[radar] GET ");
    Serial.println(path);

    client.print("GET ");
    client.print(path);
    client.print(" HTTP/1.1\r\n");
    client.print("Host: opensky-network.org\r\n");
    client.print("User-Agent: BambuHelper/1.0\r\n");
    client.print("Connection: close\r\n\r\n");

    String body = client.readString();
    client.stop();

    Serial.print("[radar] body len=");
    Serial.println(body.length());

    int brace = body.indexOf('{');
    if (brace < 0) {
        Serial.println("[radar] no JSON brace found");
        g_radar_no_signal = true;
        g_last_radar_fetch = millis();
        return;
    }
    body = body.substring(brace);

    DynamicJsonDocument doc(16384);
    DeserializationError err = deserializeJson(doc, body);
    if (err) {
        Serial.print("[radar] JSON parse error: ");
        Serial.println(err.c_str());
        g_radar_no_signal = true;
        g_last_radar_fetch = millis();
        return;
    }

    JsonArray states = doc["states"];
    g_aircraft_count = 0;
    for (JsonArray s : states) {
        if (g_aircraft_count >= 40) break;
        const char* callsign = s[1] | "";
        const char* country  = s[2] | "";
        float lon   = s[5] | 0.0f;
        float lat   = s[6] | 0.0f;
        float alt   = s[7] | 0.0f;
        float vel   = s[9] | 0.0f;
        float track = s[10] | 0.0f;
        if (lat != 0.0f && lon != 0.0f) {
            strncpy(g_aircraft[g_aircraft_count].callsign, callsign, 15);
            g_aircraft[g_aircraft_count].callsign[15] = 0;
            strncpy(g_aircraft[g_aircraft_count].origin_country, country, 23);
            g_aircraft[g_aircraft_count].origin_country[23] = 0;
            g_aircraft[g_aircraft_count].lat = lat;
            g_aircraft[g_aircraft_count].lon = lon;
            g_aircraft[g_aircraft_count].alt = alt;
            g_aircraft[g_aircraft_count].velocity = vel;
            g_aircraft[g_aircraft_count].true_track = track;
            g_aircraft_count++;
        }
    }

    Serial.print("[radar] aircraft count=");
    Serial.println(g_aircraft_count);

    g_radar_no_signal = (g_aircraft_count == 0);
    g_last_radar_fetch = millis();
}
