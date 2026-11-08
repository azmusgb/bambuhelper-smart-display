#include "web_server.h"
#include "web_template.h"
#include "settings.h"
#include "bambu_state.h"
#include "bambu_mqtt.h"
#include "bambu_cloud.h"
#include "cloud_login.h"
// Gzipped portal assets, generated at build time from web/app.css and
// web/app.js. Included here and nowhere else - the arrays are static.
#include "web_assets_gz.h"
#include "ssdp_discovery.h"
#include "wifi_manager.h"
#include "display_ui.h"
#include "display_edge_glow.h"
#include "config.h"
#include "button.h"
#include "buzzer.h"
#include "buzzer_backend.h"
#include "led.h"
#include "timezones.h"
#include "tasmota.h"
#include "clock_mode.h"
#include "clock_pong.h"
#include "recovery_manager.h"
#include "smart_home_build.h"
#include "hms_lookup.h"
#include "security_manager.h"
#include "smart_hub.h"
#include <WebServer.h>
#include <WiFi.h>
#include <ArduinoJson.h>
#include <Update.h>
#include "esp_ota_ops.h"
#include <mbedtls/sha256.h>
#include <cstring>
#include <Preferences.h>
#ifdef ENABLE_OTA_AUTO
#include <HTTPUpdate.h>
#include <WiFiClientSecure.h>
extern const uint8_t rootca_crt_bundle_start[] asm("_binary_x509_crt_bundle_start");
#endif

// Global WebServer instance. Defined here, referenced from src/web_template.cpp
// via `extern WebServer server;` in include/web_template.h.
WebServer server(80);

// ---------------------------------------------------------------------------
//  Deferred restart — avoids blocking delay() before ESP.restart()
// ---------------------------------------------------------------------------
static unsigned long pendingRestartAt = 0;

static void scheduleRestart(unsigned long delayMs = 1000) {
  pendingRestartAt = millis() + delayMs;
}

// ---------------------------------------------------------------------------
//  PROGMEM page strings (PAGE_HTML, PAGE_AP_HTML) and the template streamer
//  (streamTemplate, resolvePlaceholder) now live in include/web_pages.h and
//  src/web_template.cpp. Route handlers below talk to them through the
//  surface declared in include/web_template.h.
// ---------------------------------------------------------------------------

// ---------------------------------------------------------------------------
//  Helper: read gauge colors from form
// ---------------------------------------------------------------------------
static void readGaugeColorsFromForm(const char* prefix, GaugeColors& gc) {
  char key[8];
  snprintf(key, sizeof(key), "%s_a", prefix);
  if (server.hasArg(key)) gc.arc = htmlToRgb565(server.arg(key).c_str());
  snprintf(key, sizeof(key), "%s_l", prefix);
  if (server.hasArg(key)) gc.label = htmlToRgb565(server.arg(key).c_str());
  snprintf(key, sizeof(key), "%s_v", prefix);
  if (server.hasArg(key)) gc.value = htmlToRgb565(server.arg(key).c_str());
}

// Read one custom gauge label from the form, sanitizing while copying (so an
// overlong raw value can't drop valid chars after truncation).
static void readGaugeLabelFromForm(const char* arg, char* dst, size_t len) {
  if (server.hasArg(arg)) sanitizeGaugeLabel(server.arg(arg).c_str(), dst, len);
}

// ---------------------------------------------------------------------------
//  Read display settings from form args
// ---------------------------------------------------------------------------
static void readDisplayFromForm() {
  if (server.hasArg("bright")) brightness = server.arg("bright").toInt();
  // Night mode
  dpSettings.nightModeEnabled = server.hasArg("nighten");
  if (server.hasArg("nstart")) dpSettings.nightStartHour = server.arg("nstart").toInt();
  if (server.hasArg("nend"))   dpSettings.nightEndHour = server.arg("nend").toInt();
  if (server.hasArg("nbright")) dpSettings.nightBrightness = server.arg("nbright").toInt();
  if (server.hasArg("ssbright")) dpSettings.screensaverBrightness = server.arg("ssbright").toInt();
  // Apply brightness after all brightness-related values are parsed
  setBacklight(getEffectiveBrightness());

  if (server.hasArg("rotation")) {
    uint8_t rot = server.arg("rotation").toInt();
    if (rot <= 3) dispSettings.rotation = rot;
  }
  if (server.hasArg("clr_bg"))    dispSettings.bgColor = htmlToRgb565(server.arg("clr_bg").c_str());
  if (server.hasArg("clr_track")) dispSettings.trackColor = htmlToRgb565(server.arg("clr_track").c_str());
  if (server.hasArg("clr_pbar"))  dispSettings.progressBarColor = htmlToRgb565(server.arg("clr_pbar").c_str());
  if (server.hasArg("clr_eta"))   dispSettings.etaColor = htmlToRgb565(server.arg("clr_eta").c_str());
  if (server.hasArg("clr_fin"))   dispSettings.finishColor = htmlToRgb565(server.arg("clr_fin").c_str());
  if (server.hasArg("clr_stok"))  dispSettings.statusOkColor = htmlToRgb565(server.arg("clr_stok").c_str());
  if (server.hasArg("clr_pname")) dispSettings.printerNameColor = htmlToRgb565(server.arg("clr_pname").c_str());
  if (server.hasArg("clr_txt"))   dispSettings.textColor = htmlToRgb565(server.arg("clr_txt").c_str());
  if (server.hasArg("clr_txtd"))  dispSettings.textDimColor = htmlToRgb565(server.arg("clr_txtd").c_str());
  if (server.hasArg("clr_dorc"))  dispSettings.doorClosedColor = htmlToRgb565(server.arg("clr_dorc").c_str());
  if (server.hasArg("clr_doro"))  dispSettings.doorOpenColor = htmlToRgb565(server.arg("clr_doro").c_str());
  if (server.hasArg("clk_time"))  dispSettings.clockTimeColor = htmlToRgb565(server.arg("clk_time").c_str());
  if (server.hasArg("clk_date"))  dispSettings.clockDateColor = htmlToRgb565(server.arg("clk_date").c_str());
  if (server.hasArg("clk_size")) {
    int s = server.arg("clk_size").toInt();
    if (s >= 0 && s <= 3) dispSettings.clockTimeSize = (uint8_t)s;
  }
  if (server.hasArg("clk_dsize")) {
    int s = server.arg("clk_dsize").toInt();
    if (s >= 0 && s <= 3) dispSettings.clockDateSize = (uint8_t)s;
  }
  dispSettings.hideClockDate = server.hasArg("clk_hidedate");

  readGaugeColorsFromForm("prg", dispSettings.progress);
  readGaugeColorsFromForm("noz", dispSettings.nozzle);
  readGaugeColorsFromForm("bed", dispSettings.bed);
  readGaugeColorsFromForm("pfn", dispSettings.partFan);
  readGaugeColorsFromForm("afn", dispSettings.auxFan);
  readGaugeColorsFromForm("afr", dispSettings.auxFanRight);
  readGaugeColorsFromForm("cfn", dispSettings.chamberFan);
  readGaugeColorsFromForm("exh", dispSettings.exhaustFan);
  readGaugeColorsFromForm("cht", dispSettings.chamberTemp);
  readGaugeColorsFromForm("hbk", dispSettings.heatbreak);
  readGaugeColorsFromForm("pwr", dispSettings.power);
  readGaugeColorsFromForm("lyr", dispSettings.layer);

  // Custom gauge labels (empty = keep built-in default)
  readGaugeLabelFromForm("prg_lbl", gaugeLabels.progress,    sizeof(gaugeLabels.progress));
  readGaugeLabelFromForm("noz_lbl", gaugeLabels.nozzle,      sizeof(gaugeLabels.nozzle));
  readGaugeLabelFromForm("nzr_lbl", gaugeLabels.nozzleRight, sizeof(gaugeLabels.nozzleRight));
  readGaugeLabelFromForm("nzl_lbl", gaugeLabels.nozzleLeft,  sizeof(gaugeLabels.nozzleLeft));
  readGaugeLabelFromForm("bed_lbl", gaugeLabels.bed,         sizeof(gaugeLabels.bed));
  readGaugeLabelFromForm("pfn_lbl", gaugeLabels.partFan,     sizeof(gaugeLabels.partFan));
  readGaugeLabelFromForm("afn_lbl", gaugeLabels.auxFan,      sizeof(gaugeLabels.auxFan));
  readGaugeLabelFromForm("afr_lbl", gaugeLabels.auxFanRight, sizeof(gaugeLabels.auxFanRight));
  readGaugeLabelFromForm("cfn_lbl", gaugeLabels.chamberFan,  sizeof(gaugeLabels.chamberFan));
  readGaugeLabelFromForm("exh_lbl", gaugeLabels.exhaustFan,  sizeof(gaugeLabels.exhaustFan));
  readGaugeLabelFromForm("cht_lbl", gaugeLabels.chamberTemp, sizeof(gaugeLabels.chamberTemp));
  readGaugeLabelFromForm("hbk_lbl", gaugeLabels.heatbreak,   sizeof(gaugeLabels.heatbreak));
  readGaugeLabelFromForm("pwr_lbl", gaugeLabels.power,       sizeof(gaugeLabels.power));
  readGaugeLabelFromForm("lyr_lbl", gaugeLabels.layer,       sizeof(gaugeLabels.layer));
  readGaugeLabelFromForm("clk_lbl", gaugeLabels.clock,       sizeof(gaugeLabels.clock));
  readGaugeLabelFromForm("ams_lbl", gaugeLabels.amsBase,     sizeof(gaugeLabels.amsBase));
  readGaugeLabelFromForm("dor_lbl", gaugeLabels.door,        sizeof(gaugeLabels.door));

  if (server.hasArg("fmins")) {
    dpSettings.finishDisplayMins = server.arg("fmins").toInt();
  }

  // Gauge full-scale ranges (clamp to safe bounds)
  if (server.hasArg("noz_max"))
    dispSettings.nozzleScaleMax  = constrain(server.arg("noz_max").toInt(), GAUGE_NOZZLE_SCALE_MIN, GAUGE_NOZZLE_SCALE_MAX);
  if (server.hasArg("bed_max"))
    dispSettings.bedScaleMax     = constrain(server.arg("bed_max").toInt(), GAUGE_BED_SCALE_MIN, GAUGE_BED_SCALE_MAX);
  if (server.hasArg("cht_max"))
    dispSettings.chamberScaleMax = constrain(server.arg("cht_max").toInt(), GAUGE_CHAMBER_SCALE_MIN, GAUGE_CHAMBER_SCALE_MAX);
  if (server.hasArg("pwr_max"))
    dispSettings.powerScaleW     = constrain(server.arg("pwr_max").toInt(), GAUGE_POWER_SCALE_MIN, GAUGE_POWER_SCALE_MAX);

  // Gauge behavior: smoothing speed + temp warning color
  if (server.hasArg("gsmooth")) {
    int sm = server.arg("gsmooth").toInt();
    dispSettings.gaugeSmoothing = (sm >= 0 && sm <= 3) ? (uint8_t)sm : 2;
  }
  if (server.hasArg("warn_thr"))
    dispSettings.warnThresholdPct = constrain(server.arg("warn_thr").toInt(), 0, 100);
  if (server.hasArg("warn_clr"))
    dispSettings.warnColor = htmlToRgb565(server.arg("warn_clr").c_str());
  dpSettings.keepDisplayOn = server.hasArg("keepon");
  // "Keep finish screen visible" sends no clock arg - preserve the stored
  // clock-vs-off destination instead of silently resetting it to off.
  if (!dpSettings.keepDisplayOn)
    dpSettings.showClockAfterFinish = server.hasArg("clock");
  dpSettings.doorAckEnabled = server.hasArg("dack");
  dpSettings.keepPrintScreen = server.hasArg("kps");
  dpSettings.finishShowTime = server.hasArg("fintm");
  dispSettings.animatedBar = server.hasArg("abar");
  dispSettings.pongClock = server.hasArg("pong");
  dispSettings.smallLabels = server.hasArg("slbl");
  if (server.hasArg("timem")) {
    int tm = server.arg("timem").toInt();
    if (tm >= 0 && tm <= 2) dispSettings.timeDisplayMode = (uint8_t)tm;
  }
  dispSettings.fanMatchPrinter = server.hasArg("fanmp");

  // Edge glow
  if (server.hasArg("glowm")) {
    int gm = server.arg("glowm").toInt();
    if (gm >= 0 && gm <= 2) dispSettings.glowMode = (uint8_t)gm;
    if (dispSettings.glowMode == 0) glowDismiss();  // switched off mid-animation
  }
  if (server.hasArg("glow_clr")) dispSettings.glowColor = htmlToRgb565(server.arg("glow_clr").c_str());
  if (server.hasArg("glows")) {
    int gs = server.arg("glows").toInt();
    if (gs >= 0 && gs <= 2) dispSettings.glowStyle = (uint8_t)gs;
  }
  if (server.hasArg("glowd")) {
    int gd = server.arg("glowd").toInt();
    if (gd >= 0 && gd <= 2) dispSettings.glowDuration = (uint8_t)gd;
  }

  // Printer errors. "hmsauto" is always posted when the section exists, so it
  // doubles as the presence marker: without it the whole block is left alone,
  // which is what a board that never renders the section must do (otherwise the
  // two checkbox reads below would clear settings nobody touched). The four
  // alert checkboxes ride one mask that is always sent, zero included - four
  // unchecked boxes posting nothing would leave stale bits behind.
#if HAS_HMS_WEB_UI
  if (server.hasArg("hmsauto")) {
    int ap = server.arg("hmsauto").toInt();
    if (ap >= 0 && ap <= 2) dispSettings.hmsAutoPresent = (uint8_t)ap;
    dispSettings.hmsEnabled = server.hasArg("hmsen");
    dispSettings.hmsSeverityAll = server.hasArg("hmssev");
    dispSettings.hmsLookupOnline = server.hasArg("hmsonl");
    if (server.hasArg("hmsmask"))
      dispSettings.hmsAlertMask = (uint8_t)(server.arg("hmsmask").toInt() & 0x0F);
  }
#endif

  // Clock settings (timezone, 24h)
  if (server.hasArg("tz")) {
    size_t tzCount;
    const TimezoneRegion* regions = getSupportedTimezones(&tzCount);
    int idx = server.arg("tz").toInt();
    if (idx >= 0 && idx < (int)tzCount) {
      netSettings.timezoneIndex = (uint8_t)idx;
      strlcpy(netSettings.timezoneStr, regions[idx].posixString, sizeof(netSettings.timezoneStr));
    }
  }
  netSettings.use24h = server.hasArg("use24h");
  if (server.hasArg("datefmt")) {
    int df = server.arg("datefmt").toInt();
    if (df >= 0 && df <= 5) netSettings.dateFormat = (uint8_t)df;
  }
}

// ---------------------------------------------------------------------------
//  Route handlers
// ---------------------------------------------------------------------------
static void handleRoot() {
  // Safe Mode is a rescue environment, not first-time Wi-Fi onboarding. Make
  // the recovery console the unavoidable landing page so the owner never has
  // to remember a hidden path while repairing a broken candidate firmware.
  if (isAPMode() && recoverySafeModeActive()) {
    server.sendHeader("Cache-Control", "no-cache, no-store, must-revalidate");
    server.sendHeader("Location", "/recovery");
    server.send(302, "text/plain", "");
    return;
  }
  if (isAPMode()) {
    serveApPage();
  } else {
    serveMainPage();
  }
}

// Save printer settings only (no restart — reinit MQTT)
static void handleSavePrinter() {
  // Free any active SSDP scan sockets before we reinit networking below.
  ssdpStopScan();

  uint8_t slot = 0;
  if (server.hasArg("slot")) slot = server.arg("slot").toInt();
  if (slot >= MAX_ACTIVE_PRINTERS) slot = 0;

#ifdef BOARD_LOW_RAM
  if (slot > 0 && !dualPrinterUnsafe) {
    server.send(200, "application/json",
      "{\"status\":\"error\",\"message\":\"Enable experimental 2-printer mode in Printer Settings to configure printer 2.\"}");
    return;
  }
#endif
#ifdef BOARD_HAS_PSRAM
  if (slot > 1 && !quadPrinterBeta) {
    server.send(200, "application/json",
      "{\"status\":\"error\",\"message\":\"Enable experimental 4-printer mode in Advanced settings to configure printer 3/4.\"}");
    return;
  }
#endif

  PrinterConfig& cfg = printers[slot].config;
  if (server.hasArg("connmode")) {
    String cm = server.arg("connmode");
    if (cm == "cloud_all") cfg.mode = CONN_CLOUD_ALL;
    else cfg.mode = CONN_LOCAL;
  }

  // Cloud region
  if (server.hasArg("region")) {
    String rg = server.arg("region");
    if (rg == "eu") cfg.region = REGION_EU;
    else if (rg == "cn") cfg.region = REGION_CN;
    else cfg.region = REGION_US;
  }

  bool tokenStoreFailed = false;
  if (isCloudMode(cfg.mode)) {
    if (server.hasArg("serial")) strlcpy(cfg.serial, server.arg("serial").c_str(), sizeof(cfg.serial));
    if (server.hasArg("pname")) { strlcpy(cfg.name, server.arg("pname").c_str(), sizeof(cfg.name)); utf8TrimPartial(cfg.name); }
    // Save token if provided
    if (server.hasArg("token") && server.arg("token").length() > 0) {
      tokenStoreFailed = !saveCloudToken(server.arg("token").c_str());
    }
    // Extract userId from stored token
    char tokenBuf[1200];
    if (loadCloudToken(tokenBuf, sizeof(tokenBuf))) {
      if (!cloudExtractUserId(tokenBuf, cfg.cloudUserId, sizeof(cfg.cloudUserId))) {
        cloudFetchUserId(tokenBuf, cfg.cloudUserId, sizeof(cfg.cloudUserId), cfg.region);
      }
    }
  } else {
    if (server.hasArg("pname")) { strlcpy(cfg.name, server.arg("pname").c_str(), sizeof(cfg.name)); utf8TrimPartial(cfg.name); }
    if (server.hasArg("ip"))     strlcpy(cfg.ip, server.arg("ip").c_str(), sizeof(cfg.ip));
    if (server.hasArg("serial")) strlcpy(cfg.serial, server.arg("serial").c_str(), sizeof(cfg.serial));
    if (server.hasArg("code") && server.arg("code").length() > 0) strlcpy(cfg.accessCode, server.arg("code").c_str(), sizeof(cfg.accessCode));
  }

  // Serial numbers must be uppercase (Bambu MQTT topics are case-sensitive)
  for (char* p = cfg.serial; *p; p++) *p = toupper(*p);

  // Validate required fields and build warnings
  String warnings = "";
  if (tokenStoreFailed) {
    // The write itself failed (full or fragmented NVS) - without this line the
    // portal keeps saying "No token set" however often the user pastes, with
    // nothing to explain why.
    uint16_t u, f, t;
    getNvsUsage(u, f, t);
    warnings += "The cloud token could not be stored - settings storage is full (" +
                String(u) + " of " + String(t) +
                " entries used). Export settings, factory-reset, re-import, then paste the token again. ";
  }
  if (isCloudMode(cfg.mode)) {
    if (strlen(cfg.serial) == 0)
      warnings += "Serial number is required for cloud mode. ";
    if (strlen(cfg.cloudUserId) == 0 && !tokenStoreFailed)
      warnings += "Cloud token is missing or invalid (userId extraction failed). ";
  } else {
    if (strlen(cfg.ip) == 0)
      warnings += "Printer IP address is required. ";
    if (strlen(cfg.serial) == 0)
      warnings += "Serial number is required (used for MQTT topic). ";
    if (strlen(cfg.accessCode) == 0)
      warnings += "Access code is required. ";
    else if (strlen(cfg.accessCode) != 8)
      warnings += "Access code should be 8 characters (check printer LCD). ";
  }

  savePrinterConfig(slot);

  // Reinit only the edited slot - the other printer's connection and live
  // display state stay untouched.
  initBambuMqttSlot(slot);

  if (warnings.length() > 0) {
    String resp = "{\"status\":\"ok\",\"warning\":\"" + warnings + "\"}";
    server.send(200, "application/json", resp);
  } else {
    server.send(200, "application/json", "{\"status\":\"ok\"}");
  }
}

// Clear one printer slot back to factory defaults (connection details +
// gauge layout) so a new printer can be configured from scratch. Without
// this there is no way to fully vacate a slot: the access code and token
// fields are password-style and only saved when non-empty.
static void handleClearPrinter() {
  ssdpStopScan();

  uint8_t slot = 0;
  if (server.hasArg("slot")) slot = server.arg("slot").toInt();
  if (slot >= MAX_ACTIVE_PRINTERS) slot = 0;

  clearPrinterConfig(slot);
  initBambuMqttSlot(slot);  // slot now unconfigured -> disconnects + clears state

  if (rotState.displayIndex == slot) {
    rotState.displayIndex = (slot == 0 && isPrinterConfigured(1)) ? 1 : 0;
  }
  // Keep the split second-slot valid and distinct from the deleted slot.
  if (rotState.splitIndexB == slot || rotState.splitIndexB >= MAX_ACTIVE_PRINTERS) {
    rotState.splitIndexB = (rotState.displayIndex == 0) ? 1 : 0;
  }

  server.send(200, "application/json", "{\"status\":\"ok\"}");
}

// Save gauge layout only (no MQTT reinit needed)
static void handleSaveGaugeLayout() {
  uint8_t slot = 0;
  if (server.hasArg("slot")) slot = server.arg("slot").toInt();
  if (slot >= MAX_ACTIVE_PRINTERS) slot = 0;

#ifdef BOARD_LOW_RAM
  if (slot > 0 && !dualPrinterUnsafe) {
    server.send(200, "application/json",
      "{\"status\":\"error\",\"message\":\"Enable experimental 2-printer mode to configure printer 2.\"}");
    return;
  }
#endif
#ifdef BOARD_HAS_PSRAM
  if (slot > 1 && !quadPrinterBeta) {
    server.send(200, "application/json",
      "{\"status\":\"error\",\"message\":\"Enable experimental 4-printer mode to configure printer 3/4.\"}");
    return;
  }
#endif

  PrinterConfig& cfg = printers[slot].config;
  auto readSlotArg = [&](const char* prefix, uint8_t idx, uint8_t& out) {
    char argName[8];
    snprintf(argName, sizeof(argName), "%s%d", prefix, idx);
    if (server.hasArg(argName)) {
      uint8_t val = server.arg(argName).toInt();
      out = (val < GAUGE_TYPE_COUNT) ? val : GAUGE_EMPTY;
    }
  };
  for (uint8_t g = 0; g < GAUGE_SLOT_COUNT;       g++) readSlotArg("gs", g, cfg.gaugeSlots[g]);
  for (uint8_t g = 0; g < LANDSCAPE_EXTRA_COUNT;  g++) readSlotArg("lx", g, cfg.landscapeExtras[g]);
  for (uint8_t g = 0; g < PORTRAIT_EXTRA_COUNT;   g++) readSlotArg("px", g, cfg.portraitExtras[g]);
  for (uint8_t g = 0; g < IDLE_SLOT_COUNT;        g++) {
    readSlotArg("is", g, cfg.idleSlots[g]);
    // The Ready / Print Complete screens redraw only on change, while the
    // camera tile paints on its own cadence and camera_client only streams for
    // a type parked in gaugeSlots - it would sit there as a stale frame.
    if (cfg.idleSlots[g] == GAUGE_CAMERA) cfg.idleSlots[g] = GAUGE_EMPTY;
  }
  cfg.amsView = server.hasArg("amsv");

  savePrinterConfig(slot);
  server.send(200, "application/json", "{\"status\":\"ok\"}");
}

