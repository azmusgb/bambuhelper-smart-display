#include "security_manager.h"
#include "smart_home_build.h"
#include "workshop_http_body_limit.hpp"
#include "recovery_manager.h"
#include "button.h"
#include "buzzer.h"
#include "buzzer_backend.h"
#include "smart_hub.h"
#include "display_ui.h"
#include "tasmota.h"
#include "led.h"

#include "settings.h"
#include "timezones.h"
#include "bambu_state.h"
#include "bambu_mqtt.h"
#include "fonts.h"
#include "config.h"

#include <Preferences.h>
#include <WiFi.h>
#include <HTTPClient.h>
#include <WiFiClient.h>
#include <WiFiClientSecure.h>
#include <ArduinoJson.h>
#include <time.h>
#include <math.h>
#include <new>
#include <ctype.h>

#if defined(BOARD_IS_WS350)

namespace {

static const char* HUB_NVS = "smart-hub";
static const uint16_t HUB_REFRESH_MIN = 30;
static const uint16_t HUB_REFRESH_MAX = 900;
static const uint16_t HUB_RETURN_MAX = 900;
static const uint32_t HUB_HTTP_LIMIT = 4096;

struct HubMetric {
  char label[18];
  char value[28];
};

struct HubCustomData {
  char title[36];
  char subtitle[56];
  char status[36];
  char footer[56];
  HubMetric metrics[4];
  uint8_t metricCount;
  bool valid;
  bool healthy;
  int httpCode;
  char message[64];
  unsigned long fetchedAtMs;
};

SmartHubConfig g_cfg = {
  true,
  60,
  60,
  ""
};

HubCustomData g_custom = {};
bool g_initialized = false;
bool g_dirty = true;
unsigned long g_lastFetchAttemptMs = 0;
unsigned long g_userHoldUntilMs = 0;

// v11.1 Calm Workshop preferences. Kept in the existing smart-hub NVS
// namespace so the browser and physical appliance stay in sync.
uint8_t g_experienceAccent = 0; // 0 ember, 1 cyan, 2 blue, 3 purple, 4 green
bool g_ambientEnabled = true;
bool g_ambientActive = false;
char g_workshopNote[64] = {0};
uint16_t g_timerPresetMinutes = 10; // v11.1 compatibility alias for preset 1
uint16_t g_timerPresets[4] = {5, 15, 30, 60};
uint16_t g_workshopTimerStartedMinutes = 0;
unsigned long g_workshopTimerEndMs = 0;
bool g_workshopTimerDone = false;
uint32_t g_workshopTimerLastSecond = 0xFFFFFFFFUL;
bool g_toolsView = false;
uint8_t g_ui12SettingsView = 0; // 0 root, 1 experience, 2 printer connection, 3 software update
uint8_t g_ui12SystemView = 0; // 0 system root, 1 deliberate Local Portal access
uint8_t g_printerMode = 0; // STATUS / AMS / CONTROL
bool g_displayExperienceView = false;
uint8_t g_displayExperiencePage = 0;
uint8_t g_displayGaugeColorIndex = 0;
static const uint8_t HUB_DISPLAY_PAGE_COUNT = 14;
bool g_networkSettingsView = false;
// ---------------------------------------------------------------------------
// Smart Home v11.23 physical Network / Locale / Layout Expert controls
// ---------------------------------------------------------------------------
static const uint8_t HUB_NETWORK_PAGE_COUNT = 7;
uint8_t g_networkSettingsPage = 0;
bool g_networkEditLoaded = false;
bool g_networkEditDhcp = true;
uint8_t g_networkEditField = 0;
uint8_t g_networkEditOctet = 0;
uint8_t g_networkEditValues[4][4] = {{0}};

static bool hubIpv4AllZero(const uint8_t v[4]) {
  return v[0] == 0 && v[1] == 0 && v[2] == 0 && v[3] == 0;
}

static bool hubParseIpv4(const char* text, uint8_t out[4]) {
  if (!text || !text[0]) return false;
  unsigned a=0,b=0,c=0,d=0; char tail=0;
  if (sscanf(text, "%u.%u.%u.%u%c", &a,&b,&c,&d,&tail) != 4) return false;
  if (a>255 || b>255 || c>255 || d>255) return false;
  out[0]=(uint8_t)a; out[1]=(uint8_t)b; out[2]=(uint8_t)c; out[3]=(uint8_t)d;
  return true;
}

static void hubIpv4FromAddress(const IPAddress& ip, uint8_t out[4]) {
  for (uint8_t i=0;i<4;i++) out[i]=ip[i];
}

static void hubFormatIpv4(const uint8_t v[4], char* out, size_t len) {
  snprintf(out,len,"%u.%u.%u.%u",v[0],v[1],v[2],v[3]);
}

static void hubLoadNetworkEdit() {
  g_networkEditDhcp = netSettings.useDHCP;
  const char* stored[4] = {netSettings.staticIP,netSettings.gateway,netSettings.subnet,netSettings.dns};
  for(uint8_t i=0;i<4;i++) {
    if(hubParseIpv4(stored[i],g_networkEditValues[i])) continue;
    if(WiFi.status()==WL_CONNECTED) {
      if(i==0) hubIpv4FromAddress(WiFi.localIP(),g_networkEditValues[i]);
      else if(i==1) hubIpv4FromAddress(WiFi.gatewayIP(),g_networkEditValues[i]);
      else if(i==2) hubIpv4FromAddress(WiFi.subnetMask(),g_networkEditValues[i]);
      else hubIpv4FromAddress(WiFi.dnsIP(),g_networkEditValues[i]);
    } else memset(g_networkEditValues[i],0,4);
  }
  g_networkEditField=0;
  g_networkEditOctet=0;
  g_networkEditLoaded=true;
}

static const char* hubNetworkFieldLabel(uint8_t field) {
  static const char* labels[] = {"IP ADDRESS","GATEWAY","SUBNET","DNS"};
  return labels[field%4U];
}

static const char* hubTimezoneLabel() {
  size_t count=0;
  const TimezoneRegion* regions=getSupportedTimezones(&count);
  if(!regions || count==0) return "UNAVAILABLE";
  const uint8_t idx=resolveTimezoneIndex(netSettings.timezoneStr);
  return regions[idx<count?idx:0].name;
}

static void hubStepTimezone(bool reverse) {
  size_t count=0;
  const TimezoneRegion* regions=getSupportedTimezones(&count);
  if(!regions || count==0) return;
  uint16_t idx=resolveTimezoneIndex(netSettings.timezoneStr);
  idx=reverse?(uint16_t)((idx+count-1U)%count):(uint16_t)((idx+1U)%count);
  netSettings.timezoneIndex=(uint8_t)idx;
  strlcpy(netSettings.timezoneStr,regions[idx].posixString,sizeof(netSettings.timezoneStr));
  saveSettings();
  configTzTime(netSettings.timezoneStr,"pool.ntp.org","time.nist.gov");
  buzzerPlay(BUZZ_CLICK);g_dirty=true;
}

static bool hubStaticNetworkValid() {
  if(g_networkEditDhcp) return true;
  return !hubIpv4AllZero(g_networkEditValues[0]) &&
         !hubIpv4AllZero(g_networkEditValues[1]) &&
         !hubIpv4AllZero(g_networkEditValues[2]);
}

static void hubCommitNetworkAndRestart() {
  if(!hubStaticNetworkValid()) { buzzerPlay(BUZZ_CLICK); g_dirty=true; return; }
  netSettings.useDHCP=g_networkEditDhcp;
  char value[20];
  hubFormatIpv4(g_networkEditValues[0],value,sizeof(value));strlcpy(netSettings.staticIP,value,sizeof(netSettings.staticIP));
  hubFormatIpv4(g_networkEditValues[1],value,sizeof(value));strlcpy(netSettings.gateway,value,sizeof(netSettings.gateway));
  hubFormatIpv4(g_networkEditValues[2],value,sizeof(value));strlcpy(netSettings.subnet,value,sizeof(netSettings.subnet));
  hubFormatIpv4(g_networkEditValues[3],value,sizeof(value));strlcpy(netSettings.dns,value,sizeof(netSettings.dns));
  saveSettings();
  buzzerPlay(BUZZ_CLICK);
  delay(300);
  ESP.restart();
}

static const char* hubRotationLabel() {
  static char value[8];
  snprintf(value,sizeof(value),"R%u",(unsigned)(dispSettings.rotation&3U));
  return value;
}


bool g_audioSettingsView = false;
uint8_t g_audioSettingsPage = 0;

// v11.4 transient physical-control feedback. It is intentionally local-only:
// the printer's next MQTT state remains the source of truth.
int8_t g_printerFeedbackButton = -1;
char g_printerFeedbackText[18] = {0};
unsigned long g_printerFeedbackUntilMs = 0;

static void setPrinterFeedback(uint8_t button, const char* text, uint16_t ms=1500) {
  g_printerFeedbackButton = (int8_t)button;
  strlcpy(g_printerFeedbackText, text ? text : "", sizeof(g_printerFeedbackText));
  g_printerFeedbackUntilMs = millis() + ms;
  g_dirty = true;
}

static const char* printerFeedbackLabel(uint8_t button, const char* fallback) {
  if (g_printerFeedbackButton >= 0 && (long)(g_printerFeedbackUntilMs - millis()) <= 0) {
    g_printerFeedbackButton = -1;
    g_printerFeedbackText[0] = '\0';
  }
  return g_printerFeedbackButton == (int8_t)button ? g_printerFeedbackText : fallback;
}

// v9.7 built-in Custom widget deck. These live in the existing Smart Hub NVS
// namespace so browser and recovery reset behavior stay coherent.
enum HubWidgetKind : uint8_t {
  HUB_W_PROGRESS = 0, HUB_W_NOZZLE, HUB_W_BED, HUB_W_CHAMBER,
  HUB_W_WIFI, HUB_W_AMS, HUB_W_LAYER, HUB_W_ETA, HUB_W_FAN, HUB_W_UPTIME,
  HUB_W_COUNT
};
uint8_t g_widgets[4] = { HUB_W_PROGRESS, HUB_W_NOZZLE, HUB_W_BED, HUB_W_WIFI };
bool g_widgetEditMode = false;
uint8_t g_widgetSelected = 0;

static uint16_t clampRefresh(uint16_t s) {
  if (s < HUB_REFRESH_MIN) return HUB_REFRESH_MIN;
  if (s > HUB_REFRESH_MAX) return HUB_REFRESH_MAX;
  return s;
}

static uint16_t clampReturn(uint16_t s) {
  if (s > HUB_RETURN_MAX) return HUB_RETURN_MAX;
  return s;
}

static bool validUrl(const char* value) {
  if (!value || !*value) return true;
  return strncmp(value, "http://", 7) == 0 ||
         strncmp(value, "https://", 8) == 0;
}

static void safeCopy(char* dst, size_t len, const char* src) {
  if (!dst || len == 0) return;
  strlcpy(dst, src ? src : "", len);
}

static const char* stateText(const BambuState& s) {
  if (!s.connected) return "OFFLINE";
  if (s.gcodeState[0]) return s.gcodeState;
  return s.printing ? "RUNNING" : "IDLE";
}

static void noteHubNavigation() {
  if (g_cfg.returnSeconds == 0) {
    g_userHoldUntilMs = 0;
  } else {
    g_userHoldUntilMs =
      millis() + (unsigned long)g_cfg.returnSeconds * 1000UL;
  }
  g_dirty = true;
}

static ScreenState printerScreenForState() {
  if (!isAnyPrinterConfigured()) return SCREEN_IDLE;
  const BambuState& s = displayedPrinter().state;
  if (!s.connected) return SCREEN_CONNECTING_MQTT;
  if (s.printing) return SCREEN_PRINTING;
  if (s.gcodeStateId == GCODE_FINISH) return SCREEN_FINISHED;
  return SCREEN_IDLE;
}

static void setPage(ScreenState s) {
  g_ambientActive = false;
  if (s != SCREEN_HUB_MORE) { g_toolsView = false; g_displayExperienceView = false; g_displayExperiencePage = 0; }
  if (s != SCREEN_HUB_SYSTEM) { g_networkSettingsView = false; g_audioSettingsView = false; g_audioSettingsPage = 0; }
  noteHubNavigation();
  setScreenState(s);
  if (s == SCREEN_HUB_CUSTOM && g_custom.fetchedAtMs == 0)
    g_lastFetchAttemptMs = 0;
}

static void prefsLoad() {
  Preferences p;
  if (!p.begin(HUB_NVS, true)) return;
  g_cfg.enabled = p.getBool("enabled", true);
  g_cfg.refreshSeconds = clampRefresh(
      (uint16_t)p.getUShort("refresh", 60));
  g_cfg.returnSeconds = clampReturn(
      (uint16_t)p.getUShort("return", 60));
  String u = p.getString("url", "");
  safeCopy(g_cfg.customUrl, sizeof(g_cfg.customUrl), u.c_str());
  for (uint8_t i = 0; i < 4; i++) {
    char key[4]; snprintf(key, sizeof(key), "w%u", (unsigned)i);
    uint8_t v = p.getUChar(key, g_widgets[i]);
    g_widgets[i] = v < HUB_W_COUNT ? v : g_widgets[i];
  }
  g_experienceAccent = p.getUChar("accent", 0);
  if (g_experienceAccent > 4) g_experienceAccent = 0;
  g_ambientEnabled = p.getBool("ambient", true);
  String note = p.getString("note", "");
  safeCopy(g_workshopNote, sizeof(g_workshopNote), note.c_str());
  const uint16_t legacyTimer = p.getUShort("timerMin", 10);
  g_timerPresets[0] = p.getUShort("timer1", legacyTimer);
  g_timerPresets[1] = p.getUShort("timer2", 15);
  g_timerPresets[2] = p.getUShort("timer3", 30);
  g_timerPresets[3] = p.getUShort("timer4", 60);
  static const uint16_t timerDefaults[4] = {5,15,30,60};
  for (uint8_t i=0;i<4;i++) if (g_timerPresets[i] < 1 || g_timerPresets[i] > 120) g_timerPresets[i] = timerDefaults[i];
  g_timerPresetMinutes = g_timerPresets[0];
  p.end();
}

static bool prefsSave() {
  Preferences p;
  if (!p.begin(HUB_NVS, false)) return false;
  bool ok = true;
  p.putBool("enabled", g_cfg.enabled);
  p.putUShort("refresh", g_cfg.refreshSeconds);
  p.putUShort("return", g_cfg.returnSeconds);
  p.putString("url", g_cfg.customUrl);
  for (uint8_t i = 0; i < 4; i++) {
    char key[4]; snprintf(key, sizeof(key), "w%u", (unsigned)i);
    p.putUChar(key, g_widgets[i]);
  }
  p.putUChar("accent", g_experienceAccent);
  p.putBool("ambient", g_ambientEnabled);
  p.putString("note", g_workshopNote);
  p.putUShort("timerMin", g_timerPresets[0]); // preserve the v11.1 key
  p.putUShort("timer1", g_timerPresets[0]);
  p.putUShort("timer2", g_timerPresets[1]);
  p.putUShort("timer3", g_timerPresets[2]);
  p.putUShort("timer4", g_timerPresets[3]);
  p.end();
  return ok;
}

static void customFail(const char* msg, int httpCode = 0) {
  g_custom.valid = false;
  g_custom.healthy = false;
  g_custom.httpCode = httpCode;
  safeCopy(g_custom.message, sizeof(g_custom.message), msg);
  g_custom.fetchedAtMs = millis();
  g_dirty = true;
}

static void parseCustomPayload(const String& body, int httpCode) {
  if (body.length() > HUB_HTTP_LIMIT) {
    customFail("JSON response is larger than 4 KB", httpCode);
    return;
  }

  JsonDocument doc;
  DeserializationError err = deserializeJson(doc, body);
  if (err) {
    customFail("Custom endpoint returned invalid JSON", httpCode);
    return;
  }

  memset(&g_custom, 0, sizeof(g_custom));
  safeCopy(g_custom.title, sizeof(g_custom.title),
           doc["title"] | "Custom");
  safeCopy(g_custom.subtitle, sizeof(g_custom.subtitle),
           doc["subtitle"] | "");
  safeCopy(g_custom.status, sizeof(g_custom.status),
           doc["status"] | "");
  safeCopy(g_custom.footer, sizeof(g_custom.footer),
           doc["footer"] | "");

  JsonArray metrics = doc["metrics"].as<JsonArray>();
  uint8_t i = 0;
  for (JsonVariant v : metrics) {
    if (i >= 4 || !v.is<JsonObject>()) break;
    JsonObject m = v.as<JsonObject>();
    safeCopy(g_custom.metrics[i].label,
             sizeof(g_custom.metrics[i].label),
             m["label"] | "");
    safeCopy(g_custom.metrics[i].value,
             sizeof(g_custom.metrics[i].value),
             m["value"] | "");
    i++;
  }
  g_custom.metricCount = i;
  g_custom.valid = true;
  g_custom.healthy = true;
  g_custom.httpCode = httpCode;
  safeCopy(g_custom.message, sizeof(g_custom.message), "OK");
  g_custom.fetchedAtMs = millis();
  g_dirty = true;
}

// The reply body, read from the socket into a fixed buffer. A reply with a Transfer-Encoding header (chunked, or with a
// Content-Length as well), with no Content-Length, or declaring more than HUB_HTTP_LIMIT is refused before any byte is
// read; the copy then stops at HUB_HTTP_LIMIT + 1 bytes, at the declared length, or after 4.5 s, whichever comes first
// (workshop_http_body_limit.hpp, tested on the host). HTTPClient's whole-body String reader is never used: it buffers whatever arrives.
// False after reporting why.
static char g_hubBody[HUB_HTTP_LIMIT + 1];

struct HubStreamSource {
  WiFiClient* c;
  int available() { return c->available(); }
  int read(uint8_t* dst, size_t n) { return c->read(dst, n); }
  bool connected() { return c->connected(); }
  uint32_t nowMs() { return millis(); }
  void idle() { delay(2); }
};

static bool readBoundedBody(HTTPClient& http, int code, String& out) {
  const int declared = http.getSize();
  switch (workshop::http::checkReplyHeaders(declared, http.hasHeader("Transfer-Encoding"), HUB_HTTP_LIMIT)) {
    case workshop::http::BodyLength::Ok:
      break;
    case workshop::http::BodyLength::TooLarge:
      customFail("JSON response is larger than 4 KB", code);
      return false;
    case workshop::http::BodyLength::Chunked:
      customFail("Endpoint sent a chunked reply", code);
      return false;
    case workshop::http::BodyLength::Missing:
    default:
      customFail("Endpoint did not send a Content-Length", code);
      return false;
  }
  WiFiClient* stream = http.getStreamPtr();
  if (!stream) {
    customFail("Endpoint closed the connection", code);
    return false;
  }
  HubStreamSource src{stream};
  const workshop::http::ReadResult r = workshop::http::readBounded(src, declared, HUB_HTTP_LIMIT, 4500, g_hubBody);
  switch (r.status) {
    case workshop::http::ReadStatus::Ok:
      out = String(g_hubBody);
      return true;
    case workshop::http::ReadStatus::TooLarge:
    case workshop::http::ReadStatus::OverDeclared:
      customFail("JSON response is larger than 4 KB", code);
      return false;
    case workshop::http::ReadStatus::Timeout:
      customFail("Custom endpoint timed out", code);
      return false;
    case workshop::http::ReadStatus::Truncated:
    default:
      customFail("Custom endpoint reply was cut short", code);
      return false;
  }
}

static void fetchCustom() {
  if (!g_cfg.customUrl[0]) {
    customFail("No custom endpoint configured");
    return;
  }
  if (WiFi.status() != WL_CONNECTED) {
    customFail("WiFi is not connected");
    return;
  }

  const String url(g_cfg.customUrl);
  HTTPClient http;
  http.setConnectTimeout(3500);
  http.setTimeout(4500);
  static const char* kReplyHeaders[] = {"Transfer-Encoding"};
  http.collectHeaders(kReplyHeaders, 1);  // readBoundedBody() refuses a reply that has this header
  int code = 0;

  if (url.startsWith("https://")) {
    WiFiClientSecure client;
    client.setInsecure();
    if (!http.begin(client, url)) {
      customFail("Could not open HTTPS endpoint");
      return;
    }
    code = http.GET();
    if (code > 0 && code < 400) {
      String body;
      if (readBoundedBody(http, code, body)) parseCustomPayload(body, code);
    } else
      customFail("Custom HTTPS request failed", code);
    http.end();
    return;
  }

  WiFiClient client;
  if (!http.begin(client, url)) {
    customFail("Could not open HTTP endpoint");
    return;
  }
  code = http.GET();
  if (code > 0 && code < 400) {
    String body;
    if (readBoundedBody(http, code, body)) parseCustomPayload(body, code);
  } else {
    customFail("Custom HTTP request failed", code);
  }
  http.end();
}

// ---------------------------------------------------------------------------
// Smart Home v9 visual command-center design system
// ---------------------------------------------------------------------------
// The WS350 is only 320x480. v9 gets the richer appearance with procedural
// graphics and small reusable primitives instead of large bitmaps, preserving
// flash/heap headroom and avoiding image-decoder stalls during live printing.
static const uint16_t UI_BG       = 0x0020; // #050607 graphite black
static const uint16_t UI_PANEL    = 0x0862; // #0B0D10 primary surface
static const uint16_t UI_PANEL_2  = 0x10A3; // #111418 elevated surface
static const uint16_t UI_PANEL_3  = 0x10C4; // #171B20 active surface
static const uint16_t UI_BORDER   = 0x2966; // #292E34 precision border
static const uint16_t UI_BORDER_2 = 0x2125; // #21252A soft separator
static const uint16_t UI_ORANGE   = 0xFBC0; // #FF7A00 Workshop OS ember
static const uint16_t UI_ORANGE_2 = 0xFC43; // #FF8A1F highlight
static const uint16_t UI_GLOW     = 0x38E0; // #3A1D05 low glow
static const uint16_t UI_GREEN    = 0x3E8F; // #3AD17D semantic healthy
static const uint16_t UI_CYAN     = 0x6D5F; // semantic info
static const uint16_t UI_BLUE     = 0x6D5F;
static const uint16_t UI_PURPLE   = 0xA45F;
static const uint16_t UI_AMBER    = 0xFDA9; // #FFB44A semantic warning
static const uint16_t UI_RED      = 0xFACB; // #FF5A5F semantic fault
static const uint16_t UI_TEXT     = 0xF7BE; // #F4F4F2
static const uint16_t UI_DIM      = 0xA576; // #A7ADB5
static const uint16_t UI_MUTED    = 0x6BAF; // #6D747D
static const uint16_t UI_GREEN_BG = 0x1103;
static const uint16_t UI_WARN_BG  = 0x20A1;
static const uint16_t UI_PURP_BG  = 0x1082;
static const uint16_t UI_CYAN_BG  = 0x1082;


char g_audioDiagMessage[56] = "Audio ready";
int g_audioDiagLevel = -1;
uint16_t g_audioDiagColor = UI_GREEN;

static void setAudioDiag(const char* message, uint16_t color, int level=-1) {
  strlcpy(g_audioDiagMessage, message ? message : "", sizeof(g_audioDiagMessage));
  g_audioDiagColor = color;
  g_audioDiagLevel = level;
  g_dirty = true;
}


// Smart Home v9.6.1 zero-blip compositor.
//
// WS350 normally draws directly to the ST7796. A page transition therefore
// exposes the background clear and then every card/label as it is painted.
// Render Smart Home into a 16-bit PSRAM sprite first and commit the complete
// frame to the panel only after drawing finishes. The previous page stays
// visible during composition, eliminating the blank/intermediate frame.
static lgfx::LovyanGFX* g_hubPanelCanvas = nullptr;
static lgfx::LGFX_Sprite* g_hubFrame = nullptr;
static int16_t g_hubFrameW = 0;
static int16_t g_hubFrameH = 0;
static bool g_hubFrameDirty = true;
static bool g_hubFramePrimed = false;

static bool hubEnsureFrame() {
  if (!g_hubPanelCanvas) g_hubPanelCanvas = tft_ptr;
  if (!g_hubPanelCanvas) return false;

  const int16_t w = (int16_t)g_hubPanelCanvas->width();
  const int16_t h = (int16_t)g_hubPanelCanvas->height();
  if (w <= 0 || h <= 0) return false;

  if (g_hubFrame && g_hubFrameW == w && g_hubFrameH == h &&
      g_hubFrame->getBuffer()) {
    return true;
  }

  if (g_hubFrame) {
    g_hubFrame->deleteSprite();
    delete g_hubFrame;
    g_hubFrame = nullptr;
  }

  g_hubFrame = new (std::nothrow) lgfx::LGFX_Sprite(g_hubPanelCanvas);
  if (!g_hubFrame) return false;
  g_hubFrame->setPsram(true);
  g_hubFrame->setColorDepth(16);
  if (!g_hubFrame->createSprite(w, h)) {
    delete g_hubFrame;
    g_hubFrame = nullptr;
    return false;
  }

  g_hubFrameW = w;
  g_hubFrameH = h;
  g_hubFrame->fillScreen(UI_BG);
  g_hubFrameDirty = true;
  g_hubFramePrimed = false;
  return true;
}

static inline void hubMarkFrameDirty() {
  g_hubFrameDirty = true;
  markFrameDirty();
}

static void hubCommitFrame() {
  if (!g_hubFrame || !g_hubFrame->getBuffer()) return;
  g_hubFrame->pushSprite(0, 0);
  g_hubFrameDirty = false;
  g_hubFramePrimed = true;
}

static uint16_t uiStateColor(const BambuState& s) {
  if (!s.connected) return UI_DIM;
  if (s.gcodeStateId == GCODE_FAILED) return UI_RED;
  if (s.gcodeStateId == GCODE_PAUSE) return UI_AMBER;
  if (s.printing) return UI_ORANGE;
  return UI_GREEN;
}

static const char* uiSpeedText(uint8_t speed) {
  switch (speed) {
    case 1: return "SILENT";
    case 2: return "STANDARD";
    case 3: return "SPORT";
    case 4: return "LUDICROUS";
    default: return "AUTO";
  }
}

static uint8_t uiHmsCount(const BambuState& s) {
#if HAS_HMS_UI
  uint8_t n = s.hmsCount;
  if (s.printError && n < 255) n++;
  return n;
#else
  (void)s;
  return 0;
#endif
}

static void uiTrimUtf8End(char* s) {
  if (!s) return;
  size_t n = strlen(s);
  if (!n) return;
  n--;
  while (n > 0 && (((uint8_t)s[n] & 0xC0) == 0x80)) n--;
  s[n] = '\0';
}

static void uiFitText(char* out, size_t len, const char* src,
                      int16_t maxPx, FontID font) {
  if (!out || len == 0) return;
  strlcpy(out, src && *src ? src : "—", len);
  setFont(tft, font);
  if (maxPx <= 0 || tft.textWidth(out) <= maxPx) return;
  const char* dots = "...";
  const int16_t dotsW = tft.textWidth(dots);
  while (out[0] && tft.textWidth(out) + dotsW > maxPx) uiTrimUtf8End(out);
  if (out[0] && strlen(out) + 3 < len) strlcat(out, dots, len);
  else if (dotsW <= maxPx) strlcpy(out, dots, len);
  else out[0] = '\0';
}

static void uiDrawFit(const char* text, int16_t x, int16_t y, int16_t maxPx,
                      FontID font, uint8_t datum, uint16_t fg, uint16_t bg) {
  char fitted[72];
  uiFitText(fitted, sizeof(fitted), text, maxPx, font);
  setFont(tft, font);
  tft.setTextDatum(datum);
  tft.setTextColor(fg, bg);
  tft.drawString(fitted, x, y);
}

struct HubRect {
  int16_t x, y, w, h;
  bool contains(int16_t px, int16_t py) const {
    return px >= x && py >= y && px < x + w && py < y + h;
  }
};

static HubRect hr(int16_t x, int16_t y, int16_t w, int16_t h) { return {x,y,w,h}; }
static bool hubLandscape() { return tft.width() > tft.height(); }
static int16_t hubNavH() { return 54; }
static int16_t hubHeaderH() { return 36; }
static int16_t hubContentBottom() { return tft.height() - hubNavH() - 8; }
static HubRect hubNavRect(uint8_t i) {
  const int16_t W=tft.width(), cell=W/4, x=i*cell;
  return hr(x,tft.height()-hubNavH(),i==3?W-x:cell,hubNavH());
}

static HubRect hubMoreRect(uint8_t i) {
  const int16_t W=tft.width();
  if (hubLandscape()) {
    const int16_t m=8,g=8,cw=(W-2*m-g)/2,ch=74;
    return hr(m+(i%2)*(cw+g),38+(i/2)*(ch+8),cw,ch);
  }
  const int16_t m=10,g=10,cw=(W-2*m-g)/2,ch=116;
  return hr(m+(i%2)*(cw+g),48+(i/2)*(ch+10),cw,ch);
}

static HubRect hubCustomRect(uint8_t i) {
  const int16_t W=tft.width();
  if (hubLandscape()) {
    const int16_t m=8,g=8,cw=(W-2*m-3*g)/4;
    return hr(m+i*(cw+g),100,cw,116);
  }
  const int16_t m=8,g=8,cw=(W-2*m-g)/2,ch=116;
  return hr(m+(i%2)*(cw+g),124+(i/2)*(ch+g),cw,ch);
}

static HubRect hubPrinterActionRect(uint8_t i) {
  const int16_t W=tft.width(),m=8,g=8,cw=(W-2*m-g)/2;
  if(hubLandscape()) return hr(m+(i%2)*(cw+g),106+(i/2)*76,cw,68);
  return hr(m+(i%2)*(cw+g),106+(i/2)*72,cw,64);
}

static HubRect hubWorkshopActionRect(uint8_t i) {
  const int16_t W=tft.width();
  if(hubLandscape()){const int16_t m=8,g=8,cw=(W-2*m-3*g)/4;return hr(m+i*(cw+g),212,cw,48);}
  const int16_t m=8,g=8,cw=(W-2*m-g)/2;return hr(m+(i%2)*(cw+g),328+(i/2)*56,cw,48);
}

static HubRect hubHomeRect(uint8_t i) {
  const int16_t W=tft.width();
  if(hubLandscape()) {
    if(i==1) return hr(8,44,312,146);
    if(i==0) return hr(8,198,152,62);
    if(i==2) return hr(168,198,152,62);
    return hr(0,0,0,0);
  }
  if(i==1) return hr(8,44,W-16,150);
  if(i==0) return hr(8,202,W-16,64);
  if(i==2) return hr(8,274,W-16,64);
  return hr(0,0,0,0);
}

static HubRect hubToolsPresetRect(uint8_t i) {
  const int16_t W=tft.width();
  if(hubLandscape()){const int16_t m=8,g=8,cw=(W-2*m-3*g)/4;return hr(m+i*(cw+g),140,cw,48);}
  const int16_t m=18,g=8,cw=(W-2*m-g)/2;return hr(m+(i%2)*(cw+g),222+(i/2)*56,cw,48);
}

static HubRect hubToolsActionRect(uint8_t i) {
  const int16_t W=tft.width();
  if(hubLandscape()){const int16_t m=8,g=8,cw=(W-2*m-3*g)/4;return hr(m+i*(cw+g),198,cw,54);}
  const int16_t m=12,g=6,cw=(W-2*m-g)/2;return hr(m+(i%2)*(cw+g),334+(i/2)*54,cw,48);
}

static HubRect hubSystemActionRect(uint8_t i) {
  (void)i;
  return hr(0,0,0,0);
}

static void uiCard(int16_t x, int16_t y, int16_t w, int16_t h,
                   uint16_t accent = UI_BORDER, bool strong = false) {
  tft.fillRoundRect(x + 2, y + 3, w, h, 11, 0x0000);
  tft.fillRoundRect(x, y, w, h, 11, strong ? UI_GLOW : UI_BORDER_2);
  tft.fillRoundRect(x + 1, y + 1, w - 2, h - 2, 10, UI_PANEL);
  // v11: a restrained inner highlight gives the graphite surfaces depth on the
  // physical IPS panel without adding another outline or decorative dot.
  if (w > 34) tft.drawFastHLine(x + 17, y + 2, w - 34, strong ? accent : UI_BORDER_2);
  tft.drawRoundRect(x + 1, y + 1, w - 2, h - 2, 10, strong ? accent : UI_BORDER);
  if (accent != UI_BORDER) {
    if (strong) {
      tft.fillRoundRect(x + 1, y + 9, 3, h - 18, 2, accent);
      tft.fillCircle(x + w - 12, y + 12, 3, accent);
    } else {
      // v10.5: category accent without the old stripe+dot on every card.
      tft.fillRoundRect(x + 11, y + 1, 24, 2, 1, accent);
    }
  }
}

static void uiPanelFill(int16_t x, int16_t y, int16_t w, int16_t h) {
  tft.fillRoundRect(x, y, w, h, 9, UI_PANEL_2);
  tft.drawRoundRect(x, y, w, h, 9, UI_BORDER_2);
}

static void uiPill(int16_t x, int16_t y, int16_t w,
                   const char* text, uint16_t color) {
  tft.fillRoundRect(x, y, w, 20, 10, UI_PANEL_3);
  tft.drawRoundRect(x, y, w, 20, 10, color);
  tft.fillCircle(x + 10, y + 10, 3, color);
  uiDrawFit(text,x+18,y+10,w-24,FONT_SMALL,ML_DATUM,color,UI_PANEL_3);
}

static void uiSectionLabel(int16_t x, int16_t y, const char* label,
                           uint16_t accent, int16_t maxPx=180) {
  tft.fillRoundRect(x, y + 3, 3, 12, 2, accent);
  uiDrawFit(label,x+9,y+9,maxPx,FONT_SMALL,ML_DATUM,UI_TEXT,UI_PANEL);
}

static void uiMetric(int16_t x, int16_t y, int16_t w, int16_t h,
                     const char* label, const char* value, uint16_t accent,
                     const char* sub = nullptr) {
  uiCard(x, y, w, h, UI_BORDER, false);
  uiDrawFit(label && *label ? label : "—",x+9,y+7,w-18,FONT_SMALL,TL_DATUM,UI_MUTED,UI_PANEL);
  uiDrawFit(value && *value ? value : "—",x+9,y+27,w-18,h>=58?FONT_BODY:FONT_SMALL,TL_DATUM,accent,UI_PANEL);
  if (sub && *sub && h >= 54)
    uiDrawFit(sub,x+9,y+h-15,w-18,FONT_SMALL,TL_DATUM,UI_DIM,UI_PANEL);
}

static void uiProgressBar(int16_t x, int16_t y, int16_t w, uint8_t pct,
                          uint16_t accent = UI_ORANGE) {
  if (pct > 100) pct = 100;
  tft.fillRoundRect(x, y, w, 7, 4, UI_PANEL_2);
  int16_t fw = (int32_t)w * pct / 100;
  if (fw > 0) tft.fillRoundRect(x, y, fw, 7, 4, accent);
  if (fw > 5) tft.fillCircle(x + fw - 3, y + 3, 2, UI_TEXT);
}

static void uiProgressRing(int16_t cx, int16_t cy, int16_t radius,
                           uint8_t pct, uint16_t accent) {
  if (pct > 100) pct = 100;
  const uint8_t segments = 32;
  const uint8_t active = (uint16_t)segments * pct / 100;
  for (uint8_t i = 0; i < segments; i++) {
    float a = (-90.0f + (360.0f * i / segments)) * 0.01745329252f;
    int16_t x = cx + (int16_t)(cosf(a) * radius);
    int16_t y = cy + (int16_t)(sinf(a) * radius);
    tft.fillCircle(x, y, i < active ? 3 : 2, i < active ? accent : UI_BORDER);
  }
}

static void uiPrinterArt(int16_t x, int16_t y, int16_t w, int16_t h,
                         uint16_t accent) {
  int16_t bodyX = x + w / 5, bodyY = y + h / 4;
  int16_t bodyW = w * 3 / 5, bodyH = h * 3 / 5;
  tft.fillRoundRect(bodyX + 3, bodyY + 4, bodyW, bodyH, 7, UI_BG);
  tft.fillRoundRect(bodyX, bodyY, bodyW, bodyH, 7, UI_BORDER);
  tft.fillRoundRect(bodyX + 2, bodyY + 2, bodyW - 4, bodyH - 4, 5, 0x0862);
  tft.drawRect(bodyX + 9, bodyY + 11, bodyW - 18, bodyH - 22, UI_MUTED);
  tft.drawRect(bodyX + 13, bodyY + 15, bodyW - 26, bodyH - 30, 0x0000);
  tft.fillRoundRect(bodyX + bodyW - 17, bodyY + 8, 9, 18, 2, UI_PANEL_2);
  tft.fillCircle(bodyX + bodyW - 13, bodyY + 13, 2, UI_GREEN);
  tft.fillRoundRect(bodyX + 6, bodyY - 14, bodyW - 12, 14, 5, UI_PANEL_2);
  for (uint8_t i = 0; i < 4; i++) {
    int16_t sx = bodyX + 13 + i * ((bodyW - 26) / 4);
    tft.fillCircle(sx, bodyY - 7, 5, i == 0 ? accent : UI_MUTED);
    tft.fillCircle(sx, bodyY - 7, 2, UI_BG);
  }
  tft.drawFastHLine(bodyX + 13, bodyY + bodyH - 13, bodyW - 26, accent);
  int16_t px = bodyX + bodyW / 2, py = bodyY + bodyH - 23;
  tft.fillTriangle(px - 10, py, px, py - 18, px + 10, py, accent);
  tft.fillTriangle(px - 6, py - 2, px, py - 12, px + 6, py - 2, UI_PANEL);
}

static bool uiNameHas(const char* name, const char* token) {
  if (!name || !token || !*token) return false;
  for (const char* p = name; *p; ++p) {
    const char* a = p; const char* b = token;
    while (*a && *b && toupper((unsigned char)*a) == toupper((unsigned char)*b)) { ++a; ++b; }
    if (!*b) return true;
  }
  return false;
}

enum UiPrinterFamily : uint8_t { UI_PF_GENERIC=0, UI_PF_A1, UI_PF_A1_MINI, UI_PF_P1, UI_PF_X1, UI_PF_H2, UI_PF_X2 };
static UiPrinterFamily uiPrinterFamily(const PrinterSlot& p) {
  const char* n=p.config.name;
  if (uiNameHas(n,"X2")) return UI_PF_X2;
  if (uiNameHas(n,"H2") || p.state.dualNozzle) return UI_PF_H2;
  if (uiNameHas(n,"A1 MINI")) return UI_PF_A1_MINI;
  if (uiNameHas(n,"A1")) return UI_PF_A1;
  if (uiNameHas(n,"P1")) return UI_PF_P1;
  if (uiNameHas(n,"X1")) return UI_PF_X1;
  return UI_PF_GENERIC;
}

static void uiPrinterArtFamily(int16_t x, int16_t y, int16_t w, int16_t h,
                               uint16_t accent, const PrinterSlot& p) {
  const UiPrinterFamily family=uiPrinterFamily(p);
  if (family==UI_PF_A1 || family==UI_PF_A1_MINI) {
    const int16_t cx=x+w/2, bedY=y+h*4/5;
    tft.fillRoundRect(x+w/5,bedY-4,w*3/5,7,3,UI_BORDER);
    tft.drawFastVLine(x+w/4,y+h/5,h*3/5,UI_MUTED);
    tft.drawFastHLine(x+w/4,y+h/4,w/2,UI_MUTED);
    tft.fillRoundRect(cx-11,y+h/3,22,15,4,UI_PANEL_2);
    tft.fillCircle(cx,y+h/3+7,3,accent);
    tft.fillTriangle(cx-9,bedY-5,cx,bedY-25,cx+9,bedY-5,accent);
    if (family==UI_PF_A1_MINI) uiDrawFit("mini",cx,y+h-4,w-12,FONT_SMALL,TC_DATUM,UI_MUTED,UI_BG);
    return;
  }
  uiPrinterArt(x,y,w,h,accent);
  const int16_t cx=x+w/2;
  if (family==UI_PF_P1) tft.drawFastHLine(x+w/4,y+h*4/5,w/2,UI_CYAN);
  if (family==UI_PF_X1) { tft.fillCircle(x+w*3/4,y+h/3,3,UI_BLUE); tft.drawFastHLine(x+w/4,y+h*4/5,w/2,UI_BLUE); }
  if (family==UI_PF_H2 || family==UI_PF_X2) {
    tft.fillCircle(cx-6,y+h/2,3,UI_ORANGE); tft.fillCircle(cx+6,y+h/2,3,UI_CYAN);
    tft.drawFastHLine(x+w/4,y+h*4/5,w/2,family==UI_PF_X2?UI_PURPLE:UI_ORANGE);
  }
}

static void uiSpoolScaled(int16_t cx,int16_t cy,uint16_t color,bool active,int8_t remain,uint8_t r) {
  (void)remain; if(!color)color=UI_MUTED;
  if(active)tft.fillCircle(cx,cy,r+3,UI_ORANGE);
  tft.fillCircle(cx,cy,r+1,UI_BORDER); tft.fillCircle(cx,cy,r-3,color);
  tft.fillCircle(cx,cy,r/3,UI_BG); tft.drawCircle(cx,cy,r/2,UI_PANEL_2);
}

static void uiSpoolCaption(int16_t cx,int16_t y,const char* type,int8_t remain,int16_t maxPx) {
  char line[24];
  if(remain>=0)snprintf(line,sizeof(line),"%s · %d%%",type&&*type?type:"—",(int)remain);
  else snprintf(line,sizeof(line),"%s",type&&*type?type:"—");
  uiDrawFit(line,cx,y,maxPx,FONT_SMALL,TC_DATUM,UI_DIM,UI_PANEL);
}

static void uiWifiGlyph(int16_t x, int16_t y, int rssi) {
  uint16_t c = rssi > -72 ? UI_GREEN : (rssi > -82 ? UI_AMBER : UI_RED);
  uint8_t bars = rssi > -60 ? 4 : rssi > -70 ? 3 : rssi > -80 ? 2 : 1;
  for (uint8_t i = 0; i < 4; i++) {
    int16_t bh = 5 + i * 4;
    tft.fillRoundRect(x + i * 7, y + 18 - bh, 5, bh, 2, i < bars ? c : UI_BORDER);
  }
}

static uint16_t uiPageAccent(uint8_t page) {
  (void)page;
  return UI_ORANGE;
}

static void uiClockText(char* out, size_t len) {
  if (!out || !len) return;
  out[0] = '\0';
  time_t now = time(nullptr);
  if (now < 1700000000) return;
  struct tm tmNow;
  localtime_r(&now, &tmNow);
  char tmp[12];
  if (!strftime(tmp, sizeof(tmp), "%I:%M", &tmNow)) return;
  const char* p = tmp[0] == '0' ? tmp + 1 : tmp;
  strlcpy(out, p, len);
}

static uint16_t uiExperienceAccent() {
  switch (g_experienceAccent) {
    case 1: return UI_CYAN;
    case 2: return UI_BLUE;
    case 3: return UI_PURPLE;
    case 4: return UI_GREEN;
    default:return UI_ORANGE;
  }
}

static bool workshopTimerActive() {
  return g_workshopTimerEndMs != 0 && (long)(g_workshopTimerEndMs - millis()) > 0;
}

static uint32_t workshopTimerRemainingSeconds() {
  if (!workshopTimerActive()) return 0;
  return (uint32_t)((g_workshopTimerEndMs - millis() + 999UL) / 1000UL);
}

static void workshopTimerText(char* out, size_t len, bool compact=false) {
  if (!out || !len) return;
  if (g_workshopTimerDone) { strlcpy(out, compact ? "DONE" : "Timer complete", len); return; }
  if (!workshopTimerActive()) {
    strlcpy(out, compact ? "TOOLS" : "Timer ready", len);
    return;
  }
  uint32_t sec=workshopTimerRemainingSeconds();
  snprintf(out,len,compact?"%02u:%02u":"%u:%02u remaining",
           (unsigned)(sec/60U),(unsigned)(sec%60U));
}

static void startWorkshopTimer(uint16_t minutes) {
  if (minutes < 1) minutes = 1;
  if (minutes > 120) minutes = 120;
  g_workshopTimerStartedMinutes = minutes;
  g_workshopTimerDone = false;
  g_workshopTimerEndMs = millis() + (unsigned long)minutes * 60000UL;
  g_workshopTimerLastSecond = 0xFFFFFFFFUL;
  g_dirty = true;
}

static void clearWorkshopTimer() {
  g_workshopTimerEndMs = 0;
  g_workshopTimerDone = false;
  g_workshopTimerStartedMinutes = 0;
  g_workshopTimerLastSecond = 0xFFFFFFFFUL;
  g_dirty = true;
}

static void uiClockDateText(char* out,size_t len) {
  if (!out || !len) return; out[0]='\0';
  time_t now=time(nullptr); if(now<1700000000)return;
  struct tm tmNow; localtime_r(&now,&tmNow);
  strftime(out,len,"%a • %b %d",&tmNow);
}

static void uiBackdrop() {
  const int16_t W=tft.width(), H=hubContentBottom();
  for (int16_t y=52; y<H; y+=48) tft.drawFastHLine(0,y,W,0x0841);
  for (int16_t x=24; x<W; x+=64) tft.drawFastVLine(x,40,H-40,0x0841);
  tft.drawFastHLine(10,44,58,UI_GLOW);
  tft.drawFastHLine(W-68,44,58,UI_GLOW);
  tft.fillCircle(68,44,2,UI_ORANGE);
  tft.fillCircle(W-68,44,2,UI_ORANGE);
}

static const uint16_t W25_BG=0x08A3;
static const uint16_t W25_NAV=0x10C4;
static const uint16_t W25_SURFACE=0x10E5;
static const uint16_t W25_SURFACE_2=0x1926;
static const uint16_t W25_SURFACE_3=0x21A8;
static const uint16_t W25_LINE=0x322A;
static const uint16_t W25_TEXT=0xF7BF;
static const uint16_t W25_TEXT_2=0xDF1D;
static const uint16_t W25_MUTED=0x9D57;
static const uint16_t W25_ACCENT=0x5EB9;
static const uint16_t W25_INFO=0x5D5F;
static const uint16_t W25_WARN=0xF5AB;
static const uint16_t W25_DANGER=0xFB2E;
static const uint16_t W25_SUCCESS=0x5EB1;

static constexpr uint16_t C10_BG        = 0x0000; // #000000
static constexpr uint16_t C10_SURFACE   = 0x18E3; // #1C1C1E
static constexpr uint16_t C10_SURFACE_2 = 0x2965; // #2C2C2E
static constexpr uint16_t C10_SURFACE_3 = 0x39C7; // #3A3A3C
static constexpr uint16_t C10_SEPARATOR = 0x39C7;
static constexpr uint16_t C10_TEXT      = 0xFFFF;
static constexpr uint16_t C10_MUTED     = 0x8C72; // #8E8E93
static constexpr uint16_t C10_ACCENT    = 0x0C3F; // #0A84FF
static constexpr uint16_t C10_GREEN     = 0x368B; // #30D158
static constexpr uint16_t C10_ORANGE    = 0xFCE1; // #FF9F0A
static constexpr uint16_t C10_RED       = 0xFA27; // #FF453A

static const char* hubV1125UiFingerprint(uint8_t page) {
  switch(page) {
    case 0: return "UI13-H";
    case 1: return "UI13-P";
    case 2: return "UI13-T";
    case 3: return "UI13-M";
    case 4: return "UI13-S";
    default: return "UI13";
  }
}

static uint16_t hubUi13HeaderStateColor(const char* state,bool explicitState,bool online) {
  if(!explicitState) return online?C10_GREEN:C10_ORANGE;
  if(!state||!state[0]) return C10_MUTED;
  if(strcmp(state,"Online")==0||strcmp(state,"Connected")==0||strcmp(state,"Healthy")==0||
     strcmp(state,"Ready")==0||strcmp(state,"Printing")==0||strcmp(state,"OK")==0) return C10_GREEN;
  if(strcmp(state,"Offline")==0||strcmp(state,"Set Up")==0||strcmp(state,"Setup Required")==0||
     strcmp(state,"Unavailable")==0||strcmp(state,"Needs attention")==0||strcmp(state,"Check Device")==0||
     strcmp(state,"Starting")==0) return C10_ORANGE;
  if(strcmp(state,"Error")==0||strcmp(state,"Failed")==0) return C10_RED;
  if(strcmp(state,"Unknown")==0) return C10_MUTED;
  return C10_ACCENT;
}

static void drawHeader(const char* title,const char* right,uint8_t page) {
  const int16_t W=tft.width(),HH=hubHeaderH();
  const bool online=WiFi.status()==WL_CONNECTED;
  const bool explicitState=right&&right[0];
  tft.fillRect(0,0,W,HH,C10_BG);
  uiDrawFit(title?title:"Home",12,8,hubLandscape()?270:178,FONT_BODY,TL_DATUM,C10_TEXT,C10_BG);
  const char* state=explicitState?right:(online?"Online":"Offline");
  const uint16_t c=hubUi13HeaderStateColor(state,explicitState,online);
  const int16_t pw=hubLandscape()?104:90;
  tft.fillCircle(W-pw+4,18,4,c);
  uiDrawFit(state,W-12,18,pw-18,FONT_SMALL,MR_DATUM,c,C10_BG);
  (void)hubV1125UiFingerprint(page);
}


static void uiNavIcon(int16_t cx, int16_t cy, uint8_t item, uint16_t c) {
  if (item == 0) {
    tft.drawLine(cx - 6, cy, cx, cy - 6, c); tft.drawLine(cx, cy - 6, cx + 6, cy, c);
    tft.drawRect(cx - 5, cy, 10, 7, c);
  } else if (item == 1) {
    tft.drawRoundRect(cx - 6, cy - 5, 12, 10, 2, c); tft.drawFastHLine(cx - 3, cy - 8, 6, c); tft.fillCircle(cx, cy, 2, c);
  } else if (item == 2) {
    tft.drawRect(cx - 6, cy - 6, 12, 12, c); tft.drawLine(cx - 6, cy - 6, cx + 6, cy + 6, c); tft.drawLine(cx + 6, cy - 6, cx - 6, cy + 6, c);
  } else {
    tft.drawCircle(cx, cy, 6, c); tft.fillCircle(cx - 3, cy, 1, c); tft.fillCircle(cx, cy, 1, c); tft.fillCircle(cx + 3, cy, 1, c);
  }
}

static void hubV1125TabIcon(uint8_t i,int16_t cx,int16_t cy,uint16_t c) {
  if(i==0) {
    tft.drawLine(cx-8,cy,cx,cy-7,c);
    tft.drawLine(cx,cy-7,cx+8,cy,c);
    tft.drawRect(cx-6,cy,12,9,c);
  } else if(i==1) {
    tft.drawRect(cx-8,cy-7,16,15,c);
    tft.drawFastHLine(cx-4,cy+4,8,c);
  } else if(i==2) {
    tft.drawCircle(cx,cy,5,c);
    tft.drawFastHLine(cx-9,cy,18,c);
    tft.drawFastVLine(cx,cy-9,18,c);
  } else {
    tft.drawCircle(cx,cy,6,c);
    tft.drawCircle(cx,cy,2,c);
    tft.drawFastHLine(cx-10,cy,4,c);
    tft.drawFastHLine(cx+7,cy,4,c);
    tft.drawFastVLine(cx,cy-10,4,c);
    tft.drawFastVLine(cx,cy+7,4,c);
  }
}

static void uiBottomNav(uint8_t active,const char* nextPage){(void)nextPage;const int16_t y=tft.height()-hubNavH(),W=tft.width();static const char* labels[4]={"Home","Printer","Tools","Settings"};tft.fillRect(0,y,W,hubNavH(),C10_SURFACE);tft.drawFastHLine(0,y,W,C10_SEPARATOR);for(uint8_t i=0;i<4;i++){HubRect r=hubNavRect(i);const bool selected=i==active;const uint16_t c=selected?C10_ACCENT:C10_MUTED;const int16_t cx=r.x+r.w/2;hubV1125TabIcon(i,cx,r.y+17,c);uiDrawFit(labels[i],cx,r.y+35,r.w-12,FONT_SMALL,TC_DATUM,c,C10_SURFACE);}}

static void uiActionButton(const HubRect& r, const char* label, uint16_t accent, bool filled=false) {
  const int16_t h = r.h < 44 ? 44 : r.h;
  const bool disabled = accent == UI_DIM;
  const bool primary = !disabled && (filled || accent==UI_ORANGE || accent==UI_AMBER);
  const uint16_t edge = disabled ? UI_BORDER_2 : (primary ? UI_ORANGE : UI_BORDER);
  const uint16_t bg = filled && !disabled ? UI_ORANGE : UI_PANEL_2;
  tft.fillRoundRect(r.x + 1, r.y + 2, r.w, h, 10, 0x0000);
  tft.fillRoundRect(r.x, r.y, r.w, h, 10, bg);
  tft.drawRoundRect(r.x, r.y, r.w, h, 10, edge);
  if (!filled && !disabled) {
    tft.fillRoundRect(r.x + 7, r.y + h / 2 - 8, 3, 16, 2, edge);
    if(primary)tft.fillCircle(r.x+r.w-11,r.y+10,2,UI_ORANGE);
  }
  const uint16_t textColor = disabled ? UI_DIM : (filled ? UI_BG : (primary ? UI_ORANGE : UI_TEXT));
  uiDrawFit(label, r.x + r.w / 2 + (filled ? 0 : 2), r.y + h / 2,
            r.w - 24, FONT_SMALL, MC_DATUM, textColor, bg);
}



static void formatDuration(uint16_t mins, char* out, size_t len) {
  if (mins == 0) { strlcpy(out, "—", len); return; }
  uint16_t h = mins / 60, m = mins % 60;
  if (h) snprintf(out, len, "%uh %02um", (unsigned)h, (unsigned)m);
  else snprintf(out, len, "%um", (unsigned)m);
}

static uint32_t uiAmsSignature(const BambuState& s) {
  uint32_t sig=2166136261u;sig=(sig^(uint8_t)(s.ams.present?1:0))*16777619u;sig=(sig^(uint8_t)s.ams.unitCount)*16777619u;sig=(sig^(uint8_t)(s.ams.activeTray+1))*16777619u;
  for(uint8_t i=0;i<4;i++){const AmsTray&tr=s.ams.trays[i];sig=(sig^(uint8_t)(tr.present?1:0))*16777619u;sig=(sig^(uint16_t)tr.colorRgb565)*16777619u;sig=(sig^(uint8_t)(tr.remain+1))*16777619u;for(uint8_t j=0;tr.type[j]&&j<8;j++)sig=(sig^(uint8_t)tr.type[j])*16777619u;}
  return sig;
}

static const char* hubWidgetLabel(uint8_t kind) {
  static const char* labels[]={"PROGRESS","NOZZLE","BED","CHAMBER","WI-FI","AMS","LAYER","ETA","FAN","UPTIME"};
  return kind<HUB_W_COUNT?labels[kind]:"WIDGET";
}

static void hubWidgetValue(uint8_t kind,char* value,size_t valueLen,char* sub,size_t subLen) {
  const bool configured=isAnyPrinterConfigured();const BambuState*s=configured?&displayedPrinter().state:nullptr;
  strlcpy(value,"—",valueLen);strlcpy(sub,configured?stateText(*s):"no printer",subLen);
  switch(kind){
    case HUB_W_PROGRESS:if(s)snprintf(value,valueLen,"%u%%",(unsigned)s->progress);strlcpy(sub,s&&s->printing?"active job":"printer ready",subLen);break;
    case HUB_W_NOZZLE:if(s&&s->connected)snprintf(value,valueLen,"%.0f°",s->nozzleTemp);strlcpy(sub,"nozzle",subLen);break;
    case HUB_W_BED:if(s&&s->connected)snprintf(value,valueLen,"%.0f°",s->bedTemp);strlcpy(sub,"build plate",subLen);break;
    case HUB_W_CHAMBER:if(s&&s->connected)snprintf(value,valueLen,"%.0f°",s->chamberTemp);strlcpy(sub,"chamber",subLen);break;
    case HUB_W_WIFI:snprintf(value,valueLen,"%d dBm",WiFi.status()==WL_CONNECTED?WiFi.RSSI():-100);strlcpy(sub,WiFi.status()==WL_CONNECTED?"connected":"offline",subLen);break;
    case HUB_W_AMS:if(s&&s->ams.present)snprintf(value,valueLen,"%u slots",(unsigned)(s->ams.unitCount*4));strlcpy(sub,s&&s->ams.present?"materials":"not present",subLen);break;
    case HUB_W_LAYER:if(s)snprintf(value,valueLen,"%u/%u",(unsigned)s->layerNum,(unsigned)s->totalLayers);strlcpy(sub,"layer",subLen);break;
    case HUB_W_ETA:if(s)formatDuration(s->remainingMinutes,value,valueLen);strlcpy(sub,"remaining",subLen);break;
    case HUB_W_FAN:if(s&&s->connected)snprintf(value,valueLen,"%u%%",(unsigned)s->coolingFanPct);strlcpy(sub,"part fan",subLen);break;
    case HUB_W_UPTIME:{uint32_t m=millis()/60000UL;snprintf(value,valueLen,"%uh %02um",(unsigned)(m/60),(unsigned)(m%60));strlcpy(sub,"device",subLen);break;}
  }
}

static void drawWidgetCard(uint8_t slot,const HubRect&r,bool selected=false) {
  static const uint16_t accents[4]={UI_ORANGE,UI_CYAN,UI_AMBER,UI_GREEN};char value[20],sub[24];
  hubWidgetValue(g_widgets[slot],value,sizeof(value),sub,sizeof(sub));
  uiMetric(r.x,r.y,r.w,r.h,hubWidgetLabel(g_widgets[slot]),value,selected?UI_ORANGE:accents[slot],sub);
  if(selected){tft.drawRoundRect(r.x+2,r.y+2,r.w-4,r.h-4,9,UI_ORANGE);tft.fillRoundRect(r.x+r.w-22,r.y+8,14,4,2,UI_ORANGE);}
}

static void drawTelemetryRail(const HubRect&r,const BambuState&s) {
  uiCard(r.x,r.y,r.w,r.h,s.connected?UI_BORDER:UI_RED,false);
  const char* labels[4]={"NOZZLE","BED","CHAMBER","FAN"};char vals[4][12];
  if(s.connected){snprintf(vals[0],sizeof(vals[0]),"%.0f°",s.nozzleTemp);snprintf(vals[1],sizeof(vals[1]),"%.0f°",s.bedTemp);snprintf(vals[2],sizeof(vals[2]),"%.0f°",s.chamberTemp);snprintf(vals[3],sizeof(vals[3]),"%u%%",(unsigned)s.coolingFanPct);}else{for(uint8_t i=0;i<4;i++)strlcpy(vals[i],"—",sizeof(vals[i]));}
  if(r.w>=260){const int16_t cell=r.w/4;for(uint8_t i=0;i<4;i++){if(i)tft.drawFastVLine(r.x+i*cell,r.y+9,r.h-18,UI_BORDER);int16_t cx=r.x+i*cell+cell/2;uiDrawFit(labels[i],cx,r.y+9,cell-8,FONT_SMALL,TC_DATUM,UI_DIM,UI_PANEL);uiDrawFit(vals[i],cx,r.y+31,cell-8,FONT_BODY,TC_DATUM,i==0?UI_ORANGE:i==1?UI_AMBER:i==2?UI_BLUE:UI_CYAN,UI_PANEL);}}
  else{const int16_t rowH=r.h/4;for(uint8_t i=0;i<4;i++){if(i)tft.drawFastHLine(r.x+8,r.y+i*rowH,r.w-16,UI_BORDER);uiDrawFit(labels[i],r.x+10,r.y+i*rowH+rowH/2,r.w/2-14,FONT_SMALL,ML_DATUM,UI_DIM,UI_PANEL);uiDrawFit(vals[i],r.x+r.w-10,r.y+i*rowH+rowH/2,r.w/2-14,FONT_BODY,MR_DATUM,i==0?UI_ORANGE:i==1?UI_AMBER:i==2?UI_BLUE:UI_CYAN,UI_PANEL);}}
}



static bool hubTouchHealthy();

// ---------------------------------------------------------------------------
// Smart Home v10.5 physical information architecture helpers
// ---------------------------------------------------------------------------
static const char* uiPrinterStateLabel(const BambuState& s) {
  if (!s.connected) return "OFFLINE";
  if (s.gcodeStateId == GCODE_PAUSE) return "PAUSED";
  if (s.gcodeStateId == GCODE_FAILED) return "ERROR";
  if (s.printing) return "PRINTING";
  return "READY";
}

static const char* uiFilamentColorName(uint16_t c) {
  // RGB565 -> coarse workshop-friendly color identity. This intentionally
  // favors stable names over a large palette that would truncate on-device.
  const int r=((c>>11)&0x1f)*255/31;
  const int g=((c>>5)&0x3f)*255/63;
  const int b=(c&0x1f)*255/31;
  const int hi=max(r,max(g,b)), lo=min(r,min(g,b));
  if (hi < 42) return "BLACK";
  if (lo > 220) return "WHITE";
  if (hi-lo < 24) return hi < 105 ? "DARK GRAY" : (hi > 190 ? "LIGHT GRAY" : "GRAY");
  if (r > 180 && g > 125 && b < 80) return g > 185 ? "YELLOW" : "ORANGE";
  if (r > 165 && b > 125 && g < 135) return "PURPLE";
  if (r >= g && r >= b) return "RED";
  if (g >= r && g >= b) return g > b + 35 ? "GREEN" : "TEAL";
  return b > r + 25 ? "BLUE" : "PURPLE";
}

static int8_t uiLoadedTray(const BambuState& s) {
  return (s.ams.present && s.ams.activeTray < 4) ? (int8_t)s.ams.activeTray : -1;
}

static uint8_t uiMaterialCount(const BambuState& s) {
  uint8_t count=0;
  if (!s.ams.present) return 0;
  uint8_t n=s.ams.unitCount*4; if(n>4)n=4;
  for(uint8_t i=0;i<n;i++) if(s.ams.trays[i].present) count++;
  return count;
}

static bool uiLoadedFilamentLow(const BambuState& s) {
  const int8_t i=uiLoadedTray(s);
  return i>=0 && s.ams.trays[i].present && s.ams.trays[i].remain>=0 && s.ams.trays[i].remain<=15;
}

static void uiAttentionStrip(const HubRect& r,const BambuState* s) {
  const bool wifi=WiFi.status()==WL_CONNECTED;
  const int rssi=wifi?WiFi.RSSI():-100;
  const char* msg="No attention items";
  uint16_t c=UI_GREEN;
  if(!wifi){msg="Wi-Fi is offline";c=UI_RED;}
  else if(rssi<-75){msg="Wi-Fi signal is weak";c=UI_AMBER;}
  else if(s && !s->connected){msg="Printer connection needs attention";c=UI_AMBER;}
  else if(s && uiHmsCount(*s)){msg="Printer has an active alert";c=UI_AMBER;}
  else if(s && uiLoadedFilamentLow(*s)){msg="Loaded filament is low";c=UI_AMBER;}
  uiPanelFill(r.x,r.y,r.w,r.h);
  tft.fillCircle(r.x+13,r.y+r.h/2,4,c);
  uiDrawFit(msg,r.x+25,r.y+r.h/2,r.w-37,FONT_BODY,ML_DATUM,c,UI_PANEL_2);
}

static void uiMiniLabelValue(const HubRect& r,const char* label,const char* value,
                             uint16_t accent,const char* detail=nullptr) {
  uiCard(r.x,r.y,r.w,r.h,accent,false);
  uiSectionLabel(r.x+10,r.y+8,label,accent,r.w-22);
  uiDrawFit(value,r.x+10,r.y+31,r.w-20,FONT_BODY,TL_DATUM,UI_TEXT,UI_PANEL);
  if(detail && *detail) uiDrawFit(detail,r.x+10,r.y+r.h-10,r.w-20,FONT_SMALL,BL_DATUM,UI_DIM,UI_PANEL);
}

static void uiMaterialSlot(const HubRect& r,const AmsTray* tr,bool active,uint8_t index,bool compact) {
  const bool present=tr&&tr->present;
  uint16_t filament=present?tr->colorRgb565:UI_BORDER;
  if(present && filament==0) filament=0x1082; // keep black filament visible on dark UI.
  const uint16_t bg=active?UI_PANEL_3:UI_PANEL_2;
  tft.fillRoundRect(r.x,r.y,r.w,r.h,8,bg);
  tft.drawRoundRect(r.x,r.y,r.w,r.h,8,active?UI_ORANGE:UI_BORDER_2);
  if(active)tft.fillRoundRect(r.x+3,r.y+7,3,r.h-14,2,UI_ORANGE);
  char slot[6];snprintf(slot,sizeof(slot),"A%u",(unsigned)(index+1));
  char remain[12];if(present&&tr->remain>=0)snprintf(remain,sizeof(remain),"%d%%",(int)tr->remain);else strlcpy(remain,"—",sizeof(remain));
  const char* type=present&&tr->type[0]?tr->type:"EMPTY";
  const char* color=present?uiFilamentColorName(tr->colorRgb565):"";
  if(compact){
    uiSpoolScaled(r.x+17,r.y+r.h/2,filament,active,present?tr->remain:-1,10);
    uiDrawFit(slot,r.x+32,r.y+7,r.w-39,FONT_SMALL,TL_DATUM,active?UI_ORANGE:UI_MUTED,bg);
    uiDrawFit(type,r.x+32,r.y+22,r.w-39,FONT_BODY,TL_DATUM,present?UI_TEXT:UI_MUTED,bg);
    if(present) uiDrawFit(color,r.x+32,r.y+r.h-8,r.w-66,FONT_SMALL,BL_DATUM,UI_DIM,bg);
    uiDrawFit(remain,r.x+r.w-7,r.y+r.h-8,38,FONT_BODY,BR_DATUM,active?UI_ORANGE:UI_TEXT,bg);
  }else{
    const int16_t cx=r.x+r.w/2;
    uiDrawFit(slot,r.x+8,r.y+7,r.w-16,FONT_SMALL,TL_DATUM,active?UI_ORANGE:UI_MUTED,bg);
    uiDrawFit(remain,r.x+r.w-8,r.y+7,42,FONT_BODY,TR_DATUM,active?UI_ORANGE:UI_TEXT,bg);
    uiSpoolScaled(cx,r.y+32,filament,active,present?tr->remain:-1,12);
    uiDrawFit(type,cx,r.y+51,r.w-10,FONT_BODY,TC_DATUM,present?UI_TEXT:UI_MUTED,bg);
    if(present) uiDrawFit(color,cx,r.y+r.h-8,r.w-10,FONT_SMALL,BC_DATUM,UI_DIM,bg);
  }
}


static void drawAmsCompact(const HubRect&r,const BambuState&s) {
  uiCard(r.x,r.y,r.w,r.h,UI_BORDER,false);uiSectionLabel(r.x+10,r.y+8,"AMS / FILAMENT",UI_ORANGE,r.w-28);
  if(s.ams.present && s.ams.activeTray<4){char loaded[20];snprintf(loaded,sizeof(loaded),"A%d LOADED",(int)s.ams.activeTray+1);uiDrawFit(loaded,r.x+r.w-10,r.y+8,r.w/2,FONT_SMALL,TR_DATUM,UI_ORANGE,UI_PANEL);}
  uint8_t trayCount=s.ams.present?s.ams.unitCount*4:0;if(trayCount>4)trayCount=4;
  if(!trayCount){uiDrawFit(s.connected?"No AMS / external spool data":"Material data unavailable while offline",r.x+r.w/2,r.y+r.h/2+8,r.w-24,FONT_SMALL,MC_DATUM,UI_DIM,UI_PANEL);return;}
  if(r.w<230){const int16_t gap=6,top=r.y+28,cellW=(r.w-20-gap)/2,cellH=(r.h-34-gap)/2;for(uint8_t i=0;i<4;i++){HubRect sr=hr(r.x+10+(i%2)*(cellW+gap),top+(i/2)*(cellH+gap),cellW,cellH);uiMaterialSlot(sr,(i<trayCount)?&s.ams.trays[i]:nullptr,s.ams.activeTray==i,i,true);}}
  else if(r.h>=100){const int16_t gap=5,top=r.y+28,cellW=(r.w-20-3*gap)/4;for(uint8_t i=0;i<4;i++){HubRect sr=hr(r.x+10+i*(cellW+gap),top,cellW,r.h-36);uiMaterialSlot(sr,(i<trayCount)?&s.ams.trays[i]:nullptr,s.ams.activeTray==i,i,false);}}
  else{const int16_t cell=(r.w-20)/4,cy=r.y+r.h/2+3;for(uint8_t i=0;i<4;i++){int16_t cx=r.x+10+cell/2+i*cell;if(i<trayCount&&s.ams.trays[i].present){const AmsTray&tr=s.ams.trays[i];uiSpoolScaled(cx,cy,tr.colorRgb565,s.ams.activeTray==i,tr.remain,11);uiSpoolCaption(cx,cy+15,tr.type,tr.remain,cell-6);}else tft.drawCircle(cx,cy,10,UI_BORDER);}}
}

static const char* uiHomeEyebrow(const BambuState& s) {
  if(!s.connected) return "PRINTER OFFLINE";
  if(s.gcodeStateId==GCODE_PAUSE) return "PRINT PAUSED";
  if(s.gcodeStateId==GCODE_FAILED) return "PRINT NEEDS ATTENTION";
  if(s.printing) return "NOW PRINTING";
  return "READY TO PRINT";
}

static void uiHomeStatusStrip(const HubRect& r,const BambuState& s) {
  uiPanelFill(r.x,r.y,r.w,r.h);
  char line[96];uint16_t c=UI_GREEN;
  if(!s.connected){strlcpy(line,"OFFLINE • check printer LAN / MQTT connection",sizeof(line));c=UI_RED;}
  else if(uiHmsCount(s)){snprintf(line,sizeof(line),"ATTENTION • %u printer alert%s • WiFi %d dBm",(unsigned)uiHmsCount(s),uiHmsCount(s)==1?"":"s",(int)s.wifiSignal);c=UI_AMBER;}
  else{snprintf(line,sizeof(line),"ALL CLEAR • WiFi %d dBm • %s",(int)s.wifiSignal,uiSpeedText(s.speedLevel));c=UI_GREEN;}
  tft.fillCircle(r.x+12,r.y+r.h/2,4,c);uiDrawFit(line,r.x+23,r.y+r.h/2,r.w-34,FONT_SMALL,ML_DATUM,c,UI_PANEL_2);
}

static void uiHomeMaterialPreview(const HubRect& r,const BambuState* s) {
  if(!s || !s->ams.present) return;
  uint8_t n=s->ams.unitCount*4; if(n>4)n=4;
  if(!n) return;
  const int16_t y=r.y+r.h-23;
  const int16_t start=r.x+14;
  const int16_t step=(r.w-28)/4;
  for(uint8_t i=0;i<4;i++) {
    const AmsTray* tr=i<n?&s->ams.trays[i]:nullptr;
    const bool present=tr&&tr->present;
    uint16_t c=present?tr->colorRgb565:UI_BORDER;
    if(present&&c==0)c=0x1082;
    const int16_t x=start+i*step+step/2;
    tft.fillCircle(x,y,7,UI_PANEL_2);
    tft.drawCircle(x,y,7,s->ams.activeTray==i?UI_ORANGE:UI_BORDER_2);
    if(present)tft.fillCircle(x,y,4,c);
  }
}


static uint16_t uiSignatureHeroColor(const BambuState* s) {
  if (WiFi.status()!=WL_CONNECTED) return UI_RED;
  if (!recoveryWebReady()) return UI_AMBER;
  if (!s) return UI_CYAN;
  if (!s->connected) return UI_AMBER;
  if (s->gcodeStateId==GCODE_FAILED || uiHmsCount(*s)) return UI_RED;
  if (s->gcodeStateId==GCODE_PAUSE) return UI_AMBER;
  if (uiLoadedFilamentLow(*s)) return UI_AMBER;
  if (g_workshopTimerDone) return UI_AMBER;
  if (s->printing) return UI_ORANGE;
  return UI_GREEN;
}

static const char* uiSignatureHeroTitle(const BambuState* s) {
  if (WiFi.status()!=WL_CONNECTED) return "NETWORK OFFLINE";
  if (!recoveryWebReady()) return "WORKSHOP STARTING";
  if (!s) return "READY TO SET UP";
  if (!s->connected) return "PRINTER NEEDS ATTENTION";
  if (s->gcodeStateId==GCODE_FAILED || uiHmsCount(*s)) return "ATTENTION NEEDED";
  if (s->gcodeStateId==GCODE_PAUSE) return "PRINT PAUSED";
  if (uiLoadedFilamentLow(*s)) return "FILAMENT LOW";
  if (g_workshopTimerDone) return "TIMER COMPLETE";
  if (s->printing) return "PRINT IN PROGRESS";
  return "WORKSHOP READY";
}

static void uiSignatureHero(const HubRect& r,const PrinterSlot* p,const BambuState* s) {
  const uint16_t stateColor=uiSignatureHeroColor(s);
  uiCard(r.x,r.y,r.w,r.h,stateColor,true);
  const char* title=uiSignatureHeroTitle(s);
  uiDrawFit(title,r.x+14,r.y+16,r.w-28,hubLandscape()?FONT_LARGE:FONT_BODY,TL_DATUM,UI_TEXT,UI_PANEL);

  // v11.19: the physical hero is deliberately two-line. The third idle helper
  // used in v11.18 competed with the state detail on the 86px landscape card.
  char context[100];
  if(workshopTimerActive()||g_workshopTimerDone){
    char tt[28];workshopTimerText(tt,sizeof(tt));snprintf(context,sizeof(context),"Timer • %s",tt);
  }else if(g_workshopNote[0]){
    snprintf(context,sizeof(context),"Note • %s",g_workshopNote);
  }else if(!s){
    strlcpy(context,"Add a printer when ready",sizeof(context));
  }else if(s->printing){
    char rem[22];formatDuration(s->remainingMinutes,rem,sizeof(rem));
    snprintf(context,sizeof(context),"%u%% • %s left • %s",(unsigned)s->progress,rem,p&&p->config.name[0]?p->config.name:"Printer");
  }else if(!s->connected){
    snprintf(context,sizeof(context),"%s • Check connection",p&&p->config.name[0]?p->config.name:"Printer");
  }else{
    snprintf(context,sizeof(context),"%s • Ready • %u material%s",p&&p->config.name[0]?p->config.name:"Printer",(unsigned)uiMaterialCount(*s),uiMaterialCount(*s)==1?"":"s");
  }
  uiDrawFit(context,r.x+14,r.y+51,r.w-28,FONT_SMALL,TL_DATUM,
            (workshopTimerActive()||g_workshopTimerDone)?uiExperienceAccent():UI_DIM,UI_PANEL);
}

static void uiSignatureMaterialRail(const HubRect& r,const BambuState* s);

static void drawAmbientHome(const PrinterSlot* p,const BambuState* s) {
  const int16_t W=tft.width(),H=tft.height();
  const uint16_t accent=uiExperienceAccent();
  tft.fillScreen(UI_BG);
  char clockText[12],dateText[24];uiClockText(clockText,sizeof(clockText));uiClockDateText(dateText,sizeof(dateText));
  const bool online=WiFi.status()==WL_CONNECTED;
  tft.fillCircle(W-18,18,3,online?UI_GREEN:UI_RED);
  uiDrawFit(clockText[0]?clockText:"--:--",hubLandscape()?22:W/2,hubLandscape()?34:48,hubLandscape()?160:W-24,FONT_LARGE,hubLandscape()?TL_DATUM:TC_DATUM,UI_TEXT,UI_BG);
  uiDrawFit(dateText,hubLandscape()?24:W/2,hubLandscape()?66:80,hubLandscape()?190:W-28,FONT_BODY,hubLandscape()?TL_DATUM:TC_DATUM,UI_DIM,UI_BG);

  const char* title=uiSignatureHeroTitle(s);
  uiDrawFit(title,hubLandscape()?24:W/2,hubLandscape()?104:126,hubLandscape()?W-48:W-30,FONT_LARGE,hubLandscape()?TL_DATUM:TC_DATUM,uiSignatureHeroColor(s),UI_BG);
  char detail[96];
  if(s&&s->printing){char rem[20];formatDuration(s->remainingMinutes,rem,sizeof(rem));snprintf(detail,sizeof(detail),"%u%% • %s left",(unsigned)s->progress,rem);}
  else if(s&&s->connected) snprintf(detail,sizeof(detail),"%s • ready",p&&p->config.name[0]?p->config.name:"Printer");
  else strlcpy(detail,"Workshop OS",sizeof(detail));
  uiDrawFit(detail,hubLandscape()?24:W/2,hubLandscape()?139:160,hubLandscape()?W-48:W-30,FONT_BODY,hubLandscape()?TL_DATUM:TC_DATUM,UI_TEXT,UI_BG);
  if(s&&s->printing) uiProgressBar(hubLandscape()?24:18,hubLandscape()?164:186,hubLandscape()?W-48:W-36,s->progress,accent);

  HubRect rail=hubLandscape()?hr(22,184,W-44,76):hr(16,218,W-32,116);
  uiSignatureMaterialRail(rail,s);
  char footer[96];
  if(workshopTimerActive()||g_workshopTimerDone){char tt[28];workshopTimerText(tt,sizeof(tt));snprintf(footer,sizeof(footer),"Timer • %s",tt);}
  else if(g_workshopNote[0]) snprintf(footer,sizeof(footer),"%s",g_workshopNote);
  else strlcpy(footer,"Tap anywhere to open Workshop OS",sizeof(footer));
  uiDrawFit(footer,W/2,H-24,W-32,FONT_SMALL,MC_DATUM,g_workshopNote[0]?UI_TEXT:UI_MUTED,UI_BG);
  hubMarkFrameDirty();g_dirty=false;
}


static void uiSignatureMaterialRail(const HubRect& r,const BambuState* s) {
  const uint16_t accent=uiExperienceAccent();
  uiCard(r.x,r.y,r.w,r.h,accent,false);
  uiSectionLabel(r.x+11,r.y+8,"MATERIALS",accent,r.w-86);
  if (!s || !s->ams.present) {
    uiDrawFit(s&&s->connected?"EXTERNAL SPOOL":"MATERIALS OFFLINE",
              r.x+12,r.y+42,r.w-24,FONT_LARGE,TL_DATUM,UI_TEXT,UI_PANEL);
    uiDrawFit(s&&s->connected?"AMS not reporting • tap for material details":"Printer connection unavailable",
              r.x+12,r.y+75,r.w-24,FONT_SMALL,TL_DATUM,UI_DIM,UI_PANEL);
    return;
  }
  uint8_t n=s->ams.unitCount*4;if(n>4)n=4;
  if (s->ams.activeTray<4) {
    char loaded[18];snprintf(loaded,sizeof(loaded),"A%d LOADED",(int)s->ams.activeTray+1);
    uiDrawFit(loaded,r.x+r.w-12,r.y+9,80,FONT_SMALL,TR_DATUM,accent,UI_PANEL);
  }
  const int16_t left=r.x+10,top=r.y+31,gap=4,cellW=(r.w-20-3*gap)/4;
  if(r.h<92){
    for(uint8_t i=0;i<4;i++){
      const AmsTray* tr=i<n?&s->ams.trays[i]:nullptr;const bool present=tr&&tr->present,active=s->ams.activeTray==i;const int16_t x=left+i*(cellW+gap),cx=x+cellW/2;
      char slot[5];snprintf(slot,sizeof(slot),"A%u",(unsigned)(i+1));uiDrawFit(slot,cx,top-2,cellW-4,FONT_SMALL,TC_DATUM,active?accent:UI_MUTED,UI_PANEL);
      if(present){uint16_t fc=tr->colorRgb565;if(fc==0)fc=0x1082;uiSpoolScaled(cx,top+21,fc,active,tr->remain,9);char meta[18];if(tr->remain>=0)snprintf(meta,sizeof(meta),"%s %d%%",tr->type[0]?tr->type:"FIL",(int)tr->remain);else strlcpy(meta,tr->type[0]?tr->type:"FIL",sizeof(meta));uiDrawFit(meta,cx,r.y+r.h-7,cellW-4,FONT_SMALL,BC_DATUM,tr->remain>=0&&tr->remain<=15?UI_AMBER:UI_TEXT,UI_PANEL);}
      else{tft.drawCircle(cx,top+21,8,UI_BORDER);uiDrawFit("EMPTY",cx,r.y+r.h-7,cellW-4,FONT_SMALL,BC_DATUM,UI_MUTED,UI_PANEL);}
    }
    return;
  }
  for(uint8_t i=0;i<4;i++) {
    const AmsTray* tr=i<n?&s->ams.trays[i]:nullptr;
    const bool present=tr&&tr->present,active=s->ams.activeTray==i;
    const int16_t x=left+i*(cellW+gap),cx=x+cellW/2;
    if(i)tft.drawFastVLine(x-2,top+3,r.h-43,UI_BORDER_2);
    char slot[5];snprintf(slot,sizeof(slot),"A%u",(unsigned)(i+1));
    uiDrawFit(slot,cx,top,cellW-4,FONT_SMALL,TC_DATUM,active?accent:UI_MUTED,UI_PANEL);
    if(present){
      uint16_t fc=tr->colorRgb565;if(fc==0)fc=0x1082;
      uiSpoolScaled(cx,top+29,fc,active,tr->remain,11);
      uiDrawFit(tr->type[0]?tr->type:"FIL",cx,top+49,cellW-4,FONT_SMALL,TC_DATUM,UI_TEXT,UI_PANEL);
      char pct[10];if(tr->remain>=0)snprintf(pct,sizeof(pct),"%d%%",(int)tr->remain);else strlcpy(pct,"—",sizeof(pct));
      uiDrawFit(pct,cx,r.y+r.h-9,cellW-4,FONT_BODY,BC_DATUM,
                tr->remain>=0&&tr->remain<=15?UI_AMBER:(active?accent:UI_TEXT),UI_PANEL);
    }else{
      tft.drawCircle(cx,top+29,10,UI_BORDER);
      uiDrawFit("EMPTY",cx,top+49,cellW-4,FONT_SMALL,TC_DATUM,UI_MUTED,UI_PANEL);
      uiDrawFit("—",cx,r.y+r.h-9,cellW-4,FONT_BODY,BC_DATUM,UI_MUTED,UI_PANEL);
    }
  }
}

static void uiSignaturePrinterCard(const HubRect& r,const PrinterSlot* p,const BambuState* s) {
  const uint16_t c=s?uiStateColor(*s):UI_CYAN;
  uiCard(r.x,r.y,r.w,r.h,c,false);
  uiSectionLabel(r.x+11,r.y+8,"PRINTER",c,r.w-34);
  const char* name=p&&p->config.name[0]?p->config.name:"NOT SET UP";
  if(r.h<90){
    uiDrawFit(name,r.x+11,r.y+31,r.w-22,FONT_BODY,TL_DATUM,UI_TEXT,UI_PANEL);
    if(!s){uiDrawFit("Tap to configure",r.x+11,r.y+r.h-9,r.w-22,FONT_SMALL,BL_DATUM,UI_DIM,UI_PANEL);return;}
    uiPill(r.x+r.w-83,r.y+7,72,uiPrinterStateLabel(*s),c);
    char summary[42];
    if(s->printing)snprintf(summary,sizeof(summary),"%u%% • L%u/%u",(unsigned)s->progress,(unsigned)s->layerNum,(unsigned)s->totalLayers);
    else strlcpy(summary,s->connected?"Ready for next job":"Connection check",sizeof(summary));
    uiDrawFit(summary,r.x+11,r.y+r.h-9,r.w-22,FONT_SMALL,BL_DATUM,s->connected?UI_DIM:UI_AMBER,UI_PANEL);
    return;
  }
  uiDrawFit(name,r.x+11,r.y+35,r.w-22,FONT_LARGE,TL_DATUM,UI_TEXT,UI_PANEL);
  if(!s){uiDrawFit("Tap to configure",r.x+11,r.y+72,r.w-22,FONT_SMALL,TL_DATUM,UI_DIM,UI_PANEL);return;}
  uiPill(r.x+11,r.y+64,hubLandscape()?82:92,uiPrinterStateLabel(*s),c);
  if(s->printing){
    char line[42];snprintf(line,sizeof(line),"%u%% • L%u/%u",(unsigned)s->progress,(unsigned)s->layerNum,(unsigned)s->totalLayers);
    uiDrawFit(line,r.x+11,r.y+r.h-13,r.w-22,FONT_SMALL,BL_DATUM,UI_DIM,UI_PANEL);
    uiProgressBar(r.x+11,r.y+r.h-9,r.w-22,s->progress,UI_ORANGE);
  }else{
    uiDrawFit(s->connected?"Ready for next job":"Connection check",
              r.x+11,r.y+r.h-13,r.w-22,FONT_SMALL,BL_DATUM,s->connected?UI_DIM:UI_AMBER,UI_PANEL);
  }
  const int16_t ax=r.x+r.w-17,ay=r.y+15;
  tft.drawLine(ax-3,ay-4,ax+1,ay,c);tft.drawLine(ax+1,ay,ax-3,ay+4,c);
}

static void uiSignatureServiceChip(const HubRect& r,const char* label,const char* value,
                                   uint16_t c,bool dim=false) {
  tft.fillRoundRect(r.x,r.y,r.w,r.h,8,UI_PANEL_2);
  tft.drawRoundRect(r.x,r.y,r.w,r.h,8,UI_BORDER_2);
  tft.fillCircle(r.x+11,r.y+(hubLandscape()?r.h/2:13),3,c);
  if(hubLandscape()){
    const int16_t valueW=58;
    uiDrawFit(label,r.x+19,r.y+r.h/2,r.w-27-valueW,FONT_SMALL,ML_DATUM,UI_MUTED,UI_PANEL_2);
    uiDrawFit(value,r.x+r.w-8,r.y+r.h/2,valueW,FONT_SMALL,MR_DATUM,dim?UI_DIM:c,UI_PANEL_2);
  }else{
    uiDrawFit(label,r.x+18,r.y+8,r.w-24,FONT_SMALL,TL_DATUM,UI_MUTED,UI_PANEL_2);
    uiDrawFit(value,r.x+9,r.y+29,r.w-18,FONT_SMALL,TL_DATUM,dim?UI_DIM:c,UI_PANEL_2);
  }
}

// ---------------------------------------------------------------------------
// Workshop OS v11.25 — whole-device 480x320 product UI
// ---------------------------------------------------------------------------
enum HubPrinterMode : uint8_t { HUB_PRINTER_STATUS=0, HUB_PRINTER_AMS=1, HUB_PRINTER_CONTROL=2 };

static HubRect hubV1125PrinterModeRect(uint8_t i) {
  const int16_t W=tft.width(), m=8, g=6;
  const int16_t cw=(W-2*m-2*g)/3;
  const int16_t x=m+i*(cw+g);
  return hr(x,48,i==2?W-m-x:cw,50);
}

static HubRect hubV1125MoreRect(uint8_t i) {
  const int16_t W=tft.width();
  if(hubLandscape()) {
    const int16_t m=8,g=8,cw=(W-2*m-g)/2,ch=78;
    return hr(m+(i%2)*(cw+g),48+(i/2)*(ch+8),cw,ch);
  }
  const int16_t m=10,g=10,cw=(W-2*m-g)/2,ch=126;
  return hr(m+(i%2)*(cw+g),52+(i/2)*(ch+10),cw,ch);
}

static void hubV1125Card(const HubRect& r,uint16_t rail=UI_BORDER_2,bool strong=false) {
  const uint16_t bg=strong?C10_SURFACE_2:C10_SURFACE;
  tft.fillRoundRect(r.x,r.y,r.w,r.h,16,bg);
  const bool semantic=rail!=UI_BORDER_2 && rail!=UI_BORDER && rail!=W25_LINE;
  if(semantic)tft.fillCircle(r.x+r.w-15,r.y+15,4,rail);
}

static uint16_t hubV1125PrinterColor(const BambuState* s) {
  if(!s) return W25_ACCENT;
  if(!s->connected) return W25_MUTED;
  if(s->gcodeStateId==GCODE_FAILED || uiHmsCount(*s)) return W25_DANGER;
  if(s->gcodeStateId==GCODE_PAUSE) return W25_WARN;
  if(s->printing) return W25_ACCENT;
  return W25_SUCCESS;
}

static const char* hubV1125PrinterTitle(const BambuState* s) {
  if(!s) return "SET UP PRINTER";
  if(!s->connected) return "PRINTER OFFLINE";
  if(s->gcodeStateId==GCODE_FAILED || uiHmsCount(*s)) return "ATTENTION NEEDED";
  if(s->gcodeStateId==GCODE_PAUSE) return "PRINT PAUSED";
  if(s->printing) return "PRINTING";
  return "READY";
}

static void hubV1125ModeTabs() {
  static const char* labels[3]={"Status","AMS","Control"};
  const int16_t W=tft.width(); HubRect group=hr(8,44,W-16,48);
  tft.fillRoundRect(group.x,group.y,group.w,group.h,14,C10_SURFACE);
  for(uint8_t i=0;i<3;i++) { HubRect r=hubV1125PrinterModeRect(i); const bool selected=g_printerMode==i;
    const uint16_t bg=selected?C10_SURFACE_3:C10_SURFACE;
    if(selected)tft.fillRoundRect(r.x+4,r.y+4,r.w-8,r.h-8,11,bg);
    uiDrawFit(labels[i],r.x+r.w/2,r.y+r.h/2,r.w-18,FONT_BODY,MC_DATUM,selected?C10_TEXT:C10_MUTED,bg); }
}

static void hubV1125Action(const HubRect& r,const char* label,uint16_t c,bool enabled=true,bool destructive=false) {
  const uint16_t bg=enabled?C10_SURFACE_2:C10_SURFACE; const uint16_t text=!enabled?C10_MUTED:(destructive?C10_RED:C10_TEXT);
  tft.fillRoundRect(r.x,r.y,r.w,r.h,14,bg); if(enabled)tft.fillCircle(r.x+17,r.y+r.h/2,4,destructive?C10_RED:c);
  uiDrawFit(label,r.x+r.w/2+5,r.y+r.h/2,r.w-42,FONT_BODY,MC_DATUM,text,bg);
}

static void hubV1125TelemetryColumn(const HubRect& r,const BambuState& s) {
  hubV1125Card(r,s.connected?C10_GREEN:C10_ORANGE,false); uiDrawFit("Temperatures",r.x+14,r.y+12,r.w-28,FONT_SMALL,TL_DATUM,C10_MUTED,C10_SURFACE);
  const char* labels[3]={"Nozzle","Bed","Chamber"}; char vals[3][14];
  if(s.connected){snprintf(vals[0],14,"%.0f C",s.nozzleTemp);snprintf(vals[1],14,"%.0f C",s.bedTemp);snprintf(vals[2],14,"%.0f C",s.chamberTemp);}else for(uint8_t i=0;i<3;i++)strlcpy(vals[i],"--",14);
  const int16_t top=r.y+34,row=(r.h-38)/3; for(uint8_t i=0;i<3;i++){if(i)tft.drawFastHLine(r.x+14,top+i*row,r.w-28,C10_SEPARATOR);uiDrawFit(labels[i],r.x+14,top+i*row+row/2,r.w/2-18,FONT_SMALL,ML_DATUM,C10_MUTED,C10_SURFACE);uiDrawFit(vals[i],r.x+r.w-14,top+i*row+row/2,r.w/2-18,FONT_BODY,MR_DATUM,s.connected?C10_TEXT:C10_MUTED,C10_SURFACE);}
}

static void hubV1125AmsSlot(const HubRect& r,const AmsTray* tr,bool active,uint8_t index) {
  const bool present=tr&&tr->present; const uint16_t bg=active?C10_SURFACE_3:C10_SURFACE; tft.fillRoundRect(r.x,r.y,r.w,r.h,14,bg); if(active)tft.fillCircle(r.x+r.w-14,r.y+14,4,C10_ACCENT);
  char slot[8];snprintf(slot,sizeof(slot),"%u",(unsigned)(index+1)); char remain[12]; if(present&&tr->remain>=0)snprintf(remain,sizeof(remain),"%d%%",(int)tr->remain);else strlcpy(remain,"--",sizeof(remain));
  uiDrawFit(slot,r.x+12,r.y+10,28,FONT_BODY,TL_DATUM,active?C10_ACCENT:C10_MUTED,bg);uiDrawFit(remain,r.x+r.w-12,r.y+10,42,FONT_SMALL,TR_DATUM,present?C10_TEXT:C10_MUTED,bg);
  uint16_t filament=present?tr->colorRgb565:C10_SEPARATOR;if(present&&filament==0)filament=0x1082;uiSpoolScaled(r.x+r.w/2,r.y+49,filament,active,present?tr->remain:-1,13);uiDrawFit(present&&tr->type[0]?tr->type:"Empty",r.x+r.w/2,r.y+74,r.w-18,FONT_BODY,TC_DATUM,present?C10_TEXT:C10_MUTED,bg);
}

static void drawHome(bool full) {
  (void)full; const int16_t W=tft.width(); const bool configured=isAnyPrinterConfigured(); const PrinterSlot* p=configured?&displayedPrinter():nullptr; const BambuState* s=p?&p->state:nullptr;
  if(g_ambientEnabled&&g_ambientActive){drawAmbientHome(p,s);return;} tft.fillScreen(C10_BG);drawHeader("Home",nullptr,0);uiBottomNav(0,nullptr);
  const bool paused=s&&s->gcodeStateId==GCODE_PAUSE; const bool printing=s&&s->printing; const bool online=s&&s->connected; const bool wifi=WiFi.status()==WL_CONNECTED; const bool alert=s&&uiHmsCount(*s)>0;
  const uint16_t sc=!configured?C10_MUTED:(!online?C10_ORANGE:(alert?C10_RED:(paused?C10_ORANGE:(printing?C10_ACCENT:C10_GREEN))));
  const char* state=!configured?"Set Up":(!online?"Offline":(alert?"Needs Attention":(paused?"Paused":(printing?"Printing":"Ready"))));
  if(hubLandscape()) {
    HubRect hero=hr(8,44,W-16,216); hubV1125Card(hero,sc,true);
    uiDrawFit(p&&p->config.name[0]?p->config.name:"Workshop OS",hero.x+18,hero.y+16,hero.w-36,FONT_SMALL,TL_DATUM,C10_MUTED,C10_SURFACE_2);
    uiDrawFit(state,hero.x+18,hero.y+46,hero.w-36,FONT_LARGE,TL_DATUM,sc,C10_SURFACE_2);
    if(alert){char a[48];snprintf(a,sizeof(a),"%u printer alert%s",(unsigned)uiHmsCount(*s),uiHmsCount(*s)==1?"":"s");uiDrawFit(a,hero.x+18,hero.y+96,hero.w-36,FONT_BODY,TL_DATUM,C10_TEXT,C10_SURFACE_2);uiDrawFit("Open Printer to review",hero.x+18,hero.y+190,hero.w-36,FONT_SMALL,BL_DATUM,C10_MUTED,C10_SURFACE_2);}
    else if(printing||paused){uiDrawFit(jobDisplayName(*s),hero.x+18,hero.y+92,hero.w-36,FONT_BODY,TL_DATUM,C10_TEXT,C10_SURFACE_2);uiProgressBar(hero.x+18,hero.y+130,hero.w-36,s->progress,C10_ACCENT);char rem[20],meta[40];formatDuration(s->remainingMinutes,rem,sizeof(rem));snprintf(meta,sizeof(meta),"%u%%  -  %s left",(unsigned)s->progress,rem);uiDrawFit(meta,hero.x+18,hero.y+156,hero.w-36,FONT_BODY,TL_DATUM,C10_TEXT,C10_SURFACE_2);uiDrawFit(paused?"Print paused":"Printing normally",hero.x+18,hero.y+190,hero.w-36,FONT_SMALL,BL_DATUM,paused?C10_ORANGE:C10_MUTED,C10_SURFACE_2);}
    else {const char* detail=!configured?"Connect your printer to begin":(!online?"Printer connection unavailable":(!wifi?"Network connection unavailable":"Everything is ready"));uiDrawFit(detail,hero.x+18,hero.y+98,hero.w-36,FONT_BODY,TL_DATUM,C10_TEXT,C10_SURFACE_2);uiDrawFit(!configured?"Open Settings to configure Local Access":(!online?"Open Printer to reconnect":"Tap Printer for status and controls"),hero.x+18,hero.y+190,hero.w-36,FONT_SMALL,BL_DATUM,C10_MUTED,C10_SURFACE_2);}
    if(g_workshopTimerDone){tft.fillRoundRect(hero.x+hero.w-142,hero.y+16,124,30,15,C10_SURFACE_3);uiDrawFit("Timer Done",hero.x+hero.w-80,hero.y+31,104,FONT_SMALL,MC_DATUM,C10_ORANGE,C10_SURFACE_3);}else if(workshopTimerActive()){char tv[18];workshopTimerText(tv,sizeof(tv),true);tft.fillRoundRect(hero.x+hero.w-142,hero.y+16,124,30,15,C10_SURFACE_3);uiDrawFit(tv,hero.x+hero.w-80,hero.y+31,104,FONT_SMALL,MC_DATUM,C10_ACCENT,C10_SURFACE_3);}
  } else {
    HubRect hero=hr(8,44,W-16,366);hubV1125Card(hero,sc,true);uiDrawFit(p&&p->config.name[0]?p->config.name:"Workshop OS",hero.x+16,hero.y+18,hero.w-32,FONT_SMALL,TL_DATUM,C10_MUTED,C10_SURFACE_2);uiDrawFit(state,hero.x+16,hero.y+58,hero.w-32,FONT_LARGE,TL_DATUM,sc,C10_SURFACE_2);
    if(printing||paused){uiDrawFit(jobDisplayName(*s),hero.x+16,hero.y+126,hero.w-32,FONT_BODY,TL_DATUM,C10_TEXT,C10_SURFACE_2);uiProgressBar(hero.x+16,hero.y+178,hero.w-32,s->progress,C10_ACCENT);char meta[28];snprintf(meta,sizeof(meta),"%u%% complete",(unsigned)s->progress);uiDrawFit(meta,hero.x+16,hero.y+208,hero.w-32,FONT_BODY,TL_DATUM,C10_TEXT,C10_SURFACE_2);}else uiDrawFit(!configured?"Connect your printer to begin":(online?"Everything is ready":"Check the printer connection"),hero.x+16,hero.y+132,hero.w-32,FONT_BODY,TL_DATUM,C10_TEXT,C10_SURFACE_2);
  }
  hubMarkFrameDirty();g_dirty=false;
}

static void drawPrinter(bool full) {
  (void)full;const int16_t W=tft.width();tft.fillScreen(C10_BG);drawHeader("Printer",nullptr,1);uiBottomNav(1,nullptr);hubV1125ModeTabs();
  if(!isAnyPrinterConfigured()){HubRect r=hubLandscape()?hr(8,100,W-16,160):hr(8,100,W-16,310);hubV1125Card(r,C10_ACCENT,true);uiDrawFit("Connect Printer",r.x+16,r.y+28,r.w-32,FONT_LARGE,TL_DATUM,C10_TEXT,C10_SURFACE_2);uiDrawFit("Add LAN or Cloud access in Settings.",r.x+16,r.y+78,r.w-32,FONT_BODY,TL_DATUM,C10_MUTED,C10_SURFACE_2);uiDrawFit("Open Local Access",r.x+16,r.y+r.h-22,r.w-32,FONT_BODY,BL_DATUM,C10_ACCENT,C10_SURFACE_2);hubMarkFrameDirty();g_dirty=false;return;}
  const PrinterSlot& p=displayedPrinter();const BambuState& s=p.state;const bool paused=s.gcodeStateId==GCODE_PAUSE;const bool active=s.printing||paused;const uint16_t sc=!s.connected?C10_ORANGE:(paused?C10_ORANGE:(s.printing?C10_ACCENT:C10_GREEN));const char* state=!s.connected?"Offline":(paused?"Paused":(s.printing?"Printing":"Ready"));
  if(g_printerMode==HUB_PRINTER_STATUS){if(hubLandscape()){HubRect job=hr(8,100,300,160),live=hr(316,100,W-324,160);hubV1125Card(job,sc,true);uiDrawFit(p.config.name[0]?p.config.name:"Printer",job.x+16,job.y+12,job.w-32,FONT_SMALL,TL_DATUM,C10_MUTED,C10_SURFACE_2);uiDrawFit(state,job.x+16,job.y+38,job.w-32,FONT_LARGE,TL_DATUM,sc,C10_SURFACE_2);if(active){char rem[20],meta[42];formatDuration(s.remainingMinutes,rem,sizeof(rem));snprintf(meta,sizeof(meta),"%u%%  -  %s left",(unsigned)s.progress,rem);uiDrawFit(jobDisplayName(s),job.x+16,job.y+82,job.w-32,FONT_BODY,TL_DATUM,C10_TEXT,C10_SURFACE_2);uiProgressBar(job.x+16,job.y+116,job.w-32,s.progress,C10_ACCENT);uiDrawFit(meta,job.x+16,job.y+139,job.w-32,FONT_SMALL,TL_DATUM,C10_MUTED,C10_SURFACE_2);}else uiDrawFit(s.connected?"Ready for the next print":"Check connection settings",job.x+16,job.y+92,job.w-32,FONT_BODY,TL_DATUM,s.connected?C10_TEXT:C10_ORANGE,C10_SURFACE_2);hubV1125TelemetryColumn(live,s);}else{HubRect job=hr(8,100,W-16,154),live=hr(8,262,W-16,148);hubV1125Card(job,sc,true);uiDrawFit(state,job.x+14,job.y+40,job.w-28,FONT_LARGE,TL_DATUM,sc,C10_SURFACE_2);if(active){uiDrawFit(jobDisplayName(s),job.x+14,job.y+84,job.w-28,FONT_BODY,TL_DATUM,C10_TEXT,C10_SURFACE_2);uiProgressBar(job.x+14,job.y+124,job.w-28,s.progress,C10_ACCENT);}hubV1125TelemetryColumn(live,s);}}
  else if(g_printerMode==HUB_PRINTER_AMS){if(hubLandscape()){const int16_t g=6,m=8,cw=(W-2*m-3*g)/4;uint8_t n=s.ams.present?s.ams.unitCount*4:0;if(n>4)n=4;for(uint8_t i=0;i<4;i++)hubV1125AmsSlot(hr(m+i*(cw+g),100,cw,126),(i<n)?&s.ams.trays[i]:nullptr,s.ams.present&&s.ams.activeTray==i,i);uiDrawFit(s.ams.present?"AMS telemetry - inventory identity remains explicit":"No AMS connected",10,249,W-20,FONT_SMALL,BL_DATUM,s.ams.present?C10_MUTED:C10_ORANGE,C10_BG);}else{uint8_t n=s.ams.present?s.ams.unitCount*4:0;if(n>4)n=4;const int16_t g=8,m=8,cw=(W-2*m-g)/2,ch=110;for(uint8_t i=0;i<4;i++)hubV1125AmsSlot(hr(m+(i%2)*(cw+g),100+(i/2)*(ch+g),cw,ch),(i<n)?&s.ams.trays[i]:nullptr,s.ams.present&&s.ams.activeTray==i,i);}}
  else {const char* light=s.lightState==1?"Light Off":"Light On";const char* pause=paused?"Resume":"Pause";const uint8_t plug=tasmotaControlPlugForSlot(rotState.displayIndex);const bool powerMapped=plug!=0xFF;for(uint8_t i=0;i<4;i++){HubRect r=hubPrinterActionRect(i);const char* label=i==0?printerFeedbackLabel(0,light):i==1?printerFeedbackLabel(1,pause):i==2?(powerMapped?"Printer Power":"Power Unavailable"):printerFeedbackLabel(3,active?"Hold to Stop":"Stop");const bool enabled=i==0?s.connected:i==1?(s.connected&&active):i==2?powerMapped:(s.connected&&active);const uint16_t c=i==0?C10_ACCENT:i==1?(paused?C10_GREEN:C10_ACCENT):i==2?C10_ORANGE:C10_RED;hubV1125Action(r,label,c,enabled,i==3);}if(hubLandscape())uiDrawFit(active?"Hold Stop until confirmation completes":"Controls ready",10,250,W-20,FONT_SMALL,BL_DATUM,C10_MUTED,C10_BG);}
  hubMarkFrameDirty();g_dirty=false;
}

static void drawWorkshop(bool full) {
  (void)full;
  const int16_t W=tft.width();
  tft.fillScreen(C10_BG);
  drawHeader("Tools",nullptr,2);
  uiBottomNav(2,nullptr);

  const BambuState* s=isAnyPrinterConfigured()?&displayedPrinter().state:nullptr;
  const uint16_t timerColor=g_workshopTimerDone?C10_ORANGE:
                            (workshopTimerActive()?C10_ACCENT:W25_LINE);

  const workshop::platform::InventoryProjectionState& inv=workshopPlatformInventoryState();
  char inventoryValue[38]="Inventory unknown";
  uint16_t inventoryColor=C10_MUTED;
  if(inv.available) {
    if(inv.quantityState==workshop::platform::InventoryQuantityState::InvalidLineage) {
      strlcpy(inventoryValue,"Evidence lineage invalid",sizeof(inventoryValue)); inventoryColor=C10_RED;
    } else if(inv.quantityState==workshop::platform::InventoryQuantityState::Conflict) {
      strlcpy(inventoryValue,"Quantity conflict · verify",sizeof(inventoryValue)); inventoryColor=C10_ORANGE;
    } else if(inv.quantityState==workshop::platform::InventoryQuantityState::Stale) {
      strlcpy(inventoryValue,"Quantity stale · refresh",sizeof(inventoryValue)); inventoryColor=C10_ORANGE;
    } else if(inv.quantityState==workshop::platform::InventoryQuantityState::Unknown) {
      strlcpy(inventoryValue,"Quantity unknown · weigh",sizeof(inventoryValue));
    } else if(inv.placementState==workshop::platform::InventoryPlacementState::Conflict) {
      strlcpy(inventoryValue,"Placement conflict · verify",sizeof(inventoryValue)); inventoryColor=C10_ORANGE;
    } else if(inv.placementState==workshop::platform::InventoryPlacementState::Stale) {
      strlcpy(inventoryValue,"Placement stale · refresh",sizeof(inventoryValue)); inventoryColor=C10_ORANGE;
    } else if(inv.placementState==workshop::platform::InventoryPlacementState::Unknown) {
      strlcpy(inventoryValue,"Placement unknown",sizeof(inventoryValue));
    } else {
      snprintf(inventoryValue,sizeof(inventoryValue),"%u spools · %u loaded · %u low",
               (unsigned)inv.spoolCount,(unsigned)inv.loadedCount,(unsigned)inv.lowCount);
      inventoryColor=inv.lowCount?C10_ORANGE:C10_GREEN;
    }
  }

  char materialValue[34]="Unknown telemetry";
  if(s&&s->ams.present&&s->ams.activeTray<4&&s->ams.trays[s->ams.activeTray].present) {
    const AmsTray& t=s->ams.trays[s->ams.activeTray];
    snprintf(materialValue,sizeof(materialValue),"AMS %u · %s",
             (unsigned)s->ams.activeTray+1,t.type[0]?t.type:"Filament");
  }

  if(hubLandscape()) {
    HubRect timer=hr(8,44,W-16,112);
    HubRect context=hr(8,164,W-16,40);
    hubV1125Card(timer,timerColor,true);
    hubV1125Card(context,W25_LINE,false);

    uiDrawFit("Timer",timer.x+16,timer.y+12,90,FONT_SMALL,TL_DATUM,C10_MUTED,C10_SURFACE_2);
    char tv[28];workshopTimerText(tv,sizeof(tv));
    uiDrawFit(workshopTimerActive()||g_workshopTimerDone?tv:"Ready",
              timer.x+16,timer.y+40,timer.w-32,FONT_LARGE,TL_DATUM,
              g_workshopTimerDone?C10_ORANGE:C10_TEXT,C10_SURFACE_2);
    uiDrawFit(g_workshopTimerDone?"Timer complete":
              (workshopTimerActive()?"Running":"Open Tools to choose a timer"),
              timer.x+16,timer.y+94,timer.w-32,FONT_SMALL,BL_DATUM,
              g_workshopTimerDone?C10_ORANGE:C10_MUTED,C10_SURFACE_2);

    const int16_t mid=context.x+context.w/2;
    uiDrawFit("Note",context.x+12,context.y+8,48,FONT_SMALL,TL_DATUM,C10_MUTED,C10_SURFACE);
    uiDrawFit(g_workshopNote[0]?g_workshopNote:"None",
              context.x+66,context.y+20,mid-context.x-76,FONT_BODY,ML_DATUM,
              g_workshopNote[0]?C10_TEXT:C10_MUTED,C10_SURFACE);
    tft.drawFastVLine(mid,context.y+8,context.h-16,C10_SEPARATOR);
    uiDrawFit("Inventory",mid+12,context.y+8,58,FONT_SMALL,TL_DATUM,C10_MUTED,C10_SURFACE);
    uiDrawFit(inventoryValue,mid+76,context.y+20,context.x+context.w-mid-88,FONT_BODY,ML_DATUM,
              inventoryColor,C10_SURFACE);

    char timerLab[18];workshopTimerText(timerLab,sizeof(timerLab),true);
    for(uint8_t i=0;i<4;i++) {
      const char* label=i==0?(s&&s->lightState==1?"Light Off":"Light On"):
                        i==1?(g_workshopTimerDone?"Timer Done":(workshopTimerActive()?timerLab:"Tools")):
                        i==2?"System":"Printer";
      const bool enabled=i!=0||(s&&s->connected);
      const uint16_t c=i==1&&g_workshopTimerDone?C10_ORANGE:C10_ACCENT;
      hubV1125Action(hubWorkshopActionRect(i),label,c,enabled,false);
    }
  } else {
    HubRect timer=hr(8,44,W-16,132);
    HubRect context=hr(8,184,W-16,136);
    hubV1125Card(timer,timerColor,true);
    hubV1125Card(context,W25_LINE,false);

    char tv[28];workshopTimerText(tv,sizeof(tv));
    uiDrawFit("Timer",timer.x+14,timer.y+12,timer.w-28,FONT_SMALL,TL_DATUM,C10_MUTED,C10_SURFACE_2);
    uiDrawFit(workshopTimerActive()||g_workshopTimerDone?tv:"Ready",
              timer.x+14,timer.y+48,timer.w-28,FONT_LARGE,TL_DATUM,C10_TEXT,C10_SURFACE_2);
    uiDrawFit(workshopTimerActive()?"Running":"Open Tools to choose a timer",
              timer.x+14,timer.y+108,timer.w-28,FONT_SMALL,BL_DATUM,C10_MUTED,C10_SURFACE_2);

    uiDrawFit("Note",context.x+12,context.y+12,context.w-24,FONT_SMALL,TL_DATUM,C10_MUTED,C10_SURFACE);
    uiDrawFit(g_workshopNote[0]?g_workshopNote:"None",
              context.x+12,context.y+38,context.w-24,FONT_BODY,TL_DATUM,
              g_workshopNote[0]?C10_TEXT:C10_MUTED,C10_SURFACE);
    tft.drawFastHLine(context.x+12,context.y+68,context.w-24,C10_SEPARATOR);
    uiDrawFit("Inventory",context.x+12,context.y+80,context.w-24,FONT_SMALL,TL_DATUM,C10_MUTED,C10_SURFACE);
    uiDrawFit(inventoryValue,context.x+12,context.y+106,context.w-24,FONT_BODY,TL_DATUM,
              inventoryColor,C10_SURFACE);

    for(uint8_t i=0;i<4;i++) {
      const char* label=i==0?(s&&s->lightState==1?"Light Off":"Light On"):
                        i==1?"Tools":i==2?"System":"Printer";
      hubV1125Action(hubWorkshopActionRect(i),label,C10_ACCENT,i!=0||(s&&s->connected),false);
    }
  }

  hubMarkFrameDirty();
  g_dirty=false;
}

static void drawCustom(bool full) {
  (void)full;const int16_t W=tft.width();tft.fillScreen(UI_BG);drawHeader("CUSTOM",g_widgetEditMode?"EDITING":(g_cfg.customUrl[0]?(g_custom.healthy?"LIVE":"FALLBACK"):"LOCAL"),3);uiBottomNav(3,nullptr);const bool useFeed=g_cfg.customUrl[0]&&g_custom.valid&&!g_widgetEditMode;
  if(!hubLandscape()){
    if(useFeed){uiCard(8,45,W-16,78,UI_PURPLE,true);uiDrawFit("LIVE DASHBOARD",20,55,W-150,FONT_SMALL,TL_DATUM,UI_PURPLE,UI_PANEL);uiDrawFit(g_custom.title,20,73,W-40,FONT_LARGE,TL_DATUM,UI_TEXT,UI_PANEL);uiDrawFit(g_custom.subtitle,20,101,W-130,FONT_SMALL,TL_DATUM,UI_DIM,UI_PANEL);uiPill(W-100,93,80,g_custom.healthy?"LIVE":"FEED",g_custom.healthy?UI_GREEN:UI_AMBER);for(uint8_t i=0;i<4;i++){HubRect r=hubCustomRect(i);const char* label=i<g_custom.metricCount?g_custom.metrics[i].label:"WIDGET";const char* value=i<g_custom.metricCount?g_custom.metrics[i].value:"—";static const uint16_t ac[4]={UI_CYAN,UI_ORANGE,UI_GREEN,UI_PURPLE};uiMetric(r.x,r.y,r.w,r.h,label,value,ac[i],"custom feed");}uiPanelFill(8,365,W-16,56);uiDrawFit("Feed connected • fallback widgets remain available",W/2,393,W-32,FONT_SMALL,MC_DATUM,UI_GREEN,UI_PANEL_2);}else{uiCard(8,45,W-16,70,g_cfg.customUrl[0]?UI_AMBER:UI_PURPLE,true);uiDrawFit(g_widgetEditMode?"EDIT MY WIDGETS":"MY WIDGETS",20,58,W-40,FONT_BODY,TL_DATUM,UI_TEXT,UI_PANEL);uiDrawFit(g_cfg.customUrl[0]?"Feed offline • local dashboard is still live":"Long-press anywhere here to customize",20,88,W-40,FONT_SMALL,TL_DATUM,g_cfg.customUrl[0]?UI_AMBER:UI_DIM,UI_PANEL);for(uint8_t i=0;i<4;i++)drawWidgetCard(i,hubCustomRect(i),g_widgetEditMode&&i==g_widgetSelected);uiPanelFill(8,365,W-16,56);uiDrawFit(g_widgetEditMode?"Tap a tile to cycle • long-press to finish":"Your fallback deck is stored on this device",W/2,393,W-32,FONT_SMALL,MC_DATUM,g_widgetEditMode?UI_ORANGE:UI_DIM,UI_PANEL_2);}
  }else{
    uiCard(8,42,W-16,50,useFeed?UI_PURPLE:(g_cfg.customUrl[0]?UI_AMBER:UI_PURPLE),true);uiDrawFit(useFeed?"LIVE DASHBOARD":(g_widgetEditMode?"EDIT MY WIDGETS":"MY WIDGETS"),20,53,126,FONT_SMALL,TL_DATUM,useFeed?UI_PURPLE:UI_TEXT,UI_PANEL);uiDrawFit(useFeed?g_custom.title:(g_cfg.customUrl[0]?"Feed offline • local fallback":"Long-press to customize"),20,72,W-180,FONT_BODY,TL_DATUM,UI_TEXT,UI_PANEL);if(useFeed)uiPill(W-100,52,80,g_custom.healthy?"LIVE":"FEED",g_custom.healthy?UI_GREEN:UI_AMBER);for(uint8_t i=0;i<4;i++){HubRect r=hubCustomRect(i);if(useFeed){static const uint16_t ac[4]={UI_CYAN,UI_ORANGE,UI_GREEN,UI_PURPLE};uiMetric(r.x,r.y,r.w,r.h,i<g_custom.metricCount?g_custom.metrics[i].label:"WIDGET",i<g_custom.metricCount?g_custom.metrics[i].value:"—",ac[i],"custom");}else drawWidgetCard(i,r,g_widgetEditMode&&i==g_widgetSelected);}uiPanelFill(8,224,W-16,40);uiDrawFit(g_widgetEditMode?"Tap a tile to cycle • long-press to finish":"Local custom dashboard",W/2,244,W-32,FONT_SMALL,MC_DATUM,g_widgetEditMode?UI_ORANGE:UI_DIM,UI_PANEL_2);
  }
  hubMarkFrameDirty();g_dirty=false;
}

static void uiMoreIcon(const HubRect& r,uint8_t i,uint16_t c) {
  const int16_t cx=r.x+22,cy=r.y+24;
  tft.fillCircle(cx,cy,13,UI_PANEL_2);tft.drawCircle(cx,cy,13,c);
  if(i==0){tft.drawRect(cx-5,cy-5,10,10,c);tft.drawFastHLine(cx-3,cy,6,c);}
  else if(i==1){tft.drawCircle(cx,cy,6,c);tft.fillCircle(cx,cy,2,c);tft.drawFastVLine(cx,cy-10,4,c);}
  else if(i==2){tft.drawFastHLine(cx-6,cy-4,12,c);tft.drawFastHLine(cx-6,cy,12,c);tft.drawFastHLine(cx-6,cy+4,12,c);tft.fillCircle(cx-2,cy-4,2,c);tft.fillCircle(cx+3,cy,2,c);tft.fillCircle(cx-4,cy+4,2,c);}
  else{tft.drawRect(cx-6,cy-5,12,10,c);tft.fillTriangle(cx-3,cy+1,cx,cy-4,cx+3,cy+1,c);}
}

static void drawTools(bool full) {
  (void)full;
  const int16_t W=tft.width();
  const uint16_t accent=uiExperienceAccent();
  tft.fillScreen(UI_BG);drawHeader("TOOLS",nullptr,3);uiBottomNav(3,nullptr);

  char timerValue[28]; workshopTimerText(timerValue,sizeof(timerValue));
  char timerSub[56];
  if (workshopTimerActive()) snprintf(timerSub,sizeof(timerSub),"%u minute workshop timer",(unsigned)g_workshopTimerStartedMinutes);
  else if (g_workshopTimerDone) strlcpy(timerSub,"Completed • dismiss or start another",sizeof(timerSub));
  else strlcpy(timerSub,"Choose a preset to start",sizeof(timerSub));

  if (hubLandscape()) {
    HubRect hero=hr(8,42,306,92), note=hr(322,42,W-330,92);
    uiCard(hero.x,hero.y,hero.w,hero.h,g_workshopTimerDone?UI_AMBER:accent,true);
    uiSectionLabel(hero.x+12,hero.y+9,"WORKSHOP TIMER",g_workshopTimerDone?UI_AMBER:accent,hero.w-26);
    uiDrawFit(timerValue,hero.x+15,hero.y+35,hero.w-30,FONT_LARGE,TL_DATUM,g_workshopTimerDone?UI_AMBER:UI_TEXT,UI_PANEL);
    uiDrawFit(timerSub,hero.x+15,hero.y+73,hero.w-30,FONT_SMALL,TL_DATUM,UI_DIM,UI_PANEL);
    uiCard(note.x,note.y,note.w,note.h,UI_PURPLE,false);uiSectionLabel(note.x+10,note.y+9,"NOTE",UI_PURPLE,note.w-20);
    uiDrawFit(g_workshopNote[0]?g_workshopNote:"Set in browser",note.x+12,note.y+42,note.w-24,FONT_BODY,ML_DATUM,g_workshopNote[0]?UI_TEXT:UI_DIM,UI_PANEL);
  } else {
    HubRect hero=hr(8,44,W-16,96), note=hr(8,148,W-16,70);
    uiCard(hero.x,hero.y,hero.w,hero.h,g_workshopTimerDone?UI_AMBER:accent,true);uiSectionLabel(hero.x+12,hero.y+9,"WORKSHOP TIMER",g_workshopTimerDone?UI_AMBER:accent,hero.w-26);
    uiDrawFit(timerValue,hero.x+15,hero.y+38,hero.w-30,FONT_LARGE,TL_DATUM,g_workshopTimerDone?UI_AMBER:UI_TEXT,UI_PANEL);uiDrawFit(timerSub,hero.x+15,hero.y+76,hero.w-30,FONT_SMALL,TL_DATUM,UI_DIM,UI_PANEL);
    uiCard(note.x,note.y,note.w,note.h,UI_PURPLE,false);uiSectionLabel(note.x+10,note.y+8,"WORKSHOP NOTE",UI_PURPLE,note.w-20);uiDrawFit(g_workshopNote[0]?g_workshopNote:"Set a note from the browser",note.x+12,note.y+42,note.w-24,FONT_BODY,ML_DATUM,g_workshopNote[0]?UI_TEXT:UI_DIM,UI_PANEL);
  }

  for(uint8_t i=0;i<4;i++){
    char label[12];snprintf(label,sizeof(label),"%u MIN",(unsigned)g_timerPresets[i]);
    uiActionButton(hubToolsPresetRect(i),label,i==0?accent:UI_CYAN,i==0);
  }

  const char* a0=workshopTimerActive()?"CANCEL":(g_workshopTimerDone?"DISMISS":(g_ambientEnabled?"AMBIENT ON":"AMBIENT OFF"));
  uiActionButton(hubToolsActionRect(0),a0,workshopTimerActive()||g_workshopTimerDone?UI_AMBER:accent);
  const uint8_t powerSlot=rotState.displayIndex;
  const uint8_t powerPlug=tasmotaControlPlugForSlot(powerSlot);
  bool powerMapped=(powerPlug!=0xFF);
  bool powerOnline=false,powerOn=false;
  if(powerMapped){TasmotaPlugStatsView pv;tasmotaGetStats(powerPlug,&pv);powerOnline=pv.online;powerOn=pv.powerStateKnown?pv.powerOn:(pv.online&&pv.watts>0.5f);}
  const char* powerLabel=!powerMapped?"NO POWER":(!powerOnline?"POWER ?":(powerOn?"POWER OFF":"POWER ON"));
  uiActionButton(hubToolsActionRect(1),powerLabel,powerMapped&&powerOnline?(powerOn?UI_RED:UI_GREEN):UI_DIM);
  uiActionButton(hubToolsActionRect(2),"SYSTEM",UI_BLUE);
  uiActionButton(hubToolsActionRect(3),"CLASSIC",UI_MUTED);
  hubMarkFrameDirty();g_dirty=false;
}


// ---------------------------------------------------------------------------
// Smart Home v11.8 physical Display & Experience controls
// ---------------------------------------------------------------------------
static uint8_t hubStepPreset(uint8_t current, const uint8_t* values,
                             uint8_t count, bool reverse) {
  if (!values || count == 0) return current;
  if (reverse) {
    for (int8_t i = (int8_t)count - 1; i >= 0; --i) {
      if (values[i] < current) return values[i];
    }
    return values[0];
  }
  for (uint8_t i = 0; i < count; ++i) {
    if (values[i] > current) return values[i];
  }
  return values[count - 1];
}

static uint8_t hubLevelPct(uint8_t level) {
  return (uint8_t)(((uint16_t)level * 100U + 127U) / 255U);
}

static bool hubQuarterPreset(uint8_t level, bool allowZero) {
  if (allowZero && level == 0) return true;
  return level == 64 || level == 128 || level == 192 || level == 255;
}

static void hubFormatPresetPct(uint8_t level, bool allowZero, char* out, size_t outLen) {
  if (!out || outLen == 0) return;
  const unsigned pct = (unsigned)hubLevelPct(level);
  if (hubQuarterPreset(level, allowZero)) snprintf(out, outLen, "%u%%", pct);
  else snprintf(out, outLen, "%u%% CUSTOM", pct);
}

static uint8_t hubAfterPrintMode() {
  if (dpSettings.keepDisplayOn) return 0;       // stay on
  return dpSettings.showClockAfterFinish ? 1 : 2; // clock / display off
}

static const char* hubAfterPrintLabel() {
  switch (hubAfterPrintMode()) {
    case 0: return "STAY ON";
    case 1: return "CLOCK";
    default:return "DISPLAY OFF";
  }
}

static void hubCycleAfterPrint(bool reverse) {
  uint8_t mode = hubAfterPrintMode();
  mode = reverse ? (uint8_t)((mode + 2U) % 3U) : (uint8_t)((mode + 1U) % 3U);
  if (mode == 0) {
    dpSettings.keepDisplayOn = true;
  } else {
    dpSettings.keepDisplayOn = false;
    dpSettings.showClockAfterFinish = (mode == 1);
  }
}

static void hubPersistDisplay(bool applyBacklight) {
  saveSettings();
  if (applyBacklight) setBacklight(getEffectiveBrightness());
  buzzerPlay(BUZZ_CLICK);
  g_dirty = true;
}

static void uiDisplaySettingCard(const HubRect& r, const char* label,
                                 const char* value, const char* detail,
                                 uint16_t accent, bool active=true) {
  // v11.19: preserve configurability while making parent-disabled settings
  // visibly "configured but inactive" instead of looking operational.
  const uint16_t cardAccent = active ? accent : UI_BORDER_2;
  const uint16_t labelColor = active ? accent : UI_MUTED;
  const uint16_t valueColor = active ? UI_TEXT : UI_DIM;
  const uint16_t detailColor = active ? UI_DIM : UI_MUTED;
  uiCard(r.x, r.y, r.w, r.h, cardAccent, false);
  const int16_t pad = 12;
  const int16_t labelY = r.y + (hubLandscape() ? 10 : 13);
  const int16_t valueY = r.y + (hubLandscape() ? 34 : 45);
  const int16_t detailY = r.y + (hubLandscape() ? 59 : 82);
  uiDrawFit(label, r.x + pad, labelY, r.w - pad * 2,
            FONT_SMALL, TL_DATUM, labelColor, UI_PANEL);
  uiDrawFit(value, r.x + pad, valueY, r.w - pad * 2,
            FONT_LARGE, TL_DATUM, valueColor, UI_PANEL);
  uiDrawFit(detail, r.x + pad, detailY, r.w - pad * 2,
            FONT_SMALL, TL_DATUM, detailColor, UI_PANEL);
}

static HubRect hubDisplayPagerRect() {
  const int16_t W=tft.width();
  if(hubLandscape()) return hr(W-140,207,132,48);
  return hr(18,356,W-36,48);
}

static uint8_t hubStepHour(uint8_t hour, bool reverse) {
  hour = (uint8_t)(hour % 24U);
  return reverse ? (uint8_t)((hour + 23U) % 24U)
                 : (uint8_t)((hour + 1U) % 24U);
}

static uint16_t hubStepFinishDelay(uint16_t current, bool reverse) {
  static const uint16_t values[] = {0,1,3,5,10,15,30,60};
  const uint8_t count = (uint8_t)(sizeof(values) / sizeof(values[0]));
  if (reverse) {
    for (int8_t i = (int8_t)count - 1; i >= 0; --i) {
      if (values[i] < current) return values[i];
    }
    return current;
  }
  for (uint8_t i = 0; i < count; ++i) {
    if (values[i] > current) return values[i];
  }
  return current;
}

static const char* hubTimeDisplayLabel() {
  switch (dispSettings.timeDisplayMode) {
    case 1: return "REMAINING";
    case 2: return "BOTH";
    default:return "ETA";
  }
}

static const char* hubClockSizeLabel(uint8_t v) {
  switch (v) {
    case 1: return "NORMAL";
    case 2: return "MEDIUM";
    case 3: return "LARGE";
    default:return "AUTO";
  }
}

static const char* hubHmsAutoLabel() {
#if HAS_HMS_UI
  switch (dispSettings.hmsAutoPresent) {
    case 1: return "BRIEF";
    case 2: return "HOLD";
    default:return "BADGE";
  }
#else
  return "N/A";
#endif
}


// ---------------------------------------------------------------------------
// Smart Home v11.22 physical Display Expert controls
// ---------------------------------------------------------------------------
struct HubColorChoice {
  uint16_t value;
  const char* label;
};

static const HubColorChoice HUB_EXPERT_COLORS[] = {
  {CLR_GREEN, "GREEN"}, {CLR_CYAN, "CYAN"}, {CLR_BLUE, "BLUE"},
  {CLR_ORANGE, "ORANGE"}, {CLR_GOLD, "GOLD"}, {CLR_YELLOW, "YELLOW"},
  {CLR_RED, "RED"}, {CLR_TEXT_DEFAULT, "WHITE"}
};
static const uint8_t HUB_EXPERT_COLOR_COUNT =
    (uint8_t)(sizeof(HUB_EXPERT_COLORS) / sizeof(HUB_EXPERT_COLORS[0]));

struct HubThemePreset {
  const char* label;
  uint16_t bg;
  uint16_t track;
  uint16_t pbar;
  uint16_t eta;
  uint16_t finish;
  uint16_t statusOk;
  uint16_t printerName;
  uint16_t text;
  uint16_t textDim;
  uint16_t doorClosed;
  uint16_t doorOpen;
  uint16_t clockTime;
  uint16_t clockDate;
};

static const HubThemePreset HUB_THEMES[] = {
  {"FACTORY", CLR_BG, CLR_TRACK, CLR_GREEN, CLR_GREEN, CLR_GREEN, CLR_GREEN,
   CLR_GREEN, CLR_TEXT_DEFAULT, CLR_TEXT_DIM_DEFAULT, CLR_GREEN, CLR_ORANGE,
   CLR_TEXT_DEFAULT, CLR_TEXT_DIM_DEFAULT},
  {"WORKSHOP", CLR_BG, CLR_TRACK, CLR_ORANGE, CLR_GOLD, CLR_GOLD, CLR_GREEN,
   CLR_ORANGE, CLR_TEXT_DEFAULT, CLR_TEXT_DIM_DEFAULT, CLR_GREEN, CLR_ORANGE,
   CLR_GOLD, CLR_ORANGE},
  {"OCEAN", CLR_BG, CLR_TRACK, CLR_CYAN, CLR_CYAN, CLR_BLUE, CLR_CYAN,
   CLR_BLUE, CLR_TEXT_DEFAULT, CLR_TEXT_DIM_DEFAULT, CLR_CYAN, CLR_ORANGE,
   CLR_CYAN, CLR_BLUE},
  {"MONO", CLR_BG, CLR_TRACK, CLR_TEXT_DEFAULT, CLR_TEXT_DEFAULT,
   CLR_TEXT_DEFAULT, CLR_GREEN, CLR_TEXT_DEFAULT, CLR_TEXT_DEFAULT,
   CLR_TEXT_DIM_DEFAULT, CLR_GREEN, CLR_ORANGE, CLR_TEXT_DEFAULT,
   CLR_TEXT_DIM_DEFAULT}
};
static const uint8_t HUB_THEME_COUNT =
    (uint8_t)(sizeof(HUB_THEMES) / sizeof(HUB_THEMES[0]));

static void hubPersistDisplayExpert() {
  saveSettings();
  applyDisplaySettings();
  buzzerPlay(BUZZ_CLICK);
  g_dirty = true;
}

static const char* hubExpertColorName(uint16_t value) {
  for (uint8_t i = 0; i < HUB_EXPERT_COLOR_COUNT; ++i)
    if (HUB_EXPERT_COLORS[i].value == value) return HUB_EXPERT_COLORS[i].label;
  return "CUSTOM";
}

static uint16_t hubCycleExpertColor(uint16_t current, bool reverse) {
  int8_t found = -1;
  for (uint8_t i = 0; i < HUB_EXPERT_COLOR_COUNT; ++i) {
    if (HUB_EXPERT_COLORS[i].value == current) { found = (int8_t)i; break; }
  }
  if (found < 0)
    return HUB_EXPERT_COLORS[reverse ? HUB_EXPERT_COLOR_COUNT - 1U : 0U].value;
  const uint8_t next = reverse
      ? (uint8_t)((found + HUB_EXPERT_COLOR_COUNT - 1) % HUB_EXPERT_COLOR_COUNT)
      : (uint8_t)((found + 1) % HUB_EXPERT_COLOR_COUNT);
  return HUB_EXPERT_COLORS[next].value;
}

static int8_t hubThemePresetIndex() {
  for (uint8_t i = 0; i < HUB_THEME_COUNT; ++i) {
    const HubThemePreset& p = HUB_THEMES[i];
    if (dispSettings.bgColor == p.bg && dispSettings.trackColor == p.track &&
        dispSettings.progressBarColor == p.pbar && dispSettings.etaColor == p.eta &&
        dispSettings.finishColor == p.finish && dispSettings.statusOkColor == p.statusOk &&
        dispSettings.printerNameColor == p.printerName && dispSettings.textColor == p.text &&
        dispSettings.textDimColor == p.textDim && dispSettings.doorClosedColor == p.doorClosed &&
        dispSettings.doorOpenColor == p.doorOpen && dispSettings.clockTimeColor == p.clockTime &&
        dispSettings.clockDateColor == p.clockDate) return (int8_t)i;
  }
  return -1;
}

static const char* hubThemePresetLabel() {
  const int8_t idx = hubThemePresetIndex();
  return idx >= 0 ? HUB_THEMES[idx].label : "CUSTOM";
}

static void hubApplyThemePreset(uint8_t index) {
  const HubThemePreset& p = HUB_THEMES[index % HUB_THEME_COUNT];
  dispSettings.bgColor = p.bg;
  dispSettings.trackColor = p.track;
  dispSettings.progressBarColor = p.pbar;
  dispSettings.etaColor = p.eta;
  dispSettings.finishColor = p.finish;
  dispSettings.statusOkColor = p.statusOk;
  dispSettings.printerNameColor = p.printerName;
  dispSettings.textColor = p.text;
  dispSettings.textDimColor = p.textDim;
  dispSettings.doorClosedColor = p.doorClosed;
  dispSettings.doorOpenColor = p.doorOpen;
  dispSettings.clockTimeColor = p.clockTime;
  dispSettings.clockDateColor = p.clockDate;
}

static void hubCycleTheme(bool reverse) {
  int8_t idx = hubThemePresetIndex();
  if (idx < 0) idx = reverse ? 0 : -1;
  const uint8_t next = reverse
      ? (uint8_t)((idx + HUB_THEME_COUNT - 1) % HUB_THEME_COUNT)
      : (uint8_t)((idx + 1) % HUB_THEME_COUNT);
  hubApplyThemePreset(next);
}

static const char* hubGaugeName(uint8_t index) {
  static const char* names[] = {
    "PROGRESS", "NOZZLE", "BED", "PART FAN", "AUX FAN", "AUX RIGHT",
    "CHAMBER FAN", "EXHAUST", "CHAMBER TEMP", "HEATBREAK", "POWER", "LAYER"
  };
  return names[index % 12U];
}

static GaugeColors* hubSelectedGaugeColors() {
  switch (g_displayGaugeColorIndex % 12U) {
    case 0: return &dispSettings.progress;
    case 1: return &dispSettings.nozzle;
    case 2: return &dispSettings.bed;
    case 3: return &dispSettings.partFan;
    case 4: return &dispSettings.auxFan;
    case 5: return &dispSettings.auxFanRight;
    case 6: return &dispSettings.chamberFan;
    case 7: return &dispSettings.exhaustFan;
    case 8: return &dispSettings.chamberTemp;
    case 9: return &dispSettings.heatbreak;
    case 10:return &dispSettings.power;
    default:return &dispSettings.layer;
  }
}

static uint16_t hubStepPreset16(uint16_t current, const uint16_t* values,
                                uint8_t count, bool reverse) {
  if (!values || count == 0) return current;
  if (reverse) {
    for (int8_t i = (int8_t)count - 1; i >= 0; --i)
      if (values[i] < current) return values[i];
    return values[0];
  }
  for (uint8_t i = 0; i < count; ++i)
    if (values[i] > current) return values[i];
  return values[count - 1];
}

static const char* hubGaugeSmoothingLabel() {
  switch (dispSettings.gaugeSmoothing) {
    case 0: return "OFF";
    case 1: return "SLOW";
    case 3: return "FAST";
    default:return "NORMAL";
  }
}

static const char* hubGlowModeLabel() {
  switch (dispSettings.glowMode) {
    case 1: return "SINGLE";
    case 2: return "RAINBOW";
    default:return "OFF";
  }
}

static const char* hubGlowStyleLabel() {
  switch (dispSettings.glowStyle) {
    case 1: return "PULSE";
    case 2: return "STORM";
    default:return "SWEEP";
  }
}

static const char* hubGlowDurationLabel() {
  switch (dispSettings.glowDuration) {
    case 1: return "UNTIL DISMISSED";
    case 2: return "REMINDER";
    default:return "BURST";
  }
}

static const char* hubDisplayPageLabel(uint8_t page) {
  static const char* labels[HUB_DISPLAY_PAGE_COUNT] = {
    "QUICK", "SCHEDULE", "BEHAVIOR", "VISUAL", "CLOCK", "ALERTS", "SIGNALS",
    "THEME", "GAUGE COLORS", "GAUGE SCALES", "GAUGE BEHAVIOR", "GLOW", "LAYOUT", "EXTRAS"
  };
  return labels[page % HUB_DISPLAY_PAGE_COUNT];
}

static const char* hubDisplayPageNextLabel(uint8_t page) {
  static const char* labels[HUB_DISPLAY_PAGE_COUNT] = {
    "SCHEDULE >", "BEHAVIOR >", "VISUAL >", "CLOCK >", "ALERTS >", "SIGNALS >",
    "THEME >", "COLORS >", "SCALES >", "BEHAVIOR >", "GLOW >", "LAYOUT >", "EXTRAS >", "QUICK >"
  };
  return labels[page % HUB_DISPLAY_PAGE_COUNT];
}

static const char* hubDisplayPageFooterTitle(uint8_t page) {
  static const char* labels[HUB_DISPLAY_PAGE_COUNT] = {
    "DISPLAY & EXPERIENCE", "SCHEDULE & FINISH", "FINISH BEHAVIOR", "VISUAL PRESENTATION",
    "CLOCK EXPERIENCE", "PRINTER ALERTS", "ALERT SIGNALS", "DISPLAY THEME", "GAUGE COLOR EDITOR",
    "GAUGE FULL SCALE", "GAUGE BEHAVIOR", "EDGE GLOW", "LAYOUT MODES", "EXPERT EXTRAS"
  };
  return labels[page % HUB_DISPLAY_PAGE_COUNT];
}

static const char* hubDisplayPageFooterDetail(uint8_t page) {
  static const char* labels[HUB_DISPLAY_PAGE_COUNT] = {
    "Large controls for everyday adjustments",
    "Night schedule and finish timing",
    "After-print behavior and time readout",
    "Motion, labels, fan precision and status density",
    "Clock animation, type scale and date visibility",
    "Master policy, severity and presentation",
    "Glow, buzzer, LED and wake are independent",
    "Curated safe palettes; alarm colors stay fixed",
    "Select gauge, then edit arc / label / value color",
    "Nozzle, bed, chamber and power arc maxima",
    "Smoothing and warning policy; labels remain portal input",
    "Mode, style, duration and single-color accent",
    "Extended grids and multi-printer split presentation",
    "Clock footer, AMS labels and guarded rotation"
  };
  return labels[page % HUB_DISPLAY_PAGE_COUNT];
}

// v11.23 RC2 rotation preview is referenced by drawDisplayExperience before
// its helper implementation later in this translation unit.
static bool g_rotationPreviewMode=false;
static void hubRc2DrawRotationPreview();

static void drawDisplayExperience(bool full) {
  if(g_rotationPreviewMode){hubRc2DrawRotationPreview();return;}
  (void)full;
  const int16_t W = tft.width();
  const uint8_t page = (uint8_t)(g_displayExperiencePage % HUB_DISPLAY_PAGE_COUNT);
  const bool quick = page == 0;
  const bool schedule = page == 1;
  const bool behavior = page == 2;
  const bool visual = page == 3;
  const bool clock = page == 4;
  const bool alerts = page == 5;
  tft.fillScreen(UI_BG);
  drawHeader("DISPLAY", hubDisplayPageLabel(page), 3);
  uiBottomNav(3, nullptr);

  if (quick) {
    char mainValue[16], standbyValue[16], nightDetail[40], afterDetail[48];
    hubFormatPresetPct(brightness,false,mainValue,sizeof(mainValue));
    hubFormatPresetPct(dpSettings.screensaverBrightness,true,standbyValue,sizeof(standbyValue));
    snprintf(nightDetail, sizeof(nightDetail), "%02u:00-%02u:00 • tap toggle",
             (unsigned)dpSettings.nightStartHour, (unsigned)dpSettings.nightEndHour);
    if (dpSettings.keepDisplayOn) {
      strlcpy(afterDetail, "Finish screen remains awake", sizeof(afterDetail));
    } else if (dpSettings.finishDisplayMins == 0) {
      strlcpy(afterDetail,
              dpSettings.showClockAfterFinish ? "Switches to clock immediately"
                                               : "Uses immediate finish transition",
              sizeof(afterDetail));
    } else {
      snprintf(afterDetail, sizeof(afterDetail), "After %u min finish timer",
               (unsigned)dpSettings.finishDisplayMins);
    }

    uiDisplaySettingCard(hubMoreRect(0), "MAIN BRIGHTNESS", mainValue,
                         "Tap + / hold -", UI_ORANGE);
    uiDisplaySettingCard(hubMoreRect(1), "STANDBY BRIGHTNESS", standbyValue,
                         "Tap + / hold -", UI_CYAN);
    uiDisplaySettingCard(hubMoreRect(2), "NIGHT MODE",
                         dpSettings.nightModeEnabled ? "ON" : "OFF",
                         nightDetail, dpSettings.nightModeEnabled ? UI_PURPLE : UI_MUTED);
    uiDisplaySettingCard(hubMoreRect(3), "AFTER PRINT", hubAfterPrintLabel(),
                         afterDetail, UI_GREEN);
  } else if (schedule) {
    char nightValue[16], startValue[16], endValue[16], finishValue[20];
    char nightDetail[44], finishDetail[48];
    hubFormatPresetPct(dpSettings.nightBrightness,true,nightValue,sizeof(nightValue));
    snprintf(startValue, sizeof(startValue), "%02u:00",
             (unsigned)dpSettings.nightStartHour);
    snprintf(endValue, sizeof(endValue), "%02u:00",
             (unsigned)dpSettings.nightEndHour);
    if (dpSettings.finishDisplayMins == 0)
      strlcpy(finishValue, "IMMEDIATE", sizeof(finishValue));
    else
      snprintf(finishValue, sizeof(finishValue), "%u MIN",
               (unsigned)dpSettings.finishDisplayMins);
    strlcpy(nightDetail,
            dpSettings.nightModeEnabled ? "Tap + / hold -" : "Stored • Night mode is off",
            sizeof(nightDetail));
    strlcpy(finishDetail,
            dpSettings.keepDisplayOn ? "Stored • Stay On currently overrides" : "< PREV  |  NEXT >",
            sizeof(finishDetail));

    uiDisplaySettingCard(hubMoreRect(0), "NIGHT BRIGHTNESS", nightValue,
                         dpSettings.nightModeEnabled?"Tap + / hold -":"Configured • Night mode off", UI_PURPLE,dpSettings.nightModeEnabled);
    uiDisplaySettingCard(hubMoreRect(1), "NIGHT START", startValue,
                         dpSettings.nightModeEnabled?"Tap +1h / hold -1h":"Configured • Night mode off", UI_CYAN,dpSettings.nightModeEnabled);
    uiDisplaySettingCard(hubMoreRect(2), "NIGHT END", endValue,
                         dpSettings.nightModeEnabled?"Tap +1h / hold -1h":"Configured • Night mode off", UI_CYAN,dpSettings.nightModeEnabled);
    uiDisplaySettingCard(hubMoreRect(3), "FINISH TIMEOUT", finishValue,
                         finishDetail, UI_GREEN,!dpSettings.keepDisplayOn);
  } else if (behavior) {
    uiDisplaySettingCard(hubMoreRect(0), "DOOR ACK",
                         dpSettings.doorAckEnabled ? "ON" : "OFF",
                         "Wait for door before finish timeout", UI_CYAN);
    uiDisplaySettingCard(hubMoreRect(1), "KEEP PRINT SCREEN",
                         dpSettings.keepPrintScreen ? "ON" : "OFF",
                         "Remain on Printer after finish", UI_ORANGE);
    uiDisplaySettingCard(hubMoreRect(2), "FINISH TIMESTAMP",
                         dpSettings.finishShowTime ? "ON" : "OFF",
                         "Show completion clock time", UI_PURPLE);
    uiDisplaySettingCard(hubMoreRect(3), "TIME DISPLAY",
                         hubTimeDisplayLabel(),
                         "< PREV  |  NEXT >", UI_GREEN);
  } else if (visual) {
    uiDisplaySettingCard(hubMoreRect(0), "ANIMATED PROGRESS",
                         dispSettings.animatedBar ? "ON" : "OFF",
                         "Progress-bar shimmer effect", UI_ORANGE);
    uiDisplaySettingCard(hubMoreRect(1), "SMALL LABELS",
                         dispSettings.smallLabels ? "ON" : "OFF",
                         "Compact gauge labels", UI_CYAN);
    uiDisplaySettingCard(hubMoreRect(2), "FAN DISPLAY",
                         dispSettings.fanMatchPrinter ? "MATCH PRINTER" : "PRECISE",
                         dispSettings.fanMatchPrinter ? "10% steps like printer LCD" : "1% telemetry precision",
                         UI_PURPLE);
    uiDisplaySettingCard(hubMoreRect(3), "STATUS READOUT",
                         dispSettings.hideStatusReadout ? "HIDDEN" : "SHOWN",
                         "Printing status center readout", UI_GREEN);
  } else if (clock) {
    uiDisplaySettingCard(hubMoreRect(0), "PONG CLOCK",
                         dispSettings.pongClock ? "ON" : "OFF",
                         "Animated idle clock", UI_ORANGE);
    uiDisplaySettingCard(hubMoreRect(1), "TIME SIZE",
                         hubClockSizeLabel(dispSettings.clockTimeSize),
                         "< PREV  |  NEXT >", UI_CYAN);
    uiDisplaySettingCard(hubMoreRect(2), "DATE SIZE",
                         hubClockSizeLabel(dispSettings.clockDateSize),
                         "< PREV  |  NEXT >", UI_PURPLE);
    uiDisplaySettingCard(hubMoreRect(3), "DATE VISIBILITY",
                         dispSettings.hideClockDate ? "HIDDEN" : "SHOWN",
                         "Toggle date on idle clock", UI_GREEN);
  } else if (alerts) {
#if HAS_HMS_UI
    uiDisplaySettingCard(hubMoreRect(0), "PRINTER ERRORS",
                         dispSettings.hmsEnabled ? "ON" : "OFF",
                         "Master HMS and print-error alerts", UI_ORANGE);
    uiDisplaySettingCard(hubMoreRect(1), "SEVERITY",
                         dispSettings.hmsSeverityAll ? "ALL" : "IMPORTANT",
                         dispSettings.hmsEnabled?(dispSettings.hmsSeverityAll ? "Includes common severity" : "Important severity only"):"Configured • Errors off",
                         UI_CYAN,dispSettings.hmsEnabled);
    uiDisplaySettingCard(hubMoreRect(2), "AUTO PRESENT",
                         hubHmsAutoLabel(),
                         dispSettings.hmsEnabled?"Badge / brief / hold":"Configured • Errors off", UI_PURPLE,dispSettings.hmsEnabled);
    uiDisplaySettingCard(hubMoreRect(3), "ONLINE LOOKUP",
                         dispSettings.hmsLookupOnline ? "ON" : "OFF",
                         dispSettings.hmsEnabled?"Look up HMS details online":"Configured • Errors off", UI_GREEN,dispSettings.hmsEnabled);
#else
    uiDisplaySettingCard(hubMoreRect(0), "PRINTER ERRORS", "N/A",
                         "HMS UI unavailable on this board", UI_MUTED);
#endif
  } else if (page == 6) {
#if HAS_HMS_UI
    uiDisplaySettingCard(hubMoreRect(0), "ERROR GLOW",
                         (dispSettings.hmsAlertMask & 0x01U) ? "ON" : "OFF",
                         dispSettings.hmsEnabled?"Edge-glow alert signal":"Configured • Errors off", UI_ORANGE,dispSettings.hmsEnabled);
    uiDisplaySettingCard(hubMoreRect(1), "ERROR BUZZER",
                         (dispSettings.hmsAlertMask & 0x02U) ? "ON" : "OFF",
                         dispSettings.hmsEnabled?"Audible alert signal":"Configured • Errors off", UI_CYAN,dispSettings.hmsEnabled);
    uiDisplaySettingCard(hubMoreRect(2), "ERROR LED",
                         (dispSettings.hmsAlertMask & 0x04U) ? "ON" : "OFF",
                         dispSettings.hmsEnabled?"Status LED alert signal":"Configured • Errors off", UI_PURPLE,dispSettings.hmsEnabled);
    uiDisplaySettingCard(hubMoreRect(3), "WAKE DISPLAY",
                         (dispSettings.hmsAlertMask & 0x08U) ? "ON" : "OFF",
                         dispSettings.hmsEnabled?"Wake screen for new error":"Configured • Errors off", UI_GREEN,dispSettings.hmsEnabled);
#else
    uiDisplaySettingCard(hubMoreRect(0), "ERROR SIGNALS", "N/A",
                         "HMS UI unavailable on this board", UI_MUTED);
#endif
  } else if (page == 7) {
    uiDisplaySettingCard(hubMoreRect(0), "THEME PALETTE", hubThemePresetLabel(),
                         "< PREV  |  NEXT >", UI_ORANGE);
    uiDisplaySettingCard(hubMoreRect(1), "CLOCK TIME",
                         hubExpertColorName(dispSettings.clockTimeColor),
                         "Independent clock color", UI_CYAN);
    uiDisplaySettingCard(hubMoreRect(2), "CLOCK DATE",
                         hubExpertColorName(dispSettings.clockDateColor),
                         "Independent date color", UI_PURPLE);
    uiDisplaySettingCard(hubMoreRect(3), "THEME RESET", "FACTORY",
                         "Restore curated factory palette", UI_GREEN);
  } else if (page == 8) {
    GaugeColors* gc = hubSelectedGaugeColors();
    uiDisplaySettingCard(hubMoreRect(0), "GAUGE COLORS",
                         hubGaugeName(g_displayGaugeColorIndex),
                         "Tap next gauge / hold previous", UI_ORANGE);
    uiDisplaySettingCard(hubMoreRect(1), "ARC COLOR", hubExpertColorName(gc->arc),
                         "< PREV  |  NEXT >", UI_CYAN);
    uiDisplaySettingCard(hubMoreRect(2), "LABEL COLOR", hubExpertColorName(gc->label),
                         "< PREV  |  NEXT >", UI_PURPLE);
    uiDisplaySettingCard(hubMoreRect(3), "VALUE COLOR", hubExpertColorName(gc->value),
                         "< PREV  |  NEXT >", UI_GREEN);
  } else if (page == 9) {
    char nozzle[16], bed[16], chamber[16], power[16];
    snprintf(nozzle,sizeof(nozzle),"%u C",(unsigned)dispSettings.nozzleScaleMax);
    snprintf(bed,sizeof(bed),"%u C",(unsigned)dispSettings.bedScaleMax);
    snprintf(chamber,sizeof(chamber),"%u C",(unsigned)dispSettings.chamberScaleMax);
    snprintf(power,sizeof(power),"%u W",(unsigned)dispSettings.powerScaleW);
    uiDisplaySettingCard(hubMoreRect(0), "NOZZLE SCALE", nozzle,
                         "100-400 C presets", UI_ORANGE);
    uiDisplaySettingCard(hubMoreRect(1), "BED SCALE", bed,
                         "40-150 C presets", UI_CYAN);
    uiDisplaySettingCard(hubMoreRect(2), "CHAMBER SCALE", chamber,
                         "30-120 C presets", UI_PURPLE);
    uiDisplaySettingCard(hubMoreRect(3), "POWER SCALE", power,
                         "100-5000 W presets", UI_GREEN);
  } else if (page == 10) {
    char threshold[16];
    if (dispSettings.warnThresholdPct == 0) strlcpy(threshold,"OFF",sizeof(threshold));
    else snprintf(threshold,sizeof(threshold),"%u%%",(unsigned)dispSettings.warnThresholdPct);
    uiDisplaySettingCard(hubMoreRect(0), "SMOOTHING", hubGaugeSmoothingLabel(),
                         "Off / slow / normal / fast", UI_ORANGE);
    uiDisplaySettingCard(hubMoreRect(1), "WARN THRESHOLD", threshold,
                         "0 or 50-100% presets", UI_CYAN);
    uiDisplaySettingCard(hubMoreRect(2), "WARN COLOR",
                         hubExpertColorName(dispSettings.warnColor),
                         "Temperature warning accent", UI_PURPLE,
                         dispSettings.warnThresholdPct > 0);
    uiDisplaySettingCard(hubMoreRect(3), "GAUGE DEFAULTS", "RESTORE",
                         "Smoothing normal / warning off", UI_GREEN);
  } else if (page == 11) {
    uiDisplaySettingCard(hubMoreRect(0), "GLOW MODE", hubGlowModeLabel(),
                         "Off / single / rainbow", UI_ORANGE);
    uiDisplaySettingCard(hubMoreRect(1), "GLOW STYLE", hubGlowStyleLabel(),
                         "Sweep / pulse / storm", UI_CYAN,
                         dispSettings.glowMode != 0);
    uiDisplaySettingCard(hubMoreRect(2), "GLOW DURATION", hubGlowDurationLabel(),
                         "Burst / until dismissed / reminder", UI_PURPLE,
                         dispSettings.glowMode != 0);
    uiDisplaySettingCard(hubMoreRect(3), "GLOW COLOR",
                         hubExpertColorName(dispSettings.glowColor),
                         dispSettings.glowMode == 1 ? "Single-color accent" : "Configured • Single mode only",
                         UI_GREEN, dispSettings.glowMode == 1);
  } else if (page == 12) {
    uiDisplaySettingCard(hubMoreRect(0), "8-SLOT LANDSCAPE",
                         dispSettings.landscape8Slots ? "ON" : "OFF",
                         "Replace AMS sidebar with 2x4 grid", UI_ORANGE);
    uiDisplaySettingCard(hubMoreRect(1), "9-SLOT PORTRAIT",
                         dispSettings.portrait9Slots ? "ON" : "OFF",
                         "Replace AMS strip with 3x3 grid", UI_CYAN);
    uiDisplaySettingCard(hubMoreRect(2), "SPLIT VIEW",
                         rotState.splitEnabled ? "ON" : "OFF",
                         "Two-printer split presentation", UI_PURPLE);
    uiDisplaySettingCard(hubMoreRect(3), "FORCE SPLIT",
                         rotState.splitForce ? "ON" : "OFF",
                         rotState.splitEnabled ? "Keep split even when one printer idle" : "Configured • Split view off",
                         UI_GREEN, rotState.splitEnabled);
  } else {
    uiDisplaySettingCard(hubMoreRect(0), "CLOCK INFO",
                         dispSettings.showClockInfo ? "ON" : "OFF",
                         "Printer name + LAN IP footer", UI_ORANGE);
    uiDisplaySettingCard(hubMoreRect(1), "AMS TRAY TYPES",
                         dispSettings.amsTrayTypes ? "ON" : "OFF",
                         "Show filament type under AMS bars", UI_CYAN);
    uiDisplaySettingCard(hubMoreRect(2), "GAUGE LABELS", "PORTAL",
                         "Free text stays browser-only", UI_PURPLE, false);
    uiDisplaySettingCard(hubMoreRect(3), "ROTATION", hubRotationLabel(),
                         "Tap to open guarded preview", UI_GREEN);
  }

  HubRect pager = hubDisplayPagerRect();
  const char* nextLabel = hubDisplayPageNextLabel(page);
  if (hubLandscape()) {
    uiPanelFill(8, 210, W - 156, 54);
    uiDrawFit(hubDisplayPageFooterDetail(page),
              20, 237, W - 184, FONT_SMALL, ML_DATUM, UI_DIM, UI_PANEL_2);
  } else {
    uiPanelFill(10, 306, W - 20, 108);
    uiDrawFit(hubDisplayPageFooterTitle(page),
              20, 319, W - 40, FONT_SMALL, TL_DATUM, UI_PURPLE, UI_PANEL_2);
    uiDrawFit(hubDisplayPageFooterDetail(page),
              20, 344, W - 40, FONT_BODY, TL_DATUM, UI_TEXT, UI_PANEL_2);
  }
  uiActionButton(pager, nextLabel, UI_PURPLE);
  hubMarkFrameDirty();
  g_dirty = false;
}

static HubRect hubUi12SettingsRect(uint8_t i) {
  const int16_t W=tft.width();
  if(hubLandscape()) {
    if(i==0)return hr(8,44,228,62);
    if(i==1)return hr(244,44,W-252,62);
    if(i==2)return hr(8,114,228,62);
    if(i==3)return hr(244,114,W-252,62);
    if(i==4)return hr(8,184,W-16,76);
    return hr(0,0,0,0);
  }
  return i<5?hr(8,44+i*72,W-16,64):hr(0,0,0,0);
}

static HubRect hubUi12BackRect() {
  const int16_t W=tft.width();
  return hubLandscape()?hr(8,212,112,48):hr(8,366,112,48);
}

static HubRect hubUi12SubActionRect() {
  const int16_t W=tft.width();
  return hubLandscape()?hr(W-120,212,112,48):hr(W-120,366,112,48);
}

static HubRect hubUi12ExperienceRect(uint8_t i) {
  const int16_t W=tft.width();
  if(hubLandscape()) return i==0?hr(8,54,228,104):hr(244,54,W-252,104);
  return i==0?hr(8,60,W-16,126):hr(8,194,W-16,126);
}

static void hubUi12SettingsCard(const HubRect& r,const char* title,const char* detail,uint16_t rail=C10_SEPARATOR,bool wide=false) {
  hubV1125Card(r,rail,wide);
  const uint16_t bg=wide?C10_SURFACE_2:C10_SURFACE;
  uiDrawFit(title,r.x+16,r.y+14,r.w-52,FONT_BODY,TL_DATUM,C10_TEXT,bg);
  uiDrawFit(detail,r.x+16,r.y+r.h-14,r.w-52,FONT_SMALL,BL_DATUM,C10_MUTED,bg);
  uiDrawFit(">",r.x+r.w-16,r.y+r.h/2,18,FONT_BODY,MR_DATUM,C10_ACCENT,bg);
}

static void drawUi12Experience() {
  const int16_t W=tft.width();tft.fillScreen(C10_BG);drawHeader("Experience",nullptr,3);uiBottomNav(3,nullptr);
  HubRect display=hubUi12ExperienceRect(0),sound=hubUi12ExperienceRect(1);
  hubV1125Card(display,C10_ACCENT,true);hubV1125Card(sound,C10_ACCENT,false);
  uiDrawFit("Display & Standby",display.x+16,display.y+16,display.w-32,FONT_BODY,TL_DATUM,C10_TEXT,C10_SURFACE_2);
  uiDrawFit("Brightness, appearance, sleep",display.x+16,display.y+48,display.w-32,FONT_SMALL,TL_DATUM,C10_MUTED,C10_SURFACE_2);
  uiDrawFit("Open",display.x+16,display.y+display.h-14,display.w-32,FONT_SMALL,BL_DATUM,C10_ACCENT,C10_SURFACE_2);
  uiDrawFit("Sound & Alerts",sound.x+16,sound.y+16,sound.w-32,FONT_BODY,TL_DATUM,C10_TEXT,C10_SURFACE);
  uiDrawFit("Speaker, microphone, event sounds",sound.x+16,sound.y+48,sound.w-32,FONT_SMALL,TL_DATUM,C10_MUTED,C10_SURFACE);
  uiDrawFit("Open",sound.x+16,sound.y+sound.h-14,sound.w-32,FONT_SMALL,BL_DATUM,C10_ACCENT,C10_SURFACE);
  hubV1125Action(hubUi12BackRect(),"Back",C10_ACCENT,true,false);
  if(hubLandscape())uiDrawFit("Everyday behavior only - advanced administration stays in Local Portal",132,236,W-260,FONT_SMALL,ML_DATUM,C10_MUTED,C10_BG);
  hubMarkFrameDirty();g_dirty=false;
}

static void drawUi12PrinterConnection() {
  const int16_t W=tft.width();const bool configured=isAnyPrinterConfigured();const PrinterSlot* p=configured?&displayedPrinter():nullptr;const bool connected=p&&p->state.connected;
  tft.fillScreen(C10_BG);drawHeader("Printer Connection",nullptr,3);uiBottomNav(3,nullptr);
  if(hubLandscape()) {
    HubRect status=hr(8,44,W-16,102),admin=hr(8,154,W-16,50);hubV1125Card(status,connected?C10_GREEN:(configured?C10_ORANGE:C10_ACCENT),true);hubV1125Card(admin,C10_SEPARATOR,false);
    uiDrawFit(p&&p->config.name[0]?p->config.name:(configured?"Configured Printer":"No Printer Configured"),status.x+16,status.y+14,status.w-32,FONT_LARGE,TL_DATUM,C10_TEXT,C10_SURFACE_2);
    uiDrawFit(!configured?"Setup required":(connected?"Connected":"Connection unavailable"),status.x+16,status.y+58,180,FONT_BODY,TL_DATUM,!configured?C10_MUTED:(connected?C10_GREEN:C10_ORANGE),C10_SURFACE_2);
    const uint8_t plug=configured?tasmotaControlPlugForSlot(rotState.displayIndex):0xFF;uiDrawFit(plug==0xFF?"Power mapping: Not configured":"Power mapping: Linked",status.x+220,status.y+61,status.w-236,FONT_SMALL,TL_DATUM,plug==0xFF?C10_MUTED:C10_TEXT,C10_SURFACE_2);
    uiDrawFit("Credentials and advanced setup are managed in the authenticated Local Portal.",admin.x+14,admin.y+25,admin.w-28,FONT_SMALL,ML_DATUM,C10_MUTED,C10_SURFACE);
  } else {
    HubRect status=hr(8,52,W-16,154),admin=hr(8,214,W-16,108);hubV1125Card(status,connected?C10_GREEN:(configured?C10_ORANGE:C10_ACCENT),true);hubV1125Card(admin,C10_SEPARATOR,false);
    uiDrawFit(p&&p->config.name[0]?p->config.name:(configured?"Configured Printer":"No Printer Configured"),status.x+16,status.y+18,status.w-32,FONT_LARGE,TL_DATUM,C10_TEXT,C10_SURFACE_2);
    uiDrawFit(!configured?"Setup required":(connected?"Connected":"Connection unavailable"),status.x+16,status.y+82,status.w-32,FONT_BODY,TL_DATUM,connected?C10_GREEN:C10_ORANGE,C10_SURFACE_2);
    uiDrawFit("Advanced setup is available in Local Portal",admin.x+14,admin.y+30,admin.w-28,FONT_BODY,TL_DATUM,C10_MUTED,C10_SURFACE);
  }
  hubV1125Action(hubUi12BackRect(),"Back",C10_ACCENT,true,false);hubV1125Action(hubUi12SubActionRect(),"Open Printer",C10_ACCENT,true,false);
  hubMarkFrameDirty();g_dirty=false;
}

static void drawUi12SoftwareUpdate() {
  const int16_t W=tft.width();tft.fillScreen(C10_BG);drawHeader("Software Update",nullptr,3);uiBottomNav(3,nullptr);
  if(hubLandscape()) {
    HubRect hero=hr(8,44,W-16,88),policy=hr(8,140,W-16,64);hubV1125Card(hero,C10_ACCENT,true);hubV1125Card(policy,C10_SEPARATOR,false);
    char ver[34];snprintf(ver,sizeof(ver),"Workshop OS %s",SMART_HOME_VERSION);uiDrawFit(ver,hero.x+16,hero.y+14,hero.w-32,FONT_LARGE,TL_DATUM,C10_TEXT,C10_SURFACE_2);
    uiDrawFit("UI12 Control Center - development build",hero.x+16,hero.y+57,hero.w-32,FONT_SMALL,TL_DATUM,C10_ORANGE,C10_SURFACE_2);
    uiDrawFit("Stable is the default update channel.",policy.x+14,policy.y+13,policy.w-28,FONT_BODY,TL_DATUM,C10_TEXT,C10_SURFACE);
    uiDrawFit("On-device installation is not enabled in this build. Use authenticated Local Portal.",policy.x+14,policy.y+42,policy.w-28,FONT_SMALL,TL_DATUM,C10_MUTED,C10_SURFACE);
  } else {
    HubRect hero=hr(8,52,W-16,146),policy=hr(8,206,W-16,116);hubV1125Card(hero,C10_ACCENT,true);hubV1125Card(policy,C10_SEPARATOR,false);char ver[34];snprintf(ver,sizeof(ver),"Workshop OS %s",SMART_HOME_VERSION);uiDrawFit(ver,hero.x+16,hero.y+18,hero.w-32,FONT_LARGE,TL_DATUM,C10_TEXT,C10_SURFACE_2);uiDrawFit("UI12 Control Center",hero.x+16,hero.y+84,hero.w-32,FONT_BODY,TL_DATUM,C10_ORANGE,C10_SURFACE_2);uiDrawFit("Updates are managed in authenticated Local Portal",policy.x+14,policy.y+30,policy.w-28,FONT_BODY,TL_DATUM,C10_MUTED,C10_SURFACE);
  }
  hubV1125Action(hubUi12BackRect(),"Back",C10_ACCENT,true,false);
  hubMarkFrameDirty();g_dirty=false;
}

static HubRect hubUi13RowRect(uint8_t i) {
  const int16_t W=tft.width();
  if(hubLandscape()) return i<3?hr(8,48+i*56,W-16,48):hr(0,0,0,0);
  return i<3?hr(8,58+i*82,W-16,72):hr(0,0,0,0);
}

static HubRect hubUi13BackRect() {
  const int16_t W=tft.width();
  return hubLandscape()?hr(8,214,112,48):hr(8,366,112,48);
}

static HubRect hubUi13ActionRect() {
  const int16_t W=tft.width();
  return hubLandscape()?hr(W-188,214,180,48):hr(W-188,366,180,48);
}

static HubRect hubUi13MinusRect(uint8_t i) {
  const HubRect r=hubUi13RowRect(i);
  return hr(r.x+r.w-236,r.y,52,r.h);
}

static HubRect hubUi13PlusRect(uint8_t i) {
  const HubRect r=hubUi13RowRect(i);
  return hr(r.x+r.w-60,r.y,52,r.h);
}

static HubRect hubUi13ToggleRect(uint8_t i) {
  const HubRect r=hubUi13RowRect(i);
  return hr(r.x+r.w-96,r.y,96,r.h);
}

static void hubUi13InfoRow(const HubRect& r,const char* label,const char* value,const char* detail,uint16_t accent=C10_ACCENT) {
  hubV1125Card(r,C10_SEPARATOR,false);
  uiDrawFit(label,r.x+12,r.y+8,r.w-150,FONT_SMALL,TL_DATUM,C10_MUTED,C10_SURFACE);
  uiDrawFit(value,r.x+12,r.y+25,r.w-150,FONT_BODY,TL_DATUM,accent,C10_SURFACE);
  uiDrawFit(detail,r.x+r.w-140,r.y+r.h/2,128,FONT_SMALL,MR_DATUM,C10_MUTED,C10_SURFACE);
}

static void hubUi13ToggleRow(const HubRect& r,const char* label,const char* detail,bool on,uint16_t accent=C10_ACCENT) {
  hubV1125Card(r,C10_SEPARATOR,false);
  uiDrawFit(label,r.x+12,r.y+8,r.w-108,FONT_BODY,TL_DATUM,C10_TEXT,C10_SURFACE);
  uiDrawFit(detail,r.x+12,r.y+r.h-9,r.w-108,FONT_SMALL,BL_DATUM,C10_MUTED,C10_SURFACE);
  HubRect sw=hr(r.x+r.w-82,r.y+8,66,r.h-16);
  tft.fillRoundRect(sw.x,sw.y,sw.w,sw.h,sw.h/2,on?accent:C10_SURFACE_2);
  tft.drawRoundRect(sw.x,sw.y,sw.w,sw.h,sw.h/2,on?accent:C10_SEPARATOR);
  const int16_t d=sw.h-8;
  const int16_t cx=on?(sw.x+sw.w-4-d/2):(sw.x+4+d/2);
  tft.fillCircle(cx,sw.y+sw.h/2,d/2,C10_TEXT);
}

static void hubUi13StepperRow(const HubRect& r,const char* label,const char* value,const char* detail,uint16_t accent=C10_ACCENT) {
  hubV1125Card(r,C10_SEPARATOR,false);
  uiDrawFit(label,r.x+12,r.y+8,r.w-248,FONT_SMALL,TL_DATUM,C10_MUTED,C10_SURFACE);
  uiDrawFit(detail,r.x+12,r.y+r.h-9,r.w-248,FONT_SMALL,BL_DATUM,C10_MUTED,C10_SURFACE);
  HubRect minus=hr(r.x+r.w-236,r.y+2,52,r.h-4),plus=hr(r.x+r.w-60,r.y+2,52,r.h-4);
  tft.fillRoundRect(minus.x,minus.y,minus.w,minus.h,11,C10_SURFACE_2);tft.drawRoundRect(minus.x,minus.y,minus.w,minus.h,11,C10_SEPARATOR);
  tft.fillRoundRect(plus.x,plus.y,plus.w,plus.h,11,C10_SURFACE_2);tft.drawRoundRect(plus.x,plus.y,plus.w,plus.h,11,C10_SEPARATOR);
  uiDrawFit("-",minus.x+minus.w/2,minus.y+minus.h/2,minus.w-8,FONT_LARGE,MC_DATUM,accent,C10_SURFACE_2);
  uiDrawFit("+",plus.x+plus.w/2,plus.y+plus.h/2,plus.w-8,FONT_LARGE,MC_DATUM,accent,C10_SURFACE_2);
  uiDrawFit(value,r.x+r.w-178,r.y+r.h/2,112,FONT_BODY,MC_DATUM,C10_TEXT,C10_SURFACE);
}

static HubRect hubUi13SystemCardRect(uint8_t i) {
  const int16_t W=tft.width();
  if(hubLandscape()) {
    if(i==0)return hr(8,48,228,76);
    if(i==1)return hr(244,48,W-252,76);
    if(i==2)return hr(8,132,228,76);
    if(i==3)return hr(244,132,W-252,76);
  }
  return i<4?hr(8,52+i*74,W-16,66):hr(0,0,0,0);
}

static void drawUi13Display() {
  const int16_t W=tft.width();tft.fillScreen(C10_BG);drawHeader("Display & Appearance",nullptr,3);uiBottomNav(3,nullptr);
  char mainValue[16],standbyValue[16];snprintf(mainValue,sizeof(mainValue),"%u%%",(unsigned)hubLevelPct(brightness));snprintf(standbyValue,sizeof(standbyValue),"%u%%",(unsigned)hubLevelPct(dpSettings.screensaverBrightness));
  hubUi13StepperRow(hubUi13RowRect(0),"Brightness",mainValue,"Display",C10_ACCENT);
  hubUi13StepperRow(hubUi13RowRect(1),"Standby Brightness",standbyValue,"When idle",C10_ACCENT);
  hubUi13ToggleRow(hubUi13RowRect(2),"Night Mode","Follow the night schedule",dpSettings.nightModeEnabled,C10_ACCENT);
  hubV1125Action(hubUi13BackRect(),"Back",C10_ACCENT,true,false);hubV1125Action(hubUi13ActionRect(),"After Print",C10_ACCENT,true,false);
  hubMarkFrameDirty();g_dirty=false;
}

static void drawUi13AfterPrint() {
  tft.fillScreen(C10_BG);drawHeader("After Print",nullptr,3);uiBottomNav(3,nullptr);
  char timeout[20];if(dpSettings.finishDisplayMins==0)strlcpy(timeout,"Immediate",sizeof(timeout));else snprintf(timeout,sizeof(timeout),"%u min",(unsigned)dpSettings.finishDisplayMins);
  hubUi13StepperRow(hubUi13RowRect(0),"Display Behavior",hubAfterPrintLabel(),"What the display shows",C10_ACCENT);
  hubUi13StepperRow(hubUi13RowRect(1),"Finish Timeout",timeout,"Before standby",C10_ACCENT);
  hubUi13ToggleRow(hubUi13RowRect(2),"Animated Progress","Show motion during progress",dispSettings.animatedBar,C10_ACCENT);
  hubV1125Action(hubUi13BackRect(),"Back",C10_ACCENT,true,false);hubV1125Action(hubUi13ActionRect(),"Done",C10_ACCENT,true,false);
  hubMarkFrameDirty();g_dirty=false;
}

static void drawUi13Sound() {
  tft.fillScreen(C10_BG);drawHeader("Sounds & Alerts",nullptr,3);uiBottomNav(3,nullptr);
  hubUi13ToggleRow(hubUi13RowRect(0),"Event Sounds","Print and device events",buzzerSettings.enabled,C10_ACCENT);
  hubUi13ToggleRow(hubUi13RowRect(1),"Touch Sounds","Feedback when you tap",buzzerSettings.buttonClick,C10_ACCENT);
  hubUi13ToggleRow(hubUi13RowRect(2),"Bed Cooled Alert","Notify when the bed cools",buzzerSettings.bedCooldownAlert,C10_ACCENT);
  hubV1125Action(hubUi13BackRect(),"Back",C10_ACCENT,true,false);hubV1125Action(hubUi13ActionRect(),"Printer Alerts",C10_ACCENT,true,false);
  hubMarkFrameDirty();g_dirty=false;
}

static void drawUi13PrinterAlerts() {
  tft.fillScreen(C10_BG);drawHeader("Printer Alerts",nullptr,3);uiBottomNav(3,nullptr);
#if HAS_HMS_UI
  hubUi13ToggleRow(hubUi13RowRect(0),"Printer Errors","Show printer error alerts",dispSettings.hmsEnabled,C10_ACCENT);
  hubUi13StepperRow(hubUi13RowRect(1),"Severity",dispSettings.hmsSeverityAll?"All":"Important","Which errors appear",C10_ACCENT);
  hubUi13StepperRow(hubUi13RowRect(2),"Presentation",hubHmsAutoLabel(),"How alerts appear",C10_ACCENT);
#else
  hubUi13InfoRow(hubUi13RowRect(0),"Printer Errors","Unavailable","Not available on this device",C10_MUTED);
#endif
  hubV1125Action(hubUi13BackRect(),"Back",C10_ACCENT,true,false);hubV1125Action(hubUi13ActionRect(),"Alert Signals",C10_ACCENT,true,false);
  hubMarkFrameDirty();g_dirty=false;
}

static void drawUi13AlertSignals() {
  tft.fillScreen(C10_BG);drawHeader("Alert Signals",nullptr,3);uiBottomNav(3,nullptr);
#if HAS_HMS_UI
  hubUi13ToggleRow(hubUi13RowRect(0),"Alert Sound","Play a sound for printer errors",(dispSettings.hmsAlertMask&0x02U)!=0,C10_ACCENT);
  hubUi13ToggleRow(hubUi13RowRect(1),"Status Light","Use the status light",(dispSettings.hmsAlertMask&0x04U)!=0,C10_ACCENT);
  hubUi13ToggleRow(hubUi13RowRect(2),"Wake Display","Wake the screen for new alerts",(dispSettings.hmsAlertMask&0x08U)!=0,C10_ACCENT);
#else
  hubUi13InfoRow(hubUi13RowRect(0),"Alert Signals","Unavailable","Not available on this device",C10_MUTED);
#endif
  hubV1125Action(hubUi13BackRect(),"Back",C10_ACCENT,true,false);hubV1125Action(hubUi13ActionRect(),"Done",C10_ACCENT,true,false);
  hubMarkFrameDirty();g_dirty=false;
}

static void drawUi13Network() {
  const bool wifi=WiFi.status()==WL_CONNECTED;String ip=wifi?WiFi.localIP().toString():String("Unknown");
  tft.fillScreen(C10_BG);drawHeader("Network",wifi?"Connected":"Offline",3);uiBottomNav(3,nullptr);
  hubUi13InfoRow(hubUi13RowRect(0),"Wi-Fi",wifi?"Connected":"Not connected",wifi?ip.c_str():"No network connection",wifi?C10_GREEN:C10_ORANGE);
  hubUi13ToggleRow(hubUi13RowRect(1),"Local Hostname","Make Workshop OS easy to find",netSettings.mdnsEnabled,C10_ACCENT);
  hubUi13ToggleRow(hubUi13RowRect(2),"Show IP at Startup","Show the local address after connecting",netSettings.showIPAtStartup,C10_ACCENT);
  hubV1125Action(hubUi13BackRect(),"Back",C10_ACCENT,true,false);hubV1125Action(hubUi13ActionRect(),"Local Portal",C10_ACCENT,true,false);
  hubMarkFrameDirty();g_dirty=false;
}

static uint8_t hubPowerConfigPlug();

static void drawUi13PrinterPower() {
  const bool configured=isAnyPrinterConfigured();const PrinterSlot* p=configured?&displayedPrinter():nullptr;const bool connected=p&&p->state.connected;const uint8_t plug=configured?hubPowerConfigPlug():0xFF;const bool mapped=plug!=0xFF;const bool plugReady=mapped&&tasmotaSettings[plug].enabled&&tasmotaSettings[plug].ip[0];
  tft.fillScreen(C10_BG);drawHeader("Printer & Power",connected?"Connected":(configured?"Offline":"Set Up"),3);uiBottomNav(3,nullptr);
  hubUi13InfoRow(hubUi13RowRect(0),"Printer",p&&p->config.name[0]?p->config.name:(configured?"Configured":"Not configured"),connected?"Available now":"Not currently reachable",connected?C10_GREEN:(configured?C10_ORANGE:C10_MUTED));
  hubUi13InfoRow(hubUi13RowRect(1),"Smart Plug",plugReady?"Ready":(mapped?"Needs setup":"Not mapped"),"Manage mapping in Local Portal",plugReady?C10_GREEN:C10_MUTED);
  hubUi13ToggleRow(hubUi13RowRect(2),"Automatic Power Off",mapped&&tasmotaSettings[plug].autoOffEnabled?"After a finished print":"Set up a smart plug first",mapped&&tasmotaSettings[plug].autoOffEnabled,C10_ACCENT);
  hubV1125Action(hubUi13BackRect(),"Back",C10_ACCENT,true,false);hubV1125Action(hubUi13ActionRect(),"Power Options",C10_ACCENT,mapped,false);
  hubMarkFrameDirty();g_dirty=false;
}

static void drawUi13PowerOptions() {
  const bool configured=isAnyPrinterConfigured();const uint8_t plug=configured?hubPowerConfigPlug():0xFF;const bool mapped=plug!=0xFF;
  tft.fillScreen(C10_BG);drawHeader("Power Options",mapped?"Ready":"Unavailable",3);uiBottomNav(3,nullptr);
  if(mapped){TasmotaSettings& ps=tasmotaSettings[plug];char delay[20];snprintf(delay,sizeof(delay),"%u min",(unsigned)ps.autoOffDelayMin);hubUi13StepperRow(hubUi13RowRect(0),"Auto-Off Delay",delay,"After a finished print",C10_ACCENT);hubUi13ToggleRow(hubUi13RowRect(1),"Cancel on Door","Keep power on if the door opens",ps.autoOffCancelOnDoor,C10_ACCENT);hubUi13InfoRow(hubUi13RowRect(2),"Advanced Power Setup","Local Portal","Address and device details",C10_MUTED);}else{hubUi13InfoRow(hubUi13RowRect(0),"Smart Plug","Not mapped","Set up in Local Portal",C10_MUTED);}
  hubV1125Action(hubUi13BackRect(),"Back",C10_ACCENT,true,false);hubV1125Action(hubUi13ActionRect(),"Local Portal",C10_ACCENT,true,false);
  hubMarkFrameDirty();g_dirty=false;
}

static void drawUi13AutoOffConfirm() {
  const int16_t W=tft.width();tft.fillScreen(C10_BG);drawHeader("Enable Auto-Off?",nullptr,3);uiBottomNav(3,nullptr);
  HubRect card=hubLandscape()?hr(8,52,W-16,146):hr(8,62,W-16,250);hubV1125Card(card,C10_ORANGE,true);
  uiDrawFit("Automatic printer power-off",card.x+16,card.y+16,card.w-32,FONT_LARGE,TL_DATUM,C10_TEXT,C10_SURFACE_2);
  uiDrawFit("Workshop OS can turn off the mapped smart plug after a finished print and the delay you choose.",card.x+16,card.y+60,card.w-32,FONT_BODY,TL_DATUM,C10_MUTED,C10_SURFACE_2);
  uiDrawFit("You can turn this off at any time.",card.x+16,card.y+112,card.w-32,FONT_SMALL,TL_DATUM,C10_MUTED,C10_SURFACE_2);
  hubV1125Action(hubUi13BackRect(),"Cancel",C10_ACCENT,true,false);hubV1125Action(hubUi13ActionRect(),"Enable",C10_ORANGE,true,false);
  hubMarkFrameDirty();g_dirty=false;
}

static void drawMore(bool full) {
  if(g_displayExperienceView){drawDisplayExperience(full);return;}if(g_toolsView){drawTools(full);return;}
  if(g_ui12SettingsView==1){drawUi13Display();return;}if(g_ui12SettingsView==2){drawUi13Sound();return;}if(g_ui12SettingsView==3){drawUi13Network();return;}if(g_ui12SettingsView==4){drawUi13PrinterPower();return;}if(g_ui12SettingsView==5){drawUi13AfterPrint();return;}if(g_ui12SettingsView==6){drawUi13PrinterAlerts();return;}if(g_ui12SettingsView==7){drawUi13AlertSignals();return;}if(g_ui12SettingsView==8){drawUi13PowerOptions();return;}if(g_ui12SettingsView==9){drawUi13AutoOffConfirm();return;}
  (void)full;const bool wifi=WiFi.status()==WL_CONNECTED;const bool configured=isAnyPrinterConfigured();const bool printerConnected=configured&&displayedPrinter().state.connected;const bool deviceHealthy=hubTouchHealthy()&&recoveryWebReady();tft.fillScreen(C10_BG);drawHeader("Settings",nullptr,3);uiBottomNav(3,nullptr);
  hubUi12SettingsCard(hubUi12SettingsRect(0),"Display & Appearance","Brightness, standby, after print",C10_ACCENT,false);
  hubUi12SettingsCard(hubUi12SettingsRect(1),"Sounds & Alerts","Sounds, touch feedback, printer alerts",C10_ACCENT,false);
  hubUi12SettingsCard(hubUi12SettingsRect(2),"Network",wifi?"Connected":"Offline",wifi?C10_GREEN:C10_ORANGE,false);
  hubUi12SettingsCard(hubUi12SettingsRect(3),"Printer & Power",!configured?"Not configured":(printerConnected?"Connected":"Offline"),printerConnected?C10_GREEN:(configured?C10_ORANGE:C10_MUTED),false);
  hubUi12SettingsCard(hubUi12SettingsRect(4),"System",deviceHealthy?"Ready":"Needs attention",deviceHealthy?C10_GREEN:C10_ORANGE,true);
  hubMarkFrameDirty();g_dirty=false;
}

static bool hubTouchHealthy() {
  const uint32_t last=buttonTouchLastGoodPollMs();return last!=0 && (millis()-last)<5000UL;
}

static HubRect hubSystemAudioSettingsEntryRect() {
  return hr(0,0,0,0);
}

static HubRect hubSystemSubBackRect() {
  const int16_t W=tft.width();
  if(hubLandscape()) return hr(8,207,132,48);
  const int16_t g=6,m=18,w=(W-2*m-g)/2;
  return hr(m,356,w,48);
}

static HubRect hubSystemSubNextRect() {
  const int16_t W=tft.width();
  if(hubLandscape()) return hubDisplayPagerRect();
  const int16_t g=6,m=18,w=(W-2*m-g)/2;
  return hr(m+w+g,356,w,48);
}

static const char* hubQuietHourLabel(uint8_t hour,char* out,size_t outLen,bool allowOff) {
  if(allowOff && hour==0){strlcpy(out,"OFF",outLen);return out;}
  snprintf(out,outLen,"%02u:00",(unsigned)(hour%24U));return out;
}

static uint8_t hubStepCooldownThreshold(uint8_t current,bool reverse) {
  int v=constrain((int)current,20,80);
  v=((v+2)/5)*5;
  v+=reverse?-5:5;
  if(v<20)v=80;
  if(v>80)v=20;
  return (uint8_t)v;
}

static const char* hubLedFinishModeLabel() {
  switch (ledSettings.finishMode) {
    case LED_FINISH_BREATHING: return "BREATHING";
    case LED_FINISH_HEARTBEAT: return "HEARTBEAT";
    default: return "OFF";
  }
}

static const char* hubLedDriverLabel() {
  switch (ledSettings.driver) {
    case LED_DRV_RGB: return "RGB";
    case LED_DRV_PIXEL: return "PIXEL";
    default: return "SINGLE";
  }
}

static uint16_t hubStepLedSeconds(uint16_t current, bool reverse, bool allowZero) {
  static const uint16_t finishVals[] = {5,15,30,60,120,300,600};
  static const uint16_t errorVals[]  = {0,5,10,30,60,120,300,600};
  const uint16_t* vals = allowZero ? errorVals : finishVals;
  const uint8_t count = allowZero ? 8U : 7U;
  uint8_t best = 0;
  uint32_t bestDiff = 0xFFFFFFFFUL;
  for(uint8_t i=0;i<count;i++){
    uint32_t d = current > vals[i] ? (uint32_t)(current-vals[i]) : (uint32_t)(vals[i]-current);
    if(d < bestDiff){bestDiff=d;best=i;}
  }
  best = (uint8_t)((best + (reverse ? count-1U : 1U)) % count);
  return vals[best];
}

static void hubPersistLed(const char* message, uint16_t color) {
  saveLedSettings();
  initLed();
  setAudioDiag(message,color);
}

static uint8_t hubPowerConfigPlug() {
#if TASMOTA_PLUG_COUNT == 1
  return 0;
#else
  const uint8_t slot=rotState.displayIndex;
  return slot<TASMOTA_PLUG_COUNT?slot:0xFF;
#endif
}

static const char* hubPowerDisplayModeLabel(uint8_t mode) {
  switch(mode){case 1:return "POWER";case 2:return "LAYER";default:return "ALTERNATE";}
}

static const char* hubPowerTypeLabel(uint8_t type) {
  switch(type){case 1:return "SHELLY";case 2:return "KASA";case 3:return "SHELLY STRIP";default:return "TASMOTA";}
}

static uint8_t hubStepPowerPoll(uint8_t current,bool reverse) {
  int v=constrain((int)current,10,60);
  v=((v+5)/10)*10;
  v+=reverse?-10:10;
  if(v<10)v=60;
  if(v>60)v=10;
  return (uint8_t)v;
}

static uint8_t hubStepAutoOffDelay(uint8_t current,bool reverse) {
  static const uint8_t vals[]={1,5,10,15,30,60,120,240};
  uint8_t best=0;int bestDiff=1000;
  for(uint8_t i=0;i<8;i++){int d=abs((int)current-(int)vals[i]);if(d<bestDiff){bestDiff=d;best=i;}}
  best=(uint8_t)((best+(reverse?7U:1U))%8U);
  return vals[best];
}

static void hubPersistPower(const char* message,uint16_t color) {
  saveSettings();
  tasmotaInit();
  setAudioDiag(message,color);
}

static void drawAudioSettings(bool full) {
  (void)full;
  const int16_t W=tft.width();
  const uint8_t page=(uint8_t)(g_audioSettingsPage%7U);
  tft.fillScreen(UI_BG);
  drawHeader("HARDWARE",
             page==0?"SOUND":(page==1?"COOLDOWN":(page==2?"LED":(page==3?"FINISH":(page==4?"ERROR":(page==5?"POWER":"AUTO OFF"))))),3);
  uiBottomNav(3,nullptr);

  if(page==0){
    char qs[12],qe[12];
    hubQuietHourLabel(buzzerSettings.quietStartHour,qs,sizeof(qs),true);
    hubQuietHourLabel(buzzerSettings.quietEndHour,qe,sizeof(qe),false);
    const bool quietActive=buzzerSettings.quietStartHour!=0;
    uiDisplaySettingCard(hubMoreRect(0),"EVENT SOUNDS",buzzerSettings.enabled?"ON":"OFF","Print and device events",UI_ORANGE);
    uiDisplaySettingCard(hubMoreRect(1),"BUTTON CLICKS",buzzerSettings.buttonClick?"ON":"OFF","Touch feedback",UI_CYAN);
    uiDisplaySettingCard(hubMoreRect(2),"QUIET START",qs,"Tap +1h / hold -1h",UI_PURPLE);
    uiDisplaySettingCard(hubMoreRect(3),"QUIET END",qe,quietActive?"Tap +1h / hold -1h":"Configured • Quiet Start off",UI_GREEN,quietActive);
  }else if(page==1){
    char threshold[16];snprintf(threshold,sizeof(threshold),"%u C",(unsigned)buzzerSettings.bedCooldownThresholdC);
    uiDisplaySettingCard(hubMoreRect(0),"BED COOLDOWN",buzzerSettings.bedCooldownAlert?"ON":"OFF","Alert at bed threshold",UI_ORANGE);
    uiDisplaySettingCard(hubMoreRect(1),"BED THRESHOLD",threshold,buzzerSettings.bedCooldownAlert?"20-80 C • tap / hold":"Configured • Cooldown off",UI_CYAN,buzzerSettings.bedCooldownAlert);
    uiDisplaySettingCard(hubMoreRect(2),"SPEAKER TEST","RUN","Play ES8311 chime",UI_PURPLE);
    uiDisplaySettingCard(hubMoreRect(3),"MIC ECHO","RUN","Record 1 sec • play back",UI_GREEN);
  }else if(page==2){
    char br[20];hubFormatPresetPct(ledSettings.brightness,true,br,sizeof(br));
    const bool ledActive=ledSettings.enabled;
    uiDisplaySettingCard(hubMoreRect(0),"STATUS LED",ledActive?"ON":"OFF","Master indicator output",UI_ORANGE);
    uiDisplaySettingCard(hubMoreRect(1),"LED BRIGHTNESS",br,ledActive?"0 / 25 / 50 / 75 / 100":"Configured • Status LED off",UI_CYAN,ledActive);
    uiDisplaySettingCard(hubMoreRect(2),"WHILE PRINTING",ledSettings.autoOnWhilePrinting?"AUTO":"NORMAL",ledActive?"Follow active printing":"Configured • Status LED off",UI_PURPLE,ledActive);
    uiDisplaySettingCard(hubMoreRect(3),"PAUSE BREATHING",ledSettings.pauseBreathing?"ON":"OFF",ledActive?"Slow breath on pause":"Configured • Status LED off",UI_GREEN,ledActive);
  }else if(page==3){
    char secs[20],peak[20];
    snprintf(secs,sizeof(secs),"%u SEC",(unsigned)ledSettings.finishSeconds);
    hubFormatPresetPct(ledSettings.finishBrightness,true,peak,sizeof(peak));
    const bool finishActive=ledSettings.finishMode!=0;
    uiDisplaySettingCard(hubMoreRect(0),"FINISH EFFECT",hubLedFinishModeLabel(),"Off / breathe / heartbeat",UI_ORANGE);
    uiDisplaySettingCard(hubMoreRect(1),"FINISH DURATION",secs,finishActive?"5-600 sec • hold reverse":"Configured • Effect off",UI_CYAN,finishActive);
    uiDisplaySettingCard(hubMoreRect(2),"FINISH PEAK",peak,finishActive?"Effect peak brightness":"Configured • Effect off",UI_PURPLE,finishActive);
    uiDisplaySettingCard(hubMoreRect(3),"LED DRIVER",hubLedDriverLabel(),"Wiring stays in portal",UI_GREEN);
  }else if(page==4){
    char secs[20];
    if(ledSettings.errorStrobeSeconds==0)strlcpy(secs,"UNTIL CLEAR",sizeof(secs));else snprintf(secs,sizeof(secs),"%u SEC",(unsigned)ledSettings.errorStrobeSeconds);
    const bool errorActive=ledSettings.errorStrobe;
    uiDisplaySettingCard(hubMoreRect(0),"ERROR STROBE",errorActive?"ON":"OFF","Fast indicator strobe",UI_ORANGE);
    uiDisplaySettingCard(hubMoreRect(1),"ERROR DURATION",secs,errorActive?"0 / 5-600 sec presets":"Configured • Strobe off",UI_CYAN,errorActive);
    uiDisplaySettingCard(hubMoreRect(2),"LED DRIVER",hubLedDriverLabel(),"Advanced setup in portal",UI_PURPLE);
    uiDisplaySettingCard(hubMoreRect(3),"GPIO & COLORS","PORTAL","Advanced setup",UI_GREEN);
  }else{
    const uint8_t plug=hubPowerConfigPlug();
    if(plug==0xFF){
      uiDisplaySettingCard(hubMoreRect(0),"POWER SLOT","NONE","No mapped plug for printer",UI_MUTED);
      uiDisplaySettingCard(hubMoreRect(1),"SUPPORTED SLOTS","1-2","Plug N maps to printer N",UI_CYAN);
      uiDisplaySettingCard(hubMoreRect(2),"SETUP","PORTAL","Configure printer / plug",UI_PURPLE);
      uiDisplaySettingCard(hubMoreRect(3),"POWER CONTROL","UNAVAILABLE","No mapped smart plug",UI_GREEN);
    }else{
      TasmotaSettings& ps=tasmotaSettings[plug];
      const bool plugConfigured=ps.ip[0]!=0;
      const bool plugOperational=plugConfigured&&ps.enabled;
      char plugIdentity[28];snprintf(plugIdentity,sizeof(plugIdentity),"%s • P%u",hubPowerTypeLabel(ps.plugType),(unsigned)(plug+1));
      if(page==5){
        char poll[16];snprintf(poll,sizeof(poll),"%u SEC",(unsigned)ps.pollInterval);
        uiDisplaySettingCard(hubMoreRect(0),"PLUG STATUS",plugConfigured?(ps.enabled?"ON":"OFF"):"IP REQUIRED",plugIdentity,UI_ORANGE,plugConfigured);
        uiDisplaySettingCard(hubMoreRect(1),"POLL INTERVAL",poll,plugOperational?"10-60 sec • tap / hold":"Configured • Plug inactive",UI_CYAN,plugOperational);
        uiDisplaySettingCard(hubMoreRect(2),"STATUS DISPLAY",hubPowerDisplayModeLabel(ps.displayMode),plugOperational?"Rotate Power / Layer":"Configured • Plug inactive",UI_PURPLE,plugOperational);
        uiDisplaySettingCard(hubMoreRect(3),"BUTTON POWER",dispSettings.buttonPowerControl?"ON":"OFF",plugOperational?"Physical power control":"Configured • Plug inactive",UI_GREEN,plugOperational);
      }else{
        char delay[20];snprintf(delay,sizeof(delay),"%u MIN",(unsigned)ps.autoOffDelayMin);
        const bool autoActive=ps.autoOffEnabled&&plugOperational;
        uiDisplaySettingCard(hubMoreRect(0),"AUTO OFF",ps.autoOffEnabled?"ON":"OFF",plugConfigured?"Power off after print":"IP required for auto off",UI_ORANGE,plugConfigured);
        uiDisplaySettingCard(hubMoreRect(1),"AUTO OFF DELAY",delay,autoActive?"1-240 min • hold reverse":"Configured • Auto Off inactive",UI_CYAN,autoActive);
        uiDisplaySettingCard(hubMoreRect(2),"CANCEL ON DOOR",ps.autoOffCancelOnDoor?"ON":"OFF",autoActive?"Door cancels pending off":"Configured • Auto Off inactive",UI_PURPLE,autoActive);
        uiDisplaySettingCard(hubMoreRect(3),"PLUG CONFIG",plugIdentity,plugConfigured?ps.ip:"IP REQUIRED",UI_GREEN,plugConfigured);
      }
    }
  }

  HubRect back=hubSystemSubBackRect(),next=hubSystemSubNextRect();
  const char* nextLabel=page==0?"COOLDOWN >":(page==1?"LED >":(page==2?"FINISH >":(page==3?"ERROR >":(page==4?"POWER >":(page==5?"AUTO OFF >":"SOUND >")))));
  if(hubLandscape()){
    uiPanelFill(148,210,W-296,54);
    uiDrawFit(g_audioDiagMessage,158,237,W-316,FONT_SMALL,ML_DATUM,g_audioDiagColor,UI_PANEL_2);
  }else{
    uiPanelFill(10,306,W-20,48);
    uiDrawFit(g_audioDiagMessage,20,330,W-40,FONT_SMALL,ML_DATUM,g_audioDiagColor,UI_PANEL_2);
  }
  uiActionButton(back,"< SYSTEM",UI_BLUE);
  uiActionButton(next,nextLabel,UI_PURPLE);
  hubMarkFrameDirty();g_dirty=false;
}

static HubRect hubSystemNetworkCardRect() {
  const int16_t W=tft.width();
  return hubLandscape()?hr(236,44,236,80):hr(8,132,W-16,80);
}

static const char* hubDateFormatLabel(uint8_t fmt) {
  switch (fmt) {
    case 1: return "DD-MM-YYYY";
    case 2: return "MM/DD/YYYY";
    case 3: return "YYYY-MM-DD";
    case 4: return "DD MMM YYYY";
    case 5: return "MMM DD, YYYY";
    default:return "DD.MM.YYYY";
  }
}


// ---------------------------------------------------------------------------
// Workshop OS v11.23 RC2 secure touch UX
// ---------------------------------------------------------------------------
static int16_t hubRc2SX(int16_t x) {
  return (int16_t)((int32_t)x * tft.width() / 480);
}
static int16_t hubRc2SY(int16_t y) {
  return (int16_t)((int32_t)y * tft.height() / 320);
}
static bool hubRc2HitRef(int16_t tx, int16_t ty,
                         int16_t x, int16_t y, int16_t w, int16_t h) {
  const int16_t sx=hubRc2SX(x), sy=hubRc2SY(y);
  const int16_t sw=hubRc2SX(w), sh=hubRc2SY(h);
  return tx>=sx && tx<(sx+sw) && ty>=sy && ty<(sy+sh);
}
static void hubRc2ButtonRef(int16_t x, int16_t y, int16_t w, int16_t h,
                            const char* label, uint16_t accent,
                            bool enabled=true) {
  const int16_t sx=hubRc2SX(x), sy=hubRc2SY(y);
  const int16_t sw=hubRc2SX(w), sh=hubRc2SY(h);
  const uint16_t fill=enabled?UI_PANEL_2:UI_PANEL;
  const uint16_t ink=enabled?UI_TEXT:UI_DIM;
  const uint16_t edge=enabled?accent:UI_BORDER;
  tft.fillRoundRect(sx,sy,sw,sh,10,fill);
  tft.drawRoundRect(sx,sy,sw,sh,10,edge);
  uiDrawFit(label,sx+8,sy+(sh/2),sw-16,FONT_BODY,ML_DATUM,ink,fill);
}
static void hubRc2CardRef(int16_t x, int16_t y, int16_t w, int16_t h,
                          const char* title, const char* value,
                          const char* detail, uint16_t accent) {
  const int16_t sx=hubRc2SX(x), sy=hubRc2SY(y);
  const int16_t sw=hubRc2SX(w), sh=hubRc2SY(h);
  tft.fillRoundRect(sx,sy,sw,sh,10,UI_PANEL_2);
  tft.drawRoundRect(sx,sy,sw,sh,10,UI_BORDER);
  const int16_t railH=(int16_t)(sh>18?sh-16:sh);
  if(railH>0)tft.fillRoundRect(sx+6,sy+8,3,railH,2,accent);
  uiDrawFit(title,sx+16,sy+12,sw-24,FONT_SMALL,TL_DATUM,UI_DIM,UI_PANEL_2);
  uiDrawFit(value,sx+16,sy+(sh/2),sw-24,FONT_BODY,ML_DATUM,UI_TEXT,UI_PANEL_2);
  if(detail && detail[0])
    uiDrawFit(detail,sx+16,sy+sh-10,sw-24,FONT_SMALL,BL_DATUM,UI_DIM,UI_PANEL_2);
}
static void hubRc2PageIndicator(uint8_t page, uint8_t count) {
  char label[20];
  snprintf(label,sizeof(label),"%u / %u",(unsigned)page+1U,(unsigned)count);
  const int16_t sx=hubRc2SX(202), sy=hubRc2SY(42);
  const int16_t sw=hubRc2SX(76), sh=hubRc2SY(20);
  tft.fillRoundRect(sx,sy,sw,sh,9,UI_PANEL);
  tft.drawRoundRect(sx,sy,sw,sh,9,UI_BORDER);
  uiDrawFit(label,sx+4,sy+(sh/2),sw-8,FONT_SMALL,ML_DATUM,UI_DIM,UI_PANEL);
}
static void hubNetworkDiscardEdit() {
  g_networkEditLoaded=false;
  hubLoadNetworkEdit();
  buzzerPlay(BUZZ_CLICK);
  g_dirty=true;
}


// ---------------------------------------------------------------------------
// Workshop OS v11.23 RC2 physical touch finalization
// ---------------------------------------------------------------------------
static uint8_t g_rotationPreviewValue=0;

static const char* hubRc2RotationValueLabel(uint8_t value) {
  static char label[8];
  snprintf(label,sizeof(label),"R%u",(unsigned)(value&3U));
  return label;
}

static void hubRc2OpenRotationPreview() {
  g_rotationPreviewValue=(uint8_t)(dispSettings.rotation&3U);
  g_rotationPreviewMode=true;
  buzzerPlay(BUZZ_CLICK);
  g_dirty=true;
}

static void hubRc2DrawRotationPreview() {
  tft.fillScreen(UI_BG);
  drawHeader("DISPLAY","ROTATION",3);
  hubRc2CardRef(10,66,225,70,"CURRENT",hubRotationLabel(),
                "Persisted orientation",UI_CYAN);
  hubRc2CardRef(245,66,225,70,"PREVIEW",hubRc2RotationValueLabel(g_rotationPreviewValue),
                "Staged - not applied",UI_ORANGE);
  hubRc2ButtonRef(10,146,460,40,"GUARDED - TOUCH MAPPING CHANGES WITH ROTATION",UI_ORANGE);
  hubRc2ButtonRef(10,196,220,52,"PREV",UI_CYAN);
  hubRc2ButtonRef(250,196,220,52,"NEXT",UI_CYAN);
  hubRc2ButtonRef(10,258,140,52,"CANCEL",UI_DIM);
  hubRc2ButtonRef(160,258,310,52,"HOLD TO COMMIT ROTATION",UI_ORANGE);
  hubMarkFrameDirty();
  g_dirty=false;
}

static void drawNetworkEssentials(bool full) {
  (void)full;
  if(!g_networkEditLoaded) hubLoadNetworkEdit();
  const uint8_t page=(uint8_t)(g_networkSettingsPage%HUB_NETWORK_PAGE_COUNT);
  tft.fillScreen(UI_BG);
  const char* title=page==0?"Startup":page==1?"Clock":page==2?"Date":page==3?"Local Name":page==4?"Timezone":page==5?"Address":"Review";
  drawHeader("Network",title,3);
  hubRc2PageIndicator(page,HUB_NETWORK_PAGE_COUNT);

  if(page<=3) {
    const char* label=page==0?"Show IP at Startup":page==1?"Clock Format":page==2?"Date Format":"Local Network Name";
    const char* value=page==0?(netSettings.showIPAtStartup?"ON":"OFF"):page==1?(netSettings.use24h?"24 HOUR":"12 HOUR"):page==2?hubDateFormatLabel(netSettings.dateFormat):(netSettings.mdnsEnabled?"ON":"OFF");
    const char* detail=page==0?"Show this display's address after boot":page==1?"Choose 12-hour or 24-hour time":page==2?"Choose how dates appear":"Allow a friendly name on your local network";
    hubRc2CardRef(20,82,440,132,label,value,detail,page==0?UI_BLUE:UI_CYAN);
    hubRc2ButtonRef(10,258,110,52,"BACK",UI_DIM);
    hubRc2ButtonRef(360,258,110,52,"NEXT",UI_BLUE);
  } else if(page==4) {
    hubRc2CardRef(20,76,440,116,"TIMEZONE",hubTimezoneLabel(),"Choose the timezone used by the display",UI_CYAN);
    hubRc2ButtonRef(20,202,210,48,"PREVIOUS ZONE",UI_BLUE);
    hubRc2ButtonRef(250,202,210,48,"NEXT ZONE",UI_BLUE);
    hubRc2ButtonRef(10,258,110,52,"BACK",UI_DIM);
    hubRc2ButtonRef(360,258,110,52,"NEXT",UI_BLUE);
  } else if(page==5) {
    hubRc2ButtonRef(10,58,460,36,"Changes not applied",UI_ORANGE);
    hubRc2ButtonRef(10,102,130,48,g_networkEditDhcp?"DHCP":"STATIC",UI_ORANGE);
    hubRc2ButtonRef(150,102,70,48,"PREV",UI_CYAN);
    hubRc2ButtonRef(225,102,170,48,hubNetworkFieldLabel(g_networkEditField),UI_CYAN);
    hubRc2ButtonRef(400,102,70,48,"NEXT",UI_CYAN);
    char v0[8],v1[8],v2[8],v3[8];
    snprintf(v0,sizeof(v0),"%u",(unsigned)g_networkEditValues[g_networkEditField][0]);
    snprintf(v1,sizeof(v1),"%u",(unsigned)g_networkEditValues[g_networkEditField][1]);
    snprintf(v2,sizeof(v2),"%u",(unsigned)g_networkEditValues[g_networkEditField][2]);
    snprintf(v3,sizeof(v3),"%u",(unsigned)g_networkEditValues[g_networkEditField][3]);
    hubRc2ButtonRef(10,156,108,48,v0,g_networkEditOctet==0?UI_ORANGE:UI_BLUE);
    hubRc2ButtonRef(127,156,108,48,v1,g_networkEditOctet==1?UI_ORANGE:UI_BLUE);
    hubRc2ButtonRef(244,156,108,48,v2,g_networkEditOctet==2?UI_ORANGE:UI_BLUE);
    hubRc2ButtonRef(361,156,109,48,v3,g_networkEditOctet==3?UI_ORANGE:UI_BLUE);
    hubRc2ButtonRef(10,210,108,48,"-10",UI_CYAN);
    hubRc2ButtonRef(127,210,108,48,"-1",UI_CYAN);
    hubRc2ButtonRef(244,210,108,48,"+1",UI_CYAN);
    hubRc2ButtonRef(361,210,109,48,"+10",UI_CYAN);
    hubRc2ButtonRef(10,264,110,48,"BACK",UI_DIM);
    hubRc2ButtonRef(360,264,110,48,"REVIEW",UI_BLUE);
  } else {
    char ip[20],gw[20],sn[20],dns[20];
    hubFormatIpv4(g_networkEditValues[0],ip,sizeof(ip));
    hubFormatIpv4(g_networkEditValues[1],gw,sizeof(gw));
    hubFormatIpv4(g_networkEditValues[2],sn,sizeof(sn));
    hubFormatIpv4(g_networkEditValues[3],dns,sizeof(dns));
    const bool printerActive=isAnyPrinterConfigured() && displayedPrinter().state.connected && (displayedPrinter().state.printing || displayedPrinter().state.gcodeStateId==GCODE_PAUSE);
    hubRc2ButtonRef(10,58,460,36,printerActive?"Printer active - display will restart":"Review Changes",printerActive?UI_RED:UI_ORANGE);
    hubRc2CardRef(10,100,225,58,g_networkEditDhcp?"MODE":"IP",g_networkEditDhcp?"DHCP":ip,g_networkEditDhcp?"Addressing from network":"Static address",UI_ORANGE);
    hubRc2CardRef(245,100,225,58,"GATEWAY",g_networkEditDhcp?"AUTO":gw,"",UI_CYAN);
    hubRc2CardRef(10,166,225,58,"SUBNET",g_networkEditDhcp?"AUTO":sn,"",UI_CYAN);
    hubRc2CardRef(245,166,225,58,"DNS",g_networkEditDhcp?"AUTO":dns,hubStaticNetworkValid()?(printerActive?"Display reconnects after restart":"Ready to apply"):"Static values incomplete",hubStaticNetworkValid()?(printerActive?UI_ORANGE:UI_GREEN):UI_RED);
    hubRc2ButtonRef(10,252,105,56,"BACK",UI_DIM);
    hubRc2ButtonRef(125,252,105,56,"DISCARD",UI_RED);
    hubRc2ButtonRef(240,252,230,56,"Hold to Apply",hubStaticNetworkValid()?UI_ORANGE:UI_RED,hubStaticNetworkValid());
  }
  hubMarkFrameDirty();g_dirty=false;
}

static void uiHealthDot(int16_t x,int16_t y,const char* label,bool ok,uint16_t goodColor=UI_GREEN) {
  tft.fillCircle(x,y,5,ok?goodColor:UI_RED);uiDrawFit(label,x+10,y,80,FONT_SMALL,ML_DATUM,ok?UI_TEXT:UI_AMBER,UI_PANEL);
}

static HubRect hubUi12SystemBackRect() {
  const int16_t W=tft.width();
  return hubLandscape()?hr(8,212,112,48):hr(8,366,112,48);
}

static HubRect hubUi12SystemPortalRect() {
  const int16_t W=tft.width();
  return hubLandscape()?hr(128,212,W-136,48):hr(128,366,W-136,48);
}

static void drawUi12PortalAccess() {
  const int16_t W=tft.width();const bool wifi=WiFi.status()==WL_CONNECTED;String ip=wifi?WiFi.localIP().toString():String("Wi-Fi required");
  tft.fillScreen(C10_BG);drawHeader("Local Portal",wifi?"Ready":"Offline",3);uiBottomNav(3,nullptr);
  if(hubLandscape()) {
    HubRect card=hr(8,44,W-16,160);hubV1125Card(card,wifi?C10_ACCENT:C10_ORANGE,true);
    uiDrawFit("Authenticated Administration",card.x+16,card.y+14,card.w-32,FONT_LARGE,TL_DATUM,C10_TEXT,C10_SURFACE_2);
    uiDrawFit("Open this device address in a browser on your local network",card.x+16,card.y+58,card.w-32,FONT_SMALL,TL_DATUM,C10_MUTED,C10_SURFACE_2);
    uiDrawFit(ip.c_str(),card.x+16,card.y+84,card.w/2-24,FONT_BODY,TL_DATUM,wifi?C10_ACCENT:C10_ORANGE,C10_SURFACE_2);
    uiDrawFit("Access Code",card.x+card.w/2,card.y+84,100,FONT_SMALL,TL_DATUM,C10_MUTED,C10_SURFACE_2);
    uiDrawFit(securityPortalCode(),card.x+card.w/2,card.y+110,card.w/2-24,FONT_LARGE,TL_DATUM,C10_TEXT,C10_SURFACE_2);
    uiDrawFit("Code changes after every reboot",card.x+16,card.y+144,card.w-32,FONT_SMALL,BL_DATUM,C10_MUTED,C10_SURFACE_2);
  } else {
    HubRect card=hr(8,52,W-16,296);hubV1125Card(card,wifi?C10_ACCENT:C10_ORANGE,true);
    uiDrawFit("Authenticated Administration",card.x+16,card.y+18,card.w-32,FONT_LARGE,TL_DATUM,C10_TEXT,C10_SURFACE_2);
    uiDrawFit("Open this device on your local network",card.x+16,card.y+86,card.w-32,FONT_BODY,TL_DATUM,C10_MUTED,C10_SURFACE_2);
    uiDrawFit(ip.c_str(),card.x+16,card.y+126,card.w-32,FONT_BODY,TL_DATUM,wifi?C10_ACCENT:C10_ORANGE,C10_SURFACE_2);
    uiDrawFit("Access Code",card.x+16,card.y+178,card.w-32,FONT_SMALL,TL_DATUM,C10_MUTED,C10_SURFACE_2);
    uiDrawFit(securityPortalCode(),card.x+16,card.y+210,card.w-32,FONT_LARGE,TL_DATUM,C10_TEXT,C10_SURFACE_2);
    uiDrawFit("Code changes after every reboot",card.x+16,card.y+270,card.w-32,FONT_SMALL,BL_DATUM,C10_MUTED,C10_SURFACE_2);
  }
  hubV1125Action(hubUi12SystemBackRect(),"Back",C10_ACCENT,true,false);hubMarkFrameDirty();g_dirty=false;
}

static void drawUi13DateTime() {
  tft.fillScreen(C10_BG);drawHeader("Date & Time",nullptr,3);uiBottomNav(3,nullptr);
  hubUi13StepperRow(hubUi13RowRect(0),"Time Zone",hubTimezoneLabel(),"Region",C10_ACCENT);
  hubUi13ToggleRow(hubUi13RowRect(1),"24-Hour Time","Use a 24-hour clock",netSettings.use24h,C10_ACCENT);
  hubUi13StepperRow(hubUi13RowRect(2),"Date Format",hubDateFormatLabel(netSettings.dateFormat),"Format",C10_ACCENT);
  hubV1125Action(hubUi13BackRect(),"Back",C10_ACCENT,true,false);hubV1125Action(hubUi13ActionRect(),"Done",C10_ACCENT,true,false);hubMarkFrameDirty();g_dirty=false;
}

static void drawUi13SoftwareUpdate() {
  const int16_t W=tft.width();tft.fillScreen(C10_BG);drawHeader("Software Update",nullptr,3);uiBottomNav(3,nullptr);
  HubRect hero=hubLandscape()?hr(8,48,W-16,86):hr(8,58,W-16,126);hubV1125Card(hero,C10_ACCENT,true);char ver[40];snprintf(ver,sizeof(ver),"Workshop OS %s",SMART_HOME_VERSION);uiDrawFit(ver,hero.x+16,hero.y+14,hero.w-32,FONT_LARGE,TL_DATUM,C10_TEXT,C10_SURFACE_2);uiDrawFit("UI13 · pre-release build",hero.x+16,hero.y+56,hero.w-32,FONT_SMALL,TL_DATUM,C10_ORANGE,C10_SURFACE_2);
  hubUi13InfoRow(hubUi13RowRect(2),"Device Update","Local Portal","On-device install is not enabled in this build",C10_MUTED);
  hubV1125Action(hubUi13BackRect(),"Back",C10_ACCENT,true,false);hubV1125Action(hubUi13ActionRect(),"Local Portal",C10_ACCENT,true,false);hubMarkFrameDirty();g_dirty=false;
}

static void drawUi13Diagnostics() {
  const bool touchOk=hubTouchHealthy(),recoveryOk=recoveryWebReady(),wifi=WiFi.status()==WL_CONNECTED;const bool configured=isAnyPrinterConfigured(),printerOk=configured&&displayedPrinter().state.connected;
  tft.fillScreen(C10_BG);drawHeader("Diagnostics",touchOk&&recoveryOk?"Healthy":"Check Device",3);uiBottomNav(3,nullptr);
  hubUi13InfoRow(hubUi13RowRect(0),"Touch",touchOk?"OK":"Check","Touchscreen input",touchOk?C10_GREEN:C10_ORANGE);
  hubUi13InfoRow(hubUi13RowRect(1),"Recovery",recoveryOk?"Ready":"Starting","Recovery service",recoveryOk?C10_GREEN:C10_ORANGE);
  hubUi13InfoRow(hubUi13RowRect(2),"Connectivity",wifi?(printerOk?"Network + Printer":"Network only"):"Offline","Connectivity is separate from device health",wifi?C10_GREEN:C10_ORANGE);
  hubV1125Action(hubUi13BackRect(),"Back",C10_ACCENT,true,false);hubV1125Action(hubUi13ActionRect(),"Local Portal",C10_ACCENT,true,false);hubMarkFrameDirty();g_dirty=false;
}

static void drawSystem(bool full) {
  if(g_audioSettingsView){drawAudioSettings(full);return;}if(g_networkSettingsView){drawNetworkEssentials(full);return;}if(g_ui12SystemView==1){drawUi12PortalAccess();return;}if(g_ui12SystemView==2){drawUi13DateTime();return;}if(g_ui12SystemView==3){drawUi13SoftwareUpdate();return;}if(g_ui12SystemView==4){drawUi13Diagnostics();return;}
  (void)full;const int16_t W=tft.width();const bool touchOk=hubTouchHealthy(),recoveryOk=recoveryWebReady();const bool deviceHealthy=touchOk&&recoveryOk;const bool wifi=WiFi.status()==WL_CONNECTED;const bool configured=isAnyPrinterConfigured();const bool printerOk=configured&&displayedPrinter().state.connected;tft.fillScreen(C10_BG);drawHeader("System",deviceHealthy?"Healthy":"Check Device",3);uiBottomNav(3,nullptr);
  hubUi12SettingsCard(hubUi13SystemCardRect(0),"Device Health",deviceHealthy?"Healthy":"Needs attention",deviceHealthy?C10_GREEN:C10_ORANGE,false);
  hubUi12SettingsCard(hubUi13SystemCardRect(1),"Connectivity",!wifi?"Offline":(printerOk?"Network + printer":"Network connected"),wifi?C10_GREEN:C10_ORANGE,false);
  hubUi12SettingsCard(hubUi13SystemCardRect(2),"Date & Time",hubTimezoneLabel(),C10_ACCENT,false);
  hubUi12SettingsCard(hubUi13SystemCardRect(3),"Software Update","Version and update options",C10_ACCENT,false);
  hubV1125Action(hubUi13BackRect(),"Back",C10_ACCENT,true,false);hubV1125Action(hubUi13ActionRect(),"Local Portal",C10_ACCENT,true,false);hubMarkFrameDirty();g_dirty=false;
}




} // namespace

