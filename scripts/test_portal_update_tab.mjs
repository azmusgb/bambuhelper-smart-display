#!/usr/bin/env node
// The portal's Online update tab (baseline/files/web/app.js) against a fake display.
// Runs the tab's own functions, cut from app.js, with a scripted fetch: no browser, no device.
//   node --test scripts/test_portal_update_tab.mjs
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { test } from 'node:test';
import { fileURLToPath } from 'node:url';
import vm from 'node:vm';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const source = readFileSync(join(root, 'baseline/files/web/app.js'), 'utf8');
const START = '/* Online-update helpers.';
const END = '/* ============ Reboot / factory reset';
const from = source.indexOf(START);
const to = source.indexOf(END);
assert.ok(from >= 0 && to > from, 'the Online update block is where this test expects it in app.js');
const block = source.slice(from, to);

const reply = (status, body, extra = {}) => ({
  status,
  redirected: false,
  text: async () => (typeof body === 'string' ? body : JSON.stringify(body)),
  ...extra,
});
const state = (over = {}) => ({
  channel: 'Stable', phase: 'Idle', progress: 0, busy: false, updateAvailable: false,
  runningVersion: '12.9.0', availableVersion: '', availableLabel: '', status: '', ...over,
});

function portal({ confirm = true } = {}) {
  const elements = {};
  const el = (id) => (elements[id] ??= { id, style: {}, textContent: '', disabled: false, setAttribute() {} });
  const queue = [];
  const calls = [];
  const timers = [];
  const rebootWaits = [];
  const context = vm.createContext({
    document: { getElementById: el },
    console: { warn() {} },
    confirm: () => confirm,
    setInterval: (fn) => { timers.push(fn); return timers.length; },
    clearInterval: (id) => { timers[id - 1] = null; },
    waitForReboot: (st) => { rebootWaits.push(st); },
    fetch: async (path, options = {}) => {
      calls.push(`${options.method || 'GET'} ${path}`);
      assert.ok(queue.length, `unexpected request: ${path}`);
      const next = queue.shift();
      if (next instanceof Error) throw next;
      return next;
    },
  });
  vm.runInContext(block, context);
  const settle = async () => { for (let i = 0; i < 8; i++) await new Promise((r) => setImmediate(r)); };
  return {
    el, calls, rebootWaits,
    answer: (...replies) => queue.push(...replies),
    async run(name) { context[name](); await settle(); },
    // One turn of the status poll, as the page's one-second timer would fire it.
    async tick() { const fn = timers.findLast((t) => t); assert.ok(fn, 'the status poll is running'); fn(); await settle(); },
    polling: () => timers.some((t) => t),
  };
}

test('up to date: says so with the running version and frees the buttons', async () => {
  const p = portal();
  p.answer(reply(202, state({ phase: 'Checking', busy: true, status: 'Checking the update server manifest…' })));
  await p.run('checkForUpdates');
  assert.equal(p.el('checkUpdateBtn').disabled, true);
  assert.equal(p.el('updateResult').textContent, 'Checking the update server manifest…');
  p.answer(reply(200, state({ status: 'Workshop OS is up to date on this channel.' })));
  await p.tick();
  assert.equal(p.el('updateResult').textContent, 'Workshop OS is up to date on this channel. Running 12.9.0.');
  assert.equal(p.el('updateResult').style.color, 'var(--success)');
  assert.equal(p.el('updateInfo').style.display, 'none');
  assert.equal(p.el('checkUpdateBtn').disabled, false);
  assert.equal(p.polling(), false);
  assert.deepEqual(p.calls, ['POST /os12/update/check', 'GET /os12/update/status']);
});

test('update available, then the display refuses the install during a print', async () => {
  const p = portal();
  const available = state({
    phase: 'Available', updateAvailable: true, availableVersion: '12.9.1',
    availableLabel: 'Workshop OS 12.9.1', status: 'A newer OTA image is available.',
  });
  p.answer(reply(202, state({ phase: 'Checking', busy: true })));
  await p.run('checkForUpdates');
  p.answer(reply(200, available));
  await p.tick();
  assert.equal(p.el('updateVer').textContent, 'Workshop OS 12.9.1');
  assert.equal(p.el('updateChannel').textContent, 'Stable channel · running 12.9.0');
  assert.equal(p.el('updateInfo').style.display, 'block');
  assert.equal(p.el('updateResult').style.color, 'var(--warn)');

  p.answer(reply(409, { ...available, status: 'A print is running. Install after it finishes.' }));
  await p.run('installUpdate');
  assert.equal(p.el('updateResult').textContent, 'A print is running. Install after it finishes.');
  assert.equal(p.el('updateResult').style.color, 'var(--danger)');
  assert.equal(p.el('autoOtaWrap').style.display, 'none');
  assert.equal(p.el('updateInfo').style.display, 'block', 'the offer stays so it can be tried again');
  assert.equal(p.el('installBtn').disabled, false);
  assert.equal(p.el('installBtn').textContent, 'Install update');
  assert.equal(p.polling(), false);
});