// Save WiFi + network settings (requires restart)
static void handleSaveWifi() {
  if (server.hasArg("ssid")) strlcpy(wifiSSID, server.arg("ssid").c_str(), sizeof(wifiSSID));
  if (server.hasArg("pass") && server.arg("pass").length() > 0) strlcpy(wifiPass, server.arg("pass").c_str(), sizeof(wifiPass));

  netSettings.useDHCP = (!server.hasArg("netmode") || server.arg("netmode") == "dhcp");
  if (server.hasArg("net_ip"))  strlcpy(netSettings.staticIP, server.arg("net_ip").c_str(), sizeof(netSettings.staticIP));
  if (server.hasArg("net_gw"))  strlcpy(netSettings.gateway, server.arg("net_gw").c_str(), sizeof(netSettings.gateway));
  if (server.hasArg("net_sn"))  strlcpy(netSettings.subnet, server.arg("net_sn").c_str(), sizeof(netSettings.subnet));
  if (server.hasArg("net_dns")) strlcpy(netSettings.dns, server.arg("net_dns").c_str(), sizeof(netSettings.dns));
  if (server.hasArg("has_showip"))  // full page sends this; AP page doesn't
    netSettings.showIPAtStartup = server.hasArg("showip");

  if (server.hasArg("has_mdns")) {
    netSettings.mdnsEnabled = server.hasArg("mdns_en");
    // Don't trust the client - sanitize server-side too.
    if (server.hasArg("mdns_host"))
      sanitizeHostname(server.arg("mdns_host").c_str(), netSettings.hostname,
                       sizeof(netSettings.hostname));
  }

  saveSettings();

  server.send(200, "application/json", "{\"status\":\"ok\"}");
  scheduleRestart();
}

// Live brightness preview (no save, just PWM update)
// Only applies when the main display is active — during clock/screensaver
// the screensaverBrightness governs the backlight, not the main slider.
static void handleBrightnessPreview() {
  if (server.hasArg("val")) {
    uint8_t val = server.arg("val").toInt();
    ScreenState scr = getScreenState();
    if (scr != SCREEN_CLOCK && scr != SCREEN_OFF) {
      setBacklight(val);
    }
  }
  server.send(200, "text/plain", "OK");
}

// Apply display settings live (no restart)
static void handleApply() {
  // Snapshot timezone before parsing — only re-init NTP if it changes.
  // configTzTime() resets the SNTP sync status, which causes getLocalTime()
  // to return false for up to 60s, blanking the clock screen unnecessarily.
  char prevTz[sizeof(netSettings.timezoneStr)];
  strlcpy(prevTz, netSettings.timezoneStr, sizeof(prevTz));
  readDisplayFromForm();
  saveSettings();
  applyDisplaySettings();
  if (strcmp(netSettings.timezoneStr, prevTz) != 0) {
    configTzTime(netSettings.timezoneStr, "pool.ntp.org", "time.nist.gov");
  }
  server.send(200, "text/plain", "OK");
}

static void handleStatus() {
  uint8_t slot = 0;
  if (server.hasArg("slot")) slot = server.arg("slot").toInt();
  // Bound by the config array, not by MAX_ACTIVE_PRINTERS: the two differ on a
  // low-RAM board, which still keeps MAX_PRINTERS NVS slots but only runs two
  // MQTT connections. Clamping to 0 made /status?slot=2 there answer about slot
  // 0, and the portal's error card - which polls 0..3 blind, having no way to
  // see a board-specific limit - listed the same printer three times.
  if (slot >= MAX_PRINTERS) slot = 0;

  BambuState& st = printers[slot].state;

  JsonDocument doc;
  // Per-printer (driven by ?slot=)
  doc["connected"] = st.connected;
  doc["configured"] = isPrinterConfigured(slot);
  doc["state"] = st.gcodeState;
  // "Connected but no data": broker accepted us but zero messages have arrived
  // 20s after connecting. Means a wrong serial (topic never matches) or the
  // printer is powered off - both look identical from the broker's side.
  {
    const MqttDiag& d = getMqttDiag(slot);
    doc["no_data"] = st.connected && d.messagesRx == 0 && d.connectTime > 0 &&
                     (millis() - d.connectTime) > 20000;
  }
  doc["progress"] = st.progress;
  doc["nozzle"] = (int)st.nozzleTemp;
  doc["nozzle_t"] = (int)st.nozzleTarget;
  doc["bed"] = (int)st.bedTemp;
  doc["bed_t"] = (int)st.bedTarget;
  doc["fan"] = st.coolingFanPct;
  doc["chamber"] = (int)st.chamberTemp;
  doc["remaining"] = st.remainingMinutes;
  doc["layer"] = st.layerNum;
  doc["layers"] = st.totalLayers;

  JsonObject ams = doc["ams"].to<JsonObject>();
  ams["present"] = st.ams.present;
  ams["units"] = st.ams.unitCount;
  ams["activeTray"] = st.ams.activeTray;
  ams["externalPresent"] = st.ams.vtPresent;
  if (st.ams.vtPresent) {
    ams["externalType"] = st.ams.vtType;
    char c[8]; rgb565ToHtml(st.ams.vtColorRgb565, c); ams["externalColor"] = c;
  }
  JsonArray trays = ams["trays"].to<JsonArray>();
  for (uint8_t i = 0; i < AMS_MAX_TRAYS; ++i) {
    const AmsTray& tr = st.ams.trays[i];
    if (!tr.present) continue;
    JsonObject jt = trays.add<JsonObject>();
    jt["slot"] = i; jt["type"] = tr.type; jt["remain"] = tr.remain;
    jt["active"] = (st.ams.activeTray == i);
    char c[8]; rgb565ToHtml(tr.colorRgb565, c); jt["color"] = c;
  }
  doc["display_off"] = (getScreenState() == SCREEN_OFF);
  doc["name"] = printers[slot].config.name;
  doc["lightState"] = st.lightState;  // -1 unknown / 0 off / 1 on (chamber light)
  doc["cali"] = isCalibrationPrint(st);  // current/last job is a calibration print (issue #149)
#if HAS_HMS_UI
  // Printer errors. Emitted only when there is something to report, so the 3 s
  // poll stays small on a healthy printer. The portal card consumes these -
  // keep the names stable.
  //
  // Baseline membership rides each entry rather than a second array: it is the
  // same information in fewer bytes, and the card wants it per row anyway.
  if (dispSettings.hmsEnabled && (st.printError != 0 || st.hmsCount > 0)) {
    char codeBuf[HMS_CODE_FULL_STR_LEN];
    if (st.printError != 0) {
      printErrorFormatCode(st.printError, codeBuf, sizeof(codeBuf));
      doc["printError"] = codeBuf;
      const char* peText = printErrorLookupText(st.printError);
      if (peText) doc["printErrorText"] = peText;
      // The card says "Canceled", not "error", for a stop the user asked for.
      if (printErrorIsCancel(st.printError)) doc["printErrorCancel"] = true;
    }
    if (st.hmsCount > 0) {
      JsonArray arr = doc["hms"].to<JsonArray>();
      for (uint8_t i = 0; i < st.hmsCount; i++) {
        JsonObject e = arr.add<JsonObject>();
        // Bambu's own full notation - this is the string a user copies into a
        // search box, and "0500_0100_0002_000B" matched nothing (issue #164).
        hmsFormatCodeFull(st.hms[i].attr, st.hms[i].code, codeBuf, sizeof(codeBuf));
        e["code"] = codeBuf;
        e["sev"] = hmsSeverityOf(st.hms[i].code);
        e["module"] = hmsModuleLabel(st.hms[i].attr);
        if (hmsIsBaseline(st, st.hms[i].attr, st.hms[i].code)) e["baseline"] = true;
        // Only on boards carrying the table. Elsewhere the card falls back to
        // the published mirror, which the browser can reach and we cannot.
        const char* text = hmsLookupText(st.hms[i].attr, st.hms[i].code);
        if (text) e["text"] = text;
      }
      if (st.hmsOverflow) doc["hmsOverflow"] = (uint8_t)(st.hmsTotal - st.hmsCount);
    }
    const ErrorBadge badge = errorBadgeFor(st);
    if (badge.active) doc["errSev"] = badge.severity;
  }
#endif

  // Device-wide (new design's Detected Hardware + WiFi live KV)
  doc["heap_kb"] = ESP.getFreeHeap() / 1024;
  doc["uptime"] = (uint32_t)(millis() / 1000);
  doc["rssi"] = WiFi.RSSI();
  doc["ip"] = WiFi.localIP().toString();
  doc["mac"] = WiFi.macAddress();
  doc["flash_kb"] = ESP.getFlashChipSize() / 1024;
#if defined(BOARD_HAS_PSRAM) || defined(CONFIG_SPIRAM_SUPPORT)
  doc["psram_kb"] = ESP.getPsramSize() / 1024;
#else
  doc["psram_kb"] = 0;
#endif
  JsonObject hw = doc["hardware"].to<JsonObject>();
#if defined(BOARD_HAS_ES8311_AUDIO)
  hw["audio"] = "ES8311";
#endif
#if defined(BOARD_HAS_MICROPHONE)
  hw["microphone"] = true;
#endif
#if defined(BOARD_HAS_BLE5)
  hw["bluetooth"] = "BLE 5 LE";
#endif
#if defined(BOARD_HAS_AXP2101_HW)
  hw["pmic"] = "AXP2101";
#endif
#if defined(BOARD_HAS_PCF85063_HW)
  hw["rtc"] = "PCF85063";
#endif
#if defined(BOARD_HAS_QMI8658_HW)
  hw["imu"] = "QMI8658";
#endif
#if defined(BOARD_HAS_TF_HW)
  hw["tfHardware"] = true;
#endif

  String json;
  serializeJson(doc, json);
  server.send(200, "application/json", json);
}

// Clean reboot (preserves NVS). Wired to the Danger Zone "Reboot" button.
// Distinct from /reset which wipes settings via resetSettings().
static void handleReboot() {
  server.send(200, "application/json", "{\"status\":\"ok\"}");
  scheduleRestart(1000);
}

static void handleTimezones() {
  size_t tzCount;
  const TimezoneRegion* regions = getSupportedTimezones(&tzCount);
  // Stream JSON directly to avoid building large String
  server.setContentLength(CONTENT_LENGTH_UNKNOWN);
  server.send(200, "application/json", "");
  server.sendContent("{\"selected\":");
  server.sendContent(String((int)netSettings.timezoneIndex));
  server.sendContent(",\"zones\":[");
  for (size_t i = 0; i < tzCount; i++) {
    if (i > 0) server.sendContent(",");
    // JSON-escape the label into a stack buffer (defensive - current labels are clean)
    char esc[80];
    size_t j = 0;
    esc[j++] = '"';
    for (const char* p = regions[i].name; *p && j < sizeof(esc) - 2; p++) {
      if (*p == '"' || *p == '\\') esc[j++] = '\\';
      esc[j++] = *p;
    }
    esc[j++] = '"';
    esc[j] = '\0';
    server.sendContent(esc);
  }
  server.sendContent("]}");
  server.sendContent("");  // terminate chunked response
}

static void handleReset() {
  server.send(200, "text/html",
    "<html><body style='background:#0D1117;color:#E6EDF3;text-align:center;padding-top:80px;font-family:sans-serif'>"
    "<h2 style='color:#F85149'>Factory Reset</h2>"
    "<p>Restarting...</p></body></html>");
  resetSettings();  // clears NVS and calls ESP.restart()
}

static void handleDebug() {
  JsonDocument doc;
  unsigned long now = millis();

  JsonArray arr = doc["printers"].to<JsonArray>();
  for (uint8_t i = 0; i < MAX_ACTIVE_PRINTERS; i++) {
    if (!isPrinterConfigured(i)) continue;
    const MqttDiag& d = getMqttDiag(i);
    BambuState& st = printers[i].state;
    JsonObject p = arr.add<JsonObject>();
    p["slot"] = i;
    p["name"] = printers[i].config.name;
    p["connected"] = st.connected;
    p["attempts"] = d.attempts;
    p["messages"] = d.messagesRx;
    p["last_rc"] = d.lastRc;
    p["rc_text"] = mqttRcToString(d.lastRc);
    if (isCloudMode(printers[i].config.mode) &&
        (d.lastRc == 4 || d.lastRc == 5)) {
      p["rc_hint"] = "Token expired or invalidated (90-day TTL, or 'log out everywhere'/password change). Paste a fresh token in Setup.";
    }
    p["tcp_ok"] = d.tcpOk;
    p["pushall_total"] = d.pushallTotal;
    p["rec_print"] = d.recoveryPrint;
    p["rec_conn_dead"] = d.recoveryConnDead;
    p["rec_finish"] = d.recoveryFinish;
    p["rec_idle"] = d.recoveryIdle;
    p["rec_idle_hot"] = d.recoveryIdleHot;
    p["rec_finish_hot"] = d.recoveryFinishHot;
    p["rec_failed"] = d.recoveryFailed;
    p["last_pushall_reason"] = pushallReasonToString(d.lastPushallReason);
    p["last_pushall_age_s"] = d.lastPushallMs > 0 ? (now - d.lastPushallMs) / 1000UL : 0;
    p["last_update_age_s"] = st.lastUpdate > 0 ? (now - st.lastUpdate) / 1000UL : 0;
    p["last_print_data_age_s"] = st.lastPrintDataMs > 0 ? (now - st.lastPrintDataMs) / 1000UL : 0;
#if HAS_HMS_UI
    // Printer errors. The portal card and /status get their own shaped fields
    // later; this is the raw diagnostic view.
    char codeBuf[HMS_CODE_FULL_STR_LEN];
    if (st.printError != 0) {
      printErrorFormatCode(st.printError, codeBuf, sizeof(codeBuf));
      p["print_error"] = codeBuf;
      const char* peText = printErrorLookupText(st.printError);
      if (peText) p["print_error_text"] = peText;
    }
    if (st.hmsCount > 0) {
      JsonArray hmsArr = p["hms"].to<JsonArray>();
      for (uint8_t k = 0; k < st.hmsCount; k++) {
        JsonObject e = hmsArr.add<JsonObject>();
        hmsFormatCodeFull(st.hms[k].attr, st.hms[k].code, codeBuf, sizeof(codeBuf));
        e["code"] = codeBuf;
        e["sev"] = hmsSeverityOf(st.hms[k].code);
        e["module"] = hmsModuleLabel(st.hms[k].attr);
        e["baseline"] = hmsIsBaseline(st, st.hms[k].attr, st.hms[k].code);
        const char* text = hmsLookupText(st.hms[k].attr, st.hms[k].code);
        if (text) e["text"] = text;
      }
      p["hms_total"] = st.hmsTotal;
      p["hms_overflow"] = st.hmsOverflow;
      p["hms_worst_sev"] = st.hmsWorstSeverity;
    }
    // Emitted outside the hmsCount guard on purpose: a report where every code
    // was undescribed leaves hms[] empty, and that is precisely the case someone
    // asks about ("the printer shows a code, BambuHelper shows none"). The codes
    // themselves ride along, not just the count - a diagnostic dump is the only
    // way to answer that question without a USB cable, so it has to name them.
    p["hms_suppressed"] = st.hmsSuppressed;
    if (st.hmsSuppressed > 0) {
      JsonArray sup = p["hms_suppressed_codes"].to<JsonArray>();
      const uint8_t n = st.hmsSuppressed < HMS_SUPPRESSED_MAX
                          ? st.hmsSuppressed : HMS_SUPPRESSED_MAX;
      for (uint8_t k = 0; k < n; k++) {
        hmsFormatCodeFull(st.hmsSuppressedCodes[k].attr,
                          st.hmsSuppressedCodes[k].code, codeBuf, sizeof(codeBuf));
        sup.add(codeBuf);
      }
    }
    p["hms_baseline_n"] = st.hmsBaselineCount;
    if (st.hmsBaselineSaturated) p["hms_baseline_saturated"] = true;
    // What the on-screen badge resolves to, so a "why is nothing showing"
    // report can be answered without a panel in front of you.
    {
      const ErrorBadge eb = errorBadgeFor(st);
      p["badge_active"] = eb.active;
      if (eb.active) p["badge_sev"] = eb.severity;
      if (printerWasCanceled(st)) p["canceled"] = true;
    }
#endif
  }

  doc["heap"] = ESP.getFreeHeap();
  doc["uptime"] = millis() / 1000;
  doc["rssi"] = WiFi.RSSI();
  doc["debug_log"] = mqttDebugLog;
  {
    // Settings-storage pressure. free_entries overcounts (erased-but-not-yet-
    // collected entries ride along), so used/total is the number a support
    // thread should quote.
    uint16_t u, f, t;
    getNvsUsage(u, f, t);
    doc["nvs_used"]  = u;
    doc["nvs_free"]  = f;
    doc["nvs_total"] = t;
  }
#if HAS_HMS_UI
  {
    const char* tv = hmsTableVersion();
    doc["hms_table_ver"] = tv ? tv : "none";
    // The key set behind the suppression rule. Present even where hms_table_ver
    // is "none", which is the whole point of it being a separate field.
    const char* kv = hmsKnownVersion();
    doc["hms_known_ver"] = kv ? kv : "none";
  }
#endif

  String json;
  serializeJson(doc, json);
  server.send(200, "application/json", json);
}

static void handleDebugToggle() {
  if (server.hasArg("on")) {
    mqttDebugLog = (server.arg("on") == "1");
  }
  server.send(200, "text/plain", mqttDebugLog ? "ON" : "OFF");
}

static void handleToggleSetting() {
  if (!server.hasArg("key") || !server.hasArg("val")) {
    server.send(400, "text/plain", "Missing key/val");
    return;
  }
  String key = server.arg("key");
  bool on = (server.arg("val") == "1");

  if      (key == "keepon")  dpSettings.keepDisplayOn = on;
  else if (key == "clock")   dpSettings.showClockAfterFinish = on;
  else if (key == "dack")    dpSettings.doorAckEnabled = on;
  else if (key == "kps")     dpSettings.keepPrintScreen = on;
  else if (key == "fintm")   dpSettings.finishShowTime = on;
  else if (key == "abar")    dispSettings.animatedBar = on;
  else if (key == "pong")    dispSettings.pongClock = on;
  else if (key == "slbl")    dispSettings.smallLabels = on;
  else if (key == "timem")   dispSettings.timeDisplayMode = (uint8_t)constrain(server.arg("val").toInt(), 0, 2);
  else if (key == "fanmp")   dispSettings.fanMatchPrinter = on;
  else if (key == "hidelp")  dispSettings.hideStatusReadout = on;
  else if (key == "invcol")  dispSettings.invertColors = on;
  else if (key == "cydcls")  dispSettings.cydPanelClassic = on;
  else if (key == "cyd32e")  dispSettings.cyd32eVariant = on;
  else if (key == "rskin")   dispSettings.roundSkin = (uint8_t)constrain(server.arg("val").toInt(), 0, 2);
  else if (key == "l8s")     dispSettings.landscape8Slots = on;
  else if (key == "p9s")     dispSettings.portrait9Slots = on;
  else if (key == "clkinfo") dispSettings.showClockInfo = on;
  else if (key == "amst")    dispSettings.amsTrayTypes = on;
  else if (key == "btnpwr")  dispSettings.buttonPowerControl = on;
  else if (key == "glowm") {
    dispSettings.glowMode = (uint8_t)constrain(server.arg("val").toInt(), 0, 2);
    if (dispSettings.glowMode == 0) glowDismiss();  // switched off mid-animation
  }
  else if (key == "glows")   dispSettings.glowStyle = (uint8_t)constrain(server.arg("val").toInt(), 0, 2);
  else if (key == "glowd")   dispSettings.glowDuration = (uint8_t)constrain(server.arg("val").toInt(), 0, 2);
#if HAS_HMS_WEB_UI
  else if (key == "hmsen")   dispSettings.hmsEnabled = on;
  else if (key == "hmssev")  dispSettings.hmsSeverityAll = on;
  else if (key == "hmsauto") dispSettings.hmsAutoPresent = (uint8_t)constrain(server.arg("val").toInt(), 0, 2);
  else if (key == "hmsmask") dispSettings.hmsAlertMask = (uint8_t)(constrain(server.arg("val").toInt(), 0, 15));
  // Browser-side only - the device never fetches the list, so nothing on the
  // panel has to be repainted for this one.
  else if (key == "hmsonl")  dispSettings.hmsLookupOnline = on;
#endif
  else if (key == "nighten") dpSettings.nightModeEnabled = on;
  else if (key == "use24h")  netSettings.use24h = on;
  else if (key == "rotsplit")  rotState.splitEnabled = on;
  else if (key == "rotsplitf") rotState.splitForce = on;
  else if (key == "clkhd")     dispSettings.hideClockDate = on;
  else if (key == "showip")    netSettings.showIPAtStartup = on;
#ifdef BOARD_LOW_RAM
  else if (key == "dualp")   dualPrinterUnsafe = on;
#endif
#ifdef BOARD_HAS_PSRAM
  else if (key == "quadp")   quadPrinterBeta = on;
#endif
  else {
    server.send(400, "text/plain", "Unknown key");
    return;
  }

  saveSettings();
  // "fintm" joins these because it rewrites text already on screen: the finish
  // headline is painted only under forceRedraw, so without a re-render the
  // toggle would appear to do nothing until the next print.
  // "hmsen" / "hmssev" join these because they change what the state badge
  // says without any printer state moving, and every badge site is cached.
  if (key == "invcol" || key == "slbl" || key == "abar" || key == "timem" ||
      key == "fintm" || key == "hmsen" || key == "hmssev") applyDisplaySettings();
  if (key == "cydcls") scheduleRestart(800);  // panel swap needs a fresh init
  if (key == "cyd32e") scheduleRestart(800);  // re-init amp enable + RGB pins cleanly
  if (key == "rskin") triggerDisplayTransition();  // repaint print dashboard with the new skin
  if (key == "use24h") { resetClock(); resetPongClock(); triggerDisplayTransition(); }
  if (key == "clkinfo") { resetClock(); triggerDisplayTransition(); }
  if (key == "clkhd") { resetClock(); triggerDisplayTransition(); }
  if (key == "hidelp") triggerDisplayTransition();  // repaint status bar with/without readout
  if (key == "rotsplit" || key == "rotsplitf") triggerDisplayTransition();  // flip split layout live
  if (key == "amst") triggerDisplayTransition();  // force AMS-zone repaint
#ifdef BOARD_LOW_RAM
  if (key == "dualp") {
    if (!on && rotState.displayIndex == 1) {
      // User just disabled 2-printer mode - drop slot 1 from rotation/display
      rotState.displayIndex = 0;
    }
    if (!on && rotState.splitIndexB == 1) rotState.splitIndexB = 0;
    // Re-evaluate slot 1 active state without reboot; slot 0 stays connected.
    initBambuMqttSlot(1);
  }
#endif
#ifdef BOARD_HAS_PSRAM
  if (key == "quadp") {
    if (!on) {
      // User just disabled 4-printer beta - drop slots 2/3 from rotation/display
      if (rotState.displayIndex > 1) rotState.displayIndex = 0;
      if (rotState.splitIndexB > 1) rotState.splitIndexB = 0;
    }
    // Re-evaluate slots 2/3 without reboot; slots 0/1 stay connected.
    initBambuMqttSlot(2);
    initBambuMqttSlot(3);
  }
#endif
  if (key == "kps") {
    BambuState& st = printers[rotState.displayIndex].state;
    ScreenState cur = getScreenState();
    if (on && !st.printing && !st.ams.anyDrying &&
        (cur == SCREEN_IDLE || cur == SCREEN_FINISHED)) {
      setScreenState(SCREEN_PRINTING);
    } else if (!on && cur == SCREEN_PRINTING && !st.printing) {
      setScreenState(st.gcodeStateId == GCODE_FINISH
                     ? SCREEN_FINISHED : SCREEN_IDLE);
    }
  }
  server.send(200, "text/plain", "OK");
}

// ---------------------------------------------------------------------------
//  Static portal assets
//
//  Served straight from PROGMEM, still gzipped - the browser inflates them. The
//  URLs carry a hash of the file's own bytes, so `immutable` is safe: any change
//  to the asset changes its URL and the cached copy is simply never asked for
//  again.
// ---------------------------------------------------------------------------
const char* webAssetCssVersion() { return WEB_APP_CSS_VER; }
const char* webAssetJsVersion()  { return WEB_APP_JS_VER; }

static void sendGzipAsset(const char* contentType, const uint8_t* data, size_t len) {
  server.sendHeader("Content-Encoding", "gzip");
  server.sendHeader("Cache-Control", "public, max-age=31536000, immutable");
  server.send_P(200, contentType, (PGM_P)data, len);
}

static void handleAppCss() { sendGzipAsset("text/css", WEB_APP_CSS_GZ, WEB_APP_CSS_GZ_LEN); }
static void handleAppJs()  { sendGzipAsset("application/javascript", WEB_APP_JS_GZ, WEB_APP_JS_GZ_LEN); }

static void handleCloudLogout() {
  clearCloudToken();
  // NVS is only half of it: the sign-in module still holds the live site
  // session cookie, the 2FA challenge and a state that answers "Signed in."
  // until the next reboot.
  cloudLoginReset();
  server.send(200, "text/plain", "OK");
}

