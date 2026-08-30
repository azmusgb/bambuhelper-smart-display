#!/usr/bin/env python3
from pathlib import Path
import argparse

WORKSHOP = r'''static void drawWorkshop(bool full) {
  tft.fillScreen(dispSettings.bgColor);
  drawHeader("WORKSHOP", "X2D + AMS", 1);

  if (!isAnyPrinterConfigured()) {
    setFont(tft, FONT_BODY);
    tft.setTextDatum(MC_DATUM);
    tft.setTextColor(CLR_TEXT_DIM, dispSettings.bgColor);
    tft.drawString("Configure a printer to populate Workshop", tft.width() / 2, tft.height() / 2);
    drawTapHint("CUSTOM"); markFrameDirty(); return;
  }

  const PrinterSlot& p = displayedPrinter();
  const BambuState& s = p.state;
  const int16_t W = tft.width();

  setFont(tft, FONT_BODY); tft.setTextDatum(TL_DATUM);
  tft.setTextColor(dispSettings.printerNameColor, dispSettings.bgColor);
  tft.drawString(p.config.name[0] ? p.config.name : "Bambu printer", 12, 43);
  const char* job = jobDisplayName(s);
  setFont(tft, FONT_SMALL); tft.setTextColor(CLR_TEXT_DIM, dispSettings.bgColor);
  tft.drawString(job && *job ? job : "No active job", 12, 67);

  const int16_t sx=12, sy=91, sw=W-24, sh=62;
  tft.fillRoundRect(sx,sy,sw,sh,10,dispSettings.trackColor);
  tft.fillRoundRect(sx+1,sy+1,sw-2,sh-2,9,dispSettings.bgColor);
  char pct[12]; snprintf(pct,sizeof(pct),"%u%%",(unsigned)s.progress);
  setFont(tft,FONT_LARGE); tft.setTextDatum(ML_DATUM);
  tft.setTextColor(dispSettings.progress.value,dispSettings.bgColor);
  tft.drawString(pct,sx+12,sy+23);
  char layer[24]; snprintf(layer,sizeof(layer),"Layer %u / %u",(unsigned)s.layerNum,(unsigned)s.totalLayers);
  setFont(tft,FONT_SMALL); tft.setTextDatum(MR_DATUM); tft.setTextColor(CLR_TEXT,dispSettings.bgColor);
  tft.drawString(layer,sx+sw-12,sy+18);
  char remain[20]; formatDuration(s.remainingMinutes,remain,sizeof(remain));
  char remainLine[32]; snprintf(remainLine,sizeof(remainLine),"%s remaining",remain);
  tft.setTextColor(dispSettings.etaColor,dispSettings.bgColor); tft.drawString(remainLine,sx+sw-12,sy+38);
  const int16_t barX=sx+12, barY=sy+48, barW=sw-24, barH=6;
  tft.fillRoundRect(barX,barY,barW,barH,3,dispSettings.trackColor);
  int16_t fillW=(int16_t)((uint32_t)barW*min((uint8_t)100,s.progress)/100U);
  if(fillW>0) tft.fillRoundRect(barX,barY,fillW,barH,3,dispSettings.progressBarColor);

  uint8_t unitCount=s.ams.present?s.ams.unitCount:0; if(unitCount>AMS_MAX_UNITS) unitCount=AMS_MAX_UNITS;
  uint8_t focusUnit=0; if(s.ams.activeTray<AMS_MAX_TRAYS) focusUnit=s.ams.activeTray/AMS_TRAYS_PER_UNIT;
  if(focusUnit>=unitCount) focusUnit=0;
  const int16_t amsLabelY=166;
  setFont(tft,FONT_SMALL); tft.setTextDatum(TL_DATUM); tft.setTextColor(CLR_TEXT_DIM,dispSettings.bgColor);
  if(unitCount==0) tft.drawString("AMS · no data",12,amsLabelY);
  else { char amsLabel[34]; if(unitCount>1) snprintf(amsLabel,sizeof(amsLabel),"AMS %u of %u",(unsigned)(focusUnit+1),(unsigned)unitCount); else snprintf(amsLabel,sizeof(amsLabel),"AMS 1 · 4 trays"); tft.drawString(amsLabel,12,amsLabelY); }

  const int16_t trayY=184,trayGap=5,trayW=(W-24-trayGap*3)/4,trayH=82;
  for(uint8_t t=0;t<4;t++) {
    int16_t x=12+t*(trayW+trayGap); const AmsTray* trp=nullptr;
    if(unitCount>0) trp=&s.ams.trays[focusUnit*4+t];
    bool present=trp&&trp->present; uint16_t c=present&&trp->colorRgb565?trp->colorRgb565:dispSettings.trackColor;
    tft.fillRoundRect(x,trayY,trayW,trayH,8,dispSettings.trackColor); tft.fillRoundRect(x+2,trayY+2,trayW-4,trayH-4,7,c);
    uint8_t r=(c>>11)&0x1F,g=(c>>5)&0x3F,b=c&0x1F; bool light=(r*2+g*3+b)>150; uint16_t tc=light?TFT_BLACK:TFT_WHITE;
    tft.setTextColor(tc,c); char trayId[8]; snprintf(trayId,sizeof(trayId),"T%u",(unsigned)(t+1));
    setFont(tft,FONT_SMALL); tft.setTextDatum(TC_DATUM); tft.drawString(trayId,x+trayW/2,trayY+7);
    setFont(tft,FONT_BODY); tft.setTextDatum(MC_DATUM); char rem[10]="—";
    if(present&&trp->remain>=0) snprintf(rem,sizeof(rem),"%d%%",(int)trp->remain); tft.drawString(rem,x+trayW/2,trayY+39);
    setFont(tft,FONT_SMALL); tft.setTextDatum(BC_DATUM); const char* type=present&&trp->type[0]?trp->type:"Empty"; char shortType[11]; strlcpy(shortType,type,sizeof(shortType)); tft.drawString(shortType,x+trayW/2,trayY+trayH-7);
    if(s.ams.activeTray==focusUnit*4+t) { tft.drawRoundRect(x,trayY,trayW,trayH,8,dispSettings.statusOkColor); tft.drawRoundRect(x+1,trayY+1,trayW-2,trayH-2,7,dispSettings.statusOkColor); }
  }

  const int16_t gap=8,margin=12,cardW=(W-margin*2-gap)/2,cardH=64,row1=280,row2=352;
  char v1[18],v2[18],v3[18],v4[18];
  if(s.dualNozzle){snprintf(v1,sizeof(v1),"%.0f°",s.nozzleTempN[1]);snprintf(v2,sizeof(v2),"%.0f°",s.nozzleTempN[0]);}
  else{snprintf(v1,sizeof(v1),"%.0f°",s.nozzleTemp);strlcpy(v2,"—",sizeof(v2));}
  snprintf(v3,sizeof(v3),"%.0f°",s.bedTemp); snprintf(v4,sizeof(v4),"%.0f°",s.chamberTemp);
  drawMetricCard(margin,row1,cardW,cardH,s.dualNozzle?"NOZZLE L":"NOZZLE",v1,dispSettings.nozzle.value);
  drawMetricCard(margin+cardW+gap,row1,cardW,cardH,s.dualNozzle?"NOZZLE R":"SECOND NOZZLE",v2,dispSettings.nozzle.value);
  drawMetricCard(margin,row2,cardW,cardH,"BED",v3,dispSettings.bed.value);
  drawMetricCard(margin+cardW+gap,row2,cardW,cardH,"CHAMBER",v4,dispSettings.chamberTemp.value);
  drawTapHint("CUSTOM"); markFrameDirty(); g_dirty=false;
}
'''