void smartHubInit() {
  if (g_initialized) return;
  prefsLoad();
  g_initialized = true;
  g_dirty = true;
}

void smartHubService() {
  if (!g_initialized) smartHubInit();
  unsigned long now = millis();
  if(g_workshopTimerEndMs && (long)(now-g_workshopTimerEndMs)>=0){
    g_workshopTimerEndMs=0;g_workshopTimerDone=true;g_workshopTimerLastSecond=0xFFFFFFFFUL;g_dirty=true;
    buzzerPlay(BUZZ_PRINT_FINISHED);
  } else if(workshopTimerActive()) {
    uint32_t sec=workshopTimerRemainingSeconds();
    if(sec!=g_workshopTimerLastSecond){g_workshopTimerLastSecond=sec;if(getScreenState()==SCREEN_HUB_HOME||getScreenState()==SCREEN_HUB_WORKSHOP||(getScreenState()==SCREEN_HUB_MORE&&g_toolsView))g_dirty=true;}
  }
  if (!g_cfg.enabled || !g_cfg.customUrl[0]) return;


  unsigned long interval =
      (unsigned long)g_cfg.refreshSeconds * 1000UL;

  bool customVisible = getScreenState() == SCREEN_HUB_CUSTOM;
  bool stale = g_custom.fetchedAtMs == 0 ||
               now - g_custom.fetchedAtMs >= interval;
  bool attemptReady = g_lastFetchAttemptMs == 0 ||
                      now - g_lastFetchAttemptMs >= interval;

  bool backgroundDue =
      g_custom.fetchedAtMs == 0 ||
      now - g_custom.fetchedAtMs >= interval * 5UL;

  if (attemptReady && ((customVisible && stale) || backgroundDue)) {
    g_lastFetchAttemptMs = now;
    fetchCustom();
  }
}

