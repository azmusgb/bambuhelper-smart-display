#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

MARKER = "Workshop OS v11.30 Unified Web + Companion RC1"


class PatchError(RuntimeError):
    pass


def load(root: Path, rel: str) -> str:
    p = root / rel
    if not p.exists():
        raise PatchError(f"missing reconstructed source: {rel}")
    return p.read_text(encoding="utf-8")


def save(root: Path, rel: str, text: str) -> None:
    (root / rel).write_text(text, encoding="utf-8")


def once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise PatchError(f"{label}: expected exactly one anchor, found {count}")
    return text.replace(old, new, 1)


STANDARD_WEB_JS = r'''
// ---------------------------------------------------------------------------
// Workshop OS v11.30 Unified Web + Companion UX
// ---------------------------------------------------------------------------
(function(){
  'use strict';
  var pollTimer=null, paused=false, lastGood=0, current=null;
  function q(id){return document.getElementById(id)}
  function text(v,f){return (v===undefined||v===null||v==='')?(f||'—'):String(v)}
  function upper(v){return text(v,'').toUpperCase()}
  function isPrinting(p){var s=upper(p&&p.state);return !!(p&&p.printing)||!!(p&&p.paused)||s==='RUNNING'||s==='PRINTING'||s==='PAUSE'||s==='PAUSED'||s==='PREPARE'}
  function injectStyle(){
    if(q('v1130UnifiedStyle'))return;
    var s=document.createElement('style');s.id='v1130UnifiedStyle';s.textContent='\
.v1130-rail{display:grid;grid-template-columns:minmax(180px,1.35fr) repeat(4,minmax(110px,.7fr));gap:8px;margin:10px 0 16px;padding:10px;border:1px solid rgba(112,137,160,.26);border-radius:14px;background:rgba(15,21,28,.72);backdrop-filter:blur(12px);position:relative;z-index:3}\
.v1130-rail-main,.v1130-chip{min-height:58px;border:1px solid rgba(112,137,160,.18);border-radius:11px;background:rgba(29,38,49,.82);padding:9px 11px;display:flex;flex-direction:column;justify-content:center}.v1130-rail-main{background:linear-gradient(135deg,rgba(255,107,61,.12),rgba(72,198,217,.07))}.v1130-k{font-size:10px;letter-spacing:.08em;text-transform:uppercase;color:#91a1b1;font-weight:800}.v1130-v{font-size:14px;font-weight:780;margin-top:3px;color:#eff5fa;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.v1130-sub{font-size:11px;color:#8d9cab;margin-top:2px}.v1130-good .v1130-v{color:#8ce8a3}.v1130-warn .v1130-v{color:#ffd179}.v1130-bad .v1130-v{color:#ff9ca2}.v1130-actions{display:flex;gap:8px;flex-wrap:wrap;margin:0 0 14px}.v1130-action{min-height:42px;padding:0 13px;border-radius:10px;border:1px solid #344252;background:#202a35;color:#eef5fa;font-weight:760;text-decoration:none;display:inline-flex;align-items:center;justify-content:center}.v1130-action.primary{background:#173b43;border-color:#285c67;color:#acf0f7}.v1130-attention{display:none;margin:-5px 0 14px;padding:10px 13px;border-radius:11px;border:1px solid #5e4b27;background:#382f1c;color:#ffd887;font-size:12px;line-height:1.45}.v1130-attention.show{display:block}.v1130-mobile-dock{display:none}.v1130-dot{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:6px;background:#607081}.v1130-dot.good{background:#52d273}.v1130-dot.warn{background:#f5b642}.v1130-dot.bad{background:#ff5b61}\
@media(max-width:980px){.v1130-rail{grid-template-columns:repeat(2,1fr)}.v1130-rail-main{grid-column:1/-1}}\
@media(max-width:720px){body{padding-bottom:76px!important}.v1130-rail{grid-template-columns:1fr 1fr;padding:8px;gap:7px}.v1130-rail-main{grid-column:1/-1}.v1130-chip{min-height:54px}.v1130-actions{display:none}.v1130-mobile-dock{display:grid;grid-template-columns:repeat(4,1fr);position:fixed;left:10px;right:10px;bottom:max(8px,env(safe-area-inset-bottom));z-index:9999;background:rgba(13,17,23,.94);border:1px solid #334151;border-radius:16px;padding:6px;box-shadow:0 14px 40px #0008;backdrop-filter:blur(16px)}.v1130-mobile-dock button,.v1130-mobile-dock a{min-height:50px;border:0;border-radius:11px;background:transparent;color:#dbe6ef;font:inherit;font-size:11px;font-weight:780;text-decoration:none;display:flex;align-items:center;justify-content:center}.v1130-mobile-dock .primary{background:#173842;color:#a7ecf4}}';
    document.head.appendChild(s);
  }
  function navButton(label,section,klass){var b=document.createElement('button');b.type='button';b.className='v1130-action '+(klass||'');b.textContent=label;b.addEventListener('click',function(){if(typeof loadSection==='function')loadSection(section)});return b}
  function build(){
    injectStyle();if(q('v1130UnifiedRail'))return;
    var host=document.querySelector('main')||document.querySelector('.main')||document.body;
    var rail=document.createElement('div');rail.id='v1130UnifiedRail';rail.className='v1130-rail';rail.innerHTML='\
<div class="v1130-rail-main" id="v1130Main"><div class="v1130-k">Workshop now</div><div class="v1130-v" id="v1130Headline"><span class="v1130-dot" id="v1130Dot"></span>Connecting…</div><div class="v1130-sub" id="v1130Fresh">Waiting for live state</div></div>\
<div class="v1130-chip" id="v1130PrinterChip"><div class="v1130-k">Printer</div><div class="v1130-v" id="v1130Printer">—</div><div class="v1130-sub" id="v1130Job">No state</div></div>\
<div class="v1130-chip" id="v1130PowerChip"><div class="v1130-k">Power</div><div class="v1130-v" id="v1130Power">—</div><div class="v1130-sub" id="v1130Watts">Not mapped</div></div>\
<div class="v1130-chip" id="v1130PhoneChip"><div class="v1130-k">Companion</div><div class="v1130-v" id="v1130Phone">—</div><div class="v1130-sub" id="v1130Photo">No photo</div></div>\
<div class="v1130-chip" id="v1130DeviceChip"><div class="v1130-k">Device</div><div class="v1130-v" id="v1130Device">—</div><div class="v1130-sub" id="v1130Rssi">Wi‑Fi —</div></div>';
    host.insertBefore(rail,host.firstChild);
    var attention=document.createElement('div');attention.id='v1130Attention';attention.className='v1130-attention';rail.insertAdjacentElement('afterend',attention);
    var actions=document.createElement('div');actions.className='v1130-actions';actions.appendChild(navButton('Home','home','primary'));actions.appendChild(navButton('Workshop','workshop',''));var ca=document.createElement('a');ca.className='v1130-action';ca.href='/companion';ca.textContent='Open Companion';actions.appendChild(ca);actions.appendChild(navButton('Updates','wifi',''));attention.insertAdjacentElement('afterend',actions);
    var dock=document.createElement('div');dock.className='v1130-mobile-dock';dock.appendChild(navButton('Home','home','primary'));dock.appendChild(navButton('Printer','printer',''));var dca=document.createElement('a');dca.href='/companion';dca.textContent='Companion';dock.appendChild(dca);dock.appendChild(navButton('More','workshop',''));document.body.appendChild(dock);
  }
  function classState(el,kind){if(!el)return;el.classList.remove('v1130-good','v1130-warn','v1130-bad');if(kind)el.classList.add('v1130-'+kind)}
  function render(){
    build();var now=Date.now(),fresh=lastGood&&now-lastGood<9000,d=current||{},p=d.printer||{},pw=d.power||{},dev=d.device||{},cap=d.capture||{},conn=!!p.connected,printing=isPrinting(p),paused=!!p.paused,st=upper(p.state||'');
    var dot=q('v1130Dot');dot.className='v1130-dot '+(fresh?(conn?'good':'warn'):'bad');
    q('v1130Headline').lastChild.nodeValue=fresh?(conn?(printing?(paused?' Print paused':' Printing live'):' Workshop online'):' Device online · printer offline'):' Reconnecting…';
    q('v1130Fresh').textContent=lastGood?('Live state · '+Math.max(0,Math.round((now-lastGood)/1000))+'s ago'):'Waiting for live state';
    q('v1130Printer').textContent=!fresh?'Unknown':!conn?'Offline':paused?'Paused':printing?('Printing '+Math.round(Number(p.progress||0))+'%'):(st||'Ready');
    q('v1130Job').textContent=text(p.job,printing?'Active print':text(p.name,'Ready'));
    classState(q('v1130PrinterChip'),!fresh?'bad':!conn?'warn':printing?'good':'');
    q('v1130Power').textContent=!pw.available?'Not mapped':!pw.online?'Offline':pw.on?'On':'Off';q('v1130Watts').textContent=(pw.available&&pw.online&&pw.watts!==undefined)?(Math.round(Number(pw.watts||0))+' W'):(pw.available?'No live reading':'Map a smart plug');classState(q('v1130PowerChip'),pw.available&&!pw.online?'warn':(printing&&pw.available&&!pw.on)?'bad':'');
    q('v1130Phone').textContent=d.phone&&d.phone.connected?'Connected':'Available';q('v1130Photo').textContent=cap.available?('Photo ready · '+text(cap.width,'?')+'×'+text(cap.height,'?')):'No photo stored';classState(q('v1130PhoneChip'),cap.available?'good':'');
    q('v1130Device').textContent=fresh?'Online':'Stale';q('v1130Rssi').textContent=dev.rssi!==undefined?('Wi‑Fi '+dev.rssi+' dBm'):'Wi‑Fi —';classState(q('v1130DeviceChip'),!fresh?'bad':(dev.rssi!==undefined&&Number(dev.rssi)<-75)?'warn':'good');
    var problems=[];if(!fresh)problems.push('Live state is stale.');else if(!conn)problems.push('Printer is not connected.');if(printing&&pw.available&&pw.online&&!pw.on)problems.push('Printer reports an active print while mapped power is off.');if(dev.rssi!==undefined&&Number(dev.rssi)<-80)problems.push('Wi‑Fi signal is weak ('+dev.rssi+' dBm).');
    var a=q('v1130Attention');a.textContent=problems.join(' ');a.className='v1130-attention'+(problems.length?' show':'');
  }
  function poll(){
    clearTimeout(pollTimer);if(paused){pollTimer=setTimeout(poll,1200);return}var delay=document.hidden?7000:3200;
    fetch('/companion/state?slot=0&_='+Date.now(),{cache:'no-store',credentials:'same-origin'}).then(function(r){if(!r.ok)throw new Error('HTTP '+r.status);return r.json()}).then(function(d){current=d||{};lastGood=Date.now();render()}).catch(function(){render()}).finally(function(){pollTimer=setTimeout(poll,delay)});
  }
  window.v1130PauseLiveRail=function(value){paused=!!value;if(!paused)poll()};
  document.addEventListener('visibilitychange',function(){if(!document.hidden)poll()});window.addEventListener('online',poll);window.addEventListener('offline',render);
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',function(){build();render();poll()});else{build();render();poll()}
})();

'''