SYSTEM = r'''static void drawSystem(bool full) {
  static unsigned long lastDraw=0; if(!full&&!g_dirty&&millis()-lastDraw<1000)return; lastDraw=millis();
  tft.fillScreen(dispSettings.bgColor); drawHeader("SYSTEM","Smart Home 7.1",3);
  char wifi[24]; if(WiFi.status()==WL_CONNECTED) snprintf(wifi,sizeof(wifi),"%d dBm",WiFi.RSSI()); else strlcpy(wifi,"Offline",sizeof(wifi));
  char heap[24]; snprintf(heap,sizeof(heap),"%u KB",(unsigned)(ESP.getFreeHeap()/1024));
  char psram[24]; snprintf(psram,sizeof(psram),"%u KB",(unsigned)(ESP.getFreePsram()/1024));
  unsigned long sec=millis()/1000UL,hours=sec/3600UL,mins=(sec/60UL)%60UL; char uptime[24]; snprintf(uptime,sizeof(uptime),"%luh %02lum",hours,mins);
  const int16_t gap=10,margin=16,cardW=(tft.width()-margin*2-gap)/2,cardH=76;
  drawMetricCard(margin,54,cardW,cardH,"WIFI",wifi,dispSettings.statusOkColor); drawMetricCard(margin+cardW+gap,54,cardW,cardH,"UPTIME",uptime,dispSettings.etaColor);
  drawMetricCard(margin,54+cardH+gap,cardW,cardH,"FREE HEAP",heap,dispSettings.progress.value); drawMetricCard(margin+cardW+gap,54+cardH+gap,cardW,cardH,"FREE PSRAM",psram,dispSettings.nozzle.value);
  const int16_t iy=230,iw=tft.width()-32,ih=108; tft.fillRoundRect(16,iy,iw,ih,10,dispSettings.trackColor); tft.fillRoundRect(17,iy+1,iw-2,ih-2,9,dispSettings.bgColor);
  setFont(tft,FONT_BODY); tft.setTextDatum(TL_DATUM); tft.setTextColor(dispSettings.printerNameColor,dispSettings.bgColor); tft.drawString("Smart Home v7.1",30,iy+16);
  setFont(tft,FONT_SMALL); tft.setTextColor(CLR_TEXT,dispSettings.bgColor); char base[44]; snprintf(base,sizeof(base),"BambuHelper %s · ws_lcd_350",FW_VERSION); tft.drawString(base,30,iy+48);
  tft.setTextColor(CLR_TEXT_DIM,dispSettings.bgColor); tft.drawString("UX build: ux71 · OTA capable",30,iy+72);
  tft.setTextDatum(BC_DATUM); String ip=WiFi.status()==WL_CONNECTED?WiFi.localIP().toString():String("No IP"); tft.drawString(ip,tft.width()/2,367); drawTapHint("PRINTER"); markFrameDirty(); g_dirty=false;
}
'''

def replace_function(text,start_sig,next_sig,replacement):
    start=text.find(start_sig); end=text.find(next_sig,start+1)
    if start<0 or end<0 or end<=start: raise SystemExit(f'anchor failure: {start_sig} -> {next_sig}')
    return text[:start]+replacement+'\n'+text[end:]

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--repo',required=True); ap.add_argument('--apply',action='store_true'); ns=ap.parse_args()
    p=Path(ns.repo)/'src'/'smart_hub.cpp'; text=p.read_text(encoding='utf-8')
    if 'Smart Home v7.1' in text: print('v7.1 already applied'); return
    text=replace_function(text,'static void drawWorkshop(bool full) {','static void drawCustom(bool full) {',WORKSHOP)
    text=replace_function(text,'static void drawSystem(bool full) {','\n} // namespace',SYSTEM)
    text+='\n// BambuHelper Smart Home UX evolution v7.1\n'
    if ns.apply: p.write_text(text,encoding='utf-8'); print('Applied Smart Home UX v7.1')
    else: print('Dry run PASS')

if __name__=='__main__': main()