bool smartHubAvailable() { return true; }
bool smartHubEnabled() { return g_cfg.enabled; }

bool smartHubIsScreen(ScreenState screen) {
  return screen == SCREEN_HUB_HOME ||
         screen == SCREEN_HUB_PRINTER ||
         screen == SCREEN_HUB_WORKSHOP ||
         screen == SCREEN_HUB_MORE ||
         screen == SCREEN_HUB_CUSTOM ||
         screen == SCREEN_HUB_SYSTEM;
}

bool smartHubIsNativePrinterScreen(ScreenState screen) {
  return screen == SCREEN_HUB_PRINTER;
}

bool smartHubShouldYieldToPrinter(bool printing) {
  // v9.8: native Smart Home Printer is the normal live-print surface.
  // Classic Printer remains an explicit advanced destination.
  (void)printing;
  return false;
}

void smartHubEnter() {
  if (!g_cfg.enabled) return;
  setPage(SCREEN_HUB_HOME);
}

void smartHubEnterIdleHome() {
  if (!g_cfg.enabled) return;
  g_ambientActive = g_ambientEnabled;
  // Idle HOME is not a user hold. A print/HMS event must be able to preempt it
  // immediately instead of waiting out returnSeconds.
  g_userHoldUntilMs = 0;
  g_dirty = true;
  setScreenState(SCREEN_HUB_HOME);
}

