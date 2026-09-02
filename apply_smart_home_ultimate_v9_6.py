#!/usr/bin/env python3
from pathlib import Path
import argparse

class PatchError(RuntimeError):
    pass

def replace_once(text, old, new, label):
    n=text.count(old)
    if n!=1:
        raise PatchError(f"{label}: expected 1 match, found {n}")
    return text.replace(old,new,1)

def replace_between(text,start,end,repl,label):
    a=text.find(start)
    if a<0: raise PatchError(f"{label}: start anchor not found")
    b=text.find(end,a)
    if b<0: raise PatchError(f"{label}: end anchor not found")
    return text[:a]+repl+text[b:]

AMBIENT = r'''
static bool g_ambientHome = false;

static uint32_t v96Mix(uint32_t h, uint32_t v) {
  h ^= v + 0x9e3779b9u + (h << 6) + (h >> 2);
  return h;
}

static uint32_t v96PrinterSignature(const BambuState& s) {
  uint32_t h=0x56393650u;
  h=v96Mix(h,s.connected?1u:0u); h=v96Mix(h,(uint32_t)s.gcodeStateId); h=v96Mix(h,(uint32_t)s.progress);
  h=v96Mix(h,(uint32_t)s.remainingMinutes); h=v96Mix(h,((uint32_t)s.layerNum<<16)|(uint32_t)s.totalLayers);
  h=v96Mix(h,(uint32_t)((int)s.nozzleTemp+200)); h=v96Mix(h,(uint32_t)((int)s.bedTemp+200));
  h=v96Mix(h,(uint32_t)((int)s.wifiSignal+128)); h=v96Mix(h,uiAmsSignature(s));
  return h;
}

static bool uiLocalTime(struct tm& out) {
  time_t now = time(nullptr);
  if (now < 1700000000) return false;
  localtime_r(&now, &out);
  return true;
}

static uint32_t uiAmbientSignature() {
  uint32_t h = 0x414D4236u;
  struct tm t = {};
  if (uiLocalTime(t)) h = v96Mix(h, (uint32_t)(t.tm_yday * 1440 + t.tm_hour * 60 + t.tm_min));
  h = v96Mix(h, WiFi.status() == WL_CONNECTED ? (uint32_t)((WiFi.RSSI() + 128) / 5) : 0u);
  if (isAnyPrinterConfigured()) h = v96Mix(h, v96PrinterSignature(displayedPrinter().state));
  return h;
}

static void uiAmbientOrb(int16_t cx, int16_t cy, uint16_t accent) {
  for (int16_t r = 42; r >= 18; r -= 8) {
    uint16_t c = r == 18 ? accent : (r == 26 ? UI_BORDER : UI_PANEL_2);
    tft.drawCircle(cx, cy, r, c);
  }
  tft.fillCircle(cx, cy, 7, accent);
}

static void drawAmbientHome(bool full) {
  static bool initialized = false;
  static uint32_t prevSig = 0xffffffffu;
  const uint32_t sig = uiAmbientSignature();
  if (!full && initialized && !g_dirty && sig == prevSig) return;
  const bool first = full || !initialized;
  const int16_t W = tft.width();
  bool painted = false;

  if (first) {
    tft.fillScreen(UI_BG);
    initialized = true;
    prevSig = 0xffffffffu;
    tft.fillRoundRect(12, 12, W - 24, 3, 2, UI_ORANGE);
    setFont(tft, FONT_SMALL);
    tft.setTextDatum(TL_DATUM);
    tft.setTextColor(UI_MUTED, UI_BG);
    tft.drawString("WAVESHARE HOME", 16, 24);
    tft.setTextDatum(TR_DATUM);
    tft.drawString("AMBIENT", W - 16, 24);
    setFont(tft, FONT_SMALL);
    tft.setTextDatum(BC_DATUM);
    tft.setTextColor(UI_MUTED, UI_BG);
    tft.drawString("tap to wake  •  local-first", W / 2, 466);
    painted = true;
  }

  struct tm lt = {};
  const bool clockOk = uiLocalTime(lt);
  char clock[12] = "--:--";
  char date[32] = "LOCAL DEVICE";
  if (clockOk) {
    strftime(clock, sizeof(clock), "%l:%M", &lt);
    if (clock[0] == ' ') memmove(clock, clock + 1, strlen(clock));
    strftime(date, sizeof(date), "%a • %b %e", &lt);
  }
  tft.fillRect(10, 48, W - 20, 93, UI_BG);
  setFont(tft, FONT_LARGE);
  tft.setTextDatum(MC_DATUM);
  tft.setTextColor(UI_TEXT, UI_BG);
  tft.drawString(clock, W / 2, 86);
  setFont(tft, FONT_BODY);
  tft.setTextColor(UI_DIM, UI_BG);
  tft.drawString(date, W / 2, 126);
  painted = true;

  if (isAnyPrinterConfigured()) {
    const PrinterSlot& p = displayedPrinter();
    const BambuState& s = p.state;
    const uint16_t accent = uiStateColor(s);
    uiCard(10, 151, W - 20, 170, accent, true);
    uiAmbientOrb(65, 216, accent);
    setFont(tft, FONT_BODY);
    tft.setTextDatum(TL_DATUM);
    tft.setTextColor(UI_TEXT, UI_PANEL);
    char pname[22]; uiCopyShort(pname, sizeof(pname), p.config.name[0] ? p.config.name : "Bambu printer", 18);
    tft.drawString(pname, 122, 166);
    uiPill(122, 191, 108, stateText(s), accent);
    char job[28]; uiCopyShort(job, sizeof(job), jobDisplayName(s), 24);
    setFont(tft, FONT_SMALL); tft.setTextColor(UI_DIM, UI_PANEL);
    tft.drawString(job[0] ? job : "Ready for the next print", 122, 220);
    char pct[12]; snprintf(pct, sizeof(pct), "%u%%", (unsigned)s.progress);
    setFont(tft, FONT_LARGE); tft.setTextColor(UI_ORANGE, UI_PANEL);
    tft.drawString(pct, 122, 246);
    char remain[18]; formatDuration(s.remainingMinutes, remain, sizeof(remain));
    setFont(tft, FONT_SMALL); tft.setTextColor(UI_DIM, UI_PANEL);
    char eta[24]; snprintf(eta, sizeof(eta), "ETA %s", remain); tft.drawString(eta, 122, 278);
    uiProgressBar(20, 299, W - 40, s.progress, UI_ORANGE);

    const int16_t gap=7, cw=(W-20-gap*2)/3;
    char b[18];
    snprintf(b,sizeof(b),"%.0f°",s.nozzleTemp); uiMetric(10,332,cw,78,"NOZZLE",b,UI_ORANGE);
    snprintf(b,sizeof(b),"%.0f°",s.bedTemp); uiMetric(10+cw+gap,332,cw,78,"BED",b,UI_AMBER);
    int8_t active=s.ams.activeTray; const AmsTray* tr=(s.ams.present&&active>=0&&active<4)?&s.ams.trays[(uint8_t)active]:nullptr;
    if(tr&&tr->present&&tr->remain>=0) snprintf(b,sizeof(b),"%d%%",(int)tr->remain); else strlcpy(b,"—",sizeof(b));
    uiMetric(10+(cw+gap)*2,332,cw,78,"ACTIVE AMS",b,UI_PURPLE);
  } else {
    uiCard(10, 168, W - 20, 190, UI_BLUE, true);
    uiAmbientOrb(W / 2, 224, WiFi.status()==WL_CONNECTED ? UI_GREEN : UI_AMBER);
    setFont(tft, FONT_LARGE); tft.setTextDatum(MC_DATUM); tft.setTextColor(UI_TEXT,UI_PANEL);
    tft.drawString("WAVESHARE READY",W/2,286);
    setFont(tft,FONT_SMALL); tft.setTextColor(UI_DIM,UI_PANEL);
    String ip=WiFi.status()==WL_CONNECTED?WiFi.localIP().toString():String("Connect WiFi to continue");
    tft.drawString(ip,W/2,321);
  }

  const int rssi=WiFi.status()==WL_CONNECTED?WiFi.RSSI():-100;
  tft.fillRect(12,421,W-24,28,UI_BG);
  char footer[58];
  snprintf(footer,sizeof(footer),"LOCAL • %s • %d dBm • RECOVERY READY",WiFi.status()==WL_CONNECTED?"ONLINE":"OFFLINE",rssi);
  setFont(tft,FONT_SMALL);tft.setTextDatum(MC_DATUM);tft.setTextColor(WiFi.status()==WL_CONNECTED?UI_GREEN:UI_AMBER,UI_BG);tft.drawString(footer,W/2,436);

  prevSig=sig;
  if (painted) markFrameDirty();
  g_dirty=false;
}

'''