// List the printers bound to the stored token's account, so the portal can
// offer a picker instead of a serial the user has to transcribe. Available with
// a pasted token too, not only after an on-device sign-in.
static void handleCloudPrinters() {
  char token[1200];
  if (!loadCloudToken(token, sizeof(token))) {
    server.send(200, "application/json",
                "{\"printers\":[],\"message\":\"Sign in or paste a token first.\"}");
    return;
  }

  CloudRegion region = printers[0].config.region;
  if (server.hasArg("region")) {
    String r = server.arg("region");
    region = (r == "cn") ? REGION_CN : (r == "eu" ? REGION_EU : REGION_US);
  }

  String response;
  if (!cloudFetchDeviceList(token, region, response)) {
    server.send(200, "application/json",
                "{\"printers\":[],\"message\":\"Bambu refused the request - the token may have expired.\"}");
    return;
  }

  // The bind payload carries far more per device than the picker needs, and a
  // busy account can make it big, so only the four fields are parsed out.
  JsonDocument filter;
  filter["devices"][0]["dev_id"] = true;
  filter["devices"][0]["name"] = true;
  filter["devices"][0]["dev_product_name"] = true;
  filter["devices"][0]["dev_model_name"] = true;
  filter["devices"][0]["online"] = true;

  JsonDocument doc;
  if (deserializeJson(doc, response, DeserializationOption::Filter(filter))) {
    server.send(200, "application/json",
                "{\"printers\":[],\"message\":\"Could not read the account's printer list.\"}");
    return;
  }

  JsonDocument out;
  JsonArray arr = out["printers"].to<JsonArray>();
  for (JsonObject dev : doc["devices"].as<JsonArray>()) {
    const char* serial = dev["dev_id"];
    if (!serial || strlen(serial) == 0) continue;
    JsonObject p = arr.add<JsonObject>();
    p["serial"] = serial;
    p["name"]   = dev["name"].is<const char*>() ? (const char*)dev["name"] : serial;
    const char* model = dev["dev_product_name"].is<const char*>()
                          ? (const char*)dev["dev_product_name"]
                          : (const char*)dev["dev_model_name"];
    p["model"]  = model ? model : "";
    p["online"] = dev["online"].as<bool>();
  }

  String body;
  serializeJson(out, body);
  server.send(200, "application/json", body);
}

#if HAS_CLOUD_LOGIN

// Signing in mints a fresh token, so every cloud slot needs its userId derived
// again - it is part of the MQTT topic.
static void refreshCloudUserIds() {
  char tokenBuf[1200];
  if (!loadCloudToken(tokenBuf, sizeof(tokenBuf))) return;

  for (uint8_t i = 0; i < MAX_PRINTERS; i++) {
    PrinterConfig& cfg = printers[i].config;
    if (!isCloudMode(cfg.mode)) continue;
    if (!cloudExtractUserId(tokenBuf, cfg.cloudUserId, sizeof(cfg.cloudUserId))) {
      cloudFetchUserId(tokenBuf, cfg.cloudUserId, sizeof(cfg.cloudUserId), cfg.region);
    }
  }
  saveSettings();
}

static const char* cloudLoginStateName() {
  switch (cloudLoginState()) {
    case CLOUD_LOGIN_NEED_TFA:        return "need_tfa";
    case CLOUD_LOGIN_NEED_EMAIL_CODE: return "need_email_code";
    case CLOUD_LOGIN_OK:              return "ok";
    case CLOUD_LOGIN_FAILED:          return "failed";
    default:                          return "idle";
  }
}

static void sendCloudLoginState() {
  JsonDocument doc;
  doc["state"]   = cloudLoginStateName();
  doc["message"] = cloudLoginMessage();
  doc["failed"]  = cloudLoginLastFailed();

  char email[96];
  doc["email"] = loadCloudEmail(email, sizeof(email)) ? email : "";
  doc["saved_password"] = cloudLoginCanAutoRefresh();

  char token[1200];
  doc["has_token"] = loadCloudToken(token, sizeof(token));

  String out;
  serializeJson(doc, out);
  server.send(200, "application/json", out);
}

// Step 1. `mode=code` mails a code and never sees a password; `mode=password`
// posts the password once. It is only persisted when the caller asked for it
// AND the account signed in without a second factor - a stored password is
// useless for silent refresh otherwise.
static void sendCloudLoginError(const char* message) {
  JsonDocument doc;
  doc["state"]   = "failed";
  doc["failed"]  = true;
  doc["message"] = message;
  String out;
  serializeJson(doc, out);
  server.send(200, "application/json", out);
}

static void handleCloudLoginStart() {
  String email = server.arg("email");
  email.trim();
  if (email.length() == 0) {
    sendCloudLoginError("Enter your Bambu account email.");
    return;
  }
  // Both credentials are read back out of fixed buffers. Storing something
  // longer would truncate on load and then fail every silent renewal for good,
  // reported as a wrong password rather than as the length problem it is.
  if (email.length() > CLOUD_EMAIL_MAX) {
    sendCloudLoginError("That email address is too long for this device to store.");
    return;
  }

  // Smart Home v8.3: this local portal never accepts a Bambu account
  // password. Email-code sign-in gives us a short-lived verification secret
  // instead of transmitting a long-lived password over plain LAN HTTP.
  if (server.arg("mode") != "code") {
    sendCloudLoginError("Smart Home requires email-code sign-in; Bambu account passwords are not accepted by this portal.");
    return;
  }
  cloudLoginRequestEmailCode(email.c_str());
  sendCloudLoginState();
  return;
String password = server.arg("password");
  if (password.length() == 0) {
    sendCloudLoginError("Enter your password.");
    return;
  }

  const bool save = (server.arg("save") == "1");
  if (save && password.length() > CLOUD_PASSWORD_MAX) {
    sendCloudLoginError("That password is too long for this device to remember. "
                        "Sign in without saving it, or use an emailed code.");
    return;
  }

  cloudLoginWithPassword(email.c_str(), password.c_str());

  if (cloudLoginState() == CLOUD_LOGIN_OK) {
    // Not saving means not keeping: without this, signing into a second account
    // leaves the first account's password behind, now paired with the new
    // email, and the renewal path posts that mismatched pair every 15 minutes.
    if (save) saveCloudPassword(password.c_str());
    else      clearCloudPassword();
    refreshCloudUserIds();
  }
  sendCloudLoginState();
}

// Step 2: the authenticator code or the emailed one, whichever is pending.
static void handleCloudLoginCode() {
  String code = server.arg("code");
  code.trim();
  if (code.length() == 0) {
    sendCloudLoginState();
    return;
  }

  cloudLoginSubmitCode(code.c_str());
  if (cloudLoginState() == CLOUD_LOGIN_OK) refreshCloudUserIds();
  sendCloudLoginState();
}

static void handleCloudLoginStatus() {
  sendCloudLoginState();
}

// Reachability check for support: proves whether this device can talk to the
// Bambu sign-in service, using throwaway credentials only.
static void handleCloudSelfTest() {
  String result;
  cloudLoginSelfTest(result);
  Serial.print("CLOUD selftest: ");
  Serial.println(result);
  server.send(200, "application/json", result);
}

#endif // HAS_CLOUD_LOGIN

// "Test" button next to the edge-glow settings: preview the configured effect
// for ~5 s on whatever screen is up. Accepts the picker's current color so the
// preview matches even before the user hits Save (applied live, not persisted).
static void handleGlowTest() {
  if (server.hasArg("clr")) dispSettings.glowColor = htmlToRgb565(server.arg("clr").c_str());
  glowStartTest(rotState.displayIndex);
  server.send(200, "text/plain", "OK");
}

// Discover Bambu printers on the local network via SSDP so the user can pick the
// exact serial (and IP) instead of typing it. POST starts a scan, GET polls.
static void handleLanScan() {
  if (server.method() == HTTP_POST) {
    int opened = ssdpStartScan();
    if (opened == 0) {
      server.send(200, "application/json",
                  "{\"status\":\"error\",\"msg\":\"Cannot scan: not on a Wi-Fi network, "
                  "or the network blocks multicast.\"}");
      return;
    }
    server.send(200, "application/json", "{\"status\":\"scanning\"}");
    return;
  }

  // GET: report progress + whatever has been discovered so far.
  String devices;
  ssdpScanResultJson(devices);
  String json = "{\"status\":\"";
  json += ssdpScanActive() ? "scanning" : "done";
  json += "\",\"devices\":";
  json += devices;
  json += "}";
  server.send(200, "application/json", json);
}

// Explicit credential reveal. This route is registered through SECURE_GET below,
// so normal portal session authentication applies. Keep the access code out of
// /status, /printer/config, diagnostics and page source.
static void handlePrinterAccessCode() {
  uint8_t slot = 0;
  if (server.hasArg("slot")) slot = server.arg("slot").toInt();
  if (slot >= MAX_ACTIVE_PRINTERS) {
    server.send(400, "application/json", "{\"status\":\"error\",\"message\":\"Invalid printer slot\"}");
    return;
  }
  const PrinterConfig& cfg = printers[slot].config;
  if (cfg.mode != CONN_LOCAL || !cfg.accessCode[0]) {
    server.sendHeader("Cache-Control", "no-store");
    server.send(404, "application/json", "{\"status\":\"error\",\"message\":\"No LAN access code is configured for this printer\"}");
    return;
  }
  JsonDocument doc;
  doc["status"] = "ok";
  doc["slot"] = slot;
  doc["accessCode"] = cfg.accessCode;
  String json;
  serializeJson(doc, json);
  server.sendHeader("Cache-Control", "no-store");
  server.sendHeader("Pragma", "no-cache");
  server.send(200, "application/json", json);
}

// Get printer config for a specific slot (multi-printer tabs)
static void handlePrinterConfig() {
  uint8_t slot = 0;
  if (server.hasArg("slot")) slot = server.arg("slot").toInt();
  if (slot >= MAX_ACTIVE_PRINTERS) slot = 0;

  PrinterConfig& cfg = printers[slot].config;
  BambuState& st = printers[slot].state;

  JsonDocument doc;
  doc["mode"] = isCloudMode(cfg.mode) ? "cloud_all" : "local";
  doc["name"] = cfg.name;
  doc["ip"] = cfg.ip;
  doc["serial"] = cfg.serial;
  doc["hasAccessCode"] = cfg.accessCode[0] != '\0';
  doc["configStorage"] = "NVS / OTA-preserved";
  doc["region"] = cfg.region == REGION_EU ? "eu" : (cfg.region == REGION_CN ? "cn" : "us");
  doc["connected"] = st.connected;
  doc["configured"] = isPrinterConfigured(slot);
  // Per-fan capability flags derived from device.airduct.parts[] (only the
  // funcs actually reported by this printer). H2C reports func 0/1/2/4, X2D
  // reports 0/2/5/6 — so the UI gates each gauge on its specific bit instead
  // of a coarse "has airduct" boolean (which would falsely enable Aux-Right on H2C).
  doc["hasAuxFanRight"] = (st.airductFuncs & (1u << 6)) != 0;  // X2D only
  doc["hasExhaustFan"]  = (st.airductFuncs & (1u << 2)) != 0;  // X2D + H2C
  doc["hasDualNozzle"]  = st.dualNozzle;                       // H2D/H2C/X2D per-nozzle temp gauges
  doc["hasTasmota"]     = tasmotaConfiguredForSlot(slot);      // gates the Power gauge option
#if BOARD_HAS_CAMERA
  // Camera gauge: only LAN-mode P1/A1 with an access code serve the port-6000
  // chamber image. (P1S=01P, P1P=01S, A1=039, A1mini=030.)
  {
    const char* cs = cfg.serial;
    bool p1a1 = strlen(cs) >= 3 &&
                (strncmp(cs, "01P", 3) == 0 || strncmp(cs, "01S", 3) == 0 ||
                 strncmp(cs, "039", 3) == 0 || strncmp(cs, "030", 3) == 0);
    doc["hasLanCamera"] = (cfg.mode == CONN_LOCAL) && cfg.accessCode[0] && p1a1;
  }
#else
  doc["hasLanCamera"] = false;
#endif
  JsonArray slots = doc["gaugeSlots"].to<JsonArray>();
  for (uint8_t g = 0; g < GAUGE_SLOT_COUNT; g++) slots.add(cfg.gaugeSlots[g]);
  JsonArray lext = doc["landscapeExtras"].to<JsonArray>();
  for (uint8_t g = 0; g < LANDSCAPE_EXTRA_COUNT; g++) lext.add(cfg.landscapeExtras[g]);
  JsonArray pext = doc["portraitExtras"].to<JsonArray>();
  for (uint8_t g = 0; g < PORTRAIT_EXTRA_COUNT;  g++) pext.add(cfg.portraitExtras[g]);
  JsonArray islot = doc["idleSlots"].to<JsonArray>();
  for (uint8_t g = 0; g < IDLE_SLOT_COUNT;       g++) islot.add(cfg.idleSlots[g]);
  doc["amsView"] = cfg.amsView;
  doc["lightFlags"] = cfg.lightFlags;       // chamber-light automation bitmask
  doc["lightDelay"] = cfg.lightOffDelayMin; // off delay (minutes)
  doc["lightState"] = st.lightState;        // -1 unknown / 0 off / 1 on

  String json;
  serializeJson(doc, json);
  server.send(200, "application/json", json);
}

// Save chamber-light automation settings (no MQTT reinit - mirrors gauge layout)
static void handleLightConfig() {
  uint8_t slot = 0;
  if (server.hasArg("slot")) slot = server.arg("slot").toInt();
  if (slot >= MAX_ACTIVE_PRINTERS) slot = 0;

  PrinterConfig& cfg = printers[slot].config;
  uint8_t flags = 0;
  if (server.hasArg("loff_fin"))  flags |= LIGHT_OFF_ON_FINISH;
  if (server.hasArg("loff_fail")) flags |= LIGHT_OFF_ON_FAILED;
  if (server.hasArg("lon_start")) flags |= LIGHT_ON_AT_START;
  cfg.lightFlags = flags;
  if (server.hasArg("ldelay"))
    cfg.lightOffDelayMin = constrain(server.arg("ldelay").toInt(), 0, 60);

  // If both off-rules are now disabled, cancel any pending off timer so a stale
  // deadline scheduled under the old rules doesn't still turn the light off later.
  if (!(flags & (LIGHT_OFF_ON_FINISH | LIGHT_OFF_ON_FAILED)))
    printers[slot].state.lightOffDueMs = 0;

  savePrinterConfig(slot);
  server.send(200, "application/json", "{\"status\":\"ok\"}");
}

// Turn chamber light on/off now from the web UI
static void handleLightSet() {
  uint8_t slot = 0;
  if (server.hasArg("slot")) slot = server.arg("slot").toInt();
  if (slot >= MAX_ACTIVE_PRINTERS) slot = 0;
  if (!isPrinterConfigured(slot)) {
    server.send(409, "application/json", "{\"status\":\"error\",\"message\":\"printer not configured\"}");
    return;
  }
  if (!printers[slot].state.connected) {
    server.send(409, "application/json", "{\"status\":\"error\",\"message\":\"printer offline\"}");
    return;
  }
  String mode = server.hasArg("mode") ? server.arg("mode") : String();
  if (mode != "on" && mode != "off") {
    server.send(400, "application/json", "{\"status\":\"error\",\"message\":\"mode must be on or off\"}");
    return;
  }
  requestLightCommand(slot, mode == "on");
  server.send(200, "application/json", "{\"status\":\"ok\"}");
}

// Everyday printer remote control. STOP requires an explicit confirmation
// token even after authentication so a stray browser/touch request cannot
// cancel a print. State-specific validity is enforced here as well as in UI.
static void handlePrinterControl() {
  uint8_t slot = server.hasArg("slot") ? server.arg("slot").toInt() : 0;
  if (slot >= MAX_ACTIVE_PRINTERS) slot = 0;
  if (!isPrinterConfigured(slot)) { server.send(409,"application/json","{\"status\":\"error\",\"message\":\"printer not configured\"}"); return; }
  BambuState& st=printers[slot].state;
  if (!st.connected) { server.send(409,"application/json","{\"status\":\"error\",\"message\":\"printer offline\"}"); return; }
  const String command=server.hasArg("command")?server.arg("command"):String();
  const bool paused=(st.gcodeStateId==GCODE_PAUSE);
  const bool active=st.printing||paused;
  PrinterControlCommand code=PRINTER_CTRL_NONE;
  if(command=="pause"&&active&&!paused)code=PRINTER_CTRL_PAUSE;
  else if(command=="resume"&&paused)code=PRINTER_CTRL_RESUME;
  else if(command=="stop"&&active){
    if(!server.hasArg("confirm")||server.arg("confirm")!="STOP"){server.send(400,"application/json","{\"status\":\"error\",\"message\":\"stop confirmation required\"}");return;}
    code=PRINTER_CTRL_STOP;
  } else { server.send(409,"application/json","{\"status\":\"error\",\"message\":\"command not valid for current printer state\"}"); return; }
  if(!requestPrinterControlCommand(slot,code)){server.send(409,"application/json","{\"status\":\"error\",\"message\":\"command not queued\"}");return;}
  server.send(202,"application/json","{\"status\":\"queued\"}");
}

static void handlePrinterPowerStatus() {
  uint8_t slot=server.hasArg("slot")?server.arg("slot").toInt():0;
  if(slot>=MAX_ACTIVE_PRINTERS)slot=0;
  JsonDocument doc;doc["slot"]=slot;
  uint8_t plug=tasmotaControlPlugForSlot(slot);
  const bool available=(plug!=0xFF&&tasmotaSettings[plug].enabled);
  doc["available"]=available;
  if(available){TasmotaPlugStatsView v;tasmotaGetStats(plug,&v);doc["plug"]=plug;doc["online"]=v.online;doc["stateKnown"]=v.powerStateKnown;doc["on"]=v.powerStateKnown?v.powerOn:(v.online&&v.watts>0.5f);doc["watts"]=v.watts;}
  String json;serializeJson(doc,json);server.send(200,"application/json",json);
}

static void handlePrinterPower() {
  uint8_t slot=server.hasArg("slot")?server.arg("slot").toInt():0;
  if(slot>=MAX_ACTIVE_PRINTERS)slot=0;
  if(!isPrinterConfigured(slot)){server.send(409,"application/json","{\"status\":\"error\",\"message\":\"printer not configured\"}");return;}
  uint8_t plug=tasmotaControlPlugForSlot(slot);
  if(plug==0xFF||!tasmotaSettings[plug].enabled){server.send(409,"application/json","{\"status\":\"error\",\"message\":\"no power plug mapped to printer\"}");return;}
  if(!server.hasArg("on")){server.send(400,"application/json","{\"status\":\"error\",\"message\":\"missing on parameter\"}");return;}
  const bool on=server.arg("on").toInt()!=0;
  const bool printing=isPrintingGcodeState(printers[slot].state.gcodeStateId);
  if(!on){
    const String token=server.hasArg("confirm")?server.arg("confirm"):String();
    const char* required=printing?"POWER OFF DURING PRINT":"POWER OFF";
    if(token!=required){server.send(400,"application/json",printing?"{\"status\":\"error\",\"message\":\"printing: stronger power-off confirmation required\"}":"{\"status\":\"error\",\"message\":\"power-off confirmation required\"}");return;}
  }
  if(tasmotaSetPower(plug,on))server.send(200,"application/json","{\"status\":\"ok\"}");
  else server.send(502,"application/json","{\"status\":\"error\",\"message\":\"power plug did not respond\"}");
}

// Test buzzer from web UI
static void handleBuzzerTest() {
  uint8_t snd = 0;
  if (server.hasArg("sound")) snd = server.arg("sound").toInt();
  if (snd <= 2) buzzerPlay((BuzzerEvent)snd);
  else if (snd == 4) buzzerPlay(BUZZ_BED_COOLDOWN);
  server.send(200, "application/json", "{\"status\":\"ok\"}");
}

static void handleAudioMicTest() {
#if defined(BOARD_HAS_MICROPHONE)
  int level = buzzerBackendMicLevel(350);
  if (level < 0) {
    server.send(503, "application/json", "{\"status\":\"error\",\"message\":\"microphone unavailable\"}");
    return;
  }
  JsonDocument doc;
  doc["status"] = "ok";
  doc["level"] = level;
  doc["kind"] = "activity";
  String json;
  serializeJson(doc, json);
  server.send(200, "application/json", json);
#else
  server.send(404, "application/json", "{\"status\":\"error\",\"message\":\"microphone not present\"}");
#endif
}


static void handleAudioMicEcho() {
#if defined(BOARD_HAS_MICROPHONE)
  if (buzzerIsPlaying()) {
    server.send(409, "application/json", "{\"status\":\"error\",\"message\":\"speaker busy\"}");
    return;
  }
  int level = buzzerBackendMicEcho(1000);
  if (level < 0) {
    server.send(503, "application/json", "{\"status\":\"error\",\"message\":\"microphone echo unavailable\"}");
    return;
  }
  JsonDocument doc;
  doc["status"] = "ok";
  doc["level"] = level;
  doc["kind"] = "echo";
  String json;
  serializeJson(doc, json);
  server.send(200, "application/json", json);
#else
  server.send(404, "application/json", "{\"status\":\"error\",\"message\":\"microphone not present\"}");
#endif
}

// Parse an "#rrggbb" or "rrggbb" form value into 0xRRGGBB, falling back to the
// saved value when the argument is missing or malformed.
static uint32_t ledColorArg(const char *arg, uint32_t fallback) {
  if (!server.hasArg(arg)) return fallback;
  String s = server.arg(arg);
  if (s.startsWith("#")) s.remove(0, 1);
  if (s.length() != 6) return fallback;
  for (uint8_t i = 0; i < 6; i++) if (!isHexadecimalDigit(s[i])) return fallback;
  return (uint32_t)strtoul(s.c_str(), NULL, 16) & 0xFFFFFF;
}

// Live LED preview from web UI. Validates pin range as int before casting to
// uint8_t (avoids 300 -> 44 wraparound). On invalid pin we shut the preview
// off so the user doesn't see a "ghost" LED still lit on the previous pin.
static void handleLedPreview() {
  bool en = server.hasArg("en") ? (server.arg("en") == "1") : ledSettings.enabled;

  uint8_t drv = ledSettings.driver;
  if (server.hasArg("drv")) {
    int v = server.arg("drv").toInt();
    if (v >= 0 && v <= LED_DRV_PIXEL) drv = (uint8_t)v;
  }

  // Red / green / blue pins. Green and blue only matter for LED_DRV_RGB, but
  // they are range-checked unconditionally so a stray value can never reach
  // previewLed() as a wrapped uint8_t.
  int rawPin = server.hasArg("pin") ? server.arg("pin").toInt() : ledSettings.pin;
  int rawG   = server.hasArg("ping") ? server.arg("ping").toInt() : ledSettings.pinG;
  int rawB   = server.hasArg("pinb") ? server.arg("pinb").toInt() : ledSettings.pinB;
  const bool rgb = (drv == LED_DRV_RGB);
  if (rawPin < 1 || rawPin > 48 ||
      (rgb && (rawG < 1 || rawG > 48 || rawB < 1 || rawB > 48))) {
    previewLed(false, LED_DRV_SINGLE, 0, 0, 0, false, 0, 0);
    server.send(400, "application/json", "{\"error\":\"pin out of range\"}");
    return;
  }

  uint8_t br = ledSettings.brightness;
  if (server.hasArg("br")) {
    int v = server.arg("br").toInt();
    if (v < 0) v = 0; if (v > 255) v = 255;
    br = (uint8_t)v;
  }

  const bool anode = server.hasArg("anode") ? (server.arg("anode") == "1")
                                            : ledSettings.commonAnode;
  const uint32_t col = ledColorArg("col", ledSettings.colorIdle);

  previewLed(en, drv, (uint8_t)rawPin, (uint8_t)rawG, (uint8_t)rawB, anode, br, col);
  server.send(200, "application/json", "{\"status\":\"ok\"}");
}

