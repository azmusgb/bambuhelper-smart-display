#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

HERE = Path(__file__).resolve().parent
MARKER = "Workshop OS v11.27 Companion Link RC1"


class PatchError(RuntimeError):
    pass


def load(root: Path, rel: str) -> str:
    p = root / rel
    if not p.exists():
        raise PatchError(f"missing reconstructed source: {rel}")
    return p.read_text(encoding="utf-8")


def save(root: Path, rel: str, text: str) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise PatchError(f"{label}: expected exactly one anchor, found {count}")
    return text.replace(old, new, 1)


SCRIPT_V11_27 = r'''(function(){
'use strict';
var envelope=null,state=null,power=null,device=null,capture=null,lastGood=0,pollTimer=null,busy={},holdTimer=null,powerHoldTimer=null,suppressPowerClickUntil=0;
var $=function(id){return document.getElementById(id)};
var pick=function(o,names,fallback){for(var i=0;i<names.length;i++){var v=o&&o[names[i]];if(v!==undefined&&v!==null&&v!=='')return v}return fallback};
var num=function(v,fallback){var n=Number(v);return Number.isFinite(n)?n:(fallback||0)};
var slot=function(){return Number($('slotSelect').value||0)};
var upper=function(v){return String(v||'').toUpperCase()};
function setFeedback(msg,kind){var e=$('feedback');e.textContent=msg||'';e.className='feedback'+(kind?' '+kind:'')}
function authRedirect(r){if(r&&r.redirected&&String(r.url).indexOf('/login')>=0){location.href='/login?next=/companion';return true}return false}
function fetchJson(url,opts,timeout){var c=new AbortController(),t=setTimeout(function(){c.abort()},timeout||3500);opts=opts||{};opts.cache='no-store';opts.credentials='same-origin';opts.signal=c.signal;return fetch(url,opts).then(function(r){clearTimeout(t);if(authRedirect(r))throw new Error('Authentication required');var ct=r.headers.get('content-type')||'';if(!r.ok)return r.json().catch(function(){return {}}).then(function(j){throw new Error(j.message||('HTTP '+r.status))});if(ct.indexOf('application/json')<0)throw new Error('Unexpected response');return r.json()}).catch(function(e){clearTimeout(t);throw e})}
function post(path,data){var p=new URLSearchParams();Object.keys(data||{}).forEach(function(k){p.append(k,data[k])});return fetchJson(path,{method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded'},body:p.toString()},5000)}
function isPaused(d){return !!(d&&d.paused)||upper(pick(d,['state','gcodeState','gcode_state'],''))==='PAUSE'}
function isPrinting(d){return !!(d&&d.printing)||isPaused(d)||['RUNNING','PRINTING','PREPARE'].indexOf(upper(pick(d,['state','gcodeState','gcode_state'],'')))>=0}
function connected(d){return !!(d&&d.connected)}
function tempText(v){if(v===undefined||v===null||v==='')return '—';return Math.round(num(v,0))+'°'}
function progressOf(d){return Math.max(0,Math.min(100,num(pick(d,['progress'],0),0)))}
function render(){
  var now=Date.now(),fresh=lastGood&&now-lastGood<5000,c=connected(state),paused=isPaused(state),printing=isPrinting(state),st=upper(pick(state,['state'],c?'READY':'OFFLINE'));
  $('connDot').className='dot '+(fresh&&c?'good':fresh?'warn':'bad');$('connText').textContent=fresh?(c?'Connected':'Device online · printer offline'):'Reconnecting…';
  $('freshText').textContent=lastGood?Math.max(0,Math.round((now-lastGood)/1000))+'s ago':'No state yet';
  $('printerName').textContent=pick(state,['name'], 'Workshop Printer');
  var stateEl=$('printerState');stateEl.textContent=paused?'Paused':(printing?'Printing':(st||'Ready'));stateEl.className='state'+(paused?' paused':printing?' printing':(st.indexOf('ERR')>=0||st.indexOf('FAIL')>=0)?' error':'');
  var pct=progressOf(state);$('progressBar').style.width=pct+'%';$('progressText').textContent=(printing||pct)?Math.round(pct)+'%':'—%';$('fileText').textContent=pick(state,['job'],printing?'Active print':'Ready');
  $('nozzle').textContent=tempText(pick(state,['nozzle'],null));$('bed').textContent=tempText(pick(state,['bed'],null));
  var layer=pick(state,['layer'],null),total=pick(state,['layers'],null);$('layer').textContent=layer==null?'—':String(layer)+(total?'/'+total:'');
  if($('remaining')){$('remaining').textContent=printing?Math.max(0,num(state&&state.remainingMinutes,0))+'m':'—'}
  var cmdOk=fresh&&c&&!busy.command;$('lightBtn').disabled=!cmdOk;$('lightBtn').textContent=state&&num(state.lightState,0)===1?'Light off':'Light on';
  $('pauseBtn').disabled=!cmdOk||!printing;$('pauseBtn').textContent=paused?'Resume':'Pause';$('stopBtn').disabled=!cmdOk||!printing;
  var pOk=power&&power.available&&power.online&&fresh&&!busy.power;$('powerBtn').disabled=!pOk;$('powerBtn').textContent=!power||!power.available?'Power not mapped':!power.online?'Power offline':power.on?'Power off':'Power on';$('powerBtn').className='btn '+(power&&power.on?'danger':'powerOn');
  if($('deviceHealth')){var parts=[];if(device){if(device.rssi!==undefined)parts.push('Wi‑Fi '+device.rssi+' dBm');if(device.heapKb!==undefined)parts.push('Heap '+device.heapKb+' KB');if(device.psramFreeKb!==undefined&&device.psramFreeKb>0)parts.push('PSRAM '+Math.round(device.psramFreeKb/1024*10)/10+' MB free')} $('deviceHealth').textContent=parts.length?parts.join(' · '):'Waiting for device health…'}
  if($('photoState')){$('photoState').textContent=capture&&capture.available?('On Waveshare RAM · '+Math.round(num(capture.bytes,0)/1024)+' KB · capture #'+capture.id):'No phone photo stored on the Waveshare.'}
  if($('clearCaptureBtn'))$('clearCaptureBtn').disabled=!(capture&&capture.available)||!!busy.capture;
}
function refresh(){var s=slot();return fetchJson('/companion/state?slot='+s+'&_='+Date.now(),null,3500).then(function(d){envelope=d||{};state=envelope.printer||{};power=envelope.power||{};device=envelope.device||{};capture=envelope.capture||{};lastGood=Date.now();render();return envelope}).catch(function(e){render();setFeedback(e.message==='Authentication required'?'Sign in required.':('Connection: '+e.message),'error')})}
function schedule(){clearTimeout(pollTimer);pollTimer=setTimeout(function tick(){refresh().finally(function(){pollTimer=setTimeout(tick,document.hidden?4500:1000)})},120)}
function command(path,data,label){if(busy.command)return;busy.command=true;render();setFeedback(label+'…');return post(path,data).then(function(){setFeedback(label+' sent. Waiting for printer state…','ok');return refresh()}).catch(function(e){setFeedback(e.message||'Command failed','error')}).finally(function(){busy.command=false;render()})}
$('lightBtn').addEventListener('click',function(){if(!state)return;command('/light/set',{slot:slot(),mode:num(state.lightState,0)===1?'off':'on'},num(state.lightState,0)===1?'Turning light off':'Turning light on')});
$('pauseBtn').addEventListener('click',function(){if(!state)return;var cmd=isPaused(state)?'resume':'pause';command('/printer/control',{slot:slot(),command:cmd},cmd==='resume'?'Resuming':'Pausing')});
function clearHold(){clearTimeout(holdTimer);holdTimer=null;$('stopFill').style.transition='none';$('stopFill').style.width='0';requestAnimationFrame(function(){$('stopFill').style.transition='width 1500ms linear'})}
$('stopBtn').addEventListener('pointerdown',function(e){if(this.disabled)return;e.preventDefault();$('stopFill').style.transition='width 1500ms linear';$('stopFill').style.width='100%';holdTimer=setTimeout(function(){clearHold();command('/printer/control',{slot:slot(),command:'stop',confirm:'STOP'},'Stopping print')},1500)});
['pointerup','pointercancel','pointerleave'].forEach(function(n){$('stopBtn').addEventListener(n,function(){if(holdTimer)clearHold()})});
$('powerBtn').addEventListener('click',function(){if(Date.now()<suppressPowerClickUntil||!power||busy.power)return;var desired=!power.on;if(!desired){setFeedback('Hold Power off for 2 seconds to confirm.','error');return}busy.power=true;render();post('/printer/power',{slot:slot(),on:'1'}).then(function(){setFeedback('Printer power-on sent.','ok');return refresh()}).catch(function(e){setFeedback(e.message,'error')}).finally(function(){busy.power=false;render()})});
$('powerBtn').addEventListener('pointerdown',function(e){if(this.disabled||!power||!power.on)return;e.preventDefault();clearTimeout(powerHoldTimer);setFeedback(isPrinting(state)?'Keep holding — active print power-off guard…':'Keep holding to power off…','error');powerHoldTimer=setTimeout(function(){powerHoldTimer=null;suppressPowerClickUntil=Date.now()+1200;var token=isPrinting(state)?'POWER OFF DURING PRINT':'POWER OFF';busy.power=true;render();post('/printer/power',{slot:slot(),on:'0',confirm:token}).then(function(){setFeedback('Printer power-off sent.','ok');return refresh()}).catch(function(err){setFeedback(err.message,'error')}).finally(function(){busy.power=false;render()})},2000)});
['pointerup','pointercancel','pointerleave'].forEach(function(n){$('powerBtn').addEventListener(n,function(){if(powerHoldTimer){clearTimeout(powerHoldTimer);powerHoldTimer=null}})});
function uploadCaptureBlob(blob){if(!blob)throw new Error('Could not encode photo');if(blob.size>250*1024)throw new Error('Photo is still too large after compression');var form=new FormData();form.append('capture',blob,'capture.jpg');busy.capture=true;render();setFeedback('Sending '+Math.round(blob.size/1024)+' KB photo to Waveshare…');return fetchJson('/companion/capture',{method:'POST',body:form},12000).then(function(r){setFeedback('Photo transferred to Waveshare RAM.','ok');return refresh()}).finally(function(){busy.capture=false;render()})}
function encodeCanvas(canvas,quality,done){canvas.toBlob(function(blob){if(blob&&blob.size>250*1024&&quality>0.48)return encodeCanvas(canvas,quality-0.12,done);done(blob)},'image/jpeg',quality)}
function prepareCapture(file){var preview=$('cameraPreview'),localUrl=URL.createObjectURL(file);preview.src=localUrl;preview.style.display='block';var img=new Image();img.onload=function(){var maxDim=480,scale=Math.min(1,maxDim/Math.max(img.naturalWidth||1,img.naturalHeight||1)),w=Math.max(1,Math.round(img.naturalWidth*scale)),h=Math.max(1,Math.round(img.naturalHeight*scale)),canvas=document.createElement('canvas');canvas.width=w;canvas.height=h;var ctx=canvas.getContext('2d');ctx.drawImage(img,0,0,w,h);encodeCanvas(canvas,0.76,function(blob){uploadCaptureBlob(blob).catch(function(e){setFeedback(e.message||'Photo transfer failed','error')})})};img.onerror=function(){setFeedback('Could not read the selected photo.','error')};img.src=localUrl}
$('cameraInput').addEventListener('change',function(){var f=this.files&&this.files[0];if(f)prepareCapture(f)});
$('clearCaptureBtn').addEventListener('click',function(){if(!(capture&&capture.available)||busy.capture)return;busy.capture=true;render();post('/companion/capture/clear',{}).then(function(){setFeedback('Waveshare photo cleared.','ok');return refresh()}).catch(function(e){setFeedback(e.message||'Could not clear photo','error')}).finally(function(){busy.capture=false;render()})});
$('refreshBtn').addEventListener('click',function(){refresh()});$('slotSelect').addEventListener('change',function(){envelope=state=power=device=capture=null;lastGood=0;render();refresh()});
document.addEventListener('visibilitychange',function(){schedule();if(!document.hidden)refresh()});window.addEventListener('online',function(){schedule();refresh()});window.addEventListener('offline',function(){render();setFeedback('iPhone network is offline.','error')});
render();refresh();schedule();
})();'''