CUSTOM_WIDGET = r'''
static uint16_t v96WidgetAccent(const char* name, uint8_t fallback) {
  if(name&&*name){
    if(!strcasecmp(name,"orange"))return UI_ORANGE; if(!strcasecmp(name,"cyan"))return UI_CYAN;
    if(!strcasecmp(name,"green"))return UI_GREEN; if(!strcasecmp(name,"purple"))return UI_PURPLE;
    if(!strcasecmp(name,"blue"))return UI_BLUE; if(!strcasecmp(name,"amber"))return UI_AMBER; if(!strcasecmp(name,"red"))return UI_RED;
  }
  static const uint16_t d[4]={UI_CYAN,UI_ORANGE,UI_GREEN,UI_PURPLE};return d[fallback&3u];
}

static void drawCustomWidget(int16_t x, int16_t y, int16_t w, int16_t h,
                             const HubMetric& m, uint8_t index) {
  const uint16_t accent = v96WidgetAccent(m.accent, index);
  uiCard(x, y, w, h, accent, false);
  setFont(tft, FONT_SMALL);
  tft.setTextDatum(TL_DATUM);
  tft.setTextColor(UI_DIM, UI_PANEL);
  tft.drawString(m.label[0] ? m.label : "WIDGET", x + 13, y + 12);

  if (!strcasecmp(m.type, "gauge") && m.progress >= 0) {
    const uint8_t pct=(uint8_t)(m.progress>100?100:m.progress);
    uiProgressRing(x+w/2,y+55,27,pct,accent);
    char val[18]; uiCopyShort(val,sizeof(val),m.value[0]?m.value:"",14);
    if(val[0]) { setFont(tft,FONT_SMALL);tft.setTextDatum(BC_DATUM);tft.setTextColor(UI_TEXT,UI_PANEL);tft.drawString(val,x+w/2,y+h-8); }
  } else if (!strcasecmp(m.type, "status")) {
    uiPill(x + 12, y + 43, w - 24, m.value[0] ? m.value : "—", accent);
    if(m.detail[0]) { setFont(tft,FONT_SMALL);tft.setTextColor(UI_DIM,UI_PANEL);char d[22];uiCopyShort(d,sizeof(d),m.detail,18);tft.drawString(d,x+13,y+h-18); }
  } else {
    tft.fillCircle(x + w - 23, y + 22, 8, accent);
    tft.fillCircle(x + w - 23, y + 22, 3, UI_PANEL);
    setFont(tft, FONT_LARGE);
    tft.setTextColor(accent, UI_PANEL);
    char val[22]; uiCopyShort(val, sizeof(val), m.value[0] ? m.value : "—", 17);
    tft.drawString(val, x + 13, y + 39);
    if (!strcasecmp(m.type, "progress") && m.progress >= 0) {
      uiProgressBar(x + 13, y + h - 20, w - 26,
                    (uint8_t)(m.progress > 100 ? 100 : m.progress), accent);
    } else if (m.detail[0]) {
      setFont(tft, FONT_SMALL); tft.setTextColor(UI_DIM, UI_PANEL);
      char detail[24]; uiCopyShort(detail, sizeof(detail), m.detail, 20);
      tft.drawString(detail, x + 13, y + h - 18);
    }
  }
}

static uint32_t uiWidgetSignature(const HubMetric& m, uint8_t index) {
  uint32_t h=uiTextSignature(m.label,m.value,m.detail);
  h=(h^uiTextSignature(m.type,m.accent))*16777619u;
  h=(h^(uint16_t)(m.progress+2))*16777619u;
  h=(h^index)*16777619u;
  return h;
}

'''