void smartHubAdvance() {
  if (!g_cfg.enabled) { smartHubReturnToPrinter(); return; }
  switch (getScreenState()) {
    case SCREEN_HUB_HOME:     setPage(SCREEN_HUB_PRINTER);  break;
    case SCREEN_HUB_PRINTER:  setPage(SCREEN_HUB_WORKSHOP); break;
    case SCREEN_HUB_WORKSHOP: g_ui12SettingsView=0;g_ui12SystemView=0;setPage(SCREEN_HUB_MORE);     break;
    case SCREEN_HUB_MORE:
    case SCREEN_HUB_CUSTOM:
    case SCREEN_HUB_SYSTEM:   setPage(SCREEN_HUB_HOME);     break;
    default:                   setPage(SCREEN_HUB_HOME);     break;
  }
}

void smartHubReturnToPrinter() {
  g_userHoldUntilMs = 0;
  g_dirty = true;
  setScreenState(printerScreenForState());
}

bool smartHubShowPage(const char* pageName) {
  if (!pageName) return false;
  if (strcmp(pageName, "legacy-printer") == 0) { smartHubReturnToPrinter(); return true; }
  if (!g_cfg.enabled) return false;

  if (strcmp(pageName, "home") == 0) { setPage(SCREEN_HUB_HOME); return true; }
  if (strcmp(pageName, "printer") == 0) { setPage(SCREEN_HUB_PRINTER); return true; }
  if (strcmp(pageName, "workshop") == 0) { setPage(SCREEN_HUB_WORKSHOP); return true; }

  if (strcmp(pageName, "more") == 0) {
    g_ui12SettingsView=0;g_ui12SystemView=0;setPage(SCREEN_HUB_MORE);
    g_toolsView = false;
    g_displayExperienceView = false;
    g_displayExperiencePage = 0;
    g_dirty = true;
    return true;
  }

  if (strcmp(pageName, "tools") == 0) {
    g_ui12SettingsView=0;g_ui12SystemView=0;setPage(SCREEN_HUB_MORE);
    g_displayExperienceView = false;
    g_displayExperiencePage = 0;
    g_toolsView = true;
    g_dirty = true;
    return true;
  }

  static const char* const kDisplayPages[] = {
    "display-quick", "display-schedule", "display-behavior",
    "display-visual", "display-clock", "display-alerts", "display-signals",
    "display-theme", "display-gauge-colors", "display-gauge-scales",
    "display-gauge-behavior", "display-glow", "display-layout", "display-extras"
  };
  for (uint8_t i = 0; i < HUB_DISPLAY_PAGE_COUNT; ++i) {
    if (strcmp(pageName, kDisplayPages[i]) == 0 ||
        (i == 0 && strcmp(pageName, "display") == 0)) {
      g_ui12SettingsView=0;g_ui12SystemView=0;setPage(SCREEN_HUB_MORE);
      g_toolsView = false;
      g_displayExperienceView = true;
      g_displayExperiencePage = i;
      g_dirty = true;
      return true;
    }
  }

  if (strcmp(pageName, "settings-experience") == 0) {
    setPage(SCREEN_HUB_MORE);g_toolsView=false;g_displayExperienceView=false;g_networkSettingsView=false;g_audioSettingsView=false;g_ui12SystemView=0;g_ui12SettingsView=1;g_dirty=true;return true;
  }

  if (strcmp(pageName, "settings-printer") == 0) {
    setPage(SCREEN_HUB_MORE);g_toolsView=false;g_displayExperienceView=false;g_networkSettingsView=false;g_audioSettingsView=false;g_ui12SystemView=0;g_ui12SettingsView=4;g_dirty=true;return true;
  }

  if (strcmp(pageName, "settings-update") == 0) {
    setPage(SCREEN_HUB_SYSTEM);g_ui12SettingsView=0;g_networkSettingsView=false;g_audioSettingsView=false;g_ui12SystemView=3;g_dirty=true;return true;
  }

  if (strcmp(pageName, "system-portal") == 0) {
    setPage(SCREEN_HUB_SYSTEM);
    g_ui12SettingsView = 0;
    g_networkSettingsView = false;
    g_audioSettingsView = false;
    g_audioSettingsPage = 0;
    g_ui12SystemView = 1;
    g_dirty = true;
    return true;
  }

  if (strcmp(pageName, "settings-display") == 0) { setPage(SCREEN_HUB_MORE);g_ui12SettingsView=1;g_ui12SystemView=0;g_networkSettingsView=false;g_audioSettingsView=false;g_dirty=true;return true; }
  if (strcmp(pageName, "settings-sounds") == 0) { setPage(SCREEN_HUB_MORE);g_ui12SettingsView=2;g_ui12SystemView=0;g_networkSettingsView=false;g_audioSettingsView=false;g_dirty=true;return true; }
  if (strcmp(pageName, "settings-network") == 0) { setPage(SCREEN_HUB_MORE);g_ui12SettingsView=3;g_ui12SystemView=0;g_networkSettingsView=false;g_audioSettingsView=false;g_dirty=true;return true; }
  if (strcmp(pageName, "settings-printer-power") == 0) { setPage(SCREEN_HUB_MORE);g_ui12SettingsView=4;g_ui12SystemView=0;g_networkSettingsView=false;g_audioSettingsView=false;g_dirty=true;return true; }
  if (strcmp(pageName, "system-date-time") == 0) { setPage(SCREEN_HUB_SYSTEM);g_ui12SettingsView=0;g_ui12SystemView=2;g_networkSettingsView=false;g_audioSettingsView=false;g_dirty=true;return true; }
  if (strcmp(pageName, "system-update") == 0) { setPage(SCREEN_HUB_SYSTEM);g_ui12SettingsView=0;g_ui12SystemView=3;g_networkSettingsView=false;g_audioSettingsView=false;g_dirty=true;return true; }
  if (strcmp(pageName, "system-diagnostics") == 0) { setPage(SCREEN_HUB_SYSTEM);g_ui12SettingsView=0;g_ui12SystemView=4;g_networkSettingsView=false;g_audioSettingsView=false;g_dirty=true;return true; }
  if (strcmp(pageName, "custom") == 0) { setPage(SCREEN_HUB_CUSTOM); return true; }

  if (strcmp(pageName, "system") == 0) {
    g_ui12SystemView = 0;
    setPage(SCREEN_HUB_SYSTEM);
    g_networkSettingsView = false;
    g_audioSettingsView = false;
    g_audioSettingsPage = 0;
    g_dirty = true;
    return true;
  }

  static const char* const kNetworkPages[] = {
    "system-network", "system-time-locale", "system-network-address", "system-network-review"
  };
  for(uint8_t i=0;i<(uint8_t)(sizeof(kNetworkPages)/sizeof(kNetworkPages[0]));i++) {
    if(strcmp(pageName,kNetworkPages[i])==0) {
    g_ui12SystemView = 0;
      setPage(SCREEN_HUB_SYSTEM);
      g_audioSettingsView=false;g_audioSettingsPage=0;
      g_networkSettingsView=true;g_networkSettingsPage=i;g_networkEditLoaded=false;
      g_dirty=true;return true;
    }
  }

  static const char* const kHardwarePages[] = {
    "hardware-sound", "hardware-cooldown", "hardware-led",
    "hardware-finish", "hardware-error", "hardware-power", "hardware-auto-off"
  };
  for (uint8_t i = 0; i < 7; ++i) {
    if (strcmp(pageName, kHardwarePages[i]) == 0) {
    g_ui12SystemView = 0;
      setPage(SCREEN_HUB_SYSTEM);
      g_networkSettingsView = false;
      g_audioSettingsView = true;
      g_audioSettingsPage = i;
      g_dirty = true;
      return true;
    }
  }

  return false;
}