def html_v11_27() -> str:
    p = HERE / "assets" / "v11_26_companion_web.html"
    if not p.exists():
        raise PatchError("missing v11.26 Companion Web source asset")
    html = p.read_text(encoding="utf-8")
    html = once(
        html,
        '<div class="metrics">\n      <div class="metric"><div class="k">Nozzle</div><div id="nozzle" class="v">—</div></div>\n      <div class="metric"><div class="k">Bed</div><div id="bed" class="v">—</div></div>\n      <div class="metric"><div class="k">Layer</div><div id="layer" class="v">—</div></div>\n    </div>',
        '<div class="metrics">\n      <div class="metric"><div class="k">Nozzle</div><div id="nozzle" class="v">—</div></div>\n      <div class="metric"><div class="k">Bed</div><div id="bed" class="v">—</div></div>\n      <div class="metric"><div class="k">Layer</div><div id="layer" class="v">—</div></div>\n      <div class="metric"><div class="k">Remaining</div><div id="remaining" class="v">—</div></div>\n    </div>',
        "remaining metric",
    )
    html = once(
        html,
        '<label class="btn linkBtn" for="cameraInput">Take photo</label>\n      <a class="btn linkBtn" href="/">Full Workshop OS</a>\n      <input id="cameraInput" class="cameraInput" type="file" accept="image/*" capture="environment">',
        '<label class="btn linkBtn" for="cameraInput">Take + send</label>\n      <button id="clearCaptureBtn" class="btn" type="button" disabled>Clear photo</button>\n      <a class="btn linkBtn full" href="/">Full Workshop OS</a>\n      <input id="cameraInput" class="cameraInput" type="file" accept="image/*" capture="environment">',
        "camera actions",
    )
    html = once(
        html,
        '<div class="helper">Camera preview stays on this phone in Web v1. Large photo transfer will use an authenticated Wi‑Fi upload path after physical acceptance.</div>',
        '<div id="photoState" class="helper">No phone photo stored on the Waveshare.</div>\n    <div class="helper">The iPhone resizes captures to the display scale before transfer. Workshop OS keeps only the latest JPEG in PSRAM; it is never written to flash and disappears on reboot.</div>',
        "camera transfer copy",
    )
    html = once(
        html,
        '<div class="helper">Keep this page open or add it to your iPhone Home Screen. It talks directly to the Waveshare over your local Wi‑Fi; no cloud relay is required.</div>',
        '<div id="deviceHealth" class="helper">Waiting for device health…</div>\n    <div class="helper">One authenticated state envelope now carries printer, power, device health and phone presence. Keep this page open or add it to your iPhone Home Screen; no cloud relay is required.</div>',
        "state envelope copy",
    )
    html = html.replace('Workshop Companion Web · v11.26 candidate · authenticated LAN session', 'Workshop Companion Link · v11.27 candidate · authenticated LAN session')
    start = html.find("<script>\n(function(){")
    end = html.find("</script>", start)
    if start < 0 or end < 0:
        raise PatchError("could not locate v11.26 Companion script block")
    html = html[:start] + "<script>\n" + SCRIPT_V11_27 + "\n</script>" + html[end + len("</script>"):]
    if ')COMPANION"' in html:
        raise PatchError("v11.27 HTML collides with C++ raw-string delimiter")
    return html