test('install runs through to the restart', async () => {
  const p = portal();
  const offer = { updateAvailable: true, availableVersion: '12.9.1', availableLabel: 'Workshop OS 12.9.1' };
  p.el('updateVer').textContent = 'Workshop OS 12.9.1';
  p.answer(reply(202, state({ ...offer, phase: 'Downloading', busy: true, status: 'Starting verified OTA download…' })));
  await p.run('installUpdate');
  assert.equal(p.el('installBtn').disabled, true);
  assert.equal(p.el('installBtn').textContent, 'Installing...');
  assert.equal(p.el('autoOtaWrap').style.display, 'block');
  p.answer(reply(200, state({ ...offer, phase: 'Verifying', busy: true, progress: 60, status: 'Verifying SHA-256…' })));
  await p.tick();
  assert.equal(p.el('autoOtaBar').style.width, '60%');
  assert.equal(p.el('autoOtaStatus').textContent, 'Verifying SHA-256… (60%)');
  p.answer(reply(200, state({ ...offer, phase: 'Restarting', busy: true, progress: 100, status: 'Restarting Workshop OS…' })));
  await p.tick();
  assert.equal(p.el('autoOtaBar').style.width, '100%');
  assert.equal(p.rebootWaits.length, 1);
  assert.equal(p.polling(), false);
});

test('a failed install (SHA mismatch) shows the reason and hides the progress bar', async () => {
  const p = portal();
  p.answer(reply(202, state({ phase: 'Downloading', busy: true, updateAvailable: true })));
  await p.run('installUpdate');
  p.answer(reply(200, state({ phase: 'Failed', status: 'SHA-256 mismatch. The running version is unchanged.' })));
  await p.tick();
  assert.equal(p.el('updateResult').textContent, 'SHA-256 mismatch. The running version is unchanged.');
  assert.equal(p.el('updateResult').style.color, 'var(--danger)');
  assert.equal(p.el('autoOtaWrap').style.display, 'none');
  assert.equal(p.el('installBtn').disabled, false);
  assert.equal(p.rebootWaits.length, 0);
});

test('replies that are not the update state each get a plain message', async () => {
  const cases = [
    [reply(404, 'Not found: /os12/update/check'), 'Check failed: The display answered HTTP 404.'],
    [reply(401, { status: 'error', message: 'Sign in to Workshop OS with the code shown on the display.', signIn: '/login' }),
      'Check failed: Sign in to Workshop OS with the code shown on the display.'],
    [reply(403, { status: 'error', message: 'Rejected by Workshop OS same-origin protection.' }),
      'Check failed: Rejected by Workshop OS same-origin protection.'],
    [reply(200, '<!doctype html><title>Sign in</title>', { redirected: true }), 'Check failed: Sign in again to manage updates.'],
    [new Error('NetworkError when attempting to fetch resource.'), 'Check failed: NetworkError when attempting to fetch resource.'],
  ];
  for (const [answer, message] of cases) {
    const p = portal();
    p.answer(answer);
    await p.run('checkForUpdates');
    assert.equal(p.el('updateResult').textContent, message);
    assert.equal(p.el('updateResult').style.color, 'var(--danger)');
    assert.equal(p.el('checkUpdateBtn').disabled, false);
    assert.equal(p.polling(), false);
  }
});

test('a cancelled confirmation sends nothing', async () => {
  const p = portal({ confirm: false });
  await p.run('installUpdate');
  assert.deepEqual(p.calls, []);
  assert.equal(p.polling(), false);
});

test('the display going quiet after 90% is the restart, not a failure', async () => {
  const p = portal();
  p.answer(reply(202, state({ phase: 'Downloading', busy: true, updateAvailable: true })));
  await p.run('installUpdate');
  p.answer(reply(200, state({ phase: 'Installing', busy: true, updateAvailable: true, progress: 95 })));
  await p.tick();
  p.answer(new Error('connection reset'));
  await p.tick();
  assert.equal(p.rebootWaits.length, 1);
  assert.equal(p.polling(), false);
});

test('ten missed status replies during a check end it with the reason', async () => {
  const p = portal();
  p.answer(reply(202, state({ phase: 'Checking', busy: true })));
  await p.run('checkForUpdates');
  for (let i = 0; i < 9; i++) { p.answer(new Error('timeout')); await p.tick(); }
  assert.equal(p.polling(), true);
  p.answer(new Error('timeout'));
  await p.tick();
  assert.equal(p.el('updateResult').textContent, 'Lost contact with the display: timeout');
  assert.equal(p.el('checkUpdateBtn').disabled, false);
  assert.equal(p.polling(), false);
});