CUSTOM = r'''static void drawCustom(bool full) {
  static bool initialized=false;
  static bool prevHasUrl=false;
  static uint32_t prevHeaderSig=0xffffffffu;
  static uint32_t prevWidgetSig[4]={0xffffffffu,0xffffffffu,0xffffffffu,0xffffffffu};
  static uint32_t prevFooterSig=0xffffffffu;
  static uint8_t prevProgress=0xff;
  static int16_t prevNozzle=-32768,prevBed=-32768;
  static int8_t prevWifi=127;
  static uint16_t prevUptimeMin=0xffff;
  const bool hasUrl=g_cfg.customUrl[0]!=0;
  const bool layoutReset=full||!initialized||hasUrl!=prevHasUrl;
  bool painted=false;
  const int16_t W=tft.width();
  if(layoutReset){
    tft.fillScreen(UI_BG);drawHeader("CUSTOM",hasUrl?"LIVE WIDGETS":"MY WIDGETS",2);uiBottomNav(2,"SYSTEM");
    initialized=true;prevHasUrl=hasUrl;prevHeaderSig=prevFooterSig=0xffffffffu;
    for(uint8_t i=0;i<4;i++)prevWidgetSig[i]=0xffffffffu;
    prevProgress=0xff;prevNozzle=prevBed=-32768;prevWifi=127;prevUptimeMin=0xffff;painted=true;
  }

  if(!hasUrl){
    const bool configured=isAnyPrinterConfigured(); const BambuState* sp=configured?&displayedPrinter().state:nullptr;
    const uint8_t progress=sp?sp->progress:0; const int16_t nozzle=sp?(int16_t)(sp->nozzleTemp+0.5f):0; const int16_t bed=sp?(int16_t)(sp->bedTemp+0.5f):0;
    const int8_t wifi=WiFi.status()==WL_CONNECTED?WiFi.RSSI():-100; const uint16_t uptimeMin=(uint16_t)(millis()/60000UL);
    if(layoutReset){
      uiCard(8,45,W-16,78,UI_PURPLE,true);setFont(tft,FONT_LARGE);tft.setTextDatum(TL_DATUM);tft.setTextColor(UI_TEXT,UI_PANEL);tft.drawString("MY WIDGETS",20,57);
      setFont(tft,FONT_SMALL);tft.setTextColor(UI_DIM,UI_PANEL);tft.drawString("Live device deck • zero cloud required",20,91);
    }
    const int16_t gap=8,margin=8,cardW=(W-margin*2-gap)/2,cardH=104,top=134;
    if(layoutReset||progress!=prevProgress){char v[16];snprintf(v,sizeof(v),"%u%%",(unsigned)progress);uiMetric(margin,top,cardW,cardH,"PRINT PROGRESS",configured?v:"—",UI_ORANGE,configured?(sp->printing?"active job":"printer ready"):"configure printer");prevProgress=progress;painted=true;}
    if(layoutReset||nozzle!=prevNozzle){char v[16];snprintf(v,sizeof(v),"%d°C",nozzle);uiMetric(margin+cardW+gap,top,cardW,cardH,"NOZZLE",configured?v:"—",UI_CYAN,configured?stateText(*sp):"offline");prevNozzle=nozzle;painted=true;}
    if(layoutReset||bed!=prevBed){char v[16];snprintf(v,sizeof(v),"%d°C",bed);uiMetric(margin,top+cardH+gap,cardW,cardH,"BED",configured?v:"—",UI_AMBER,"live thermal");prevBed=bed;painted=true;}
    if(layoutReset||wifi!=prevWifi||uptimeMin!=prevUptimeMin){char v[18];snprintf(v,sizeof(v),"%d dBm",(int)wifi);char sub[24];snprintf(sub,sizeof(sub),"uptime %uh %02um",(unsigned)(uptimeMin/60),(unsigned)(uptimeMin%60));uiMetric(margin+cardW+gap,top+cardH+gap,cardW,cardH,"DEVICE",WiFi.status()==WL_CONNECTED?v:"Offline",UI_GREEN,sub);prevWifi=wifi;prevUptimeMin=uptimeMin;painted=true;}
    if(layoutReset){uiCard(8,358,W-16,61,UI_BLUE,false);uiSectionLabel(18,367,"WIDGET STUDIO",UI_BLUE);setFont(tft,FONT_SMALL);tft.setTextDatum(TL_DATUM);tft.setTextColor(UI_DIM,UI_PANEL);tft.drawString("Browser Home → Experience Studio",18,394);}
    if(painted)markFrameDirty();g_dirty=false;return;
  }

  if(!g_custom.valid){
    const uint32_t errSig=uiTextSignature(g_custom.message); if(!layoutReset&&!g_dirty&&errSig==prevHeaderSig)return;
    tft.fillRect(0,39,W,tft.height()-82,UI_BG);uiCard(8,45,W-16,374,UI_AMBER,true);tft.fillCircle(W/2,112,32,UI_WARN_BG);tft.drawCircle(W/2,112,32,UI_AMBER);
    setFont(tft,FONT_LARGE);tft.setTextDatum(MC_DATUM);tft.setTextColor(UI_AMBER,UI_WARN_BG);tft.drawString("!",W/2,112);setFont(tft,FONT_BODY);tft.setTextColor(UI_TEXT,UI_PANEL);tft.drawString("CUSTOM FEED OFFLINE",W/2,168);
    setFont(tft,FONT_SMALL);tft.setTextColor(UI_DIM,UI_PANEL);char msg[48];uiCopyShort(msg,sizeof(msg),g_custom.message,42);tft.drawString(msg,W/2,198);tft.drawString("Retrying automatically • local UI stays available",W/2,222);uiPill(96,258,128,"AUTO RETRY",UI_AMBER);
    prevHeaderSig=errSig;painted=true;if(painted)markFrameDirty();g_dirty=false;return;
  }

  const uint32_t headerSig=uiTextSignature(g_custom.title,g_custom.subtitle,g_custom.status);
  if(layoutReset||headerSig!=prevHeaderSig){
    uiCard(8,45,W-16,92,UI_PURPLE,true);setFont(tft,FONT_LARGE);tft.setTextDatum(TL_DATUM);tft.setTextColor(UI_TEXT,UI_PANEL);char title[30];uiCopyShort(title,sizeof(title),g_custom.title,25);tft.drawString(title,20,57);
    setFont(tft,FONT_SMALL);tft.setTextColor(UI_DIM,UI_PANEL);char sub[42];uiCopyShort(sub,sizeof(sub),g_custom.subtitle,38);tft.drawString(sub,20,88);uiPill(218,103,82,g_custom.healthy?"LIVE":"FEED",g_custom.healthy?UI_GREEN:UI_AMBER);prevHeaderSig=headerSig;painted=true;
  }
  const int16_t gap=8,margin=8,cardW=(W-margin*2-gap)/2,cardH=96,top=146; HubMetric empty={}; strlcpy(empty.type,"metric",sizeof(empty.type)); empty.progress=-1;
  for(uint8_t i=0;i<4;i++){
    const HubMetric& m=i<g_custom.metricCount?g_custom.metrics[i]:empty; const uint32_t sig=uiWidgetSignature(m,i);
    if(layoutReset||sig!=prevWidgetSig[i]){int16_t x=margin+(i%2)*(cardW+gap),y=top+(i/2)*(cardH+gap);drawCustomWidget(x,y,cardW,cardH,m,i);prevWidgetSig[i]=sig;painted=true;}
  }
  const char* foot=g_custom.footer[0]?g_custom.footer:g_custom.status; const uint32_t footerSig=uiTextSignature(foot,g_custom.message);
  if(layoutReset||footerSig!=prevFooterSig){
    uiCard(8,354,W-16,65,UI_BLUE,false);uiSectionLabel(18,363,"FEED STATUS",UI_BLUE);setFont(tft,FONT_SMALL);tft.setTextDatum(TL_DATUM);tft.setTextColor(UI_TEXT,UI_PANEL);char footer[48];uiCopyShort(footer,sizeof(footer),foot&&*foot?foot:"Endpoint healthy",42);tft.drawString(footer,18,389);char http[18];snprintf(http,sizeof(http),"HTTP %d",g_custom.httpCode);tft.setTextDatum(TR_DATUM);tft.setTextColor(UI_GREEN,UI_PANEL);tft.drawString(http,W-18,389);prevFooterSig=footerSig;painted=true;
  }
  if(painted)markFrameDirty();g_dirty=false;
}

'''