// Trigger the chosen finish effect for a short window without waiting for a
// real print finish. Reads md/sec/br as overrides; falls back to ledSettings.
// Doesn't gate on ledSettings.enabled - a previewed-but-unsaved config also
// has the pin attached and should be testable. ledTriggerTestEffect() reports
// whether it actually started so we can return a meaningful error.
static void handleLedTest() {
  uint8_t md = ledSettings.finishMode;
  if (server.hasArg("md")) {
    int v = server.arg("md").toInt();
    if (v >= 0 && v <= 2) md = (uint8_t)v;
  }
  if (md == LED_FINISH_OFF) {
    server.send(409, "application/json", "{\"status\":\"err\",\"error\":\"mode off\"}");
    return;
  }

  uint16_t sec = LED_TEST_DURATION_S;
  if (server.hasArg("sec")) {
    int v = server.arg("sec").toInt();
    if (v < 5) v = 5; if (v > 600) v = 600;
    // For the test we cap to a sane preview window so the user isn't stuck
    // waiting 10 minutes if they configured a long real-finish duration.
    if (v > 30) v = LED_TEST_DURATION_S;
    sec = (uint16_t)v;
  }

  uint8_t br = ledSettings.finishBrightness;
  if (server.hasArg("br")) {
    int v = server.arg("br").toInt();
    if (v < 0) v = 0; if (v > 255) v = 255;
    br = (uint8_t)v;
  }

  if (!ledTriggerTestEffect(md, sec, br, ledColorArg("col", ledSettings.colorFinished))) {
    server.send(409, "application/json", "{\"status\":\"err\",\"error\":\"LED not attached - enable it first\"}");
    return;
  }
  server.send(200, "application/json", "{\"status\":\"ok\"}");
}

// Save rotation settings (multi-printer)
static void handleSaveRotation() {
  if (server.hasArg("rotmode")) {
    uint8_t mode = server.arg("rotmode").toInt();
    if (mode <= 2) rotState.mode = (RotateMode)mode;
  }
  if (server.hasArg("rotinterval")) {
    uint32_t sec = server.arg("rotinterval").toInt();
    uint32_t ms = sec * 1000;
    if (ms < ROTATE_MIN_MS) ms = ROTATE_MIN_MS;
    if (ms > ROTATE_MAX_MS) ms = ROTATE_MAX_MS;
    rotState.intervalMs = ms;
  }
  if (server.hasArg("rotsplit")) {
    rotState.splitEnabled = (server.arg("rotsplit") == "1");
  }
  if (server.hasArg("rotsplitf")) {
    rotState.splitForce = (server.arg("rotsplitf") == "1");
  }
  saveRotationSettings();

  // Button settings
#if defined(BOARD_IS_WS350)
  // Integrated touch is a hardware requirement on this build. Do not permit a
  // portal save to persist BTN_DISABLED and recreate the lockout state.
  buttonType = BTN_TOUCHSCREEN;
#else
  if (server.hasArg("btntype")) {
    uint8_t bt = server.arg("btntype").toInt();
    if (bt <= 3) buttonType = (ButtonType)bt;
  }
#endif
  if (server.hasArg("btnpin")) {
    uint8_t bp = server.arg("btnpin").toInt();
    if (bp > 0 && bp <= 48) buttonPin = bp;
  }
  saveButtonSettings();
  initButton();

  // Buzzer settings
  if (server.hasArg("buzzen")) {
    buzzerSettings.enabled = (server.arg("buzzen") == "1");
  }
  if (server.hasArg("buzpin")) {
    uint8_t bp = server.arg("buzpin").toInt();
    if (bp > 0 && bp <= 48) buzzerSettings.pin = bp;
  }
  if (server.hasArg("buzqs")) {
    int qs = server.arg("buzqs").toInt();
    if (qs >= 0 && qs <= 23) buzzerSettings.quietStartHour = qs;
  }
  if (server.hasArg("buzqe")) {
    int qe = server.arg("buzqe").toInt();
    if (qe >= 0 && qe <= 23) buzzerSettings.quietEndHour = qe;
  }
  if (server.hasArg("buzclick")) {
    buzzerSettings.buttonClick = (server.arg("buzclick") == "1");
  }
  if (server.hasArg("buzbeden")) {
    buzzerSettings.bedCooldownAlert = (server.arg("buzbeden") == "1");
  }
  if (server.hasArg("buzbedtemp")) {
    int t = server.arg("buzbedtemp").toInt();
    if (t < 20) t = 20;
    if (t > 80) t = 80;
    buzzerSettings.bedCooldownThresholdC = (uint8_t)t;
  }
  saveBuzzerSettings();
  initBuzzer();

  // Battery indicator visibility (Waveshare boards). Always parse so the
  // form's unchecked state reaches NVS (browsers omit unchecked checkboxes;
  // saveRotation() JS sends an explicit 0/1 to work around that).
  if (server.hasArg("batshow")) {
    dispSettings.showBatteryIndicator = (server.arg("batshow") == "1");
    saveBatteryIndicatorSetting();
  }

  // Status LED — must be parsed AFTER button + buzzer so sanitizeLedPin()
  // sees the freshly-applied buttonPin and buzzerSettings.pin when checking
  // for conflicts.
  if (server.hasArg("leden"))  ledSettings.enabled = (server.arg("leden") == "1");
  if (server.hasArg("leddrv")) {
    int v = server.arg("leddrv").toInt();
    if (v >= 0 && v <= LED_DRV_PIXEL) ledSettings.driver = (uint8_t)v;
  }
  if (server.hasArg("ledpin")) {
    int lp = server.arg("ledpin").toInt();
    if (lp > 0 && lp <= 48) ledSettings.pin = (uint8_t)lp;
  }
  if (server.hasArg("ledping")) {
    int lp = server.arg("ledping").toInt();
    if (lp > 0 && lp <= 48) ledSettings.pinG = (uint8_t)lp;
  }
  if (server.hasArg("ledpinb")) {
    int lp = server.arg("ledpinb").toInt();
    if (lp > 0 && lp <= 48) ledSettings.pinB = (uint8_t)lp;
  }
  if (server.hasArg("ledanode")) ledSettings.commonAnode = (server.arg("ledanode") == "1");
  ledSettings.colorIdle     = ledColorArg("ledcidl", ledSettings.colorIdle);
  ledSettings.colorPrinting = ledColorArg("ledcprn", ledSettings.colorPrinting);
  ledSettings.colorPaused   = ledColorArg("ledcpau", ledSettings.colorPaused);
  ledSettings.colorFinished = ledColorArg("ledcfin", ledSettings.colorFinished);
  ledSettings.colorError    = ledColorArg("ledcerr", ledSettings.colorError);
  if (server.hasArg("ledbr")) {
    int br = server.arg("ledbr").toInt();
    if (br < 0) br = 0; if (br > 255) br = 255;
    ledSettings.brightness = (uint8_t)br;
  }
  if (server.hasArg("ledfxmd")) {
    int v = server.arg("ledfxmd").toInt();
    if (v >= 0 && v <= 2) ledSettings.finishMode = (uint8_t)v;
  }
  if (server.hasArg("ledfxsec")) {
    int v = server.arg("ledfxsec").toInt();
    if (v < 5) v = 5; if (v > 600) v = 600;
    ledSettings.finishSeconds = (uint16_t)v;
  }
  if (server.hasArg("ledfxbr")) {
    int v = server.arg("ledfxbr").toInt();
    if (v < 0) v = 0; if (v > 255) v = 255;
    ledSettings.finishBrightness = (uint8_t)v;
  }
  // Checkboxes: present + value "1" = enabled. Form posts "0" when unchecked
  // (saveRotation JS sends both states explicitly).
  if (server.hasArg("ledauto"))  ledSettings.autoOnWhilePrinting = (server.arg("ledauto")  == "1");
  if (server.hasArg("ledpause")) ledSettings.pauseBreathing      = (server.arg("ledpause") == "1");
  if (server.hasArg("lederr"))   ledSettings.errorStrobe         = (server.arg("lederr")   == "1");
  if (server.hasArg("lederrsec")) {
    int v = server.arg("lederrsec").toInt();
    if (v != 0 && v < 5) v = 5; if (v > 600) v = 600;
    ledSettings.errorStrobeSeconds = (uint16_t)v;
  }
  saveLedSettings();
  initLed();

  server.send(200, "application/json", "{\"status\":\"ok\"}");
}

// ---------------------------------------------------------------------------
//  Tasmota power monitoring — config + stats + save
// ---------------------------------------------------------------------------
static void handleGetPowerConfig() {
  int plug = server.hasArg("plug") ? server.arg("plug").toInt() : 0;
  if (plug < 0 || plug >= TASMOTA_PLUG_COUNT) {
    server.send(400, "application/json", "{\"status\":\"error\"}");
    return;
  }
  TasmotaSettings& s = tasmotaSettings[plug];
  JsonDocument doc;
  doc["enabled"]         = s.enabled;
  doc["plugType"]        = s.plugType;            // 0=Tasmota, 1=Shelly Gen2/3, 2=Kasa legacy, 3=Shelly Power Strip Gen4
  doc["plugOutlet"]      = s.plugOutlet;          // plugType 3 only: which outlet (0-3)
  doc["ip"]              = s.ip;
  doc["displayMode"]     = s.displayMode;
  doc["pollInterval"]    = s.pollInterval;
  doc["autoOffEnabled"]      = s.autoOffEnabled;
  doc["autoOffDelayMin"]     = s.autoOffDelayMin;
  doc["autoOffCancelOnDoor"] = s.autoOffCancelOnDoor;
  doc["tariff"]              = tasmotaTariffPerKwh;   // global
  doc["currency"]        = tasmotaCurrency;       // global
#if TASMOTA_PLUG_COUNT == 1
  doc["assignedSlot"]    = s.assignedSlot;
#endif
  String json;
  serializeJson(doc, json);
  server.send(200, "application/json", json);
}

static void handleGetPowerStats() {
  JsonDocument doc;
  JsonArray arr = doc.to<JsonArray>();
  for (uint8_t i = 0; i < TASMOTA_PLUG_COUNT; i++) {
    TasmotaPlugStatsView v;
    tasmotaGetStats(i, &v);
    JsonObject o = arr.add<JsonObject>();
    o["online"]     = v.online;
    o["watts"]      = v.watts;
    o["today"]      = v.todayKwh;
    o["total"]      = v.totalKwh;
    o["thisPrint"]  = v.printUsedKwh;
    o["plugType"]   = tasmotaSettings[i].plugType;  // JS hides Today row when unavailable
    o["stateKnown"] = v.powerStateKnown;            // true => use real on/off below
    o["on"]         = v.powerOn;
  }
  String json;
  serializeJson(doc, json);
  server.send(200, "application/json", json);
}

static void handleSavePower() {
  // Currency and tariff are global - update if present regardless of plug index
  if (server.hasArg("tsm_cur")) {
    strlcpy(tasmotaCurrency, server.arg("tsm_cur").c_str(), sizeof(tasmotaCurrency));
    utf8TrimPartial(tasmotaCurrency);  // 8B buffer can slice a multi-byte symbol
  }
  if (server.hasArg("tsm_tar")) {
    float t = server.arg("tsm_tar").toFloat();
    if (t < 0.0f) t = 0.0f;
    if (t > 10.0f) t = 10.0f;
    tasmotaTariffPerKwh = t;
  }

  int plug = server.hasArg("plug") ? server.arg("plug").toInt() : 0;
  if (plug < 0 || plug >= TASMOTA_PLUG_COUNT) {
    server.send(400, "application/json", "{\"status\":\"error\",\"message\":\"Invalid plug index\"}");
    return;
  }
  TasmotaSettings& s = tasmotaSettings[plug];

  // Checkboxes are always submitted as 0/1 from the JS; treat "absent" as no change
  if (server.hasArg("tsm_en"))  s.enabled = (server.arg("tsm_en").toInt() != 0);
  if (server.hasArg("tsm_pt")) {
    int pt = server.arg("tsm_pt").toInt();
    s.plugType = (pt >= 0 && pt <= 3) ? (uint8_t)pt : 0;
  }
  if (server.hasArg("tsm_po")) {
    int po = server.arg("tsm_po").toInt();
    s.plugOutlet = (po >= 0 && po <= 3) ? (uint8_t)po : 0;
  }
  if (server.hasArg("tsm_ip"))  strlcpy(s.ip, server.arg("tsm_ip").c_str(), sizeof(s.ip));
  if (server.hasArg("tsm_dm")) {
    int dm = server.arg("tsm_dm").toInt();
    s.displayMode = (dm >= 0 && dm <= 2) ? (uint8_t)dm : 0;  // 0=alt 1=watts 2=layer
  }
  if (server.hasArg("tsm_pi")) {
    int pi = server.arg("tsm_pi").toInt();
    s.pollInterval = (pi >= 10 && pi <= 60) ? (uint8_t)pi : 10;
  }
  if (server.hasArg("tsm_ao"))  s.autoOffEnabled = (server.arg("tsm_ao").toInt() != 0);
  if (server.hasArg("tsm_ad")) {
    int ad = server.arg("tsm_ad").toInt();
    s.autoOffDelayMin = (ad >= 1 && ad <= 240) ? (uint8_t)ad : 10;
  }
  if (server.hasArg("tsm_aod")) s.autoOffCancelOnDoor = (server.arg("tsm_aod").toInt() != 0);
#if TASMOTA_PLUG_COUNT == 1
  if (server.hasArg("tsm_slot")) {
    int slot = server.arg("tsm_slot").toInt();
    s.assignedSlot = (slot >= 0 && slot < MAX_ACTIVE_PRINTERS) ? (uint8_t)slot : 255;
  }
#endif

  saveSettings();
  tasmotaInit();
  server.send(200, "application/json", "{\"status\":\"ok\"}");
}

static void handlePowerControl() {
  int plug = server.hasArg("plug") ? server.arg("plug").toInt() : 0;
  if (plug < 0 || plug >= TASMOTA_PLUG_COUNT || !tasmotaSettings[plug].enabled) {
    server.send(400, "application/json", "{\"status\":\"error\",\"message\":\"Plug not enabled\"}");
    return;
  }
  if (!server.hasArg("on")) {
    server.send(400, "application/json", "{\"status\":\"error\",\"message\":\"Missing on parameter\"}");
    return;
  }
  bool on = (server.arg("on").toInt() != 0);
  if (tasmotaSetPower((uint8_t)plug, on)) {
    server.send(200, "application/json", "{\"status\":\"ok\"}");
  } else {
    server.send(502, "application/json", "{\"status\":\"error\",\"message\":\"Plug did not respond\"}");
  }
}

// ---------------------------------------------------------------------------
//  Settings export (JSON download)
// ---------------------------------------------------------------------------
static void gaugeColorsToJson(JsonObject& obj, const GaugeColors& gc) {
  char buf[8];
  rgb565ToHtml(gc.arc, buf);   obj["arc"] = String(buf);
  rgb565ToHtml(gc.label, buf); obj["label"] = String(buf);
  rgb565ToHtml(gc.value, buf); obj["value"] = String(buf);
}

static void handleSettingsExport() {
  JsonDocument doc;
  doc["_type"] = "bambuhelper_settings";
  doc["_version"] = FW_VERSION;
  doc["_secretsIncluded"] = false;
  doc["_secretPolicy"] = "redacted; re-enter WiFi and printer access codes after restore";

  // WiFi (SSID is configuration; password is deliberately omitted)
  JsonObject wifi = doc["wifi"].to<JsonObject>();
  wifi["ssid"] = wifiSSID;
  wifi["pass"] = "";
  wifi["passRedacted"] = true;

  // Printers
  JsonArray pArr = doc["printers"].to<JsonArray>();
  for (uint8_t i = 0; i < MAX_PRINTERS; i++) {
    PrinterConfig& cfg = printers[i].config;
    JsonObject p = pArr.add<JsonObject>();
    p["mode"] = (uint8_t)cfg.mode;
    p["name"] = cfg.name;
    p["ip"] = cfg.ip;
    p["serial"] = cfg.serial;
    p["accessCode"] = "";
    p["accessCodeRedacted"] = true;
    p["cloudUserId"] = "";
    p["cloudIdentityRedacted"] = true;
    p["region"] = (uint8_t)cfg.region;
    JsonArray slots = p["gaugeSlots"].to<JsonArray>();
    for (uint8_t g = 0; g < GAUGE_SLOT_COUNT; g++) slots.add(cfg.gaugeSlots[g]);
    JsonArray lext = p["landscapeExtras"].to<JsonArray>();
    for (uint8_t g = 0; g < LANDSCAPE_EXTRA_COUNT; g++) lext.add(cfg.landscapeExtras[g]);
    JsonArray pext = p["portraitExtras"].to<JsonArray>();
    for (uint8_t g = 0; g < PORTRAIT_EXTRA_COUNT;  g++) pext.add(cfg.portraitExtras[g]);
    JsonArray islot = p["idleSlots"].to<JsonArray>();
    for (uint8_t g = 0; g < IDLE_SLOT_COUNT;       g++) islot.add(cfg.idleSlots[g]);
    p["amsView"] = cfg.amsView;
    p["lightFlags"] = cfg.lightFlags;       // chamber-light automation bitmask
    p["lightDelay"] = cfg.lightOffDelayMin; // off delay (minutes)
  }

  // Display
  char buf[8];
  JsonObject disp = doc["display"].to<JsonObject>();
  disp["brightness"] = brightness;
  disp["rotation"] = dispSettings.rotation;
  rgb565ToHtml(dispSettings.bgColor, buf);    disp["bgColor"] = String(buf);
  rgb565ToHtml(dispSettings.trackColor, buf); disp["trackColor"] = String(buf);
  rgb565ToHtml(dispSettings.progressBarColor, buf); disp["progressBarColor"] = String(buf);
  rgb565ToHtml(dispSettings.clockTimeColor, buf); disp["clockTimeColor"] = String(buf);
  rgb565ToHtml(dispSettings.clockDateColor, buf); disp["clockDateColor"] = String(buf);
  disp["clockTimeSize"] = dispSettings.clockTimeSize;
  disp["clockDateSize"] = dispSettings.clockDateSize;
  disp["hideClockDate"] = dispSettings.hideClockDate;
  disp["showClockInfo"] = dispSettings.showClockInfo;
  disp["amsTrayTypes"] = dispSettings.amsTrayTypes;
  disp["buttonPowerControl"] = dispSettings.buttonPowerControl;
  disp["animatedBar"] = dispSettings.animatedBar;
  disp["pongClock"] = dispSettings.pongClock;
  disp["smallLabels"] = dispSettings.smallLabels;
  disp["timeDisplayMode"] = dispSettings.timeDisplayMode;
  // Legacy key, still emitted so an export imported by pre-3.7.7 firmware keeps
  // the closest behaviour ("Both" degrades to the ETA form).
  disp["showTimeRemaining"] = (dispSettings.timeDisplayMode == 1);
  disp["fanMatchPrinter"] = dispSettings.fanMatchPrinter;
  disp["hideStatusReadout"] = dispSettings.hideStatusReadout;
  disp["showBatteryIndicator"] = dispSettings.showBatteryIndicator;
  disp["nozzleScaleMax"]  = dispSettings.nozzleScaleMax;
  disp["bedScaleMax"]     = dispSettings.bedScaleMax;
  disp["chamberScaleMax"] = dispSettings.chamberScaleMax;
  disp["powerScaleW"]     = dispSettings.powerScaleW;
  disp["gaugeSmoothing"]  = dispSettings.gaugeSmoothing;
  rgb565ToHtml(dispSettings.warnColor, buf); disp["warnColor"] = String(buf);
  disp["warnThresholdPct"] = dispSettings.warnThresholdPct;
  rgb565ToHtml(dispSettings.etaColor, buf);      disp["etaColor"] = String(buf);
  rgb565ToHtml(dispSettings.finishColor, buf);   disp["finishColor"] = String(buf);
  rgb565ToHtml(dispSettings.statusOkColor, buf); disp["statusOkColor"] = String(buf);
  rgb565ToHtml(dispSettings.printerNameColor, buf); disp["printerNameColor"] = String(buf);
  rgb565ToHtml(dispSettings.textColor, buf);     disp["textColor"] = String(buf);
  rgb565ToHtml(dispSettings.textDimColor, buf);  disp["textDimColor"] = String(buf);
  rgb565ToHtml(dispSettings.doorClosedColor, buf); disp["doorClosedColor"] = String(buf);
  rgb565ToHtml(dispSettings.doorOpenColor, buf);   disp["doorOpenColor"] = String(buf);
  disp["roundSkin"] = dispSettings.roundSkin;
  disp["glowMode"] = dispSettings.glowMode;
  rgb565ToHtml(dispSettings.glowColor, buf); disp["glowColor"] = String(buf);
  disp["glowStyle"] = dispSettings.glowStyle;
  disp["glowDuration"] = dispSettings.glowDuration;
#if HAS_HMS_UI
  disp["hmsEnabled"] = dispSettings.hmsEnabled;
  disp["hmsSeverityAll"] = dispSettings.hmsSeverityAll;
  disp["hmsAlertMask"] = dispSettings.hmsAlertMask;
  disp["hmsAutoPresent"] = dispSettings.hmsAutoPresent;
  disp["hmsLookupOnline"] = dispSettings.hmsLookupOnline;
#endif

  JsonObject gauges = disp["gauges"].to<JsonObject>();
  JsonObject gPrg = gauges["progress"].to<JsonObject>(); gaugeColorsToJson(gPrg, dispSettings.progress);
  JsonObject gNoz = gauges["nozzle"].to<JsonObject>();   gaugeColorsToJson(gNoz, dispSettings.nozzle);
  JsonObject gBed = gauges["bed"].to<JsonObject>();      gaugeColorsToJson(gBed, dispSettings.bed);
  JsonObject gPfn = gauges["partFan"].to<JsonObject>();  gaugeColorsToJson(gPfn, dispSettings.partFan);
  JsonObject gAfn = gauges["auxFan"].to<JsonObject>();   gaugeColorsToJson(gAfn, dispSettings.auxFan);
  JsonObject gAfr = gauges["auxFanRight"].to<JsonObject>(); gaugeColorsToJson(gAfr, dispSettings.auxFanRight);
  JsonObject gCfn = gauges["chamberFan"].to<JsonObject>(); gaugeColorsToJson(gCfn, dispSettings.chamberFan);
  JsonObject gExh = gauges["exhaustFan"].to<JsonObject>(); gaugeColorsToJson(gExh, dispSettings.exhaustFan);
  JsonObject gCht = gauges["chamberTemp"].to<JsonObject>(); gaugeColorsToJson(gCht, dispSettings.chamberTemp);
  JsonObject gHbk = gauges["heatbreak"].to<JsonObject>(); gaugeColorsToJson(gHbk, dispSettings.heatbreak);
  JsonObject gPwr = gauges["power"].to<JsonObject>();     gaugeColorsToJson(gPwr, dispSettings.power);
  JsonObject gLyr = gauges["layer"].to<JsonObject>();     gaugeColorsToJson(gLyr, dispSettings.layer);

  // Custom gauge labels
  JsonObject glbl = disp["gaugeLabels"].to<JsonObject>();
  glbl["progress"]    = gaugeLabels.progress;
  glbl["nozzle"]      = gaugeLabels.nozzle;
  glbl["nozzleRight"] = gaugeLabels.nozzleRight;
  glbl["nozzleLeft"]  = gaugeLabels.nozzleLeft;
  glbl["bed"]         = gaugeLabels.bed;
  glbl["partFan"]     = gaugeLabels.partFan;
  glbl["auxFan"]      = gaugeLabels.auxFan;
  glbl["auxFanRight"] = gaugeLabels.auxFanRight;
  glbl["chamberFan"]  = gaugeLabels.chamberFan;
  glbl["exhaustFan"]  = gaugeLabels.exhaustFan;
  glbl["chamberTemp"] = gaugeLabels.chamberTemp;
  glbl["heatbreak"]   = gaugeLabels.heatbreak;
  glbl["power"]       = gaugeLabels.power;
  glbl["layer"]       = gaugeLabels.layer;
  glbl["clock"]       = gaugeLabels.clock;
  glbl["amsBase"]     = gaugeLabels.amsBase;
  glbl["door"]        = gaugeLabels.door;

  // Display power
  JsonObject dp = doc["displayPower"].to<JsonObject>();
  dp["finishDisplayMins"] = dpSettings.finishDisplayMins;
  dp["keepDisplayOn"] = dpSettings.keepDisplayOn;
  dp["showClockAfterFinish"] = dpSettings.showClockAfterFinish;
  dp["doorAckEnabled"] = dpSettings.doorAckEnabled;
  dp["keepPrintScreen"] = dpSettings.keepPrintScreen;
  dp["finishShowTime"] = dpSettings.finishShowTime;
  dp["nightModeEnabled"] = dpSettings.nightModeEnabled;
  dp["nightStartHour"] = dpSettings.nightStartHour;
  dp["nightEndHour"] = dpSettings.nightEndHour;
  dp["nightBrightness"] = dpSettings.nightBrightness;
  dp["screensaverBrightness"] = dpSettings.screensaverBrightness;

  // Network
  JsonObject net = doc["network"].to<JsonObject>();
  net["useDHCP"] = netSettings.useDHCP;
  net["staticIP"] = netSettings.staticIP;
  net["gateway"] = netSettings.gateway;
  net["subnet"] = netSettings.subnet;
  net["dns"] = netSettings.dns;
  net["timezoneIndex"] = netSettings.timezoneIndex;
  net["timezoneStr"] = netSettings.timezoneStr;
  net["use24h"] = netSettings.use24h;
  net["dateFormat"] = netSettings.dateFormat;
  net["mdnsEnabled"] = netSettings.mdnsEnabled;
  net["hostname"] = netSettings.hostname;

  // Rotation
  JsonObject rot = doc["rotation"].to<JsonObject>();
  rot["mode"] = (uint8_t)rotState.mode;
  rot["intervalMs"] = rotState.intervalMs;
  rot["split"] = rotState.splitEnabled;
  rot["splitForce"] = rotState.splitForce;

  // Button
  JsonObject btn = doc["button"].to<JsonObject>();
  btn["type"] = (uint8_t)buttonType;
  btn["pin"] = buttonPin;

  // Buzzer
  JsonObject buz = doc["buzzer"].to<JsonObject>();
  buz["enabled"] = buzzerSettings.enabled;
  buz["pin"] = buzzerSettings.pin;
  buz["quietStart"] = buzzerSettings.quietStartHour;
  buz["quietEnd"] = buzzerSettings.quietEndHour;
  buz["buttonClick"] = buzzerSettings.buttonClick;
  buz["bedCooldownAlert"] = buzzerSettings.bedCooldownAlert;
  buz["bedCooldownThresholdC"] = buzzerSettings.bedCooldownThresholdC;

  // Status LED
  JsonObject led = doc["led"].to<JsonObject>();
  led["enabled"]    = ledSettings.enabled;
  led["pin"]        = ledSettings.pin;
  led["brightness"] = ledSettings.brightness;
  led["driver"]      = ledSettings.driver;
  led["pinG"]        = ledSettings.pinG;
  led["pinB"]        = ledSettings.pinB;
  led["commonAnode"] = ledSettings.commonAnode;
  JsonObject ledCol = led["colors"].to<JsonObject>();
  ledCol["idle"]     = ledSettings.colorIdle;
  ledCol["printing"] = ledSettings.colorPrinting;
  ledCol["paused"]   = ledSettings.colorPaused;
  ledCol["finished"] = ledSettings.colorFinished;
  ledCol["error"]    = ledSettings.colorError;
  JsonObject ledFx = led["finish"].to<JsonObject>();
  ledFx["mode"]       = ledSettings.finishMode;
  ledFx["seconds"]    = ledSettings.finishSeconds;
  ledFx["brightness"] = ledSettings.finishBrightness;
  led["autoOnWhilePrinting"] = ledSettings.autoOnWhilePrinting;
  led["pauseBreathing"]      = ledSettings.pauseBreathing;
  led["errorStrobe"]         = ledSettings.errorStrobe;
  led["errorStrobeSeconds"]  = ledSettings.errorStrobeSeconds;

  // Tasmota power monitoring
  JsonObject tsm = doc["tasmota"].to<JsonObject>();
  tsm["currency"] = tasmotaCurrency;
  tsm["tariff"]   = tasmotaTariffPerKwh;
  JsonArray plugs = tsm["plugs"].to<JsonArray>();
  for (uint8_t i = 0; i < TASMOTA_PLUG_COUNT; i++) {
    JsonObject p = plugs.add<JsonObject>();
    p["enabled"]         = tasmotaSettings[i].enabled;
    p["plugType"]        = tasmotaSettings[i].plugType;
    p["plugOutlet"]      = tasmotaSettings[i].plugOutlet;
    p["ip"]              = tasmotaSettings[i].ip;
    p["displayMode"]     = tasmotaSettings[i].displayMode;
    p["pollInterval"]    = tasmotaSettings[i].pollInterval;
    p["autoOffEnabled"]      = tasmotaSettings[i].autoOffEnabled;
    p["autoOffDelayMin"]     = tasmotaSettings[i].autoOffDelayMin;
    p["autoOffCancelOnDoor"] = tasmotaSettings[i].autoOffCancelOnDoor;
#if TASMOTA_PLUG_COUNT == 1
    p["assignedSlot"]    = tasmotaSettings[i].assignedSlot;
#endif
  }

  String json;
  serializeJsonPretty(doc, json);

  server.sendHeader("Content-Disposition", "attachment; filename=\"bambuhelper_settings.json\"");
  server.send(200, "application/json", json);
}