COMPANION_CSS = r'''
/* v11.30 Companion refinement */
html{scroll-behavior:smooth}.top{position:sticky;top:0;z-index:20;background:linear-gradient(180deg,#0d1117 72%,#0d111700);padding-top:12px}.v1130-companion-nav{position:sticky;top:68px;z-index:19;display:grid;grid-template-columns:repeat(4,1fr);gap:6px;padding:7px;margin:0 0 12px;background:rgba(13,17,23,.92);border:1px solid #293443;border-radius:14px;backdrop-filter:blur(16px)}.v1130-companion-nav button{min-height:42px;border:0;border-radius:10px;background:#1b2530;color:#dbe6ef;font-size:11px;font-weight:800}.v1130-companion-nav button:active{transform:scale(.98)}.v1130-attention-card{border-color:#3a4858;background:linear-gradient(135deg,#17212b,#121820)}.v1130-attention-row{display:flex;align-items:flex-start;justify-content:space-between;gap:12px}.v1130-attention-title{font-size:18px;font-weight:850}.v1130-attention-copy{font-size:12px;color:#9eacba;line-height:1.45;margin-top:4px}.v1130-badge{font-size:10px;font-weight:850;letter-spacing:.06em;text-transform:uppercase;padding:6px 8px;border-radius:999px;background:#263342;color:#dbe7f0;white-space:nowrap}.v1130-badge.good{background:#173923;color:#9ae9ad}.v1130-badge.warn{background:#433619;color:#ffd77c}.v1130-badge.bad{background:#492127;color:#ffadb3}.v1130-mini-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:7px;margin-top:12px}.v1130-mini{border:1px solid #2b3744;border-radius:11px;background:#1a222c;padding:9px}.v1130-mini b{display:block;font-size:13px;margin-top:3px}.v1130-mini span{font-size:9px;letter-spacing:.07em;text-transform:uppercase;color:#8f9ead;font-weight:800}.card{scroll-margin-top:126px}.btn{min-height:58px}.cameraPreview{max-height:330px}.helper{font-size:12.5px}.footer{padding-bottom:max(10px,env(safe-area-inset-bottom))}@media(max-width:390px){.v1130-companion-nav{top:64px}.v1130-mini-grid{grid-template-columns:1fr 1fr}.v1130-mini:last-child{grid-column:1/-1}}
'''

