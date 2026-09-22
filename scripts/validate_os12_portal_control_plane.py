#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path


class ValidationError(RuntimeError):
    pass


def need(text:str, needle:str, label:str) -> None:
    if needle not in text:
        raise ValidationError(f"missing {label}: {needle}")


def forbid(text:str, needle:str, label:str) -> None:
    if needle in text:
        raise ValidationError(f"forbidden {label}: {needle}")


def main() -> int:
    ap=argparse.ArgumentParser()
    ap.add_argument('--repo',required=True)
    ap.add_argument('--contract',required=True)
    args=ap.parse_args()
    root=Path(args.repo).resolve()
    contract=Path(args.contract).resolve()

    html=(root/'include/web_pages.h').read_text(encoding='utf-8')
    js=(root/'web/app.js').read_text(encoding='utf-8')
    css=(root/'web/app.css').read_text(encoding='utf-8')
    sec=(root/'src/security_manager.cpp').read_text(encoding='utf-8')
    sech=(root/'include/security_manager.h').read_text(encoding='utf-8')
    web=(root/'src/web_server.cpp').read_text(encoding='utf-8')
    build=(root/'include/smart_home_build.h').read_text(encoding='utf-8')

    for needle in ('<title>Workshop OS</title>','portal-nav-mark">OS','Workshop OS 12.0.0','WS350 · local control plane'):
        need(html,needle,'Workshop OS identity')
    for stale in ('<title>Waveshare Home</title>','<div class="mark">WH</div>','BambuHelper v3.8.1 engine'):
        forbid(html,stale,'legacy primary identity')

    for section in ('data-section="home"','data-section="printer"','data-section="workshop"','data-section="more"'):
        need(html,section,'primary IA')
    primary_sidebar=html[html.find('<aside class="sidebar"'):html.find('</aside>',html.find('<aside class="sidebar"'))]
    for child in ('data-section="errors"','data-section="display"','data-section="hardware"','data-section="wifi"','data-section="power"','data-section="diag"','data-section="advanced"'):
        forbid(primary_sidebar,child,'secondary destination in root sidebar')
    need(html,'id="sec-more"','More destination')
    need(js,"more: 'More'",'More registry entry')

    for marker in ('No authoritative Filament Inventory evidence','Canonical placement unavailable','Print requirements unavailable','Filament Inventory is the source of truth.','printer are telemetry only'):
        need(html,marker,'inventory truth boundary')
    for risky in ('ACTIVE MATERIAL','Waiting for AMS / external spool data'):
        forbid(html,risky,'authoritative-looking printer telemetry')

    forbid(html,'id="cl_passWrap" style="display:none" style="display:none"','duplicate style attribute')
    if '<label class="check-row"' in html and '<label for=' in html:
        import re
        nested=re.search(r'<label class="check-row"[^>]*>\s*<input[^>]*>\s*<label\s+for=',html,re.S)
        if nested:
            raise ValidationError('nested label remains in check-row markup')

    for marker in ('Workshop OS 12 portal control-plane v4','os12-settings-list','os12-evidence-row'):
        need(css if marker!='Workshop OS 12 portal control-plane v4' else js+css,marker,'v4 presentation')

    for marker in ('kPortalPolicyNamespace','portal_lock','prefs.getBool(kPortalPolicyKey, true)','securityPortalCodeRequired()','securitySetPortalCodeRequired','securityResetPortalPolicy'):
        need(sec+sech,marker,'persisted portal policy')
    need(sec,'if (!mutating && !securityPortalCodeRequired()) return true;','read-only open policy')
    need(sec,'if (mutating && !sameOrigin(server))','mutation same-origin gate')
    need(sec,'if (cookieMatches(server)) return true;','mutation session gate')

    need(sec,'RC6 secure physical acceptance forbids WORKSHOP_OS_TEMP_NO_CODE_LAN','legacy bypass fail-closed guard')
    for marker in (
        'kTemporaryNoCodeLan',
        'TEMPORARY PHYSICAL-TEST MODE ONLY.',
        'if (kTemporaryNoCodeLan) return true;',
        'TEMPORARY physical-test mode: station-LAN authentication is bypassed',
    ):
        forbid(sec,marker,'temporary no-code authorization bypass')
    forbid(sec,'if (!isAPMode()) return true;','station-LAN blanket auth bypass')

    for marker in ('handlePortalSecurityStatus','handlePortalSecuritySave','/api/portal-security','securityResetPortalPolicy(); // OS12 secure factory default'):
        need(web,marker,'portal security API/reset behavior')
    need(web,'securityPortalCodeRequired()?"portal-code":"open-readonly"','runtime auth observability')

    for marker in ('WORKSHOP_OS_PORTAL_CONTROL_PLANE_V4 1','WORKSHOP_OS_DEVICE_FEED_SCHEMA 1'):
        need(build,marker,'build identity')

    if not contract.exists():
        raise ValidationError(f'device-feed v1 schema mirror missing: {contract}')
    schema_text=contract.read_text(encoding='utf-8')
    for marker in ('"schemaVersion"','"quantity"','"placement"','"readiness"','"unknowns"','"attention"','"CalculatedFromMeasured"'):
        need(schema_text,marker,'device feed contract')

    print('PASS: OS12 portal control-plane v4 identity, IA, security, markup and inventory-authority boundaries are coherent')
    return 0


if __name__=='__main__':
    try:
        raise SystemExit(main())
    except ValidationError as exc:
        raise SystemExit(f'FAIL: {exc}')
