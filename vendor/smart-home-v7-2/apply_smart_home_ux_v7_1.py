#!/usr/bin/env python3
from pathlib import Path
import argparse

class PatchError(RuntimeError):
    pass

def replace_between(text, start, end, replacement, name):
    a = text.find(start)
    if a < 0:
        raise PatchError(f'{name}: start anchor not found')
    b = text.find(end, a)
    if b < 0:
        raise PatchError(f'{name}: end anchor not found')
    return text[:a] + replacement + text[b:]

def replace_once(text, old, new, name):
    n = text.count(old)
    if n != 1:
        raise PatchError(f'{name}: expected exactly 1 match, found {n}')
    return text.replace(old, new, 1)

PAGE_DOTS = r'''static void drawPageDots(uint8_t active) {
  // Keep page position visible but out of the bezel / touch-hint text.
  const int16_t y = tft.height() - 18;
  const int16_t gap = 14;
  const int16_t x0 = 22;
  for (uint8_t i = 0; i < 4; i++) {
    uint16_t c = (i == active)
        ? dispSettings.statusOkColor : dispSettings.trackColor;
    tft.fillCircle(x0 + i * gap, y, i == active ? 3 : 2, c);
  }
}

'''

TAP_HINT = r'''static void drawTapHint(const char* nextPage) {
  char hint[34];
  snprintf(hint, sizeof(hint), "TAP > %s", nextPage ? nextPage : "NEXT");
  setFont(tft, FONT_SMALL);
  tft.setTextDatum(BR_DATUM);
  tft.setTextColor(CLR_TEXT_DIM, dispSettings.bgColor);
  // Keep the footer inside the visible glass instead of riding the bezel.
  tft.drawString(hint, tft.width() - 12, tft.height() - 18);
}

'''

HELPERS = r'''static void formatDuration(uint16_t mins, char* out, size_t len) {
  if (mins == 0) {
    strlcpy(out, "—", len);
    return;
  }
  uint16_t h = mins / 60;
  uint16_t m = mins % 60;
  if (h) snprintf(out, len, "%uh %02um", (unsigned)h, (unsigned)m);
  else snprintf(out, len, "%um", (unsigned)m);
}

static void drawProgressTrack(int16_t x, int16_t y, int16_t w,
                              uint8_t progress) {
  if (progress > 100) progress = 100;
  const int16_t h = 12;
  tft.fillRoundRect(x, y, w, h, 6, dispSettings.trackColor);
  int16_t fillW = (int32_t)(w - 2) * progress / 100;
  if (fillW > 0)
    tft.fillRoundRect(x + 1, y + 1, fillW, h - 2, 5,
                      dispSettings.progress.value);
}

static void drawThermalCard(int16_t x, int16_t y, int16_t w, int16_t h,
                            const char* label, float value, uint16_t accent) {
  char buf[18];
  snprintf(buf, sizeof(buf), "%.0f°", value);
  drawMetricCard(x, y, w, h, label, buf, accent);
}

'''