COMPANION_JS = r'''
<script id="v1130CompanionEnhance">
(function(){
'use strict';
function q(id){return document.getElementById(id)}
function txt(id,f){var e=q(id);return e&&e.textContent?e.textContent.trim():(f||'—')}
function build(){
  var shell=document.querySelector('.shell'),top=document.querySelector('.top');if(!shell||!top||q('v1130CompanionNav'))return;
  var nav=document.createElement('div');nav.id='v1130CompanionNav';nav.className='v1130-companion-nav';['Overview','Controls','Photo','System'].forEach(function(label,i){var b=document.createElement('button');b.type='button';b.textContent=label;b.addEventListener('click',function(){var cards=document.querySelectorAll('.card');if(cards[i])cards[i].scrollIntoView({behavior:'smooth',block:'start'})});nav.appendChild(b)});top.insertAdjacentElement('afterend',nav);
  var card=document.createElement('section');card.id='v1130AttentionCard';card.className='card v1130-attention-card';card.innerHTML='<div class="v1130-attention-row"><div><div class="v1130-attention-title" id="v1130AttentionTitle">Getting workshop state…</div><div class="v1130-attention-copy" id="v1130AttentionCopy">Companion is watching the same live state used by the controls below.</div></div><div class="v1130-badge" id="v1130AttentionBadge">Live</div></div><div class="v1130-mini-grid"><div class="v1130-mini"><span>Printer</span><b id="v1130MiniPrinter">—</b></div><div class="v1130-mini"><span>Power</span><b id="v1130MiniPower">—</b></div><div class="v1130-mini"><span>Photo</span><b id="v1130MiniPhoto">—</b></div></div>';
  nav.insertAdjacentElement('afterend',card);
  var brand=document.querySelector('.brand');if(brand)brand.textContent='Workshop Companion';
}
function update(){
  build();var conn=txt('connText','Reconnecting…'),state=txt('printerState','Unknown'),fresh=txt('freshText','No state yet'),power=txt('powerBtn','Power'),photo=txt('photoState','No phone photo');
  q('v1130MiniPrinter').textContent=state;q('v1130MiniPower').textContent=power.replace('Printer ','');q('v1130MiniPhoto').textContent=photo.indexOf('On Waveshare')===0?'Ready':'None';
  var badge=q('v1130AttentionBadge'),title=q('v1130AttentionTitle'),copy=q('v1130AttentionCopy');badge.className='v1130-badge';
  if(conn.indexOf('Reconnecting')>=0){title.textContent='Reconnecting to Workshop OS';copy.textContent='Keep the phone on the same local Wi‑Fi. Controls remain disabled until fresh state returns.';badge.textContent='Stale';badge.classList.add('bad');return}
  if(conn.indexOf('printer offline')>=0){title.textContent='Waveshare online · printer offline';copy.textContent='The display is reachable, but the configured printer is not currently connected.';badge.textContent='Check';badge.classList.add('warn');return}
  if(state.toLowerCase().indexOf('paused')>=0){title.textContent='Print paused';copy.textContent='Review the printer, then use Resume below when the physical condition is safe.';badge.textContent='Paused';badge.classList.add('warn');return}
  if(state.toLowerCase().indexOf('printing')>=0){title.textContent='Print in progress';copy.textContent=txt('progressText','—')+' complete · '+txt('remaining','—')+' remaining · state '+fresh+'.';badge.textContent='Live';badge.classList.add('good');return}
  title.textContent='Workshop ready';copy.textContent='Printer and device state are current. Quick controls, photo handoff and system details are below.';badge.textContent='Ready';badge.classList.add('good');
}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',function(){build();update();setInterval(update,900)});else{build();update();setInterval(update,900)}
})();
</script>
'''


