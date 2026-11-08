/* Profile capabilities: initialised before any boot path reads them. */
var _profileCaps = {};
/* ============ Loader / section dispatcher ============ */
var SECTION_LABELS = {
  home: 'Home',
  printer: 'Printer',
  workshop: 'Workshop',
  display: 'Display & Experience',
  errors: 'Printer Errors',
  hardware: 'Sound & Hardware',
  advanced: 'Advanced',
  wifi: 'Network & Updates',
  power: 'Power & Automation',
  diag: 'Diagnostics'
};
var currentSection = null;
function loadSection(id){
  if (id === currentSection) return;
  var sections = document.querySelectorAll('.section');
  for (var i = 0; i < sections.length; i++) {
    var sid = sections[i].id;  // sec-printer etc.
    sections[i].hidden = (sid !== 'sec-' + id);
  }
  currentSection = id;
  var title = SECTION_LABELS[id] || id;
  document.title = 'Waveshare Home — ' + title;
  var st = document.getElementById('sectionTitle');
  if (st) st.textContent = title;
  var navs = document.querySelectorAll('.nav-item');
  for (var j = 0; j < navs.length; j++) {
    navs[j].setAttribute('aria-current', navs[j].dataset.section === id ? 'true' : 'false');
  }
  document.getElementById('sidebar').classList.remove('open');
  document.getElementById('scrim').classList.remove('show');
  window.scrollTo(0, 0);
  try { localStorage.setItem('bambu_section', id); } catch(e){}
  if (location.hash !== '#' + id) {
    try { history.replaceState(null, '', '#' + id); } catch(e){}
  }
  startPolling(id);
  if (ccTimer && id !== 'home') { clearInterval(ccTimer); ccTimer = null; }
  if (id !== 'workshop' && typeof v117StopWorkshopPolling === 'function') v117StopWorkshopPolling();
  if (id === 'home') { refreshCommandCenter(false); if (ccTimer) clearInterval(ccTimer); ccTimer = setInterval(function(){ refreshCommandCenter(false); }, 5000); }
  if (id === 'workshop' && typeof v117StartWorkshopPolling === 'function') v117StartWorkshopPolling();
}

var navBtns = document.querySelectorAll('.nav-item');
for (var b = 0; b < navBtns.length; b++){
  navBtns[b].addEventListener('click', function(){ loadSection(this.dataset.section); });
}

/* ============ Theme toggle ============ */
/* Pure DOM mutation. Persistence happens only on explicit user click below,
   so an OS-detected preference on first load is not stamped into storage
   (which would freeze it and stop auto-following OS theme changes). */
function applyThemeMode(theme){
  document.documentElement.setAttribute('data-theme', theme);
  document.getElementById('iconSun').style.display = (theme === 'dark') ? '' : 'none';
  document.getElementById('iconMoon').style.display = (theme === 'dark') ? 'none' : '';
}
document.getElementById('themeToggle').addEventListener('click', function(){
  var cur = document.documentElement.getAttribute('data-theme');
  var next = (cur === 'dark') ? 'light' : 'dark';
  applyThemeMode(next);
  try { localStorage.setItem('bh-theme', next); } catch(e){}
});

/* ============ Mobile drawer ============ */
document.getElementById('hamburger').addEventListener('click', function(){
  document.getElementById('sidebar').classList.toggle('open');
  document.getElementById('scrim').classList.toggle('show');
});
document.getElementById('scrim').addEventListener('click', function(){
  document.getElementById('sidebar').classList.remove('open');
  document.getElementById('scrim').classList.remove('show');
});
document.addEventListener('keydown', function(e){
  if (e.key !== 'Escape') return;
  document.getElementById('sidebar').classList.remove('open');
  document.getElementById('scrim').classList.remove('show');
});

/* ============ Toast ============ */
var _toastTimer = null;
function showToast(msg){
  var t = document.getElementById('toast');
  t.textContent = msg || 'Applied!';
  t.classList.add('show');
  clearTimeout(_toastTimer);
  _toastTimer = setTimeout(function(){ t.classList.remove('show'); }, msg && msg.length > 40 ? 5000 : 2000);
}

/* ============ HTML escape ============ */
function esc(s){var d=document.createElement('div');d.appendChild(document.createTextNode(s));return d.innerHTML;}

/* ============ Polling ============ */
var diagTimer = null, statsTimer = null, powerTimer = null, hwTimer = null;
function startPolling(id){
  stopPolling();
  if (id === 'diag') { refreshDiag(); diagTimer = setInterval(refreshDiag, 5000); }
  if (id === 'printer') { refreshLiveStats(); statsTimer = setInterval(refreshLiveStats, 3000); }
  /* Errors move on their own schedule, not the user's - 5 s is plenty, and it
     is four slot fetches per tick. */
  if (id === 'errors') { refreshErrorCard(); statsTimer = setInterval(refreshErrorCard, 5000); }
  if (id === 'power') { refreshPowerStats(); powerTimer = setInterval(refreshPowerStats, 5000); }
  if (id === 'hardware' || id === 'wifi') { refreshHwInfo(); hwTimer = setInterval(refreshHwInfo, 5000); }
}
function stopPolling(){
  if (ccTimer) { clearInterval(ccTimer); ccTimer = null; }
  if (diagTimer) { clearInterval(diagTimer); diagTimer = null; }
  if (statsTimer) { clearInterval(statsTimer); statsTimer = null; }
  if (powerTimer) { clearInterval(powerTimer); powerTimer = null; }
  if (hwTimer) { clearInterval(hwTimer); hwTimer = null; }
}

/* ============ Brightness debounce ============ */
var _brightTimer = null;
function sendBrightness(val){ clearTimeout(_brightTimer); _brightTimer = setTimeout(function(){ fetch('/brightness?val=' + encodeURIComponent(val),{method:'POST'}); }, 150); }

/* ============ Gauge slot type labels (must match GaugeType enum in settings.h) ============
   Array index = numeric gauge ID. Empty `group` renders ungrouped at the top
   of the dropdown; named groups render as <optgroup> blocks in the order the
   first member of each group appears below. */
var gaugeTypes = [
  {name:'-- Empty --',        group:''},                  /*  0 */
  {name:'Progress',           group:'Print status'},      /*  1 */
  {name:'Nozzle Temp',        group:'Temperatures'},      /*  2 */
  {name:'Bed Temp',           group:'Temperatures'},      /*  3 */
  {name:'Part Fan',           group:'Fans'},              /*  4 */
  {name:'Aux Fan',            group:'Fans'},              /*  5 */
  {name:'Chamber Fan',        group:'Fans'},              /*  6 */
  {name:'Chamber Temp',       group:'Temperatures'},      /*  7 */
  {name:'Heatbreak Fan',      group:'Fans'},              /*  8 */
  {name:'Clock',              group:'Other'},             /*  9 */
  {name:'AMS 1 Humidity',     group:'AMS humidity'},      /* 10 */
  {name:'AMS 2 Humidity',     group:'AMS humidity'},      /* 11 */
  {name:'AMS 3 Humidity',     group:'AMS humidity'},      /* 12 */
  {name:'AMS 4 Humidity',     group:'AMS humidity'},      /* 13 */
  {name:'Layer Progress',     group:'Print status'},      /* 14 */
  {name:'AMS 1 Temp',         group:'AMS temperature'},   /* 15 */
  {name:'AMS 2 Temp',         group:'AMS temperature'},   /* 16 */
  {name:'AMS 3 Temp',         group:'AMS temperature'},   /* 17 */
  {name:'AMS 4 Temp',         group:'AMS temperature'},   /* 18 */
  {name:'AMS 1 Filament',     group:'AMS filament (quad)'},/* 19 */
  {name:'AMS 2 Filament',     group:'AMS filament (quad)'},/* 20 */
  {name:'AMS 3 Filament',     group:'AMS filament (quad)'},/* 21 */
  {name:'AMS 4 Filament',     group:'AMS filament (quad)'},/* 22 */
  {name:'Aux Fan Right (X2D)',group:'Fans'},              /* 23 */
  {name:'Exhaust Fan',        group:'Fans'},              /* 24 */
  {name:'AMS 1 Bars',         group:'AMS filament (bars)'},/* 25 */
  {name:'AMS 2 Bars',         group:'AMS filament (bars)'},/* 26 */
  {name:'AMS 3 Bars',         group:'AMS filament (bars)'},/* 27 */
  {name:'AMS 4 Bars',         group:'AMS filament (bars)'},/* 28 */
  {name:'Nozzle R Temp',      group:'Temperatures'},      /* 29 */
  {name:'Nozzle L Temp',      group:'Temperatures'},      /* 30 */
  {name:'Power',              group:'Other'},             /* 31 */
  {name:'Camera (P1/A1 LAN)', group:'Other'}              /* 32 */
];
var GAUGE_REQUIRES = { 23: 'hasAuxFanRight', 24: 'hasExhaustFan', 29: 'hasDualNozzle', 30: 'hasDualNozzle', 31: 'hasTasmota', 32: 'hasLanCamera' };
var gaugeCaps = {}, persistedGauges = {};
function gaugeAllowed(idx){
  if (persistedGauges[idx]) return true;
  var req = GAUGE_REQUIRES[idx];
  if (req) return !!gaugeCaps[req];
  return true;
}
var GAUGE_CAMERA_ID = 32;  // keep in sync with GAUGE_CAMERA in settings.h
function rebuildGaugeOptions(){
  // Build ungrouped + groups once, then clone into each <select>.
  // groups[] preserves first-seen order; groupMembers[g] is a list of {i, name}.
  var ungrouped = [];
  var groups = [];
  var groupMembers = {};
  gaugeTypes.forEach(function(gt, i){
    if (!gaugeAllowed(i)) return;
    if (!gt.group) { ungrouped.push({i:i, name:gt.name}); return; }
    if (!groupMembers[gt.group]) { groups.push(gt.group); groupMembers[gt.group] = []; }
    groupMembers[gt.group].push({i:i, name:gt.name});
  });
  var sels = document.querySelectorAll('.gauge-slot-sel');
  sels.forEach(function(sel){
    // Ready / Print complete slots cannot host the camera: that tile paints on
    // its own cadence and the stream only starts for a print-grid slot, so it
    // would sit frozen. Filtered here because this runs again on every capability
    // refresh and tab switch - removing the option once would not stick.
    var isIdleSel = (sel.id === 'is0' || sel.id === 'is1');
    var cur = sel.value;
    sel.innerHTML = '';
    ungrouped.forEach(function(e){
      if (isIdleSel && e.i === GAUGE_CAMERA_ID) return;
      var o = document.createElement('option');
      o.value = e.i; o.textContent = e.name;
      sel.appendChild(o);
    });
    groups.forEach(function(g){
      var og = document.createElement('optgroup');
      og.label = g;
      groupMembers[g].forEach(function(e){
        if (isIdleSel && e.i === GAUGE_CAMERA_ID) return;
        var o = document.createElement('option');
        o.value = e.i; o.textContent = e.name;
        og.appendChild(o);
      });
      if (og.children.length) sel.appendChild(og);
    });
    if (cur !== '') sel.value = cur;
  });
}
rebuildGaugeOptions();

/* Round boards (GC9A01): the printing dashboard has no 2x3 grid. Only the Rim
   skin renders gauges - three mini slots fed from gaugeSlots[0..2] - so the
   card re-labels itself and hides the bottom row. gs3-gs5 stay in the DOM
   (hidden) so saveGaugeLayout keeps posting all six slots unchanged.
   The is0/is1 pair drives the round Ready screen only: the round Print
   complete screen is a fixed layout (checkmark, headline, file name, energy)
   with no room for the two gauges, so the divider says so rather than
   promising a screen that ignores the setting. */
var IS_ROUND = DEV.round === '1';
if (IS_ROUND){
  var gd = document.getElementById('glDesc');
  if (gd) gd.innerHTML = 'Per-printer mini gauges for the round <em>Rim</em> skin: left, center and right slot. The <em>Speedo</em> and <em>Rings</em> skins have fixed layouts. The last pair is the two gauges on the <em>Ready</em> screen - the round <em>Print complete</em> screen has a fixed layout and does not use them. Set a slot to <em>Empty</em> to hide it.';
  var ipd = document.getElementById('idlePairDivider');
  if (ipd) ipd.innerHTML = '&#9670; Ready screen';
  var roundLbls = ['Left gauge','Center gauge','Right gauge'];
  for (var ri = 0; ri < 3; ri++){
    var rsel = document.getElementById('gs' + ri);
    if (rsel){ var rlb = rsel.parentNode.querySelector('label'); if (rlb) rlb.textContent = roundLbls[ri]; }
  }
  var trd = document.getElementById('topRowDivider'); if (trd) trd.style.display = 'none';
  var brg = document.getElementById('bottomRowGroup'); if (brg) brg.style.display = 'none';
}

function refreshGaugeCaps(){
  Promise.all([0,1].map(function(slot){
    return fetch('/printer/config?slot=' + slot).then(function(r){return r.json();}).catch(function(){return {};});
  })).then(function(arr){
    var changed = false;
    Object.keys(GAUGE_REQUIRES).forEach(function(idx){
      var capName = GAUGE_REQUIRES[idx];
      var v = arr.some(function(d){ return d && d[capName]; });
      if (v !== !!gaugeCaps[capName]){ gaugeCaps[capName] = v; changed = true; }
    });
    arr.forEach(function(d){
      if (!d) return;
      ['gaugeSlots','landscapeExtras','portraitExtras','idleSlots'].forEach(function(key){
        if (!Array.isArray(d[key])) return;
        d[key].forEach(function(v){
          if (!persistedGauges[v]) { persistedGauges[v] = true; changed = true; }
        });
      });
    });
    if (changed) rebuildGaugeOptions();
    refreshGaugeProfileUi();
  });
}
refreshGaugeCaps();
setTimeout(refreshGaugeProfileUi, 0);

