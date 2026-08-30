// app.js – improved version
const EXPECTED_RELEASE = 'production-rc-v7.2';
const MAX_SERIAL_LENGTH = 180000;          // limit serial output length
const ANALYZE_DEBOUNCE_MS = 250;           // debounce serial analysis
const SOURCE_COMMIT = '8cb1cbbb6d3c175af91989e8ebe1bbdcbe848ac4';

// Global state (mutable)
let release = null;
let selectedProfile = 'smart-home-v7.2';
let assetVerified = false;
let otaVerified = false;
let hardwareConfirmed = false;
let usbChecked = false;
let manifestUrl = null;
let serialPort = null;
let serialReader = null;
let lastAnalysis = null;
let analyzeTimeout = null;                 // debounce timer

// Helper: query selector
const $ = (id) => document.getElementById(id);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// Update state badge
function setState(id, text, kind = '') {
    const el = $(id);
    if (!el) return;
    el.textContent = text;
    el.className = 'state' + (kind ? ' ' + kind : '');
}

// Update readiness indicator (class-based)
function markReady(id, yes, kind = 'ready') {
    const el = $(id);
    if (!el) return;
    el.classList.remove('ready', 'warn', 'bad');
    if (yes) el.classList.add(kind);
}

// Format bytes
const fmtBytes = (n) => Number(n).toLocaleString() + ' bytes';