// Prepare a pixel-accurate capture from the same 16-bit PSRAM sprite that is
// committed to the physical LCD. Calling this forces the requested view to be
// fully composed before the web server streams it.
bool smartHubCapturePrepare(uint16_t* width, uint16_t* height) {
  if (!g_cfg.enabled) return false;
  smartHubDraw(getScreenState(), true);
  if (!g_hubFrame || !g_hubFrame->getBuffer() || g_hubFrameW <= 0 || g_hubFrameH <= 0)
    return false;
  if (width) *width = (uint16_t)g_hubFrameW;
  if (height) *height = (uint16_t)g_hubFrameH;
  return true;
}

// Convert one sprite row from its logical RGB565 pixels to RGB888. readPixel()
// deliberately returns standard RGB565 regardless of the sprite's internal
// byte order, so the capture stays correct if LovyanGFX storage details change.
bool smartHubCaptureRgbRow(uint16_t y, uint8_t* out, size_t outLen) {
  if (!out || !g_hubFrame || !g_hubFrame->getBuffer()) return false;
  if (y >= (uint16_t)g_hubFrameH) return false;
  const size_t need = (size_t)g_hubFrameW * 3U;
  if (outLen < need) return false;

  for (int16_t x = 0; x < g_hubFrameW; ++x) {
    const uint16_t c = g_hubFrame->readPixel(x, (int16_t)y);
    const uint8_t r5 = (uint8_t)((c >> 11) & 0x1F);
    const uint8_t g6 = (uint8_t)((c >> 5) & 0x3F);
    const uint8_t b5 = (uint8_t)(c & 0x1F);
    out[(size_t)x * 3U + 0U] = (uint8_t)((r5 << 3) | (r5 >> 2));
    out[(size_t)x * 3U + 1U] = (uint8_t)((g6 << 2) | (g6 >> 4));
    out[(size_t)x * 3U + 2U] = (uint8_t)((b5 << 3) | (b5 >> 2));
  }
  return true;
}