function resetGaugeLayout(){
  // Standard 2x3 grid -> Progress/Nozzle/Bed/PartFan/AuxFan/ChamberFan.
  // Round Rim skin -> Nozzle/Bed/PartFan (the original fixed layout).
  // Both extras arrays default to Empty (user opts in via mode toggles).
  var d = IS_ROUND ? [2,3,4,0,0,0] : [1,2,3,4,5,6];
  for (var i = 0; i < 6; i++) { var s = document.getElementById('gs' + i); if (s) s.value = d[i]; }
  var lx = ['lx0','lx1'], px = ['px0','px1','px2'];
  lx.forEach(function(id){ var s = document.getElementById(id); if (s) s.value = 0; });
  px.forEach(function(id){ var s = document.getElementById(id); if (s) s.value = 0; });
  // Ready / Print complete -> Nozzle/Bed, what those screens always drew.
  var di = [2,3];
  for (var i = 0; i < 2; i++) { var s = document.getElementById('is' + i); if (s) s.value = di[i]; }
  showToast('Restored layout defaults');
}
function saveGaugeLayout(){
  var p = new URLSearchParams();
  p.append('slot', currentSlot);
  for (var g = 0; g < 6; g++) { var s = document.getElementById('gs' + g); if (s) p.append('gs' + g, s.value); }
  for (var g = 0; g < 2; g++) { var s = document.getElementById('lx' + g); if (s) p.append('lx' + g, s.value); }
  for (var g = 0; g < 3; g++) { var s = document.getElementById('px' + g); if (s) p.append('px' + g, s.value); }
  for (var g = 0; g < 2; g++) { var s = document.getElementById('is' + g); if (s) p.append('is' + g, s.value); }
  var av = document.getElementById('amsv');
  if (av && av.checked) p.append('amsv', '1');
  fetch('/save/gaugelayout',{method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded'},body:p.toString()})
    .then(function(r){return r.json();})
    .then(function(d){if(d.status==='ok')showToast('Gauge layout saved!');else showToast('Error');})
    .catch(function(){showToast('Save failed');});
}

/* ============ Chamber light ============ */
function renderLightState(v){
  var el = document.getElementById('lightStateLbl');
  if (!el) return;
  if (v === 1) { el.className = 'status-pill status-ok'; el.textContent = 'Light: On'; }
  else if (v === 0) { el.className = 'status-pill status-off'; el.textContent = 'Light: Off'; }
  else { el.className = 'status-pill status-na'; el.textContent = 'Light: -'; }
}
function refreshLightState(){
  fetch('/printer/config?slot=' + currentSlot).then(function(r){return r.json();})
    .then(function(d){ renderLightState(d.lightState); }).catch(function(){});
}
function saveLightConfig(){
  var p = new URLSearchParams();
  p.append('slot', currentSlot);
  if (document.getElementById('loff_fin').checked)  p.append('loff_fin', '1');
  if (document.getElementById('loff_fail').checked) p.append('loff_fail', '1');
  if (document.getElementById('lon_start').checked) p.append('lon_start', '1');
  p.append('ldelay', document.getElementById('ldelay').value);
  fetch('/light/config',{method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded'},body:p.toString()})
    .then(function(r){return r.json();})
    .then(function(d){if(d.status==='ok')showToast('Light settings saved!');else showToast('Error');})
    .catch(function(){showToast('Save failed');});
}
function setLight(mode){
  var p = new URLSearchParams();
  p.append('slot', currentSlot);
  p.append('mode', mode);
  fetch('/light/set',{method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded'},body:p.toString()})
    .then(function(r){return r.json();})
    .then(function(d){
      if (d.status === 'ok'){
        showToast(mode === 'on' ? 'Light on sent' : 'Light off sent');
        setTimeout(refreshLightState, 1500);  // confirm from next lights_report
      } else showToast('Error');
    })
    .catch(function(){showToast('Command failed');});
}

/* ============ Printer tabs ============ */
var currentSlot = 0;
function selectPrinterTab(slot){
  currentSlot = slot;
  var btns = document.querySelectorAll('.tab-btn');
  for (var i = 0; i < btns.length; i++) btns[i].classList.toggle('active', i === slot);
  var reqSlot = slot;
  fetch('/printer/config?slot=' + slot).then(function(r){return r.json();}).then(function(d){
    if (reqSlot !== currentSlot) return;
    document.getElementById('connmode').value = d.mode;
    document.getElementById('pname').value = d.name || '';
    document.getElementById('ip').value = d.ip || '';
    document.getElementById('serial').value = d.serial || '';
    document.getElementById('code').value = d.code || '';
    document.getElementById('cl_serial').value = d.serial || '';
    document.getElementById('cl_pname').value = d.name || '';
    // The picker merged US and EU into one entry, but devices configured before
    // that still report 'eu' - without this the select would end up on nothing.
    document.getElementById('region').value = (d.region === 'eu') ? 'us' : (d.region || 'us');
    document.getElementById('cl_token').value = '';
    var capsChanged = false;
    Object.keys(GAUGE_REQUIRES).forEach(function(idx){
      var capName = GAUGE_REQUIRES[idx];
      if (d[capName] && !gaugeCaps[capName]){ gaugeCaps[capName] = true; capsChanged = true; }
    });
    // Keep options for gauges this printer has saved even when it is offline and
    // its capability flags say otherwise - otherwise the select renders empty and
    // the next save silently downgrades the slot to Empty.
    ['gaugeSlots','idleSlots'].forEach(function(key){
      if (!d[key]) return;
      d[key].forEach(function(v){
        if (!persistedGauges[v]){ persistedGauges[v] = true; capsChanged = true; }
      });
    });
    if (capsChanged) rebuildGaugeOptions();
    if (d.gaugeSlots) { for (var g = 0; g < 6; g++) { var sel = document.getElementById('gs' + g); if (sel) sel.value = d.gaugeSlots[g] || 0; } }
    if (d.landscapeExtras) { for (var g = 0; g < 2; g++) { var sel = document.getElementById('lx' + g); if (sel) sel.value = d.landscapeExtras[g] || 0; } }
    if (d.portraitExtras)  { for (var g = 0; g < 3; g++) { var sel = document.getElementById('px' + g); if (sel) sel.value = d.portraitExtras[g] || 0; } }
    if (d.idleSlots)       { for (var g = 0; g < 2; g++) { var sel = document.getElementById('is' + g); if (sel) sel.value = d.idleSlots[g] || 0; } }
    var av = document.getElementById('amsv');
    if (av) { av.checked = !!d.amsView; syncAmsView(); }
    var lf = d.lightFlags || 0;
    document.getElementById('loff_fin').checked  = !!(lf & 1);
    document.getElementById('loff_fail').checked = !!(lf & 2);
    document.getElementById('lon_start').checked = !!(lf & 4);
    if (typeof d.lightDelay === 'number') document.getElementById('ldelay').value = d.lightDelay;
    renderLightState(d.lightState);
    toggleConnMode();
    var ps = document.getElementById('printerStatus');
    if (d.connected) { ps.className = 'status-pill status-ok'; ps.textContent = 'Connected'; }
    else if (d.configured) { ps.className = 'status-pill status-off'; ps.textContent = 'Disconnected'; }
    else { ps.className = 'status-pill status-na'; ps.textContent = 'Not Configured'; }
    updatePrinterOnboarding();
    updateHealthPanel(d);
    setCurrentProfileCaps(d);
  }).catch(function(e){console.warn('selectPrinterTab:', e);updateHealthPanel(null);});
}

function syncAmsView(){
  var cb = document.getElementById('amsv');
  var bg = document.getElementById('bottomRowGroup');
  if (bg) bg.style.display = (cb && cb.checked) ? 'none' : '';
}

/* ============ Misc ============ */
function readJsonResponse(r){
  return r.text().then(function(text){
    var data = {};
    if (text) { try { data = JSON.parse(text); } catch(e) { data = {message: text}; } }
    data._httpOk = r.ok; data._httpStatus = r.status;
    return data;
  });
}
function isValidIpv4(v){
  if (!v) return false;
  var m = v.match(/^(\d{1,3})(\.\d{1,3}){3}$/);
  if (!m) return false;
  var parts = v.split('.');
  for (var i = 0; i < parts.length; i++) { var n = parseInt(parts[i], 10); if (n < 0 || n > 255) return false; }
  return true;
}
function toggleStatic(){
  var m = document.getElementById('netmode').value;
  document.getElementById('staticFields').style.display = (m === 'static') ? 'block' : 'none';
}
function setPrinterSetupStep(id, state, detail){
  var el = document.getElementById(id);
  if (!el) return;
  el.setAttribute('data-state', state);
  var sm = el.querySelector('small');
  if (sm && detail) sm.textContent = detail;
}
function setPrinterSaveState(message, kind){
  var el = document.getElementById('printerSaveState');
  if (!el) return;
  el.textContent = message || '';
  el.className = 'action-status' + (kind ? ' ' + kind : '');
}
function cloudAccessReady(){
  var cs = document.getElementById('cloudStatus');
  var token = document.getElementById('cl_token');
  return !!((cs && (cs.textContent || '').indexOf('Token active') !== -1) ||
            (token && token.value.trim().length > 0));
}
function updatePrinterOnboarding(){
  var modeEl = document.getElementById('connmode');
  if (!modeEl) return;
  var mode = modeEl.value, cloud = mode === 'cloud_all';
  var guide = document.getElementById('connectionGuidance');

  setPrinterSetupStep('setupStepConnection','done',cloud?'Bambu Cloud selected':'LAN selected');
  if (guide){
    guide.innerHTML = cloud
      ? '<strong>Bambu Cloud:</strong> best when the printer is on another network, you do not want to enable LAN/Developer Mode, or the printer only supports cloud status. Email code is the recommended account sign-in path.'
      : '<strong>LAN:</strong> fastest and stays local. The ESP32 and printer must be reachable on the network, and you need the printer IP, serial number, and LAN access code.';
  }

  var accessReady=false, printerReady=false;
  if (cloud){
    accessReady=cloudAccessReady();
    var cser=document.getElementById('cl_serial'), cnam=document.getElementById('cl_pname');
    printerReady=!!(cser&&cser.value.trim()&&cnam&&cnam.value.trim());
  } else {
    var ip=document.getElementById('ip'), ser=document.getElementById('serial');
    var code=document.getElementById('code'), nam=document.getElementById('pname');
    accessReady=!!(ip&&isValidIpv4(ip.value.trim())&&code&&(code.value.trim().length===0||code.value.trim().length===8));
    printerReady=!!(ser&&ser.value.trim()&&nam&&nam.value.trim());
  }

  setPrinterSetupStep('setupStepAccess',accessReady?'done':'active',
    accessReady?(cloud?'Cloud authorized':'LAN details ready'):(cloud?'Sign in or paste token':'Enter network access'));
  setPrinterSetupStep('setupStepPrinter',printerReady?'done':(accessReady?'active':'pending'),
    printerReady?'Printer selected':'Select printer');

  var ps=document.getElementById('printerStatus');
  var statusText=ps?(ps.textContent||''):'';
  if (statusText==='Connected'){
    setPrinterSetupStep('setupStepVerify','done','Connected');
    setPrinterSaveState('Printer is connected and reporting status.','ok');
  } else if (statusText==='Disconnected'){
    setPrinterSetupStep('setupStepVerify','active','Saved; reconnecting');
  } else {
    setPrinterSetupStep('setupStepVerify',printerReady&&accessReady?'active':'pending',
      printerReady&&accessReady?'Ready to save':'Save and connect');
  }
}
var _printerOnboardingWired=false;
function wirePrinterOnboarding(){
  if (_printerOnboardingWired) return;
  _printerOnboardingWired=true;
  ['connmode','pname','ip','serial','code','region','cl_token','cl_serial','cl_pname','cl_email'].forEach(function(id){
    var el=document.getElementById(id);
    if (!el) return;
    el.addEventListener('input',updatePrinterOnboarding);
    el.addEventListener('change',updatePrinterOnboarding);
  });
  updatePrinterOnboarding();
}
function toggleConnMode(){
  var v=document.getElementById('connmode').value;
  var cloud=(v==='cloud_all');
  document.getElementById('localFields').style.display=cloud?'none':'block';
  document.getElementById('cloudFields').style.display=cloud?'block':'none';
  updatePrinterOnboarding();
  refreshGaugeProfileUi();
  refreshPrinterHealth(false);
}
setTimeout(wirePrinterOnboarding,0);

/* ============ Save printer ============ */
function savePrinter(){
  var p = new URLSearchParams();
  p.append('slot', currentSlot);
  var mode = document.getElementById('connmode').value;
  var nameField = mode === 'cloud_all' ? document.getElementById('cl_pname') : document.getElementById('pname');
  var serialField = mode === 'cloud_all' ? document.getElementById('cl_serial') : document.getElementById('serial');
  var serial = serialField.value.trim().toUpperCase();
  // Fallback: if the field is empty but a scan dropdown still has a selection,
  // use it (covers the case where the field got cleared after picking).
  if (serial.length === 0){
    var dsel = document.getElementById(mode === 'cloud_all' ? 'cl_devsel' : 'lan_devsel');
    if (dsel && dsel.value){ serial = dsel.value.trim().toUpperCase(); serialField.value = serial; }
  }
  var token = document.getElementById('cl_token').value.trim();
  if (nameField && nameField.value.trim().length === 0) { showToast('Printer name is required'); return; }
  if (serial.length === 0) { showToast(mode === 'cloud_all' ? 'Cloud mode requires a printer serial number' : 'LAN mode requires a printer serial number'); return; }
  p.append('connmode', mode);
  if (mode === 'cloud_all'){
    var cloudStatus = document.getElementById('cloudStatus').textContent || '';
    if (token.length === 0 && cloudStatus.indexOf('Token active') === -1) { showToast('Cloud mode requires a valid token'); return; }
    p.append('serial', serial);
    p.append('pname', nameField.value.trim());
    p.append('region', document.getElementById('region').value);
    if (token) p.append('token', token);
  } else {
    var ip = document.getElementById('ip').value.trim();
    var code = document.getElementById('code').value.trim();
    if (ip.length === 0) { showToast('LAN mode requires a printer IP address'); return; }
    if (!isValidIpv4(ip)) { showToast('Printer IP address is not valid'); return; }
    if (code.length > 0 && code.length !== 8) { showToast('LAN access code should be 8 characters'); return; }
    p.append('pname', nameField.value.trim());
    p.append('ip', ip);
    p.append('serial', serial);
    p.append('code', code);
  }
  var saveBtn=document.getElementById('savePrinterBtn');
  if(saveBtn){saveBtn.disabled=true;saveBtn.textContent='Saving...';}
  setPrinterSaveState('Saving printer settings...','');
  fetch('/save/printer',{method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded'},body:p.toString()})
    .then(readJsonResponse)
    .then(function(d){
      if(d.status==='ok'){
        if(d.warning)showToast('Saved with warning: '+d.warning);else showToast('Printer settings saved');
        setPrinterSaveState(d.warning?'Saved with warning. Verifying connection...':'Saved. Verifying connection...',d.warning?'warn':'');
        setPrinterSetupStep('setupStepVerify','active','Verifying connection');
        setTimeout(verifyPrinterSetup,1200);
      }else{
        var msg=d.message?'Save failed: '+d.message:'Save failed';
        showToast(msg);setPrinterSaveState(msg,'error');
        setPrinterSetupStep('setupStepVerify','error','Save failed');
      }
    })
    .catch(function(e){
      showToast('Save failed: network error');
      setPrinterSaveState('Save failed: network error','error');
      setPrinterSetupStep('setupStepVerify','error','Network error');
      console.warn('savePrinter:',e);
    })
    .then(function(){if(saveBtn){saveBtn.disabled=false;saveBtn.textContent='Save & Verify';}});
}

function verifyPrinterSetup(){
  var btn=document.getElementById('verifyPrinterBtn');
  if(btn){btn.disabled=true;btn.textContent='Checking...';}
  setPrinterSaveState('Checking printer connection...','');
  setPrinterSetupStep('setupStepVerify','active','Checking status');
  fetch('/printer/config?slot='+currentSlot,{cache:'no-store'})
    .then(function(r){if(!r.ok)throw new Error('HTTP '+r.status);return r.json();})
    .then(function(d){
      var ps=document.getElementById('printerStatus');
      if(d.connected){
        if(ps){ps.className='status-pill status-ok';ps.textContent='Connected';}
        setPrinterSetupStep('setupStepVerify','done','Connected');
        setPrinterSaveState('Connected. BambuHelper is receiving printer status.','ok');
        recordVerifiedNow();
        updateHealthPanel(d);
        showToast('Printer connection verified');
      }else if(d.configured){
        if(ps){ps.className='status-pill status-off';ps.textContent='Disconnected';}
        setPrinterSetupStep('setupStepVerify','active','Saved; not connected yet');
        setPrinterSaveState('Settings are saved, but the printer is not connected yet. Check network/account access and try again.','warn');
        updateHealthPanel(d);
      }else{
        if(ps){ps.className='status-pill status-na';ps.textContent='Not Configured';}
        setPrinterSetupStep('setupStepVerify','error','Not configured');
        setPrinterSaveState('Printer settings are not configured.','error');
        updateHealthPanel(d);
      }
      updatePrinterOnboarding();
    })
    .catch(function(e){
      setPrinterSetupStep('setupStepVerify','error','Check failed');
      setPrinterSaveState('Could not read printer status from BambuHelper.','error');
      updateHealthPanel(null);
      console.warn('verifyPrinterSetup:',e);
    })
    .then(function(){if(btn){btn.disabled=false;btn.textContent='Verify Connection';}});
}

function cloudLogout(){
  fetch('/cloud/logout',{method:'POST'}).then(function(){
    var cs = document.getElementById('cloudStatus');
    cs.style.color = 'var(--text-mid)'; cs.textContent = 'No token set';
    document.getElementById('cl_token').value = '';
    var pw = document.getElementById('cl_pass');
    if (pw) { pw.value = ''; document.getElementById('cl_savePass').checked = false; }
    var msg = document.getElementById('cl_loginMsg');
    if (msg) { msg.textContent = 'Signed out.'; msg.style.color = 'var(--text-mid)'; }
    var wrap = document.getElementById('cl_codeWrap');
    if (wrap) wrap.style.display = 'none';
    // The picker still lists the account we just signed out of.
    var sel = document.getElementById('cl_acctsel');
    if (sel) { sel.innerHTML = ''; sel.style.display = 'none'; }
    var summary = document.getElementById('cl_printerSummary');
    if (summary) { summary.hidden = true; summary.textContent = ''; }
    updatePrinterOnboarding();
  });
}



var clLoginMode = 'code';

/* This file is shared by every board, but the sign-in markup is not: boards
   without the flow render the token block alone and no method picker. Bail out
   whenever the picker is absent, or the token block - the only way in on those
   boards - would get hidden with nothing to replace it. */
function clHasSignIn(){ return !!document.getElementById('cl_method'); }

function clSetAuthMethod(m){
  if (!clHasSignIn()) return;
  document.getElementById('cl_signinWrap').style.display = (m === 'signin') ? '' : 'none';
  document.getElementById('cl_tokenWrap').style.display  = (m === 'signin') ? 'none' : '';
  updatePrinterOnboarding();
}

function clInitAuthUi(){
  if (!clHasSignIn()) return;
  clSetAuthMethod('signin');
  clSetLoginMode('code');
  fetch('/cloud/login/status').then(function(r){return r.json();}).then(function(d){
    if (d.email) document.getElementById('cl_email').value = d.email;
    if (d.saved_password) document.getElementById('cl_savePass').checked = true;

    // A sign-in left waiting for a code, or a background renewal that gave up,
    // is device state the page has to show - nothing else polls for it, so
    // without this the user only learns about it by trying something.
    if (d.state === 'need_tfa' || d.state === 'need_email_code' || d.failed){
      clApplyLoginState(d);
      return;
    }
    if (d.has_token && d.email){
      document.getElementById('cl_loginMsg').textContent = 'Signed in as ' + d.email;
    }
  }).catch(function(){});
}

function clSetLoginMode(m){
  // Smart Home v8.3: the local portal is email-code only.
  clLoginMode = 'code';
  var passBtn = document.getElementById('cl-mode-pass-btn');
  var codeBtn = document.getElementById('cl-mode-code-btn');
  var passWrap = document.getElementById('cl_passWrap');
  if (passBtn) { passBtn.setAttribute('aria-pressed', 'false'); passBtn.disabled = true; passBtn.style.display = 'none'; }
  if (codeBtn) codeBtn.setAttribute('aria-pressed', 'true');
  if (passWrap) passWrap.style.display = 'none';
  var signBtn = document.getElementById('cl_signinBtn');
  if (signBtn) signBtn.textContent = 'Email me a code';
}

// One place decides what the sign-in box shows, so the password step and the
// code step cannot disagree about the current state.
function clApplyLoginState(d){
  var msg = document.getElementById('cl_loginMsg');
  var wrap = document.getElementById('cl_codeWrap');
  msg.textContent = d.message || '';
  // A refused code leaves the device waiting on the same step, so the state
  // stays 'need_*' while the message is a complaint - the device says which.
  msg.style.color = (d.failed || d.state === 'failed') ? 'var(--warn)' : 'var(--text-mid)';

  if (d.state === 'need_tfa' || d.state === 'need_email_code'){
    wrap.style.display = '';
    document.getElementById('cl_codeLabel').textContent =
      (d.state === 'need_tfa') ? 'Authenticator code' : 'Code from your email';
    document.getElementById('cl_code').focus();
    return;
  }

  wrap.style.display = 'none';
  if (d.state === 'ok'){
    document.getElementById('cl_pass').value = '';
    document.getElementById('cl_code').value = '';
    var cs = document.getElementById('cloudStatus');
    cs.style.color = 'var(--success)';
    cs.textContent = 'Token active' + (d.email ? ' (' + d.email + ')' : '');
    showToast('Signed in to Bambu Cloud');
    // The account's printer list is the whole point of being signed in - offer
    // it straight away instead of making the user hunt for the button.
    loadAccountPrinters();
  }
}

function cloudSignIn(){
  var email=document.getElementById('cl_email').value.trim();
  var msg=document.getElementById('cl_loginMsg');
  var btn=document.getElementById('cl_signinBtn');
  if(!email){msg.textContent='Enter your Bambu account email.';msg.style.color='var(--warn)';document.getElementById('cl_email').focus();return;}
  if(clLoginMode==='password'&&!document.getElementById('cl_pass').value){msg.textContent='Enter your Bambu password.';msg.style.color='var(--warn)';document.getElementById('cl_pass').focus();return;}
  var p=new URLSearchParams();p.append('email',email);p.append('mode', 'code');
  if(clLoginMode==='password'){}
  msg.style.color='var(--text-mid)';
  msg.textContent=clLoginMode==='code'?'Requesting an email code...':'Contacting Bambu...';
  if(btn)btn.disabled=true;
  fetch('/cloud/login',{method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded'},body:p.toString()})
    .then(function(r){return r.json();}).then(clApplyLoginState)
    .catch(function(){msg.textContent='Sign-in request failed. Check network access and try again.';msg.style.color='var(--warn)';})
    .then(function(){if(btn)btn.disabled=false;});
}

function cloudSubmitCode(){
  var code=document.getElementById('cl_code').value.trim();
  var msg=document.getElementById('cl_loginMsg');
  if(!code){msg.textContent='Enter the verification code.';msg.style.color='var(--warn)';document.getElementById('cl_code').focus();return;}
  var p=new URLSearchParams();p.append('code',code);
  msg.style.color='var(--text-mid)';msg.textContent='Checking the code...';
  fetch('/cloud/login/code',{method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded'},body:p.toString()})
    .then(function(r){return r.json();}).then(clApplyLoginState)
    .catch(function(){msg.textContent='Verification request failed. Check the code and network connection.';msg.style.color='var(--warn)';});
}



/* Every printer bound to the account, straight from the cloud - so the serial
   is picked from a list instead of copied off a label. Works with a pasted
   token too, which is why it is not tied to the sign-in flow. */
function loadAccountPrinters(){
  var btn = document.getElementById('cl_acctBtn');
  var sel = document.getElementById('cl_acctsel');
  btn.disabled = true; btn.textContent = 'Loading...';
  fetch('/cloud/printers?region=' + document.getElementById('region').value)
    .then(function(r){return r.json();})
    .then(function(d){
      btn.disabled = false; btn.textContent = 'My printers';
      sel.innerHTML = '';
      if (!d.printers || !d.printers.length){
        sel.style.display = 'none';
        showToast(d.message || 'No printers found on this account');
        return;
      }
      var head = document.createElement('option');
      head.value = ''; head.textContent = 'Select a printer (' + d.printers.length + ')';
      sel.appendChild(head);
      for (var i = 0; i < d.printers.length; i++){
        var pr = d.printers[i];
        var o = document.createElement('option');
        o.value = pr.serial;
        o.setAttribute('data-name', pr.name || '');
        o.setAttribute('data-model', pr.model || '');
        o.setAttribute('data-online', pr.online ? '1' : '0');
        o.textContent = (pr.name || pr.serial) + ' - ' + (pr.model || '?') + (pr.online ? '' : ' (offline)');
        sel.appendChild(o);
      }
      sel.style.display = '';
      if (d.printers.length === 1){ sel.selectedIndex = 1; pickAccountPrinter(); showToast('Printer selected from your Bambu account'); }
      updatePrinterOnboarding();
    })
    .catch(function(){
      btn.disabled = false; btn.textContent = 'My printers';
      showToast('Could not reach the Bambu account service');
    });
}

function pickAccountPrinter(){
  var sel=document.getElementById('cl_acctsel');
  var o=sel.options[sel.selectedIndex];
  var summary=document.getElementById('cl_printerSummary');
  if(!o||!o.value){if(summary){summary.hidden=true;summary.textContent='';}updatePrinterOnboarding();return;}
  document.getElementById('cl_serial').value=o.value;
  var nm=document.getElementById('cl_pname');
  var accountName=o.getAttribute('data-name')||'';
  if(!nm.value)nm.value=accountName.substring(0,23);
  if(summary){
    var model=o.getAttribute('data-model')||'Unknown model';
    var online=o.getAttribute('data-online')==='1';
    summary.hidden=false;
    summary.innerHTML='<strong>'+esc(accountName||o.value)+'</strong> · '+esc(model)+' · <span class="'+(online?'online':'offline')+'">'+(online?'online':'currently offline')+'</span><br><span class="mono">'+esc(o.value)+'</span>';
    if(/X2D/i.test(model)){
      summary.innerHTML += '<div class="x2d-advisory"><strong>X2D:</strong> Bambu Cloud is the supported path in the current compatibility table; keep this slot in Cloud mode.</div>';
    }
  }
  updatePrinterOnboarding();
  refreshGaugeProfileUi();
  refreshPrinterHealth(false);
}


function clearPrinter(){
  if (!confirm('Clear all settings for printer ' + (currentSlot + 1) + '? Connection details are removed and the gauge layout resets to defaults. The cloud token is shared and stays (use Clear Token to remove it).')) return;
  var p = new URLSearchParams();
  p.append('slot', currentSlot);
  fetch('/printer/clear',{method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded'},body:p.toString()})
    .then(readJsonResponse)
    .then(function(d){
      if (d.status === 'ok'){ showToast('Printer ' + (currentSlot + 1) + ' cleared'); selectPrinterTab(currentSlot); }
      else showToast('Clear failed');
    })
    .catch(function(e){showToast('Clear failed: network error');console.warn('clearPrinter:',e);});
}

/* ============ SSDP local-network printer scan ============ */
var lanScanRunId = 0;
function scanLan(mode){
  var btn = document.getElementById(mode === 'lan' ? 'lan_scanBtn' : 'cl_scanBtn');
  var sel = document.getElementById(mode === 'lan' ? 'lan_devsel' : 'cl_devsel');
  sel.innerHTML = ''; sel.style.display = 'none';
  // Guard against results landing after the user switches tab/mode mid-scan.
  var slotAtStart = currentSlot;
  var modeAtStart = document.getElementById('connmode').value;
  var myRun = ++lanScanRunId;
  function stale(){
    return myRun !== lanScanRunId || currentSlot !== slotAtStart ||
           document.getElementById('connmode').value !== modeAtStart;
  }
  function restore(){ btn.disabled = false; btn.textContent = 'Scan local network'; }
  btn.disabled = true; btn.textContent = 'Scanning...';
  fetch('/lan/scan',{method:'POST'}).then(function(r){return r.json();}).then(function(d){
    if (stale()){ restore(); return; }
    if (d.status === 'error'){ showToast(d.msg || 'Scan failed'); restore(); return; }
    var deadline = Date.now() + 19000;  // server scans for 16s; allow transport + final poll margin
    (function poll(){
      if (stale()){ restore(); return; }
      fetch('/lan/scan').then(function(r){return r.json();}).then(function(d){
        if (stale()){ restore(); return; }
        var devs = d.devices || [];
        if (d.status === 'done' || Date.now() > deadline){
          renderLanDevices(mode, sel, devs); restore();
        } else {
          setTimeout(poll, 1000);
        }
      }).catch(function(e){ showToast('Scan failed: network error'); restore(); console.warn('scanLan poll:', e); });
    })();
  }).catch(function(e){ showToast('Scan failed: network error'); restore(); console.warn('scanLan start:', e); });
}

function v92DiscoveryCard(){
  var card = document.getElementById('v92DiscoveryResult');
  if (card) return card;
  var btn = document.getElementById('lan_scanBtn');
  if (!btn) return null;
  var field = btn.closest ? btn.closest('.field') : btn.parentElement;
  if (!field || !field.parentNode) return null;
  card = document.createElement('div');
  card.id = 'v92DiscoveryResult';
  card.className = 'v92-discovery';
  card.hidden = true;
  field.parentNode.insertBefore(card, field.nextSibling);
  return card;
}

function v92ShowDiscovery(dev, count){
  var card = v92DiscoveryCard();
  if (!card) return;
  if (!dev){ card.hidden = true; card.innerHTML = ''; return; }
  var title = dev.name || dev.serial || 'Bambu printer';
  var bits = [];
  if (dev.model) bits.push(dev.model);
  if (dev.ip) bits.push(dev.ip);
  if (dev.serial) bits.push(String(dev.serial).toUpperCase());
  card.hidden = false;
  card.innerHTML = '<strong>Detected: ' + esc(title) + '</strong>' +
    (bits.length ? '<div class="v92-discovery-meta">' + esc(bits.join(' · ')) + '</div>' : '') +
    '<div class="v92-discovery-next">Next: enter the LAN access code, then choose <strong>Save &amp; Verify</strong>.</div>';
  if (count && count > 1) card.querySelector('.v92-discovery-next').textContent =
    count + ' printers found. Select the printer you want to assign to this slot.';
}

function renderLanDevices(mode, sel, devs){
  if (devs.length === 0){
    v92ShowDiscovery(null);
    showToast('No Bambu printers found. Same Wi-Fi/subnet is required; you can still enter details manually.');
    return;
  }
  if (devs.length === 1){
    fillLanDevice(mode, devs[0]);
    v92ShowDiscovery(devs[0], 1);
    showToast('Printer discovered. Enter the LAN access code, then Save & Verify.');
    return;
  }
  var ph = document.createElement('option');
  ph.value = ''; ph.textContent = 'Select a printer (' + devs.length + ' found)...';
  sel.appendChild(ph);
  devs.forEach(function(dev){
    var o = document.createElement('option');
    o.value = (dev.serial || '').toUpperCase();
    o.setAttribute('data-ip', dev.ip || '');
    o.setAttribute('data-name', dev.name || '');
    o.setAttribute('data-model', dev.model || '');
    o.textContent = (dev.name || dev.serial) + (dev.model ? ' (' + dev.model + ')' : '') +
                    ' - ' + o.value + (dev.ip ? ' @ ' + dev.ip : '');
    sel.appendChild(o);
  });
  sel.style.display = '';
  v92ShowDiscovery({name: devs.length + ' Bambu printers'}, devs.length);
  showToast(devs.length + ' printers found - choose one for this slot');
}

function fillLanDevice(mode, dev){
  var serial = (dev.serial || '').toUpperCase();
  if (mode === 'lan'){
    document.getElementById('serial').value = serial;
    if (dev.ip) document.getElementById('ip').value = dev.ip;
    var name = document.getElementById('pname');
    if (name && dev.name){
      var current = name.value.trim();
      if (!current || /^My P1S$/i.test(current) || /^Bambu printer$/i.test(current))
        name.value = String(dev.name).substring(0, 23);
    }
  } else {
    document.getElementById('cl_serial').value = serial;
    var cloudName = document.getElementById('cl_pname');
    if (cloudName && dev.name && !cloudName.value.trim()) cloudName.value = String(dev.name).substring(0, 23);
  }
  v92ShowDiscovery(dev, 1);
  updatePrinterOnboarding();
  refreshGaugeProfileUi();
  refreshPrinterHealth(false);
}

function pickLanDevice(mode){
  var sel = document.getElementById(mode === 'lan' ? 'lan_devsel' : 'cl_devsel');
  if (!sel.value) return;
  var opt = sel.options[sel.selectedIndex];
  fillLanDevice(mode, {
    serial: sel.value,
    ip: opt.getAttribute('data-ip') || '',
    name: opt.getAttribute('data-name') || '',
    model: opt.getAttribute('data-model') || ''
  });
}

/* ============ Save WiFi ============ */
function saveWifi(){
  var ssid = document.getElementById('ssid').value.trim();
  var netmode = document.getElementById('netmode').value;
  var ip = document.getElementById('net_ip').value.trim();
  var gw = document.getElementById('net_gw').value.trim();
  var sn = document.getElementById('net_sn').value.trim();
  var dns = document.getElementById('net_dns').value.trim();
  if (!ssid) { showToast('WiFi SSID is required'); return; }
  if (netmode === 'static'){
    if (!ip || !gw || !sn) { showToast('Static IP mode requires IP, gateway, and subnet mask'); return; }
    if (!isValidIpv4(ip)) { showToast('Static IP address is not valid'); return; }
    if (!isValidIpv4(gw)) { showToast('Gateway address is not valid'); return; }
    if (!isValidIpv4(sn)) { showToast('Subnet mask is not valid'); return; }
    if (dns && !isValidIpv4(dns)) { showToast('DNS server address is not valid'); return; }
  }
  var p = new URLSearchParams();
  p.append('ssid', ssid);
  p.append('pass', document.getElementById('pass').value);
  p.append('netmode', netmode);
  p.append('net_ip', ip);
  p.append('net_gw', gw);
  p.append('net_sn', sn);
  p.append('net_dns', dns);
  p.append('has_showip', '1');
  if (document.getElementById('showip').checked) p.append('showip', '1');
  var host = document.getElementById('mdns_host').value.trim().toLowerCase()
               .replace(/[^a-z0-9-]/g,'').replace(/^-+|-+$/g,'');
  if (!host) host = 'bambuhelper';
  p.append('has_mdns', '1');
  p.append('mdns_host', host);
  if (document.getElementById('mdns_en').checked) p.append('mdns_en', '1');
  fetch('/save/wifi',{method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded'},body:p.toString()})
    .then(readJsonResponse)
    .then(function(d){
      if (d.status && d.status !== 'ok') { throw new Error(d.message || 'settings were not accepted'); }
      document.body.innerHTML = '<div style="text-align:center;padding-top:80px;font-family:sans-serif"><h2 style="color:#3FB950">WiFi Saved!</h2><p style="color:#8B949E;margin-top:10px">Restarting...</p></div>';
    })
    .catch(function(e){showToast('WiFi save failed: ' + (e && e.message ? e.message : 'network error'));console.warn('saveWifi:', e);});
}

/* ============ Hardware ============ */
function toggleBtnPin(){
  var v = document.getElementById('btntype').value;
  document.getElementById('btnPinRow').style.display = (v === '0' || v === '3') ? 'none' : 'block';
  toggleBuzPin();
}
function toggleBuzPin(){
  var buzOn = document.getElementById('buzzen').value !== '0';
  document.getElementById('buzFields').style.display = buzOn ? 'block' : 'none';
  var isES8311 = DEV.es8311 === '1';
  document.getElementById('buzPinRow').style.display = (buzOn && !isES8311) ? 'block' : 'none';
  document.getElementById('buzEs8311Info').style.display = (buzOn && isES8311) ? 'block' : 'none';
  var micRow = document.getElementById('micDiagRow');
  if (micRow) micRow.style.display = (buzOn && DEV.mic === '1') ? 'block' : 'none';
  var btnOn = document.getElementById('btntype').value !== '0';
  document.getElementById('buzClickRow').style.display = (buzOn && btnOn) ? 'flex' : 'none';
}
function toggleLed(){
  document.getElementById('ledFields').style.display = document.getElementById('leden').value !== '0' ? 'block' : 'none';
  var drv = document.getElementById('leddrv').value;
  /* Only a three-pin RGB LED needs the extra pins and the polarity tick; a
     WS2812 carries its own driver chip and gets colour from the data stream. */
  document.getElementById('ledRgbPins').style.display  = drv === '1' ? 'flex' : 'none';
  document.getElementById('ledAnodeRow').style.display = drv === '1' ? 'flex' : 'none';
  document.getElementById('ledColors').style.display   = drv === '0' ? 'none' : 'block';
  document.getElementById('ledpinLbl').textContent =
    drv === '1' ? 'Red GPIO pin' : (drv === '2' ? 'Data GPIO pin' : 'LED GPIO pin');
  toggleLedFx();
  toggleLedErr();
}
/* Fills the pin fields from the board's own onboard RGB wiring. The button only
   exists on boards that have one, so every caller path is guarded on the row. */
function ledUseOnboard(){
  var row = document.getElementById('ledOnboard');
  if (!row) return;
  document.getElementById('leddrv').value = row.getAttribute('data-drv');
  document.getElementById('ledpin').value = row.getAttribute('data-r');
  document.getElementById('ledping').value = row.getAttribute('data-g');
  document.getElementById('ledpinb').value = row.getAttribute('data-b');
  document.getElementById('ledanode').checked = row.getAttribute('data-anode') === '1';
  toggleLed();
  ledPreviewSend();
}
function toggleLedFx(){
  var fx = document.getElementById('ledfxmd');
  if (!fx) return;
  document.getElementById('ledFxParams').style.display = fx.value !== '0' ? 'block' : 'none';
}
function toggleLedErr(){
  var c = document.getElementById('lederr');
  if (!c) return;
  document.getElementById('ledErrParams').style.display = c.checked ? 'block' : 'none';
}
/* col is the colour to light during the preview. A colour picker passes its own
   value so the user sees that swatch on the LED while dragging; everything else
   omits it and the idle colour stands in. */
function ledPreviewSend(col){
  var p = new URLSearchParams();
  p.append('en', document.getElementById('leden').value);
  p.append('drv', document.getElementById('leddrv').value);
  p.append('pin', document.getElementById('ledpin').value);
  p.append('ping', document.getElementById('ledping').value);
  p.append('pinb', document.getElementById('ledpinb').value);
  p.append('anode', document.getElementById('ledanode').checked ? '1' : '0');
  p.append('br', document.getElementById('ledbr').value);
  p.append('col', col || document.getElementById('ledcidl').value);
  fetch('/led/preview',{method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded'},body:p.toString()}).catch(function(){});
}
function ledTestEffect(){
  var p = new URLSearchParams();
  p.append('md', document.getElementById('ledfxmd').value);
  p.append('sec', document.getElementById('ledfxsec').value);
  p.append('br', document.getElementById('ledfxbr').value);
  p.append('col', document.getElementById('ledcfin').value);
  fetch('/led/test',{method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded'},body:p.toString()})
    .then(function(r){return r.json();})
    .then(function(d){if(d.status==='ok')showToast('LED effect test running');else if(d.error)showToast('Test failed: '+d.error);})
    .catch(function(e){showToast('LED test failed');console.warn('ledTestEffect:', e);});
}
var buzTestSounds = [{id:0,name:'Print Finished'},{id:1,name:'Error'},{id:2,name:'Connected'},{id:4,name:'Bed Cooled'}];
var buzTestIdx = 0;
function testBuzzer(){
  var snd = buzTestSounds[buzTestIdx];
  fetch('/buzzer/test',{method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded'},body:'sound='+snd.id})
    .then(function(r){return r.json();})
    .then(function(d){if(d.status==='ok')showToast('Playing: '+snd.name);})
    .catch(function(e){showToast('Buzzer test failed');console.warn('testBuzzer:',e);});
  buzTestIdx = (buzTestIdx + 1) % buzTestSounds.length;
  document.getElementById('buzTestBtn').textContent = 'Test: ' + buzTestSounds[buzTestIdx].name;
}
function testMicrophone(){
  var status = document.getElementById('micDiagStatus');
  if (!status) return;
  status.textContent = 'Listening…';
  fetch('/audio/mic/test',{method:'POST'})
    .then(readJsonResponse)
    .then(function(d){
      if (d.status !== 'ok' || typeof d.level !== 'number') throw new Error(d.message || 'microphone unavailable');
      status.textContent = 'Input level ' + d.level + '%';
      showToast('Microphone input: ' + d.level + '%');
    })
    .catch(function(e){
      status.textContent = 'Test failed';
      showToast('Microphone test failed: ' + (e && e.message ? e.message : 'unavailable'));
      console.warn('testMicrophone:', e);
    });
}
function saveRotation(){
  var p = new URLSearchParams();
  p.append('rotmode', document.getElementById('rotmode').value);
  p.append('rotinterval', document.getElementById('rotinterval').value);
  p.append('rotsplit', document.getElementById('rotsplit').checked ? '1' : '0');
  p.append('rotsplitf', document.getElementById('rotsplitf').checked ? '1' : '0');
  p.append('btntype', document.getElementById('btntype').value);
  p.append('btnpin', document.getElementById('btnpin').value);
  p.append('buzzen', document.getElementById('buzzen').value);
  p.append('buzpin', document.getElementById('buzpin').value);
  p.append('buzqs', document.getElementById('buzqs').value);
  p.append('buzqe', document.getElementById('buzqe').value);
  p.append('buzclick', document.getElementById('buzclick').checked ? '1' : '0');
  p.append('buzbeden', document.getElementById('buzbeden').checked ? '1' : '0');
  p.append('buzbedtemp', document.getElementById('buzbedtemp').value);
  p.append('leden', document.getElementById('leden').value);
  p.append('leddrv', document.getElementById('leddrv').value);
  p.append('ledpin', document.getElementById('ledpin').value);
  p.append('ledping', document.getElementById('ledping').value);
  p.append('ledpinb', document.getElementById('ledpinb').value);
  p.append('ledanode', document.getElementById('ledanode').checked ? '1' : '0');
  p.append('ledcidl', document.getElementById('ledcidl').value);
  p.append('ledcprn', document.getElementById('ledcprn').value);
  p.append('ledcpau', document.getElementById('ledcpau').value);
  p.append('ledcfin', document.getElementById('ledcfin').value);
  p.append('ledcerr', document.getElementById('ledcerr').value);
  p.append('ledbr', document.getElementById('ledbr').value);
  p.append('ledfxmd', document.getElementById('ledfxmd').value);
  p.append('ledfxsec', document.getElementById('ledfxsec').value);
  p.append('ledfxbr', document.getElementById('ledfxbr').value);
  p.append('ledauto', document.getElementById('ledauto').checked ? '1' : '0');
  p.append('ledpause', document.getElementById('ledpause').checked ? '1' : '0');
  p.append('lederr', document.getElementById('lederr').checked ? '1' : '0');
  p.append('lederrsec', document.getElementById('lederrsec').value);
  var bs = document.getElementById('batshow');
  if (bs) p.append('batshow', bs.checked ? '1' : '0');
  fetch('/save/rotation',{method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded'},body:p.toString()})
    .then(function(r){return r.json();})
    .then(function(d){if(d.status==='ok')showToast('Settings saved');})
    .catch(function(e){showToast('Save failed');console.warn('saveRotation:',e);});
}

/* Cap custom gauge label inputs: 8 chars with the normal (big) font, 12 when
   "Smaller gauge labels" is on. Non-destructive - only limits new typing; any
   already-stored longer label is kept and just trimmed on the device display. */
function applyLabelMaxlen(){
  var slbl = document.getElementById('slbl');
  var max = (slbl && slbl.checked) ? 12 : 8;
  var inputs = document.querySelectorAll('input.lbl');
  for (var i = 0; i < inputs.length; i++) inputs[i].maxLength = max;
}

/* ============ Power monitoring ============ */
var currentPowerPlug = 0;
var powerPlugCount = (document.getElementById('ptab1') ? 2 : 1);
/* Grey out the display-mode radios when the status-bar readout is hidden
   (Display tab) - the whole readout is gone, so the choice does nothing. */
function applyHideReadoutToPowerDM(){
  var hp = document.getElementById('hidelp');
  var hidden = !!(hp && hp.checked);
  var plugOff = !document.getElementById('tsm_en').checked;
  var dm = document.querySelectorAll('input[name="tsm_dm"]');
  for (var i = 0; i < dm.length; i++) dm[i].disabled = hidden || plugOff;
  var note = document.getElementById('dmHiddenNote');
  if (note) note.style.display = hidden ? 'block' : 'none';
}
/* Grey out and disable the per-plug settings while "Enable power monitoring"
   is unchecked, so a filled-in but disabled plug can't be mistaken for a
   working one. The tariff card (shared) and Live stats stay active. */
function applyPowerEnableState(){
  var en = document.getElementById('tsm_en').checked;
  var blocks = ['plugDeps1', 'plugDeps2'];
  for (var i = 0; i < blocks.length; i++){
    var el = document.getElementById(blocks[i]);
    if (!el) continue;
    el.classList.toggle('deps-off', !en);
    var ctl = el.querySelectorAll('input,select');
    for (var j = 0; j < ctl.length; j++) ctl[j].disabled = !en;
  }
  applyHideReadoutToPowerDM();
}
function selectPowerTab(plug){
  if (plug >= powerPlugCount) return;
  currentPowerPlug = plug;
  for (var i = 0; i < 2; i++){
    var btn = document.getElementById('ptab' + i);
    if (!btn) continue;
    btn.classList.toggle('active', i === plug);
  }
  fetch('/power/config?plug=' + plug).then(function(r){return r.json();}).then(function(d){
    if (plug !== currentPowerPlug) return;
    document.getElementById('tsm_en').checked = !!d.enabled;
    document.getElementById('tsm_pt').value = (d.plugType >= 0 && d.plugType <= 3) ? String(d.plugType) : '0';
    document.getElementById('tsm_po').value = (d.plugOutlet >= 0 && d.plugOutlet <= 3) ? String(d.plugOutlet) : '0';
    onPlugTypeChange();
    document.getElementById('tsm_ip').value = d.ip || '';
    var dm = document.querySelectorAll('input[name="tsm_dm"]');
    for (var j = 0; j < dm.length; j++) dm[j].checked = (parseInt(dm[j].value) === (d.displayMode || 0));
    applyPowerEnableState();
    var slotSel = document.getElementById('tsm_slot');
    if (slotSel && typeof d.assignedSlot !== 'undefined') slotSel.value = d.assignedSlot;
    document.getElementById('tsm_pi').value = d.pollInterval || 10;
    document.getElementById('tsm_ao').checked = !!d.autoOffEnabled;
    document.getElementById('tsm_ad').value = d.autoOffDelayMin || 10;
    document.getElementById('tsm_aod').checked = !!d.autoOffCancelOnDoor;
    if (typeof d.tariff === 'number') document.getElementById('tsm_tar').value = d.tariff;
    if (typeof d.currency === 'string') document.getElementById('tsm_cur').value = d.currency;
    refreshPowerStats();
  }).catch(function(e){console.warn('selectPowerTab:',e);});
}
function onPlugTypeChange(){
  var type = document.getElementById('tsm_pt').value;
  var shelly = (type === '1');
  var kasa = (type === '2');
  var shellyStrip = (type === '3');
  var hint = document.getElementById('tsm_shelly_hint');
  if (hint) hint.style.display = shelly ? '' : 'none';
  var kasaHint = document.getElementById('tsm_kasa_hint');
  if (kasaHint) kasaHint.style.display = kasa ? '' : 'none';
  var stripHint = document.getElementById('tsm_shellystrip_hint');
  if (stripHint) stripHint.style.display = shellyStrip ? '' : 'none';
  var outletField = document.getElementById('tsm_outlet_field');
  if (outletField) outletField.style.display = shellyStrip ? '' : 'none';
  var ptRow = document.getElementById('tsm_pt_row');
  // Class, not an inline style: an inline grid-template-columns would beat the
  // narrow-screen media query that collapses .row to a single column.
  if (ptRow) { if (shellyStrip) ptRow.classList.remove('row-solo'); else ptRow.classList.add('row-solo'); }
  // Shelly and Kasa realtime APIs have no Today odometer.
  var tdLbl = document.getElementById('ptTodayLabel');
  var tdVal = document.getElementById('ptToday');
  if (tdLbl) tdLbl.style.display = (shelly || kasa || shellyStrip) ? 'none' : '';
  if (tdVal) tdVal.style.display = (shelly || kasa || shellyStrip) ? 'none' : '';
}
function fmtKwh(v){ return (v >= 0) ? (v.toFixed(3) + ' kWh') : '-'; }
function fmtMoney(v, cur){ if (!(v >= 0) || !cur) return ''; return ' (' + v.toFixed(2) + ' ' + cur + ')'; }
function refreshPowerStats(){
  fetch('/power/stats').then(function(r){return r.json();}).then(function(arr){
    if (!arr || !arr[currentPowerPlug]) return;
    var s = arr[currentPowerPlug];
    var cur = document.getElementById('tsm_cur').value || '';
    var tar = parseFloat(document.getElementById('tsm_tar').value) || 0;
    var dot = document.getElementById('ptStatusDot');
    dot.textContent = s.online ? '(online)' : '(offline)';
    dot.style.color = s.online ? 'var(--success)' : 'var(--text-dim)';
    document.getElementById('ptThis').textContent = fmtKwh(s.thisPrint) + (s.thisPrint >= 0 ? fmtMoney(s.thisPrint * tar, cur) : '');
    document.getElementById('ptToday').textContent = fmtKwh(s.today) + (s.today >= 0 ? fmtMoney(s.today * tar, cur) : '');
    document.getElementById('ptTotal').textContent = fmtKwh(s.total) + (s.total >= 0 ? fmtMoney(s.total * tar, cur) : '');
    document.getElementById('ptWatts').textContent = (s.online && s.watts >= 0) ? (s.watts.toFixed(0) + ' W') : '-';
    // Prefer the real relay state when the plug reports it (Shelly/Kasa output);
    // otherwise fall back to watt inference (Tasmota has no state field).
    var on = s.stateKnown ? !!s.on : (s.online && s.watts > 0.5);
    document.getElementById('btnPowerOn').style.display = on ? 'none' : '';
    document.getElementById('btnPowerOff').style.display = on ? '' : 'none';
  }).catch(function(){});
}
function powerControl(on){
  var label = on ? 'Power ON' : 'Power OFF';
  if (!confirm(label + ' plug ' + (currentPowerPlug + 1) + ' now?')) return;
  var p = new URLSearchParams();
  p.append('plug', String(currentPowerPlug));
  p.append('on', on ? '1' : '0');
  fetch('/power/control',{method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded'},body:p.toString()})
    .then(function(r){return r.json().then(function(d){return {ok:r.ok,d:d};});})
    .then(function(res){
      if (res.ok && res.d.status === 'ok') { showToast(label + ' sent'); setTimeout(refreshPowerStats, 800); }
      else { showToast((res.d && res.d.message) || (label + ' failed')); }
    })
    .catch(function(e){showToast(label + ' failed');console.warn('powerControl:',e);});
}
function savePower(){
  var p = new URLSearchParams();
  p.append('plug', String(currentPowerPlug));
  p.append('tsm_en', document.getElementById('tsm_en').checked ? '1' : '0');
  p.append('tsm_pt', document.getElementById('tsm_pt').value);
  p.append('tsm_po', document.getElementById('tsm_po').value);
  p.append('tsm_ip', document.getElementById('tsm_ip').value.trim());
  var dm = document.querySelector('input[name="tsm_dm"]:checked');
  if (dm) p.append('tsm_dm', dm.value);
  p.append('tsm_pi', document.getElementById('tsm_pi').value);
  p.append('tsm_ao', document.getElementById('tsm_ao').checked ? '1' : '0');
  p.append('tsm_ad', document.getElementById('tsm_ad').value);
  p.append('tsm_aod', document.getElementById('tsm_aod').checked ? '1' : '0');
  p.append('tsm_tar', document.getElementById('tsm_tar').value);
  p.append('tsm_cur', document.getElementById('tsm_cur').value);
  var slotSel = document.getElementById('tsm_slot');
  if (slotSel) p.append('tsm_slot', slotSel.value);
  fetch('/save/power',{method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded'},body:p.toString()})
    .then(function(r){return r.json();})
    .then(function(d){if(d.status==='ok')showToast('Power settings saved');})
    .catch(function(e){showToast('Save failed');console.warn('savePower:',e);});
}

/* ============ Display ============ */
var GAUGE_KEYS = ['prg','noz','bed','pfn','afn','afr','cfn','exh','cht','hbk','pwr','lyr'];
// Label override keys = the 12 colour gauges + Clock + AMS + Nozzle L/R (label-only rows).
var GAUGE_LABEL_KEYS = GAUGE_KEYS.concat(['clk','ams','nzr','nzl','dor']);
// eta/fin/stok = the three accent colours that belong to no gauge (#163).
var themes = {
  default:{bg:'#081018',track:'#182028',clkt:'#FFFFFF',clkd:'#C0C0C0',eta:'#00FF00',fin:'#00FF00',stok:'#00FF00',pname:'#00FF00',txt:'#FFFFFF',txtd:'#C0C0C0',dorc:'#00FF00',doro:'#FF7D00',prg:{a:'#00FF00',l:'#00FF00',v:'#FFFFFF'},noz:{a:'#FFA500',l:'#FFA500',v:'#FFFFFF'},bed:{a:'#00FFFF',l:'#00FFFF',v:'#FFFFFF'},pfn:{a:'#00FFFF',l:'#00FFFF',v:'#FFFFFF'},afn:{a:'#FFA500',l:'#FFA500',v:'#FFFFFF'},afr:{a:'#FFA500',l:'#FFA500',v:'#FFFFFF'},cfn:{a:'#00FF00',l:'#00FF00',v:'#FFFFFF'},exh:{a:'#00FF00',l:'#00FF00',v:'#FFFFFF'},cht:{a:'#00FFFF',l:'#00FFFF',v:'#FFFFFF'},hbk:{a:'#FFA500',l:'#FFA500',v:'#FFFFFF'},pwr:{a:'#FFD600',l:'#FFD600',v:'#FFFFFF'},lyr:{a:'#00FF00',l:'#00FF00',v:'#FFFFFF'}},
  mono_green:{bg:'#000800',track:'#0A1A0A',clkt:'#00FF41',clkd:'#00CC33',eta:'#00FF41',fin:'#00FF41',stok:'#00FF41',pname:'#00FF41',txt:'#00FF41',txtd:'#00CC33',dorc:'#00CC33',doro:'#00FF41',prg:{a:'#00FF41',l:'#00CC33',v:'#00FF41'},noz:{a:'#00FF41',l:'#00CC33',v:'#00FF41'},bed:{a:'#00FF41',l:'#00CC33',v:'#00FF41'},pfn:{a:'#00FF41',l:'#00CC33',v:'#00FF41'},afn:{a:'#00FF41',l:'#00CC33',v:'#00FF41'},afr:{a:'#00FF41',l:'#00CC33',v:'#00FF41'},cfn:{a:'#00FF41',l:'#00CC33',v:'#00FF41'},exh:{a:'#00FF41',l:'#00CC33',v:'#00FF41'},cht:{a:'#00FF41',l:'#00CC33',v:'#00FF41'},hbk:{a:'#00FF41',l:'#00CC33',v:'#00FF41'},pwr:{a:'#00FF41',l:'#00CC33',v:'#00FF41'},lyr:{a:'#00FF41',l:'#00CC33',v:'#00FF41'}},
  neon:{bg:'#0A0014',track:'#1A0A2E',clkt:'#FF00FF',clkd:'#AA00FF',eta:'#00FF88',fin:'#FF00FF',stok:'#00FF88',pname:'#FF00FF',txt:'#FFFFFF',txtd:'#B080C0',dorc:'#00FF88',doro:'#FF4400',prg:{a:'#FF00FF',l:'#FF00FF',v:'#FFFFFF'},noz:{a:'#FF4400',l:'#FF6600',v:'#FFFFFF'},bed:{a:'#00FFFF',l:'#00FFFF',v:'#FFFFFF'},pfn:{a:'#00FF88',l:'#00FF88',v:'#FFFFFF'},afn:{a:'#FFFF00',l:'#FFFF00',v:'#FFFFFF'},afr:{a:'#FFFF00',l:'#FFFF00',v:'#FFFFFF'},cfn:{a:'#FF00FF',l:'#FF00FF',v:'#FFFFFF'},exh:{a:'#FF00FF',l:'#FF00FF',v:'#FFFFFF'},cht:{a:'#00FFFF',l:'#00FFFF',v:'#FFFFFF'},hbk:{a:'#FF4400',l:'#FF6600',v:'#FFFFFF'},pwr:{a:'#FFFF00',l:'#FFFF00',v:'#FFFFFF'},lyr:{a:'#FF00FF',l:'#FF00FF',v:'#FFFFFF'}},
  warm:{bg:'#140A00',track:'#2E1A08',clkt:'#FFEEDD',clkd:'#FFB347',eta:'#FFB347',fin:'#FFD700',stok:'#FFB347',pname:'#FFEEDD',txt:'#FFEEDD',txtd:'#C9A98F',dorc:'#FFB347',doro:'#FF6347',prg:{a:'#FFB347',l:'#FFB347',v:'#FFEEDD'},noz:{a:'#FF6347',l:'#FF6347',v:'#FFEEDD'},bed:{a:'#FFA500',l:'#FFA500',v:'#FFEEDD'},pfn:{a:'#FFD700',l:'#FFD700',v:'#FFEEDD'},afn:{a:'#FF8C00',l:'#FF8C00',v:'#FFEEDD'},afr:{a:'#FF8C00',l:'#FF8C00',v:'#FFEEDD'},cfn:{a:'#FFB347',l:'#FFB347',v:'#FFEEDD'},exh:{a:'#FFB347',l:'#FFB347',v:'#FFEEDD'},cht:{a:'#FFA500',l:'#FFA500',v:'#FFEEDD'},hbk:{a:'#FF8C00',l:'#FF8C00',v:'#FFEEDD'},pwr:{a:'#FFD700',l:'#FFD700',v:'#FFEEDD'},lyr:{a:'#FFB347',l:'#FFB347',v:'#FFEEDD'}},
  ocean:{bg:'#000A14',track:'#0A1A2E',clkt:'#E0F0FF',clkd:'#00BFFF',eta:'#00BFFF',fin:'#00CED1',stok:'#00BFFF',pname:'#E0F0FF',txt:'#E0F0FF',txtd:'#8FB4CF',dorc:'#00BFFF',doro:'#FF7F50',prg:{a:'#00BFFF',l:'#00BFFF',v:'#E0F0FF'},noz:{a:'#FF7F50',l:'#FF7F50',v:'#E0F0FF'},bed:{a:'#4169E1',l:'#4169E1',v:'#E0F0FF'},pfn:{a:'#00CED1',l:'#00CED1',v:'#E0F0FF'},afn:{a:'#48D1CC',l:'#48D1CC',v:'#E0F0FF'},afr:{a:'#48D1CC',l:'#48D1CC',v:'#E0F0FF'},cfn:{a:'#20B2AA',l:'#20B2AA',v:'#E0F0FF'},exh:{a:'#20B2AA',l:'#20B2AA',v:'#E0F0FF'},cht:{a:'#4169E1',l:'#4169E1',v:'#E0F0FF'},hbk:{a:'#FF7F50',l:'#FF7F50',v:'#E0F0FF'},pwr:{a:'#FFD700',l:'#FFD700',v:'#E0F0FF'},lyr:{a:'#00BFFF',l:'#00BFFF',v:'#E0F0FF'}},
  /* The only light preset, and the only one whose gauge values are dark. Both
     halves matter on a light background: the neon arcs the dark presets use are
     unreadable on one, and a light glyph is worse than unreadable - gauge values
     are drawn transparently (setGaugeClearedTextColor), so their antialiased
     edge always blends toward black and a pale value picks up a dark outline.
     Dark values make that blend the correct one. Every colour here survives the
     RGB565 round trip, so what the picker shows is what the panel paints. */
  paper:{bg:'#FFFFFF',track:'#CDCACD',clkt:'#101010',clkd:'#5A595A',eta:'#007100',fin:'#007100',stok:'#007100',pname:'#0050A4',txt:'#101010',txtd:'#5A595A',dorc:'#007100',doro:'#D52000',prg:{a:'#00A100',l:'#00A100',v:'#101010'},noz:{a:'#D56100',l:'#D56100',v:'#101010'},bed:{a:'#0091A4',l:'#0091A4',v:'#101010'},pfn:{a:'#0091A4',l:'#0091A4',v:'#101010'},afn:{a:'#D56100',l:'#D56100',v:'#101010'},afr:{a:'#D56100',l:'#D56100',v:'#101010'},cfn:{a:'#00A100',l:'#00A100',v:'#101010'},exh:{a:'#00A100',l:'#00A100',v:'#101010'},cht:{a:'#0091A4',l:'#0091A4',v:'#101010'},hbk:{a:'#D56100',l:'#D56100',v:'#101010'},pwr:{a:'#B48100',l:'#B48100',v:'#101010'},lyr:{a:'#00A100',l:'#00A100',v:'#101010'}}
};
function applyTheme(name){
  var t = themes[name]; if (!t) return;
  document.getElementById('clr_bg').value = t.bg;
  document.getElementById('clr_track').value = t.track;
  document.getElementById('clr_pbar').value = t.prg.a;
  document.getElementById('clk_time').value = t.clkt;
  document.getElementById('clk_date').value = t.clkd;
  setAccentColors(t.eta, t.fin, t.stok, t.pname, t.txt, t.txtd);
  setDoorColors(t.dorc, t.doro);
  for (var i = 0; i < GAUGE_KEYS.length; i++){
    var k = GAUGE_KEYS[i], c = t[k];
    if (!c) continue;
    document.getElementById(k + '_a').value = c.a;
    document.getElementById(k + '_l').value = c.l;
    document.getElementById(k + '_v').value = c.v;
  }
  applyDisplay();
}
// The accent pickers, written together. Tolerates a missing value so a theme
// that predates any of them still applies cleanly.
function setAccentColors(eta, fin, stok, pname, txt, txtd){
  if (eta)   document.getElementById('clr_eta').value = eta;
  if (fin)   document.getElementById('clr_fin').value = fin;
  if (stok)  document.getElementById('clr_stok').value = stok;
  if (pname) document.getElementById('clr_pname').value = pname;
  if (txt)   document.getElementById('clr_txt').value = txt;
  if (txtd)  document.getElementById('clr_txtd').value = txtd;
}
// Door status pair. Open stays a contrast colour in every preset - it is the
// half of the pair that has to catch an eye across the room.
function setDoorColors(closed, open){
  if (closed) document.getElementById('clr_dorc').value = closed;
  if (open)   document.getElementById('clr_doro').value = open;
}
function bulkSet(suffix, color){
  for (var i = 0; i < GAUGE_KEYS.length; i++) document.getElementById(GAUGE_KEYS[i] + '_' + suffix).value = color;
}
var DEFAULT_GAUGES = {
  prg:{a:'#00FF00',l:'#00FF00',v:'#FFFFFF'},noz:{a:'#FF7D00',l:'#FF7D00',v:'#FFFFFF'},bed:{a:'#00FFFF',l:'#00FFFF',v:'#FFFFFF'},pfn:{a:'#00FFFF',l:'#00FFFF',v:'#FFFFFF'},afn:{a:'#FF7D00',l:'#FF7D00',v:'#FFFFFF'},afr:{a:'#FF7D00',l:'#FF7D00',v:'#FFFFFF'},cfn:{a:'#00FF00',l:'#00FF00',v:'#FFFFFF'},exh:{a:'#00FF00',l:'#00FF00',v:'#FFFFFF'},cht:{a:'#00FFFF',l:'#00FFFF',v:'#FFFFFF'},hbk:{a:'#FF7D00',l:'#FF7D00',v:'#FFFFFF'},pwr:{a:'#FFD600',l:'#FFD600',v:'#FFFFFF'},lyr:{a:'#00FF00',l:'#00FF00',v:'#FFFFFF'}
};
function resetGaugeColors(){
  for (var i = 0; i < GAUGE_KEYS.length; i++){
    var k = GAUGE_KEYS[i], c = DEFAULT_GAUGES[k];
    document.getElementById(k + '_a').value = c.a;
    document.getElementById(k + '_l').value = c.l;
    document.getElementById(k + '_v').value = c.v;
  }
  document.getElementById('clr_pbar').value = document.getElementById('prg_a').value;
  // Firmware defaults: green accents, white text, grey muted text. The grey is
  // #C0C0C0 and not #C6C6C6 because only the former survives the round trip -
  // RGB565 quantises it to 0xC618, which is exactly CLR_TEXT_DIM_DEFAULT and
  // exactly what themes.default.txtd carries. #C6C6C6 lands on 0xC638, so
  // "reset to defaults" would have left the device on a value its own defaults
  // never produce, and disagreeing with the Default theme for the same field.
  setAccentColors('#00FF00', '#00FF00', '#00FF00', '#00FF00', '#FFFFFF', '#C0C0C0');
  setDoorColors('#00FF00', '#FF7D00');
  applyDisplay();
}
function clearGaugeLabels(){
  for (var i = 0; i < GAUGE_LABEL_KEYS.length; i++){
    var k = GAUGE_LABEL_KEYS[i];
    // Door has no built-in fallback (empty = icon only, an intentional mode), so
    // "clear to defaults" must write its default text rather than blank it.
    document.getElementById(k + '_lbl').value = (k === 'dor') ? 'Door' : '';
  }
  applyDisplay();
}
function randomGaugeColors(){
  var baseH = Math.floor(Math.random() * 360);
  var hueStep = 360 / GAUGE_KEYS.length;
  for (var i = 0; i < GAUGE_KEYS.length; i++){
    var h = (baseH + i * hueStep) % 360, hex = hslToHex(h, 70, 55);
    document.getElementById(GAUGE_KEYS[i] + '_a').value = hex;
    document.getElementById(GAUGE_KEYS[i] + '_l').value = hex;
    document.getElementById(GAUGE_KEYS[i] + '_v').value = '#FFFFFF';
  }
  // Give the progress bar its own hue, kept 60-300 deg from the Progress gauge
  // so it never matches the first gauge.
  var pbarH = (baseH + 60 + Math.floor(Math.random() * 240)) % 360;
  document.getElementById('clr_pbar').value = hslToHex(pbarH, 70, 55);
  // Accents share the base hue so the ETA, the finish headline, the status
  // badge and the printer name read as one family instead of four more random
  // colours.
  var accent = hslToHex(baseH, 70, 60);
  // Text stays white/grey through a randomise: a random hue on the readouts
  // themselves costs legibility, which no roll of the dice is worth.
  setAccentColors(accent, accent, accent, accent, '#FFFFFF', '#C0C0C0');
  // Closed door joins the accent family; open keeps a fixed contrast colour so
  // a random roll can never make "door open" blend into "door closed".
  setDoorColors(accent, '#FF7D00');
  applyDisplay();
}
function hslToHex(h, s, l){
  s /= 100; l /= 100;
  var c = (1 - Math.abs(2 * l - 1)) * s, x = c * (1 - Math.abs(((h / 60) % 2) - 1)), m = l - c / 2;
  var r = 0, g = 0, b = 0;
  if (h < 60) { r = c; g = x; } else if (h < 120) { r = x; g = c; } else if (h < 180) { g = c; b = x; }
  else if (h < 240) { g = x; b = c; } else if (h < 300) { r = x; b = c; } else { r = c; b = x; }
  function h2(v){ return ('0' + Math.round((v + m) * 255).toString(16)).slice(-2); }
  return '#' + h2(r) + h2(g) + h2(b);
}
function applyDisplay(){
  var p = new URLSearchParams();
  p.append('bright', document.getElementById('bright').value);
  if (document.getElementById('nighten').checked) p.append('nighten', '1');
  p.append('nstart', document.getElementById('nstart').value);
  p.append('nend', document.getElementById('nend').value);
  p.append('nbright', document.getElementById('nbright').value);
  p.append('ssbright', document.getElementById('ssbright').value);
  p.append('rotation', document.getElementById('rotation').value);
  var ap = document.getElementById('afterprint').value;
  var afClock = document.getElementById('afterfin').value !== 'off';
  if (ap === 'keepon') { p.append('keepon', '1'); p.append('fmins', '0'); }
  else if (ap === 'custom') { p.append('fmins', document.getElementById('fmins').value); if (afClock) p.append('clock', '1'); }
  else { p.append('fmins', ap); if (afClock) p.append('clock', '1'); }
  if (document.getElementById('dack').checked) p.append('dack', '1');
  if (document.getElementById('fintm').checked) p.append('fintm', '1');
  if (document.getElementById('kps').checked) p.append('kps', '1');
  if (document.getElementById('abar').checked) p.append('abar', '1');
  if (document.getElementById('pong').checked) p.append('pong', '1');
  if (document.getElementById('slbl').checked) p.append('slbl', '1');
  p.append('timem', document.getElementById('timem').value);
  if (document.getElementById('fanmp').checked) p.append('fanmp', '1');
  p.append('glowm', document.getElementById('glowm').value);
  p.append('glow_clr', document.getElementById('glow_clr').value);
  p.append('glows', document.getElementById('glows').value);
  p.append('glowd', document.getElementById('glowd').value);
  appendHmsSettings(p);   /* no-op where the Printer Errors section does not exist */
  p.append('tz', document.getElementById('tz').value);
  if (document.getElementById('use24h').checked) p.append('use24h', '1');
  p.append('datefmt', document.getElementById('datefmt').value);
  p.append('clr_bg', document.getElementById('clr_bg').value);
  p.append('clr_track', document.getElementById('clr_track').value);
  p.append('clr_pbar', document.getElementById('clr_pbar').value);
  p.append('clr_eta', document.getElementById('clr_eta').value);
  p.append('clr_fin', document.getElementById('clr_fin').value);
  p.append('clr_stok', document.getElementById('clr_stok').value);
  p.append('clr_pname', document.getElementById('clr_pname').value);
  p.append('clr_txt', document.getElementById('clr_txt').value);
  p.append('clr_txtd', document.getElementById('clr_txtd').value);
  p.append('clr_dorc', document.getElementById('clr_dorc').value);
  p.append('clr_doro', document.getElementById('clr_doro').value);
  p.append('clk_time', document.getElementById('clk_time').value);
  p.append('clk_date', document.getElementById('clk_date').value);
  p.append('clk_size', document.getElementById('clk_size').value);
  p.append('clk_dsize', document.getElementById('clk_dsize').value);
  if (document.getElementById('clk_hidedate').checked) p.append('clk_hidedate', '1');
  p.append('noz_max', document.getElementById('noz_max').value);
  p.append('bed_max', document.getElementById('bed_max').value);
  p.append('cht_max', document.getElementById('cht_max').value);
  p.append('pwr_max', document.getElementById('pwr_max').value);
  p.append('gsmooth', document.getElementById('gsmooth').value);
  p.append('warn_thr', document.getElementById('warn_thr').value);
  p.append('warn_clr', document.getElementById('warn_clr').value);
  for (var i = 0; i < GAUGE_KEYS.length; i++){
    var k = GAUGE_KEYS[i];
    p.append(k + '_a', document.getElementById(k + '_a').value);
    p.append(k + '_l', document.getElementById(k + '_l').value);
    p.append(k + '_v', document.getElementById(k + '_v').value);
  }
  for (var j = 0; j < GAUGE_LABEL_KEYS.length; j++){
    var lk = GAUGE_LABEL_KEYS[j];
    p.append(lk + '_lbl', document.getElementById(lk + '_lbl').value);
  }
  fetch('/apply',{method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded'},body:p.toString()})
    .then(function(r){ if (r.ok) showToast('Applied!'); else showToast('Error'); })
    .catch(function(e){showToast('Apply failed');console.warn('applyDisplay:',e);});
}

/* ============ Whitelisted toggle ============ */
/* Checkboxes pass a boolean; value pickers (e.g. round skin select) pass
   their string value through unchanged. */
function toggleSetting(key, on){
  var val = (on === true) ? '1' : (on === false) ? '0' : String(on);
  fetch('/save/toggle',{method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded'},body:'key='+key+'&val='+encodeURIComponent(val)})
    .then(function(r){if(r.ok)showToast(typeof on==='boolean'?(on?key+' ON':key+' OFF'):key+' saved');else showToast('Error');})
    .catch(function(e){showToast('Toggle failed');console.warn('toggleSetting:',e);});
}

/* ============ Printer errors (HMS + print_error) ============

   This file is shared by every board, but the Printer Errors section is not:
   flash-poor boards compile its markup out and keep only the on-screen badge.
   Every function here therefore checks that its markup exists first, and the
   two called from shared code - appendHmsSettings() and refreshErrorCard() -
   simply do nothing where it does not. */

function hmsHasSection(){ return !!document.getElementById('hmsauto'); }

/* The four alert checkboxes ride one bitmask, and it is always sent -
   including zero. Four unchecked boxes posting nothing at all would leave the
   old bits in place on the device. */
function hmsMaskValue(){
  var m = 0;
  for (var i = 0; i < 4; i++){
    var e = document.getElementById('hmsm' + i);
    if (e && e.checked) m |= (1 << i);
  }
  return m;
}
function applyHmsMask(){ toggleSetting('hmsmask', hmsMaskValue()); }

function toggleHmsFields(){
  var f = document.getElementById('hmsFields');
  var e = document.getElementById('hmsen');
  if (f && e) f.style.display = e.checked ? 'block' : 'none';
}

function appendHmsSettings(p){
  if (!hmsHasSection()) return;
  var en = document.getElementById('hmsen'), sv = document.getElementById('hmssev');
  if (en && en.checked) p.append('hmsen', '1');
  if (sv && sv.checked) p.append('hmssev', '1');
  var ol = document.getElementById('hmsonl');
  if (ol && ol.checked) p.append('hmsonl', '1');
  p.append('hmsauto', document.getElementById('hmsauto').value);
  p.append('hmsmask', String(hmsMaskValue()));
}

/* Live card. Text comes from the device where a table is compiled in; the rest
   is looked up in the published mirror, which the browser can reach and the
   firmware cannot (e.bambulab.com sends no CORS header, and the feed is
   750 KB). Fetched once per page load, never inside the poll.

   Boards carrying the full table (DEV.hmsFull) never fetch it: a code with no
   device text is blank in Bambu's feed, and the mirror is built from that same
   feed with the same blanks dropped, so the request could only ever fail to
   help. And the "hmsonl" setting lets anyone turn the lookup off - on an
   isolated network it can only fail, and some people want no third-party
   request from a LAN page at all. */
var HMS_MIRROR = 'https://keralots.github.io/BambuHelper/errors/hms_en.json';
var HMS_ON_DEVICE = (DEV.hmsFull === '1');
var _hmsMirror = null, _hmsTexts = null, _hmsLast = null;

/* Read live rather than cached: flipping the checkbox has to take effect on the
   next render, without a reload. Missing markup means an older page, where the
   lookup was unconditional. */
function hmsLookupAllowed(){
  if (HMS_ON_DEVICE) return false;
  var c = document.getElementById('hmsonl');
  return !c || c.checked;
}

/* Turning the lookup off has to drop what was already fetched, or the sentences
   stay on screen until a reload and the switch looks broken. Turning it back on
   clears the cached promise too, so the next render refetches. */
function hmsLookupChanged(){
  if (!hmsLookupAllowed()) _hmsTexts = null;
  _hmsMirror = null;
  refreshErrorCard();
}

function hmsMirror(){
  if (!hmsLookupAllowed()) return Promise.resolve(null);
  if (!_hmsMirror){
    _hmsMirror = fetch(HMS_MIRROR)
      .then(function(r){ return r.ok ? r.json() : null; })
      .catch(function(){ return null; });
  }
  return _hmsMirror;
}
function hmsSevName(s){ return ['Info','Fatal','Serious','Common'][s] || 'Info'; }
function hmsSevClr(s){
  return ['var(--text-dim)','var(--danger)','var(--warn)','var(--warn)'][s] || 'var(--text-dim)';
}

/* lbl overrides the severity word: a print_error carries no severity of its
   own, and a cancel is not an error at all. */
function hmsRow(code, sev, mod, text, base, wiki, lbl){
  var h = '<div style="padding:8px 0;border-top:1px solid var(--line-soft)">'
        + '<div class="hstack" style="flex-wrap:wrap">'
        + '<span style="font-weight:600;color:' + hmsSevClr(sev) + '">' + (lbl || hmsSevName(sev)) + '</span>'
        + (mod ? '<span class="text-dim small">' + esc(mod) + '</span>' : '')
        + '<span class="mono small">' + esc(code) + '</span>';
  if (base) h += '<span class="text-dim small" title="Already active when the device connected - listed, never alerts">standing</span>';
  if (wiki) h += '<a class="small" target="_blank" rel="noopener" href="' + wiki + '">wiki</a>';
  h += '</div>';
  if (text) h += '<div class="small" style="margin-top:2px;color:var(--text-mid)">' + esc(text) + '</div>';
  return h + '</div>';
}

/* The device now sends codes the way Bambu writes them - "HMS_0300-1A00-0002-0002"
   for HMS, "0300-8007" for print_error - because that is what a user can paste
   into a search box (issue #164). Both lookup maps are keyed on the bare 16 or 8
   hex digits, so strip the prefix and every separator before indexing them.
   Tolerates the old underscore form too: a page can outlive a firmware. */
function hmsBareCode(code){
  return String(code).replace(/^HMS[_-]/i, '').replace(/[_-]/g, '').toUpperCase();
}

function hmsText(map, code, dev){
  if (dev) return dev;
  if (!map) return '';
  var k = hmsBareCode(code);
  return map[k] || '';
}

/* Every per-code wiki page sits under a model path segment (x1, a1-mini, a2l,
   h2d, ams-ht, ...) that the code itself does not carry, so the URL cannot be
   built from the code alone - the old fixed /en/x1/ link 404'd for most codes.
   The mirror ships the path verbatim (the wiki's own separator and case; some
   of its links use "-" between the code groups, not "_"). Where the map is
   missing - a full-table board never fetches the mirror, and the text lookup
   can be switched off - link the HMS index, which lists every documented code
   and never 404s. Only ~224 of 2014 codes have a page at all, so the index is
   the common case either way. */
var HMS_WIKI_INDEX = 'https://wiki.bambulab.com/en/hms/home';
function hmsWikiUrl(code){
  var m = _hmsTexts && _hmsTexts.wiki, p = m && m[hmsBareCode(code)];
  return p ? 'https://wiki.bambulab.com/en/' + p : HMS_WIKI_INDEX;
}

function hmsRender(){
  var el = document.getElementById('hmsLive');
  if (!el || !_hmsLast) return;
  var h = '', need = false, m = _hmsTexts || {};

  for (var i = 0; i < _hmsLast.length; i++){
    var d = _hmsLast[i];
    if (!d || !d.configured) continue;
    var rows = '';

    if (d.printError){
      var t = hmsText(m.err, d.printError, d.printErrorText);
      if (!t && !d.printErrorText) need = true;
      rows += hmsRow(d.printError, d.printErrorCancel ? 0 : 1, '', t, false, '',
                     d.printErrorCancel ? 'Canceled' : 'Print error');
    }

    var a = d.hms || [];
    for (var j = 0; j < a.length; j++){
      var e = a[j], tx = hmsText(m.hms, e.code, e.text);
      if (!tx && !e.text) need = true;
      rows += hmsRow(e.code, e.sev, e.module, tx, e.baseline, hmsWikiUrl(e.code));
    }

    if (d.hmsOverflow) rows += '<div class="small text-dim" style="padding-top:6px">+' + d.hmsOverflow + ' more not kept</div>';
    if (rows) h += '<div style="margin-bottom:var(--sp-3)"><strong>' + esc(d.name || ('Printer ' + (i + 1))) + '</strong>' + rows + '</div>';
  }

  el.innerHTML = h || '<span class="text-dim">No errors reported.</span>';
  // Second guard at the call site as well as inside hmsMirror(): the card
  // re-renders on every 3 s poll, and a standing blank code would otherwise
  // build a throwaway promise each time. The third guard is inside the
  // continuation: a request already in flight when the user unticks the box
  // still resolves, and without the re-check it would put the sentences back
  // on screen after the switch said no.
  if (need && !_hmsTexts && hmsLookupAllowed())
    hmsMirror().then(function(j){
      if (j && hmsLookupAllowed()){ _hmsTexts = j; hmsRender(); }
    });
}

function refreshErrorCard(){
  if (!document.getElementById('hmsLive')) return;
  var q = [];
  for (var s = 0; s < 4; s++){
    q.push(fetch('/status?slot=' + s).then(function(r){ return r.json(); }).catch(function(){ return null; }));
  }
  Promise.all(q).then(function(all){ _hmsLast = all; hmsRender(); });
}

function toggleDualPrinterMode(on){
  toggleSetting('dualp', on);
  var t = document.getElementById('tab1');
  if (t) t.style.display = on ? '' : 'none';
  var d = document.getElementById('topStatusDot1');
  if (d) d.style.display = on ? '' : 'none';
  if (!on) selectPrinterTab(0);
}
/* PSRAM boards: reveal/hide printer 3 + 4 tabs and topbar dots when the
   experimental 4-printer beta is toggled, mirroring toggleDualPrinterMode. */
function toggleQuadPrinterMode(on){
  toggleSetting('quadp', on);
  [2,3].forEach(function(i){
    var t = document.getElementById('tab'+i);
    if (t) t.style.display = on ? '' : 'none';
    var d = document.getElementById('topStatusDot'+i);
    if (d) d.style.display = on ? '' : 'none';
  });
  if (!on) selectPrinterTab(0);
}
/* Toggle a grid mode (l8s / p9s) and sync the matching Gauge Layout extras
   block in the Printer section. Hides the extra dropdowns when the user
   doesn't have the mode enabled so the layout card stays compact. */
function toggleGridMode(key, on){
  toggleSetting(key, on);
  var elId = (key === 'l8s') ? 'landExtrasGroup' : 'portExtrasGroup';
  var el = document.getElementById(elId);
  if (el) el.style.display = on ? '' : 'none';
}
function toggleDangerUnlock(on){
  var ops = document.getElementById('dangerOps');
  if (ops) ops.style.display = on ? '' : 'none';
}

/* ============ Diagnostics ============ */
function toggleDebug(on){
  fetch('/debug/toggle',{method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded'},body:'on='+(on?'1':'0')})
    .then(function(r){if(r.ok)showToast(on?'Debug ON':'Debug OFF');});
}
function refreshDiag(){
  fetch('/debug').then(function(r){return r.json();}).then(function(d){
    var h = '';
    function ageText(sec, hasAny){
      if (!hasAny) return 'Never';
      if (sec < 60) return sec + 's ago';
      if (sec < 3600) return Math.round(sec / 60) + ' min ago';
      return Math.round(sec / 3600) + ' h ago';
    }
    if (d.printers){
      d.printers.forEach(function(p){
        h += '<div style="margin-bottom:8px;padding:6px;border-left:2px solid '+(p.connected?'var(--success)':'var(--danger)')+'">';
        h += '<strong style="color:var(--text)">'+esc(p.name)+'</strong> (slot '+p.slot+')<br>';
        h += '<div class="stat-row"><span>MQTT:</span><span class="stat-val">'+(p.connected?'<span style="color:var(--success)">Connected</span>':'<span style="color:var(--danger)">Disconnected</span>')+'</span></div>';
        h += '<div class="stat-row"><span>Attempts:</span><span class="stat-val">'+p.attempts+'</span></div>';
        h += '<div class="stat-row"><span>Messages RX:</span><span class="stat-val">'+p.messages+'</span></div>';
        h += '<div class="stat-row"><span>Pushall total:</span><span class="stat-val">'+(p.pushall_total||0)+'</span></div>';
        var rc=p.rec_print||0, rd=p.rec_conn_dead||0, rf=p.rec_finish||0, ri=p.rec_idle||0;
        h += '<div class="stat-row"><span>Pushall recovery:</span><span class="stat-val">'+(rc+rd+rf+ri)+' (P:'+rc+' D:'+rd+' F:'+rf+' I:'+ri+')</span></div>';
        h += '<div class="stat-row"><span>Last pushall:</span><span class="stat-val">'+esc(p.last_pushall_reason||'Never')+' ('+ageText(p.last_pushall_age_s,p.pushall_total>0)+')</span></div>';
        if (p.last_rc!==0) h += '<div class="stat-row"><span>Last error:</span><span class="stat-val" style="color:var(--danger)">'+esc(p.rc_text)+'</span></div>';
        if (p.rc_hint) h += '<div style="margin-top:4px;font-size:11px;color:var(--warn);line-height:1.3">'+esc(p.rc_hint)+'</div>';
        h += '</div>';
      });
    }
    h += '<div class="stat-row"><span>Free heap:</span><span class="stat-val">'+Math.round(d.heap/1024)+' KB</span></div>';
    h += '<div class="stat-row"><span>Uptime:</span><span class="stat-val">'+formatUptime(d.uptime)+'</span></div>';
    h += '<div style="margin-top:8px;font-size:11px;color:var(--text-dim)">Recovery: P=Print stale, D=Conn dead, F=Finish stale, I=Idle/Unknown</div>';
    document.getElementById('diagInfo').innerHTML = h;
  }).catch(function(e){console.warn('refreshDiag:',e);});
}

/* ============ Hardware info (also drives WiFi section live KV) ============ */
function fmtBytes(kb){ if (kb >= 1024) return (kb/1024).toFixed(1) + ' MB'; return kb + ' KB'; }
function formatUptime(secs){
  var d = Math.floor(secs / 86400);
  var h = Math.floor((secs % 86400) / 3600);
  var m = Math.floor((secs % 3600) / 60);
  var s = secs % 60;
  if (d > 0) return d + 'd ' + h + 'h ' + m + 'm';
  if (h > 0) return h + 'h ' + m + 'm';
  if (m > 0) return m + 'm ' + s + 's';
  return s + 's';
}
function refreshHwInfo(){
  fetch('/status?slot='+currentSlot).then(function(r){return r.json();}).then(function(d){
    var heapEl = document.getElementById('hwHeap');
    if (heapEl && typeof d.heap_kb === 'number') heapEl.textContent = fmtBytes(d.heap_kb) + ' free';
    var fEl = document.getElementById('hwFlash');
    if (fEl && d.flash_kb) fEl.textContent = fmtBytes(d.flash_kb);
    var pEl = document.getElementById('hwPsram');
    if (pEl) pEl.textContent = d.psram_kb ? fmtBytes(d.psram_kb) : 'none';
    var mEl = document.getElementById('hwMac');
    if (mEl && d.mac) mEl.textContent = d.mac;
    var rEl = document.getElementById('wifiRssi');
    if (rEl && typeof d.rssi === 'number') rEl.textContent = d.rssi + ' dBm';
    var uEl = document.getElementById('wifiUptime');
    if (uEl && typeof d.uptime === 'number') uEl.textContent = formatUptime(d.uptime);
    var wt = document.getElementById('wifiTopText');
    if (wt) wt.textContent = d.ip || '-';
  }).catch(function(){});
}

/* ============ Topbar status dots (per-slot, independent of current tab) ============ */
function _updateTopDot(slot, dotId, txtId){
  var dot = document.getElementById(dotId);
  // Skip missing dots, and skip dots hidden by an experimental opt-in gate
  // (low-RAM 2-printer / PSRAM 4-printer) so disabled slots are not polled.
  if (!dot || dot.style.display === 'none') return;
  fetch('/status?slot=' + slot).then(function(r){return r.json();}).then(function(d){
    var ts = document.getElementById(txtId);
    var label;
    if (!d.configured) label = '-';
    else if (d.connected) label = d.name || ('Slot ' + (slot + 1));
    else label = (d.name || ('Slot ' + (slot + 1))) + ' (off)';
    if (ts) ts.textContent = label;
    dot.classList.toggle('off', !d.connected);
  }).catch(function(){});
}
function refreshTopStatusDots(){
  _updateTopDot(0, 'topStatusDot', 'topStatusText');
  _updateTopDot(1, 'topStatusDot1', 'topStatusText1');
  _updateTopDot(2, 'topStatusDot2', 'topStatusText2');
  _updateTopDot(3, 'topStatusDot3', 'topStatusText3');
}

/* ============ Live stats (printer card) ============ */
function refreshLiveStats(){
  fetch('/status?slot='+currentSlot).then(function(r){return r.json();}).then(function(d){
    var h = '';
    if (d.display_off) h += '<div class="stat-row"><span>Display:</span><span class="stat-val" style="color:var(--danger)">Off</span></div>';
    if (d.connected){
      if (d.no_data) h += '<div style="margin-bottom:var(--sp-2);padding:8px 10px;border:1px solid var(--danger);border-radius:6px;background:rgba(220,53,69,0.08);color:var(--danger);font-size:12.5px;line-height:1.5">Connected to Bambu, but no data received from the printer. Check: (1) the serial number is correct and UPPERCASE, (2) the printer is powered on, (3) for a Cloud printer, that the sign-in account owns this printer &mdash; not a second Bambu account (e.g. an Apple/Google login).</div>';
      h += '<div class="stat-row"><span>State:</span><span class="stat-val">'+esc(d.state)+'</span></div>';
      h += '<div class="stat-row"><span>Nozzle:</span><span class="stat-val">'+d.nozzle+'/'+d.nozzle_t+'&deg;C</span></div>';
      h += '<div class="stat-row"><span>Bed:</span><span class="stat-val">'+d.bed+'/'+d.bed_t+'&deg;C</span></div>';
      if (d.progress > 0) h += '<div class="stat-row"><span>Progress:</span><span class="stat-val">'+d.progress+'%</span></div>';
      if (d.fan > 0) h += '<div class="stat-row"><span>Fan:</span><span class="stat-val">'+d.fan+'%</span></div>';
    } else if (d.configured) {
      h += '<span class="text-dim">Not connected (printer may be off)</span>';
    } else {
      h += '<span class="text-dim">Not Configured</span>';
    }
    document.getElementById('liveStats').innerHTML = h;
    var ps = document.getElementById('printerStatus');
    if (d.connected) { ps.className = 'status-pill status-ok'; ps.textContent = 'Connected'; }
    else if (d.configured) { ps.className = 'status-pill status-off'; ps.textContent = 'Disconnected / Powered Off'; }
    else { ps.className = 'status-pill status-na'; ps.textContent = 'Not Configured'; }
    if (d.display_off && d.connected) ps.textContent += ' (Display Off)';
  }).catch(function(e){console.warn('liveStats:',e);});
}

/* ============ Settings export / import ============ */
function exportSettings(){
  fetch('/settings/export').then(function(r){return r.text();}).then(function(t){
    try {
      var meta = JSON.parse(t);
      if (meta._secretsIncluded === false)
        showToast('Backup created without WiFi or printer secrets');
    } catch(e){}
    var d = new Date();
    var pad = function(n){return (n<10?'0':'')+n;};
    var ts = d.getFullYear() + pad(d.getMonth()+1) + pad(d.getDate()) + '_' +
             pad(d.getHours()) + pad(d.getMinutes()) + pad(d.getSeconds());
    var a = document.createElement('a');
    a.href = 'data:application/json;charset=utf-8,' + encodeURIComponent(t);
    a.download = 'bambuhelper_settings_' + ts + '.json';
    document.body.appendChild(a); a.click(); document.body.removeChild(a);
  }).catch(function(){showToast('Export failed');});
}
function importSettings(){
  var f = document.getElementById('importFile').files[0];
  if (!f) { showToast('Select a JSON file first'); return; }
  if (!f.name.toLowerCase().endsWith('.json')) { showToast('Import file must be a JSON backup'); return; }
  if (!confirm('Import settings and restart? Current settings will be overwritten.')) return;
  var fd = new FormData(); fd.append('settings', f);
  var stat = document.getElementById('importStatus');
  stat.style.color = 'var(--info)'; stat.textContent = 'Importing...';
  fetch('/settings/import',{method:'POST',body:fd})
    .then(readJsonResponse)
    .then(function(d){
      if (d.status === 'ok'){ stat.style.color = 'var(--success)'; stat.textContent = d.message; }
      else if (d.message){ stat.style.color = 'var(--danger)'; stat.textContent = 'Import failed: ' + d.message; }
      else { stat.style.color = 'var(--danger)'; stat.textContent = 'Import failed'; }
    })
    .catch(function(e){ stat.style.color = 'var(--danger)'; stat.textContent = 'Import failed: upload or parsing error'; console.warn('importSettings:',e); });
}

/* ============ OTA ============ */

/* Smart Home v8: SHA-256 implementation that works on the device's plain-HTTP
   LAN portal. WebCrypto is restricted to secure contexts on many browsers. */
function sha256HexArrayBuffer(buffer){
  var bytes=new Uint8Array(buffer);
  var bitLen=bytes.length*8;
  var total=((bytes.length+9+63)>>6)<<6;
  var data=new Uint8Array(total);
  data.set(bytes);
  data[bytes.length]=0x80;
  var view=new DataView(data.buffer);
  view.setUint32(total-8,Math.floor(bitLen/4294967296),false);
  view.setUint32(total-4,bitLen>>>0,false);
  var K=[
    0x428a2f98,0x71374491,0xb5c0fbcf,0xe9b5dba5,0x3956c25b,0x59f111f1,0x923f82a4,0xab1c5ed5,
    0xd807aa98,0x12835b01,0x243185be,0x550c7dc3,0x72be5d74,0x80deb1fe,0x9bdc06a7,0xc19bf174,
    0xe49b69c1,0xefbe4786,0x0fc19dc6,0x240ca1cc,0x2de92c6f,0x4a7484aa,0x5cb0a9dc,0x76f988da,
    0x983e5152,0xa831c66d,0xb00327c8,0xbf597fc7,0xc6e00bf3,0xd5a79147,0x06ca6351,0x14292967,
    0x27b70a85,0x2e1b2138,0x4d2c6dfc,0x53380d13,0x650a7354,0x766a0abb,0x81c2c92e,0x92722c85,
    0xa2bfe8a1,0xa81a664b,0xc24b8b70,0xc76c51a3,0xd192e819,0xd6990624,0xf40e3585,0x106aa070,
    0x19a4c116,0x1e376c08,0x2748774c,0x34b0bcb5,0x391c0cb3,0x4ed8aa4a,0x5b9cca4f,0x682e6ff3,
    0x748f82ee,0x78a5636f,0x84c87814,0x8cc70208,0x90befffa,0xa4506ceb,0xbef9a3f7,0xc67178f2
  ];
  var H=[0x6a09e667,0xbb67ae85,0x3c6ef372,0xa54ff53a,0x510e527f,0x9b05688c,0x1f83d9ab,0x5be0cd19];
  var W=new Uint32Array(64);
  function rotr(x,n){return (x>>>n)|(x<<(32-n));}
  for(var off=0;off<total;off+=64){
    var i;
    for(i=0;i<16;i++)W[i]=view.getUint32(off+i*4,false);
    for(i=16;i<64;i++){
      var x=W[i-15],y=W[i-2];
      var s0=(rotr(x,7)^rotr(x,18)^(x>>>3))>>>0;
      var s1=(rotr(y,17)^rotr(y,19)^(y>>>10))>>>0;
      W[i]=(W[i-16]+s0+W[i-7]+s1)>>>0;
    }
    var a=H[0],b=H[1],c=H[2],d=H[3],e=H[4],f=H[5],g=H[6],h=H[7];
    for(i=0;i<64;i++){
      var S1=(rotr(e,6)^rotr(e,11)^rotr(e,25))>>>0;
      var ch=((e&f)^((~e)&g))>>>0;
      var t1=(h+S1+ch+K[i]+W[i])>>>0;
      var S0=(rotr(a,2)^rotr(a,13)^rotr(a,22))>>>0;
      var maj=((a&b)^(a&c)^(b&c))>>>0;
      var t2=(S0+maj)>>>0;
      h=g;g=f;f=e;e=(d+t1)>>>0;d=c;c=b;b=a;a=(t1+t2)>>>0;
    }
    H[0]=(H[0]+a)>>>0;H[1]=(H[1]+b)>>>0;H[2]=(H[2]+c)>>>0;H[3]=(H[3]+d)>>>0;
    H[4]=(H[4]+e)>>>0;H[5]=(H[5]+f)>>>0;H[6]=(H[6]+g)>>>0;H[7]=(H[7]+h)>>>0;
  }
  return H.map(function(v){return v.toString(16).padStart(8,'0');}).join('');
}

function confirmOtaAfterTransportLoss(stat){
  stat.style.color = 'var(--info)';
  stat.textContent = 'Firmware transferred. Confirming device acceptance...';
  var tries = 0;
  function probe(){
    tries++;
    var ctrl = new AbortController();
    var timeout = setTimeout(function(){ ctrl.abort(); }, 1800);
    fetch('/ota/manual/status?_=' + Date.now(), {
      cache:'no-store', credentials:'same-origin', signal:ctrl.signal
    }).then(function(r){
      clearTimeout(timeout);
      if (r.status === 401 || r.status === 403) throw new Error('session');
      if (!r.ok) throw new Error('HTTP ' + r.status);
      return r.json();
    }).then(function(d){
      if (d.phase === 'accepted'){
        stat.style.color = 'var(--success)';
        stat.textContent = d.message || 'Firmware accepted. Waiting for restart...';
        waitForReboot(stat);
        return;
      }
      if (d.phase === 'error'){
        stat.style.color = 'var(--danger)';
        stat.textContent = 'Update failed: ' + (d.message || 'device rejected firmware');
        startPolling(currentSection);
        return;
      }
      if (tries < 6){
        stat.textContent = 'Firmware transferred. Device is ' + (d.phase || 'processing') + '...';
        setTimeout(probe, 650);
        return;
      }
      stat.style.color = 'var(--danger)';
      stat.textContent = 'Update not accepted: device stayed online without confirming firmware.';
      startPolling(currentSection);
    }).catch(function(e){
      clearTimeout(timeout);
      // A network failure after every upload byte was sent is the expected
      // signature of the ESP32 leaving the network for its reboot. The existing
      // reboot watcher requires an offline -> online transition before reload.
      if (e && e.message === 'session'){
        stat.style.color = 'var(--danger)';
        stat.textContent = 'Update could not be confirmed because the portal session expired.';
        startPolling(currentSection);
      } else {
        waitForReboot(stat);
      }
    });
  }
  probe();
}

async function startOta(){
  var f = document.getElementById('otaFile').files[0];
  if (!f) { showToast('Select a .bin file first'); return; }
  if (!f.name.toLowerCase().endsWith('.bin')) { showToast('Firmware file must end with .bin'); return; }
  if (f.size < 32768) { showToast('File too small'); return; }
  var slotMax = parseInt(DEV.otaSlot, 10) || 1835008;
  if (f.size > slotMax) { showToast('File too large (max ' + (slotMax/1048576).toFixed(2).replace(/\.?0+$/,'') + 'MB)'); return; }
  var lowerName = f.name.toLowerCase();
  var board = DEV.board.toLowerCase();
  if (lowerName.indexOf('bambuhelper-') === 0 && lowerName.indexOf('-' + board + '-') === -1){ showToast('Selected firmware looks like a different board variant'); return; }

  var shaHex;
  try {
    var fileBuf = await f.arrayBuffer();
    shaHex = sha256HexArrayBuffer(fileBuf);
  } catch (e) {
    showToast('Could not calculate firmware SHA-256: ' + e.message);
    return;
  }

  if (!confirm('SHA-256 verified locally. Upload firmware and restart?')) return;
  var prog = document.getElementById('otaProgress');
  var bar = document.getElementById('otaBar');
  var pct = document.getElementById('otaPct');
  var stat = document.getElementById('otaStatus');
  prog.style.display = 'block'; bar.style.width = '0%'; pct.textContent = '0%';
  stat.innerHTML = '<span style="color:var(--info)">Uploading...</span>';
  var fd = new FormData(); fd.append('firmware', f);
  // Stop background hardware polling while the ESP32 WebServer owns the
  // single long-running upload connection. This also prevents auth/state
  // traffic from racing the OTA completion response.
  stopPolling();
  var xhr = new XMLHttpRequest();
  xhr.open('POST','/ota/upload',true);
  xhr.withCredentials = true;
  xhr.timeout = 180000;
  xhr.setRequestHeader('X-SHA256', shaHex);
  var uploadTransferred = false;
  xhr.upload.onprogress = function(e){
    if (e.lengthComputable){
      var p = Math.round(e.loaded / e.total * 100);
      bar.style.width = p + '%'; pct.textContent = p + '%';
      if (p >= 100){ uploadTransferred = true; stat.style.color = 'var(--info)'; stat.textContent = 'Verifying and flashing...'; }
    }
  };
  xhr.onload = function(){
    if (xhr.status === 401 || xhr.status === 403){
      stat.style.color = 'var(--danger)';
      stat.textContent = 'Update failed: portal session expired. Reload, sign in, and retry.';
      startPolling(currentSection);
      return;
    }
    try {
      var d = JSON.parse(xhr.responseText);
      if (d.status === 'ok'){
        bar.style.width = '100%'; pct.textContent = '100%';
        stat.style.color = 'var(--success)'; stat.textContent = d.message;
        waitForReboot(stat);
      } else {
        var msg = d.message || ('Firmware update failed (HTTP ' + xhr.status + ')');
        if (msg === 'Invalid firmware file') msg = 'Invalid firmware file or wrong board build';
        stat.style.color = 'var(--danger)'; stat.textContent = 'Update failed: ' + msg;
        startPolling(currentSection);
      }
    } catch(e) {
      var body = (xhr.responseText || '').replace(/\s+/g,' ').trim().slice(0,120);
      stat.style.color = 'var(--danger)';
      stat.textContent = 'Update failed: HTTP ' + xhr.status + (body ? ' — ' + body : ' — empty response');
      startPolling(currentSection);
    }
  };
  xhr.onerror = function(){
    if (uploadTransferred){ confirmOtaAfterTransportLoss(stat); return; }
    stat.style.color = 'var(--danger)';
    stat.textContent = 'Update failed before the firmware finished uploading.';
    startPolling(currentSection);
  };
  xhr.ontimeout = function(){
    if (uploadTransferred){ confirmOtaAfterTransportLoss(stat); return; }
    stat.style.color = 'var(--danger)';
    stat.textContent = 'Update failed: upload timed out before transfer completed.';
    startPolling(currentSection);
  };
  xhr.onabort = function(){
    if (uploadTransferred){ confirmOtaAfterTransportLoss(stat); return; }
    stat.style.color = 'var(--danger)';
    stat.textContent = 'Update cancelled before transfer completed.';
    startPolling(currentSection);
  };
  xhr.send(fd);
}

// Poll the device until it reboots and serves again, then reload the page.
// Used by both the manual (.bin upload) and online-update paths. Poll one
// request at a time: setInterval would stack up probes that each hang for the
// full TCP timeout while the device is offline, and a fresh success could
// resolve before those pending catches flip wentOffline - leaving the gate
// false so we never reload. A 3s AbortController makes a hang count as offline
// quickly; no-store + a cache-buster stop the browser serving a cached 200. We
// reload only after seeing the device drop AND return, never into the old fw.
function waitForReboot(st){
  st.textContent = 'Waiting for device to restart...';
  var wentOffline = false, elapsed = 0;
  (function poll(){
    if (elapsed >= 90){ st.textContent = 'Reboot timeout - please refresh manually.'; return; }
    var ctrl = new AbortController();
    var to = setTimeout(function(){ ctrl.abort(); }, 3000);
    fetch('/?_=' + Date.now(), {cache:'no-store', signal:ctrl.signal})
      .then(function(r){
        clearTimeout(to);
        if (!r.ok) throw 0;
        if (wentOffline){ location.reload(); return; }
        elapsed += 2; setTimeout(poll, 2000);
      })
      .catch(function(){
        clearTimeout(to);
        wentOffline = true; elapsed += 2;
        st.textContent = 'Restarting... (' + elapsed + 's)';
        setTimeout(poll, 2000);
      });
  })();
}

/* Rollback: the device tells us whether the inactive app slot holds a
   different, bootable firmware; if so the "Previous firmware" block appears.
   The slot's version is only known when that firmware was new enough to
   record it, hence the two phrasings. */
function initRollback(){
  if (!document.getElementById('rollbackWrap')) return;
  fetch('/ota/slots').then(function(r){return r.json();}).then(function(d){
    if (!d.can) return;
    document.getElementById('rollbackInfo').textContent = d.fw
      ? 'Version ' + d.fw + ' is still installed in the second update slot.'
      : 'An older firmware build is still installed in the second update slot.';
    document.getElementById('rollbackWrap').style.display = 'block';
  }).catch(function(e){console.warn('rollback info:',e);});
}
function otaRollback(){
  if (!confirm('Reboot into the firmware in the other update slot? Settings are kept, but options added by the newer version may reset, and its cloud token storage is not readable by older versions (re-paste the token there if cloud stops working). You can update again at any time.')) return;
  var st = document.getElementById('rollbackStatus');
  st.style.color = 'var(--info)'; st.textContent = 'Verifying the other slot...';
  fetch('/ota/rollback',{method:'POST'}).then(function(r){return r.json();}).then(function(d){
    if (d.status === 'ok'){ st.style.color = 'var(--success)'; st.textContent = d.message; waitForReboot(st); }
    else { st.style.color = 'var(--danger)'; st.textContent = d.message || 'Rollback failed'; }
  }).catch(function(e){ st.style.color = 'var(--danger)'; st.textContent = 'Rollback failed: network error'; console.warn('rollback:',e); });
}

/* Online-update helpers. The markup that calls them is still built only where
   ENABLE_OTA_AUTO is set; this file ships to every board, so on the others the
   functions simply have no buttons to be reached from. */
var _autoOtaUrl='',_autoOtaProgress=0;
function switchFwTab(t){
  document.getElementById('fw-tab-auto').style.display = t === 'auto' ? 'block' : 'none';
  document.getElementById('fw-tab-manual').style.display = t === 'manual' ? 'block' : 'none';
  document.getElementById('tab-auto-btn').setAttribute('aria-pressed', t === 'auto' ? 'true' : 'false');
  document.getElementById('tab-manual-btn').setAttribute('aria-pressed', t === 'manual' ? 'true' : 'false');
}
function checkForUpdates(){
  var res = document.getElementById('updateResult'), info = document.getElementById('updateInfo');
  res.style.color = 'var(--info)'; res.textContent = 'Checking...'; info.style.display = 'none'; _autoOtaUrl = '';
  fetch('https://api.github.com/repos/Keralots/BambuHelper/releases/latest')
    .then(function(r){ if (!r.ok) throw new Error('GitHub API returned ' + r.status); return r.json(); })
    .then(function(d){
      var latest = d.tag_name, current = DEV.fw;
      function parseVer(v){ var m = v.replace(/^v/,'').match(/^(\d+)\.(\d+)(?:\.(\d+))?(.*)$/); return m ? {major:parseInt(m[1]),minor:parseInt(m[2]),patch:m[3]?parseInt(m[3]):0,pre:m[4]!==''} : null; }
      function isNewer(a, b){ var av = parseVer(a), bv = parseVer(b); if (!av || !bv) return a !== b; if (av.major !== bv.major) return av.major > bv.major; if (av.minor !== bv.minor) return av.minor > bv.minor; if (av.patch !== bv.patch) return av.patch > bv.patch; return !av.pre && bv.pre; }
      if (!isNewer(latest, current)){ res.style.color = 'var(--success)'; res.textContent = latest === current ? 'You are up to date (' + current + ')' : 'Running newer version (' + current + ')'; return; }
      var board = DEV.board, expectedPrefix = 'BambuHelper-' + board + '-', otaBin = null;
      for (var i = 0; i < d.assets.length; i++){ var n = d.assets[i].name; if (n.startsWith(expectedPrefix) && n.endsWith('-ota.bin')){ otaBin = d.assets[i]; break; } }
      var slotB = parseInt(DEV.otaSlot, 10) || 0, flashMb = parseInt(DEV.flashMb, 10) || 0;
      if (otaBin && slotB > 0 && otaBin.size > slotB){
        res.style.color = 'var(--danger)';
        res.textContent = 'Update ' + latest + ' (' + Math.round(otaBin.size/1024) + ' KB) does not fit the ' + Math.round(slotB/1024) + ' KB update slot on this device.' +
          (flashMb >= 16 ? ' Back up settings (Export), then reflash once via the web flasher to repartition the ' + flashMb + ' MB chip - OTA works normally afterwards.'
                         : ' This board cannot hold this update - stay on the current version.');
        return;
      }
      res.style.color = 'var(--warn)'; res.textContent = 'Update available!';
      document.getElementById('updateVer').textContent = latest;
      document.getElementById('updateDate').textContent = new Date(d.published_at).toLocaleDateString();
      var installBtn = document.getElementById('installBtn'), link = document.getElementById('updateLink');
      if (otaBin){ _autoOtaUrl = otaBin.browser_download_url; link.href = otaBin.browser_download_url; link.style.display = 'inline-block'; installBtn.style.display = 'inline-block'; }
      else { installBtn.style.display = 'none'; link.style.display = 'none'; }
      info.style.display = 'block';
    })
    .catch(function(e){ res.style.color = 'var(--danger)'; res.textContent = 'Check failed: ' + e.message; console.warn('updateCheck:',e); });
}
function installUpdate(){
  if (!_autoOtaUrl) return;
  var btn = document.getElementById('installBtn');
  btn.disabled = true; btn.textContent = 'Installing...';
  document.getElementById('autoOtaWrap').style.display = 'block';
  document.getElementById('autoOtaBar').style.width = '0%';
  document.getElementById('autoOtaStatus').textContent = 'Starting...';
  _autoOtaProgress = 0;
  var p = new URLSearchParams(); p.append('url', _autoOtaUrl);
  fetch('/ota/auto',{method:'POST',body:p})
    .then(function(r){return r.json();})
    .then(function(d){ if (d.error) throw new Error(d.error); pollOtaStatus(); })
    .catch(function(e){ document.getElementById('autoOtaStatus').style.color = 'var(--danger)'; document.getElementById('autoOtaStatus').textContent = 'Error: ' + e.message; btn.disabled = false; btn.textContent = 'Install Update'; });
}
var _otaPoller = null;
function pollOtaStatus(){
  _otaPoller = setInterval(function(){
    fetch('/ota/status').then(function(r){return r.json();}).then(function(d){
      var bar = document.getElementById('autoOtaBar'), st = document.getElementById('autoOtaStatus');
      _autoOtaProgress = d.progress || 0;
      bar.style.width = d.progress + '%';
      if (d.status === 'done'){ clearInterval(_otaPoller); _otaPoller = null; bar.style.width = '100%'; st.style.color = 'var(--success)'; st.textContent = 'Done! Restarting device...'; waitForReboot(st); }
      else if (d.status && d.status.indexOf('failed') === 0){ clearInterval(_otaPoller); _otaPoller = null; st.style.color = 'var(--danger)'; st.textContent = d.status; var btn = document.getElementById('installBtn'); btn.disabled = false; btn.textContent = 'Retry'; }
      else { st.textContent = d.status + ' (' + d.progress + '%)'; }
    }).catch(function(){
      if (_autoOtaProgress >= 90){ clearInterval(_otaPoller); _otaPoller = null; var bar = document.getElementById('autoOtaBar'), st = document.getElementById('autoOtaStatus'); bar.style.width = '100%'; st.style.color = 'var(--success)'; st.textContent = 'Done! Restarting device...'; waitForReboot(st); }
    });
  }, 1000);
}



/* ============ Reboot / factory reset ============ */
function rebootDevice(){
  if (!confirm('Reboot device? Settings are preserved.')) return;
  fetch('/reboot',{method:'POST'}).then(function(){
    document.body.innerHTML = '<div style="text-align:center;padding-top:80px;font-family:sans-serif"><h2 style="color:#3FB950">Rebooting...</h2><p style="color:#8B949E;margin-top:10px">The device will be back in a few seconds.</p></div>';
  }).catch(function(){});
}
function factoryReset(){
  if (!confirm('Factory reset wipes ALL settings (WiFi, printers, gauge layout). Continue?')) return;
  if (!confirm('Are you absolutely sure? This cannot be undone.')) return;
  fetch('/reset',{method:'POST'})
    .then(function(r){ if(!r.ok) throw new Error('HTTP '+r.status); document.body.innerHTML='<div style="text-align:center;padding-top:80px"><h2>Factory reset started</h2><p>Reconnect to the BambuHelper setup network after restart.</p></div>'; })
    .catch(function(e){ showToast('Factory reset failed: '+e.message); });
}

/* ============ After-print reveal ============ */
function toggleAfterPrint(){
  var v = document.getElementById('afterprint').value;
  document.getElementById('customMinsWrap').style.display = (v === 'custom') ? 'block' : 'none';
  // Destination select is meaningless when the finish screen never times out.
  document.getElementById('afterFinWrap').style.display = (v === 'keepon') ? 'none' : 'block';
  var pong = document.getElementById('pong');
  var row = document.getElementById('pong-row');
  var showClock = (v !== 'keepon') && document.getElementById('afterfin').value !== 'off';
  pong.disabled = !showClock;
  if (row) row.style.opacity = showClock ? '1' : '0.4';
}

/* ============ Edge glow reveal ============ */
function toggleGlowFields(){
  var m = document.getElementById('glowm').value;
  document.getElementById('glowFields').style.display = (m === '0') ? 'none' : 'block';
  document.getElementById('glowClrWrap').style.display = (m === '1') ? 'block' : 'none';
}
function glowTestNow(){
  /* Send the current picker color so the preview matches even before Save. */
  var p = new URLSearchParams();
  p.append('clr', document.getElementById('glow_clr').value);
  fetch('/glow/test',{method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded'},body:p.toString()});
}

/* ============ Timezone list (AJAX-loaded to keep PROGMEM small) ============ */
fetch('/api/timezones').then(function(r){return r.json();}).then(function(d){
  var sel = document.getElementById('tz');
  for (var i = 0; i < d.zones.length; i++){
    var o = document.createElement('option');
    o.value = i; o.textContent = d.zones[i];
    if (i === d.selected) o.selected = true;
    sel.appendChild(o);
  }
}).catch(function(e){console.warn('tz load:',e);});



/* Smart Home RC3 browser command center */
var ccTimer = null;
function ccText(id,value){var e=document.getElementById(id);if(e)e.textContent=value==null?'—':String(value)}
function ccClass(id,name,on){var e=document.getElementById(id);if(e)e.classList.toggle(name,!!on)}
function ccPrinterSnapshot(){
  var status=document.getElementById('printerStatus'),health=document.getElementById('healthConnection'),mode=document.getElementById('healthMode'),name=document.getElementById('pname'),ip=document.getElementById('ip');
  var statusText=(health&&health.textContent&&health.textContent!=='Checking…')?health.textContent:(status?status.textContent:'Checking…');
  var lower=(statusText||'').toLowerCase();
  var connected=lower.indexOf('connected')>=0 && lower.indexOf('disconnected')<0;
  ccText('ccPrinter',connected?'Connected':statusText||'Not configured');
  ccText('ccConnection',statusText||'Checking…');
  ccText('ccMode',mode&&mode.textContent&&mode.textContent!=='—'?mode.textContent:(document.getElementById('connmode')&&document.getElementById('connmode').value==='local'?'LAN':'Cloud'));
  ccText('ccPrinterName',name&&name.value?name.value:'Printer '+(Number(currentSlot||0)+1));
  ccText('ccPrinterIp',ip&&ip.value?ip.value:'Not set');
  var att=document.getElementById('ccAttention'),btn=document.getElementById('ccAttentionAction');
  if(connected){
    if(att)att.classList.add('ok');
    ccText('ccAttentionTitle','Everything important is online');
    ccText('ccAttentionText','The selected printer is connected and the Waveshare control plane is responding.');
    if(btn){btn.textContent='Open printer';btn.onclick=function(){loadSection('printer')}}
  }else{
    if(att)att.classList.remove('ok');
    ccText('ccAttentionTitle','Printer connection needs attention');
    ccText('ccAttentionText','Verify the saved printer or scan the local network. Device and recovery services remain available.');
    if(btn){btn.textContent='Check connection';btn.onclick=ccVerifyPrinter}
  }
  return connected;
}
function refreshCommandCenter(manual){
  if(manual && typeof refreshPrinterHealth==='function')refreshPrinterHealth(true);
  if(typeof refreshTopStatusDots==='function')refreshTopStatusDots();
  var connected=ccPrinterSnapshot();
  fetch('/recovery/status?_='+Date.now(),{cache:'no-store'}).then(function(r){if(!r.ok)throw new Error('HTTP '+r.status);return r.json()}).then(function(d){
    ccText('ccDevice','Online');
    ccText('ccDeviceDetail',d.ip||location.host);
    ccText('ccFirmware',d.build||'Smart Home');
    ccText('ccFirmwareDetail',d.safeMode?'Safe Mode':'Normal');
    ccText('ccRecovery',d.safeMode?'SAFE MODE':'Ready');
    ccText('ccRecoveryDetail',d.safeMode?'Recovery environment active':'Independent console available');
    ccText('ccTouch',d.touch||'Unknown');
    ccText('ccWebReady',d.webReady?'READY':'STARTING');
    ccText('ccSlot',d.runningSlot||'—');
    ccText('ccCandidate',d.candidatePending?('Pending · attempt '+d.candidateAttempts):'Healthy');
    ccText('ccOverall',connected?'Operational':'Device online');
    ccText('ccUpdated','Updated '+new Date().toLocaleTimeString([], {hour:'numeric',minute:'2-digit'}));
    ccClass('ccStatusOrb','ok',true);ccClass('ccStatusOrb','bad',false);
  }).catch(function(){
    ccText('ccDevice','Attention');ccText('ccOverall','Recovery status unavailable');ccText('ccUpdated','Refresh to retry');
    ccClass('ccStatusOrb','ok',false);ccClass('ccStatusOrb','bad',true);
  });
  setTimeout(ccPrinterSnapshot,650);
  ccRefreshLiveWidget();
}
function ccVerifyPrinter(){loadSection('printer');setTimeout(function(){if(typeof verifyPrinterSetup==='function')verifyPrinterSetup()},80)}
function ccScanPrinter(){loadSection('printer');setTimeout(function(){if(typeof scanLan==='function')scanLan('lan')},80)}

// Promote Home once after this UI evolution. Afterwards normal last-page
// persistence resumes so the browser still respects the owner's workflow.
try{if(!localStorage.getItem('waveshare_cc_rc3')){localStorage.setItem('bambu_section','home');localStorage.setItem('waveshare_cc_rc3','1')}}catch(e){}



/* Smart Home v9.5 customizable browser widgets */
var CC_WIDGET_KEY='waveshare_widgets_v95';
var CC_WIDGET_IDS=['live','printer','display','device','quick'];
function ccWidgetPrefs(){try{var v=JSON.parse(localStorage.getItem(CC_WIDGET_KEY)||'null');if(v&&Array.isArray(v.visible))return v;}catch(e){}return{visible:CC_WIDGET_IDS.slice()}}
function ccSaveWidgetPrefs(p){try{localStorage.setItem(CC_WIDGET_KEY,JSON.stringify(p))}catch(e){}}
function ccApplyWidgetPrefs(){var p=ccWidgetPrefs();CC_WIDGET_IDS.forEach(function(id){var e=document.querySelector('[data-cc-widget="'+id+'"]');if(e)e.hidden=p.visible.indexOf(id)<0});}
function ccToggleWidget(id,on){var p=ccWidgetPrefs(),i=p.visible.indexOf(id);if(on&&i<0)p.visible.push(id);if(!on&&i>=0)p.visible.splice(i,1);ccSaveWidgetPrefs(p);ccApplyWidgetPrefs()}
function ccToggleWidgetEditor(){var e=document.getElementById('ccWidgetEditor');if(e)e.hidden=!e.hidden}
function ccInstallWidgetEditor(){
  var sec=document.getElementById('sec-home'),grid=sec&&sec.querySelector('.cc-grid');if(!grid||document.getElementById('ccWidgetEditor'))return;
  var existing=grid.querySelectorAll('.cc-panel');var ids=['printer','display','device','quick'];for(var i=0;i<existing.length&&i<ids.length;i++)existing[i].setAttribute('data-cc-widget',ids[i]);
  var live=document.createElement('div');live.className='card cc-panel cc-live-widget';live.setAttribute('data-cc-widget','live');live.innerHTML='<div class="cc-panel-head"><div><span class="cc-label">LIVE PRINT</span><h3 id="ccLiveName">Selected printer</h3></div><span class="cc-live-state" id="ccLiveState">Checking…</span></div><div class="cc-progress-track"><span id="ccLiveBar"></span></div><div class="cc-live-metrics"><div><span>Progress</span><strong id="ccLiveProgress">—</strong></div><div><span>Nozzle</span><strong id="ccLiveNozzle">—</strong></div><div><span>Bed</span><strong id="ccLiveBed">—</strong></div><div><span>Layer</span><strong id="ccLiveLayer">—</strong></div></div><div class="cc-panel-actions"><button type="button" class="cc-action" onclick="loadSection(\'printer\')"><strong>Printer setup</strong><span>Connection & gauges</span></button><button type="button" class="cc-action" onclick="ccVerifyPrinter()"><strong>Verify now</strong><span>Test connection</span></button></div>';
  grid.insertBefore(live,grid.firstChild);
  var hero=sec.querySelector('.cc-actions');if(hero){var b=document.createElement('button');b.type='button';b.className='btn btn-ghost';b.textContent='Customize widgets';b.onclick=ccToggleWidgetEditor;hero.appendChild(b)}
  var editor=document.createElement('div');editor.id='ccWidgetEditor';editor.className='cc-widget-editor';editor.hidden=true;editor.innerHTML='<div><span class="cc-label">CUSTOMIZE HOME</span><strong>Choose dashboard widgets</strong><p>Saved in this browser. Device settings are unchanged.</p></div><div class="cc-widget-toggles">'+[['live','Live print'],['printer','Printer'],['display','Smart display'],['device','Device health'],['quick','Quick control']].map(function(x){return '<label><input type="checkbox" data-widget="'+x[0]+'"> '+x[1]+'</label>'}).join('')+'</div>';
  var attention=document.getElementById('ccAttention');if(attention&&attention.parentNode)attention.parentNode.insertBefore(editor,attention.nextSibling);
  var p=ccWidgetPrefs();editor.querySelectorAll('input[data-widget]').forEach(function(c){c.checked=p.visible.indexOf(c.dataset.widget)>=0;c.onchange=function(){ccToggleWidget(c.dataset.widget,c.checked)}});ccApplyWidgetPrefs();
}
function ccRefreshLiveWidget(){
  if(!document.querySelector('[data-cc-widget="live"]')||document.querySelector('[data-cc-widget="live"]').hidden)return;
  fetch('/status?slot='+(Number(currentSlot||0)),{cache:'no-store'}).then(function(r){return r.json()}).then(function(d){
    ccText('ccLiveName',d.name||('Printer '+(Number(currentSlot||0)+1)));ccText('ccLiveState',d.connected?(d.state||'Connected'):'Offline');var p=Number(d.progress||0);ccText('ccLiveProgress',p+'%');ccText('ccLiveNozzle',d.nozzle==null?'—':Math.round(Number(d.nozzle))+'°');ccText('ccLiveBed',d.bed==null?'—':Math.round(Number(d.bed))+'°');ccText('ccLiveLayer',(d.layer||0)+' / '+(d.layers||0));var bar=document.getElementById('ccLiveBar');if(bar)bar.style.width=Math.max(0,Math.min(100,p))+'%';
  }).catch(function(){ccText('ccLiveState','Unavailable')});
}
setTimeout(function(){ccInstallWidgetEditor();ccRefreshLiveWidget()},0);


/* Smart Home v10.3 browser Workshop workspace */
var v103WorkshopData={};
function v103Minutes(m){m=Number(m||0);if(!m)return '—';var h=Math.floor(m/60),r=m%60;return h?(h+'h '+String(r).padStart(2,'0')+'m'):(r+'m')}
function v103Set(id,text){var e=document.getElementById(id);if(e)e.textContent=text==null?'—':String(text)}
function v103RefreshWorkshop(manual){
  var root=document.getElementById('sec-workshop');if(!root)return;
  fetch('/status?slot='+(Number(currentSlot||0))+'&_='+Date.now(),{cache:'no-store'}).then(function(r){if(!r.ok)throw new Error('HTTP '+r.status);return r.json()}).then(function(d){
    v103WorkshopData=d||{};var connected=!!d.connected,p=Number(d.progress||0);
    v103Set('wkState',connected?(d.state||'CONNECTED'):(d.configured?'OFFLINE':'SETUP'));v103Set('wkUpdated','Updated '+new Date().toLocaleTimeString([], {hour:'numeric',minute:'2-digit'}));
    var dot=document.getElementById('wkDot');if(dot)dot.className=connected?'ok':(d.configured?'bad':'warn');
    v103Set('wkProgress',p+'%');v103Set('wkProgressSub',connected?(d.state||'Printer connected'):'Printer unavailable');v103Set('wkRemaining',v103Minutes(d.remaining));v103Set('wkLayer',(Number(d.layer||0))+' / '+(Number(d.layers||0)));v103Set('wkChamber',d.chamber==null?'—':Math.round(Number(d.chamber))+'°C');
    v103Set('wkLightState',d.lightState===1?'On — tap to turn off':(d.lightState===0?'Off — tap to turn on':'State unavailable'));
    var ams=d.ams||{},trays=Array.isArray(ams.trays)?ams.trays:[],active=null;for(var i=0;i<trays.length;i++)if(trays[i].active){active=trays[i];break}
    if(!active&&ams.activeTray===254&&ams.externalPresent)active={type:ams.externalType||'External spool',remain:-1,color:ams.externalColor||'#8b949e',external:true};
    v103Set('wkAmsState',ams.present?((Number(ams.units||0))+' unit'+(Number(ams.units||0)===1?'':'s')):(ams.externalPresent?'External spool':'No AMS'));
    v103Set('wkLoadedName',active?(active.type||'Loaded filament'):'None loaded');v103Set('wkLoadedDetail',active?(active.external?'External spool':('AMS A'+(Number(active.slot)+1)+(Number(active.remain)>=0?' · '+active.remain+'% remaining':''))):'No active material reported');
    var spool=document.getElementById('wkLoadedSpool');if(spool)spool.style.setProperty('--spool-color',active&&active.color?active.color:'#59636e');
    var deck=document.getElementById('wkTrays');if(deck){if(!trays.length){deck.innerHTML='<div class="wk-empty">'+(ams.present?'AMS detected; no tray material data yet.':'No AMS tray data reported by the selected printer.')+'</div>'}else{deck.innerHTML=trays.map(function(tr){var remain=Number(tr.remain);return '<div class="wk-tray '+(tr.active?'active':'')+'"><span class="wk-tray-swatch" style="--tray-color:'+(tr.color||'#59636e')+'"></span><div><small>A'+(Number(tr.slot)+1)+'</small><strong>'+(tr.type||'Filament')+'</strong></div><span class="wk-remain">'+(remain>=0?remain+'%':'—')+'</span></div>'}).join('')}}
  }).catch(function(){v103Set('wkState','Unavailable');v103Set('wkUpdated','Device status could not be read');var dot=document.getElementById('wkDot');if(dot)dot.className='bad'});
}
function v103ToggleWorkshopLight(){var d=v103WorkshopData||{};if(typeof setLight!=='function')return;setLight(d.lightState===1?'off':'on');setTimeout(function(){v103RefreshWorkshop(false)},700)}

/* ============ Boot ============ */
/* Theme already applied by the inline <head> script before first paint;
   here we just sync the icon to match whatever state the document is in. */
applyThemeMode(document.documentElement.getAttribute('data-theme') || 'dark');

(function boot(){
  // First-time setup that runs once



  clInitAuthUi();



  toggleConnMode();
  toggleStatic();
  toggleBtnPin();
  toggleLed();
  toggleAfterPrint();
  // Initial section: URL hash, else last visited (localStorage), else printer.
  // Printer Errors only exists on boards that compiled its markup in, so it
  // joins the list only when the page actually carries it.
  var SECTIONS = ['home','printer','workshop','display','hardware','wifi','power','diag','advanced'];
  if (document.getElementById('sec-errors')) SECTIONS.push('errors');
  var initId = 'home';
  if (location.hash){
    var h = location.hash.substring(1);
    if (SECTIONS.indexOf(h) >= 0) initId = h;
  } else {
    try { var saved = localStorage.getItem('bambu_section'); if (saved && SECTIONS.indexOf(saved) >= 0) initId = saved; } catch(e){}
  }
  loadSection(initId);
  applyLabelMaxlen();
  setTimeout(function(){ selectPrinterTab(0); }, 80);
  setTimeout(function(){ selectPowerTab(0); }, 140);
  refreshHwInfo();
  initRollback();
  refreshTopStatusDots();
  setInterval(refreshTopStatusDots, 5000);
})();

/* ============ BambuHelper commissioning evolution v5 ============ */
var _commissionHealth = null;
var _commissionTouchTimer = null;
var _commissionTouchBaseline = null;
var _commissionTouchPassed = false;

function commissionStorageKey(name){
  var board = (typeof DEV === 'object' && DEV && DEV.board) ? DEV.board : 'device';
  return 'bh_commission_' + String(board) + '_' + name;
}
function commissionGetBool(name){
  try { return localStorage.getItem(commissionStorageKey(name)) === '1'; }
  catch(e){ return false; }
}
function commissionSetBool(name, value){
  try { localStorage.setItem(commissionStorageKey(name), value ? '1' : '0'); }
  catch(e){}
}
function commissionSetItem(id, state, detail){
  var el = document.getElementById(id);
  if (!el) return;
  el.classList.remove('commission-pass','commission-warn','commission-fail','commission-pending');
  el.classList.add('commission-' + state);
  var small = el.querySelector('small');
  if (small) small.textContent = detail;
}
function loadCommissionManual(){
  var lcd = document.getElementById('commissionLcd');
  var rec = document.getElementById('commissionRecovery');
  var cas = document.getElementById('commissionCase');
  if (lcd) lcd.checked = commissionGetBool('lcd');
  if (rec) rec.checked = commissionGetBool('recovery');
  if (cas) cas.checked = commissionGetBool('case');
  _commissionTouchPassed = commissionGetBool('touch');
}
function saveCommissionManual(){
  commissionSetBool('lcd', !!document.getElementById('commissionLcd').checked);
  commissionSetBool('recovery', !!document.getElementById('commissionRecovery').checked);
  commissionSetBool('case', !!document.getElementById('commissionCase').checked);
  renderCommissioning();
}

function expectedWs350Board(h){
  var joined = String((h.board || '') + ' ' + (h.panel || '') + ' ' + (h.variant || ''));
  return /Waveshare/i.test(joined) && /ST7796|ws_lcd_350/i.test(joined);
}

function renderCommissioning(){
  var h = _commissionHealth;
  if (!h) return;

  var canvasOk = (h.width === 480 && h.height === 320) ||
                 (h.width === 320 && h.height === 480);
  var boardOk = expectedWs350Board(h) && canvasOk;
  commissionSetItem(
    'commissionBoard',
    boardOk ? 'pass' : 'warn',
    (h.board || 'Unknown board') + ' · ' + (h.panel || 'Unknown panel') +
      ' · ' + h.width + '×' + h.height
  );

  var psramOk = Number(h.psramSize || 0) >= 4 * 1024 * 1024;
  var heapKb = Math.round(Number(h.freeHeap || 0) / 1024);
  var psramMb = (Number(h.psramSize || 0) / 1048576).toFixed(1);
  commissionSetItem(
    'commissionMemory',
    psramOk ? 'pass' : 'warn',
    'Free heap ' + heapKb + ' KB · PSRAM ' + psramMb + ' MB'
  );

  var touchConfigured = Number(h.buttonType) === 3 && !!h.touchscreenConfigured;
  commissionSetItem(
    'commissionTouch',
    _commissionTouchPassed ? 'pass' : (touchConfigured ? 'pending' : 'warn'),
    _commissionTouchPassed
      ? 'BambuHelper registered a touchscreen press'
      : (touchConfigured
          ? 'Touchscreen input configured; run the live tap test'
          : 'Touchscreen is not the active input type')
  );

  var wifiOk = !!h.wifiConnected;
  var rssi = Number(h.rssi || 0);
  var wifiDetail = wifiOk
    ? ('Connected · ' + rssi + ' dBm' + (rssi <= -75 ? ' · weak signal' : ''))
    : 'Not connected to normal WiFi';
  commissionSetItem(
    'commissionWifi',
    wifiOk ? (rssi <= -75 ? 'warn' : 'pass') : 'pending',
    wifiDetail
  );

  var printerOk = !!h.printerConnected;
  commissionSetItem(
    'commissionPrinter',
    printerOk ? 'pass' : (h.printerConfigured ? 'warn' : 'pending'),
    printerOk
      ? 'Connected and receiving status'
      : (h.printerConfigured ? 'Configured but not connected' : 'Printer not configured yet')
  );

  var dual = !!h.dualNozzle;
  commissionSetItem(
    'commissionDual',
    dual ? 'pass' : (printerOk ? 'warn' : 'pending'),
    dual
      ? ('Dual-nozzle telemetry detected' + (h.hasAuxFanRight ? ' · X2D right aux fan detected' : ''))
      : (printerOk ? 'Connected, but dual-nozzle capability is not yet reported' : 'Waiting for printer telemetry')
  );

  var lcd = commissionGetBool('lcd');
  var recovery = commissionGetBool('recovery');
  var enclosure = commissionGetBool('case');
  var core = boardOk && psramOk && _commissionTouchPassed && lcd;
  var integrated = core && wifiOk && printerOk;
  var finalReady = integrated && recovery && enclosure;

  var badge = document.getElementById('commissionBadge');
  var summary = document.getElementById('commissionSummary');
  if (!badge || !summary) return;

  if (finalReady){
    badge.textContent = 'COMMISSIONED';
    badge.className = 'commission-badge commission-badge-pass';
    summary.innerHTML = '<strong>Commissioning complete.</strong> Hardware, network, printer telemetry, recovery access and enclosure fit are all confirmed.';
  } else if (integrated){
    badge.textContent = 'INTEGRATED';
    badge.className = 'commission-badge commission-badge-pass';
    summary.innerHTML = '<strong>Hardware + printer integration passed.</strong> Finish the physical recovery/enclosure checks before sealing the case.';
  } else if (core){
    badge.textContent = 'HARDWARE PASS';
    badge.className = 'commission-badge commission-badge-pass';
    summary.innerHTML = '<strong>Core hardware passed.</strong> Next: connect WiFi and verify live printer telemetry.';
  } else {
    badge.textContent = 'IN PROGRESS';
    badge.className = 'commission-badge';
    summary.innerHTML = '<strong>Commissioning is not complete.</strong> Run the touch test and confirm the physical LCD check first.';
  }
}

function refreshCommissioning(userInitiated){
  fetch('/hardware/health?slot=' + currentSlot, {cache:'no-store'})
    .then(function(r){
      if (!r.ok) throw new Error('HTTP ' + r.status);
      return r.json();
    })
    .then(function(h){
      _commissionHealth = h;
      renderCommissioning();
      if (userInitiated) showToast('Hardware health refreshed');
    })
    .catch(function(e){
      commissionSetItem('commissionBoard','fail','Could not read hardware health');
      var b = document.getElementById('commissionBadge');
      if (b) {
        b.textContent = 'UNAVAILABLE';
        b.className = 'commission-badge commission-badge-fail';
      }
      console.warn('refreshCommissioning:', e);
    });
}

function stopTouchValidation(){
  if (_commissionTouchTimer){
    clearInterval(_commissionTouchTimer);
    _commissionTouchTimer = null;
  }
  var prompt = document.getElementById('commissionTouchPrompt');
  if (prompt) prompt.hidden = true;
  var btn = document.getElementById('commissionTouchBtn');
  if (btn){ btn.disabled = false; btn.textContent = 'Test touch'; }
}

function startTouchValidation(){
  stopTouchValidation();
  var btn = document.getElementById('commissionTouchBtn');
  var prompt = document.getElementById('commissionTouchPrompt');
  if (btn){ btn.disabled = true; btn.textContent = 'Waiting for tap…'; }
  if (prompt) prompt.hidden = false;

  fetch('/hardware/health?slot=' + currentSlot, {cache:'no-store'})
    .then(function(r){
      if (!r.ok) throw new Error('HTTP ' + r.status);
      return r.json();
    })
    .then(function(h){
      _commissionTouchBaseline = Number(h.pressCount || 0);
      var deadline = Date.now() + 15000;

      _commissionTouchTimer = setInterval(function(){
        fetch('/hardware/health?slot=' + currentSlot, {cache:'no-store'})
          .then(function(r){
            if (!r.ok) throw new Error('HTTP ' + r.status);
            return r.json();
          })
          .then(function(next){
            _commissionHealth = next;
            if (Number(next.pressCount || 0) > _commissionTouchBaseline){
              _commissionTouchPassed = true;
              commissionSetBool('touch', true);
              stopTouchValidation();
              renderCommissioning();
              showToast('Touch input verified');
              return;
            }
            if (Date.now() >= deadline){
              stopTouchValidation();
              commissionSetItem(
                'commissionTouch',
                'warn',
                'No touch press was registered in 15 seconds'
              );
              showToast('Touch test timed out');
            }
          })
          .catch(function(e){
            stopTouchValidation();
            commissionSetItem(
              'commissionTouch',
              'fail',
              'Health polling failed during touch test'
            );
            console.warn('touch validation:', e);
          });
      }, 600);
    })
    .catch(function(e){
      stopTouchValidation();
      showToast('Could not start touch test');
      console.warn('startTouchValidation:', e);
    });
}

function exportCommissioningReport(){
  if (!_commissionHealth){
    showToast('Refresh hardware health first');
    return;
  }

  var report = {
    generatedAt: new Date().toISOString(),
    purpose: 'BambuHelper hardware commissioning report',
    health: _commissionHealth,
    manual: {
      lcdVisualPass: commissionGetBool('lcd'),
      recoveryAccessPass: commissionGetBool('recovery'),
      enclosureFitPass: commissionGetBool('case'),
      touchLivePass: _commissionTouchPassed
    }
  };

  [
    'ssid','password','pass','token','email','serial','name','accessCode',
    'cloudUserId','ip'
  ].forEach(function(k){
    if (report.health) delete report.health[k];
  });

  var blob = new Blob(
    [JSON.stringify(report,null,2)],
    {type:'application/json;charset=utf-8'}
  );
  var url = URL.createObjectURL(blob);
  var a = document.createElement('a');
  a.href = url;
  a.download = 'bambuhelper-commissioning-' +
    new Date().toISOString().replace(/[:.]/g,'-') + '.json';
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  setTimeout(function(){ URL.revokeObjectURL(url); }, 1000);
  showToast('Commissioning report exported');
}

setTimeout(function(){
  loadCommissionManual();
  refreshCommissioning(false);
}, 0);

setInterval(function(){
  if (
    typeof currentSection !== 'undefined' &&
    currentSection === 'hardware'
  ){
    refreshCommissioning(false);
  }
}, 5000);

/* ============ BambuHelper smart remote profiles evolution v3 ============ */
var BH_PROFILE_PREFIX = 'bh_monitor_profile_';
/* _profileCaps is initialised at the top of app.js, before boot reads it. */

function gaugeProfileStorageKey(){
  return BH_PROFILE_PREFIX + String(currentSlot);
}

function setCurrentProfileCaps(d){
  d = d || {};
  _profileCaps = {
    hasDualNozzle: !!d.hasDualNozzle,
    hasAuxFanRight: !!d.hasAuxFanRight,
    hasExhaustFan: !!d.hasExhaustFan,
    hasTasmota: !!d.hasTasmota,
    hasLanCamera: !!d.hasLanCamera
  };
  refreshGaugeProfileUi();
}

function currentPrinterLooksX2D(){
  var sel = document.getElementById('cl_acctsel');
  if (sel && sel.selectedIndex >= 0){
    var opt = sel.options[sel.selectedIndex];
    if (opt && /X2D/i.test(opt.getAttribute('data-model') || '')) return true;
  }
  var name = document.getElementById('cl_pname');
  return !!(name && /X2D/i.test(name.value || ''));
}

function gaugeOptionAvailable(selectId, gaugeId){
  var sel = document.getElementById(selectId);
  if (!sel) return false;
  for (var i = 0; i < sel.options.length; i++){
    if (String(sel.options[i].value) === String(gaugeId)) return true;
  }
  return false;
}

function setGaugeWithFallback(selectId, candidates){
  var sel = document.getElementById(selectId);
  if (!sel) return null;
  for (var i = 0; i < candidates.length; i++){
    var gaugeId = candidates[i];
    if (gaugeOptionAvailable(selectId, gaugeId)){
      sel.value = String(gaugeId);
      return gaugeId;
    }
  }
  if (gaugeOptionAvailable(selectId, 0)){
    sel.value = '0';
    return 0;
  }
  return null;
}

function profileDefinition(name){
  var dual = !!!!(_profileCaps && _profileCaps.hasDualNozzle) || currentPrinterLooksX2D();
  var rightAux = !!_profileCaps.hasAuxFanRight;

  if (name === 'x2d'){
    return {
      label: 'X2D dual-nozzle',
      requiresDual: true,
      gauges: [1, 30, 29, 3, 14, rightAux ? 23 : 7],
      idle: [30, 29]
    };
  }

  if (name === 'thermal'){
    return dual ? {
      label: 'Thermal & fans',
      gauges: [30, 29, 3, 7, 4, rightAux ? 23 : 5],
      idle: [30, 29]
    } : {
      label: 'Thermal & fans',
      gauges: [2, 3, 7, 4, 5, 6],
      idle: [2, 3]
    };
  }

  if (name === 'ams'){
    return {
      label: 'AMS overview',
      gauges: [1, 25, 26, 27, 28, 14],
      idle: dual ? [30, 29] : [2, 3]
    };
  }

  return dual ? {
    label: 'Remote status',
    gauges: [1, 30, 29, 3, 14, 7],
    idle: [30, 29]
  } : {
    label: 'Remote status',
    gauges: [1, 2, 3, 14, 7, 4],
    idle: [2, 3]
  };
}

function profileGaugeName(id){
  return gaugeTypes[id] ? gaugeTypes[id].name : ('Gauge ' + id);
}

function refreshGaugeProfileUi(){
  var caps = document.getElementById('profileCapabilities');
  var x2dBtn = document.getElementById('x2dProfileBtn');
  var summary = document.getElementById('profileSummary');
  if (!caps || !summary) return;

  if (typeof IS_ROUND !== 'undefined' && IS_ROUND){
    caps.innerHTML = '<strong>Round display detected.</strong> Profile presets are disabled because this board does not use the standard 2×3 print dashboard.';
    var buttons = document.querySelectorAll('.profile-option');
    for (var r = 0; r < buttons.length; r++) buttons[r].disabled = true;
    summary.textContent = 'Use the existing round-display skin and mini-gauge controls instead.';
    summary.className = 'profile-warning';
    return;
  }

  var parts = [];
  if (!!(_profileCaps && _profileCaps.hasDualNozzle)) parts.push('dual nozzle');
  if (_profileCaps.hasAuxFanRight) parts.push('right aux fan');
  if (_profileCaps.hasExhaustFan) parts.push('exhaust fan');
  if (!parts.length) parts.push('standard telemetry');

  caps.innerHTML =
    '<strong>Detected:</strong> ' + parts.join(' · ') +
    '. Presets automatically fall back when a preferred tile is unavailable.';

  var x2dReady = !!!!(_profileCaps && _profileCaps.hasDualNozzle) || currentPrinterLooksX2D();
  if (x2dBtn){
    x2dBtn.disabled = !x2dReady;
    x2dBtn.title = x2dReady ? '' : 'Available after a dual-nozzle/X2D printer is detected.';
  }

  var stored = '';
  try { stored = localStorage.getItem(gaugeProfileStorageKey()) || ''; } catch(e){}
  if (stored){
    summary.textContent = 'Last applied on this browser: ' + stored + '.';
    summary.className = 'profile-applied';
  } else {
    summary.textContent = 'Choose a profile to apply it to the selected printer slot.';
    summary.className = '';
  }
}

function loadProfileCapsThen(callback){
  fetch('/printer/config?slot=' + currentSlot, {cache:'no-store'})
    .then(function(r){
      if (!r.ok) throw new Error('HTTP ' + r.status);
      return r.json();
    })
    .then(function(d){
      setCurrentProfileCaps(d);
      if (callback) callback();
    })
    .catch(function(e){
      console.warn('loadProfileCapsThen:', e);
      if (callback) callback();
    });
}

function commitGaugeProfile(profile){
  var applied = [];
  for (var i = 0; i < 6; i++){
    var selected = setGaugeWithFallback(
      'gs' + i,
      [profile.gauges[i], 2, 3, 14, 1, 0]
    );
    if (selected !== null) applied.push(profileGaugeName(selected));
  }
  for (var j = 0; j < 2; j++){
    setGaugeWithFallback('is' + j, [profile.idle[j], 2, 3, 0]);
  }

  try { localStorage.setItem(gaugeProfileStorageKey(), profile.label); } catch(e){}
  var summary = document.getElementById('profileSummary');
  if (summary){
    summary.textContent = profile.label + ' applied: ' + applied.join(' · ');
    summary.className = 'profile-applied';
  }

  saveGaugeLayout();
}

function applyGaugeProfile(name){
  if (typeof IS_ROUND !== 'undefined' && IS_ROUND){
    showToast('Profiles are not available on the round dashboard');
    return;
  }

  loadProfileCapsThen(function(){
    var profile = profileDefinition(name);
    if (
      profile.requiresDual &&
      !(!!(_profileCaps && _profileCaps.hasDualNozzle) || currentPrinterLooksX2D())
    ){
      showToast('X2D profile requires a detected dual-nozzle/X2D printer');
      refreshGaugeProfileUi();
      return;
    }
    commitGaugeProfile(profile);
  });
}

function clearGaugeProfileMemory(){
  try { localStorage.removeItem(gaugeProfileStorageKey()); } catch(e){}
  var summary = document.getElementById('profileSummary');
  if (summary){
    summary.textContent =
      'BambuHelper default layout restored in the editor. Save the gauge layout to persist it.';
    summary.className = '';
  }
}

/* ============ BambuHelper resilience evolution v2 ============ */
var BH_HEALTH_PREFIX = 'bh_printer_verified_';
var _healthBusy = false;

function healthStorageKey(){
  return BH_HEALTH_PREFIX + String(currentSlot);
}
function setHealthValue(id, text, kind){
  var el = document.getElementById(id);
  if (!el) return;
  el.textContent = text;
  el.classList.remove('health-ok','health-warn','health-error');
  if (kind) el.classList.add('health-' + kind);
}
function formatHealthTimestamp(iso){
  if (!iso) return 'Never on this browser';
  var d = new Date(iso);
  if (isNaN(d.getTime())) return 'Never on this browser';
  return d.toLocaleString();
}
function getLastVerified(){
  try { return localStorage.getItem(healthStorageKey()) || ''; }
  catch(e){ return ''; }
}
function recordVerifiedNow(){
  var iso = new Date().toISOString();
  try { localStorage.setItem(healthStorageKey(), iso); } catch(e){}
  setHealthValue('healthLastVerified', formatHealthTimestamp(iso), 'ok');
}
function printerModeLabel(){
  var mode = document.getElementById('connmode');
  if (!mode) return '—';
  return mode.value === 'cloud_all' ? 'Bambu Cloud' : 'LAN Direct';
}
function renderHealthAdvice(d){
  var el = document.getElementById('healthAdvice');
  if (!el) return;
  var mode = document.getElementById('connmode');
  var cloud = mode && mode.value === 'cloud_all';
  var model = '';
  var sel = document.getElementById('cl_acctsel');
  if (sel && sel.selectedIndex >= 0){
    var opt = sel.options[sel.selectedIndex];
    if (opt) model = opt.getAttribute('data-model') || '';
  }

  el.hidden = false;
  el.className = 'health-advice';

  if (d && d.connected){
    el.classList.add('health-advice-ok');
    el.innerHTML = '<strong>Healthy.</strong> BambuHelper is connected and receiving printer status.';
    return;
  }

  if (cloud){
    el.innerHTML =
      '<strong>Cloud connection needs attention.</strong> Settings may be saved while the cloud session is disconnected. ' +
      'Check internet access, then use the email-code sign-in path if Bambu authentication needs to be refreshed.';
    if (/X2D/i.test(model)){
      el.innerHTML +=
        ' <span class="x2d-advisory"><strong>X2D:</strong> keep this slot on Bambu Cloud; the current BambuHelper LAN Direct compatibility table does not list X2D.</span>';
    }
  } else {
    el.innerHTML =
      '<strong>LAN connection needs attention.</strong> Confirm the printer IP, serial number, LAN access code, ' +
      'and that the ESP32 can reach the printer on the local network.';
  }

  if (!d || !d.configured){
    el.classList.add('health-advice-error');
    el.innerHTML =
      '<strong>Printer is not fully configured.</strong> Complete Connection, Access, and Printer above, then choose Save & Verify.';
  }
}
function updateHealthPanel(d){
  var last = getLastVerified();
  setHealthValue('healthDevice','Online','ok');
  setHealthValue('healthMode',printerModeLabel(),'');
  setHealthValue('healthLastVerified',formatHealthTimestamp(last),last?'ok':'');

  if (!d){
    setHealthValue('healthConnection','Unavailable','error');
    renderHealthAdvice(null);
    return;
  }
  if (d.connected){
    setHealthValue('healthConnection','Connected','ok');
  } else if (d.configured){
    setHealthValue('healthConnection','Disconnected','warn');
  } else {
    setHealthValue('healthConnection','Not configured','error');
  }
  renderHealthAdvice(d);
}
function refreshPrinterHealth(userInitiated){
  if (_healthBusy) return;
  _healthBusy = true;
  fetch('/printer/config?slot=' + currentSlot, {cache:'no-store'})
    .then(function(r){
      if (!r.ok) throw new Error('HTTP ' + r.status);
      return r.json();
    })
    .then(function(d){
      updateHealthPanel(d);
      if (userInitiated) showToast(d.connected ? 'Connection is healthy' : 'Connection check complete');
    })
    .catch(function(e){
      updateHealthPanel(null);
      if (userInitiated) showToast('Could not refresh printer health');
      console.warn('refreshPrinterHealth:', e);
    })
    .then(function(){ _healthBusy = false; });
}

function scrubSupportValue(value, key){
  var sensitive = /token|pass|password|code|access|email|ssid|secret|credential/i.test(key || '');
  if (sensitive) return '[redacted]';
  if (Array.isArray(value)) return value.map(function(v){ return scrubSupportValue(v, ''); });
  if (value && typeof value === 'object'){
    var out = {};
    Object.keys(value).forEach(function(k){ out[k] = scrubSupportValue(value[k], k); });
    return out;
  }
  return value;
}
function downloadSupportText(name, text){
  var blob = new Blob([text], {type:'text/plain;charset=utf-8'});
  var url = URL.createObjectURL(blob);
  var a = document.createElement('a');
  a.href = url;
  a.download = name;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  setTimeout(function(){ URL.revokeObjectURL(url); }, 1000);
}
function exportSupportReport(){
  var btn = document.getElementById('supportBundleBtn');
  if (btn){ btn.disabled = true; btn.textContent = 'Preparing...'; }
  Promise.all([
    fetch('/printer/config?slot=' + currentSlot, {cache:'no-store'}).then(function(r){
      if (!r.ok) throw new Error('printer config HTTP ' + r.status);
      return r.json();
    }),
    Promise.resolve(typeof DEV === 'object' ? DEV : {})
  ]).then(function(parts){
    var cfg = scrubSupportValue(parts[0], '');
    var dev = scrubSupportValue(parts[1], '');
    var report = {
      generatedAt: new Date().toISOString(),
      purpose: 'BambuHelper support report (credentials redacted)',
      selectedSlot: currentSlot,
      connectionMode: printerModeLabel(),
      lastVerifiedOnThisBrowser: getLastVerified() || null,
      browser: navigator.userAgent,
      device: dev,
      printerConfig: cfg
    };
    var stamp = new Date().toISOString().replace(/[:.]/g,'-');
    downloadSupportText('bambuhelper-support-' + stamp + '.json', JSON.stringify(report, null, 2));
    showToast('Redacted support report exported');
  }).catch(function(e){
    showToast('Could not export support report');
    console.warn('exportSupportReport:', e);
  }).then(function(){
    if (btn){ btn.disabled = false; btn.textContent = 'Export Support Report'; }
  });
}

setInterval(function(){
  if (currentSection === 'printer') refreshPrinterHealth(false);
}, 10000);

/* BambuHelper commissioning evolution v5 */

/* ============ BambuHelper smart display platform evolution v6 ============ */
function setHubStatus(message, kind){
  var el = document.getElementById('hubStatus');
  if (!el) return;
  el.textContent = message || '';
  el.className = 'action-status' + (kind ? ' ' + kind : '');
}

function loadSmartHubConfig(){
  var card = document.getElementById('smartHubCard');
  if (!card) return;

  fetch('/hub/config', {cache:'no-store'})
    .then(function(r){
      if (!r.ok) throw new Error('HTTP ' + r.status);
      return r.json();
    })
    .then(function(d){
      var available = !!d.available;
      var badge = document.getElementById('hubAvailability');
      if (badge){
        badge.textContent = available ? 'WS350 READY' : 'NOT AVAILABLE';
        badge.className = 'hub-platform-badge' +
          (available ? ' hub-platform-badge-ready' : '');
      }

      document.getElementById('hubEnabled').checked = !!d.enabled;
      document.getElementById('hubUrl').value = d.customUrl || '';
      document.getElementById('hubRefresh').value =
        String(d.refreshSeconds || 60);
      document.getElementById('hubReturn').value =
        String(d.returnSeconds == null ? 60 : d.returnSeconds);

      if (!available){
        card.classList.add('hub-unavailable');
        setHubStatus('Smart Display v6 is enabled only on the Waveshare 3.5 target.', 'warn');
      } else {
        setHubStatus(
          d.customHealthy
            ? 'Custom feed: connected'
            : ('Custom feed: ' + (d.customStatus || 'not configured')),
          d.customHealthy ? 'ok' : ''
        );
      }
    })
    .catch(function(e){
      setHubStatus('Could not read Smart Display settings.', 'error');
      console.warn('loadSmartHubConfig:', e);
    });
}

function saveSmartHubConfig(){
  var btn = document.getElementById('hubSaveBtn');
  var p = new URLSearchParams();
  p.append('enabled', document.getElementById('hubEnabled').checked ? '1' : '0');
  p.append('url', document.getElementById('hubUrl').value.trim());
  p.append('refresh', document.getElementById('hubRefresh').value);
  p.append('return', document.getElementById('hubReturn').value);

  if (btn){ btn.disabled = true; btn.textContent = 'Saving...'; }
  setHubStatus('Saving Smart Display settings...', '');

  fetch('/hub/config', {
    method:'POST',
    headers:{'Content-Type':'application/x-www-form-urlencoded'},
    body:p.toString()
  })
    .then(function(r){
      return r.json().then(function(d){
        if (!r.ok) throw new Error(d.message || ('HTTP ' + r.status));
        return d;
      });
    })
    .then(function(){
      setHubStatus('Smart Display settings saved.', 'ok');
      showToast('Smart Display settings saved');
      loadSmartHubConfig();
    })
    .catch(function(e){
      setHubStatus('Save failed: ' + e.message, 'error');
    })
    .then(function(){
      if (btn){ btn.disabled = false; btn.textContent = 'Save Smart Display'; }
    });
}

function hubShow(page){
  var p = new URLSearchParams();
  p.append('page', page);
  fetch('/hub/show', {
    method:'POST',
    headers:{'Content-Type':'application/x-www-form-urlencoded'},
    body:p.toString()
  })
    .then(function(r){
      if (!r.ok) throw new Error('HTTP ' + r.status);
      return r.json();
    })
    .then(function(){
      showToast(page === 'printer' ? 'Printer dashboard selected'
                                   : ('Smart Display: ' + page));
    })
    .catch(function(){
      showToast('Could not change Smart Display page');
    });
}

setTimeout(loadSmartHubConfig, 0);

/* ============ Smart Home v9.2 portal evolution ============ */
function v92PortalEvolution(){
  if (document.getElementById('v92EvolutionStyle')) return;

  var style = document.createElement('style');
  style.id = 'v92EvolutionStyle';
  style.textContent =
    '.v92-build-pill{margin-left:6px;border-color:rgba(249,115,22,.45)!important;color:#ff9b68!important;background:rgba(249,115,22,.10)!important}' +
    '.v92-discovery{margin-top:12px;padding:12px 14px;border:1px solid rgba(46,160,67,.45);border-radius:10px;background:rgba(46,160,67,.08);line-height:1.45}' +
    '.v92-discovery strong{color:var(--text)}' +
    '.v92-discovery-meta{margin-top:4px;color:var(--text-dim);font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:12px}' +
    '.v92-discovery-next{margin-top:7px;color:var(--success);font-size:12.5px}' +
    '.v92-hw-note{margin-top:6px;color:var(--text-dim);font-size:12px}';
  document.head.appendChild(style);

  var brand = document.querySelector('.brand');
  if (brand && !document.getElementById('smartHomeBuildPill')){
    var pill = document.createElement('span');
    pill.id = 'smartHomeBuildPill';
    pill.className = 'version-pill v92-build-pill';
    pill.textContent = 'Workshop OS';
    brand.appendChild(pill);
  }

  var intro = document.querySelector('#sec-printer .section-intro p');
  var tabs = document.querySelectorAll('#printerTabs .tab-btn');
  if (intro && tabs.length){
    intro.textContent = 'Configure ' + tabs.length + ' printer slot' + (tabs.length === 1 ? '' : 's') +
      ' available on this hardware build. Each slot is independent - use LAN Direct or Bambu Cloud.';
    var note = document.createElement('div');
    note.className = 'v92-hw-note';
    note.textContent = 'Smart Home reports the slots this device can actually run instead of advertising unavailable capacity.';
    intro.parentNode.appendChild(note);
  }

  v92DiscoveryCard();
}
setTimeout(v92PortalEvolution, 0);

/* ============ Workshop OS v11.20 WS350 physical safety ============ */
function v1120Ws350Safety(){
  // Touch safety is independent of portal authentication: this integrated
  // panel must never inherit a persisted Disabled mode and strand recovery.
  var bt = document.getElementById('btntype');
  if (bt){
    bt.value = '3';
    bt.disabled = true;
    var row = bt.closest ? bt.closest('.field') : bt.parentElement;
    if (row && !document.getElementById('v1120TouchNote')){
      var note = document.createElement('div');
      note.id = 'v1120TouchNote';
      note.className = 'hint';
      note.textContent = 'WS350 integrated touchscreen stays enabled as an independent physical recovery path.';
      row.appendChild(note);
    }
  }
}
setTimeout(v1120Ws350Safety, 0);

/* BambuHelper smart display platform evolution v6 */


/* Smart Home v9.6 printer workspace */
var v96PrinterTab = 'overview';
var v96SelectedGaugeSlot = 0;
var v96PrinterDirty = false;
var v96PrinterTimer = null;

function v96Esc(s){return (window.esc?esc(String(s==null?'':s)):String(s==null?'':s).replace(/[&<>\"']/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;',"'":'&#39;'}[c]}))}
function v96ById(id){return document.getElementById(id)}
function v96Txt(id,value){var e=v96ById(id);if(e)e.textContent=(value==null||value==='')?'—':String(value)}
function v96FindCard(root,title){var cards=root.querySelectorAll('.card');for(var i=0;i<cards.length;i++){var h=cards[i].querySelector('h3');if(h&&h.textContent.trim().toLowerCase()===title.toLowerCase())return cards[i]}return null}
function v96PrinterArt(){return '<div class="v96-printer-art" aria-hidden="true"><div class="v96-ams"><i class="v96-spool"></i><i class="v96-spool"></i><i class="v96-spool"></i><i class="v96-spool"></i></div><div class="v96-machine"><i class="v96-bed"></i><i class="v96-part"></i></div></div>'}
function v96OpenPrinterTab(name){v96PrinterTab=name;document.querySelectorAll('.v96-tab').forEach(function(b){b.classList.toggle('active',b.getAttribute('data-tab')===name);b.setAttribute('aria-selected',b.getAttribute('data-tab')===name?'true':'false')});document.querySelectorAll('.v96-panel').forEach(function(p){p.classList.toggle('active',p.getAttribute('data-panel')===name)});if(name==='display'){v96RenderDisplayPreview();v96BuildWidgetLibrary()}if(name==='automation')v96SyncAutomationUi();try{localStorage.setItem('waveshare_printer_tab',name)}catch(e){}}
function v96SetDirty(on){v96PrinterDirty=!!on;var bar=v96ById('v96StickySave');if(bar)bar.classList.toggle('show',v96PrinterDirty);v96Txt('v96SaveContext',v96PrinterTab==='connection'?'Printer connection':v96PrinterTab==='display'?'Touchscreen display':v96PrinterTab==='automation'?'Automation rules':'Printer settings')}
function v96DiscardChanges(){if(typeof selectPrinterTab==='function')selectPrinterTab(Number(currentSlot||0));v96SetDirty(false);setTimeout(function(){v96RenderDisplayPreview();v96SyncAutomationUi();v96RefreshPrinterWorkspace()},450)}
function v96SaveChanges(){if(v96PrinterTab==='connection'&&typeof savePrinter==='function')savePrinter();else if(v96PrinterTab==='display'&&typeof saveGaugeLayout==='function')saveGaugeLayout();else if(v96PrinterTab==='automation'&&typeof saveLightConfig==='function')saveLightConfig();else if(typeof savePrinter==='function')savePrinter();setTimeout(function(){v96SetDirty(false);v96RefreshPrinterWorkspace()},850)}
function v96WidgetValue(id){var s=v96ById(id);if(!s)return 0;return Number(s.value||0)}
function v96GaugeName(id){return(window.gaugeTypes&&gaugeTypes[id])?gaugeTypes[id].name:('Widget '+id)}
function v96RenderDisplayPreview(){var host=v96ById('v96ScreenGrid');if(!host)return;var html='';for(var i=0;i<6;i++){var id=v96WidgetValue('gs'+i);html+='<button type="button" class="v96-screen-tile '+(v96SelectedGaugeSlot===i?'selected':'')+'" onclick="v96SelectGaugeSlot('+i+')"><span>'+(['Top left','Top center','Top right','Bottom left','Bottom center','Bottom right'][i])+'</span><strong>'+v96Esc(v96GaugeName(id))+'</strong></button>'}host.innerHTML=html;var ready=v96ById('v96ReadyGrid');if(ready){ready.innerHTML='';for(var j=0;j<2;j++){var rid=v96WidgetValue('is'+j),slot=6+j;ready.innerHTML+='<button type="button" class="v96-screen-tile '+(v96SelectedGaugeSlot===slot?'selected':'')+'" onclick="v96SelectGaugeSlot('+slot+')"><span>'+(j?'Ready right':'Ready left')+'</span><strong>'+v96Esc(v96GaugeName(rid))+'</strong></button>'}}v96Txt('v96SelectedSlotLabel',v96SelectedGaugeSlot<6?('Print tile '+(v96SelectedGaugeSlot+1)):('Ready tile '+(v96SelectedGaugeSlot-5)))}
function v96SelectGaugeSlot(slot){v96SelectedGaugeSlot=slot;v96RenderDisplayPreview()}
function v96AssignWidget(id){var target=v96SelectedGaugeSlot<6?v96ById('gs'+v96SelectedGaugeSlot):v96ById('is'+(v96SelectedGaugeSlot-6));if(!target)return;target.value=String(id);target.dispatchEvent(new Event('change',{bubbles:true}));v96RenderDisplayPreview();v96SetDirty(true)}
function v96BuildWidgetLibrary(){var host=v96ById('v96WidgetList');if(!host||!window.gaugeTypes)return;var q=(v96ById('v96WidgetSearch')?v96ById('v96WidgetSearch').value:'').trim().toLowerCase();var group=v96ById('v96WidgetGroup')?v96ById('v96WidgetGroup').value:'';var groups={},html='';gaugeTypes.forEach(function(g,i){if(i===0)return;if(typeof gaugeAllowed==='function'&&!gaugeAllowed(i))return;groups[g.group||'Other']=true;if(q&&(g.name+' '+(g.group||'')).toLowerCase().indexOf(q)<0)return;if(group&&(g.group||'Other')!==group)return;html+='<button type="button" class="v96-widget" onclick="v96AssignWidget('+i+')"><strong>'+v96Esc(g.name)+'</strong><span>'+v96Esc(g.group||'Other')+'</span></button>'});host.innerHTML=html||'<div class="text-dim">No matching widgets.</div>';var sel=v96ById('v96WidgetGroup');if(sel&&sel.options.length<=1){Object.keys(groups).sort().forEach(function(g){var o=document.createElement('option');o.value=g;o.textContent=g;sel.appendChild(o)})}}
function v96ApplyPreset(name){if(typeof applyGaugeProfile==='function')applyGaugeProfile(name);setTimeout(function(){v96RenderDisplayPreview();v96SetDirty(false)},220)}
function v96RuleChange(srcId,backendId){var src=v96ById(srcId),back=v96ById(backendId);if(src&&back){back.checked=src.checked;v96SetDirty(true)}}
function v96DelayChange(){var src=v96ById('v96LightDelay'),back=v96ById('ldelay');if(src&&back){back.value=src.value;v96SetDirty(true)}}
function v96SyncAutomationUi(){[['v96RuleStart','lon_start'],['v96RuleSuccess','loff_fin'],['v96RuleFail','loff_fail']].forEach(function(p){var a=v96ById(p[0]),b=v96ById(p[1]);if(a&&b)a.checked=!!b.checked});var d=v96ById('ldelay'),out=v96ById('v96LightDelay');if(d&&out)out.value=d.value;var ls=v96ById('lightStateLbl');v96Txt('v96LightState',ls?ls.textContent.replace('Light:','').trim():'—')}
function v96RefreshPrinterWorkspace(){if(!v96ById('v96PrinterWorkspace'))return;var slot=Number(window.currentSlot||0);Promise.all([fetch('/status?slot='+slot+'&_='+Date.now(),{cache:'no-store'}).then(function(r){return r.json()}),fetch('/printer/config?slot='+slot+'&_='+Date.now(),{cache:'no-store'}).then(function(r){return r.json()}).catch(function(){return {}})]).then(function(res){var d=res[0]||{},c=res[1]||{},name=d.name||c.name||('Printer '+(slot+1)),connected=!!d.connected,configured=!!d.configured;v96Txt('v96PrinterName',name);v96Txt('v96PrinterMeta',(c.mode||'LAN')+' · '+(c.ip||d.ip||'No address'));var state=v96ById('v96PrinterState');if(state){state.textContent=connected?(d.state||'CONNECTED'):(configured?'OFFLINE':'SETUP');state.classList.toggle('ok',connected);state.classList.toggle('bad',configured&&!connected)}v96Txt('v96Progress',(Number(d.progress||0))+'%');v96Txt('v96Nozzle',d.nozzle==null?'—':Math.round(Number(d.nozzle))+'°');v96Txt('v96Bed',d.bed==null?'—':Math.round(Number(d.bed))+'°');v96Txt('v96Layer',(Number(d.layer||0))+' / '+(Number(d.layers||0)));v96Txt('v96Wifi',typeof d.rssi==='number'?d.rssi+' dBm':'—');var health=v96ById('v96Health');if(health)health.classList.toggle('ok',connected);if(connected){v96Txt('v96HealthTitle','Everything important is online');v96Txt('v96HealthText','Printer telemetry is live. Connection and touchscreen configuration are ready.');var hb=v96ById('v96HealthButton');if(hb){hb.textContent='Verify again';hb.onclick=function(){if(typeof verifyPrinterSetup==='function')verifyPrinterSetup()}}}else if(configured){v96Txt('v96HealthTitle','Printer connection needs attention');v96Txt('v96HealthText',(c.mode==='cloud'?'Cloud connection is not responding.':'LAN printer is not responding. Check power, address, access code, or the Bambu LAN client limit.'));var hb2=v96ById('v96HealthButton');if(hb2){hb2.textContent='Troubleshoot';hb2.onclick=function(){v96OpenPrinterTab('connection')}}}else{v96Txt('v96HealthTitle','Finish printer setup');v96Txt('v96HealthText','Choose LAN or Cloud, identify the printer, then Save & Verify.');var hb3=v96ById('v96HealthButton');if(hb3){hb3.textContent='Configure printer';hb3.onclick=function(){v96OpenPrinterTab('connection')}}}v96SyncAutomationUi()}).catch(function(){v96Txt('v96HealthTitle','Device reachable, printer status unavailable');v96Txt('v96HealthText','Use Verify Connection or Diagnostics for the current slot.')})}
function v96InitPrinterWorkspace(){var sec=v96ById('sec-printer');if(!sec||v96ById('v96PrinterWorkspace'))return;sec.classList.add('v96-printer-evolved');var legacy=document.createElement('div');legacy.id='v96LegacyPrinter';legacy.className='v96-advanced-legacy';while(sec.firstChild)legacy.appendChild(sec.firstChild);var shell=document.createElement('div');shell.id='v96PrinterWorkspace';shell.className='v96-printer-shell';shell.innerHTML='<div class="v96-printer-hero"><div><span class="v96-eyebrow">PRINTER WORKSPACE</span><div class="v96-hero-title"><h2 id="v96PrinterName">Selected printer</h2><span class="v96-state" id="v96PrinterState">CHECKING</span></div><div class="v96-hero-sub" id="v96PrinterMeta">Loading connection details…</div><div class="v96-hero-actions"><button type="button" class="btn btn-primary" onclick="v96OpenPrinterTab(\'connection\')">Configure</button><button type="button" class="btn btn-ghost" onclick="if(typeof verifyPrinterSetup===\'function\')verifyPrinterSetup()">Test connection</button><button type="button" class="btn btn-ghost" onclick="v96OpenPrinterTab(\'display\')">Customize display</button></div></div>'+v96PrinterArt()+'</div><div class="v96-tabs" role="tablist"><button class="v96-tab active" data-tab="overview" onclick="v96OpenPrinterTab(\'overview\')">Overview</button><button class="v96-tab" data-tab="connection" onclick="v96OpenPrinterTab(\'connection\')">Connection</button><button class="v96-tab" data-tab="display" onclick="v96OpenPrinterTab(\'display\')">Display</button><button class="v96-tab" data-tab="automation" onclick="v96OpenPrinterTab(\'automation\')">Automation</button><button class="v96-tab" data-tab="advanced" onclick="v96OpenPrinterTab(\'advanced\')">Advanced</button></div><div class="v96-panel active" data-panel="overview"><div class="v96-panel-stack"><div class="v96-health" id="v96Health"><div><strong id="v96HealthTitle">Checking printer…</strong><span id="v96HealthText">Reading current health and telemetry.</span></div><button type="button" class="btn btn-ghost btn-sm" id="v96HealthButton">Refresh</button></div><div class="v96-live-grid"><div class="v96-live-card"><span>PROGRESS</span><strong id="v96Progress">—</strong><small>Current job</small></div><div class="v96-live-card"><span>NOZZLE</span><strong id="v96Nozzle">—</strong><small>Live temperature</small></div><div class="v96-live-card"><span>BED</span><strong id="v96Bed">—</strong><small>Live temperature</small></div><div class="v96-live-card"><span>LAYER</span><strong id="v96Layer">—</strong><small>Current / total</small></div><div class="v96-live-card"><span>WI-FI</span><strong id="v96Wifi">—</strong><small>Device signal</small></div></div><div id="v96OverviewCards"></div></div></div><div class="v96-panel" data-panel="connection"><div class="v96-panel-stack"><div class="v96-panel-note"><strong>Connection</strong> contains only printer identity and transport settings. Use <b>Save & Verify</b> when these values change.</div><div id="v96ConnectionCards"></div></div></div><div class="v96-panel" data-panel="display"><div class="v96-panel-stack"><div class="v96-preview-shell"><div class="v96-preview-card"><div class="v96-preview-title"><div><span class="v96-eyebrow">TOUCHSCREEN PREVIEW</span><h3>Print dashboard</h3></div><span class="text-dim" id="v96SelectedSlotLabel">Print tile 1</span></div><div class="v96-screen"><div class="v96-screen-top"><span>PRINTING</span><strong>64%</strong></div><div class="v96-screen-grid" id="v96ScreenGrid"></div><div class="v96-ready-preview" id="v96ReadyGrid"></div></div><div class="v96-preset-row"><button type="button" class="v96-preset" onclick="v96ApplyPreset(\'remote\')">Remote status</button><button type="button" class="v96-preset" onclick="v96ApplyPreset(\'thermal\')">Thermal & fans</button><button type="button" class="v96-preset" onclick="v96ApplyPreset(\'ams\')">AMS overview</button><button type="button" class="v96-preset" onclick="v96ApplyPreset(\'x2d\')">X2D</button></div></div><div class="v96-library"><span class="v96-eyebrow">WIDGET LIBRARY</span><h3 style="margin:5px 0 0">Choose what the Waveshare shows</h3><p class="text-dim" style="font-size:11px">Select a preview tile, then choose a widget. This writes the same gauge slots used by the physical touchscreen.</p><div class="v96-library-tools"><input id="v96WidgetSearch" placeholder="Search widgets" oninput="v96BuildWidgetLibrary()"><select id="v96WidgetGroup" onchange="v96BuildWidgetLibrary()"><option value="">All categories</option></select></div><div class="v96-widget-list" id="v96WidgetList"></div></div></div><div id="v96DisplayCards"></div></div></div><div class="v96-panel" data-panel="automation"><div class="v96-panel-stack"><div class="v96-rule-card"><div class="v96-rule-head"><div><span class="v96-eyebrow">CHAMBER LIGHT</span><h3>Automation rules</h3></div><div class="v96-light-now"><span class="text-dim">Current</span><strong id="v96LightState">—</strong><button type="button" class="btn btn-ghost btn-sm" onclick="setLight(\'on\')">On</button><button type="button" class="btn btn-ghost btn-sm" onclick="setLight(\'off\')">Off</button></div></div><label class="v96-rule"><input type="checkbox" id="v96RuleStart" onchange="v96RuleChange(\'v96RuleStart\',\'lon_start\')"><span><strong>Print starts</strong><span>Illuminate the chamber when a job begins.</span></span><span class="v96-rule-action">TURN ON</span></label><label class="v96-rule"><input type="checkbox" id="v96RuleSuccess" onchange="v96RuleChange(\'v96RuleSuccess\',\'loff_fin\')"><span><strong>Print completes successfully</strong><span>Turn the chamber light off after the configured delay.</span></span><span class="v96-rule-action">TURN OFF</span></label><label class="v96-rule"><input type="checkbox" id="v96RuleFail" onchange="v96RuleChange(\'v96RuleFail\',\'loff_fail\')"><span><strong>Print fails or is cancelled</strong><span>Turn the chamber light off after the configured delay.</span></span><span class="v96-rule-action">TURN OFF</span></label><div class="v96-rule"><span></span><span><strong>Off delay</strong><span>0 minutes means immediately.</span></span><input class="v96-delay" type="number" min="0" max="1440" id="v96LightDelay" onchange="v96DelayChange()"></div></div><div id="v96AutomationCards"></div></div></div><div class="v96-panel" data-panel="advanced"><div class="v96-panel-stack"><div class="v96-panel-note v96-advanced-copy"><strong>Advanced printer configuration</strong> keeps the original detailed setup flow and any controls that do not belong in the everyday workspace.</div><div id="v96AdvancedCards"></div></div></div><div class="v96-sticky-save" id="v96StickySave"><div><strong>Unsaved changes</strong><span id="v96SaveContext">Printer settings</span></div><div class="v96-save-actions"><button type="button" class="btn btn-ghost btn-sm" onclick="v96DiscardChanges()">Discard</button><button type="button" class="btn btn-primary btn-sm" onclick="v96SaveChanges()">Save changes</button></div></div>';sec.appendChild(shell);var panels={overview:v96ById('v96OverviewCards'),connection:v96ById('v96ConnectionCards'),display:v96ById('v96DisplayCards'),automation:v96ById('v96AutomationCards'),advanced:v96ById('v96AdvancedCards')};panels.advanced.appendChild(legacy);[['Setup health','overview'],['Active slot','connection'],['Connection','connection'],['Remote monitor profile','display'],['Gauge Layout','display'],['Chamber light','automation']].forEach(function(pair){var c=v96FindCard(legacy,pair[0]);if(c){panels[pair[1]].appendChild(c);if(pair[0]==='Chamber light')c.classList.add('v96-backend-light')}});var remembered='overview';try{remembered=localStorage.getItem('waveshare_printer_tab')||'overview'}catch(e){}if(['overview','connection','display','automation','advanced'].indexOf(remembered)<0)remembered='overview';v96OpenPrinterTab(remembered);sec.addEventListener('change',function(e){if(e.target&&e.target.matches('input,select,textarea'))v96SetDirty(true)},true);sec.addEventListener('input',function(e){if(e.target&&e.target.matches('input[type=text],input[type=number],input[type=password]'))v96SetDirty(true)},true);sec.addEventListener('click',function(e){var b=e.target.closest&&e.target.closest('button');if(b&&/save|verify/i.test(b.textContent||''))setTimeout(function(){v96SetDirty(false)},700)},true);v96ById('v96HealthButton').onclick=v96RefreshPrinterWorkspace;v96RefreshPrinterWorkspace();v96RenderDisplayPreview();v96BuildWidgetLibrary();v96SyncAutomationUi();if(v96PrinterTimer)clearInterval(v96PrinterTimer);v96PrinterTimer=setInterval(function(){var p=v96ById('sec-printer');if(p&&p.style.display!=='none')v96RefreshPrinterWorkspace()},3500)}
setTimeout(v96InitPrinterWorkspace,0);
setTimeout(v96InitPrinterWorkspace,500);


/* Smart Home v9.7 Interaction & Layout */
function v97FamilyFromName(name){name=String(name||'').toUpperCase();if(name.indexOf('H2')>=0||name.indexOf('X2')>=0)return 'h2';if(name.indexOf('A1 MINI')>=0)return 'a1mini';if(name.indexOf('A1')>=0)return 'a1';if(name.indexOf('P1')>=0)return 'p1';if(name.indexOf('X1')>=0)return 'x1';return 'generic'}
function v97ApplyPrinterFamily(){var art=v96ById('v97PrinterArt')||document.querySelector('.v96-printer-art');if(!art)return;var n=(v96ById('v96PrinterName')||{}).textContent||'';art.className='v96-printer-art v97-family-'+v97FamilyFromName(n)}
v96PrinterArt=function(){return '<div class="v96-printer-art v97-family-generic" id="v97PrinterArt" aria-hidden="true"><div class="v96-ams"><i class="v96-spool"></i><i class="v96-spool"></i><i class="v96-spool"></i><i class="v96-spool"></i></div><div class="v96-machine"><i class="v96-bed"></i><i class="v96-part"></i><i class="v97-tool-left"></i><i class="v97-tool-right"></i></div></div>'}
var v97BaseRefresh=v96RefreshPrinterWorkspace;v96RefreshPrinterWorkspace=function(){var r=v97BaseRefresh.apply(this,arguments);setTimeout(v97ApplyPrinterFamily,180);return r}
function v97UpgradePrinterWorkspace(){var root=v96ById('v96PrinterWorkspace');if(!root)return;var legacy=v96ById('v96LegacyPrinter');if(legacy){var health=v96FindCard(root,'Setup health');if(health)health.style.display='none';var display=v96ById('v96DisplayCards');if(display&&!v96ById('v97LegacyDisplay')){var details=document.createElement('details');details.id='v97LegacyDisplay';details.className='v97-legacy-display';details.innerHTML='<summary>Advanced display configuration</summary><p class="text-dim">Original BambuHelper profile and slot controls. The visual preview and Widget Library above are the primary experience.</p>';var profile=v96FindCard(root,'Remote monitor profile'),gauges=v96FindCard(root,'Gauge Layout');if(profile)details.appendChild(profile);if(gauges)details.appendChild(gauges);display.appendChild(details)}}v97ApplyPrinterFamily()}
setTimeout(v97UpgradePrinterWorkspace,650);setTimeout(v97UpgradePrinterWorkspace,1400);


/* Smart Home v9.8 unified physical display preview */
var v98PreviewPage='home',v98PreviewOrientation='portrait',v98PreviewData={status:{},config:{},recovery:{}};
function v98FamilyFromName(name){name=String(name||'').toUpperCase();if(name.indexOf('X2')>=0)return 'x2';if(name.indexOf('H2')>=0)return 'h2';if(name.indexOf('A1 MINI')>=0)return 'a1mini';if(name.indexOf('A1')>=0)return 'a1';if(name.indexOf('P1')>=0)return 'p1';if(name.indexOf('X1')>=0)return 'x1';return 'generic'}
v97FamilyFromName=v98FamilyFromName;
function v98SetPreviewPage(page){v98PreviewPage=page;v98RenderDevicePreview()}
function v98SetPreviewOrientation(o){v98PreviewOrientation=o;v98RenderDevicePreview()}
function v98Metric(label,value,cls){return '<div class="v98-metric '+(cls||'')+'"><span>'+v96Esc(label)+'</span><strong>'+v96Esc(value==null?'—':value)+'</strong></div>'}
function v98Nav(){return '<div class="v98-nav">'+['home','printer','workshop','more'].map(function(p){return '<button class="'+(v98PreviewPage===p?'active':'')+'" onclick="v98SetPreviewPage(\''+p+'\')">'+p.toUpperCase()+'</button>'}).join('')+'</div>'}
function v98PrinterGlyph(name){return '<div class="v98-machine v98-family-'+v98FamilyFromName(name)+'"><i class="v98-ams"></i><i class="v98-frame"></i><i class="v98-bed"></i><i class="v98-part"></i><i class="v98-tool a"></i><i class="v98-tool b"></i></div>'}
function v98ScreenBody(){var d=v98PreviewData.status||{},r=v98PreviewData.recovery||{},name=d.name||'Bambu Printer',state=d.connected?(d.state||'ONLINE'):'OFFLINE',progress=Number(d.progress||0),noz=d.nozzle==null?'—':Math.round(Number(d.nozzle))+'°',bed=d.bed==null?'—':Math.round(Number(d.bed))+'°',ch=d.chamber==null?'—':Math.round(Number(d.chamber))+'°',fan=d.fan==null?'—':Math.round(Number(d.fan))+'%',layer=(Number(d.layer||0))+'/'+(Number(d.layers||0)),wifi=typeof d.rssi==='number'?d.rssi+' dBm':'—';
  var head='<div class="v98-head"><b>B</b><strong>'+v96Esc(v98PreviewPage.toUpperCase())+'</strong><span>'+v96Esc(state)+'</span></div>',body='';
  if(v98PreviewPage==='home'||v98PreviewPage==='printer'){body='<div class="v98-hero"><div><strong class="v98-printer-name">'+v96Esc(name)+'</strong><span>'+v96Esc(d.job||'Live printer status')+'</span>'+v98PrinterGlyph(name)+'</div><div class="v98-ring"><b>'+progress+'%</b><span>'+layer+'</span></div></div><div class="v98-telemetry">'+v98Metric('NOZZLE',noz,'orange')+v98Metric('BED',bed,'amber')+v98Metric('CHAMBER',ch,'blue')+v98Metric('FAN',fan,'cyan')+'</div><div class="v98-amsdeck"><span>AMS / FILAMENT</span><div><i></i><i></i><i></i><i></i></div></div>'+(v98PreviewPage==='printer'?'<div class="v98-actions"><button>LIGHT</button><button>MATERIALS</button></div>':'<div class="v98-strip">'+v96Esc(wifi)+' • '+v96Esc(state)+'</div>');}
  else if(v98PreviewPage==='workshop'){body='<div class="v98-summary">'+v98Metric('PRINT',progress+'%','orange')+v98Metric('ENVIRONMENT',ch,'blue')+'</div><div class="v98-amsdeck"><span>AMS / FILAMENT</span><div><i></i><i></i><i></i><i></i></div></div><div class="v98-actions four"><button>LIGHT</button><button>CUSTOM</button><button>SYSTEM</button><button>PRINTER</button></div>';}
  else if(v98PreviewPage==='more'){body='<div class="v98-moregrid">'+['CUSTOM','SYSTEM','EDIT WIDGETS','TOOLS'].map(function(x){return '<div><b>'+x+'</b><span>OPEN ›</span></div>'}).join('')+'</div><div class="v98-device"><span>DEVICE</span><strong>'+v96Esc(r.build||'Smart Home')+'</strong><small>'+v96Esc(r.webReady?'Recovery ready':'Recovery status')+'</small></div>';}
  else if(v98PreviewPage==='custom'){body='<div class="v98-custom-title"><b>MY WIDGETS</b><span>Fallback dashboard</span></div><div class="v98-widgetgrid">'+v98Metric('PROGRESS',progress+'%','orange')+v98Metric('NOZZLE',noz,'cyan')+v98Metric('BED',bed,'amber')+v98Metric('WI-FI',wifi,'green')+'</div>';}
  else {body='<div class="v98-systemgrid">'+v98Metric('NETWORK',wifi,d.connected?'green':'amber')+v98Metric('DEVICE','WS350','cyan')+v98Metric('RECOVERY',r.runningSlot||'app?','purple')+v98Metric('DEVICE HEALTH',r.touchResponsive===false?'CHECK':'HEALTHY',r.touchResponsive===false?'amber':'green')+'</div>';}
  return head+'<div class="v98-content">'+body+'</div>'+v98Nav();}
function v98RenderDevicePreview(){var host=v96ById('v98DeviceCanvas');if(!host)return;host.className='v98-device-canvas '+v98PreviewOrientation+' page-'+v98PreviewPage;host.innerHTML=v98ScreenBody();document.querySelectorAll('.v98-page-btn').forEach(function(b){b.classList.toggle('active',b.getAttribute('data-page')===v98PreviewPage)});document.querySelectorAll('.v98-orient-btn').forEach(function(b){b.classList.toggle('active',b.getAttribute('data-orient')===v98PreviewOrientation)})}
function v98RefreshPreviewData(){if(!v96ById('v98DeviceCanvas'))return;var slot=Number(window.currentSlot||0);Promise.all([fetch('/status?slot='+slot+'&_='+Date.now(),{cache:'no-store'}).then(function(x){return x.json()}).catch(function(){return {}}),fetch('/printer/config?slot='+slot+'&_='+Date.now(),{cache:'no-store'}).then(function(x){return x.json()}).catch(function(){return {}}),fetch('/recovery/status?_='+Date.now(),{cache:'no-store'}).then(function(x){return x.json()}).catch(function(){return {}})]).then(function(a){v98PreviewData={status:a[0]||{},config:a[1]||{},recovery:a[2]||{}};var bp=v96ById('smartHomeBuildPill');if(bp&&v98PreviewData.recovery.build)bp.textContent=v98PreviewData.recovery.build;v98RenderDevicePreview()})}
function v98UpgradeDisplayPreview(){var card=document.querySelector('.v96-preview-card');if(!card||v96ById('v98DeviceCanvas'))return;card.innerHTML='<div class="v96-preview-title"><div><span class="v96-eyebrow">PHYSICAL TOUCHSCREEN PREVIEW</span><h3>Smart Home display</h3></div><span class="text-dim">320×480 / 480×320</span></div><div class="v98-preview-toolbar"><div>'+['home','printer','workshop','more','custom','system'].map(function(p){return '<button type="button" class="v98-page-btn '+(p===v98PreviewPage?'active':'')+'" data-page="'+p+'" onclick="v98SetPreviewPage(\''+p+'\')">'+p[0].toUpperCase()+p.slice(1)+'</button>'}).join('')+'</div><div><button type="button" class="v98-orient-btn active" data-orient="portrait" onclick="v98SetPreviewOrientation(\'portrait\')">Portrait</button><button type="button" class="v98-orient-btn" data-orient="landscape" onclick="v98SetPreviewOrientation(\'landscape\')">Landscape</button></div></div><div class="v98-device-wrap"><div id="v98DeviceCanvas" class="v98-device-canvas portrait"></div></div><p class="text-dim v98-preview-note">This mirrors the physical Smart Home hierarchy and live telemetry. Original gauge-slot controls remain under Advanced display configuration.</p>';var lib=document.querySelector('.v96-library'),advanced=v96ById('v97LegacyDisplay');if(lib&&advanced){lib.querySelector('h3')&&(lib.querySelector('h3').textContent='Legacy gauge widget library');advanced.appendChild(lib)}var shell=document.querySelector('.v96-preview-shell');if(shell)shell.classList.add('v98-preview-shell');v98RefreshPreviewData();if(window.v98PreviewTimer)clearInterval(window.v98PreviewTimer);window.v98PreviewTimer=setInterval(function(){if(v96PrinterTab==='display')v98RefreshPreviewData()},4000)}
var v98BaseOpen=v96OpenPrinterTab;v96OpenPrinterTab=function(name){var r=v98BaseOpen.apply(this,arguments);if(name==='display')setTimeout(function(){v98UpgradeDisplayPreview();v98RefreshPreviewData()},30);return r};
function v98RefreshBuildIdentity(){fetch('/recovery/status?_='+Date.now(),{cache:'no-store'}).then(function(x){return x.json()}).then(function(r){var bp=v96ById('smartHomeBuildPill');if(bp&&r.build)bp.textContent=r.build}).catch(function(){})}
setTimeout(v98RefreshBuildIdentity,250);setTimeout(v98UpgradeDisplayPreview,900);setTimeout(v98UpgradeDisplayPreview,1700);

/* Smart Home v9.9 Display Experience — physical/browser parity polish. */
function v99StateTone(state){state=String(state||'').toUpperCase();if(state.indexOf('OFF')>=0||state.indexOf('FAIL')>=0)return 'red';if(state.indexOf('PAUSE')>=0||state.indexOf('ATT')>=0)return 'amber';if(state.indexOf('PRINT')>=0||state.indexOf('RUN')>=0)return 'orange';return 'green'}
function v99MaterialSlot(i,d){var names=(d&&d.amsTypes)||[],rem=(d&&d.amsRemain)||[],active=Number((d&&d.activeTray)==null?-1:d.activeTray),label=names[i]||('A'+(i+1)),pct=rem[i];return '<div class="v99-mat '+(active===i?'active':'')+'"><i style="--mat:'+(i===0?'#ff6b23':i===1?'#26c6da':i===2?'#ffc342':'#b06bff')+'"></i><b>'+v96Esc(label)+'</b><span>'+(pct==null?'—':v96Esc(String(pct)+'%'))+'</span></div>'}
function v99Materials(d){return '<div class="v99-materials"><div class="v99-section"><b>MATERIALS</b><span>AMS / spool state</span></div><div class="v99-mat-grid">'+[0,1,2,3].map(function(i){return v99MaterialSlot(i,d)}).join('')+'</div></div>'}
function v99StatusStrip(d,state){var alerts=Number(d.hmsCount||d.alerts||0),rssi=typeof d.rssi==='number'?d.rssi+' dBm':'—',text,cls;if(!d.connected){text='OFFLINE • check printer LAN / MQTT connection';cls='red'}else if(alerts){text='ATTENTION • '+alerts+' printer alert'+(alerts===1?'':'s')+' • WiFi '+rssi;cls='amber'}else{text='ALL CLEAR • WiFi '+rssi+' • '+v96Esc(d.speed||'STANDARD');cls='green'}return '<div class="v99-status '+cls+'"><i></i><span>'+text+'</span></div>'}
function v99Header(page,state){var now=new Date(),clock=now.toLocaleTimeString([],{hour:'numeric',minute:'2-digit'}),tone=v99StateTone(state);return '<div class="v99-head tone-'+tone+'"><b>B</b><strong>'+v96Esc(page.toUpperCase())+'</strong><span><i></i>'+v96Esc(state)+'</span><small>'+v96Esc(clock)+'</small></div>'}
function v99Hero(d,name,state,progress,layer,printerPage){var printing=/PRINT|RUN/i.test(state)||progress>0,ready=d.connected&&!printing,tone=v99StateTone(state),eyebrow=!d.connected?'PRINTER OFFLINE':printing?'NOW PRINTING':'READY TO PRINT';return '<div class="v99-hero tone-'+tone+'"><div class="v99-hero-copy"><em>'+eyebrow+'</em><strong>'+v96Esc(name)+'</strong><span>'+v96Esc(printing?(d.job||'Active print'):(d.connected?'Workshop is ready':'Waiting for printer connection'))+'</span>'+v98PrinterGlyph(name)+'</div><div class="v99-hero-focus '+(printing?'printing':'ready')+'">'+(printing?'<div class="v99-ring"><b>'+progress+'%</b><span>'+v96Esc(layer)+'</span></div><small>'+v96Esc(d.eta||'—')+'</small>':'<b>'+(ready?'READY':'OFFLINE')+'</b><small>'+(ready?'Tap Printer for details':'Check connection')+'</small>')+'</div>'+(printing?'<div class="v99-progress"><i style="width:'+Math.max(0,Math.min(100,progress))+'%"></i></div>':'')+'</div>'}
function v99Telemetry(d){var connected=!!d.connected,noz=connected&&d.nozzle!=null?Math.round(Number(d.nozzle))+'°':'—',bed=connected&&d.bed!=null?Math.round(Number(d.bed))+'°':'—',ch=connected&&d.chamber!=null?Math.round(Number(d.chamber))+'°':'—',fan=connected&&d.fan!=null?Math.round(Number(d.fan))+'%':'—';return '<div class="v99-telemetry">'+v98Metric('NOZZLE',noz,'orange')+v98Metric('BED',bed,'amber')+v98Metric('CHAMBER',ch,'blue')+v98Metric('FAN',fan,'cyan')+'</div>'}
function v99More(){var items=[['CUSTOM','Personal dashboard','purple'],['SYSTEM','Health & recovery','blue'],['EDIT WIDGETS','Choose dashboard tiles','orange'],['TOOLS','Timers, notes & legacy','orange']];return '<div class="v99-moregrid">'+items.map(function(x,i){return '<div class="'+x[2]+'"><i class="ico i'+i+'"></i><b>'+x[0]+'</b><span>'+x[1]+'</span><small>OPEN ›</small></div>'}).join('')+'</div>'}
function v99System(d,r){var net=!!d.connected,touch=r.touchResponsive!==false,rec=!!r.webReady,healthy=net&&touch&&rec;return '<div class="v99-health '+(healthy?'green':'amber')+'"><em>'+(healthy?'ALL SYSTEMS NORMAL':'DEVICE NEEDS ATTENTION')+'</em><b>'+(healthy?'Healthy':'Check status')+'</b><div><span class="'+(net?'ok':'bad')+'">Network</span><span class="'+(touch?'ok':'bad')+'">Touch</span><span class="'+(rec?'ok':'bad')+'">Recovery</span></div></div><div class="v99-systemgrid">'+v98Metric('NETWORK',net?((typeof d.rssi==='number'?d.rssi+' dBm':'Connected')):'Offline',net?'green':'amber')+v98Metric('TOUCH',touch?'Responsive':'Attention',touch?'cyan':'amber')+v98Metric('FIRMWARE',r.runningSlot||'app?','purple')+v98Metric('FALLBACK',r.knownGood||'—','green')+'</div>'}
function v99ScreenBody(){var d=v98PreviewData.status||{},r=v98PreviewData.recovery||{},name=d.name||'Bambu Printer',state=d.connected?(d.state||((Number(d.progress||0)>0)?'PRINTING':'ONLINE')):'OFFLINE',progress=Number(d.progress||0),layer=(Number(d.layer||0))+'/'+(Number(d.layers||0)),body='';
  if(v98PreviewPage==='home'||v98PreviewPage==='printer'){body=v99Hero(d,name,state,progress,layer,v98PreviewPage==='printer')+v99Telemetry(d)+v99Materials(d)+(v98PreviewPage==='printer'?'<div class="v99-actions"><button>LIGHT</button><button>MATERIALS</button></div>':v99StatusStrip(d,state));}
  else if(v98PreviewPage==='workshop'){body='<div class="v99-work-top">'+v98Metric('JOB',progress>0?progress+'%':'READY','orange')+v98Metric('ENVIRONMENT',d.chamber==null?'—':Math.round(Number(d.chamber))+'°','blue')+'</div>'+v99Materials(d)+'<div class="v99-actions four"><button>LIGHT</button><button>DASHBOARD</button><button>SYSTEM</button><button>PRINTER</button></div>';}
  else if(v98PreviewPage==='more'){body=v99More()+'<div class="v99-device"><em>THIS DEVICE</em><b>'+v96Esc(r.build||'Smart Home')+'</b><span>'+(r.webReady?'Recovery ready':'Recovery starting')+' • '+v96Esc(r.runningSlot||'app?')+'</span></div>';}
  else if(v98PreviewPage==='custom'){body='<div class="v99-custom"><em>MY WIDGETS</em><b>Local dashboard</b><span>Stored on this device</span></div><div class="v99-widgetgrid">'+v98Metric('PROGRESS',progress+'%','orange')+v98Metric('NOZZLE',d.nozzle==null?'—':Math.round(Number(d.nozzle))+'°','cyan')+v98Metric('BED',d.bed==null?'—':Math.round(Number(d.bed))+'°','amber')+v98Metric('WI-FI',typeof d.rssi==='number'?d.rssi+' dBm':'—','green')+'</div>';}
  else body=v99System(d,r);
  return v99Header(v98PreviewPage,state)+'<div class="v99-content">'+body+'</div>'+v98Nav();
}
v98ScreenBody=v99ScreenBody;
setTimeout(function(){v98RenderDevicePreview()},80);

/* Smart Home v10.4 Portal UX */
var v104PortalTimer=null;
var v104PrinterHooked=false;
function v104El(id){return document.getElementById(id)}
function v104NavTo(section){if(typeof loadSection==='function')loadSection(section);else location.hash='#'+section}
function v104EnsureTopHealth(){
  var actions=document.querySelector('.topbar-actions');if(!actions||v104El('v104TopHealth'))return;
  document.querySelectorAll('.topbar-actions .status-dot').forEach(function(x){x.classList.add('v104-legacy-status')});
  var wrap=document.createElement('div');wrap.id='v104TopHealth';wrap.className='v104-top-health';
  wrap.innerHTML='<span class="v104-health-pill ok" id="v104DeviceHealth"><i></i><span>Device</span><strong>Online</strong></span><span class="v104-health-pill" id="v104PrinterHealth"><i></i><span>Printer</span><strong>Checking</strong></span>';
  var theme=v104El('themeToggle');actions.insertBefore(wrap,theme||null);
}
function v104RefreshTopHealth(){
  v104EnsureTopHealth();var slot=Number(window.currentSlot||0),p=v104El('v104PrinterHealth'),d=v104El('v104DeviceHealth');if(!p||!d)return;
  fetch('/status?slot='+slot+'&_='+Date.now(),{cache:'no-store'}).then(function(r){if(!r.ok)throw new Error('status');return r.json()}).then(function(s){
    d.className='v104-health-pill ok';d.querySelector('strong').textContent='Online';
    p.querySelector('span').textContent='Printer '+(slot+1);
    var connected=!!s.connected,configured=!!s.configured;
    p.className='v104-health-pill '+(connected?'ok':(configured?'warn':''));
    p.querySelector('strong').textContent=connected?(s.state||'Connected'):(configured?'Offline':'Not set up');
  }).catch(function(){d.className='v104-health-pill warn';d.querySelector('strong').textContent='Check';p.className='v104-health-pill';p.querySelector('strong').textContent='Unavailable'});
}
function v104BuildSlotSwitcher(){
  var root=v104El('v96PrinterWorkspace'),hero=root&&root.querySelector('.v96-printer-hero');if(!root||!hero||v104El('v104SlotSwitcher'))return;
  var old=v104El('printerTabs');if(!old)return;
  var bar=document.createElement('div');bar.id='v104SlotSwitcher';bar.className='v104-slot-switcher';bar.innerHTML='<span class="v104-slot-label">ACTIVE PRINTER</span><div class="v104-slot-buttons"></div><span class="v104-slot-summary" id="v104SlotSummary">Selected slot</span>';
  var dest=bar.querySelector('.v104-slot-buttons');
  old.querySelectorAll('.tab-btn').forEach(function(btn,i){
    if(btn.style&&btn.style.display==='none')return;
    var b=document.createElement('button');b.type='button';b.className='v104-slot-btn';b.dataset.slot=String(i);b.textContent='Printer '+(i+1);b.onclick=function(){if(typeof selectPrinterTab==='function'){selectPrinterTab(i);setTimeout(function(){v104SyncPrinterUX();v104RefreshTopHealth()},300)}};dest.appendChild(b);
  });
  hero.insertAdjacentElement('afterend',bar);
  var oldCard=old.closest('.card');if(oldCard)oldCard.classList.add('v104-backend-slot');
}
function v104BuildSupportPanel(){
  var panel=document.querySelector('.v96-panel[data-panel="advanced"] .v96-panel-stack');if(!panel||v104El('v104SupportCard'))return;
  var note=panel.querySelector('.v96-panel-note');if(note){note.innerHTML='<strong>Support &amp; advanced</strong> keeps troubleshooting and uncommon printer controls out of the everyday workflow.'}
  var card=document.createElement('div');card.id='v104SupportCard';card.className='v104-support-card';
  card.innerHTML='<div class="v104-support-copy"><span class="v96-eyebrow">SUPPORT</span><h3>Printer support tools</h3><p>Verify the selected printer, export a credential-redacted report, or open device diagnostics.</p></div><div class="v104-support-actions"><button type="button" class="btn btn-primary" onclick="if(typeof verifyPrinterSetup===\'function\')verifyPrinterSetup()">Verify connection</button><button type="button" class="btn btn-ghost" onclick="if(typeof exportSupportReport===\'function\')exportSupportReport()">Export support report</button><button type="button" class="btn btn-ghost" onclick="v104NavTo(\'diag\')">Diagnostics</button><button type="button" class="btn btn-ghost" id="v104ErrorsBtn" onclick="v104NavTo(\'errors\')">Printer errors</button><button type="button" class="btn btn-danger" onclick="if(typeof clearPrinter===\'function\')clearPrinter()">Clear selected printer</button></div>';
  if(!v104El('sec-errors'))card.querySelector('#v104ErrorsBtn').style.display='none';
  panel.insertBefore(card,note?note.nextSibling:panel.firstChild);
  var legacy=v104El('v96LegacyPrinter');if(legacy&&!v104El('v104LegacyDetails')){
    var details=document.createElement('details');details.id='v104LegacyDetails';details.className='v104-legacy-details';details.innerHTML='<summary>Legacy / expert printer controls</summary><p>Original BambuHelper controls remain available here for troubleshooting and edge cases.</p>';
    legacy.parentNode.insertBefore(details,legacy);details.appendChild(legacy);
  }
}
function v104TrimConnectionActions(){
  var con=v104El('v96ConnectionCards');if(!con)return;
  var card=con.querySelector('.card');if(card)card.classList.add('v104-connection-card');
  var support=v104El('supportBundleBtn');if(support)support.classList.add('v104-moved-action');
  if(card){card.querySelectorAll('.btn-danger').forEach(function(b){if(/clear printer/i.test(b.textContent||''))b.classList.add('v104-moved-action')})}
}
function v104PolishDisplayPanel(){
  var details=v104El('v97LegacyDisplay');if(details){var s=details.querySelector('summary');if(s)s.textContent='Advanced gauge configuration';var p=details.querySelector('p');if(p)p.textContent='Fine-tune individual gauge slots only when the visual presets above are not enough.'}
}
function v104SyncPrinterUX(){
  var root=v104El('v96PrinterWorkspace');if(!root)return;
  var state=v104El('v96PrinterState'),slot=Number(window.currentSlot||0),connected=state&&state.classList.contains('ok');
  var setup=v104El('printerSetupProgress'),health=v104El('setupHealth');if(setup)setup.classList.toggle('v104-hide-when-ready',!!connected);if(health)health.classList.add('v104-redundant-health');
  document.querySelectorAll('.v104-slot-btn').forEach(function(b){b.classList.toggle('active',Number(b.dataset.slot)===slot)});
  var summary=v104El('v104SlotSummary');if(summary)summary.textContent=(state?state.textContent:'Selected')+' · Printer '+(slot+1);
  var originalTabs=root.querySelectorAll('.v96-tab');originalTabs.forEach(function(b){var t=b.getAttribute('data-tab');if(t==='display')b.textContent='Touchscreen';if(t==='automation')b.textContent='Automations';if(t==='advanced')b.textContent='Support'});
}
function v104EnsurePrinterWorkspace(){
  var sec=v104El('sec-printer');if(!sec)return;
  if(!v104El('v96PrinterWorkspace')&&typeof v96InitPrinterWorkspace==='function'){try{v96InitPrinterWorkspace()}catch(e){console.warn('v10.4 printer workspace init',e)}}
  var root=v104El('v96PrinterWorkspace');if(!root)return;
  root.classList.add('v104-printer-workspace');v104BuildSlotSwitcher();v104BuildSupportPanel();v104TrimConnectionActions();v104PolishDisplayPanel();v104SyncPrinterUX();
  if(!v104PrinterHooked&&typeof v96RefreshPrinterWorkspace==='function'){
    var base=v96RefreshPrinterWorkspace;v96RefreshPrinterWorkspace=function(){var r=base.apply(this,arguments);setTimeout(v104SyncPrinterUX,260);return r};v104PrinterHooked=true;
  }
}
function v104PolishSidebar(){
  var footer=document.querySelector('.sidebar-footer');if(footer&&!footer.dataset.v104){footer.dataset.v104='1';footer.innerHTML='<strong>Workshop OS v10.4</strong><span>ws_lcd_350 · local-first</span><button type="button" onclick="v104NavTo(\'diag\')">System details</button>'}
  var adv=document.querySelector('.nav-item[data-section="advanced"] span:first-child');if(adv)adv.textContent='Advanced & Recovery';
}
function v104InitPortalUX(){
  v104EnsureTopHealth();v104PolishSidebar();v104EnsurePrinterWorkspace();v104RefreshTopHealth();
  if(v104PortalTimer)clearInterval(v104PortalTimer);v104PortalTimer=setInterval(function(){v104RefreshTopHealth();if(v104El('sec-printer')&&!v104El('v96PrinterWorkspace'))v104EnsurePrinterWorkspace()},5000);
  document.querySelectorAll('.nav-item[data-section="printer"]').forEach(function(b){b.addEventListener('click',function(){setTimeout(v104EnsurePrinterWorkspace,60)})});
}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',v104InitPortalUX);else v104InitPortalUX();
setTimeout(v104InitPortalUX,700);setTimeout(v104EnsurePrinterWorkspace,1800);

/* Smart Home v10.4.1 workshop-first Home */
var HH_WIDGET_KEY='waveshare_home_v1041';
var HH_WIDGET_IDS=['workshop','printer','device','network','system','quick'];
function hhEl(id){return document.getElementById(id)}
function hhSet(id,value){var e=hhEl(id);if(e)e.textContent=(value==null||value==='')?'—':String(value)}
function hhPrefs(){try{var p=JSON.parse(localStorage.getItem(HH_WIDGET_KEY)||'null');if(p&&Array.isArray(p.visible))return p}catch(e){}return{visible:(Array.isArray(HH_WIDGET_IDS) ? HH_WIDGET_IDS : []).slice()}}
function hhSavePrefs(p){try{localStorage.setItem(HH_WIDGET_KEY,JSON.stringify(p))}catch(e){}}
function hhApplyPrefs(){var p=hhPrefs();document.querySelectorAll('[data-hh-widget]').forEach(function(e){e.hidden=p.visible.indexOf(e.getAttribute('data-hh-widget'))<0});var ed=hhEl('hhEditor');if(ed)ed.querySelectorAll('[data-hh-toggle]').forEach(function(c){c.checked=p.visible.indexOf(c.getAttribute('data-hh-toggle'))>=0})}
function hhToggleWidget(id,on){var p=hhPrefs(),i=p.visible.indexOf(id);if(on&&i<0)p.visible.push(id);if(!on&&i>=0)p.visible.splice(i,1);hhSavePrefs(p);hhApplyPrefs()}
function hhToggleEditor(){var e=hhEl('hhEditor');if(!e)return;e.hidden=!e.hidden;if(!e.hidden)hhApplyPrefs()}
function hhInitEditor(){var e=hhEl('hhEditor');if(!e||e.dataset.ready)return;e.dataset.ready='1';e.querySelectorAll('[data-hh-toggle]').forEach(function(c){c.onchange=function(){hhToggleWidget(c.getAttribute('data-hh-toggle'),c.checked)}});hhApplyPrefs()}
function hhMinutes(m){m=Number(m||0);if(!m)return '—';var h=Math.floor(m/60),r=m%60;return h?(h+'h '+String(r).padStart(2,'0')+'m'):(r+'m')}
function hhNetworkLabel(rssi){rssi=Number(rssi);if(!isFinite(rssi)||rssi===0)return 'Unknown';if(rssi>=-60)return 'Strong';if(rssi>=-70)return 'Good';if(rssi>=-78)return 'Fair';return 'Weak'}
function hhActiveMaterial(d){var ams=d&&d.ams||{},trays=Array.isArray(ams.trays)?ams.trays:[],active=null;for(var i=0;i<trays.length;i++){if(trays[i].active){active=trays[i];break}}if(!active&&ams.activeTray===254&&ams.externalPresent)active={external:true,type:ams.externalType||'External spool',remain:-1,color:ams.externalColor||'#59636e'};return{ams:ams,trays:trays,active:active}}
function hhSetAttention(kind,title,text,label,action){var a=hhEl('hhAttention'),b=hhEl('hhAttentionAction');if(a)a.className='hh-attention '+(kind||'');hhSet('hhAttentionTitle',title);hhSet('hhAttentionText',text);if(b){b.textContent=label||'Open';b.onclick=action||function(){loadSection('workshop')}}}
function hhApplyStatus(d,r){d=d||{};r=r||{};var mat=hhActiveMaterial(d),active=mat.active,ams=mat.ams,configured=!!d.configured,connected=!!d.connected,printing=connected&&(Number(d.progress||0)>0||/PRINT|RUN/i.test(String(d.state||''))),rssi=Number(d.rssi||0),hw=d.hardware||{},errors=(Array.isArray(d.hms)?d.hms.length:0)+(d.printError?1:0),low=active&&Number(active.remain)>=0&&Number(active.remain)<15;
  // Top-level domains: Home intentionally balances workshop, printer, network and device.
  hhSet('hhWorkshopState',low?'Material low':(active?'Material loaded':(ams.present?'AMS ready':'Ready')));hhSet('hhWorkshopDetail',active?((active.type||'Filament')+(Number(active.remain)>=0?' · '+active.remain+'%':'')):(ams.present?((Number(ams.units||0))+' AMS unit'+(Number(ams.units||0)===1?'':'s')):'Workshop controls'));
  hhSet('hhPrinterState',printing?(d.state||'Printing'):(connected?(d.state||'Connected'):(configured?'Offline':'Not configured')));hhSet('hhPrinterDetail',configured?(d.name||'Selected printer'):'Printer setup is optional');
  hhSet('hhNetworkState',hhNetworkLabel(rssi));hhSet('hhNetworkDetail',(rssi?rssi+' dBm · ':'')+(d.ip||'No IP'));
  hhSet('hhDeviceState',r.webReady===false?'Starting':'Healthy');hhSet('hhDeviceDetail',(r.build||'Workshop OS')+(r.runningSlot?' · '+r.runningSlot:''));

  // Workshop card.
  hhSet('hhMaterial',active?(active.type||'Loaded filament'):'No material reported');hhSet('hhMaterialDetail',active?(active.external?'External spool':('AMS A'+(Number(active.slot)+1)+(Number(active.remain)>=0?' · '+active.remain+'% remaining':''))):(ams.present?'AMS connected; no active tray':'No AMS / external spool active'));
  var spool=hhEl('hhSpool');if(spool)spool.style.setProperty('--hh-spool',active&&active.color?active.color:'#59636e');
  hhSet('hhAms',ams.present?((Number(ams.units||0))+' unit'+(Number(ams.units||0)===1?'':'s')):(ams.externalPresent?'External spool':'Not present'));hhSet('hhLoadedTray',active?(active.external?'External':('A'+(Number(active.slot)+1))):'None');hhSet('hhLight',d.lightState===1?'On':(d.lightState===0?'Off':'Unknown'));

  // Compact Printer snapshot only — no duplicate deep telemetry.
  hhSet('hhPrinterName',d.name||('Printer '+(Number(window.currentSlot||0)+1)));hhSet('hhPrintState',configured?(connected?(d.state||'Connected'):'Offline'):'Not configured');var prog=Math.max(0,Math.min(100,Number(d.progress||0)));hhSet('hhPrintProgress',printing?prog+'%':(connected?'Ready':'—'));var bar=hhEl('hhPrintBar');if(bar)bar.style.width=(printing?prog:0)+'%';hhSet('hhEta',printing?hhMinutes(d.remaining):'—');hhSet('hhLayer',printing?((Number(d.layer||0))+' / '+(Number(d.layers||0))):'—');hhSet('hhChamber',d.chamber==null?'—':Math.round(Number(d.chamber))+'°C');

  // Device / network / system.
  hhSet('hhTouch',r.touchResponsive===false?'Attention':(r.touch?'Ready':'FT6336'));hhSet('hhAudio',hw.audio||'ES8311');hhSet('hhMic',hw.microphone?'Available':'—');hhSet('hhBle',hw.bluetooth||'BLE');
  hhSet('hhRssi',rssi?rssi+' dBm · '+hhNetworkLabel(rssi):'Unknown');hhSet('hhIp',d.ip||r.ip||'—');hhSet('hhPrinterLink',configured?(connected?'Connected':'Offline'):'Not configured');
  hhSet('hhBuild',r.build||'Workshop OS');hhSet('hhSlot',r.runningSlot||'—');hhSet('hhCandidate',r.candidatePending?('Pending · attempt '+Number(r.candidateAttempts||0)):'Healthy');

  // Cross-domain attention. Printer is one source, never the sole definition of Home health.
  var overall='Operational',orb='ok';
  if(r.safeMode){overall='Recovery mode';orb='bad';hhSetAttention('bad','Recovery Safe Mode is active','Normal Workshop OS services may be intentionally limited.','Open Recovery',function(){location.href='/recovery'})}
  else if(r.webReady===false){overall='Starting';orb='';hhSetAttention('','Control plane is starting','The device is online but the normal web control plane is not fully ready yet.','Diagnostics',function(){loadSection('diag')})}
  else if(errors){overall='Needs attention';orb='bad';hhSetAttention('bad','Printer reports '+errors+' issue'+(errors===1?'':'s'),'Open Printer Errors for the current printer while the rest of Workshop OS remains available.','Printer Errors',function(){if(hhEl('sec-errors'))loadSection('errors');else loadSection('printer')})}
  else if(low){overall='Material low';orb='';hhSetAttention('','Loaded filament is running low',(active.type||'Filament')+' is at '+active.remain+'% remaining.','Open Workshop',function(){loadSection('workshop')})}
  else if(rssi&&rssi<-78){overall='Network attention';orb='';hhSetAttention('','Wi‑Fi signal is weak','The device reports '+rssi+' dBm. Printer and portal reliability may improve with a stronger signal.','Network',function(){loadSection('wifi')})}
  else if(configured&&!connected){overall='Printer offline';orb='';hhSetAttention('','Printer is offline','Workshop, device and recovery services are still available. Open Printer when you want to troubleshoot the connection.','Open Printer',function(){loadSection('printer')})}
  else{hhSetAttention('ok','Workshop is ready',active?((active.type||'Material')+' is loaded and core device services are healthy.'):'Core device services are healthy. No immediate action is required.','Open Workshop',function(){loadSection('workshop')})}
  hhSet('hhOverall',overall);hhSet('hhUpdated','Updated '+new Date().toLocaleTimeString([], {hour:'numeric',minute:'2-digit'}));var o=hhEl('hhOverallOrb');if(o)o.className='hh-orb '+orb;
}
function refreshCommandCenter(manual){hhInitEditor();if(manual&&typeof refreshPrinterHealth==='function')refreshPrinterHealth(true);var slot=Number(window.currentSlot||0);Promise.all([fetch('/status?slot='+slot+'&_='+Date.now(),{cache:'no-store'}).then(function(x){if(!x.ok)throw new Error('status');return x.json()}),fetch('/recovery/status?_='+Date.now(),{cache:'no-store'}).then(function(x){if(!x.ok)throw new Error('recovery');return x.json()})]).then(function(v){hhApplyStatus(v[0],v[1])}).catch(function(){hhSet('hhOverall','Status unavailable');hhSet('hhUpdated','Refresh to retry');var o=hhEl('hhOverallOrb');if(o)o.className='hh-orb bad';hhSetAttention('bad','Home status could not be refreshed','The local portal is reachable, but one or more status endpoints did not respond.','Diagnostics',function(){loadSection('diag')})})}
// Disable the legacy v9.5 Home injector. Its full-width Live Print card duplicated the dedicated Printer workspace.
function ccInstallWidgetEditor(){hhInitEditor()}
function ccRefreshLiveWidget(){}
setTimeout(function(){hhInitEditor();refreshCommandCenter(false)},50);


/* Smart Home v11.1 Calm Workshop OS — Home & Standby customization */
(function(){
  function el(id){return document.getElementById(id)}
  function esc(v){return String(v==null?'':v).replace(/[&<>"']/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]})}
  function accentHex(v){return ['#f59a45','#43c7d9','#69a7ff','#aa83ff','#65d89b'][Number(v)||0]}
  function preview(){var box=el('v111Preview');if(!box)return;var a=accentHex(el('v111Accent').value);box.style.setProperty('--v111-accent',a);var note=(el('v111Note').value||'').trim();el('v111PreviewNote').textContent=note||'Everything important is one tap away';el('v111PreviewAudio').textContent=el('v111Events').checked?'Audio on':'Muted';}
  function hours(value){var out='';for(var i=0;i<24;i++){out+='<option value="'+i+'"'+(Number(value)===i?' selected':'')+'>'+String(i).padStart(2,'0')+':00</option>'}return out}
  window.v111LoadExperience=function(){fetch('/hub/experience?_='+Date.now(),{cache:'no-store'}).then(function(r){if(!r.ok)throw new Error('HTTP '+r.status);return r.json()}).then(function(d){el('v111Accent').value=String(d.accent||0);el('v111Ambient').checked=d.ambient!==false;el('v111Note').value=d.note||'';var tp=d.timerPresets||[d.timerMinutes||5,15,30,60];for(var i=0;i<4;i++){var t=el('v112Timer'+(i+1));if(t)t.value=String(tp[i]==null?[5,15,30,60][i]:tp[i]);}el('v111Events').checked=!!d.eventSounds;el('v111QuietStart').innerHTML=hours(d.quietStart||0);el('v111QuietEnd').innerHTML=hours(d.quietEnd||0);preview();}).catch(function(e){var st=el('v111Status');if(st)st.textContent='Could not load Workshop experience settings.';console.warn(e)})}
  window.v111SaveExperience=function(){var p=new URLSearchParams();p.append('accent',el('v111Accent').value);p.append('ambient',el('v111Ambient').checked?'1':'0');p.append('note',el('v111Note').value.trim());for(var i=1;i<=4;i++)p.append('timer'+i,el('v112Timer'+i).value);p.append('timerMinutes',el('v112Timer1').value);p.append('eventSounds',el('v111Events').checked?'1':'0');p.append('quietStart',el('v111QuietStart').value);p.append('quietEnd',el('v111QuietEnd').value);var b=el('v111Save');b.disabled=true;b.textContent='Saving…';fetch('/hub/experience',{method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded'},body:p.toString()}).then(function(r){if(!r.ok)throw new Error('HTTP '+r.status);return r.json()}).then(function(){el('v111Status').textContent='Saved to the physical Workshop OS.';showToast('Home & Standby updated');preview();}).catch(function(){el('v111Status').textContent='Save failed.'}).then(function(){b.disabled=false;b.textContent='Save Workshop Experience'})}
  function init(){var host=el('smartHubCard');if(!host||el('v111ExperienceCard'))return;var card=document.createElement('div');card.className='card v111-experience';card.id='v111ExperienceCard';card.innerHTML='<div class="card-head"><div><span class="v111-eyebrow">HOME, STANDBY & TOOLS</span><h3>Make the physical display yours</h3><p>Calm at a glance, detailed on demand. These settings are stored locally on the Waveshare.</p></div><span class="v111-chip">v11.2</span></div><div class="v111-layout"><div class="v111-form"><label>Accent<select id="v111Accent"><option value="0">Ember</option><option value="1">Cyan</option><option value="2">Blue</option><option value="3">Purple</option><option value="4">Green</option></select></label><label class="v111-check"><input id="v111Ambient" type="checkbox"> Ambient standby when idle</label><label>Workshop note<textarea id="v111Note" maxlength="63" rows="2" placeholder="Dry PETG before next print"></textarea></label><div><span class="v112-label">QUICK TIMER PRESETS</span><div class="v112-timer-grid"><label>Preset 1<span><input id="v112Timer1" type="number" min="1" max="120" value="5"> min</span></label><label>Preset 2<span><input id="v112Timer2" type="number" min="1" max="120" value="15"> min</span></label><label>Preset 3<span><input id="v112Timer3" type="number" min="1" max="120" value="30"> min</span></label><label>Preset 4<span><input id="v112Timer4" type="number" min="1" max="120" value="60"> min</span></label></div></div><div class="v112-runtime"><div><small>WORKSHOP TIMER</small><strong id="v112TimerState">Ready</strong></div><div class="v112-runtime-actions"><button type="button" onclick="v112StartPreset(1)">Start 1</button><button type="button" onclick="v112StartPreset(2)">Start 2</button><button type="button" onclick="v112StartPreset(3)">Start 3</button><button type="button" onclick="v112StartPreset(4)">Start 4</button><button type="button" class="danger" onclick="v112CancelTimer()">Cancel</button></div></div><label class="v111-check"><input id="v111Events" type="checkbox"> Event sounds</label><div class="v111-pair"><label>Quiet from<select id="v111QuietStart"></select></label><label>Quiet until<select id="v111QuietEnd"></select></label></div><button id="v111Save" class="btn btn-primary" type="button" onclick="v111SaveExperience()">Save Workshop Experience</button><small id="v111Status" class="text-dim">Quiet start = quiet end disables quiet hours.</small></div><div id="v111Preview" class="v111-preview"><div class="v111-preview-head"><b>WORKSHOP</b><span>9:02 ●</span></div><strong>WORKSHOP READY</strong><p id="v111PreviewNote">Everything important is one tap away</p><div class="v111-preview-spools"><i></i><i></i><i></i><i></i></div><div class="v111-preview-services"><span>Network</span><span id="v111PreviewAudio">Audio on</span><span>Recovery</span></div></div></div>';host.insertAdjacentElement('afterend',card);['v111Accent','v111Ambient','v111Note','v111Events'].forEach(function(id){el(id).addEventListener('input',preview)});v111LoadExperience()}
  setTimeout(init,700);setTimeout(init,1800);
})();


/* Smart Home v11.2 Workshop Tools — live timer controls */
(function(){
  function el(id){return document.getElementById(id)}
  function fmt(sec){sec=Math.max(0,Number(sec)||0);return String(Math.floor(sec/60)).padStart(2,'0')+':'+String(sec%60).padStart(2,'0')}
  function status(){fetch('/hub/timer/status?_='+Date.now(),{cache:'no-store'}).then(function(r){return r.json()}).then(function(d){var s=el('v112TimerState');if(!s)return;s.textContent=d.done?'Complete':(d.active?fmt(d.remainingSeconds):'Ready');s.className=d.done?'done':(d.active?'active':'');if(d.active)setTimeout(status,1000)}).catch(function(){})}
  window.v112StartPreset=function(i){var input=el('v112Timer'+i);var m=Math.max(1,Math.min(120,Number(input&&input.value)||0));var p=new URLSearchParams();p.append('minutes',String(m));fetch('/hub/timer/start',{method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded'},body:p.toString()}).then(function(r){if(!r.ok)throw new Error('start');showToast('Workshop timer started');status()}).catch(function(){showToast('Could not start timer')})}
  window.v112CancelTimer=function(){fetch('/hub/timer/cancel',{method:'POST'}).then(function(r){if(!r.ok)throw new Error('cancel');showToast('Workshop timer cleared');status()}).catch(function(){showToast('Could not clear timer')})}
  setTimeout(status,250);
})();


/* Smart Home v11.3 Printer Control */
var v113ControlTimer=null;
function v113El(id){return document.getElementById(id)}
function v113Post(path,data){var p=new URLSearchParams();Object.keys(data).forEach(function(k){p.append(k,data[k])});return fetch(path,{method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded'},body:p.toString()}).then(function(r){return r.json().catch(function(){return {}}).then(function(j){if(!r.ok)throw new Error(j.message||('HTTP '+r.status));return j})})}
function v114ControlBusy(busy){['v113Light','v113Pause','v113Stop','v115Power'].forEach(function(id){var el=v113El(id);if(el)el.disabled=!!busy})}
function v113PrinterCommand(cmd){var slot=Number(window.currentSlot||0);if(cmd==='stop'&&!window.confirm('Stop the current print? This cannot be undone.'))return;var b=v113El('v113ControlStatus');if(b)b.textContent='Sending '+cmd+'…';v114ControlBusy(true);v113Post('/printer/control',{slot:slot,command:cmd,confirm:cmd==='stop'?'STOP':''}).then(function(){if(b)b.textContent=cmd.charAt(0).toUpperCase()+cmd.slice(1)+' command sent';showToast('Printer command sent');setTimeout(v113RefreshControls,700)}).catch(function(e){if(b)b.textContent=e.message||'Command failed';showToast('Command failed')}).then(function(){setTimeout(function(){v114ControlBusy(false);v113RefreshControls()},450)})}
function v113Light(mode){var slot=Number(window.currentSlot||0),b=v113El('v113ControlStatus');if(b)b.textContent='Turning light '+mode+'…';v114ControlBusy(true);v113Post('/light/set',{slot:slot,mode:mode}).then(function(){if(b)b.textContent='Light command sent';setTimeout(v113RefreshControls,600)}).catch(function(e){if(b)b.textContent=e.message||'Light command failed'}).then(function(){setTimeout(function(){v114ControlBusy(false);v113RefreshControls()},450)})}
function v113EnsureControls(){var host=v113El('v96OverviewCards');if(!host||v113El('v113PrinterControl'))return;var card=document.createElement('div');card.id='v113PrinterControl';card.className='v113-control-card';card.innerHTML='<div class="v113-control-head"><div><span class="v96-eyebrow">PRINTER CONTROL</span><h3>Remote controls</h3><p>Direct controls for the selected printer. Stop is always confirmed.</p></div><span id="v113ControlStatus">Reading printer…</span></div><div class="v113-controls"><button id="v113Light" type="button" onclick="v113Light(this.dataset.mode||\'on\')">Light</button><button id="v113Pause" type="button" onclick="v113PrinterCommand(this.dataset.command||\'pause\')">Pause</button><button id="v113Stop" class="danger" type="button" onclick="v113PrinterCommand(\'stop\')">Stop print</button><button id="v115Power" type="button" onclick="v115PrinterPower()" disabled>Printer power</button></div>';host.insertBefore(card,host.firstChild);v113RefreshControls();if(v113ControlTimer)clearInterval(v113ControlTimer);v113ControlTimer=setInterval(function(){var p=v113El('sec-printer');if(p&&p.style.display!=='none')v113RefreshControls()},2500)}
function v113RefreshControls(){if(!v113El('v113PrinterControl')){v113EnsureControls();return}var slot=Number(window.currentSlot||0);fetch('/status?slot='+slot+'&_='+Date.now(),{cache:'no-store'}).then(function(r){return r.json()}).then(function(d){var connected=!!d.connected,state=String(d.state||'').toUpperCase(),paused=state==='PAUSE'||state==='PAUSED',active=!!d.printing||paused||state==='RUNNING'||state==='PRINTING';var l=v113El('v113Light'),p=v113El('v113Pause'),x=v113El('v113Stop'),s=v113El('v113ControlStatus');if(l){l.disabled=!connected;l.dataset.mode=Number(d.lightState)===1?'off':'on';l.textContent=Number(d.lightState)===1?'Turn light off':'Turn light on'}if(p){p.disabled=!connected||!active;p.dataset.command=paused?'resume':'pause';p.textContent=paused?'Resume print':'Pause print'}if(x)x.disabled=!connected||!active;if(s)s.textContent=connected?(active?(paused?'Print paused · controls ready':'Printing · controls ready'):'Printer ready · light control available'):'Printer offline'})['catch'](function(){var s=v113El('v113ControlStatus');if(s)s.textContent='Printer status unavailable'})}
(function(){var boot=function(){var wait=setInterval(function(){if(v113El('v96OverviewCards')){clearInterval(wait);v113EnsureControls()}},250)};if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot);else boot();document.addEventListener('click',function(e){var b=e.target.closest&&e.target.closest('.nav-item[data-section="printer"]');if(b)setTimeout(v113EnsureControls,120)},true)}());


/* Smart Home v11.5 Printer Power */
var v115PowerState={available:false,online:false,on:false,printing:false,busy:false};
function v115RefreshPower(){var b=v113El('v115Power');if(!b)return;var slot=Number(window.currentSlot||0);Promise.all([fetch('/printer/power/status?slot='+slot+'&_='+Date.now(),{cache:'no-store'}).then(function(r){return r.json()}),fetch('/status?slot='+slot+'&_='+Date.now(),{cache:'no-store'}).then(function(r){return r.json()})]).then(function(v){var p=v[0]||{},d=v[1]||{},state=String(d.state||'').toUpperCase();v115PowerState.available=!!p.available;v115PowerState.online=!!p.online;v115PowerState.on=!!p.on;v115PowerState.printing=!!d.printing||state==='RUNNING'||state==='PRINTING'||state==='PAUSE'||state==='PAUSED';b.disabled=!p.available||!p.online||v115PowerState.busy;b.textContent=!p.available?'Power not mapped':(!p.online?'Power plug offline':(p.on?'Power off':'Power on'));b.classList.toggle('danger',!!p.on);}).catch(function(){b.disabled=true;b.textContent='Power unavailable'})}
function v115PrinterPower(){var b=v113El('v115Power'),s=v113El('v113ControlStatus'),st=v115PowerState;if(!b||!st.available||!st.online||st.busy)return;var desired=!st.on,token='';if(!desired){var msg=st.printing?'The printer is actively printing. Cutting power can damage the print and should only be used intentionally. Power off anyway?':'Power off the mapped printer plug?';if(!window.confirm(msg))return;token=st.printing?'POWER OFF DURING PRINT':'POWER OFF';}else if(!window.confirm('Power on the mapped printer plug?'))return;st.busy=true;v114ControlBusy(true);if(s)s.textContent=desired?'Powering printer on…':'Powering printer off…';v113Post('/printer/power',{slot:Number(window.currentSlot||0),on:desired?'1':'0',confirm:token}).then(function(){if(s)s.textContent=desired?'Printer power on sent':'Printer power off sent';showToast(desired?'Printer power on':'Printer power off');setTimeout(v115RefreshPower,900)}).catch(function(e){if(s)s.textContent=e.message||'Power command failed';showToast('Power command failed')}).then(function(){st.busy=false;setTimeout(function(){v114ControlBusy(false);v113RefreshControls();v115RefreshPower()},500)})}
(function(){var old=v113RefreshControls;v113RefreshControls=function(){var r=old.apply(this,arguments);setTimeout(v115RefreshPower,80);return r};setTimeout(v115RefreshPower,600)})();

/* Smart Home v11.6 Workshop Command Center */
var v116PowerState={slot:-1,available:false,online:false,on:false,printing:false,busy:false};
var v116WorkshopSlot=-1;
var v116StatusSeq=0;
var v116PowerSeq=0;

function v116Set(id,text){
  var e=document.getElementById(id);
  if(e)e.textContent=text==null?'—':String(text);
}
function v116CurrentSlot(){
  var n=Number(window.currentSlot||0);
  return Number.isFinite(n)&&n>=0?Math.floor(n):0;
}
function v116Finite(value,fallback){
  var n=Number(value);
  return Number.isFinite(n)?n:fallback;
}
function v116Percent(value){
  return Math.max(0,Math.min(100,v116Finite(value,0)));
}
function v116SafeColor(value,fallback){
  var s=String(value||'').trim();
  if(/^[0-9a-fA-F]{6}$/.test(s)||/^[0-9a-fA-F]{8}$/.test(s))s='#'+s;
  if(/^#[0-9a-fA-F]{3}$/.test(s)||/^#[0-9a-fA-F]{4}$/.test(s)||/^#[0-9a-fA-F]{6}$/.test(s)||/^#[0-9a-fA-F]{8}$/.test(s))return s;
  return fallback||'#59636e';
}
function v116Post(path,data){
  var p=new URLSearchParams();
  Object.keys(data).forEach(function(k){p.append(k,data[k])});
  return fetch(path,{method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded'},body:p.toString()}).then(function(r){
    return r.json().catch(function(){return {}}).then(function(j){
      if(!r.ok)throw new Error(j.message||('HTTP '+r.status));
      return j;
    });
  });
}
function v116IsPaused(d){
  var s=String((d&&d.state)||'').toUpperCase();
  return s==='PAUSE'||s==='PAUSED';
}
function v116IsPrinting(d){
  var s=String((d&&d.state)||'').toUpperCase();
  return !!(d&&d.printing)||s==='RUNNING'||s==='PRINTING'||s==='PAUSE'||s==='PAUSED';
}
function v116StateLabel(d){
  if(!d.configured)return 'Setup Required';
  if(!d.connected)return 'Printer Offline';
  var s=String(d.state||'READY').toUpperCase();
  if(s==='FINISH'||s==='FINISHED')return 'Print Complete';
  if(s==='IDLE')return 'Ready';
  return s.toLowerCase().replace(/(^|[\s_-])([a-z])/g,function(m,a,c){return (a==='_'?' ':a)+c.toUpperCase()});
}
function v116JobLabel(d){
  if(!d.connected)return d.configured?'Printer unavailable':'Configure a printer';
  var s=String(d.state||'').toUpperCase();
  if(v116IsPrinting(d))return v116IsPaused(d)?'Print paused':'Print in progress';
  if(s==='FINISH'||s==='FINISHED')return 'Last print complete';
  return 'Ready for the next print';
}
function v116Feedback(text,bad){
  var e=document.getElementById('wk116Feedback');
  if(!e)return;
  e.textContent=text||'';
  e.style.color=bad?'var(--danger)':'var(--text-dim)';
}
function v116SetConnectionState(connected,configured,label){
  var chip=document.getElementById('wk116Connection');
  if(!chip)return;
  chip.className='wk116-live-chip '+(connected?'ok':(configured?'bad':'warn'));
  chip.textContent=label||(connected?'Local · Live':(configured?'Offline':'Setup'));
}
function v116DisableControls(){
  var ids=['wkLightBtn','wk116PauseBtn','wk116PowerBtn'];
  ids.forEach(function(id){var b=document.getElementById(id);if(b)b.disabled=true});
  v116PowerState.slot=-1;
  v116PowerState.available=false;
  v116PowerState.online=false;
  v116PowerState.busy=false;
}
function v116ClearChildren(node){
  while(node.firstChild)node.removeChild(node.firstChild);
}
function v116RenderTrays(ams){
  var deck=document.getElementById('wkTrays');
  if(!deck)return;
  var trays=Array.isArray(ams.trays)?ams.trays:[];
  v116ClearChildren(deck);
  if(!trays.length){
    var empty=document.createElement('div');
    empty.className='wk-empty';
    empty.textContent=ams.present?'AMS detected; waiting for material details.':'No AMS tray data reported.';
    deck.appendChild(empty);
    return;
  }
  trays.forEach(function(tr){
    tr=tr||{};
    var remain=v116Finite(tr.remain,-1);
    var slot=v116Finite(tr.slot,-1);
    var color=v116SafeColor(tr.color,'#59636e');
    var card=document.createElement('div');
    card.className='wk-tray'+(tr.active?' active':'');
    card.style.setProperty('--tray-color',color);

    var swatch=document.createElement('span');
    swatch.className='wk-tray-swatch';
    swatch.style.setProperty('--tray-color',color);
    swatch.setAttribute('aria-hidden','true');

    var copy=document.createElement('div');
    var small=document.createElement('small');
    small.textContent=(slot>=0?'A'+(slot+1):'A?')+(tr.active?' · ACTIVE':'');
    var strong=document.createElement('strong');
    strong.textContent=String(tr.type||'Filament');
    copy.appendChild(small);
    copy.appendChild(strong);

    var remaining=document.createElement('span');
    remaining.className='wk-remain';
    remaining.textContent=remain>=0?Math.max(0,Math.min(100,Math.round(remain)))+'%':'—';

    card.appendChild(swatch);
    card.appendChild(copy);
    card.appendChild(remaining);
    deck.appendChild(card);
  });
}
function v116RefreshPower(d,slot){
  var b=document.getElementById('wk116PowerBtn');
  if(!b)return;
  slot=slot==null?v116CurrentSlot():slot;
  var seq=++v116PowerSeq;
  return v117FetchJson('/printer/power/status?slot='+slot+'&_='+Date.now(),3000).then(function(p){
    if(seq!==v116PowerSeq||slot!==v116CurrentSlot()||slot!==v116WorkshopSlot)return;
    v116PowerState.slot=slot;
    v116PowerState.available=!!p.available;
    v116PowerState.online=!!p.online;
    v116PowerState.on=!!p.on;
    v116PowerState.printing=v116IsPrinting(d);
    b.disabled=!p.available||!p.online||v116PowerState.busy||!v117StateFresh(slot);
    v116Set('wk116PowerLabel',!p.available?'Power not mapped':(p.on?'Power off':'Power on'));
    v116Set('wk116PowerHint',!p.available?'Map a smart plug in Power':(!p.online?'Plug offline':(p.on?'Printer outlet is on':'Printer outlet is off')));
  }).catch(function(){
    if(seq!==v116PowerSeq||slot!==v116CurrentSlot()||slot!==v116WorkshopSlot)return;
    v116PowerState.slot=-1;
    v116PowerState.available=false;
    v116PowerState.online=false;
    v116PowerState.busy=false;
    b.disabled=true;
    v116Set('wk116PowerLabel','Power unavailable');
    v116Set('wk116PowerHint','Could not read smart plug');
  });
}
function v103RefreshWorkshop(manual){
  var root=document.getElementById('sec-workshop');
  if(!root)return;
  var slot=v116CurrentSlot();
  var seq=++v116StatusSeq;
  if(slot!==v116WorkshopSlot){
    v103WorkshopData={};
    v116DisableControls();
    v116Set('wkUpdated','Syncing selected printer…');
    v116SetConnectionState(false,false,'Syncing');
  }
  return v117FetchJson('/status?slot='+slot+'&_='+Date.now(),3500).then(function(d){
    if(seq!==v116StatusSeq||slot!==v116CurrentSlot())return;
    d=d||{};
    v116WorkshopSlot=slot;
    v103WorkshopData=d;
    v117MarkFresh(slot);
    var connected=!!d.connected;
    var p=v116Percent(d.progress);
    var paused=v116IsPaused(d);
    var printing=v116IsPrinting(d);

    v116Set('wkState',v116StateLabel(d));
    v116Set('wkUpdated','Updated '+new Date().toLocaleTimeString([],{hour:'numeric',minute:'2-digit'}));
    v116SetConnectionState(connected,!!d.configured);
    var dot=document.getElementById('wkDot');
    if(dot)dot.className=connected?'ok':(d.configured?'bad':'warn');

    v116Set('wkProgress',p+'%');
    v116Set('wkProgressSub',printing?(paused?'Paused':'Current Job'):'Printer Status');
    v116Set('wk116Job',v116JobLabel(d));
    var bar=document.getElementById('wk116ProgressBar');
    if(bar){
      bar.style.width=(printing||p?p:0)+'%';
      bar.parentElement.setAttribute('aria-valuenow',String(p));
      bar.parentElement.setAttribute('aria-valuetext',printing?(p+'% complete'):'No active print');
    }
    v116Set('wkRemaining',v103Minutes(d.remaining));
    var layer=v116Finite(d.layer,0),layers=v116Finite(d.layers,0);
    v116Set('wkLayer',Math.max(0,Math.round(layer))+' / '+Math.max(0,Math.round(layers)));
    var chamber=v116Finite(d.chamber,NaN);
    v116Set('wkChamber',Number.isFinite(chamber)?Math.round(chamber)+'°C':'—');
    v116Set('wk116Summary',connected?(printing?(paused?'Print paused — controls remain available locally.':'Printing now — material and controls are live below.'):'Printer ready — materials and local controls are available.'):(d.configured?'Printer is configured but currently offline.':'Configure your printer to unlock live Workshop controls.'));

    v116Set('wkLightState',d.lightState===1?'On':(d.lightState===0?'Off':'State unavailable'));
    v116Set('wk116LightLabel',d.lightState===1?'Light off':'Light on');
    var light=document.getElementById('wkLightBtn');
    if(light)light.disabled=!connected||v117CommandBusy.light||!v117StateFresh(slot);

    var pause=document.getElementById('wk116PauseBtn');
    if(pause){
      pause.disabled=!connected||!printing||v117CommandBusy.pause||!v117StateFresh(slot);
      v116Set('wk116PauseLabel',paused?'Resume':'Pause');
      v116Set('wk116PauseHint',printing?(paused?'Continue print':'Pause safely'):'No active print');
    }

    var ams=d.ams||{};
    var trays=Array.isArray(ams.trays)?ams.trays:[];
    var active=null;
    for(var i=0;i<trays.length;i++)if(trays[i]&&trays[i].active){active=trays[i];break}
    if(!active&&ams.activeTray===254&&ams.externalPresent){
      active={type:ams.externalType||'External spool',remain:-1,color:ams.externalColor||'#8b949e',external:true};
    }
    var units=Math.max(0,Math.round(v116Finite(ams.units,0)));
    v116Set('wkAmsState',ams.present?(units+' AMS unit'+(units===1?'':'s')):(ams.externalPresent?'External spool':'No AMS'));
    var readyCount=trays.length;
    v116Set('wkLoadedEyebrow',active?'Active Material':(readyCount?'AMS Ready':'Material Status'));
    v116Set('wkLoadedName',active?(active.type||'Loaded filament'):(readyCount?(readyCount+' material'+(readyCount===1?'':'s')+' ready'):'No material detected'));
    var activeSlot=v116Finite(active&&active.slot,-1);
    var activeRemain=v116Finite(active&&active.remain,-1);
    v116Set('wkLoadedDetail',active?(active.external?'External spool':((activeSlot>=0?'A'+(activeSlot+1):'AMS tray')+(activeRemain>=0?' · '+Math.max(0,Math.min(100,Math.round(activeRemain)))+'% remaining':''))):(readyCount?'AMS loaded · no tray currently feeding':'Printer has not reported material'));
    var spool=document.getElementById('wkLoadedSpool');
    if(spool)spool.style.setProperty('--spool-color',v116SafeColor(active&&active.color,'#59636e'));
    v116RenderTrays(ams);
    v116RefreshPower(d,slot);
    if(manual)v116Feedback('Workshop refreshed');
  }).catch(function(err){
    if(seq!==v116StatusSeq||slot!==v116CurrentSlot())return;
    v116WorkshopSlot=-1;
    v103WorkshopData={};
    v116DisableControls();
    v116Set('wkState','Unavailable');
    v116Set('wkUpdated','Device status could not be read');
    v116SetConnectionState(false,true);
    var dot=document.getElementById('wkDot');
    if(dot)dot.className='bad';
    v116Feedback(err.message||'Status unavailable',true);
    v117MarkStale(err.message||'Status unavailable');
  });
}
function v103ToggleWorkshopLight(){
  var slot=v116CurrentSlot();
  var d=v103WorkshopData||{},b=document.getElementById('wkLightBtn');
  if(v116WorkshopSlot!==slot||!d.connected||!b||!v117StateFresh(slot)||v117CommandBusy.light)return;
  v117CommandBusy.light=true;
  b.disabled=true;
  v116Feedback(d.lightState===1?'Turning chamber light off…':'Turning chamber light on…');
  v116Post('/light/set',{slot:slot,mode:d.lightState===1?'off':'on'}).then(function(){
    v117CommandBusy.light=false;
    if(slot!==v116CurrentSlot())return;
    v116Feedback('Light command sent');
    setTimeout(function(){if(slot===v116CurrentSlot())v103RefreshWorkshop(false)},500);
  }).catch(function(e){
    v117CommandBusy.light=false;
    if(slot!==v116CurrentSlot())return;
    v116Feedback(e.message||'Light command failed',true);
    b.disabled=false;
  });
}
function v116PauseResume(){
  var slot=v116CurrentSlot();
  var d=v103WorkshopData||{},b=document.getElementById('wk116PauseBtn');
  if(v116WorkshopSlot!==slot||!d.connected||!v116IsPrinting(d)||!b||!v117StateFresh(slot)||v117CommandBusy.pause)return;
  var cmd=v116IsPaused(d)?'resume':'pause';
  v117CommandBusy.pause=true;
  b.disabled=true;
  v116Feedback(cmd==='resume'?'Resuming print…':'Pausing print…');
  v116Post('/printer/control',{slot:slot,command:cmd}).then(function(){
    v117CommandBusy.pause=false;
    if(slot!==v116CurrentSlot())return;
    v116Feedback((cmd==='resume'?'Resume':'Pause')+' command sent');
    setTimeout(function(){if(slot===v116CurrentSlot())v103RefreshWorkshop(false)},650);
  }).catch(function(e){
    v117CommandBusy.pause=false;
    if(slot!==v116CurrentSlot())return;
    v116Feedback(e.message||'Printer command failed',true);
    b.disabled=false;
  });
}
function v116TogglePower(){
  var slot=v116CurrentSlot();
  var st=v116PowerState,b=document.getElementById('wk116PowerBtn');
  if(!b||st.slot!==slot||v116WorkshopSlot!==slot||!st.available||!st.online||st.busy||!v117StateFresh(slot))return;
  var desired=!st.on,token='';
  if(!desired){
    var msg=st.printing?'A print is active. Cutting power can damage the print. Power off anyway?':'Power off the mapped printer outlet?';
    if(!window.confirm(msg))return;
    token=st.printing?'POWER OFF DURING PRINT':'POWER OFF';
  }else if(!window.confirm('Power on the mapped printer outlet?'))return;
  st.busy=true;
  b.disabled=true;
  v116Feedback(desired?'Powering printer on…':'Powering printer off…');
  v116Post('/printer/power',{slot:slot,on:desired?1:0,confirm:token}).then(function(){
    if(slot!==v116CurrentSlot())return;
    v116Feedback(desired?'Printer power on command complete':'Printer power off command complete');
    st.busy=false;
    setTimeout(function(){if(slot===v116CurrentSlot())v103RefreshWorkshop(false)},700);
  }).catch(function(e){
    if(slot!==v116CurrentSlot())return;
    st.busy=false;
    b.disabled=false;
    v116Feedback(e.message||'Power command failed',true);
  });
}

/* Smart Home v11.7 Live State Integrity */
var v116LastStatusAt=0;
var v117PollTimer=null;
var v117WatchdogTimer=null;
var v117Polling=false;
var v117CommandBusy={light:false,pause:false};
var V117_STALE_MS=10000;

function v117WorkshopVisible(){
  var root=document.getElementById('sec-workshop');
  return !!root&&!root.hidden&&document.visibilityState!=='hidden';
}
function v117DisableUiOnly(){
  ['wkLightBtn','wk116PauseBtn','wk116PowerBtn'].forEach(function(id){
    var b=document.getElementById(id);
    if(b)b.disabled=true;
  });
}
function v117StateFresh(slot){
  slot=slot==null?v116CurrentSlot():slot;
  return slot===v116CurrentSlot()&&slot===v116WorkshopSlot&&v116LastStatusAt>0&&(Date.now()-v116LastStatusAt)<=V117_STALE_MS;
}
function v117FetchJson(url,timeoutMs){
  timeoutMs=Math.max(1000,Number(timeoutMs)||3500);
  var controller=typeof AbortController!=='undefined'?new AbortController():null;
  var options={cache:'no-store'};
  if(controller)options.signal=controller.signal;
  var timer=null;
  var timeout=new Promise(function(resolve,reject){
    timer=setTimeout(function(){
      if(controller){try{controller.abort()}catch(e){}}
      var err=new Error('Local device response timed out');
      err.name='TimeoutError';
      reject(err);
    },timeoutMs);
  });
  var request=fetch(url,options).then(function(r){
    return r.json().catch(function(){return {}}).then(function(j){
      if(!r.ok)throw new Error(j.message||('HTTP '+r.status));
      return j;
    });
  });
  return Promise.race([request,timeout]).then(function(value){
    if(timer)clearTimeout(timer);
    return value;
  },function(err){
    if(timer)clearTimeout(timer);
    if(err&&err.name==='AbortError')throw new Error('Local device response timed out');
    throw err;
  });
}
function v117MarkFresh(slot){
  if(slot!==v116CurrentSlot()||slot!==v116WorkshopSlot)return;
  v116LastStatusAt=Date.now();
  var root=document.getElementById('sec-workshop');
  if(root)root.classList.remove('is-stale');
}
function v117MarkStale(reason){
  var root=document.getElementById('sec-workshop');
  if(!root||root.hidden)return;
  v117DisableUiOnly();
  root.classList.add('is-stale');
  v116SetConnectionState(false,false,'STALE');
  v116Set('wkUpdated',reason||'Live state expired — refreshing…');
}
function v117WatchFreshness(){
  if(!v117WorkshopVisible())return;
  if(!v117StateFresh(v116CurrentSlot()))v117MarkStale('Live state expired — refreshing…');
}
function v117PollDelay(){
  var d=v103WorkshopData||{};
  return v116IsPrinting(d)?2500:6000;
}
function v117SchedulePoll(delay){
  if(v117PollTimer)clearTimeout(v117PollTimer);
  if(!v117Polling)return;
  v117PollTimer=setTimeout(v117PollNow,Math.max(250,Number(delay)||v117PollDelay()));
}
function v117PollNow(){
  if(!v117Polling||!v117WorkshopVisible())return;
  var result;
  try{result=v103RefreshWorkshop(false)}catch(e){v117MarkStale(e&&e.message?e.message:'Status refresh failed');v117SchedulePoll(1500);return}
  Promise.resolve(result).then(function(){
    if(v117Polling&&v117WorkshopVisible())v117SchedulePoll(v117PollDelay());
  },function(){
    if(v117Polling&&v117WorkshopVisible())v117SchedulePoll(1500);
  });
}
function v117StopWorkshopPolling(){
  v117Polling=false;
  if(v117PollTimer){clearTimeout(v117PollTimer);v117PollTimer=null}
  if(v117WatchdogTimer){clearInterval(v117WatchdogTimer);v117WatchdogTimer=null}
  if(window.v103WorkshopTimer){clearInterval(window.v103WorkshopTimer);window.v103WorkshopTimer=null}
}
function v117StartWorkshopPolling(){
  v117StopWorkshopPolling();
  v117Polling=true;
  if(!v117WorkshopVisible())return;
  if(!v117StateFresh(v116CurrentSlot())){
    v117DisableUiOnly();
    v116SetConnectionState(false,false,'SYNCING');
    v116Set('wkUpdated','Refreshing selected printer…');
  }
  v117WatchdogTimer=setInterval(v117WatchFreshness,1000);
  v117PollNow();
}
function v117HandleVisibility(){
  if(document.visibilityState==='hidden'){
    v117StopWorkshopPolling();
    return;
  }
  var root=document.getElementById('sec-workshop');
  if(root&&!root.hidden)v117StartWorkshopPolling();
}
document.addEventListener('visibilitychange',v117HandleVisibility);
setTimeout(function(){if(v117WorkshopVisible())v117StartWorkshopPolling()},0);


/* ============ Workshop OS RC11 · Printer credentials ============ */
(function(){
  var revealTimer = null;
  function conceal(){
    var v=document.getElementById('wsPrinterAccessValue');
    if(v){ v.textContent='••••••••'; v.dataset.revealed='0'; }
  }
  function credentialCard(){
    var sec=document.getElementById('sec-printer');
    if(!sec || document.getElementById('wsPrinterCredentials')) return;
    var card=document.createElement('div');
    card.id='wsPrinterCredentials'; card.className='card';
    card.innerHTML='<h3>Credentials</h3><div class="hint">LAN Direct credential stored on this Workshop OS device.</div>'+
      '<div class="kv" style="margin-top:12px"><span>Printer Access Code</span><strong id="wsPrinterAccessValue" data-revealed="0">••••••••</strong></div>'+
      '<div class="btn-row" style="margin-top:12px"><button type="button" class="secondary" id="wsRevealAccess">Reveal</button><button type="button" class="secondary" id="wsCopyAccess">Copy</button></div>'+
      '<div class="hint" style="margin-top:10px">Different from the Workshop OS Portal Code. Conceals automatically after 30 seconds.</div>';
    sec.appendChild(card);
    document.getElementById('wsRevealAccess').addEventListener('click',function(){fetchAccess(false);});
    document.getElementById('wsCopyAccess').addEventListener('click',function(){fetchAccess(true);});
  }
  function fetchAccess(copy){
    fetch('/printer/access-code?slot='+encodeURIComponent(typeof currentSlot==='number'?currentSlot:0),{cache:'no-store',credentials:'same-origin'})
      .then(function(r){if(!r.ok) return r.json().catch(function(){return {};}).then(function(d){throw new Error(d.message||'Access code unavailable');}); return r.json();})
      .then(function(d){
        if(!d.accessCode) throw new Error('Access code unavailable');
        var v=document.getElementById('wsPrinterAccessValue'); if(v){v.textContent=d.accessCode;v.dataset.revealed='1';}
        clearTimeout(revealTimer); revealTimer=setTimeout(conceal,30000);
        if(copy && navigator.clipboard && navigator.clipboard.writeText){
          navigator.clipboard.writeText(d.accessCode).then(function(){showToast('Printer access code copied');},function(){showToast('Code revealed — copy it manually');});
        } else if(copy) showToast('Code revealed — copy it manually');
      }).catch(function(e){showToast(e.message||'Access code unavailable');});
  }
  credentialCard();
  var oldLoad=loadSection;
  loadSection=function(id){ if(id!=='printer') conceal(); oldLoad(id); if(id==='printer') credentialCard(); };
})();