STATE_CAPTURE_CPP = r'''

void notePhoneSeen(uint8_t slot) {
  if (slot < MAX_PRINTERS) g_lastPhoneSlot = slot;
  g_lastPhoneSeenMs = millis();
}

void handleCompanionState() {
  if (!securityAuthorize(server, false)) return;
  uint8_t slot = 0;
  if (server.hasArg("slot")) {
    int v = server.arg("slot").toInt();
    if (v >= 0 && v < MAX_PRINTERS) slot = static_cast<uint8_t>(v);
  }
  notePhoneSeen(slot);

  PrinterSlot& p = printers[slot];
  BambuState& st = p.state;
  JsonDocument doc;
  doc["protocol"] = 2;
  doc["transport"] = "wifi-web";

  JsonObject phone = doc["phone"].to<JsonObject>();
  phone["connected"] = true;
  phone["slot"] = slot;
  phone["ageMs"] = 0;

  JsonObject dev = doc["device"].to<JsonObject>();
  dev["uptimeSec"] = static_cast<uint32_t>(millis() / 1000U);
  dev["heapKb"] = ESP.getFreeHeap() / 1024U;
#ifdef BOARD_HAS_PSRAM
  dev["psramFreeKb"] = ESP.getFreePsram() / 1024U;
  dev["psramTotalKb"] = ESP.getPsramSize() / 1024U;
#else
  dev["psramFreeKb"] = 0;
  dev["psramTotalKb"] = 0;
#endif
  dev["rssi"] = WiFi.RSSI();
  dev["ip"] = WiFi.localIP().toString();

  JsonObject printer = doc["printer"].to<JsonObject>();
  printer["slot"] = slot;
  printer["configured"] = isPrinterConfigured(slot);
  printer["connected"] = st.connected;
  printer["name"] = p.config.name;
  printer["state"] = st.gcodeState;
  printer["printing"] = isPrintingGcodeState(st.gcodeStateId);
  printer["paused"] = st.gcodeStateId == GCODE_PAUSE;
  printer["progress"] = st.progress;
  printer["remainingMinutes"] = st.remainingMinutes;
  printer["nozzle"] = st.nozzleTemp;
  printer["nozzleTarget"] = st.nozzleTarget;
  printer["bed"] = st.bedTemp;
  printer["bedTarget"] = st.bedTarget;
  printer["chamber"] = st.chamberTemp;
  printer["layer"] = st.layerNum;
  printer["layers"] = st.totalLayers;
  printer["job"] = jobDisplayName(st);
  printer["lightState"] = st.lightState;
  printer["doorSensor"] = st.doorSensorPresent;
  printer["doorOpen"] = st.doorSensorPresent && st.doorOpen;
  printer["stateAgeMs"] = st.lastUpdate ? static_cast<uint32_t>(millis() - st.lastUpdate) : 0;

  JsonObject pwr = doc["power"].to<JsonObject>();
  const bool powerAvailable = tasmotaConfiguredForSlot(slot);
  pwr["available"] = powerAvailable;
  if (powerAvailable) {
    const uint8_t plug = tasmotaControlPlugForSlot(slot);
    if (plug != 0xFF) {
      TasmotaPlugStatsView v;
      tasmotaGetStats(plug, &v);
      pwr["plug"] = plug;
      pwr["online"] = v.online;
      pwr["stateKnown"] = v.powerStateKnown;
      pwr["on"] = v.powerStateKnown ? v.powerOn : (v.online && v.watts > 0.5f);
      pwr["watts"] = v.watts;
    }
  }

  JsonObject cap = doc["capture"].to<JsonObject>();
  cap["available"] = g_capturePublished != nullptr && g_capturePublishedLen > 0;
  cap["id"] = g_captureId;
  cap["bytes"] = g_capturePublishedLen;
  cap["ageMs"] = g_captureAtMs ? static_cast<uint32_t>(millis() - g_captureAtMs) : 0;
  cap["volatile"] = true;
  cap["maxBytes"] = kCaptureMaxBytes;

  String json;
  serializeJson(doc, json);
  server.sendHeader("Cache-Control", "no-store");
  server.send(200, "application/json", json);
}

enum CaptureUploadError : uint8_t {
  CAPTURE_UPLOAD_OK = 0,
  CAPTURE_UPLOAD_AUTH,
  CAPTURE_UPLOAD_TYPE,
  CAPTURE_UPLOAD_ALLOC,
  CAPTURE_UPLOAD_TOO_LARGE,
  CAPTURE_UPLOAD_INVALID_JPEG,
  CAPTURE_UPLOAD_ABORTED,
};

void freeInflightCapture() {
  if (g_captureInflight) {
    heap_caps_free(g_captureInflight);
    g_captureInflight = nullptr;
  }
  g_captureInflightLen = 0;
}

void clearPublishedCapture() {
  if (g_capturePublished) {
    heap_caps_free(g_capturePublished);
    g_capturePublished = nullptr;
  }
  g_capturePublishedLen = 0;
  g_captureAtMs = 0;
}

void handleCompanionCaptureUpload() {
  HTTPUpload& upload = server.upload();
  if (upload.status == UPLOAD_FILE_START) {
    freeInflightCapture();
    g_captureUploadAuthorized = securityAuthorize(server, true);
    g_captureUploadError = g_captureUploadAuthorized ? CAPTURE_UPLOAD_OK : CAPTURE_UPLOAD_AUTH;
    if (!g_captureUploadAuthorized) return;
    if (upload.type != "image/jpeg") {
      g_captureUploadError = CAPTURE_UPLOAD_TYPE;
      return;
    }
#ifdef BOARD_HAS_PSRAM
    g_captureInflight = static_cast<uint8_t*>(heap_caps_malloc(kCaptureMaxBytes, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT));
    if (!g_captureInflight) g_captureUploadError = CAPTURE_UPLOAD_ALLOC;
#else
    g_captureUploadError = CAPTURE_UPLOAD_ALLOC;
#endif
    return;
  }

  if (!g_captureUploadAuthorized || g_captureUploadError != CAPTURE_UPLOAD_OK) return;

  if (upload.status == UPLOAD_FILE_WRITE) {
    if (g_captureInflightLen + upload.currentSize > kCaptureMaxBytes) {
      g_captureUploadError = CAPTURE_UPLOAD_TOO_LARGE;
      freeInflightCapture();
      return;
    }
    memcpy(g_captureInflight + g_captureInflightLen, upload.buf, upload.currentSize);
    g_captureInflightLen += upload.currentSize;
    return;
  }

  if (upload.status == UPLOAD_FILE_END) {
    if (g_captureInflightLen < 4 || g_captureInflight[0] != 0xFF || g_captureInflight[1] != 0xD8 ||
        g_captureInflight[g_captureInflightLen - 2] != 0xFF || g_captureInflight[g_captureInflightLen - 1] != 0xD9) {
      g_captureUploadError = CAPTURE_UPLOAD_INVALID_JPEG;
      freeInflightCapture();
      return;
    }
    clearPublishedCapture();
    g_capturePublished = g_captureInflight;
    g_capturePublishedLen = g_captureInflightLen;
    g_captureInflight = nullptr;
    g_captureInflightLen = 0;
    g_captureAtMs = millis();
    ++g_captureId;
    if (g_captureId == 0) ++g_captureId;
    notePhoneSeen(g_lastPhoneSlot);
    return;
  }

  if (upload.status == UPLOAD_FILE_ABORTED) {
    g_captureUploadError = CAPTURE_UPLOAD_ABORTED;
    freeInflightCapture();
  }
}

void handleCompanionCaptureComplete() {
  if (!g_captureUploadAuthorized) return;  // securityAuthorize already replied
  server.sendHeader("Cache-Control", "no-store");
  if (g_captureUploadError == CAPTURE_UPLOAD_OK && g_capturePublishedLen > 0) {
    String json = String("{\"status\":\"ok\",\"id\":") + String(g_captureId) +
        ",\"bytes\":" + String(g_capturePublishedLen) + ",\"volatile\":true}";
    server.send(200, "application/json", json);
    return;
  }
  int code = 400;
  const char* message = "capture upload failed";
  switch (g_captureUploadError) {
    case CAPTURE_UPLOAD_TYPE: code = 415; message = "JPEG capture required"; break;
    case CAPTURE_UPLOAD_ALLOC: code = 507; message = "PSRAM unavailable for capture"; break;
    case CAPTURE_UPLOAD_TOO_LARGE: code = 413; message = "capture exceeds 256 KB limit"; break;
    case CAPTURE_UPLOAD_INVALID_JPEG: code = 400; message = "invalid JPEG capture"; break;
    case CAPTURE_UPLOAD_ABORTED: code = 400; message = "capture upload aborted"; break;
    default: break;
  }
  String json = String("{\"status\":\"error\",\"message\":\"") + message + "\"}";
  server.send(code, "application/json", json);
}

void handleCompanionCaptureClear() {
  if (!securityAuthorize(server, true)) return;
  clearPublishedCapture();
  notePhoneSeen(g_lastPhoneSlot);
  server.sendHeader("Cache-Control", "no-store");
  server.send(200, "application/json", "{\"status\":\"ok\"}");
}
'''