void smartHubDraw(ScreenState screen, bool forceRedraw) {
  if (!g_cfg.enabled) return;

  lgfx::LovyanGFX* panel = tft_ptr;
  const bool buffered = hubEnsureFrame();
  if (buffered) {
    panel = g_hubPanelCanvas;
    tft_ptr = g_hubFrame;
    g_hubFrameDirty = false;
  }

  const bool effectiveForce = forceRedraw || (buffered && !g_hubFramePrimed);
  switch (screen) {
    case SCREEN_HUB_HOME:     drawHome(effectiveForce);     break;
    case SCREEN_HUB_PRINTER:  drawPrinter(effectiveForce);  break;
    case SCREEN_HUB_WORKSHOP: drawWorkshop(effectiveForce); break;
    case SCREEN_HUB_MORE:     drawMore(effectiveForce);     break;
    case SCREEN_HUB_CUSTOM:   drawCustom(effectiveForce);   break;
    case SCREEN_HUB_SYSTEM:   drawSystem(effectiveForce);   break;
    default: break;
  }

  if (buffered) {
    // Restore the real panel before the sprite pushes to its parent device.
    tft_ptr = panel;
    if (g_hubFrameDirty || effectiveForce) {
      g_hubFrameDirty = true;
      hubCommitFrame();
    }
  }
}