// ---------------------------------------------------------------------------
//  Settings import (JSON upload)
// ---------------------------------------------------------------------------
static String settingsImportBuf;
static bool   settingsImportOverflow = false;
static bool   otaInProgress  = false;
static bool   otaFirstChunk  = false;
static String otaError       = "";

// A >=16 MB flash chip still running the 4 MB partition table (1.75 MB OTA
// slots). Such a board can be repartitioned with a one-time full web-flasher
// flash, so "firmware too large" OTA failures get actionable guidance appended
// instead of dead-ending the user on a generic error.
static bool isUnderPartitioned() {
  const esp_partition_t* p = esp_ota_get_next_update_partition(NULL);
  return p && p->size <= 0x1C0000 && ESP.getFlashChipSize() >= 16 * 1024 * 1024;
}
static const char REPARTITION_HINT[] =
  " This board has a 16 MB flash chip on the old 4 MB layout: back up settings"
  " (Export), then reflash once via the web flasher to repartition. OTA works"
  " normally afterwards.";
// Every OTA entry point calls disconnectBambuMqtt() up front, and only a
// reboot (success path) re-arms the connections. When an OTA attempt fails
// or is aborted, this flag requests initBambuMqtt() from handleWebServer()
// on the main loop - never directly from otaAutoTaskFn, whose 8KB stack
// cannot host the TLS userId extraction initBambuMqtt() may perform.
static volatile bool otaMqttReinitPending = false;

// Auto-update (device-initiated, HTTPUpdate from GitHub releases)
#ifdef ENABLE_OTA_AUTO
static volatile bool otaAutoInProgress = false;
static volatile int  otaAutoProgress   = 0;
static String        otaAutoStatus     = "";

static bool isExpectedOtaAssetUrl(const String& url) {
  if (url.length() == 0) return false;
  // The initiating URL must be the canonical BambuHelper release path. The
  // GitHub HTTP client may subsequently follow GitHub's signed CDN redirect.
  if (!url.startsWith("https://github.com/Keralots/BambuHelper/releases/download/")) {
    return false;
  }

  int q = url.indexOf('?');
  String clean = q >= 0 ? url.substring(0, q) : url;
  int slash = clean.lastIndexOf('/');
  String file = slash >= 0 ? clean.substring(slash + 1) : clean;

  String prefix = "BambuHelper-" BOARD_VARIANT "-";
  return file.startsWith(prefix) && file.endsWith("-ota.bin");
}
#endif

static void gaugeColorsFromJson(JsonObject obj, GaugeColors& gc) {
  if (obj["arc"].is<const char*>())   gc.arc   = htmlToRgb565(obj["arc"]);
  if (obj["label"].is<const char*>()) gc.label = htmlToRgb565(obj["label"]);
  if (obj["value"].is<const char*>()) gc.value = htmlToRgb565(obj["value"]);
}

static void handleSettingsImportUpload() {
  HTTPUpload& upload = server.upload();
  if (upload.status == UPLOAD_FILE_START) {
    settingsImportBuf = "";
    settingsImportBuf.reserve(4096);
    settingsImportOverflow = false;
  } else if (upload.status == UPLOAD_FILE_WRITE) {
    if (settingsImportOverflow) return;
    if (settingsImportBuf.length() + upload.currentSize > 12288) {
      settingsImportOverflow = true;
      settingsImportBuf = "";  // free memory, rest of upload is ignored
      return;
    }
    for (size_t i = 0; i < upload.currentSize; i++)
      settingsImportBuf += (char)upload.buf[i];
  }
}

static void handleSettingsImportFinish() {
  if (settingsImportOverflow) {
    settingsImportOverflow = false;
    server.send(400, "application/json",
      "{\"status\":\"error\",\"message\":\"Settings file too large (max 12 KB)\"}");
    return;
  }

  JsonDocument doc;
  DeserializationError err = deserializeJson(doc, settingsImportBuf);
  settingsImportBuf = "";  // free memory

  if (err) {
    server.send(400, "application/json", "{\"status\":\"error\",\"message\":\"Invalid JSON\"}");
    return;
  }
  if (!doc["_type"].is<const char*>() || strcmp(doc["_type"], "bambuhelper_settings") != 0) {
    server.send(400, "application/json", "{\"status\":\"error\",\"message\":\"Not a BambuHelper settings file\"}");
    return;
  }

  // WiFi
  JsonObject wifi = doc["wifi"];
  if (wifi) {
    if (wifi["ssid"].is<const char*>()) strlcpy(wifiSSID, wifi["ssid"], sizeof(wifiSSID));
    if (wifi["pass"].is<const char*>()) {
      const char* importedPass = wifi["pass"];
      if (importedPass && importedPass[0] != '\0')
        strlcpy(wifiPass, importedPass, sizeof(wifiPass));
    }
  }

  // Printers
  // Resolve per-printer amsView with backward compat for legacy backups: per-slot
  // value wins; if absent, fall back to top-level display.amsView (old format);
  // otherwise leave default. An explicit per-printer value must never be
  // overridden by the legacy global (matters for mixed/hand-edited backups).
  JsonObject legacyDisp = doc["display"];
  bool legacyAmsViewPresent = legacyDisp && legacyDisp["amsView"].is<bool>();
  bool legacyAmsView = legacyAmsViewPresent ? legacyDisp["amsView"].as<bool>() : false;

  JsonArray pArr = doc["printers"];
  if (pArr) {
    for (uint8_t i = 0; i < MAX_PRINTERS && i < pArr.size(); i++) {
      JsonObject p = pArr[i];
      PrinterConfig& cfg = printers[i].config;
      if (p["mode"].is<uint8_t>())            cfg.mode = (ConnMode)p["mode"].as<uint8_t>();
      if (p["name"].is<const char*>())      { strlcpy(cfg.name, p["name"], sizeof(cfg.name)); utf8TrimPartial(cfg.name); }
      if (p["ip"].is<const char*>())          strlcpy(cfg.ip, p["ip"], sizeof(cfg.ip));
      if (p["serial"].is<const char*>())      strlcpy(cfg.serial, p["serial"], sizeof(cfg.serial));
      if (p["accessCode"].is<const char*>()) {
        const char* importedCode = p["accessCode"];
        if (importedCode && importedCode[0] != '\0')
          strlcpy(cfg.accessCode, importedCode, sizeof(cfg.accessCode));
      }
      if (p["cloudUserId"].is<const char*>()) {
        const char* importedUser = p["cloudUserId"];
        if (importedUser && importedUser[0] != '\0')
          strlcpy(cfg.cloudUserId, importedUser, sizeof(cfg.cloudUserId));
      }
      if (p["region"].is<uint8_t>())          cfg.region = (CloudRegion)p["region"].as<uint8_t>();
      JsonArray slots = p["gaugeSlots"];
      // Standard 2x3 grid. Accept any export with size >= 6 (legacy 8/9-byte
      // arrays from the in-development shared-extras branch get truncated -
      // their extras moved to dedicated landscapeExtras / portraitExtras
      // fields in the same export, so nothing is lost).
      if (slots && slots.size() >= 6) {
        static const uint8_t defSlots[GAUGE_SLOT_COUNT] = {
          GAUGE_PROGRESS, GAUGE_NOZZLE, GAUGE_BED,
          GAUGE_PART_FAN, GAUGE_AUX_FAN, GAUGE_CHAMBER_FAN
        };
        for (uint8_t g = 0; g < GAUGE_SLOT_COUNT; g++) {
          uint8_t v = slots[g].as<uint8_t>();
          cfg.gaugeSlots[g] = (v < GAUGE_TYPE_COUNT) ? v : defSlots[g];
        }
      }
      auto importExtras = [](JsonArray arr, uint8_t* out, uint8_t count) {
        for (uint8_t g = 0; g < count; g++) {
          if (arr && g < arr.size()) {
            uint8_t v = arr[g].as<uint8_t>();
            out[g] = (v < GAUGE_TYPE_COUNT) ? v : GAUGE_EMPTY;
          } else {
            out[g] = GAUGE_EMPTY;
          }
        }
      };
      importExtras(p["landscapeExtras"].as<JsonArray>(), cfg.landscapeExtras, LANDSCAPE_EXTRA_COUNT);
      importExtras(p["portraitExtras"].as<JsonArray>(),  cfg.portraitExtras,  PORTRAIT_EXTRA_COUNT);
      // Ready / Print Complete pair. Backups predating it have no field, so
      // restore the nozzle+bed those screens used to draw rather than blanking
      // them. Camera is refused here too - see handleSaveGaugeLayout.
      {
        JsonArray islot = p["idleSlots"].as<JsonArray>();
        static const uint8_t defIdle[IDLE_SLOT_COUNT] = { GAUGE_NOZZLE, GAUGE_BED };
        for (uint8_t g = 0; g < IDLE_SLOT_COUNT; g++) {
          if (islot && g < islot.size()) {
            uint8_t v = islot[g].as<uint8_t>();
            cfg.idleSlots[g] = (v < GAUGE_TYPE_COUNT && v != GAUGE_CAMERA) ? v : GAUGE_EMPTY;
          } else {
            cfg.idleSlots[g] = defIdle[g];
          }
        }
      }
      if (p["amsView"].is<bool>()) {
        cfg.amsView = p["amsView"].as<bool>();
      } else if (legacyAmsViewPresent) {
        cfg.amsView = legacyAmsView;
      }
      if (p["lightFlags"].is<uint8_t>()) cfg.lightFlags = p["lightFlags"].as<uint8_t>();
      if (p["lightDelay"].is<uint8_t>()) cfg.lightOffDelayMin = constrain(p["lightDelay"].as<int>(), 0, 60);
    }
  }

  // Display
  JsonObject disp = doc["display"];
  if (disp) {
    if (disp["brightness"].is<uint8_t>()) brightness = disp["brightness"].as<uint8_t>();
    if (disp["rotation"].is<uint8_t>())   dispSettings.rotation = disp["rotation"].as<uint8_t>();
    if (disp["bgColor"].is<const char*>())    dispSettings.bgColor = htmlToRgb565(disp["bgColor"]);
    if (disp["trackColor"].is<const char*>()) dispSettings.trackColor = htmlToRgb565(disp["trackColor"]);
    if (disp["progressBarColor"].is<const char*>()) dispSettings.progressBarColor = htmlToRgb565(disp["progressBarColor"]);
    if (disp["clockTimeColor"].is<const char*>()) dispSettings.clockTimeColor = htmlToRgb565(disp["clockTimeColor"]);
    if (disp["clockDateColor"].is<const char*>()) dispSettings.clockDateColor = htmlToRgb565(disp["clockDateColor"]);
    if (disp["clockTimeSize"].is<int>()) {
      int s = disp["clockTimeSize"].as<int>();
      dispSettings.clockTimeSize = (s >= 0 && s <= 3) ? (uint8_t)s : 0;
    }
    if (disp["clockDateSize"].is<int>()) {
      int s = disp["clockDateSize"].as<int>();
      dispSettings.clockDateSize = (s >= 0 && s <= 3) ? (uint8_t)s : 0;
    }
    if (disp["hideClockDate"].is<bool>()) dispSettings.hideClockDate = disp["hideClockDate"].as<bool>();
    if (disp["showClockInfo"].is<bool>()) dispSettings.showClockInfo = disp["showClockInfo"].as<bool>();
    if (disp["amsTrayTypes"].is<bool>())  dispSettings.amsTrayTypes = disp["amsTrayTypes"].as<bool>();
    if (disp["buttonPowerControl"].is<bool>()) dispSettings.buttonPowerControl = disp["buttonPowerControl"].as<bool>();
    if (disp["animatedBar"].is<bool>())       dispSettings.animatedBar = disp["animatedBar"].as<bool>();
    if (disp["pongClock"].is<bool>())           dispSettings.pongClock = disp["pongClock"].as<bool>();
    if (disp["smallLabels"].is<bool>())         dispSettings.smallLabels = disp["smallLabels"].as<bool>();
    // New tri-state key wins; fall back to the legacy boolean for old exports.
    if (disp["timeDisplayMode"].is<int>()) {
      int tm = disp["timeDisplayMode"].as<int>();
      dispSettings.timeDisplayMode = (tm >= 0 && tm <= 2) ? (uint8_t)tm : 0;
    } else if (disp["showTimeRemaining"].is<bool>()) {
      dispSettings.timeDisplayMode = disp["showTimeRemaining"].as<bool>() ? 1 : 0;
    }
    if (disp["fanMatchPrinter"].is<bool>())     dispSettings.fanMatchPrinter = disp["fanMatchPrinter"].as<bool>();
    if (disp["hideStatusReadout"].is<bool>())   dispSettings.hideStatusReadout = disp["hideStatusReadout"].as<bool>();
    if (disp["showBatteryIndicator"].is<bool>()) dispSettings.showBatteryIndicator = disp["showBatteryIndicator"].as<bool>();
    // Gauge full-scale ranges: accept any JSON number and clamp (so crafted
    // out-of-range values are corrected, not silently ignored).
    if (disp["nozzleScaleMax"].is<int>())  dispSettings.nozzleScaleMax  = constrain(disp["nozzleScaleMax"].as<int>(),  GAUGE_NOZZLE_SCALE_MIN,  GAUGE_NOZZLE_SCALE_MAX);
    if (disp["bedScaleMax"].is<int>())     dispSettings.bedScaleMax     = constrain(disp["bedScaleMax"].as<int>(),     GAUGE_BED_SCALE_MIN,     GAUGE_BED_SCALE_MAX);
    if (disp["chamberScaleMax"].is<int>()) dispSettings.chamberScaleMax = constrain(disp["chamberScaleMax"].as<int>(), GAUGE_CHAMBER_SCALE_MIN, GAUGE_CHAMBER_SCALE_MAX);
    if (disp["powerScaleW"].is<int>())     dispSettings.powerScaleW     = constrain(disp["powerScaleW"].as<int>(),     GAUGE_POWER_SCALE_MIN,   GAUGE_POWER_SCALE_MAX);
    if (disp["gaugeSmoothing"].is<int>())  { int sm = disp["gaugeSmoothing"].as<int>(); dispSettings.gaugeSmoothing = (sm >= 0 && sm <= 3) ? (uint8_t)sm : 2; }
    if (disp["warnColor"].is<const char*>()) dispSettings.warnColor = htmlToRgb565(disp["warnColor"]);
    if (disp["warnThresholdPct"].is<int>()) dispSettings.warnThresholdPct = constrain(disp["warnThresholdPct"].as<int>(), 0, 100);
    if (disp["etaColor"].is<const char*>())      dispSettings.etaColor = htmlToRgb565(disp["etaColor"]);
    if (disp["finishColor"].is<const char*>())   dispSettings.finishColor = htmlToRgb565(disp["finishColor"]);
    if (disp["statusOkColor"].is<const char*>()) dispSettings.statusOkColor = htmlToRgb565(disp["statusOkColor"]);
    if (disp["printerNameColor"].is<const char*>()) dispSettings.printerNameColor = htmlToRgb565(disp["printerNameColor"]);
    if (disp["textColor"].is<const char*>())     dispSettings.textColor = htmlToRgb565(disp["textColor"]);
    if (disp["textDimColor"].is<const char*>())  dispSettings.textDimColor = htmlToRgb565(disp["textDimColor"]);
    if (disp["doorClosedColor"].is<const char*>()) dispSettings.doorClosedColor = htmlToRgb565(disp["doorClosedColor"]);
    if (disp["doorOpenColor"].is<const char*>())   dispSettings.doorOpenColor = htmlToRgb565(disp["doorOpenColor"]);
    if (disp["roundSkin"].is<int>()) { int rs = disp["roundSkin"].as<int>(); dispSettings.roundSkin = (rs >= 0 && rs <= 2) ? (uint8_t)rs : 0; }
    if (disp["glowMode"].is<int>())  { int gm = disp["glowMode"].as<int>();  dispSettings.glowMode = (gm >= 0 && gm <= 2) ? (uint8_t)gm : 0; }
    if (disp["glowColor"].is<const char*>()) dispSettings.glowColor = htmlToRgb565(disp["glowColor"]);
    if (disp["glowStyle"].is<int>()) { int gs = disp["glowStyle"].as<int>(); dispSettings.glowStyle = (gs >= 0 && gs <= 2) ? (uint8_t)gs : 0; }
    if (disp["glowDuration"].is<int>()) { int gd = disp["glowDuration"].as<int>(); dispSettings.glowDuration = (gd >= 0 && gd <= 2) ? (uint8_t)gd : 0; }
#if HAS_HMS_UI
    if (disp["hmsEnabled"].is<bool>())     dispSettings.hmsEnabled = disp["hmsEnabled"].as<bool>();
    if (disp["hmsSeverityAll"].is<bool>()) dispSettings.hmsSeverityAll = disp["hmsSeverityAll"].as<bool>();
    if (disp["hmsAlertMask"].is<int>())    dispSettings.hmsAlertMask = (uint8_t)(disp["hmsAlertMask"].as<int>() & 0x0F);
    if (disp["hmsAutoPresent"].is<int>())  { int ap = disp["hmsAutoPresent"].as<int>(); dispSettings.hmsAutoPresent = (ap >= 0 && ap <= 2) ? (uint8_t)ap : 0; }
    if (disp["hmsLookupOnline"].is<bool>()) dispSettings.hmsLookupOnline = disp["hmsLookupOnline"].as<bool>();
#endif
    // Legacy disp["amsView"] is consumed in the printers block above as a fallback
    // for slots that don't have their own per-printer value.

    JsonObject gauges = disp["gauges"];
    if (gauges) {
      if (gauges["progress"].is<JsonObject>()) { JsonObject g = gauges["progress"]; gaugeColorsFromJson(g, dispSettings.progress); }
      if (gauges["nozzle"].is<JsonObject>())   { JsonObject g = gauges["nozzle"];   gaugeColorsFromJson(g, dispSettings.nozzle); }
      if (gauges["bed"].is<JsonObject>())      { JsonObject g = gauges["bed"];      gaugeColorsFromJson(g, dispSettings.bed); }
      if (gauges["partFan"].is<JsonObject>())  { JsonObject g = gauges["partFan"];  gaugeColorsFromJson(g, dispSettings.partFan); }
      if (gauges["auxFan"].is<JsonObject>())   { JsonObject g = gauges["auxFan"];   gaugeColorsFromJson(g, dispSettings.auxFan); }
      if (gauges["auxFanRight"].is<JsonObject>()){ JsonObject g = gauges["auxFanRight"]; gaugeColorsFromJson(g, dispSettings.auxFanRight); }
      if (gauges["chamberFan"].is<JsonObject>()){ JsonObject g = gauges["chamberFan"]; gaugeColorsFromJson(g, dispSettings.chamberFan); }
      if (gauges["exhaustFan"].is<JsonObject>()){ JsonObject g = gauges["exhaustFan"]; gaugeColorsFromJson(g, dispSettings.exhaustFan); }
      if (gauges["chamberTemp"].is<JsonObject>()){ JsonObject g = gauges["chamberTemp"]; gaugeColorsFromJson(g, dispSettings.chamberTemp); }
      if (gauges["heatbreak"].is<JsonObject>()){ JsonObject g = gauges["heatbreak"]; gaugeColorsFromJson(g, dispSettings.heatbreak); }
      if (gauges["power"].is<JsonObject>())    { JsonObject g = gauges["power"];     gaugeColorsFromJson(g, dispSettings.power); }
      if (gauges["layer"].is<JsonObject>())    { JsonObject g = gauges["layer"];     gaugeColorsFromJson(g, dispSettings.layer); }
    }

    JsonObject glbl = disp["gaugeLabels"];
    if (glbl) {
      struct { const char* k; char* dst; size_t len; } LB[] = {
        {"progress",    gaugeLabels.progress,    sizeof(gaugeLabels.progress)},
        {"nozzle",      gaugeLabels.nozzle,      sizeof(gaugeLabels.nozzle)},
        {"nozzleRight", gaugeLabels.nozzleRight, sizeof(gaugeLabels.nozzleRight)},
        {"nozzleLeft",  gaugeLabels.nozzleLeft,  sizeof(gaugeLabels.nozzleLeft)},
        {"bed",         gaugeLabels.bed,         sizeof(gaugeLabels.bed)},
        {"partFan",     gaugeLabels.partFan,     sizeof(gaugeLabels.partFan)},
        {"auxFan",      gaugeLabels.auxFan,      sizeof(gaugeLabels.auxFan)},
        {"auxFanRight", gaugeLabels.auxFanRight, sizeof(gaugeLabels.auxFanRight)},
        {"chamberFan",  gaugeLabels.chamberFan,  sizeof(gaugeLabels.chamberFan)},
        {"exhaustFan",  gaugeLabels.exhaustFan,  sizeof(gaugeLabels.exhaustFan)},
        {"chamberTemp", gaugeLabels.chamberTemp, sizeof(gaugeLabels.chamberTemp)},
        {"heatbreak",   gaugeLabels.heatbreak,   sizeof(gaugeLabels.heatbreak)},
        {"power",       gaugeLabels.power,       sizeof(gaugeLabels.power)},
        {"layer",       gaugeLabels.layer,       sizeof(gaugeLabels.layer)},
        {"clock",       gaugeLabels.clock,       sizeof(gaugeLabels.clock)},
        {"amsBase",     gaugeLabels.amsBase,     sizeof(gaugeLabels.amsBase)},
        {"door",        gaugeLabels.door,        sizeof(gaugeLabels.door)},
      };
      for (auto& e : LB)
        if (glbl[e.k].is<const char*>()) sanitizeGaugeLabel(glbl[e.k].as<const char*>(), e.dst, e.len);
    }
  }

  // Display power
  JsonObject dp = doc["displayPower"];
  if (dp) {
    if (dp["finishDisplayMins"].is<uint16_t>()) dpSettings.finishDisplayMins = dp["finishDisplayMins"].as<uint16_t>();
    if (dp["keepDisplayOn"].is<bool>())         dpSettings.keepDisplayOn = dp["keepDisplayOn"].as<bool>();
    if (dp["showClockAfterFinish"].is<bool>())  dpSettings.showClockAfterFinish = dp["showClockAfterFinish"].as<bool>();
    if (dp["doorAckEnabled"].is<bool>())        dpSettings.doorAckEnabled = dp["doorAckEnabled"].as<bool>();
    if (dp["keepPrintScreen"].is<bool>())       dpSettings.keepPrintScreen = dp["keepPrintScreen"].as<bool>();
    if (dp["finishShowTime"].is<bool>())        dpSettings.finishShowTime = dp["finishShowTime"].as<bool>();
    if (dp["nightModeEnabled"].is<bool>())      dpSettings.nightModeEnabled = dp["nightModeEnabled"].as<bool>();
    if (dp["nightStartHour"].is<uint8_t>())     dpSettings.nightStartHour = dp["nightStartHour"].as<uint8_t>();
    if (dp["nightEndHour"].is<uint8_t>())       dpSettings.nightEndHour = dp["nightEndHour"].as<uint8_t>();
    if (dp["nightBrightness"].is<uint8_t>())    dpSettings.nightBrightness = dp["nightBrightness"].as<uint8_t>();
    if (dp["screensaverBrightness"].is<uint8_t>()) dpSettings.screensaverBrightness = dp["screensaverBrightness"].as<uint8_t>();
  }

  // Network
  JsonObject net = doc["network"];
  if (net) {
    if (net["useDHCP"].is<bool>())            netSettings.useDHCP = net["useDHCP"].as<bool>();
    if (net["staticIP"].is<const char*>())    strlcpy(netSettings.staticIP, net["staticIP"], sizeof(netSettings.staticIP));
    if (net["gateway"].is<const char*>())     strlcpy(netSettings.gateway, net["gateway"], sizeof(netSettings.gateway));
    if (net["subnet"].is<const char*>())      strlcpy(netSettings.subnet, net["subnet"], sizeof(netSettings.subnet));
    if (net["dns"].is<const char*>())         strlcpy(netSettings.dns, net["dns"], sizeof(netSettings.dns));
    if (net["timezoneStr"].is<const char*>()) {
      strlcpy(netSettings.timezoneStr, net["timezoneStr"], sizeof(netSettings.timezoneStr));
      // Derive the index from the string, never from the backup's stored index:
      // a backup taken on an older firmware numbered the database differently.
      netSettings.timezoneIndex = resolveTimezoneIndex(netSettings.timezoneStr);
    } else if (net["gmtOffsetMin"].is<int16_t>()) {
      // Backward compat: import from old format
      int16_t oldOffset = net["gmtOffsetMin"].as<int16_t>();
      const char* migrated = getDefaultTimezoneForOffset(oldOffset);
      if (migrated) {
        strlcpy(netSettings.timezoneStr, migrated, sizeof(netSettings.timezoneStr));
        netSettings.timezoneIndex = resolveTimezoneIndex(netSettings.timezoneStr);
      }
    }
    if (net["use24h"].is<bool>())             netSettings.use24h = net["use24h"].as<bool>();
    if (net["dateFormat"].is<uint8_t>())     netSettings.dateFormat = net["dateFormat"].as<uint8_t>();
    if (net["mdnsEnabled"].is<bool>())        netSettings.mdnsEnabled = net["mdnsEnabled"].as<bool>();
    if (net["hostname"].is<const char*>())    sanitizeHostname(net["hostname"], netSettings.hostname, sizeof(netSettings.hostname));
  }

  // Rotation
  JsonObject rot = doc["rotation"];
  if (rot) {
    if (rot["mode"].is<uint8_t>())      rotState.mode = (RotateMode)rot["mode"].as<uint8_t>();
    if (rot["intervalMs"].is<uint32_t>()) rotState.intervalMs = rot["intervalMs"].as<uint32_t>();
    if (rot["split"].is<bool>())        rotState.splitEnabled = rot["split"].as<bool>();
    if (rot["splitForce"].is<bool>())   rotState.splitForce = rot["splitForce"].as<bool>();
  }

  // Button
  JsonObject btn = doc["button"];
  if (btn) {
    if (btn["type"].is<uint8_t>()) buttonType = (ButtonType)btn["type"].as<uint8_t>();
    if (btn["pin"].is<uint8_t>())  buttonPin = btn["pin"].as<uint8_t>();
  }

  // Buzzer
  JsonObject buz = doc["buzzer"];
  if (buz) {
    if (buz["enabled"].is<bool>())    buzzerSettings.enabled = buz["enabled"].as<bool>();
    if (buz["pin"].is<uint8_t>())     buzzerSettings.pin = buz["pin"].as<uint8_t>();
    if (buz["quietStart"].is<uint8_t>()) {
      uint8_t qs = buz["quietStart"].as<uint8_t>();
      if (qs <= 23) buzzerSettings.quietStartHour = qs;
    }
    if (buz["quietEnd"].is<uint8_t>()) {
      uint8_t qe = buz["quietEnd"].as<uint8_t>();
      if (qe <= 23) buzzerSettings.quietEndHour = qe;
    }
    if (buz["buttonClick"].is<bool>()) buzzerSettings.buttonClick = buz["buttonClick"].as<bool>();
    if (buz["bedCooldownAlert"].is<bool>()) buzzerSettings.bedCooldownAlert = buz["bedCooldownAlert"].as<bool>();
    if (buz["bedCooldownThresholdC"].is<uint8_t>()) {
      uint8_t t = buz["bedCooldownThresholdC"].as<uint8_t>();
      if (t >= 20 && t <= 80) buzzerSettings.bedCooldownThresholdC = t;
    }
  }

  // Status LED
  JsonObject led = doc["led"];
  if (led) {
    if (led["enabled"].is<bool>())       ledSettings.enabled = led["enabled"].as<bool>();
    if (led["pin"].is<uint8_t>())        ledSettings.pin = led["pin"].as<uint8_t>();
    if (led["brightness"].is<uint8_t>()) ledSettings.brightness = led["brightness"].as<uint8_t>();
    if (led["driver"].is<uint8_t>()) {
      uint8_t d = led["driver"].as<uint8_t>();
      if (d <= LED_DRV_PIXEL) ledSettings.driver = d;
    }
    if (led["pinG"].is<uint8_t>())        ledSettings.pinG = led["pinG"].as<uint8_t>();
    if (led["pinB"].is<uint8_t>())        ledSettings.pinB = led["pinB"].as<uint8_t>();
    if (led["commonAnode"].is<bool>())    ledSettings.commonAnode = led["commonAnode"].as<bool>();
    JsonObject ledCol = led["colors"];
    if (ledCol) {
      if (ledCol["idle"].is<uint32_t>())     ledSettings.colorIdle     = ledCol["idle"].as<uint32_t>() & 0xFFFFFF;
      if (ledCol["printing"].is<uint32_t>()) ledSettings.colorPrinting = ledCol["printing"].as<uint32_t>() & 0xFFFFFF;
      if (ledCol["paused"].is<uint32_t>())   ledSettings.colorPaused   = ledCol["paused"].as<uint32_t>() & 0xFFFFFF;
      if (ledCol["finished"].is<uint32_t>()) ledSettings.colorFinished = ledCol["finished"].as<uint32_t>() & 0xFFFFFF;
      if (ledCol["error"].is<uint32_t>())    ledSettings.colorError    = ledCol["error"].as<uint32_t>() & 0xFFFFFF;
    }
    JsonObject ledFx = led["finish"];
    if (ledFx) {
      if (ledFx["mode"].is<uint8_t>()) {
        uint8_t m = ledFx["mode"].as<uint8_t>();
        if (m <= 2) ledSettings.finishMode = m;
      }
      if (ledFx["seconds"].is<uint16_t>()) {
        uint16_t s = ledFx["seconds"].as<uint16_t>();
        if (s < 5) s = 5; if (s > 600) s = 600;
        ledSettings.finishSeconds = s;
      }
      if (ledFx["brightness"].is<uint8_t>()) ledSettings.finishBrightness = ledFx["brightness"].as<uint8_t>();
    }
    if (led["autoOnWhilePrinting"].is<bool>()) ledSettings.autoOnWhilePrinting = led["autoOnWhilePrinting"].as<bool>();
    if (led["pauseBreathing"].is<bool>())      ledSettings.pauseBreathing      = led["pauseBreathing"].as<bool>();
    if (led["errorStrobe"].is<bool>())         ledSettings.errorStrobe         = led["errorStrobe"].as<bool>();
    if (led["errorStrobeSeconds"].is<uint16_t>()) {
      uint16_t s = led["errorStrobeSeconds"].as<uint16_t>();
      if (s != 0 && s < 5) s = 5; if (s > 600) s = 600;
      ledSettings.errorStrobeSeconds = s;
    }
  }

  // Tasmota power monitoring
  // Accept new schema {"tasmota":{"currency":"€","plugs":[{...}, ...]}} and
  // legacy schema where "tasmota" was a single object (treat as plugs[0]).
  JsonVariant tsmRoot = doc["tasmota"];
  if (!tsmRoot.isNull()) {
    JsonArray plugs;
    JsonObject tsmObj = tsmRoot.as<JsonObject>();
    if (tsmObj && tsmObj["plugs"].is<JsonArray>()) {
      plugs = tsmObj["plugs"];
      if (tsmObj["currency"].is<const char*>()) {
        strlcpy(tasmotaCurrency, tsmObj["currency"], sizeof(tasmotaCurrency));
        utf8TrimPartial(tasmotaCurrency);
      }
      if (tsmObj["tariff"].is<float>() || tsmObj["tariff"].is<double>() || tsmObj["tariff"].is<int>()) {
        float t = tsmObj["tariff"].as<float>();
        if (t < 0.0f) t = 0.0f;
        if (t > 10.0f) t = 10.0f;
        tasmotaTariffPerKwh = t;
      } else if (plugs && plugs.size() > 0) {
        // Back-compat: lift tariff from first plug entry if global field absent.
        JsonObject p0 = plugs[0].as<JsonObject>();
        if (p0["tariffPerKwh"].is<float>() || p0["tariffPerKwh"].is<double>() || p0["tariffPerKwh"].is<int>()) {
          float t = p0["tariffPerKwh"].as<float>();
          if (t < 0.0f) t = 0.0f;
          if (t > 10.0f) t = 10.0f;
          tasmotaTariffPerKwh = t;
        }
      }
    }
    // Helper lambda: apply one plug object into tasmotaSettings[idx]
    auto applyPlug = [](uint8_t idx, JsonObject p) {
      if (idx >= TASMOTA_PLUG_COUNT) return;
      TasmotaSettings& s = tasmotaSettings[idx];
      if (p["enabled"].is<bool>())          s.enabled = p["enabled"].as<bool>();
      if (p["plugType"].is<uint8_t>())      { uint8_t pt = p["plugType"].as<uint8_t>(); s.plugType = (pt <= 3) ? pt : 0; }
      if (p["plugOutlet"].is<uint8_t>())    { uint8_t po = p["plugOutlet"].as<uint8_t>(); s.plugOutlet = (po <= 3) ? po : 0; }
      if (p["ip"].is<const char*>())        strlcpy(s.ip, p["ip"], sizeof(s.ip));
      if (p["displayMode"].is<uint8_t>())   { uint8_t dm = p["displayMode"].as<uint8_t>(); s.displayMode = (dm <= 2) ? dm : 0; }
      if (p["pollInterval"].is<uint8_t>()) {
        uint8_t pi = p["pollInterval"].as<uint8_t>();
        if (pi < 10 || pi > 60) pi = 10;
        s.pollInterval = pi;
      }
      if (p["autoOffEnabled"].is<bool>())   s.autoOffEnabled = p["autoOffEnabled"].as<bool>();
      if (p["autoOffDelayMin"].is<uint8_t>()) {
        uint8_t ad = p["autoOffDelayMin"].as<uint8_t>();
        if (ad < 1 || ad > 240) ad = 10;
        s.autoOffDelayMin = ad;
      }
      if (p["autoOffCancelOnDoor"].is<bool>()) s.autoOffCancelOnDoor = p["autoOffCancelOnDoor"].as<bool>();
#if TASMOTA_PLUG_COUNT == 1
      if (p["assignedSlot"].is<uint8_t>()) {
        uint8_t a = p["assignedSlot"].as<uint8_t>();
        if (a != 255 && a >= MAX_ACTIVE_PRINTERS) a = 255;
        s.assignedSlot = a;
      }
#endif
    };
    if (plugs) {
      uint8_t i = 0;
      for (JsonObject p : plugs) {
        if (i >= TASMOTA_PLUG_COUNT) break;
        applyPlug(i++, p);
      }
    } else if (tsmObj) {
      // Legacy "tasmota" was a single object (or new schema with no "plugs"
      // array). Treat the object itself as plug 0.
      applyPlug(0, tsmObj);
    }
  }

  // Save everything to NVS
  saveSettings();
  saveRotationSettings();
  saveButtonSettings();
  saveBuzzerSettings();
  saveLedSettings();   // sanitizes pin (incl. conflict with freshly-imported buzzer/button)

  server.send(200, "application/json", "{\"status\":\"ok\",\"message\":\"Settings imported. Restarting...\"}");
  scheduleRestart();
}