def patch_companion_source(root: Path) -> None:
    rel = "src/companion_web.cpp"
    text = load(root, rel)
    text = once(
        text,
        '#include "security_manager.h"\n#include <WebServer.h>\n',
        '#include "security_manager.h"\n#include "bambu_state.h"\n#include "bambu_mqtt.h"\n#include "tasmota.h"\n#include "config.h"\n#include <ArduinoJson.h>\n#include <WiFi.h>\n#include <WebServer.h>\n#include <esp_heap_caps.h>\n',
        "Companion Link includes",
    )
    text = once(
        text,
        'uint32_t g_lastPhoneSeenMs = 0;\nuint8_t g_lastPhoneSlot = 0;\n',
        'uint32_t g_lastPhoneSeenMs = 0;\nuint8_t g_lastPhoneSlot = 0;\nconstexpr size_t kCaptureMaxBytes = 256U * 1024U;\nuint8_t* g_captureInflight = nullptr;\nsize_t g_captureInflightLen = 0;\nuint8_t* g_capturePublished = nullptr;\nsize_t g_capturePublishedLen = 0;\nuint32_t g_captureId = 0;\nuint32_t g_captureAtMs = 0;\nbool g_captureUploadAuthorized = false;\nuint8_t g_captureUploadError = 0;\n',
        "capture state",
    )

    html = html_v11_27()
    start_token = 'const char kCompanionHtml[] PROGMEM = R"COMPANION('
    end_token = ')COMPANION";'
    start = text.find(start_token)
    end = text.find(end_token, start)
    if start < 0 or end < 0:
        raise PatchError("could not replace embedded Companion HTML")
    start += len(start_token)
    text = text[:start] + html + text[end:]

    text = once(text, '}  // namespace\n\nvoid registerCompanionWebRoutes() {', STATE_CAPTURE_CPP + '\n}  // namespace\n\nvoid registerCompanionWebRoutes() {', "state/capture handlers")
    text = once(
        text,
        '  server.on("/companion/connection", HTTP_GET, handleCompanionConnection);\n',
        '  server.on("/companion/connection", HTTP_GET, handleCompanionConnection);\n  server.on("/companion/state", HTTP_GET, handleCompanionState);\n  server.on("/companion/capture", HTTP_POST, handleCompanionCaptureComplete, handleCompanionCaptureUpload);\n  server.on("/companion/capture/clear", HTTP_POST, handleCompanionCaptureClear);\n',
        "Companion Link routes",
    )
    text += '''\n\nbool companionWebGetLatestCapture(const uint8_t** buf, size_t* len, uint32_t* captureId) {\n  if (!buf || !len || !captureId || !g_capturePublished || g_capturePublishedLen == 0) return false;\n  *buf = g_capturePublished;\n  *len = g_capturePublishedLen;\n  *captureId = g_captureId;\n  return true;\n}\n\nvoid companionWebClearCapture() { clearPublishedCapture(); }\n'''
    save(root, rel, text)