SYSTEM = r'''static void drawSystem(bool full) {
  static bool initialized=false; static bool prevWifiUp=false; static int prevRssi=999; static uint32_t prevIp=0xffffffffu; static uint16_t prevUptimeMin=0xffff;
  static uint16_t prevFreeHeap=0xffff,prevPsram=0xffff; static unsigned long lastMemorySample=0;
  const bool layoutReset=full||!initialized; bool painted=false; const int16_t W=tft.width();
  if(layoutReset){
    tft.fillScreen(UI_BG);drawHeader("SYSTEM","DEVICE OS",3);uiBottomNav(3,"PRINTER");initialized=true;prevRssi=999;prevIp=0xffffffffu;prevUptimeMin=0xffff;prevFreeHeap=prevPsram=0xffff;lastMemorySample=0;painted=true;
    uiCard(8,143,W-16,78,UI_PURPLE,false);uiShield(30,182,UI_PURPLE);setFont(tft,FONT_SMALL);tft.setTextDatum(TL_DATUM);tft.setTextColor(UI_DIM,UI_PANEL);tft.drawString("LOCAL ACCESS",55,153);
    setFont(tft,FONT_BODY);tft.setTextColor(UI_GREEN,UI_PANEL);tft.drawString("DEVELOPMENT UNLOCKED",55,177);setFont(tft,FONT_SMALL);tft.setTextColor(UI_DIM,UI_PANEL);tft.drawString("Portal auth OFF • recovery remains independent",55,201);
    uiCard(8,350,W-16,81,UI_ORANGE,false);uiSectionLabel(18,359,"RECOVERY FOUNDATION",UI_ORANGE);setFont(tft,FONT_BODY);tft.setTextDatum(TL_DATUM);tft.setTextColor(UI_GREEN,UI_PANEL);tft.drawString("READY",18,383);
    setFont(tft,FONT_SMALL);tft.setTextColor(UI_DIM,UI_PANEL);tft.drawString("/recovery • rollback • settings backup",18,406);tft.setTextDatum(TR_DATUM);tft.setTextColor(UI_ORANGE,UI_PANEL);tft.drawString("RC3",W-18,383);
  }
  const bool wifiUp=WiFi.status()==WL_CONNECTED;const int rssi=wifiUp?WiFi.RSSI():-100;const uint32_t ip=wifiUp?(uint32_t)WiFi.localIP():0;const uint16_t uptimeMin=(uint16_t)(millis()/60000UL);
  if(layoutReset||wifiUp!=prevWifiUp||rssi/4!=prevRssi/4||ip!=prevIp||uptimeMin!=prevUptimeMin){
    uiCard(8,43,W-16,92,wifiUp?UI_GREEN:UI_RED,true);uiWifiGlyph(20,57,rssi);setFont(tft,FONT_BODY);tft.setTextDatum(TL_DATUM);tft.setTextColor(UI_TEXT,UI_PANEL);tft.drawString("WiFi & Network",57,53);uiPill(219,50,81,wifiUp?"CONNECTED":"OFFLINE",wifiUp?UI_GREEN:UI_RED);
    char wifi[24];snprintf(wifi,sizeof(wifi),wifiUp?"%d dBm":"Offline",rssi);setFont(tft,FONT_LARGE);tft.setTextColor(wifiUp?UI_GREEN:UI_RED,UI_PANEL);tft.drawString(wifi,20,87);String ips=wifiUp?WiFi.localIP().toString():String("No IP");setFont(tft,FONT_SMALL);tft.setTextColor(UI_DIM,UI_PANEL);tft.drawString(ips,20,116);char uptime[24];snprintf(uptime,sizeof(uptime),"%uh %02um",(unsigned)(uptimeMin/60),(unsigned)(uptimeMin%60));tft.setTextDatum(TR_DATUM);tft.drawString(uptime,W-20,116);prevWifiUp=wifiUp;prevRssi=rssi;prevIp=ip;prevUptimeMin=uptimeMin;painted=true;
  }
  const unsigned long now=millis(); if(layoutReset||lastMemorySample==0||now-lastMemorySample>=15000UL){
    const uint16_t freeHeap=(uint16_t)(ESP.getFreeHeap()/1024),psram=(uint16_t)(ESP.getFreePsram()/1024); const int16_t gap=8,cw=(W-16-gap)/2;char b[20];
    if(layoutReset||freeHeap!=prevFreeHeap){snprintf(b,sizeof(b),"%u KB",(unsigned)freeHeap);uiMetric(8,231,cw,105,"FREE HEAP",b,UI_CYAN,"runtime headroom");prevFreeHeap=freeHeap;painted=true;}
    if(layoutReset||psram!=prevPsram){snprintf(b,sizeof(b),"%u KB",(unsigned)psram);uiMetric(8+cw+gap,231,cw,105,"PSRAM FREE",b,UI_PURPLE,"display workspace");prevPsram=psram;painted=true;}
    lastMemorySample=now;
  }
  if(painted)markFrameDirty();g_dirty=false;
}

'''