static void mapHubTouch(uint16_t rawX, uint16_t rawY, int16_t& x, int16_t& y) {
  switch (dispSettings.rotation & 3) {
    case 1: x = (int16_t)rawY;       y = (int16_t)(319 - rawX); break;
    case 2: x = (int16_t)(319-rawX); y = (int16_t)(479 - rawY); break;
    case 3: x = (int16_t)(479-rawY); y = (int16_t)rawX; break;
    default:x = (int16_t)rawX;       y = (int16_t)rawY; break;
  }
  if (x < 0) x = 0; if (y < 0) y = 0;
  if (x >= tft.width()) x = tft.width() - 1;
  if (y >= tft.height()) y = tft.height() - 1;
}


void smartHubUpdateHoldProgress(uint16_t rawX, uint16_t rawY, uint32_t holdMs) {
  static uint8_t lastKind=0;
  static uint8_t lastSegments=255;
  if(holdMs==0){lastKind=0;lastSegments=255;return;}
  if(!g_cfg.enabled||!smartHubIsScreen(getScreenState()))return;
  int16_t x=0,y=0;mapHubTouch(rawX,rawY,x,y);
  uint8_t kind=0;int16_t bx=0,by=0,bw=0,bh=0;const char* label=nullptr;
  if(g_networkSettingsView && (g_networkSettingsPage%HUB_NETWORK_PAGE_COUNT)==6 && hubStaticNetworkValid() && hubRc2HitRef(x,y,240,252,230,56)){
    kind=1;bx=240;by=252;bw=230;bh=56;label="Keep Holding";
  }else if(g_displayExperienceView && g_rotationPreviewMode && hubRc2HitRef(x,y,160,258,310,52)){
    kind=2;bx=160;by=258;bw=310;bh=52;label="Keep Holding";
  }else if(getScreenState()==SCREEN_HUB_PRINTER && g_printerMode==HUB_PRINTER_CONTROL && isAnyPrinterConfigured() && hubPrinterActionRect(3).contains(x,y)){
    BambuState& s=displayedPrinter().state;const bool paused=s.gcodeStateId==GCODE_PAUSE;
    if(s.connected&&(s.printing||paused)){HubRect r=hubPrinterActionRect(3);kind=3;bx=r.x;by=r.y;bw=r.w;bh=r.h;label="Keep Holding";}else{lastKind=0;lastSegments=255;return;}
  }else{lastKind=0;lastSegments=255;return;}
  uint8_t segments=(uint8_t)((holdMs*5U+649U)/650U);if(segments>5U)segments=5U;
  if(kind==lastKind && segments==lastSegments)return;lastKind=kind;lastSegments=segments;
  if(kind==3)hubV1125Action(hr(bx,by,bw,bh),label,W25_DANGER,true,true);else hubRc2ButtonRef(bx,by,bw,bh,label,UI_ORANGE,true);
  int16_t px=kind==3?(int16_t)(bx+10):hubRc2SX((int16_t)(bx+10));
  int16_t py=kind==3?(int16_t)(by+bh-13):hubRc2SY((int16_t)(by+bh-13));
  int16_t total=kind==3?(int16_t)(bw-20):hubRc2SX((int16_t)(bw-20));
  int16_t gap=kind==3?3:hubRc2SX(3);if(gap<2)gap=2;
  int16_t sh=kind==3?8:hubRc2SY(8);if(sh<5)sh=5;
  int16_t sw=(int16_t)((total-gap*4)/5);if(sw<5)sw=5;
  for(uint8_t i=0;i<5;i++){const uint16_t c=(i<segments)?(kind==3?W25_DANGER:UI_ORANGE):UI_BORDER;tft.fillRoundRect((int16_t)(px+i*(sw+gap)),py,sw,sh,3,c);}
  hubMarkFrameDirty();
}