WORKSHOP = r'''static void drawWorkshop(bool full) {
  (void)full;
  tft.fillScreen(dispSettings.bgColor);
  drawHeader("WORKSHOP", "Printer + AMS", 1);

  if (!isAnyPrinterConfigured()) {
    setFont(tft, FONT_BODY);
    tft.setTextDatum(MC_DATUM);
    tft.setTextColor(CLR_TEXT_DIM, dispSettings.bgColor);
    tft.drawString("Configure a printer to populate Workshop",
                   tft.width() / 2, tft.height() / 2);
    drawTapHint("CUSTOM");
    markFrameDirty();
    g_dirty = false;
    return;
  }

  const PrinterSlot& p = displayedPrinter();
  const BambuState& s = p.state;
  const int16_t W = tft.width();

  // Header block: printer, live state, job, progress and layer count.
  setFont(tft, FONT_BODY);
  tft.setTextDatum(TL_DATUM);
  tft.setTextColor(dispSettings.printerNameColor, dispSettings.bgColor);
  tft.drawString(p.config.name[0] ? p.config.name : "Bambu printer", 14, 44);

  setFont(tft, FONT_SMALL);
  tft.setTextDatum(TR_DATUM);
  tft.setTextColor(s.connected ? dispSettings.statusOkColor : CLR_TEXT_DIM,
                   dispSettings.bgColor);
  tft.drawString(stateText(s), W - 14, 45);

  const char* job = jobDisplayName(s);
  tft.setTextDatum(TL_DATUM);
  tft.setTextColor(CLR_TEXT_DIM, dispSettings.bgColor);
  tft.drawString(job && *job ? job : "No active job", 14, 69);

  char progressText[28];
  snprintf(progressText, sizeof(progressText), "%u%%  ·  L%u/%u",
           (unsigned)s.progress,
           (unsigned)s.layerNum,
           (unsigned)s.totalLayers);
  setFont(tft, FONT_BODY);
  tft.setTextDatum(TR_DATUM);
  tft.setTextColor(dispSettings.progress.value, dispSettings.bgColor);
  tft.drawString(progressText, W - 14, 89);
  drawProgressTrack(14, 111, W - 28, s.progress);

  // AMS zone. One unit gets a roomy, information-rich row; additional units
  // compress cleanly instead of leaving a large dead area on the 320x480 panel.
  uint8_t unitCount = s.ams.present ? s.ams.unitCount : 0;
  if (unitCount > 4) unitCount = 4;
  const int16_t amsTop = 143;
  const int16_t thermalTop = 300;
  const int16_t amsHeight = thermalTop - amsTop - 8;

  if (unitCount == 0) {
    setFont(tft, FONT_BODY);
    tft.setTextDatum(MC_DATUM);
    tft.setTextColor(CLR_TEXT_DIM, dispSettings.bgColor);
    tft.drawString("No AMS data", W / 2, amsTop + 48);
  } else {
    int16_t rowH = amsHeight / unitCount;
    if (rowH > 116) rowH = 116;
    if (rowH < 34) rowH = 34;
    const int16_t areaW = W - 28;
    const int16_t trayGap = 5;
    const int16_t trayW = (areaW - 3 * trayGap) / 4;

    for (uint8_t u = 0; u < unitCount; u++) {
      int16_t rowY = amsTop + u * rowH;
      setFont(tft, FONT_SMALL);
      tft.setTextDatum(TL_DATUM);
      tft.setTextColor(CLR_TEXT_DIM, dispSettings.bgColor);
      char unitLabel[18];
      snprintf(unitLabel, sizeof(unitLabel), "AMS %u", (unsigned)(u + 1));
      tft.drawString(unitLabel, 14, rowY);

      int16_t labelH = rowH >= 58 ? 18 : 12;
      int16_t trayY = rowY + labelH;
      int16_t trayH = rowH - labelH - 4;
      if (trayH > 88) trayH = 88;
      if (trayH < 16) trayH = 16;

      for (uint8_t t = 0; t < 4; t++) {
        uint8_t idx = u * 4 + t;
        const AmsTray& tr = s.ams.trays[idx];
        int16_t x = 14 + t * (trayW + trayGap);
        uint16_t c = tr.present && tr.colorRgb565
            ? tr.colorRgb565 : dispSettings.trackColor;
        tft.fillRoundRect(x, trayY, trayW, trayH, 8,
                          dispSettings.trackColor);
        tft.fillRoundRect(x + 2, trayY + 2, trayW - 4, trayH - 4, 7, c);

        uint8_t r = (c >> 11) & 0x1F;
        uint8_t g = (c >> 5) & 0x3F;
        uint8_t b = c & 0x1F;
        bool light = (r * 2 + g * 3 + b) > 150;
        uint16_t tc = light ? TFT_BLACK : TFT_WHITE;
        tft.setTextColor(tc, c);

        if (tr.present) {
          char remain[10];
          if (tr.remain >= 0)
            snprintf(remain, sizeof(remain), "%d%%", (int)tr.remain);
          else
            strlcpy(remain, "—", sizeof(remain));
          setFont(tft, trayH >= 58 ? FONT_BODY : FONT_SMALL);
          tft.setTextDatum(MC_DATUM);
          tft.drawString(remain, x + trayW / 2,
                         trayY + (trayH >= 58 ? trayH / 2 - 7 : trayH / 2));

          if (trayH >= 58) {
            char typeShort[10] = {};
            if (tr.type[0]) {
              strlcpy(typeShort, tr.type, sizeof(typeShort));
              if (strlen(typeShort) > 8) typeShort[8] = '\0';
            } else {
              strlcpy(typeShort, "FILAMENT", sizeof(typeShort));
            }
            setFont(tft, FONT_SMALL);
            tft.setTextDatum(BC_DATUM);
            tft.drawString(typeShort, x + trayW / 2, trayY + trayH - 7);
          }
        } else {
          setFont(tft, FONT_SMALL);
          tft.setTextDatum(MC_DATUM);
          tft.drawString("EMPTY", x + trayW / 2, trayY + trayH / 2);
        }
      }
    }
  }

  // Thermal telemetry gets dedicated cards instead of a clipped footer string.
  const int16_t gap = 8;
  const int16_t margin = 14;
  const int16_t cardW = (W - margin * 2 - gap) / 2;
  const int16_t cardH = 62;
  if (s.dualNozzle) {
    drawThermalCard(margin, thermalTop, cardW, cardH,
                    "NOZZLE L", s.nozzleTempN[1], dispSettings.nozzle.value);
    drawThermalCard(margin + cardW + gap, thermalTop, cardW, cardH,
                    "NOZZLE R", s.nozzleTempN[0], dispSettings.nozzle.value);
  } else {
    drawThermalCard(margin, thermalTop, cardW, cardH,
                    "NOZZLE", s.nozzleTemp, dispSettings.nozzle.value);
    char remain[18];
    formatDuration(s.remainingMinutes, remain, sizeof(remain));
    drawMetricCard(margin + cardW + gap, thermalTop, cardW, cardH,
                   "REMAINING", remain, dispSettings.etaColor);
  }
  drawThermalCard(margin, thermalTop + cardH + gap, cardW, cardH,
                  "BED", s.bedTemp, dispSettings.bed.value);
  drawThermalCard(margin + cardW + gap, thermalTop + cardH + gap,
                  cardW, cardH, "CHAMBER", s.chamberTemp,
                  dispSettings.chamberTemp.value);

  drawTapHint("CUSTOM");
  markFrameDirty();
  g_dirty = false;
}

'''