// Trigger file download from text
function download(name, text) {
    const blob = new Blob([text], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = name;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
}

// Compute SHA-256 of an ArrayBuffer
async function sha256Buffer(buf) {
    const digest = await crypto.subtle.digest('SHA-256', buf);
    return [...new Uint8Array(digest)]
        .map((b) => b.toString(16).padStart(2, '0'))
        .join('');
}

// Get currently selected profile object
const profile = () => release?.profiles?.[selectedProfile];

// Load release manifest and verify assets
async function loadRelease() {
    const resp = await fetch('release.json', { cache: 'no-store' });
    if (!resp.ok) throw new Error('release.json HTTP ' + resp.status);
    const data = await resp.json();
    if (data.release !== EXPECTED_RELEASE || data.board.id !== 'ws_lcd_350') {
        throw new Error('unexpected release metadata');
    }
    release = data;
    $('release-pill').textContent = 'RC v7.2 · ' + data.board.id;
    renderProfile();
    await Promise.all([verifyAsset(), verifyOtaAsset()]);
}

// Update profile summary in UI
function renderProfile() {
    const p = profile();
    if (!p) return;
    $('profile-title').textContent = p.label;
    $('profile-description').textContent = p.description;
    $('prov-version').textContent = p.version;
    $('prov-file').textContent = p.file;
    $('prov-size').textContent = fmtBytes(p.size);
    $('prov-sha').textContent = p.sha256;
    $('prov-verified').textContent = assetVerified ? 'Verified in this browser' : 'Pending';
    renderOta();
    updateReadiness();
}

// Verify full firmware image
async function verifyAsset() {
    assetVerified = false;
    setState('integrity-state', 'CHECKING', 'warn');
    $('integrity-detail').textContent = 'Fetching and hashing selected firmware…';
    try {
        const p = profile();
        const resp = await fetch(p.file, { cache: 'no-store' });
        if (!resp.ok) throw new Error('firmware HTTP ' + resp.status);
        const buf = await resp.arrayBuffer();
        if (buf.byteLength !== p.size) throw new Error('size mismatch');
        const actual = await sha256Buffer(buf);
        if (actual.toLowerCase() !== p.sha256.toLowerCase()) throw new Error('SHA-256 mismatch');
        assetVerified = true;
        setState('integrity-state', 'VERIFIED', 'ok');
        $('integrity-detail').textContent = 'Firmware verified locally in this browser.';
    } catch (e) {
        assetVerified = false;
        setState('integrity-state', 'FAILED', 'bad');
        $('integrity-detail').textContent = 'Integrity verification failed: ' + e.message;
    }
    renderProfile();
}

// Render OTA panel
function renderOta() {
    const p = profile();
    const panel = $('ota-panel');
    const btn = $('ota-download');
    const meta = $('ota-meta');
    const status = $('ota-status');
    if (!panel || !btn || !meta || !status) return;
    if (!p?.otaFile) {
        panel.hidden = true;
        otaVerified = false;
        return;
    }
    panel.hidden = false;
    meta.textContent = fmtBytes(p.otaSize) + ' · SHA-256 ' + p.otaSha256;
    status.textContent = otaVerified
        ? 'OTA application image verified in this browser. Safe to download for manual Wi-Fi update.'
        : 'OTA image verification pending.';
    btn.href = otaVerified ? new URL(p.otaFile, location.href).href : '#';
    btn.classList.toggle('disabled', !otaVerified);
    btn.setAttribute('aria-disabled', otaVerified ? 'false' : 'true');
    setState('ota-state', otaVerified ? 'VERIFIED' : 'PENDING', otaVerified ? 'ok' : 'warn');
}

// Verify OTA image
async function verifyOtaAsset() {
    otaVerified = false;
    const p = profile();
    if (!p?.otaFile) {
        renderOta();
        return;
    }
    setState('ota-state', 'CHECKING', 'warn');
    $('ota-status').textContent = 'Fetching and hashing the OTA application image…';
    try {
        const resp = await fetch(p.otaFile, { cache: 'no-store' });
        if (!resp.ok) throw new Error('OTA HTTP ' + resp.status);
        const buf = await resp.arrayBuffer();
        if (buf.byteLength !== p.otaSize) throw new Error('OTA size mismatch');
        const actual = await sha256Buffer(buf);
        if (actual.toLowerCase() !== p.otaSha256.toLowerCase()) throw new Error('OTA SHA-256 mismatch');
        otaVerified = true;
        setState('ota-state', 'VERIFIED', 'ok');
        $('ota-status').textContent = 'OTA application image verified in this browser. Safe to download for manual Wi-Fi update.';
    } catch (e) {
        otaVerified = false;
        setState('ota-state', 'FAILED', 'bad');
        $('ota-status').textContent = 'OTA verification failed: ' + e.message;
    }
    renderOta();
}

// Build ESP Web Tools manifest object
function buildManifest() {
    const p = profile();
    return {
        name: selectedProfile.startsWith('smart-home') ? 'BambuHelper Smart Home' : 'BambuHelper Smart Display',
        version: p.version,
        new_install_prompt_erase: true,
        new_install_improv_wait_time: 15,
        builds: [{
            chipFamily: 'ESP32-S3',
            parts: [{ path: new URL(p.file, location.href).href, offset: 0 }]
        }]
    };
}

// Render install button (or placeholder)
function renderInstall() {
    const slot = $('install-slot');
    slot.innerHTML = '';
    const canInstall = hardwareConfirmed && assetVerified && ('serial' in navigator) && window.isSecureContext && !serialPort;
    if (!canInstall) {
        const div = document.createElement('div');
        div.className = 'install-placeholder';
        div.textContent = serialPort
            ? 'Disconnect Diagnostics before installing.'
            : 'Complete required checks to enable Install.';
        slot.appendChild(div);
        setState('install-state', 'LOCKED', 'warn');
        return;
    }
    if (manifestUrl) URL.revokeObjectURL(manifestUrl);
    manifestUrl = URL.createObjectURL(new Blob([JSON.stringify(buildManifest())], { type: 'application/json' }));
    const button = document.createElement('esp-web-install-button');
    button.setAttribute('manifest', manifestUrl);
    const unsupported = document.createElement('span');
    unsupported.slot = 'unsupported';
    unsupported.textContent = 'Use desktop Chrome or Edge.';
    button.appendChild(unsupported);
    slot.appendChild(button);
    setState('install-state', 'READY', 'ok');
}

// Update overall readiness indicators and install button
function updateReadiness() {
    const hasSerial = 'serial' in navigator;
    const secure = window.isSecureContext;
    markReady('ready-browser', hasSerial, hasSerial ? 'ready' : 'bad');
    markReady('ready-secure', secure, secure ? 'ready' : 'bad');
    markReady('ready-hardware', hardwareConfirmed);
    markReady('ready-firmware', assetVerified);
    markReady('ready-usb', usbChecked);
    $('browser-pill').textContent = hasSerial && secure
        ? 'Browser ready'
        : 'Desktop Chrome/Edge + HTTPS required';
    renderInstall();
    syncSteps();
}

// Check USB permission (optional preflight)
async function checkUsb() {
    if (!('serial' in navigator)) return;
    try {
        const port = await navigator.serial.requestPort();
        const info = port.getInfo ? port.getInfo() : {};
        usbChecked = true;
        markReady('ready-usb', true);
        $('ready-usb').querySelector('small').textContent =
            info.usbVendorId != null
                ? 'VID ' + info.usbVendorId.toString(16).padStart(4, '0') +
                  ' · PID ' + (info.usbProductId || 0).toString(16).padStart(4, '0')
                : 'Permission granted';
    } catch (e) {
        if (e.name !== 'NotFoundError') {
            $('ready-usb').querySelector('small').textContent = e.message;
        }
    }
    updateReadiness();
}

// Normalize an address input to a valid URL with protocol
function normalizeAddress(v) {
    v = String(v || '').trim();
    if (!v) return '';
    if (!/^https?:\/\//i.test(v)) v = 'http://' + v;
    try {
        const u = new URL(v);
        return u.protocol + '//' + u.host;
    } catch {
        return '';
    }
}

// Check if IP is private IPv4
function privateIp(ip) {
    const parts = ip.split('.').map(Number);
    if (parts.length !== 4 || parts.some((n) => !Number.isInteger(n) || n < 0 || n > 255)) return false;
    return parts[0] === 10 ||
           (parts[0] === 192 && parts[1] === 168) ||
           (parts[0] === 172 && parts[1] >= 16 && parts[1] <= 31);
}

// Improved IP finder: look for private IPs that appear after "ip:" or "address" or in known patterns
function findIps(text) {
    const candidates = [];
    const lines = text.split(/\r?\n/);
    for (const line of lines) {
        // Prefer explicit mentions like "ip: 192.168.x.x" or "address: ..."
        const match = line.match(/\b(?:ip|address|staip|ipv4|local ip)\s*[:=]\s*(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})/i);
        if (match && privateIp(match[1])) {
            candidates.push({ ip: match[1], line });
            continue;
        }
        // Fallback to any private IP in line
        const ips = line.match(/\b(?:\d{1,3}\.){3}\d{1,3}\b/g) || [];
        for (const ip of ips) {
            if (privateIp(ip) && ip !== '192.168.4.1') {
                candidates.push({ ip, line });
                break; // only first private IP per line unless explicit earlier
            }
        }
    }
    return candidates;
}

// Redact sensitive information
function redact(line) {
    return String(line)
        .replace(/(password|pass|token|authorization|access[_ -]?code|api[_ -]?key|secret|ssid)\s*[:=]\s*\S+/ig, '$1=[redacted]')
        .replace(/[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/ig, '[email redacted]');
}

// Update a signal indicator
function signal(id, state, detail) {
    const el = $(id);
    el.className = 'signal-' + state;
    el.querySelector('small').textContent = detail;
}

// Analyze serial output (debounced)
function analyzeSerial() {
    if (analyzeTimeout) clearTimeout(analyzeTimeout);
    analyzeTimeout = setTimeout(() => {
        analyzeTimeout = null;
        analyzeSerialNow();
    }, ANALYZE_DEBOUNCE_MS);
}

// Immediate analysis
function analyzeSerialNow() {
    const text = $('serial-output').textContent || '';
    const ips = findIps(text);
    const normal = ips.find((x) => x.ip !== '192.168.4.1');
    const boot = /bambuhelper|firmware.*v?\d+\.\d+|\bboot(?:ing|ed)?\b/i.test(text);
    const wifiFail = /(wi-?fi|wlan|sta).{0,70}(failed|failure|timeout|timed out|auth|disconnect|no ssid|not found)/i.test(text);
    const wifiOk = /(wi-?fi|wlan|sta|station).{0,60}(connected|got ip|online)/i.test(text) || !!normal;
    const fallback = /192\.168\.4\.1|bambuhelper-[a-f0-9]{4}|fallback.{0,20}(ap|hotspot)|ap mode/i.test(text);
    const crash = /guru meditation|brownout|stack canary|fatal exception|panic'ed|abort\(\)|assert failed/i.test(text);
    const crashCount = (text.match(/guru meditation|panic(?:'ed)?|stack canary|fatal exception|assert failed|abort\(\)/gi) || []).length;
    const resetCount = (text.match(/\brst:0x[0-9a-f]+/gi) || []).length;
    const brownout = /brownout/i.test(text);

    lastAnalysis = {
        boot, wifiFail, wifiOk, fallback, crash, crashCount, resetCount, brownout,
        normalIp: normal?.ip || '',
        evidence: text.split(/\r?\n/).filter((l) =>
            /bambuhelper|boot|wi-?fi|got ip|local ip|mqtt|cloud|guru|brownout|panic|fatal|assert/i.test(l)
        ).slice(-20).map(redact)
    };

    signal('sig-boot', boot ? 'ok' : 'warn', boot ? 'BambuHelper startup observed' : 'No conclusive boot evidence');
    signal('sig-wifi', wifiFail ? 'bad' : wifiOk ? 'ok' : fallback ? 'warn' : 'warn',
        wifiFail ? 'Wi‑Fi failure observed' : wifiOk ? 'Normal network evidence' : fallback ? 'Fallback setup mode' : 'No network evidence');
    signal('sig-ip', normal ? 'ok' : fallback ? 'warn' : 'warn',
        normal ? 'LAN ' + normal.ip : fallback ? 'Only fallback 192.168.4.1' : 'No normal LAN IP');
    signal('sig-health', crash ? 'bad' : boot ? 'ok' : 'warn',
        crash ? 'Crash/power signature observed' : boot ? 'No severe crash signature' : 'Waiting for startup evidence');

    if (normal) {
        $('device-address').value = 'http://' + normal.ip;
        $('device-status').textContent = 'Detected normal LAN address from serial output.';
        setState('handoff-state', 'DEVICE FOUND', 'ok');
    } else if (wifiFail) {
        setState('handoff-state', 'WIFI ISSUE', 'bad');
    } else if (fallback) {
        setState('handoff-state', 'SETUP AP', 'warn');
    } else if (boot) {
        setState('handoff-state', 'BOOTED', 'ok');
    } else {
        setState('handoff-state', 'WAITING', 'warn');
    }

    evaluateRecovery();
    syncSteps();
}

// Recovery recommendation
function evaluateRecovery() {
    const a = lastAnalysis || {};
    let code = 'CAPTURE FIRST';
    let title = 'Capture a boot before changing firmware';
    let copy = 'Preserve evidence before erasing or reflashing.';

    if (a.brownout) {
        code = 'CHECK POWER';
        title = 'Brownout evidence points to USB/power';
        copy = 'Try a known-good cable/power source before reflashing.';
    } else if (a.crashCount >= 2 && a.resetCount >= 2) {
        code = 'REFLASH CANDIDATE';
        title = 'Repeated crash/reset evidence supports recovery flash';
        copy = 'Export support first, then use BOOT/RST and reinstall the verified Full image.';
    } else if (a.crash) {
        code = 'RETRY FIRST';
        title = 'One crash is not enough to erase evidence';
        copy = 'Power-cycle once and confirm whether the severe failure repeats.';
    } else if (a.wifiFail) {
        code = 'REPROVISION WIFI';
        title = 'Firmware is running; repair Wi‑Fi';
        copy = 'Use Improv or fallback AP; do not reflash for credentials/network.';
    } else if (a.fallback && !a.normalIp) {
        code = 'FINISH WIFI';
        title = 'Device is in setup mode';
        copy = 'Complete normal Wi‑Fi provisioning instead of reflashing.';
    } else if (a.boot && a.normalIp) {
        code = 'NO REFLASH';
        title = 'BambuHelper booted and joined the LAN';
        copy = 'Continue device/X2D configuration.';
    } else if (a.boot) {
        code = 'WAIT FOR WIFI';
        title = 'BambuHelper appears to be booting';
        copy = 'Keep Diagnostics connected while networking settles.';
    }

    setState('recovery-state', code,
        code === 'NO REFLASH' ? 'ok' : code === 'REFLASH CANDIDATE' ? 'bad' : 'warn');
    $('recovery-title').textContent = title;
    $('recovery-copy').textContent = copy;
}

// Serial connection management
async function serialConnect() {
    if (!('serial' in navigator) || serialPort) return;
    try {
        serialPort = await navigator.serial.requestPort();
        await serialPort.open({ baudRate: 115200 });
    } catch (e) {
        if (e.name !== 'NotFoundError') {
            $('device-status').textContent = 'Serial open failed: ' + e.message;
        }
        serialPort = null;
        return;
    }
    $('serial-connect').disabled = true;
    $('serial-disconnect').disabled = false;
    renderInstall();
    serialRead();
}

async function serialRead() {
    const decoder = new TextDecoder();
    try {
        if (!serialPort?.readable) return;
        serialReader = serialPort.readable.getReader();
        while (true) {
            const { value, done } = await serialReader.read();
            if (done) break;
            if (value) {
                const out = $('serial-output');
                out.textContent += decoder.decode(value, { stream: true });
                if (out.textContent.length > MAX_SERIAL_LENGTH) {
                    out.textContent = out.textContent.slice(-MAX_SERIAL_LENGTH * 0.75);
                }
                out.scrollTop = out.scrollHeight;
                analyzeSerial();   // debounced
            }
        }
    } finally {
        if (serialReader) {
            try { serialReader.releaseLock(); } catch {}
            serialReader = null;
        }
    }
}

async function serialDisconnect() {
    if (serialReader) {
        try { await serialReader.cancel(); } catch {}
    }
    await sleep(50);
    if (serialPort) {
        try { await serialPort.close(); } catch {}
    }
    serialPort = null;
    $('serial-connect').disabled = false;
    $('serial-disconnect').disabled = true;
    renderInstall();
}

// Commission tracking
function syncCommission() {
    const checks = [...document.querySelectorAll('[data-commission]')];
    const done = checks.filter((x) => x.checked).length;
    setState('commission-state', done + ' / ' + checks.length, done === checks.length ? 'ok' : '');
    syncSteps();
}

// Sync step navigation indicators
function syncSteps() {
    const checks = [...document.querySelectorAll('[data-commission]')];
    const map = [
        ['step-hardware', hardwareConfirmed],
        ['step-firmware', assetVerified],
        ['step-install', hardwareConfirmed && assetVerified],
        ['step-network', $('check-wifi').checked],
        ['step-device', !!normalizeAddress($('device-address').value)],
        ['step-printer', $('check-printer').checked],
        ['step-verify', checks.length && checks.every((x) => x.checked)]
    ];
    let active = false;
    for (const [id, done] of map) {
        const el = $(id);
        el.classList.toggle('done', !!done);
        el.classList.remove('active');
        if (!done && !active) {
            el.classList.add('active');
            active = true;
        }
    }
}

// Export functions
function receipt() {
    const p = profile();
    const checks = [...document.querySelectorAll('[data-commission]')];
    return [
        'BambuHelper Smart Display commissioning receipt',
        '==============================================',
        'timestamp: ' + new Date().toISOString(),
        'board: ws_lcd_350',
        'profile: ' + selectedProfile,
        'version: ' + p.version,
        'firmware: ' + p.file,
        'sha256: ' + p.sha256,
        'browser_integrity_verified: ' + (assetVerified ? 'yes' : 'no'),
        'ota_sha256: ' + (p.otaSha256 || 'n/a'),
        'ota_browser_verified: ' + (otaVerified ? 'yes' : 'no'),
        'hardware_confirmed: ' + (hardwareConfirmed ? 'yes' : 'no'),
        'wifi_joined: ' + ($('check-wifi').checked ? 'yes' : 'no'),
        'x2d_telemetry: ' + ($('check-printer').checked ? 'yes' : 'no'),
        ...checks.map((x) => x.id + ': ' + (x.checked ? 'PASS' : 'NOT CONFIRMED')),
        ''
    ].join('\n');
}

function supportBundle() {
    const p = profile();
    const a = lastAnalysis || { evidence: [] };
    return [
        'BambuHelper Smart Display support bundle',
        '=======================================',
        'timestamp: ' + new Date().toISOString(),
        'release: production-rc-v7.2',
        'source_commit: ' + SOURCE_COMMIT,
        'board: ws_lcd_350',
        'profile: ' + selectedProfile,
        'version: ' + p.version,
        'firmware_sha256: ' + p.sha256,
        'browser_integrity_verified: ' + (assetVerified ? 'yes' : 'no'),
        'ota_sha256: ' + (p.otaSha256 || 'n/a'),
        'ota_browser_verified: ' + (otaVerified ? 'yes' : 'no'),
        'web_serial: ' + (('serial' in navigator) ? 'yes' : 'no'),
        'secure_context: ' + (window.isSecureContext ? 'yes' : 'no'),
        'recovery_state: ' + $('recovery-state').textContent,
        '',
        'Redacted evidence',
        '-----------------',
        ...(a.evidence || []),
        '',
        'Redacted serial log',
        '-------------------',
        redact($('serial-output').textContent || ''),
        ''
    ].join('\n');
}

// Event listeners
function initEvents() {
    $('hardware-confirm').addEventListener('change', (e) => {
        hardwareConfirmed = e.target.checked;
        setState('hardware-state', hardwareConfirmed ? 'CONFIRMED' : 'REQUIRED', hardwareConfirmed ? 'ok' : 'warn');
        updateReadiness();
    });

    $('profile').addEventListener('change', async (e) => {
        selectedProfile = e.target.value;
        otaVerified = false;
        await Promise.all([verifyAsset(), verifyOtaAsset()]);
    });

    $('verify-asset').addEventListener('click', verifyAsset);
    $('verify-ota').addEventListener('click', verifyOtaAsset);

    $('ota-download').addEventListener('click', (e) => {
        if (!otaVerified) e.preventDefault();
    });

    $('check-usb').addEventListener('click', checkUsb);

    $('check-wifi').addEventListener('change', syncSteps);
    $('check-printer').addEventListener('change', syncSteps);

    $('find-ip').addEventListener('click', () => analyzeSerialNow());

    $('open-device').addEventListener('click', () => {
        const addr = normalizeAddress($('device-address').value);
        if (addr) {
            window.open(addr, '_blank', 'noopener,noreferrer');
        } else {
            $('device-status').textContent = 'Enter or detect a valid device address first.';
        }
    });

    $('copy-address').addEventListener('click', async () => {
        const addr = normalizeAddress($('device-address').value);
        if (!addr) return;
        try {
            await navigator.clipboard.writeText(addr);
            $('device-status').textContent = 'Address copied.';
        } catch {
            $('device-address').select();
        }
    });

    $('device-address').addEventListener('change', syncSteps);

    document.querySelectorAll('[data-commission]').forEach((el) =>
        el.addEventListener('change', syncCommission)
    );

    $('serial-connect').addEventListener('click', serialConnect);
    $('serial-disconnect').addEventListener('click', serialDisconnect);

    $('serial-clear').addEventListener('click', () => {
        $('serial-output').textContent = '';
        lastAnalysis = null;
        analyzeSerialNow();
    });

    $('export-receipt').addEventListener('click', () =>
        download('bambuhelper-commissioning.txt', receipt())
    );

    $('export-support').addEventListener('click', () =>
        download('bambuhelper-support.txt', supportBundle())
    );
}

// Initialization
async function init() {
    initEvents();
    updateReadiness();
    syncCommission();
    try {
        await loadRelease();
    } catch (e) {
        setState('integrity-state', 'FAILED', 'bad');
        $('integrity-detail').textContent = 'Could not load release metadata: ' + e.message;
    }
}

init();