// ---------------------------------------------------------------------------
//  OTA firmware update
// ---------------------------------------------------------------------------
// ---------------------------------------------------------------------------
//  Auto-update: FreeRTOS task that runs HTTPUpdate from a GitHub release URL
// ---------------------------------------------------------------------------
#ifdef ENABLE_OTA_AUTO
static void otaAutoTaskFn(void* param) {
  String* urlPtr = (String*)param;
  String url = *urlPtr;
  delete urlPtr;

  otaAutoStatus = "downloading";

  // Pause IDLE0 watchdog: a sustained TLS download keeps the WiFi task on
  // core 0 hot enough that IDLE0 can be starved past the 5 s TWDT window,
  // especially on CYD (original ESP32 without S3's crypto accelerator).
  // The OTA task itself runs pinned to core 1 (see handleOtaAuto).
  disableCore0WDT();

  WiFiClientSecure client;
  client.setCACertBundle(rootca_crt_bundle_start);

  httpUpdate.setFollowRedirects(HTTPC_FORCE_FOLLOW_REDIRECTS);
  httpUpdate.onProgress([](int cur, int total) {
    if (total > 0) otaAutoProgress = (int)((cur / (float)total) * 100);
  });

  t_httpUpdate_return ret = httpUpdate.update(client, url);

  switch (ret) {
    case HTTP_UPDATE_OK:
      otaAutoProgress = 100;
      otaAutoStatus = "done";
      Serial.println("OTA auto: success, scheduling restart");
      scheduleRestart(4000);  // let JS poller detect "done" before reboot
      break;
    case HTTP_UPDATE_NO_UPDATES:
      otaAutoStatus = "already_current";
      otaMqttReinitPending = true;  // no reboot coming - restore MQTT
      break;
    case HTTP_UPDATE_FAILED:
    default: {
      int lastErr = httpUpdate.getLastError();
      String err = httpUpdate.getLastErrorString();
      Serial.printf("OTA auto: failed (%d) %s\n", lastErr, err.c_str());
      // Smart Home v8: never retry an OTA download without certificate
      // validation. A CA failure is a hard failure, not a reason to
      // weaken the transport security policy.
      otaAutoStatus = "failed: " + err;
      if (lastErr == HTTP_UE_TOO_LESS_SPACE && isUnderPartitioned())
        otaAutoStatus += REPARTITION_HINT;
      otaMqttReinitPending = true;  // no reboot coming - restore MQTT
      break;
    }
  }

  enableCore0WDT();
  otaAutoInProgress = false;
  vTaskDelete(nullptr);
}

static void handleOtaAuto() {
  if (otaAutoInProgress) {
    server.send(409, "application/json", "{\"error\":\"Update already in progress\"}");
    return;
  }

  String url = server.arg("url");
  if (!isExpectedOtaAssetUrl(url)) {
    server.send(400, "application/json", "{\"error\":\"Missing or invalid url\"}");
    return;
  }

  disconnectBambuMqtt();

  otaAutoInProgress = true;
  otaAutoProgress   = 0;
  otaAutoStatus     = "starting";

  String* urlHeap = new String(url);
  // Pin to core 1: the WiFi task lives on core 0 and a concurrent TLS
  // download here would compete for the same core, starving IDLE0 and
  // tripping the task watchdog mid-flash on slower boards (CYD).
  xTaskCreatePinnedToCore(otaAutoTaskFn, "otaAuto", 8192, (void*)urlHeap, 5, nullptr, 1);

  server.send(200, "application/json", "{\"status\":\"started\"}");
}

bool        isOtaAutoInProgress() { return otaAutoInProgress; }
int         getOtaAutoProgress()  { return otaAutoProgress; }
const char* getOtaAutoStatus()    { return otaAutoStatus.c_str(); }

static void handleOtaStatus() {
  JsonDocument doc;
  doc["inProgress"] = (bool)otaAutoInProgress;
  doc["progress"]   = (int)otaAutoProgress;
  doc["status"]     = otaAutoStatus;
  String json;
  serializeJson(doc, json);
  server.send(200, "application/json", json);
}
#endif // ENABLE_OTA_AUTO


// ---------------------------------------------------------------------------
// Smart Home v8 manual OTA SHA-256 verification
// ---------------------------------------------------------------------------
static mbedtls_sha256_context otaShaCtx;
static bool otaShaActive = false;
static bool otaShaExpectedValid = false;
static uint8_t otaShaExpected[32] = {};

// Smart Home v9.1 manual OTA transaction state. This is intentionally RAM-only:
// it exists to let the browser distinguish an accepted firmware image from a
// transport disconnect while the ESP32 is transitioning into its reboot.
static String manualOtaPhase = "idle";
static String manualOtaMessage = "Ready for application firmware upload";
static size_t manualOtaBytes = 0;


static void resetOtaSha() {
  if (otaShaActive) {
    mbedtls_sha256_free(&otaShaCtx);
    otaShaActive = false;
  }
  otaShaExpectedValid = false;
  memset(otaShaExpected, 0, sizeof(otaShaExpected));
}

static bool parseSha256Hex(const String& raw, uint8_t out[32]) {
  if (raw.length() != 64) return false;
  for (size_t i = 0; i < 32; ++i) {
    const char hi = raw[i * 2];
    const char lo = raw[i * 2 + 1];
    auto nibble = [](char c) -> int {
      if (c >= '0' && c <= '9') return c - '0';
      if (c >= 'a' && c <= 'f') return c - 'a' + 10;
      if (c >= 'A' && c <= 'F') return c - 'A' + 10;
      return -1;
    };
    const int h = nibble(hi);
    const int l = nibble(lo);
    if (h < 0 || l < 0) return false;
    out[i] = static_cast<uint8_t>((h << 4) | l);
  }
  return true;
}

static void handleOtaUpload() {
  HTTPUpload& upload = server.upload();

  if (upload.status == UPLOAD_FILE_START) {
    otaError = "";
    otaInProgress = true;
    manualOtaPhase = "receiving";
    manualOtaMessage = "Receiving firmware";
    manualOtaBytes = 0;

    resetOtaSha();
    const String expectedSha = server.header("X-SHA256");
    if (!parseSha256Hex(expectedSha, otaShaExpected)) {
      otaError = "Missing or invalid X-SHA256 header. Use the Smart Home portal to upload firmware.";
      otaInProgress = false;
      return;
    }
    otaShaExpectedValid = true;
    mbedtls_sha256_init(&otaShaCtx);
    if (mbedtls_sha256_starts_ret(&otaShaCtx, 0) != 0) {
      otaError = "Could not initialize SHA-256 verification.";
      resetOtaSha();
      otaInProgress = false;
      return;
    }
    otaShaActive = true;
    otaFirstChunk = true;
    Serial.printf("OTA: start, file=%s\n", upload.filename.c_str());

    disconnectBambuMqtt();

    const esp_partition_t* partition = esp_ota_get_next_update_partition(NULL);
    if (!partition) {
      otaError = "No OTA partition found";
      Serial.println("OTA: no OTA partition found");
      otaInProgress = false;
      return;
    }
    Serial.printf("OTA: firmware upload started, partition size: %u bytes\n", partition->size);

    if (!Update.begin(partition->size)) {
      otaError = "OTA begin failed: " + String(Update.errorString());
      Serial.printf("OTA: begin failed: %s\n", otaError.c_str());
      otaInProgress = false;
      return;
    }

    if (server.hasHeader("X-MD5")) {
      String md5 = server.header("X-MD5");
      if (md5.length() == 32) {
        Update.setMD5(md5.c_str());
        Serial.printf("OTA: MD5 checksum set: %s\n", md5.c_str());
      }
    }

  } else if (upload.status == UPLOAD_FILE_WRITE) {
    if (!otaInProgress) return;

    // Validate ESP32 magic byte on first chunk
    if (otaFirstChunk && upload.currentSize > 0) {
      otaFirstChunk = false;
      if (upload.buf[0] != 0xE9) {
        otaError = "Invalid firmware file";
        Update.abort();
        otaInProgress = false;
        return;
      }
    }

    if (otaShaActive &&
        mbedtls_sha256_update_ret(&otaShaCtx, upload.buf, upload.currentSize) != 0) {
      otaError = "SHA-256 verification failed while reading the upload.";
      Update.abort();
      resetOtaSha();
      otaInProgress = false;
      return;
    }

    manualOtaBytes += upload.currentSize;
    if (Update.write(upload.buf, upload.currentSize) != upload.currentSize) {
      otaError = Update.errorString();
      if (Update.getError() == UPDATE_ERROR_SPACE && isUnderPartitioned())
        otaError += REPARTITION_HINT;
      Update.abort();
      otaInProgress = false;
    }

  } else if (upload.status == UPLOAD_FILE_END) {
    manualOtaPhase = "verifying";
    manualOtaMessage = "Verifying firmware integrity";
    if (!otaInProgress) {
      resetOtaSha();
      return;
    }

    uint8_t actualSha[32] = {};
    if (!otaShaActive || !otaShaExpectedValid ||
        mbedtls_sha256_finish_ret(&otaShaCtx, actualSha) != 0) {
      otaError = "Could not finalize SHA-256 verification.";
      Update.abort();
      resetOtaSha();
      otaInProgress = false;
      return;
    }
    mbedtls_sha256_free(&otaShaCtx);
    otaShaActive = false;

    if (memcmp(actualSha, otaShaExpected, sizeof(actualSha)) != 0) {
      otaError = "Firmware SHA-256 mismatch. Flash was aborted before activation.";
      Update.abort();
      resetOtaSha();
      otaInProgress = false;
      return;
    }
    resetOtaSha();

    if (Update.end(true)) {
      Serial.printf("OTA: success, %u bytes\n", upload.totalSize);
    } else {
      otaError = Update.errorString();
      if (Update.getError() == UPDATE_ERROR_SPACE && isUnderPartitioned())
        otaError += REPARTITION_HINT;
      Serial.printf("OTA: end failed: %s\n", otaError.c_str());
    }
    otaInProgress = false;

  } else if (upload.status == UPLOAD_FILE_ABORTED) {
    Update.abort();
    resetOtaSha();
    otaInProgress = false;
    manualOtaPhase = "error";
    manualOtaMessage = "Firmware upload was aborted";
    // Client dropped the connection: handleOtaFinish() never runs for this
    // request, so request the MQTT re-init here.
    otaMqttReinitPending = true;
    Serial.println("OTA: aborted");
  }
}

