#!/usr/bin/env python3
"""Validate the accepted static installer, its retained firmware and the device update manifest.

Run after build.py, which publishes dist/.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    r = json.loads((ROOT / 'release.json').read_text(encoding='utf-8'))
    assert r['release'] == 'production-workshop-os-12.7.1'
    assert r['board']['id'] == 'ws_lcd_350'
    assert set(r['profiles']) == {'workshop-os-12.7.1', 'workshop-os-12.4.4', 'workshop-os-v11.19.1', 'smart-home-v7.2'}
    assert r['profiles']['workshop-os-12.7.1']['recommended'] is True
    assert r['profiles']['workshop-os-12.4.4']['recommended'] is False
    assert r['profiles']['workshop-os-v11.19.1']['recommended'] is False
    assert r['profiles']['smart-home-v7.2']['recommended'] is False
    for pid, p in r['profiles'].items():
        for path_key, size_key, sha_key in [('file', 'size', 'sha256'), ('otaFile', 'otaSize', 'otaSha256')]:
            raw = (ROOT / p[path_key]).read_bytes()
            assert len(raw) == p[size_key], (pid, path_key, len(raw), p[size_key])
            assert hashlib.sha256(raw).hexdigest() == p[sha_key], (pid, path_key)
            assert sha256(ROOT / 'dist' / p[path_key]) == p[sha_key], (pid, path_key, 'dist')

    d = json.loads((ROOT / 'releases/device-update.json').read_text(encoding='utf-8'))
    assert d['schemaVersion'] == 1
    assert d['board'] == 'ws_lcd_350'
    assert d['authority'] == 'azmusgb/bambuhelper-smart-display'
    assert d['artifactBaseUrl'] == 'https://updates.home.arpa/'
    stable = d['channels']['stable']
    assert stable['status'] == 'published'
    assert stable['release'] == r['release']
    static = r['profiles']['workshop-os-12.7.1']
    assert stable['ota']['path'] == static['otaFile']
    assert stable['ota']['size'] == static['otaSize']
    assert stable['ota']['sha256'] == static['otaSha256']
    assert stable['fullFlash']['path'] == static['file']
    assert stable['fullFlash']['size'] == static['size']
    assert stable['fullFlash']['sha256'] == static['sha256']
    assert stable['fullFlash']['flashOffset'] == '0x0'
    assert stable['fullFlash']['deviceInstallAllowed'] is False
    for kind in ('ota', 'fullFlash'):
        meta = stable[kind]
        raw = (ROOT / meta['path']).read_bytes()
        assert len(raw) == meta['size'], ('device-update', kind, 'size')
        assert hashlib.sha256(raw).hexdigest() == meta['sha256'], ('device-update', kind, 'sha256')
    candidate = d['channels']['candidate']
    assert candidate['status'] in {'none-published', 'published'}
    if candidate['status'] == 'published':
        assert candidate['ota'] is not None
        raw = (ROOT / candidate['ota']['path']).read_bytes()
        assert len(raw) == candidate['ota']['size'], ('candidate', 'size')
        assert hashlib.sha256(raw).hexdigest() == candidate['ota']['sha256'], ('candidate', 'sha256')
    else:
        assert candidate['ota'] is None
    assert d['rules']['normalDeviceUpdateUsesOtaOnly'] is True
    assert d['rules']['verifySizeBeforeInstall'] is True
    assert d['rules']['verifySha256BeforeInstall'] is True
    assert d['rules']['fullFlashRequiresRecoveryFlow'] is True

    assert len(list((ROOT / 'firmware').glob('*.bin'))) == 8
    assert len(list((ROOT / 'dist' / 'firmware').glob('*.bin'))) == 8

    app = (ROOT / 'app.js').read_text(encoding='utf-8')
    index = (ROOT / 'index.html').read_text(encoding='utf-8')
    for needle in ("EXPECTED_RELEASE='production-workshop-os-12.7.1'", "selectedProfile='workshop-os-12.7.1'"):
        assert needle in app, ('app.js', needle)
    for needle in ('Workshop OS 12.7.1 — recommended', 'Workshop OS 12.4.4 — rollback',
                   'Smart Home v7.2 — older rollback', 'Workshop OS 12.7.1 OTA'):
        assert needle in index, ('index.html', needle)
    print('Accepted static installer, device update manifest and portal contract: PASS')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