BROWSER = r'''

/* Smart Home v9.6 Ultimate Experience Studio */
var CC_V96_KEY='waveshare_experience_v96';
function ccV96Prefs(){try{return Object.assign({preset:'command',density:'comfortable'},JSON.parse(localStorage.getItem(CC_V96_KEY)||'{}'))}catch(e){return{preset:'command',density:'comfortable'}}}
function ccV96Save(p){try{localStorage.setItem(CC_V96_KEY,JSON.stringify(p))}catch(e){}}
function ccV96ApplyPreset(name){
  var map={command:['live','printer','display','device','quick'],focus:['live','printer'],minimal:['live','device'],care:['device','display','quick']};
  var p=ccWidgetPrefs();p.visible=(map[name]||map.command).slice();ccSaveWidgetPrefs(p);ccApplyWidgetPrefs();
  var x=ccV96Prefs();x.preset=name;ccV96Save(x);ccV96SyncStudio();
}
function ccV96SetDensity(name){var x=ccV96Prefs();x.density=name;ccV96Save(x);var sec=document.getElementById('sec-home');if(sec)sec.classList.toggle('cc-v96-compact',name==='compact');ccV96SyncStudio()}
function ccV96SyncStudio(){var x=ccV96Prefs();document.querySelectorAll('[data-v96-preset]').forEach(function(b){b.classList.toggle('active',b.dataset.v96Preset===x.preset)});document.querySelectorAll('[data-v96-density]').forEach(function(b){b.classList.toggle('active',b.dataset.v96Density===x.density)})}
function ccV96Clock(){var e=document.getElementById('ccV96Clock');if(e)e.textContent=new Date().toLocaleTimeString([],{hour:'numeric',minute:'2-digit'});var d=document.getElementById('ccV96Date');if(d)d.textContent=new Date().toLocaleDateString([],{weekday:'short',month:'short',day:'numeric'})}
function ccV96Install(){
  if(document.getElementById('ccV96Studio'))return;var sec=document.getElementById('sec-home'),hero=sec&&sec.querySelector('.cc-hero-copy');if(!sec||!hero)return;
  var style=document.createElement('style');style.id='ccV96Style';style.textContent='.cc-v96-clock{display:flex;gap:10px;align-items:baseline;margin:10px 0 0}.cc-v96-clock strong{font-size:24px;letter-spacing:-.03em}.cc-v96-clock span{font-size:11px;color:var(--text-dim)}.cc-v96-studio{margin:0 0 16px;padding:16px 18px;border:1px solid var(--line);border-radius:14px;background:linear-gradient(135deg,var(--bg-elev),var(--bg-sub));display:grid;grid-template-columns:1fr auto;gap:16px;align-items:center}.cc-v96-studio h3{margin:4px 0 3px;font-size:15px}.cc-v96-studio p{margin:0;color:var(--text-dim);font-size:11px}.cc-v96-controls{display:flex;gap:6px;flex-wrap:wrap;justify-content:flex-end}.cc-v96-chip{border:1px solid var(--line);background:var(--bg-sub);color:var(--text-mid);border-radius:999px;padding:7px 10px;font-size:11px;cursor:pointer}.cc-v96-chip.active{border-color:var(--accent);color:var(--accent);background:var(--accent-soft)}.cc-v96-compact .cc-panel{padding:13px}.cc-v96-compact .cc-kv{padding:6px 0}.cc-v96-compact .cc-status-card{min-height:78px;padding:12px}.cc-v96-compact .cc-hero{padding:21px}@media(max-width:700px){.cc-v96-studio{grid-template-columns:1fr}.cc-v96-controls{justify-content:flex-start}}';document.head.appendChild(style);
  var clock=document.createElement('div');clock.className='cc-v96-clock';clock.innerHTML='<strong id="ccV96Clock">--:--</strong><span id="ccV96Date">Local device</span>';hero.appendChild(clock);
  var studio=document.createElement('div');studio.id='ccV96Studio';studio.className='cc-v96-studio';studio.innerHTML='<div><span class="cc-label">EXPERIENCE STUDIO</span><h3>Choose how Home behaves</h3><p>Local browser preference. Firmware and recovery settings are untouched.</p></div><div class="cc-v96-controls"><button class="cc-v96-chip" data-v96-preset="command" onclick="ccV96ApplyPreset(\'command\')">Command</button><button class="cc-v96-chip" data-v96-preset="focus" onclick="ccV96ApplyPreset(\'focus\')">Print Focus</button><button class="cc-v96-chip" data-v96-preset="minimal" onclick="ccV96ApplyPreset(\'minimal\')">Minimal</button><button class="cc-v96-chip" data-v96-preset="care" onclick="ccV96ApplyPreset(\'care\')">Device Care</button><button class="cc-v96-chip" data-v96-density="comfortable" onclick="ccV96SetDensity(\'comfortable\')">Comfort</button><button class="cc-v96-chip" data-v96-density="compact" onclick="ccV96SetDensity(\'compact\')">Compact</button></div>';
  var att=document.getElementById('ccAttention');if(att&&att.parentNode)att.parentNode.insertBefore(studio,att);else sec.appendChild(studio);
  var x=ccV96Prefs();ccV96SetDensity(x.density);ccV96Clock();ccV96SyncStudio();setInterval(ccV96Clock,30000);
}
setTimeout(ccV96Install,0);
'''