static void handleManualOtaStatus() {
  JsonDocument doc;
  doc["phase"] = manualOtaPhase;
  doc["message"] = manualOtaMessage;
  doc["inProgress"] = otaInProgress;
  doc["bytes"] = (uint32_t)manualOtaBytes;
  String json;
  serializeJson(doc, json);
  server.sendHeader("Cache-Control", "no-store");
  server.send(200, "application/json", json);
}

static void handleOtaFinish() {
  if (otaError.length() > 0) {
    manualOtaPhase = "error";
    manualOtaMessage = otaError;
    String msg = "{\"status\":\"error\",\"phase\":\"error\",\"message\":\"" + otaError + "\"}";
    server.sendHeader("Cache-Control", "no-store");
    server.send(400, "application/json", msg);
    otaError = "";
    otaMqttReinitPending = true;  // failed update means no reboot - restore MQTT
    return;
  }

  // The image has passed SHA-256 validation and Update.end(true). Keep the
  // device alive long enough for the HTTP success response to leave the TCP
  // stack before restarting. Browser-side recovery still tolerates a transport
  // drop here, but a normal OTA should receive this definitive acceptance.
  manualOtaPhase = "accepted";
  manualOtaMessage = "Firmware accepted. Restarting";
  for (uint8_t i = 0; i < MAX_PRINTERS; ++i) {
    savePrinterConfig(i);
  }
  Serial.println("OTA: printer configuration flushed to NVS before candidate reboot");
  recoveryArmCandidateBoot();
  server.sendHeader("Cache-Control", "no-store");
  server.sendHeader("Connection", "close");
  server.send(200, "application/json",
    "{\"status\":\"ok\",\"phase\":\"accepted\",\"message\":\"Firmware verified and accepted. Restarting...\",\"rebootInMs\":3500}");
  scheduleRestart(3500);
}


// ---------------------------------------------------------------------------
//  Hardware commissioning health snapshot
// ---------------------------------------------------------------------------
// Deliberately excludes SSID, passwords, access codes, account identity,
// printer serial/name and Cloud tokens. It is safe to attach to a support issue.
static void handleHardwareHealth() {
  uint8_t slot = 0;
  if (server.hasArg("slot")) slot = server.arg("slot").toInt();
  if (slot >= MAX_ACTIVE_PRINTERS) slot = 0;

  JsonDocument doc;

#ifdef BOARD_NAME
  doc["board"] = BOARD_NAME;
#else
  doc["board"] = "unknown";
#endif
#ifdef BOARD_PANEL
  doc["panel"] = BOARD_PANEL;
#else
  doc["panel"] = "unknown";
#endif
#ifdef BOARD_VARIANT
  doc["variant"] = BOARD_VARIANT;
#else
  doc["variant"] = "unknown";
#endif

  doc["width"] = tft.width();
  doc["height"] = tft.height();
  doc["rotation"] = dispSettings.rotation;
  doc["screen"] = (int)getScreenState();

  doc["buttonType"] = (int)buttonType;
  doc["touchscreenConfigured"] = (buttonType == BTN_TOUCHSCREEN);
  doc["pressCount"] = buttonPressCount();

  const bool wifiOk = isWiFiConnected() && !isAPMode();
  doc["wifiConnected"] = wifiOk;
  doc["rssi"] = wifiOk ? WiFi.RSSI() : 0;

  doc["freeHeap"] = ESP.getFreeHeap();
  doc["minFreeHeap"] = ESP.getMinFreeHeap();
#if defined(BOARD_HAS_PSRAM)
  doc["psramSize"] = ESP.getPsramSize();
  doc["freePsram"] = ESP.getFreePsram();
#else
  doc["psramSize"] = 0;
  doc["freePsram"] = 0;
#endif
  doc["uptimeMs"] = millis();

  const bool configured = isPrinterConfigured(slot);
  doc["printerConfigured"] = configured;
  if (configured) {
    const BambuState& st = printers[slot].state;
    doc["printerConnected"] = st.connected;
    doc["dualNozzle"] = st.dualNozzle;
    doc["hasAuxFanRight"] = (st.airductFuncs & (1u << 6)) != 0;
    doc["hasExhaustFan"] = (st.airductFuncs & (1u << 2)) != 0;
    doc["lastUpdateMs"] = st.lastUpdate;
  } else {
    doc["printerConnected"] = false;
    doc["dualNozzle"] = false;
    doc["hasAuxFanRight"] = false;
    doc["hasExhaustFan"] = false;
    doc["lastUpdateMs"] = 0;
  }

  String out;
  serializeJson(doc, out);
  server.sendHeader("Cache-Control", "no-store");
  server.send(200, "application/json", out);
}

// ---------------------------------------------------------------------------
//  OTA rollback - boot the firmware still sitting in the inactive app slot,
//  no re-download involved. Escape hatch for a regressing update.
//
//  Every Arduino-core image carries the lib-builder's app descriptor
//  ("arduino-lib-builder" / "esp-idf: v4.4.7" for every build), so builds are
//  told apart only by the per-build ELF sha256 esptool patches in. The
//  human-readable version comes from the ver_<label> note that
//  recordBootSlotVersion() maintains, trusted only while its sha tag still
//  matches the image actually in the slot.
// ---------------------------------------------------------------------------
static const esp_partition_t* rollbackCandidate(String& fwVersion, const char** reason) {
  *reason = "";
  const esp_partition_t* other = esp_ota_get_next_update_partition(NULL);
  if (!other) { *reason = "this device has no second app slot"; return nullptr; }

  esp_app_desc_t desc;
  if (esp_ota_get_partition_description(other, &desc) != ESP_OK) {
    *reason = "the other app slot is empty"; return nullptr;
  }
  const esp_app_desc_t* run = esp_ota_get_app_description();
  if (strncmp(desc.project_name, run->project_name, sizeof(desc.project_name)) != 0) {
    *reason = "the other app slot holds something else"; return nullptr;
  }
  if (memcmp(desc.app_elf_sha256, run->app_elf_sha256, sizeof(desc.app_elf_sha256)) == 0) {
    *reason = "the other app slot holds this same build"; return nullptr;
  }
  esp_ota_img_states_t st;
  if (esp_ota_get_state_partition(other, &st) != ESP_OK) st = ESP_OTA_IMG_UNDEFINED;
  if (st == ESP_OTA_IMG_INVALID || st == ESP_OTA_IMG_ABORTED) {
    *reason = "the firmware in the other slot previously failed to boot"; return nullptr;
  }

  char note[48];
  if (loadSlotVersionNote(other->label, note, sizeof(note))) {
    char* bar = strchr(note, '|');
    if (bar) {
      char sha8[9];
      snprintf(sha8, sizeof(sha8), "%02x%02x%02x%02x",
               desc.app_elf_sha256[0], desc.app_elf_sha256[1],
               desc.app_elf_sha256[2], desc.app_elf_sha256[3]);
      if (strcmp(bar + 1, sha8) == 0) { *bar = '\0'; fwVersion = note; }
    }
  }
  return other;
}

static void handleOtaSlots() {
  String fw;
  const char* reason;
  const esp_partition_t* other = rollbackCandidate(fw, &reason);
  JsonDocument doc;
  doc["can"] = other != nullptr;
  if (other) { if (fw.length() > 0) doc["fw"] = fw; }
  else doc["reason"] = reason;
  String json;
  serializeJson(doc, json);
  server.send(200, "application/json", json);
}

static void handleOtaRollback() {
  String fw;
  const char* reason;
  const esp_partition_t* other = rollbackCandidate(fw, &reason);
  if (!other) {
    String resp = String("{\"status\":\"error\",\"message\":\"Rollback unavailable: ") + reason + ".\"}";
    server.send(200, "application/json", resp);
    return;
  }
  // esp_ota_set_boot_partition() runs a full esp_image_verify() over the
  // target slot before touching otadata, so a damaged or half-written image
  // is refused right here instead of bricking the boot. (Update.canRollBack()
  // only checks the first byte - do not swap this for it.)
  esp_err_t err = esp_ota_set_boot_partition(other);
  if (err != ESP_OK) {
    String resp = String("{\"status\":\"error\",\"message\":\"The other slot's firmware failed verification (") + esp_err_to_name(err) + ").\"}";
    server.send(200, "application/json", resp);
    return;
  }
  Serial.printf("OTA: rollback -> %s (%s)\n", other->label,
                fw.length() > 0 ? fw.c_str() : "unknown version");
  disconnectBambuMqtt();
  server.send(200, "application/json",
    "{\"status\":\"ok\",\"message\":\"Booting the other firmware slot...\"}");
  scheduleRestart(1500);
}


// Smart Home v9.4 independent recovery console.
static bool recoveryMutationAllowed(){return securityAuthorize(server,true);}
static void handleRecoveryPage(){
  String h;h.reserve(7600);
  h+=F("<!doctype html><html><head><meta name='viewport' content='width=device-width,initial-scale=1'><meta name='color-scheme' content='dark'><title>Waveshare Recovery</title><style>body{margin:0;background:#0b1016;color:#eef3f8;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif}.w{max-width:620px;margin:auto;padding:24px}.brand{font-size:24px;font-weight:800}.sub{color:#9aa8b6;margin:6px 0 20px;line-height:1.45}.card{background:#141b23;border:1px solid #2b3743;border-radius:16px;padding:17px;margin:12px 0}.grid{display:grid;grid-template-columns:1fr 1fr;gap:9px}.kv{display:flex;justify-content:space-between;border-bottom:1px solid #25303a;padding:8px 0;gap:14px}.kv span:first-child{color:#91a0ad}button{width:100%;border:1px solid #3a4652;border-radius:10px;background:#202a34;color:#fff;padding:12px;font-weight:700;margin:5px 0}button.primary{border-color:#2f7ddd;background:#17375e}button.danger{border-color:#a34848;background:#4a2020}input[type=file]{width:100%;box-sizing:border-box;background:#0f151c;border:1px solid #36424e;border-radius:9px;padding:12px;color:#fff}#msg{min-height:22px;color:#9aa8b6;margin-top:9px;font-size:13px;white-space:pre-wrap}</style></head><body><div class='w'><div class='brand'>Waveshare Recovery</div><div class='sub'>Workshop OS independent recovery plane. On normal LAN, access uses your portal-code session; deliberate Recovery Safe Mode AP remains independently accessible.</div><div class='card'><div id='status'>Loading...</div></div><div class='card'><b>Recovery actions</b><div class='grid'><button onclick=\"act('/recovery/touch')\">Force Touchscreen ON</button><button onclick=\"act('/recovery/reboot')\">Reboot Normally</button><button class='primary' onclick=\"act('/recovery/safe')\">Reboot to Safe Mode</button><button class='primary' onclick=\"act('/recovery/rollback')\">Boot Previous Firmware</button><button onclick=\"act('/recovery/reset-ui')\">Reset Display UI</button><button onclick=\"act('/recovery/reset-auth')\">Reset Portal Session</button><a href='/settings/export'>Download Settings Backup</a><button class='danger' onclick=\"wifiReset()\">Reset Wi-Fi Only</button><button class='danger' onclick=\"factoryReset()\">Factory Reset</button></div></div><div class='card'><b>Application firmware recovery</b><p class='sub'>Use <b>WaveshareHome-firmware.bin</b> only. Never use Full.bin here.</p><input id='fw' type='file' accept='.bin'><button class='primary' onclick='uploadFw()'>Upload & Install</button><div id='msg'></div></div></div><script>function esc(s){return String(s==null?'':s).replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]))}function refresh(){fetch('/recovery/status?_='+Date.now(),{cache:'no-store'}).then(r=>r.json()).then(d=>{var rows=[['Build',d.build],['Mode',d.safeMode?'SAFE MODE':'Normal'],['Auth',d.authMode==='portal-code'?'ON · PORTAL CODE':(d.authMode||'UNKNOWN')],['Web control plane',d.webReady?'READY':'STARTING'],['IP',d.ip],['Touch',d.touch],['Touch health',d.touchResponsive===undefined?'—':(d.touchResponsive?'RESPONDING':'NO RECENT POLL')],['Touch presses',d.touchPresses===undefined?'—':d.touchPresses],['Touch read failures',d.touchReadFailures===undefined?'—':d.touchReadFailures],['Touch recoveries',d.touchRecoveries===undefined?'—':d.touchRecoveries],['Running slot',d.runningSlot],['Known good',d.knownGood||'—'],['Fallback',d.fallback||'—'],['Candidate OTA',d.candidatePending?('pending · attempt '+d.candidateAttempts):'healthy'],['Rapid-reset count',d.rapidBootCount]];document.getElementById('status').innerHTML=rows.map(x=>'<div class=kv><span>'+esc(x[0])+'</span><b>'+esc(x[1])+'</b></div>').join('')}).catch(()=>document.getElementById('status').textContent='Status unavailable')}function act(u){var m=document.getElementById('msg');m.textContent='Working...';fetch(u,{method:'POST'}).then(r=>r.json()).then(d=>{m.textContent=d.message||d.status||'OK';setTimeout(refresh,400)}).catch(e=>m.textContent='Request failed: '+e)}function wifiReset(){if(confirm('Clear saved Wi-Fi and restart into Safe Mode? Printer settings are preserved.'))act('/recovery/reset-wifi')}function factoryReset(){if(confirm('Factory reset ALL settings?'))act('/reset')}function recoverySha256HexArrayBuffer(buffer){var bytes=new Uint8Array(buffer),bitLen=bytes.length*8,total=((bytes.length+9+63)>>6)<<6,data=new Uint8Array(total);data.set(bytes);data[bytes.length]=0x80;var view=new DataView(data.buffer);view.setUint32(total-8,Math.floor(bitLen/4294967296),false);view.setUint32(total-4,bitLen>>>0,false);var K=[0x428a2f98,0x71374491,0xb5c0fbcf,0xe9b5dba5,0x3956c25b,0x59f111f1,0x923f82a4,0xab1c5ed5,0xd807aa98,0x12835b01,0x243185be,0x550c7dc3,0x72be5d74,0x80deb1fe,0x9bdc06a7,0xc19bf174,0xe49b69c1,0xefbe4786,0x0fc19dc6,0x240ca1cc,0x2de92c6f,0x4a7484aa,0x5cb0a9dc,0x76f988da,0x983e5152,0xa831c66d,0xb00327c8,0xbf597fc7,0xc6e00bf3,0xd5a79147,0x06ca6351,0x14292967,0x27b70a85,0x2e1b2138,0x4d2c6dfc,0x53380d13,0x650a7354,0x766a0abb,0x81c2c92e,0x92722c85,0xa2bfe8a1,0xa81a664b,0xc24b8b70,0xc76c51a3,0xd192e819,0xd6990624,0xf40e3585,0x106aa070,0x19a4c116,0x1e376c08,0x2748774c,0x34b0bcb5,0x391c0cb3,0x4ed8aa4a,0x5b9cca4f,0x682e6ff3,0x748f82ee,0x78a5636f,0x84c87814,0x8cc70208,0x90befffa,0xa4506ceb,0xbef9a3f7,0xc67178f2],H=[0x6a09e667,0xbb67ae85,0x3c6ef372,0xa54ff53a,0x510e527f,0x9b05688c,0x1f83d9ab,0x5be0cd19],W=new Uint32Array(64);function rotr(x,n){return (x>>>n)|(x<<(32-n))}for(var off=0;off<total;off+=64){var i;for(i=0;i<16;i++)W[i]=view.getUint32(off+i*4,false);for(i=16;i<64;i++){var q=W[i-15],r=W[i-2],s0=(rotr(q,7)^rotr(q,18)^(q>>>3))>>>0,s1=(rotr(r,17)^rotr(r,19)^(r>>>10))>>>0;W[i]=(W[i-16]+s0+W[i-7]+s1)>>>0}var a=H[0],b=H[1],c=H[2],d=H[3],e=H[4],f=H[5],g=H[6],h=H[7];for(i=0;i<64;i++){var S1=(rotr(e,6)^rotr(e,11)^rotr(e,25))>>>0,ch=((e&f)^((~e)&g))>>>0,t1=(h+S1+ch+K[i]+W[i])>>>0,S0=(rotr(a,2)^rotr(a,13)^rotr(a,22))>>>0,maj=((a&b)^(a&c)^(b&c))>>>0,t2=(S0+maj)>>>0;h=g;g=f;f=e;e=(d+t1)>>>0;d=c;c=b;b=a;a=(t1+t2)>>>0}H[0]=(H[0]+a)>>>0;H[1]=(H[1]+b)>>>0;H[2]=(H[2]+c)>>>0;H[3]=(H[3]+d)>>>0;H[4]=(H[4]+e)>>>0;H[5]=(H[5]+f)>>>0;H[6]=(H[6]+g)>>>0;H[7]=(H[7]+h)>>>0}return H.map(function(v){return v.toString(16).padStart(8,'0')}).join('')}async function uploadFw(){var f=document.getElementById('fw').files[0],m=document.getElementById('msg');if(!f){m.textContent='Choose WaveshareHome-firmware.bin first';return}if(f.name.toLowerCase().indexOf('full.bin')>=0){m.textContent='Rejected: Full.bin is not application firmware';return}m.textContent='Hashing...';var buf,hex;try{buf=await f.arrayBuffer();hex=recoverySha256HexArrayBuffer(buf)}catch(e){m.textContent='Hashing failed: '+(e&&e.message?e.message:e);return}var fd=new FormData();fd.append('file',f,f.name);var x=new XMLHttpRequest();x.open('POST','/ota/upload',true);x.withCredentials=true;x.timeout=180000;x.setRequestHeader('X-SHA256',hex);x.upload.onprogress=e=>{if(e.lengthComputable)m.textContent='Uploading '+Math.floor(e.loaded*100/e.total)+'%'};x.onload=()=>{try{var d=JSON.parse(x.responseText);m.textContent=d.message||x.responseText}catch(e){m.textContent=x.responseText||'Upload complete'}};x.onerror=()=>m.textContent='Device may be rebooting. Reconnect and reopen /recovery.';x.send(fd)}refresh();setInterval(refresh,5000)</script></body></html>");
  server.sendHeader("Cache-Control","no-store");server.send(200,"text/html",h);
}
static void handleRecoveryStatus(){
  JsonDocument d;
  const bool ap=isAPMode();
  const bool stationConnected=WiFi.status()==WL_CONNECTED;
  d["build"]=SMART_HOME_BUILD_LABEL;
  d["safeMode"]=recoverySafeModeActive();
  d["authMode"]=ap?(recoverySafeModeActive()?"recovery-safe-mode":"setup-ap"):WORKSHOP_OS_AUTH_MODE;
  d["apMode"]=ap;
  d["stationConnected"]=stationConnected;
  d["stationIp"]=stationConnected?WiFi.localIP().toString():String("");
  d["softApIp"]=ap?WiFi.softAPIP().toString():String("");
  d["ip"]=ap?WiFi.softAPIP().toString():WiFi.localIP().toString();
  d["touch"]=buttonType==BTN_TOUCHSCREEN?"FT6336 · FORCED ON":"NOT READY";
#if defined(USE_FT6336)
  const uint32_t touchLast=buttonTouchLastGoodPollMs();
  d["touchResponsive"]=touchLast>0 && (uint32_t)(millis()-touchLast)<2000;
  d["touchReadFailures"]=buttonTouchReadFailures();
  d["touchRecoveries"]=buttonTouchRecoveryCount();
  d["touchPresses"]=buttonPressCount();
#endif
  d["runningSlot"]=recoveryCurrentSlot();
  d["knownGood"]=recoveryKnownGoodSlot();
  d["fallback"]=recoveryFallbackSlot();
  d["candidatePending"]=recoveryCandidatePending();
  d["candidateAttempts"]=recoveryCandidateAttempts();
  d["webReady"]=recoveryWebReady();
  d["rapidBootCount"]=recoveryRapidBootCount();
  String o;serializeJson(d,o);server.sendHeader("Cache-Control","no-store");server.send(200,"application/json",o);
}
static void handleRecoveryTouch(){if(!recoveryMutationAllowed())return;buttonType=BTN_TOUCHSCREEN;saveButtonSettings();initButton();server.send(200,"application/json","{\"status\":\"ok\",\"message\":\"Touchscreen forced ON and reinitialized.\"}");}
static void handleRecoveryReboot(){if(!recoveryMutationAllowed())return;recoveryClearSafeMode();server.send(200,"application/json","{\"status\":\"ok\",\"message\":\"Restarting normally...\"}");scheduleRestart(900);}
static void handleRecoverySafeMode(){if(!recoveryMutationAllowed())return;recoveryRequestSafeModeNextBoot();server.send(200,"application/json","{\"status\":\"ok\",\"message\":\"Restarting into Recovery Safe Mode...\"}");scheduleRestart(900);}
static void handleRecoveryRollback(){if(!recoveryMutationAllowed())return;String m;if(!recoveryRollbackNow(m)){String o=String("{\"status\":\"error\",\"message\":\"")+m+"\"}";server.send(409,"application/json",o);return;}server.send(200,"application/json","{\"status\":\"ok\",\"message\":\"Previous firmware verified. Restarting...\"}");scheduleRestart(1200);}
static void handleRecoveryResetUi(){if(!recoveryMutationAllowed())return;defaultDisplaySettings(dispSettings);brightness=200;saveSettings();setBacklight(brightness);triggerDisplayTransition();server.send(200,"application/json","{\"status\":\"ok\",\"message\":\"Display/UI reset; printer and Wi-Fi preserved.\"}");}
static void handleRecoveryResetAuth(){if(!recoveryMutationAllowed())return;securityLogout(server);server.send(200,"application/json","{\"status\":\"ok\",\"message\":\"Portal session reset. Sign in again with the current code shown on System.\"}");}
static void handleRecoveryResetWifi(){if(!recoveryMutationAllowed())return;wifiSSID[0]='\0';wifiPass[0]='\0';saveSettings();recoveryRequestSafeModeNextBoot();server.send(200,"application/json","{\"status\":\"ok\",\"message\":\"Wi-Fi cleared. Restarting into Safe Mode; printer settings preserved.\"}");scheduleRestart(900);}
// Captive portal: redirect any unknown request to root
// Android/Samsung check /generate_204 expecting 204 — returning 302 triggers popup.
// Apple checks /hotspot-detect.html — non-"Success" body triggers popup.
// Using 302 + no-cache for all unknown paths ensures popup on all platforms.
static void handleNotFound() {
  if (isAPMode()) {
    server.sendHeader("Cache-Control", "no-cache, no-store, must-revalidate");
    server.sendHeader("Location", recoverySafeModeActive() ? "http://192.168.4.1/recovery" : "http://192.168.4.1/");
    server.send(302, "text/plain", "");
  } else {
    server.send(404, "text/plain", "Not Found");
  }
}

// ---------------------------------------------------------------------------
//  Init & handle
// ---------------------------------------------------------------------------
static void handleCaptiveDetect() {
  server.sendHeader("Cache-Control", "no-cache, no-store, must-revalidate");
  server.sendHeader("Location", recoverySafeModeActive() ? "http://192.168.4.1/recovery" : "http://192.168.4.1/");
  server.send(302, "text/plain", "");
}