SYSTEM = r'''static void drawSystem(bool full) {
  static unsigned long lastDraw = 0;
  if (!full && !g_dirty && millis() - lastDraw < 1000) return;
  lastDraw = millis();

  tft.fillScreen(dispSettings.bgColor);
  drawHeader("SYSTEM", "Smart Home v7.1", 3);

  char wifi[24];
  if (WiFi.status() == WL_CONNECTED)
    snprintf(wifi, sizeof(wifi), "%d dBm", WiFi.RSSI());
  else
    strlcpy(wifi, "Offline", sizeof(wifi));

  char heap[24];
  snprintf(heap, sizeof(heap), "%u KB",
           (unsigned)(ESP.getFreeHeap() / 1024));

  char psram[24];
  snprintf(psram, sizeof(psram), "%u KB",
           (unsigned)(ESP.getFreePsram() / 1024));

  unsigned long sec = millis() / 1000UL;
  unsigned long hours = sec / 3600UL;
  unsigned long mins = (sec / 60UL) % 60UL;
  char uptime[24];
  snprintf(uptime, sizeof(uptime), "%luh %02lum", hours, mins);

  const int16_t gap = 10;
  const int16_t margin = 16;
  const int16_t cardW = (tft.width() - margin * 2 - gap) / 2;
  const int16_t cardH = 82;
  drawMetricCard(margin, 58, cardW, cardH,
                 "WIFI", wifi, dispSettings.statusOkColor);
  drawMetricCard(margin + cardW + gap, 58, cardW, cardH,
                 "UPTIME", uptime, dispSettings.etaColor);
  drawMetricCard(margin, 58 + cardH + gap, cardW, cardH,
                 "FREE HEAP", heap, dispSettings.progress.value);
  drawMetricCard(margin + cardW + gap, 58 + cardH + gap, cardW, cardH,
                 "FREE PSRAM", psram, dispSettings.nozzle.value);

  // Explicitly separate the upstream BambuHelper base version from our custom
  // display release so OTA success is visible without inferring it from pages.
  setFont(tft, FONT_SMALL);
  tft.setTextDatum(TC_DATUM);
  tft.setTextColor(CLR_TEXT, dispSettings.bgColor);
  char ver[40];
  snprintf(ver, sizeof(ver), "BambuHelper %s · ws_lcd_350", FW_VERSION);
  tft.drawString(ver, tft.width() / 2, 252);

  tft.setTextColor(CLR_TEXT_DIM, dispSettings.bgColor);
  String ip = WiFi.status() == WL_CONNECTED
      ? WiFi.localIP().toString() : String("No IP");
  tft.drawString(ip, tft.width() / 2, 278);
  drawTapHint("PRINTER");

  markFrameDirty();
  g_dirty = false;
}

'''