bool smartHubHandleTouch(uint16_t rawX, uint16_t rawY, bool longPress) {
  smartHubUpdateHoldProgress(rawX,rawY,0);
  if (!g_cfg.enabled || !smartHubIsScreen(getScreenState())) return false;
  int16_t x=0,y=0;mapHubTouch(rawX,rawY,x,y);ScreenState cur=getScreenState();
  if(longPress&&cur==SCREEN_HUB_CUSTOM){g_widgetEditMode=!g_widgetEditMode;g_widgetSelected=0;g_dirty=true;return true;}
  for(uint8_t i=0;i<4;i++)if(hubNavRect(i).contains(x,y)){if(i==0)setPage(SCREEN_HUB_HOME);else if(i==1)setPage(SCREEN_HUB_PRINTER);else if(i==2)setPage(SCREEN_HUB_WORKSHOP);else{if(cur==SCREEN_HUB_MORE&&(g_toolsView||g_displayExperienceView)){g_toolsView=false;g_displayExperienceView=false;g_displayExperiencePage=0;g_dirty=true;}else g_ui12SettingsView=0;g_ui12SystemView=0;setPage(SCREEN_HUB_MORE);}return true;}
  if(cur==SCREEN_HUB_CUSTOM&&g_widgetEditMode){for(uint8_t i=0;i<4;i++)if(hubCustomRect(i).contains(x,y)){g_widgetSelected=i;g_widgets[i]=(uint8_t)((g_widgets[i]+1)%HUB_W_COUNT);prefsSave();g_dirty=true;return true;}return true;}
  if(cur==SCREEN_HUB_HOME){
    if(g_ambientActive){g_ambientActive=false;g_dirty=true;return true;}
    if(hubHomeRect(0).contains(x,y)){setPage(SCREEN_HUB_WORKSHOP);return true;}
    if(hubHomeRect(1).contains(x,y)){setPage(SCREEN_HUB_PRINTER);return true;}
    if(hubHomeRect(2).contains(x,y)||hubHomeRect(3).contains(x,y)||hubHomeRect(4).contains(x,y)){setPage(SCREEN_HUB_SYSTEM);return true;}
    return true;
  }
  if(cur==SCREEN_HUB_MORE){
    if(g_displayExperienceView){
      if(g_rotationPreviewMode){
        if(hubRc2HitRef(x,y,10,196,220,52)){
          g_rotationPreviewValue=(uint8_t)((g_rotationPreviewValue+3U)%4U);
          buzzerPlay(BUZZ_CLICK);g_dirty=true;return true;
        }
        if(hubRc2HitRef(x,y,250,196,220,52)){
          g_rotationPreviewValue=(uint8_t)((g_rotationPreviewValue+1U)%4U);
          buzzerPlay(BUZZ_CLICK);g_dirty=true;return true;
        }
        if(hubRc2HitRef(x,y,10,258,140,52)){
          g_rotationPreviewMode=false;buzzerPlay(BUZZ_CLICK);g_dirty=true;return true;
        }
        if(hubRc2HitRef(x,y,160,258,310,52)){
          if(longPress){
            dispSettings.rotation=(uint8_t)(g_rotationPreviewValue&3U);
            g_rotationPreviewMode=false;
            hubPersistDisplayExpert();
          }else{
            buzzerPlay(BUZZ_CLICK);g_dirty=true;
          }
          return true;
        }
        return true;
      }

      const bool hubRc2Reverse=(x<tft.width()/2);
      if(hubDisplayPagerRect().contains(x,y)){
        g_displayExperiencePage=hubRc2Reverse
          ? (uint8_t)((g_displayExperiencePage+HUB_DISPLAY_PAGE_COUNT-1U)%HUB_DISPLAY_PAGE_COUNT)
          : (uint8_t)((g_displayExperiencePage+1U)%HUB_DISPLAY_PAGE_COUNT);
        buzzerPlay(BUZZ_CLICK);g_dirty=true;return true;
      }
      static const uint8_t mainLevels[4] = {64,128,192,255};
      static const uint8_t standbyLevels[5] = {0,64,128,192,255};
      for(uint8_t i=0;i<4;i++)if(hubMoreRect(i).contains(x,y)){
        if(g_displayExperiencePage==0){
          if(i==0){brightness=hubStepPreset(brightness,mainLevels,4,hubRc2Reverse);hubPersistDisplay(true);}
          else if(i==1){dpSettings.screensaverBrightness=hubStepPreset(dpSettings.screensaverBrightness,standbyLevels,5,hubRc2Reverse);hubPersistDisplay(false);}
          else if(i==2){dpSettings.nightModeEnabled=!dpSettings.nightModeEnabled;hubPersistDisplay(true);}
          else{hubCycleAfterPrint(hubRc2Reverse);hubPersistDisplay(false);}
        }else if(g_displayExperiencePage==1){
          if(i==0){dpSettings.nightBrightness=hubStepPreset(dpSettings.nightBrightness,standbyLevels,5,hubRc2Reverse);hubPersistDisplay(true);}
          else if(i==1){dpSettings.nightStartHour=hubStepHour(dpSettings.nightStartHour,hubRc2Reverse);hubPersistDisplay(true);}
          else if(i==2){dpSettings.nightEndHour=hubStepHour(dpSettings.nightEndHour,hubRc2Reverse);hubPersistDisplay(true);}
          else{dpSettings.finishDisplayMins=hubStepFinishDelay(dpSettings.finishDisplayMins,hubRc2Reverse);hubPersistDisplay(false);}
        }else if(g_displayExperiencePage==2){
          if(i==0){dpSettings.doorAckEnabled=!dpSettings.doorAckEnabled;hubPersistDisplay(false);}
          else if(i==1){dpSettings.keepPrintScreen=!dpSettings.keepPrintScreen;hubPersistDisplay(false);}
          else if(i==2){dpSettings.finishShowTime=!dpSettings.finishShowTime;hubPersistDisplay(false);}
          else{dispSettings.timeDisplayMode=(uint8_t)((dispSettings.timeDisplayMode+(hubRc2Reverse?2U:1U))%3U);hubPersistDisplay(false);}
        }else if(g_displayExperiencePage==3){
          if(i==0){dispSettings.animatedBar=!dispSettings.animatedBar;hubPersistDisplay(false);}
          else if(i==1){dispSettings.smallLabels=!dispSettings.smallLabels;hubPersistDisplay(false);}
          else if(i==2){dispSettings.fanMatchPrinter=!dispSettings.fanMatchPrinter;hubPersistDisplay(false);}
          else{dispSettings.hideStatusReadout=!dispSettings.hideStatusReadout;hubPersistDisplay(false);}
        }else if(g_displayExperiencePage==4){
          if(i==0){dispSettings.pongClock=!dispSettings.pongClock;hubPersistDisplay(false);}
          else if(i==1){dispSettings.clockTimeSize=(uint8_t)((dispSettings.clockTimeSize+(hubRc2Reverse?3U:1U))%4U);hubPersistDisplay(false);}
          else if(i==2){dispSettings.clockDateSize=(uint8_t)((dispSettings.clockDateSize+(hubRc2Reverse?3U:1U))%4U);hubPersistDisplay(false);}
          else{dispSettings.hideClockDate=!dispSettings.hideClockDate;hubPersistDisplay(false);}
        }else if(g_displayExperiencePage==5){
#if HAS_HMS_UI
          if(i==0){dispSettings.hmsEnabled=!dispSettings.hmsEnabled;hubPersistDisplay(false);}
          else if(i==1){dispSettings.hmsSeverityAll=!dispSettings.hmsSeverityAll;hubPersistDisplay(false);}
          else if(i==2){dispSettings.hmsAutoPresent=(uint8_t)((dispSettings.hmsAutoPresent+(hubRc2Reverse?2U:1U))%3U);hubPersistDisplay(false);}
          else{dispSettings.hmsLookupOnline=!dispSettings.hmsLookupOnline;hubPersistDisplay(false);}
#endif
        }else if(g_displayExperiencePage==6){
#if HAS_HMS_UI
          const uint8_t bit=(uint8_t)(1U<<i);
          dispSettings.hmsAlertMask=(uint8_t)(dispSettings.hmsAlertMask^bit);hubPersistDisplay(false);
#endif
        }else if(g_displayExperiencePage==7){
          if(i==0){hubCycleTheme(hubRc2Reverse);hubPersistDisplayExpert();}
          else if(i==1){dispSettings.clockTimeColor=hubCycleExpertColor(dispSettings.clockTimeColor,hubRc2Reverse);hubPersistDisplayExpert();}
          else if(i==2){dispSettings.clockDateColor=hubCycleExpertColor(dispSettings.clockDateColor,hubRc2Reverse);hubPersistDisplayExpert();}
          else{hubApplyThemePreset(0);hubPersistDisplayExpert();}
        }else if(g_displayExperiencePage==8){
          GaugeColors* gc=hubSelectedGaugeColors();
          if(i==0){g_displayGaugeColorIndex=hubRc2Reverse?(uint8_t)((g_displayGaugeColorIndex+11U)%12U):(uint8_t)((g_displayGaugeColorIndex+1U)%12U);buzzerPlay(BUZZ_CLICK);g_dirty=true;}
          else if(i==1){gc->arc=hubCycleExpertColor(gc->arc,hubRc2Reverse);hubPersistDisplayExpert();}
          else if(i==2){gc->label=hubCycleExpertColor(gc->label,hubRc2Reverse);hubPersistDisplayExpert();}
          else{gc->value=hubCycleExpertColor(gc->value,hubRc2Reverse);hubPersistDisplayExpert();}
        }else if(g_displayExperiencePage==9){
          static const uint16_t nozzleScale[] = {100,150,200,250,300,350,400};
          static const uint16_t bedScale[] = {40,60,80,100,120,150};
          static const uint16_t chamberScale[] = {30,40,50,60,80,100,120};
          static const uint16_t powerScale[] = {100,250,500,750,1000,1500,2000,3000,5000};
          if(i==0)dispSettings.nozzleScaleMax=hubStepPreset16(dispSettings.nozzleScaleMax,nozzleScale,7,hubRc2Reverse);
          else if(i==1)dispSettings.bedScaleMax=hubStepPreset16(dispSettings.bedScaleMax,bedScale,6,hubRc2Reverse);
          else if(i==2)dispSettings.chamberScaleMax=hubStepPreset16(dispSettings.chamberScaleMax,chamberScale,7,hubRc2Reverse);
          else dispSettings.powerScaleW=hubStepPreset16(dispSettings.powerScaleW,powerScale,9,hubRc2Reverse);
          hubPersistDisplayExpert();
        }else if(g_displayExperiencePage==10){
          static const uint8_t warningPct[] = {0,50,60,70,80,90,100};
          if(i==0){dispSettings.gaugeSmoothing=(uint8_t)((dispSettings.gaugeSmoothing+(hubRc2Reverse?3U:1U))%4U);hubPersistDisplayExpert();}
          else if(i==1){dispSettings.warnThresholdPct=hubStepPreset(dispSettings.warnThresholdPct,warningPct,7,hubRc2Reverse);hubPersistDisplayExpert();}
          else if(i==2){dispSettings.warnColor=hubCycleExpertColor(dispSettings.warnColor,hubRc2Reverse);hubPersistDisplayExpert();}
          else{dispSettings.gaugeSmoothing=2;dispSettings.warnThresholdPct=0;dispSettings.warnColor=CLR_RED;hubPersistDisplayExpert();}
        }else if(g_displayExperiencePage==11){
          if(i==0){dispSettings.glowMode=(uint8_t)((dispSettings.glowMode+(hubRc2Reverse?2U:1U))%3U);hubPersistDisplayExpert();}
          else if(i==1){dispSettings.glowStyle=(uint8_t)((dispSettings.glowStyle+(hubRc2Reverse?2U:1U))%3U);hubPersistDisplayExpert();}
          else if(i==2){dispSettings.glowDuration=(uint8_t)((dispSettings.glowDuration+(hubRc2Reverse?2U:1U))%3U);hubPersistDisplayExpert();}
          else{dispSettings.glowColor=hubCycleExpertColor(dispSettings.glowColor,hubRc2Reverse);hubPersistDisplayExpert();}
        }else if(g_displayExperiencePage==12){
          if(i==0)dispSettings.landscape8Slots=!dispSettings.landscape8Slots;
          else if(i==1)dispSettings.portrait9Slots=!dispSettings.portrait9Slots;
          else if(i==2)rotState.splitEnabled=!rotState.splitEnabled;
          else rotState.splitForce=!rotState.splitForce;
          hubPersistDisplayExpert();
        }else{
          if(i==0){dispSettings.showClockInfo=!dispSettings.showClockInfo;hubPersistDisplayExpert();}
          else if(i==1){dispSettings.amsTrayTypes=!dispSettings.amsTrayTypes;hubPersistDisplayExpert();}
          else if(i==3){hubRc2OpenRotationPreview();}
          else{buzzerPlay(BUZZ_CLICK);g_dirty=true;}
        }
        return true;
      }
      return true;
    }
    if(g_toolsView){
      for(uint8_t i=0;i<4;i++)if(hubToolsPresetRect(i).contains(x,y)){startWorkshopTimer(g_timerPresets[i]);return true;}
      for(uint8_t i=0;i<4;i++)if(hubToolsActionRect(i).contains(x,y)){
        if(i==0){if(workshopTimerActive()||g_workshopTimerDone)clearWorkshopTimer();else{g_ambientEnabled=!g_ambientEnabled;prefsSave();g_dirty=true;}}
        else if(i==1){if(powerConfirmOpenForSlot(rotState.displayIndex))buzzerPlay(BUZZ_CLICK);else setPrinterFeedback(0,"Power not mapped",1200);}
        else if(i==2)setPage(SCREEN_HUB_SYSTEM);
        else smartHubReturnToPrinter();
        return true;
      }
      return true;
    }
    if(g_ui12SettingsView){
      if(g_ui12SettingsView==1){
        static const uint8_t mainLevels[4]={64,128,192,255};
        static const uint8_t standbyLevels[5]={0,64,128,192,255};
        if(hubUi13MinusRect(0).contains(x,y)){brightness=hubStepPreset(brightness,mainLevels,4,true);hubPersistDisplay(true);return true;}
        if(hubUi13PlusRect(0).contains(x,y)){brightness=hubStepPreset(brightness,mainLevels,4,false);hubPersistDisplay(true);return true;}
        if(hubUi13MinusRect(1).contains(x,y)){dpSettings.screensaverBrightness=hubStepPreset(dpSettings.screensaverBrightness,standbyLevels,5,true);hubPersistDisplay(false);return true;}
        if(hubUi13PlusRect(1).contains(x,y)){dpSettings.screensaverBrightness=hubStepPreset(dpSettings.screensaverBrightness,standbyLevels,5,false);hubPersistDisplay(false);return true;}
        if(hubUi13ToggleRect(2).contains(x,y)){dpSettings.nightModeEnabled=!dpSettings.nightModeEnabled;hubPersistDisplay(true);return true;}
        if(hubUi13BackRect().contains(x,y)){g_ui12SettingsView=0;buzzerPlay(BUZZ_CLICK);g_dirty=true;return true;}
        if(hubUi13ActionRect().contains(x,y)){g_ui12SettingsView=5;buzzerPlay(BUZZ_CLICK);g_dirty=true;return true;}
        return true;
      }
      if(g_ui12SettingsView==5){
        if(hubUi13MinusRect(0).contains(x,y)){hubCycleAfterPrint(true);hubPersistDisplay(false);return true;}
        if(hubUi13PlusRect(0).contains(x,y)){hubCycleAfterPrint(false);hubPersistDisplay(false);return true;}
        if(hubUi13MinusRect(1).contains(x,y)){dpSettings.finishDisplayMins=hubStepFinishDelay(dpSettings.finishDisplayMins,true);hubPersistDisplay(false);return true;}
        if(hubUi13PlusRect(1).contains(x,y)){dpSettings.finishDisplayMins=hubStepFinishDelay(dpSettings.finishDisplayMins,false);hubPersistDisplay(false);return true;}
        if(hubUi13ToggleRect(2).contains(x,y)){dispSettings.animatedBar=!dispSettings.animatedBar;hubPersistDisplay(false);return true;}
        if(hubUi13BackRect().contains(x,y)){g_ui12SettingsView=1;buzzerPlay(BUZZ_CLICK);g_dirty=true;return true;}
        if(hubUi13ActionRect().contains(x,y)){g_ui12SettingsView=0;buzzerPlay(BUZZ_CLICK);g_dirty=true;return true;}
        return true;
      }
      if(g_ui12SettingsView==2){
        if(hubUi13ToggleRect(0).contains(x,y)){buzzerSettings.enabled=!buzzerSettings.enabled;saveBuzzerSettings();initBuzzer();buzzerPlay(BUZZ_CLICK);g_dirty=true;return true;}
        if(hubUi13ToggleRect(1).contains(x,y)){buzzerSettings.buttonClick=!buzzerSettings.buttonClick;saveBuzzerSettings();buzzerPlay(BUZZ_CLICK);g_dirty=true;return true;}
        if(hubUi13ToggleRect(2).contains(x,y)){buzzerSettings.bedCooldownAlert=!buzzerSettings.bedCooldownAlert;saveBuzzerSettings();buzzerPlay(BUZZ_CLICK);g_dirty=true;return true;}
        if(hubUi13BackRect().contains(x,y)){g_ui12SettingsView=0;buzzerPlay(BUZZ_CLICK);g_dirty=true;return true;}
        if(hubUi13ActionRect().contains(x,y)){g_ui12SettingsView=6;buzzerPlay(BUZZ_CLICK);g_dirty=true;return true;}
        return true;
      }
      if(g_ui12SettingsView==6){
#if HAS_HMS_UI
        if(hubUi13ToggleRect(0).contains(x,y)){dispSettings.hmsEnabled=!dispSettings.hmsEnabled;hubPersistDisplay(false);return true;}
        if(hubUi13MinusRect(1).contains(x,y)||hubUi13PlusRect(1).contains(x,y)){dispSettings.hmsSeverityAll=!dispSettings.hmsSeverityAll;hubPersistDisplay(false);return true;}
        if(hubUi13MinusRect(2).contains(x,y)){dispSettings.hmsAutoPresent=(uint8_t)((dispSettings.hmsAutoPresent+2U)%3U);hubPersistDisplay(false);return true;}
        if(hubUi13PlusRect(2).contains(x,y)){dispSettings.hmsAutoPresent=(uint8_t)((dispSettings.hmsAutoPresent+1U)%3U);hubPersistDisplay(false);return true;}
#endif
        if(hubUi13BackRect().contains(x,y)){g_ui12SettingsView=2;buzzerPlay(BUZZ_CLICK);g_dirty=true;return true;}
        if(hubUi13ActionRect().contains(x,y)){g_ui12SettingsView=7;buzzerPlay(BUZZ_CLICK);g_dirty=true;return true;}
        return true;
      }
      if(g_ui12SettingsView==7){
#if HAS_HMS_UI
        if(hubUi13ToggleRect(0).contains(x,y)){dispSettings.hmsAlertMask^=0x02U;hubPersistDisplay(false);return true;}
        if(hubUi13ToggleRect(1).contains(x,y)){dispSettings.hmsAlertMask^=0x04U;hubPersistDisplay(false);return true;}
        if(hubUi13ToggleRect(2).contains(x,y)){dispSettings.hmsAlertMask^=0x08U;hubPersistDisplay(false);return true;}
#endif
        if(hubUi13BackRect().contains(x,y)){g_ui12SettingsView=6;buzzerPlay(BUZZ_CLICK);g_dirty=true;return true;}
        if(hubUi13ActionRect().contains(x,y)){g_ui12SettingsView=0;buzzerPlay(BUZZ_CLICK);g_dirty=true;return true;}
        return true;
      }
      if(g_ui12SettingsView==3){
        if(hubUi13ToggleRect(1).contains(x,y)){netSettings.mdnsEnabled=!netSettings.mdnsEnabled;saveSettings();buzzerPlay(BUZZ_CLICK);g_dirty=true;return true;}
        if(hubUi13ToggleRect(2).contains(x,y)){netSettings.showIPAtStartup=!netSettings.showIPAtStartup;saveSettings();buzzerPlay(BUZZ_CLICK);g_dirty=true;return true;}
        if(hubUi13BackRect().contains(x,y)){g_ui12SettingsView=0;buzzerPlay(BUZZ_CLICK);g_dirty=true;return true;}
        if(hubUi13ActionRect().contains(x,y)){g_ui12SettingsView=0;g_ui12SystemView=1;g_networkSettingsView=false;g_audioSettingsView=false;setPage(SCREEN_HUB_SYSTEM);buzzerPlay(BUZZ_CLICK);g_dirty=true;return true;}
        return true;
      }
      if(g_ui12SettingsView==4){
        const bool configured=isAnyPrinterConfigured();const uint8_t plug=configured?hubPowerConfigPlug():0xFF;
        if(hubUi13ToggleRect(2).contains(x,y)&&plug!=0xFF){TasmotaSettings& ps=tasmotaSettings[plug];if(ps.autoOffEnabled){ps.autoOffEnabled=false;hubPersistPower("Printer auto-off disabled",C10_MUTED);}else if(ps.enabled&&ps.ip[0]){g_ui12SettingsView=9;buzzerPlay(BUZZ_CLICK);g_dirty=true;}else{g_ui12SettingsView=0;g_ui12SystemView=1;setPage(SCREEN_HUB_SYSTEM);buzzerPlay(BUZZ_CLICK);g_dirty=true;}return true;}
        if(hubUi13BackRect().contains(x,y)){g_ui12SettingsView=0;buzzerPlay(BUZZ_CLICK);g_dirty=true;return true;}
        if(hubUi13ActionRect().contains(x,y)&&plug!=0xFF){g_ui12SettingsView=8;buzzerPlay(BUZZ_CLICK);g_dirty=true;return true;}
        return true;
      }
      if(g_ui12SettingsView==8){
        const bool configured=isAnyPrinterConfigured();const uint8_t plug=configured?hubPowerConfigPlug():0xFF;
        if(plug!=0xFF){TasmotaSettings& ps=tasmotaSettings[plug];if(hubUi13MinusRect(0).contains(x,y)){ps.autoOffDelayMin=hubStepAutoOffDelay(ps.autoOffDelayMin,true);hubPersistPower("Auto-off delay updated",C10_ACCENT);return true;}if(hubUi13PlusRect(0).contains(x,y)){ps.autoOffDelayMin=hubStepAutoOffDelay(ps.autoOffDelayMin,false);hubPersistPower("Auto-off delay updated",C10_ACCENT);return true;}if(hubUi13ToggleRect(1).contains(x,y)){ps.autoOffCancelOnDoor=!ps.autoOffCancelOnDoor;hubPersistPower("Door-cancel setting updated",C10_ACCENT);return true;}}
        if(hubUi13BackRect().contains(x,y)){g_ui12SettingsView=4;buzzerPlay(BUZZ_CLICK);g_dirty=true;return true;}
        if(hubUi13ActionRect().contains(x,y)){g_ui12SettingsView=0;g_ui12SystemView=1;setPage(SCREEN_HUB_SYSTEM);buzzerPlay(BUZZ_CLICK);g_dirty=true;return true;}
        return true;
      }
      if(g_ui12SettingsView==9){
        if(hubUi13BackRect().contains(x,y)){g_ui12SettingsView=4;buzzerPlay(BUZZ_CLICK);g_dirty=true;return true;}
        if(hubUi13ActionRect().contains(x,y)){const bool configured=isAnyPrinterConfigured();const uint8_t plug=configured?hubPowerConfigPlug():0xFF;if(plug!=0xFF){TasmotaSettings& ps=tasmotaSettings[plug];if(ps.enabled&&ps.ip[0]){ps.autoOffEnabled=true;hubPersistPower("Printer auto-off enabled",C10_GREEN);}}g_ui12SettingsView=4;g_dirty=true;return true;}
        return true;
      }
      return true;
    }
    for(uint8_t i=0;i<5;i++)if(hubUi12SettingsRect(i).contains(x,y)){
      g_displayExperienceView=false;g_toolsView=false;g_networkSettingsView=false;g_audioSettingsView=false;g_ui12SystemView=0;
      if(i<4){g_ui12SettingsView=(uint8_t)(i+1U);buzzerPlay(BUZZ_CLICK);g_dirty=true;}
      else{g_ui12SettingsView=0;setPage(SCREEN_HUB_SYSTEM);buzzerPlay(BUZZ_CLICK);g_dirty=true;}
      return true;
    }return true;}
  if(cur==SCREEN_HUB_PRINTER){
    for(uint8_t i=0;i<3;i++)if(hubV1125PrinterModeRect(i).contains(x,y)){g_printerMode=i;buzzerPlay(BUZZ_CLICK);g_dirty=true;return true;}
    if(!isAnyPrinterConfigured())return true;
    if(g_printerMode!=HUB_PRINTER_CONTROL)return true;
    BambuState&s=displayedPrinter().state;const uint8_t slot=rotState.displayIndex;const bool paused=(s.gcodeStateId==GCODE_PAUSE);const bool active=s.printing||paused;
    if(hubPrinterActionRect(0).contains(x,y)){if(s.connected){requestLightCommand(slot,s.lightState!=1);setPrinterFeedback(0,"Light sent");buzzerPlay(BUZZ_CLICK);}return true;}
    if(hubPrinterActionRect(1).contains(x,y)){if(s.connected&&active){const bool ok=requestPrinterControlCommand(slot,paused?PRINTER_CTRL_RESUME:PRINTER_CTRL_PAUSE);if(ok){setPrinterFeedback(1,paused?"Resume sent":"Pause sent");buzzerPlay(BUZZ_CLICK);}}return true;}
    if(hubPrinterActionRect(2).contains(x,y)){if(powerConfirmOpenForSlot(slot))buzzerPlay(BUZZ_CLICK);else setPrinterFeedback(0,"Power not mapped",1200);return true;}
    if(hubPrinterActionRect(3).contains(x,y)){if(s.connected&&active&&longPress){if(requestPrinterControlCommand(slot,PRINTER_CTRL_STOP)){setPrinterFeedback(3,"Stop sent",1800);buzzerPlay(BUZZ_CLICK);}}else if(s.connected&&active){setPrinterFeedback(3,"Hold to Stop",1000);}return true;}
    return true;
  }
  if(cur==SCREEN_HUB_WORKSHOP){
    for(uint8_t i=0;i<4;i++)if(hubWorkshopActionRect(i).contains(x,y)){
      if(i==0&&isAnyPrinterConfigured()){BambuState&s=displayedPrinter().state;if(s.connected){requestLightCommand(rotState.displayIndex,s.lightState!=1);buzzerPlay(BUZZ_CLICK);}g_dirty=true;}
      else if(i==1){g_ui12SettingsView=0;g_ui12SystemView=0;setPage(SCREEN_HUB_MORE);g_displayExperienceView=false;g_toolsView=true;g_dirty=true;}
      else if(i==2)setPage(SCREEN_HUB_SYSTEM);
      else if(i==3)setPage(SCREEN_HUB_PRINTER);
      return true;
    }
    return true;
  }
  if(cur==SCREEN_HUB_SYSTEM){
    if(!g_audioSettingsView&&!g_networkSettingsView){
      if(g_ui12SystemView==1){if(hubUi12SystemBackRect().contains(x,y)){g_ui12SystemView=0;buzzerPlay(BUZZ_CLICK);g_dirty=true;}return true;}
      if(g_ui12SystemView==2){
        if(hubUi13MinusRect(0).contains(x,y)){hubStepTimezone(true);return true;}if(hubUi13PlusRect(0).contains(x,y)){hubStepTimezone(false);return true;}
        if(hubUi13ToggleRect(1).contains(x,y)){netSettings.use24h=!netSettings.use24h;saveSettings();buzzerPlay(BUZZ_CLICK);g_dirty=true;return true;}
        if(hubUi13MinusRect(2).contains(x,y)){netSettings.dateFormat=(uint8_t)((netSettings.dateFormat+5U)%6U);saveSettings();buzzerPlay(BUZZ_CLICK);g_dirty=true;return true;}if(hubUi13PlusRect(2).contains(x,y)){netSettings.dateFormat=(uint8_t)((netSettings.dateFormat+1U)%6U);saveSettings();buzzerPlay(BUZZ_CLICK);g_dirty=true;return true;}
        if(hubUi13BackRect().contains(x,y)||hubUi13ActionRect().contains(x,y)){g_ui12SystemView=0;buzzerPlay(BUZZ_CLICK);g_dirty=true;return true;}return true;
      }
      if(g_ui12SystemView==3||g_ui12SystemView==4){
        if(hubUi13BackRect().contains(x,y)){g_ui12SystemView=0;buzzerPlay(BUZZ_CLICK);g_dirty=true;return true;}
        if(hubUi13ActionRect().contains(x,y)){g_ui12SystemView=1;buzzerPlay(BUZZ_CLICK);g_dirty=true;return true;}return true;
      }
      for(uint8_t i=0;i<4;i++)if(hubUi13SystemCardRect(i).contains(x,y)){
        if(i==0)g_ui12SystemView=4;
        else if(i==1){g_ui12SettingsView=3;setPage(SCREEN_HUB_MORE);}
        else if(i==2)g_ui12SystemView=2;
        else g_ui12SystemView=3;
        buzzerPlay(BUZZ_CLICK);g_dirty=true;return true;
      }
      if(hubUi13BackRect().contains(x,y)){g_ui12SystemView=0;g_ui12SettingsView=0;setPage(SCREEN_HUB_MORE);buzzerPlay(BUZZ_CLICK);g_dirty=true;return true;}
      if(hubUi13ActionRect().contains(x,y)){g_ui12SystemView=1;buzzerPlay(BUZZ_CLICK);g_dirty=true;return true;}
      return true;
    }

    if(!g_audioSettingsView&&!g_networkSettingsView&&g_ui12SystemView==1){
      if(hubUi12SystemBackRect().contains(x,y)){g_ui12SystemView=0;buzzerPlay(BUZZ_CLICK);g_dirty=true;return true;}
      return true;
    }
    if(!g_audioSettingsView&&!g_networkSettingsView&&hubUi12SystemBackRect().contains(x,y)){g_ui12SystemView=0;g_ui12SettingsView=0;setPage(SCREEN_HUB_MORE);buzzerPlay(BUZZ_CLICK);g_dirty=true;return true;}
    if(!g_audioSettingsView&&!g_networkSettingsView&&hubUi12SystemPortalRect().contains(x,y)){g_ui12SystemView=1;buzzerPlay(BUZZ_CLICK);g_dirty=true;return true;}
    if(g_audioSettingsView){
      if(hubSystemSubBackRect().contains(x,y)){g_audioSettingsView=false;g_audioSettingsPage=0;g_dirty=true;buzzerPlay(BUZZ_CLICK);return true;}
      if(hubSystemSubNextRect().contains(x,y)){g_audioSettingsPage=(uint8_t)((g_audioSettingsPage+1U)%7U);g_dirty=true;buzzerPlay(BUZZ_CLICK);return true;}
      for(uint8_t i=0;i<4;i++)if(hubMoreRect(i).contains(x,y)){
        if(g_audioSettingsPage==0){
          if(i==0){buzzerSettings.enabled=!buzzerSettings.enabled;saveBuzzerSettings();initBuzzer();setAudioDiag(buzzerSettings.enabled?"Event sounds enabled":"Event sounds muted",buzzerSettings.enabled?UI_GREEN:UI_DIM);}
          else if(i==1){buzzerSettings.buttonClick=!buzzerSettings.buttonClick;saveBuzzerSettings();setAudioDiag(buzzerSettings.buttonClick?"Button clicks enabled":"Button clicks disabled",buzzerSettings.buttonClick?UI_GREEN:UI_DIM);}
          else if(i==2){buzzerSettings.quietStartHour=hubStepHour(buzzerSettings.quietStartHour,longPress);saveBuzzerSettings();setAudioDiag(buzzerSettings.quietStartHour?"Quiet hours updated":"Quiet hours disabled",UI_PURPLE);}
          else{buzzerSettings.quietEndHour=hubStepHour(buzzerSettings.quietEndHour,longPress);saveBuzzerSettings();setAudioDiag("Quiet end updated",UI_PURPLE);}
        }else if(g_audioSettingsPage==1){
          if(i==0){buzzerSettings.bedCooldownAlert=!buzzerSettings.bedCooldownAlert;saveBuzzerSettings();setAudioDiag(buzzerSettings.bedCooldownAlert?"Bed cooldown alert enabled":"Bed cooldown alert disabled",buzzerSettings.bedCooldownAlert?UI_GREEN:UI_DIM);}
          else if(i==1){buzzerSettings.bedCooldownThresholdC=hubStepCooldownThreshold(buzzerSettings.bedCooldownThresholdC,longPress);saveBuzzerSettings();setAudioDiag("Bed cooldown threshold updated",UI_CYAN);}
          else if(i==2){if(buzzerIsPlaying()){setAudioDiag("Speaker busy • try again",UI_AMBER);}else{setAudioDiag("Speaker chime playing",UI_GREEN);drawAudioSettings(true);buzzerBackendApplyStep(1047);delay(90);buzzerBackendStop();delay(45);buzzerBackendApplyStep(1568);delay(130);buzzerBackendStop();setAudioDiag("Speaker test complete",UI_GREEN);}}
          else{if(buzzerIsPlaying()){setAudioDiag("Wait for current sound",UI_AMBER);}else{setAudioDiag("Listening 1 second • speak now",UI_PURPLE);drawAudioSettings(true);int level=buzzerBackendMicEcho(1000);if(level<0)setAudioDiag("Mic echo unavailable",UI_RED);else if(level<2){char msg[56];snprintf(msg,sizeof(msg),"Mic %d%% • very quiet • try again",level);setAudioDiag(msg,UI_AMBER,level);}else{char msg[56];snprintf(msg,sizeof(msg),"Mic %d%% • playback complete",level);setAudioDiag(msg,UI_GREEN,level);}}}
        }else if(g_audioSettingsPage==2){
          static const uint8_t ledLevels[]={0,64,128,192,255};
          if(i==0){ledSettings.enabled=!ledSettings.enabled;hubPersistLed(ledSettings.enabled?"Status LED enabled":"Status LED disabled",ledSettings.enabled?UI_GREEN:UI_DIM);}
          else if(i==1){ledSettings.brightness=hubStepPreset(ledSettings.brightness,ledLevels,5,longPress);hubPersistLed("LED brightness updated",UI_CYAN);}
          else if(i==2){ledSettings.autoOnWhilePrinting=!ledSettings.autoOnWhilePrinting;hubPersistLed("Print-follow behavior updated",UI_PURPLE);}
          else{ledSettings.pauseBreathing=!ledSettings.pauseBreathing;hubPersistLed("Pause breathing updated",UI_GREEN);}
        }else if(g_audioSettingsPage==3){
          static const uint8_t ledLevels[]={0,64,128,192,255};
          if(i==0){ledSettings.finishMode=(uint8_t)((ledSettings.finishMode+(longPress?2U:1U))%3U);hubPersistLed("Finish effect updated",UI_ORANGE);}
          else if(i==1){ledSettings.finishSeconds=hubStepLedSeconds(ledSettings.finishSeconds,longPress,false);hubPersistLed("Finish duration updated",UI_CYAN);}
          else if(i==2){ledSettings.finishBrightness=hubStepPreset(ledSettings.finishBrightness,ledLevels,5,longPress);hubPersistLed("Finish peak updated",UI_PURPLE);}
          else{setAudioDiag("Advanced setup is in the portal",UI_DIM);}
        }else if(g_audioSettingsPage==4){
          if(i==0){ledSettings.errorStrobe=!ledSettings.errorStrobe;hubPersistLed("Error strobe updated",ledSettings.errorStrobe?UI_RED:UI_DIM);}
          else if(i==1){ledSettings.errorStrobeSeconds=hubStepLedSeconds(ledSettings.errorStrobeSeconds,longPress,true);hubPersistLed("Error duration updated",UI_CYAN);}
          else{setAudioDiag("Advanced setup is in the portal",UI_DIM);}
        }else{
          const uint8_t plug=hubPowerConfigPlug();
          if(plug==0xFF){setAudioDiag("Selected printer has no smart-plug slot",UI_AMBER);}
          else{
            TasmotaSettings& ps=tasmotaSettings[plug];
            if(g_audioSettingsPage==5){
              if(i==0){if(!ps.enabled&&!ps.ip[0])setAudioDiag("Set plug IP in portal before enabling",UI_AMBER);else{ps.enabled=!ps.enabled;hubPersistPower(ps.enabled?"Smart plug enabled":"Smart plug disabled",ps.enabled?UI_GREEN:UI_DIM);}}
              else if(i==1){ps.pollInterval=hubStepPowerPoll(ps.pollInterval,longPress);hubPersistPower("Power poll interval updated",UI_CYAN);}
              else if(i==2){ps.displayMode=(uint8_t)((ps.displayMode+(longPress?2U:1U))%3U);hubPersistPower("Power status display updated",UI_PURPLE);}
              else{dispSettings.buttonPowerControl=!dispSettings.buttonPowerControl;hubPersistPower("Button power-control setting updated",UI_GREEN);}
            }else{
              if(i==0){ps.autoOffEnabled=!ps.autoOffEnabled;hubPersistPower(ps.autoOffEnabled?"Printer auto-off enabled":"Printer auto-off disabled",ps.autoOffEnabled?UI_GREEN:UI_DIM);}
              else if(i==1){ps.autoOffDelayMin=hubStepAutoOffDelay(ps.autoOffDelayMin,longPress);hubPersistPower("Auto-off delay updated",UI_CYAN);}
              else if(i==2){ps.autoOffCancelOnDoor=!ps.autoOffCancelOnDoor;hubPersistPower("Door-cancel setting updated",UI_PURPLE);}
              else{setAudioDiag("Advanced setup is in the portal",UI_DIM);}
            }
          }
        }
        g_dirty=true;return true;
      }
      return true;
    }
    if(g_networkSettingsView){
      if(!g_networkEditLoaded)hubLoadNetworkEdit();
      const uint8_t page=(uint8_t)(g_networkSettingsPage%HUB_NETWORK_PAGE_COUNT);
      if(page<=3){
        if(hubRc2HitRef(x,y,20,82,440,132)){
          if(page==0)netSettings.showIPAtStartup=!netSettings.showIPAtStartup;
          else if(page==1)netSettings.use24h=!netSettings.use24h;
          else if(page==2)netSettings.dateFormat=(uint8_t)((netSettings.dateFormat+1U)%6U);
          else netSettings.mdnsEnabled=!netSettings.mdnsEnabled;
          saveSettings();buzzerPlay(BUZZ_CLICK);g_dirty=true;return true;
        }
        if(hubRc2HitRef(x,y,10,258,110,52)){
          if(page==0){g_networkSettingsView=false;g_networkSettingsPage=0;g_networkEditLoaded=false;}
          else g_networkSettingsPage=(uint8_t)(page-1U);
          buzzerPlay(BUZZ_CLICK);g_dirty=true;return true;
        }
        if(hubRc2HitRef(x,y,360,258,110,52)){g_networkSettingsPage=(uint8_t)(page+1U);buzzerPlay(BUZZ_CLICK);g_dirty=true;return true;}
        return true;
      }
      if(page==4){
        if(hubRc2HitRef(x,y,20,202,210,48)){hubStepTimezone(true);return true;}
        if(hubRc2HitRef(x,y,250,202,210,48)){hubStepTimezone(false);return true;}
        if(hubRc2HitRef(x,y,10,258,110,52)){g_networkSettingsPage=3;buzzerPlay(BUZZ_CLICK);g_dirty=true;return true;}
        if(hubRc2HitRef(x,y,360,258,110,52)){g_networkSettingsPage=5;buzzerPlay(BUZZ_CLICK);g_dirty=true;return true;}
        return true;
      }
      if(page==5){
        if(hubRc2HitRef(x,y,10,102,130,48)){g_networkEditDhcp=!g_networkEditDhcp;buzzerPlay(BUZZ_CLICK);g_dirty=true;return true;}
        if(hubRc2HitRef(x,y,150,102,70,48)){g_networkEditField=(uint8_t)((g_networkEditField+3U)%4U);g_networkEditOctet=0;buzzerPlay(BUZZ_CLICK);g_dirty=true;return true;}
        if(hubRc2HitRef(x,y,400,102,70,48)){g_networkEditField=(uint8_t)((g_networkEditField+1U)%4U);g_networkEditOctet=0;buzzerPlay(BUZZ_CLICK);g_dirty=true;return true;}
        for(uint8_t i=0;i<4;i++)if(hubRc2HitRef(x,y,(int16_t)(10+i*117),156,(i==3)?109:108,48)){g_networkEditOctet=i;buzzerPlay(BUZZ_CLICK);g_dirty=true;return true;}
        int16_t delta=0;
        if(hubRc2HitRef(x,y,10,210,108,48))delta=-10;else if(hubRc2HitRef(x,y,127,210,108,48))delta=-1;else if(hubRc2HitRef(x,y,244,210,108,48))delta=1;else if(hubRc2HitRef(x,y,361,210,109,48))delta=10;
        if(delta){int16_t value=(int16_t)g_networkEditValues[g_networkEditField][g_networkEditOctet]+delta;if(value<0)value=0;if(value>255)value=255;g_networkEditValues[g_networkEditField][g_networkEditOctet]=(uint8_t)value;buzzerPlay(BUZZ_CLICK);g_dirty=true;return true;}
        if(hubRc2HitRef(x,y,10,264,110,48)){g_networkSettingsPage=4;buzzerPlay(BUZZ_CLICK);g_dirty=true;return true;}
        if(hubRc2HitRef(x,y,360,264,110,48)){g_networkSettingsPage=6;buzzerPlay(BUZZ_CLICK);g_dirty=true;return true;}
        return true;
      }
      if(page==6){
        if(hubRc2HitRef(x,y,10,252,105,56)){g_networkSettingsPage=5;buzzerPlay(BUZZ_CLICK);g_dirty=true;return true;}
        if(hubRc2HitRef(x,y,125,252,105,56)){hubNetworkDiscardEdit();g_networkSettingsPage=0;return true;}
        if(hubRc2HitRef(x,y,240,252,230,56)){if(longPress&&hubStaticNetworkValid())hubCommitNetworkAndRestart();else{buzzerPlay(BUZZ_CLICK);g_dirty=true;}return true;}
        return true;
      }
      return true;
    }
    if(hubSystemAudioSettingsEntryRect().contains(x,y)){g_networkSettingsView=false;g_audioSettingsView=true;g_audioSettingsPage=0;g_dirty=true;buzzerPlay(BUZZ_CLICK);return true;}
    if(hubSystemNetworkCardRect().contains(x,y)){g_audioSettingsView=false;g_networkSettingsView=true;g_networkSettingsPage=0;g_networkEditLoaded=false;g_dirty=true;buzzerPlay(BUZZ_CLICK);return true;}
    if(hubSystemActionRect(0).contains(x,y)){
      if(buzzerIsPlaying()){setAudioDiag("Speaker busy • try again",UI_AMBER);return true;}
      setAudioDiag("Speaker chime playing",UI_GREEN);drawSystem(true);
      buzzerBackendApplyStep(1047);delay(90);buzzerBackendStop();delay(45);buzzerBackendApplyStep(1568);delay(130);buzzerBackendStop();
      setAudioDiag("Speaker test complete",UI_GREEN);return true;
    }
    if(hubSystemActionRect(1).contains(x,y)){
      if(buzzerIsPlaying()){setAudioDiag("Wait for current sound",UI_AMBER);return true;}
      setAudioDiag("Listening 1 second • speak now",UI_PURPLE);drawSystem(true);
      int level=buzzerBackendMicEcho(1000);
      if(level<0)setAudioDiag("Mic echo unavailable",UI_RED);
      else if(level<2){char msg[56];snprintf(msg,sizeof(msg),"Mic %d%% • very quiet • try again",level);setAudioDiag(msg,UI_AMBER,level);}
      else{char msg[56];snprintf(msg,sizeof(msg),"Mic %d%% • playback complete",level);setAudioDiag(msg,UI_GREEN,level);}
      return true;
    }
    if(hubSystemActionRect(2).contains(x,y)){
      buzzerSettings.enabled=!buzzerSettings.enabled;
      saveBuzzerSettings();
      initBuzzer();
      setAudioDiag(buzzerSettings.enabled?"Event sounds enabled":"Event sounds muted",
                   buzzerSettings.enabled?UI_GREEN:UI_DIM);
      if(buzzerSettings.enabled) buzzerPlay(BUZZ_CONNECTED);
      return true;
    }
    return true;
  }
  return true;
}


const SmartHubConfig& smartHubGetConfig() {
  return g_cfg;
}

bool smartHubSaveConfig(bool enabled, const char* customUrl,
                        uint16_t refreshSeconds, uint16_t returnSeconds) {
  if (!validUrl(customUrl)) return false;
  g_cfg.enabled = enabled;
  g_cfg.refreshSeconds = clampRefresh(refreshSeconds);
  g_cfg.returnSeconds = clampReturn(returnSeconds);
  safeCopy(g_cfg.customUrl, sizeof(g_cfg.customUrl), customUrl);
  g_lastFetchAttemptMs = 0;
  memset(&g_custom, 0, sizeof(g_custom));
  g_dirty = true;
  bool ok = prefsSave();
  if (!g_cfg.enabled && smartHubIsScreen(getScreenState()))
    smartHubReturnToPrinter();
  return ok;
}

void smartHubReloadExperience() {
  prefsLoad();
  g_dirty = true;
}


bool smartHubStartWorkshopTimer(uint16_t minutes) {
  if (!g_initialized) smartHubInit();
  if (!g_cfg.enabled) return false;
  startWorkshopTimer(minutes);
  return true;
}

void smartHubCancelWorkshopTimer() {
  if (!g_initialized) smartHubInit();
  clearWorkshopTimer();
}

uint32_t smartHubWorkshopTimerRemaining() {
  return workshopTimerRemainingSeconds();
}

bool smartHubWorkshopTimerDone() { return g_workshopTimerDone; }
bool smartHubWorkshopTimerActive() { return workshopTimerActive(); }

const char* smartHubCustomStatus() {
  return g_custom.message[0] ? g_custom.message : "Not fetched";
}

bool smartHubCustomHealthy() {
  return g_custom.healthy;
}

#else

static SmartHubConfig g_cfg = { false, 60, 60, "" };

void smartHubInit() {}
void smartHubService() {}
bool smartHubAvailable() { return false; }
bool smartHubEnabled() { return false; }
bool smartHubIsScreen(ScreenState) { return false; }
bool smartHubIsNativePrinterScreen(ScreenState) { return false; }
bool smartHubHandleTouch(uint16_t, uint16_t, bool) { return false; }
void smartHubUpdateHoldProgress(uint16_t, uint16_t, uint32_t) {}
bool smartHubStartWorkshopTimer(uint16_t) { return false; }
void smartHubCancelWorkshopTimer() {}
uint32_t smartHubWorkshopTimerRemaining() { return 0; }
bool smartHubWorkshopTimerDone() { return false; }
bool smartHubWorkshopTimerActive() { return false; }
bool smartHubShouldYieldToPrinter(bool) { return false; }
void smartHubEnter() {}
void smartHubEnterIdleHome() {}
void smartHubAdvance() {}
void smartHubReturnToPrinter() {}
bool smartHubShowPage(const char*) { return false; }
bool smartHubCapturePrepare(uint16_t*, uint16_t*) { return false; }
bool smartHubCaptureRgbRow(uint16_t, uint8_t*, size_t) { return false; }
void smartHubDraw(ScreenState, bool) {}
const SmartHubConfig& smartHubGetConfig() { return g_cfg; }
bool smartHubSaveConfig(bool, const char*, uint16_t, uint16_t) { return false; }
void smartHubReloadExperience() {}
const char* smartHubCustomStatus() { return "Not available on this board"; }
bool smartHubCustomHealthy() { return false; }

#endif

// BambuHelper smart home navigation evolution v7

// BambuHelper smart home UX evolution v7.1
// BambuHelper display stability evolution v7.2
// Smart Home v8.3 RC2 System display stability fix
// BambuHelper security hardening evolution v8.0

// Smart Home v9.0 visual command-center evolution RC1

// Workshop OS v11.23 RC2 physical touch finalization

// Workshop OS v11.23 RC2 rotation preview declaration-order fix

// Workshop OS v11.23 RC2 calm product visual system

// Workshop OS v11.23 RC2 guarded-action feedback