// ---------------------------------------------------------------------------
//  Smart Display Platform v6
// ---------------------------------------------------------------------------
static void handleHubConfigGet() {
  const SmartHubConfig& cfg = smartHubGetConfig();
  JsonDocument doc;
  doc["available"] = smartHubAvailable();
  doc["enabled"] = cfg.enabled;
  doc["refreshSeconds"] = cfg.refreshSeconds;
  doc["returnSeconds"] = cfg.returnSeconds;
  doc["customUrl"] = cfg.customUrl;
  doc["customHealthy"] = smartHubCustomHealthy();
  doc["customStatus"] = smartHubCustomStatus();
  String out;
  serializeJson(doc, out);
  server.sendHeader("Cache-Control", "no-store");
  server.send(200, "application/json", out);
}

static void handleHubConfigSave() {
  bool enabled = server.hasArg("enabled") && server.arg("enabled") == "1";
  String url = server.hasArg("url") ? server.arg("url") : "";
  uint16_t refresh = server.hasArg("refresh")
      ? (uint16_t)server.arg("refresh").toInt() : 60;
  uint16_t returnSec = server.hasArg("return")
      ? (uint16_t)server.arg("return").toInt() : 60;

  if (!smartHubAvailable()) {
    server.send(400, "application/json",
                "{\"status\":\"error\",\"message\":\"Smart Display is not available on this board\"}");
    return;
  }

  if (!smartHubSaveConfig(enabled, url.c_str(), refresh, returnSec)) {
    server.send(400, "application/json",
                "{\"status\":\"error\",\"message\":\"Use a blank, http:// or https:// custom endpoint\"}");
    return;
  }
  server.send(200, "application/json", "{\"status\":\"ok\"}");
}

static void handleHubShow() {
  if (!server.hasArg("page") ||
      !smartHubShowPage(server.arg("page").c_str())) {
    server.send(400, "application/json",
                "{\"status\":\"error\",\"message\":\"Unknown or unavailable Smart Display page\"}");
    return;
  }
  server.send(200, "application/json", "{\"status\":\"ok\"}");
}


extern void smartHubReloadExperience();
extern bool smartHubStartWorkshopTimer(uint16_t minutes);
extern void smartHubCancelWorkshopTimer();
extern uint32_t smartHubWorkshopTimerRemaining();
extern bool smartHubWorkshopTimerDone();
extern bool smartHubWorkshopTimerActive();


// ---------------------------------------------------------------------------
// Workshop OS physical-view capture (v11.18)
// ---------------------------------------------------------------------------
extern bool smartHubCapturePrepare(uint16_t* width, uint16_t* height);
extern bool smartHubCaptureRgbRow(uint16_t y, uint8_t* out, size_t outLen);

static void handleHubViews() {
  // Deterministic physical navigation/capture order. These IDs are accepted by
  // /hub/show and are intentionally separate from human-facing labels.
  static const char kCatalog[] = R"json({"version":2,"views":[
    {"id":"home","label":"Home","group":"Primary"},
    {"id":"printer","label":"Printer","group":"Primary"},
    {"id":"workshop","label":"Tools","group":"Primary"},
    {"id":"more","label":"Settings","group":"Primary"},
    {"id":"settings-experience","label":"Display & Appearance","group":"Settings"},
    {"id":"settings-display","label":"Display & Appearance","group":"Settings"},
    {"id":"settings-sounds","label":"Sounds & Alerts","group":"Settings"},
    {"id":"settings-network","label":"Network","group":"Settings"},
    {"id":"settings-printer","label":"Printer & Power","group":"Settings"},
    {"id":"settings-printer-power","label":"Printer & Power","group":"Settings"},
    {"id":"settings-update","label":"Software Update","group":"System"},
    {"id":"system-date-time","label":"Date & Time","group":"System"},
    {"id":"system-update","label":"Software Update","group":"System"},
    {"id":"system-diagnostics","label":"Diagnostics","group":"System"},
    {"id":"custom","label":"Custom","group":"Primary"},
    {"id":"system","label":"System","group":"Primary"},
    {"id":"system-portal","label":"Local Portal","group":"System","sensitive":"portal-code"},
    {"id":"tools","label":"Tools","group":"More"},
    {"id":"display-quick","label":"Display - Quick","group":"Display"},
    {"id":"display-schedule","label":"Display - Schedule","group":"Display"},
    {"id":"display-behavior","label":"Display - Behavior","group":"Display"},
    {"id":"display-visual","label":"Display - Visual","group":"Display"},
    {"id":"display-clock","label":"Display - Clock","group":"Display"},
    {"id":"display-alerts","label":"Display - Alerts","group":"Display"},
    {"id":"display-signals","label":"Display - Signals","group":"Display"},
    {"id":"display-theme","label":"Display - Theme","group":"Display Expert"},
    {"id":"display-gauge-colors","label":"Display - Gauge Colors","group":"Display Expert"},
    {"id":"display-gauge-scales","label":"Display - Gauge Scales","group":"Display Expert"},
    {"id":"display-gauge-behavior","label":"Display - Gauge Behavior","group":"Display Expert"},
    {"id":"display-glow","label":"Display - Glow","group":"Display Expert"},
    {"id":"display-layout","label":"Display - Layout","group":"Display Expert"},
    {"id":"display-extras","label":"Display - Extras","group":"Display Expert"},
    {"id":"system-network","label":"Network Essentials","group":"System"},
    {"id":"system-time-locale","label":"Network - Time & Locale","group":"Network Expert"},
    {"id":"system-network-address","label":"Network - Address Editor","group":"Network Expert"},
    {"id":"system-network-review","label":"Network - Address Review","group":"Network Expert"},
    {"id":"hardware-sound","label":"Hardware - Sound","group":"Hardware"},
    {"id":"hardware-cooldown","label":"Hardware - Cooldown","group":"Hardware"},
    {"id":"hardware-led","label":"Hardware - LED","group":"Hardware"},
    {"id":"hardware-finish","label":"Hardware - Finish","group":"Hardware"},
    {"id":"hardware-error","label":"Hardware - Error","group":"Hardware"},
    {"id":"hardware-power","label":"Hardware - Power","group":"Hardware"},
    {"id":"hardware-auto-off","label":"Hardware - Auto Off","group":"Hardware"}
  ]})json";
  server.sendHeader("Cache-Control", "no-store");
  server.send(200, "application/json", kCatalog);
}

static void handleHubFramePpm() {
  uint16_t w = 0, h = 0;
  if (!smartHubCapturePrepare(&w, &h) || w == 0 || h == 0) {
    server.send(503, "application/json",
                "{\"status\":\"error\",\"message\":\"Physical framebuffer is unavailable\"}");
    return;
  }

  // The validated WS350 landscape framebuffer is 480x320. Keep this bounded
  // so an accidental future geometry change fails closed rather than overruns.
  if (w > 480 || h > 480) {
    server.send(500, "application/json",
                "{\"status\":\"error\",\"message\":\"Unexpected framebuffer geometry\"}");
    return;
  }

  char ppmHeader[40];
  const int headerLen = snprintf(ppmHeader, sizeof(ppmHeader),
                                 "P6\n%u %u\n255\n",
                                 (unsigned)w, (unsigned)h);
  if (headerLen <= 0 || headerLen >= (int)sizeof(ppmHeader)) {
    server.send(500, "application/json", "{\"status\":\"error\"}");
    return;
  }

  const size_t rowBytes = (size_t)w * 3U;
  const size_t totalBytes = (size_t)headerLen + rowBytes * (size_t)h;
  static uint8_t row[480U * 3U];

  server.sendHeader("Cache-Control", "no-store");
  server.sendHeader("X-BambuHelper-Capture", "lcd-framebuffer-rgb888");
  server.sendHeader("X-BambuHelper-Width", String((unsigned)w));
  server.sendHeader("X-BambuHelper-Height", String((unsigned)h));
  server.sendHeader("Content-Disposition", "inline; filename=\"bambuhelper-frame.ppm\"");
  server.setContentLength(totalBytes);
  server.send(200, "image/x-portable-pixmap", "");
  server.sendContent(ppmHeader, (size_t)headerLen);

  for (uint16_t y = 0; y < h; ++y) {
    if (!smartHubCaptureRgbRow(y, row, sizeof(row))) return;
    server.sendContent((const char*)row, rowBytes);
  }
}

static void handleHubTimerStatus(){JsonDocument d;d["active"]=smartHubWorkshopTimerActive();d["done"]=smartHubWorkshopTimerDone();d["remainingSeconds"]=smartHubWorkshopTimerRemaining();String out;serializeJson(d,out);server.sendHeader("Cache-Control","no-store");server.send(200,"application/json",out);}
static void handleHubTimerStart(){uint16_t m=server.hasArg("minutes")?(uint16_t)server.arg("minutes").toInt():0;if(m<1||m>120||!smartHubStartWorkshopTimer(m)){server.send(400,"application/json","{\"status\":\"error\"}");return;}server.send(200,"application/json","{\"status\":\"ok\"}");}
static void handleHubTimerCancel(){smartHubCancelWorkshopTimer();server.send(200,"application/json","{\"status\":\"ok\"}");}

static void handleHubExperienceGet() {
  if(!smartHubAvailable()){server.send(404,"application/json","{\"status\":\"error\",\"message\":\"Workshop experience is available on WS350 only\"}");return;}
  Preferences p; p.begin("smart-hub", true);
  JsonDocument doc;
  doc["accent"] = p.getUChar("accent", 0);
  doc["ambient"] = p.getBool("ambient", true);
  doc["note"] = p.getString("note", "");
  const uint16_t legacyTimer = p.getUShort("timerMin", 10);
  doc["timerMinutes"] = p.getUShort("timer1", legacyTimer);
  JsonArray timerPresets = doc["timerPresets"].to<JsonArray>();
  timerPresets.add(p.getUShort("timer1", legacyTimer));
  timerPresets.add(p.getUShort("timer2", 15));
  timerPresets.add(p.getUShort("timer3", 30));
  timerPresets.add(p.getUShort("timer4", 60));
  p.end();
  doc["eventSounds"] = buzzerSettings.enabled;
  doc["quietStart"] = buzzerSettings.quietStartHour;
  doc["quietEnd"] = buzzerSettings.quietEndHour;
  String out; serializeJson(doc,out);
  server.sendHeader("Cache-Control","no-store");
  server.send(200,"application/json",out);
}

static void handleHubExperienceSave() {
  if(!smartHubAvailable()){server.send(404,"application/json","{\"status\":\"error\",\"message\":\"Workshop experience is available on WS350 only\"}");return;}
  uint8_t accent = server.hasArg("accent") ? (uint8_t)server.arg("accent").toInt() : 0;
  if (accent > 4) accent = 0;
  bool ambient = !server.hasArg("ambient") || server.arg("ambient") == "1";
  String note = server.hasArg("note") ? server.arg("note") : "";
  if (note.length() > 63) note.remove(63);
  uint16_t timerPreset[4] = {5,15,30,60};
  const char* timerArg[4] = {"timer1","timer2","timer3","timer4"};
  for(uint8_t i=0;i<4;i++){
    if(server.hasArg(timerArg[i])) timerPreset[i]=(uint16_t)server.arg(timerArg[i]).toInt();
    else if(i==0 && server.hasArg("timerMinutes")) timerPreset[i]=(uint16_t)server.arg("timerMinutes").toInt();
    if(timerPreset[i]<1)timerPreset[i]=1;if(timerPreset[i]>120)timerPreset[i]=120;
  }
  Preferences p; if(!p.begin("smart-hub", false)){server.send(500,"application/json","{\"status\":\"error\",\"message\":\"Could not open Workshop settings\"}");return;}
  p.putUChar("accent",accent);p.putBool("ambient",ambient);p.putString("note",note);
  p.putUShort("timerMin",timerPreset[0]);p.putUShort("timer1",timerPreset[0]);p.putUShort("timer2",timerPreset[1]);p.putUShort("timer3",timerPreset[2]);p.putUShort("timer4",timerPreset[3]);p.end();
  if(server.hasArg("eventSounds")) buzzerSettings.enabled = server.arg("eventSounds") == "1";
  if(server.hasArg("quietStart")) buzzerSettings.quietStartHour = (uint8_t)constrain(server.arg("quietStart").toInt(),0,23);
  if(server.hasArg("quietEnd")) buzzerSettings.quietEndHour = (uint8_t)constrain(server.arg("quietEnd").toInt(),0,23);
  saveBuzzerSettings();initBuzzer();smartHubReloadExperience();
  server.send(200,"application/json","{\"status\":\"ok\"}");
}



// ---------------------------------------------------------------------------
// Smart Home v8 route-policy wrappers
// ---------------------------------------------------------------------------
#define SECURE_GET(path, handler) \
  server.on(path, HTTP_GET, []() { \
    if (securityAuthorize(server, false)) handler(); \
  })

#define SECURE_POST(path, handler) \
  server.on(path, HTTP_POST, []() { \
    if (securityAuthorize(server, true)) handler(); \
  })

#define SECURE_UPLOAD(path, finishHandler, uploadHandler) \
  server.on(path, HTTP_POST, \
    []() { if (securityAuthorize(server, true)) finishHandler(); }, \
    []() { \
      static bool requestAuthorized = false; \
      HTTPUpload& secureUpload = server.upload(); \
      if (secureUpload.status == UPLOAD_FILE_START) \
        requestAuthorized = securityAuthorize(server, true); \
      if (requestAuthorized) uploadHandler(); \
      if (secureUpload.status == UPLOAD_FILE_END || \
          secureUpload.status == UPLOAD_FILE_ABORTED) \
        requestAuthorized = false; \
    })


// ---------------------------------------------------------------------------
// Smart Home v8.3 RC3 station-mode portal login
// ---------------------------------------------------------------------------

static void sendPortalLoginPage(bool badCode = false) {
  String html;
  html.reserve(3600);
  html += F("<!doctype html><html><head><meta name='viewport' content='width=device-width,initial-scale=1'>"
            "<meta name='color-scheme' content='dark'><title>Workshop OS Secure Sign In</title><style>"
            ":root{color-scheme:dark;--bg:#0b0e10;--surface:#121719;--surface2:#171e20;--line:#2a3436;--text:#f4f7f6;--muted:#98a6a3;--accent:#20b7a8;--danger:#ef7676;}"
            "*{box-sizing:border-box}body{margin:0;min-height:100vh;background:var(--bg);color:var(--text);font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;}"
            ".wrap{max-width:430px;margin:0 auto;padding:40px 22px}.eyebrow{color:var(--accent);font-size:12px;font-weight:800;letter-spacing:.12em;text-transform:uppercase;margin-bottom:10px}"
            ".brand{font-weight:820;font-size:29px;letter-spacing:-.02em;margin-bottom:8px}.sub{color:var(--muted);line-height:1.5;margin-bottom:24px}"
            ".card{background:var(--surface);border:1px solid var(--line);border-radius:18px;padding:22px;box-shadow:0 14px 40px #0008}"
            "label{display:block;font-weight:760;margin-bottom:10px}input{width:100%;min-height:52px;font-size:22px;letter-spacing:.14em;text-transform:uppercase;background:var(--surface2);color:var(--text);border:1px solid #3b494b;border-radius:12px;padding:13px 14px;outline:none}"
            "input:focus-visible{border-color:var(--accent);box-shadow:0 0 0 3px #20b7a833}button{width:100%;min-height:52px;margin-top:16px;border:1px solid #37c9bb;border-radius:12px;padding:13px;background:var(--accent);color:#06110f;font-size:17px;font-weight:850;cursor:pointer}"
            "button:focus-visible{outline:3px solid #8ff4e8;outline-offset:3px}.hint{color:var(--muted);font-size:14px;line-height:1.5;margin-top:16px}.err{background:#351c1f;color:#ffd0d0;border:1px solid #74343b;border-radius:10px;padding:11px 12px;margin-bottom:15px}"
            "@media(prefers-reduced-motion:reduce){*{scroll-behavior:auto!important;transition:none!important}}@media(forced-colors:active){input,button,.card{forced-color-adjust:auto;border:1px solid CanvasText}}"
            "</style></head><body><main class='wrap'><div class='eyebrow'>Secure LAN access</div><div class='brand'>Workshop OS</div>"
            "<div class='sub'>Enter the current portal code shown on the physical System screen. The session is boot-scoped and stays local to this device.</div><div class='card'>");
  if (badCode) html += F("<div class='err' role='alert'>That portal code was not accepted. Check System on the WS350 and try again.</div>");
  html += F("<form method='post' action='/login'><label for='code'>Portal code</label>"
            "<input id='code' name='code' maxlength='10' minlength='10' pattern='[ABCDEFGHJKLMNPQRSTUVWXYZ23456789]{10}' autocomplete='one-time-code' autocapitalize='characters' spellcheck='false' autofocus required>"
            "<button type='submit'>Sign in securely</button></form>"
            "<div class='hint'>The code changes whenever the display reboots. No Bambu account, printer access code, or cloud password is requested here.</div></div></main></body></html>");
  server.sendHeader("Cache-Control", "no-store");
  server.send(badCode ? 401 : 200, "text/html", html);
}

static void handlePortalLoginPage() {
  if (securitySessionValid(server)) {
    server.sendHeader("Location", "/");
    server.send(303, "text/plain", "Already signed in");
    return;
  }
  sendPortalLoginPage(false);
}

static void handlePortalLoginSubmit() {
  if (!server.hasArg("code") || !securityLogin(server, server.arg("code"))) {
    sendPortalLoginPage(true);
    return;
  }
  server.sendHeader("Location", "/");
  server.send(303, "text/plain", "Signed in");
}

static void handlePortalLogout() {
  securityLogout(server);
  server.sendHeader("Location", "/login");
  server.send(303, "text/plain", "Signed out");
}

void initWebServer() {
  securityInit();
  // Login is deliberately public in station mode; every protected route
  // relies on the RAM-only BHSESSION cookie issued here.
  server.on("/login", HTTP_GET, handlePortalLoginPage);
  server.on("/login", HTTP_POST, handlePortalLoginSubmit);
  SECURE_POST("/logout", handlePortalLogout);
  // Captive portal detection endpoints (must be before onNotFound)
  server.on("/generate_204", HTTP_GET, handleCaptiveDetect);        // Android/Samsung
  server.on("/gen_204", HTTP_GET, handleCaptiveDetect);              // Android alt
  server.on("/connecttest.txt", HTTP_GET, handleCaptiveDetect);      // Windows
  server.on("/hotspot-detect.html", HTTP_GET, handleCaptiveDetect);  // Apple
  server.on("/canonical.html", HTTP_GET, handleCaptiveDetect);       // Firefox

  SECURE_GET("/", handleRoot);
  SECURE_POST("/save/wifi", handleSaveWifi);
  SECURE_POST("/save/printer", handleSavePrinter);
  SECURE_POST("/save/gaugelayout", handleSaveGaugeLayout);
  SECURE_POST("/save/rotation", handleSaveRotation);
  SECURE_POST("/save/power", handleSavePower);
  SECURE_GET("/power/config", handleGetPowerConfig);
  SECURE_GET("/power/stats", handleGetPowerStats);
  SECURE_POST("/power/control", handlePowerControl);
  SECURE_POST("/buzzer/test", handleBuzzerTest);
  SECURE_POST("/audio/mic/test", handleAudioMicTest);
  SECURE_POST("/audio/mic/echo", handleAudioMicEcho);
  SECURE_POST("/led/preview", handleLedPreview);
  SECURE_POST("/led/test", handleLedTest);
  SECURE_GET("/printer/config", handlePrinterConfig);
  SECURE_GET("/printer/access-code", handlePrinterAccessCode);
  SECURE_POST("/printer/clear", handleClearPrinter);
  SECURE_POST("/light/config", handleLightConfig);
  SECURE_POST("/light/set", handleLightSet);
  SECURE_POST("/printer/control", handlePrinterControl);
  SECURE_GET("/printer/power/status", handlePrinterPowerStatus);
  SECURE_POST("/printer/power", handlePrinterPower);
  SECURE_POST("/apply", handleApply);
  SECURE_POST("/brightness", handleBrightnessPreview);
  SECURE_GET("/status", handleStatus);
  SECURE_GET("/hub/config", handleHubConfigGet);
  SECURE_POST("/hub/config", handleHubConfigSave);
  SECURE_GET("/hub/experience", handleHubExperienceGet);
  SECURE_POST("/hub/experience", handleHubExperienceSave);
  SECURE_GET("/hub/timer/status", handleHubTimerStatus);
  SECURE_POST("/hub/timer/start", handleHubTimerStart);
  SECURE_POST("/hub/timer/cancel", handleHubTimerCancel);
  SECURE_POST("/hub/show", handleHubShow);
  SECURE_GET("/hub/views", handleHubViews);
  SECURE_GET("/hub/frame.ppm", handleHubFramePpm);
  SECURE_GET("/hardware/health", handleHardwareHealth);
  SECURE_GET("/api/timezones", handleTimezones);
  SECURE_POST("/reset", handleReset);
  SECURE_POST("/reboot", handleReboot);
  SECURE_GET("/debug", handleDebug);
  SECURE_POST("/debug/toggle", handleDebugToggle);
  SECURE_POST("/save/toggle", handleToggleSetting);
  SECURE_POST("/glow/test", handleGlowTest);
  server.on("/app.css", HTTP_GET, handleAppCss);
  server.on("/app.js", HTTP_GET, handleAppJs);
  SECURE_POST("/cloud/logout", handleCloudLogout);
  SECURE_GET("/cloud/printers", handleCloudPrinters);
#if HAS_CLOUD_LOGIN
  SECURE_POST("/cloud/login", handleCloudLoginStart);
  SECURE_POST("/cloud/login/code", handleCloudLoginCode);
  SECURE_GET("/cloud/login/status", handleCloudLoginStatus);
  SECURE_GET("/cloud/login/selftest", handleCloudSelfTest);
#endif
  SECURE_POST("/lan/scan", handleLanScan);
  SECURE_GET("/lan/scan", handleLanScan);
  SECURE_GET("/settings/export", handleSettingsExport);
  SECURE_UPLOAD("/settings/import", handleSettingsImportFinish, handleSettingsImportUpload);
  SECURE_UPLOAD("/ota/upload", handleOtaFinish, handleOtaUpload);
  SECURE_GET("/ota/manual/status", handleManualOtaStatus);
  SECURE_GET("/recovery", handleRecoveryPage);
  server.on("/recovery/status", HTTP_GET, handleRecoveryStatus);
  server.on("/recovery/touch", HTTP_POST, handleRecoveryTouch);
  server.on("/recovery/reboot", HTTP_POST, handleRecoveryReboot);
  server.on("/recovery/safe", HTTP_POST, handleRecoverySafeMode);
  server.on("/recovery/rollback", HTTP_POST, handleRecoveryRollback);
  server.on("/recovery/reset-ui", HTTP_POST, handleRecoveryResetUi);
  server.on("/recovery/reset-auth", HTTP_POST, handleRecoveryResetAuth);
  server.on("/recovery/reset-wifi", HTTP_POST, handleRecoveryResetWifi);
  // Deliberately outside ENABLE_OTA_AUTO: rolling back must work exactly on
  // the boards too constrained for the online-update path.
  SECURE_GET("/ota/slots", handleOtaSlots);
  SECURE_POST("/ota/rollback", handleOtaRollback);
#ifdef ENABLE_OTA_AUTO
  SECURE_POST("/ota/auto", handleOtaAuto);
  SECURE_GET("/ota/status", handleOtaStatus);
#endif
  server.onNotFound([]() { if (securityAuthorize(server, false)) handleNotFound(); });
  const char* requestHeaders[] = {
    "X-MD5",
    "X-SHA256",
    "Origin",
    "Referer",
    "X-BambuHelper-Client",
    "Cookie"
  };
  server.collectHeaders(requestHeaders, sizeof(requestHeaders) / sizeof(requestHeaders[0]));
  server.begin();
  recoveryMarkWebReady();
  Serial.println("Web server started on port 80");
}

void handleWebServer() {
  server.handleClient();

  if (otaMqttReinitPending) {
    bool otaBusy = otaInProgress;
#ifdef ENABLE_OTA_AUTO
    otaBusy = otaBusy || otaAutoInProgress;
#endif
    if (!otaBusy) {
      otaMqttReinitPending = false;
      Serial.println("OTA: update failed/aborted, re-initializing MQTT");
      initBambuMqtt();
    }
  }

  if (pendingRestartAt && millis() >= pendingRestartAt) {
    Serial.println("Deferred restart triggered");
    ESP.restart();
  }
}

// BambuHelper smart display platform evolution v6