def patch_build(root: Path) -> None:
    rel = "include/smart_home_build.h"
    text = load(root, rel)
    text = once(text, '#define SMART_HOME_VERSION "v11.29"', '#define SMART_HOME_VERSION "v11.30"', "version")
    text = once(text, '#define SMART_HOME_PROFILE "acceptance-open-lan"', '#define SMART_HOME_PROFILE "unified-web-companion"', "profile")
    text = once(text, 'Smart Home v11.29 Acceptance Open LAN RC1', 'Smart Home v11.30 Unified Web + Companion RC1', "build label")
    text += f"\n// {MARKER}\n"
    save(root, rel, text)


def patch_standard_web(root: Path) -> None:
    rel = "web/app.js"
    text = load(root, rel)
    if "Workshop OS v11.30 Unified Web + Companion UX" not in text:
        text = once(text, "function v1129AcceptanceOpenLanBanner(){", STANDARD_WEB_JS + "function v1129AcceptanceOpenLanBanner(){", "standard-web unified rail")
    ota_anchor = "  stopPolling();\n  var xhr = new XMLHttpRequest();\n"
    ota_replacement = "  stopPolling();\n  if (window.v1130PauseLiveRail) window.v1130PauseLiveRail(true);\n  var xhr = new XMLHttpRequest();\n  xhr.addEventListener('loadend', function(){ if ((xhr.status < 200 || xhr.status >= 300) && window.v1130PauseLiveRail) window.v1130PauseLiveRail(false); });\n"
    if "v1130PauseLiveRail(true)" not in text:
        text = once(text, ota_anchor, ota_replacement, "pause unified rail during OTA")
    save(root, rel, text)