def patch_header(root: Path) -> None:
    rel = "src/companion_web.h"
    text = load(root, rel)
    text = once(
        text,
        'uint32_t companionWebLastSeenMs();\n',
        'uint32_t companionWebLastSeenMs();\nbool companionWebGetLatestCapture(const uint8_t** buf, size_t* len, uint32_t* captureId);\nvoid companionWebClearCapture();\n',
        "capture API",
    )
    save(root, rel, text)


def patch_build(root: Path) -> None:
    rel = "include/smart_home_build.h"
    text = load(root, rel)
    text = once(text, '#define SMART_HOME_VERSION "v11.26"', '#define SMART_HOME_VERSION "v11.27"', "version")
    text = once(text, '#define SMART_HOME_PROFILE "companion-web"', '#define SMART_HOME_PROFILE "companion-link"', "profile")
    text = once(text, 'Smart Home v11.26 Companion Web RC1', 'Smart Home v11.27 Companion Link RC1', "build label")
    text += f"\n// {MARKER}\n"
    save(root, rel, text)


def apply(root: Path) -> None:
    build = load(root, "include/smart_home_build.h")
    if MARKER in build:
        print(f"{MARKER} already applied")
        return
    if 'SMART_HOME_VERSION "v11.26"' not in build:
        raise PatchError("v11.26 Companion Web base is required")
    patch_companion_source(root)
    patch_header(root)
    patch_build(root)

    checks = {
        "include/smart_home_build.h": ['SMART_HOME_VERSION "v11.27"', 'SMART_HOME_PROFILE "companion-link"', MARKER],
        "src/companion_web.h": ['companionWebGetLatestCapture', 'companionWebClearCapture'],
        "src/companion_web.cpp": [
            'server.on("/companion/state", HTTP_GET',
            'server.on("/companion/capture", HTTP_POST',
            'server.on("/companion/capture/clear", HTTP_POST',
            'securityAuthorize(server, false)',
            'securityAuthorize(server, true)',
            'kCaptureMaxBytes = 256U * 1024U',
            'MALLOC_CAP_SPIRAM',
            'CAPTURE_UPLOAD_TOO_LARGE',
            'g_capturePublishedLen',
            'doc["protocol"] = 2',
            'doc["printer"]',
            'doc["power"]',
            'doc["device"]',
            'doc["capture"]',
            "fetchJson('/companion/state?slot=",
            "form.append('capture',blob,'capture.jpg')",
            'PSRAM',
            'Workshop Companion Link · v11.27 candidate',
        ],
    }
    for rel, needles in checks.items():
        body = load(root, rel)
        for needle in needles:
            if needle not in body:
                raise PatchError(f"{rel}: missing {needle}")

    print(f"{MARKER} applied")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    if not args.apply:
        raise SystemExit("refusing to mutate without --apply")
    apply(Path(args.repo))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