def patch_hub(repo: Path):
    p=repo/'src'/'smart_hub.cpp';t=p.read_text(encoding='utf-8')
    t=replace_once(t,'''struct HubMetric {
  char label[18];
  char value[28];
};''','''struct HubMetric {
  char label[18];
  char value[28];
  char detail[32];
  char type[12];
  char accent[12];
  int16_t progress;
};''','v9.6 widget model')
    parse_old='''  JsonArray metrics = doc["metrics"].as<JsonArray>();
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
'''
    parse_new='''  JsonArray metrics = doc["widgets"].as<JsonArray>();
  if (metrics.isNull()) metrics = doc["metrics"].as<JsonArray>();
  uint8_t i = 0;
  for (JsonVariant v : metrics) {
    if (i >= 4 || !v.is<JsonObject>()) break;
    JsonObject m = v.as<JsonObject>();
    safeCopy(g_custom.metrics[i].label,sizeof(g_custom.metrics[i].label),m["label"] | "");
    safeCopy(g_custom.metrics[i].value,sizeof(g_custom.metrics[i].value),m["value"] | "");
    safeCopy(g_custom.metrics[i].detail,sizeof(g_custom.metrics[i].detail),m["detail"] | "");
    safeCopy(g_custom.metrics[i].type,sizeof(g_custom.metrics[i].type),m["type"] | "metric");
    safeCopy(g_custom.metrics[i].accent,sizeof(g_custom.metrics[i].accent),m["accent"] | "");
    int progress=m["progress"] | -1; if(progress < -1) progress=-1; if(progress>100)progress=100;
    g_custom.metrics[i].progress=(int16_t)progress; i++;
  }
'''
    t=replace_once(t,parse_old,parse_new,'v9.6 widget parser')
    t=replace_once(t,'static void drawHome(bool full) {',AMBIENT+CUSTOM_WIDGET+'static void drawHome(bool full) {','v9.6 helpers')
    t=replace_once(t,
'''static void drawHome(bool full) {
  static bool initialized = false;''',
'''static void drawHome(bool full) {
  static bool lastAmbient = false;
  static bool ambientKnown = false;
  const bool ambientChanged = !ambientKnown || lastAmbient != g_ambientHome;
  ambientKnown = true;
  lastAmbient = g_ambientHome;
  if (g_ambientHome) {
    drawAmbientHome(full || ambientChanged);
    return;
  }
  full = full || ambientChanged;
  static bool initialized = false;''','home ambient route')
    t=t.replace('drawHeader("HOME", "SMOOTH UI", 0);','drawHeader("HOME", "COMMAND CENTER", 0);',1)
    t=replace_between(t,'static void drawCustom(bool full) {','static void drawSystem(bool full) {',CUSTOM+'static void drawSystem(bool full) {','custom renderer')
    t=t.replace('static void drawSystem(bool full) {static void drawSystem(bool full) {','static void drawSystem(bool full) {',1)
    t=replace_between(t,'static void drawSystem(bool full) {','} // namespace',SYSTEM+'} // namespace','system renderer')
    t=t.replace('} // namespace} // namespace','} // namespace',1)
    t=replace_once(t,
'''void smartHubEnter() {
  if (!g_cfg.enabled) return;
  setPage(SCREEN_HUB_HOME);
}''',
'''void smartHubEnter() {
  if (!g_cfg.enabled) return;
  g_ambientHome = false;
  setPage(SCREEN_HUB_HOME);
}''','interactive home entry')
    t=replace_once(t,
'''  g_userHoldUntilMs = 0;
  g_dirty = true;
  setScreenState(SCREEN_HUB_HOME);
}''',
'''  g_userHoldUntilMs = 0;
  g_ambientHome = true;
  g_dirty = true;
  setScreenState(SCREEN_HUB_HOME);
}''','ambient idle entry')
    t=replace_once(t,
'''void smartHubAdvance() {
  if (!g_cfg.enabled) {''',
'''void smartHubAdvance() {
  if (g_ambientHome && getScreenState() == SCREEN_HUB_HOME) {
    g_ambientHome = false;
    g_dirty = true;
    setScreenState(SCREEN_HUB_HOME);
    return;
  }
  if (!g_cfg.enabled) {''','ambient tap-to-wake')
    t=replace_once(t,
'''void smartHubReturnToPrinter() {
  g_userHoldUntilMs = 0;''',
'''void smartHubReturnToPrinter() {
  g_ambientHome = false;
  g_userHoldUntilMs = 0;''','leave ambient')
    t=replace_once(t,
'''bool smartHubShowPage(const char* pageName) {
  if (!pageName) return false;''',
'''bool smartHubShowPage(const char* pageName) {
  if (!pageName) return false;
  g_ambientHome = false;''','show page interactive')
    marker='// Smart Home v9.6 Ultimate Experience RC1'
    if marker not in t:t+='\n'+marker+'\n'
    for needle in ['drawAmbientHome','g_ambientHome = true','tap to wake','"gauge"','uiWidgetSignature','DEVELOPMENT UNLOCKED','RECOVERY FOUNDATION']:
        if needle not in t:raise PatchError('hub contract missing: '+needle)
    p.write_text(t,encoding='utf-8')

def patch_app(repo: Path):
    p=repo/'web'/'app.js';t=p.read_text(encoding='utf-8')
    if 'Smart Home v9.6 Ultimate Experience Studio' not in t:
        t=replace_once(t,'/* ============ Boot ============ */',BROWSER+'\n/* ============ Boot ============ */','browser studio')
    p.write_text(t,encoding='utf-8')

def apply(repo: Path):
    patch_hub(repo);patch_app(repo)

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--repo',required=True);ap.add_argument('--apply',action='store_true');a=ap.parse_args()
    if not a.apply:raise SystemExit('Pass --apply')
    apply(Path(a.repo));print('Smart Home v9.6 Ultimate Experience RC1 applied')