def apply(repo: Path):
    p = repo / 'src' / 'smart_hub.cpp'
    text = p.read_text(encoding='utf-8')
    text = replace_between(text,
        'static void drawPageDots(uint8_t active) {',
        'static void drawHeader(', PAGE_DOTS + 'static void drawHeader(',
        'page dots')
    text = replace_between(text,
        'static void drawTapHint(const char* nextPage) {',
        'static void drawMetricCard(', TAP_HINT + 'static void drawMetricCard(',
        'tap hint')
    text = text.replace('static void drawHeader(static void drawHeader(', 'static void drawHeader(', 1)
    text = text.replace('static void drawMetricCard(static void drawMetricCard(', 'static void drawMetricCard(', 1)

    old_fmt_start = 'static void formatDuration(uint16_t mins, char* out, size_t len) {'
    home_start = 'static void drawHome(bool full) {'
    text = replace_between(text, old_fmt_start, home_start,
                           HELPERS + home_start, 'helpers')
    text = text.replace(home_start + home_start, home_start, 1)

    text = replace_once(text,
        'drawHeader("HOME", "Smart Display", 0);',
        'drawHeader("HOME", "Smart Home v7.1", 0);',
        'home build identity')

    text = replace_between(text,
        'static void drawWorkshop(bool full) {',
        'static void drawCustom(bool full) {',
        WORKSHOP + 'static void drawCustom(bool full) {',
        'workshop')
    text = text.replace('static void drawCustom(bool full) {static void drawCustom(bool full) {',
                        'static void drawCustom(bool full) {', 1)

    text = replace_between(text,
        'static void drawSystem(bool full) {',
        '} // namespace',
        SYSTEM + '} // namespace',
        'system')
    text = text.replace('} // namespace} // namespace', '} // namespace', 1)

    if '// BambuHelper smart home UX evolution v7.1' not in text:
        text += '\n// BambuHelper smart home UX evolution v7.1\n'
    p.write_text(text, encoding='utf-8')

    checks = [
        'Smart Home v7.1',
        'drawProgressTrack',
        'NOZZLE L',
        'CHAMBER',
        'tr.type',
        'BambuHelper %s · ws_lcd_350',
        'tft.height() - 18',
    ]
    out = p.read_text(encoding='utf-8')
    for c in checks:
        if c not in out:
            raise PatchError(f'contract missing: {c}')

if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--repo', required=True)
    ap.add_argument('--apply', action='store_true')
    args = ap.parse_args()
    if not args.apply:
        raise SystemExit('use --apply')
    apply(Path(args.repo))
    print('Smart Home v7.1 UX patch applied')