def patch_companion(root: Path) -> None:
    rel = "src/companion_web.cpp"
    text = load(root, rel)
    if "v11.30 Companion refinement" not in text:
        text = once(text, "</style>\n</head>", COMPANION_CSS + "</style>\n</head>", "Companion responsive refinement")
    if "v1130CompanionEnhance" not in text:
        text = once(text, "</body>\n</html>", COMPANION_JS + "</body>\n</html>", "Companion attention/navigation enhancement")
    text = text.replace("Physical Companion Viewer · v11.28 candidate", "Unified Web + Companion · v11.30 candidate")
    save(root, rel, text)


def apply(root: Path) -> None:
    build = load(root, "include/smart_home_build.h")
    if MARKER in build:
        print(f"{MARKER} already applied")
        return
    if 'SMART_HOME_VERSION "v11.29"' not in build:
        raise PatchError("v11.30 requires reconstructed v11.29 Acceptance Open LAN source")
    patch_standard_web(root)
    patch_companion(root)
    patch_build(root)

    checks = {
        "include/smart_home_build.h": [
            'SMART_HOME_VERSION "v11.30"',
            'SMART_HOME_PROFILE "unified-web-companion"',
            'Smart Home v11.30 Unified Web + Companion RC1',
            '#define WORKSHOP_OS_ACCEPTANCE_OPEN_LAN 1',
        ],
        "web/app.js": [
            'Workshop OS v11.30 Unified Web + Companion UX',
            'v1130UnifiedRail',
            'v1130-mobile-dock',
            "'/companion/state?slot=0&_='",
            'window.v1130PauseLiveRail',
            "v1130PauseLiveRail(true)",
            "href='/companion'",
        ],
        "src/companion_web.cpp": [
            'v11.30 Companion refinement',
            'v1130CompanionEnhance',
            'Workshop Companion',
            'Overview', 'Controls', 'Photo', 'System',
            'v1130AttentionCard',
            'Unified Web + Companion · v11.30 candidate',
            'server.on("/companion/capture/show", HTTP_POST',
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
    apply(Path(args.repo).resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
