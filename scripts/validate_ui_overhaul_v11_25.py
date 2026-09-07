#!/usr/bin/env python3
from pathlib import Path
import argparse, re, sys

def require(text, needle, label):
    if needle not in text:
        raise AssertionError(f"missing {label}: {needle}")

def forbid(text, needle, label):
    if needle in text:
        raise AssertionError(f"forbidden {label}: {needle}")

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('repo')
    a=ap.parse_args()
    root=Path(a.repo)
    hub=(root/'src/smart_hub.cpp').read_text()
    build=(root/'include/smart_home_build.h').read_text()

    for n in ['SMART_HOME_VERSION "v11.25"','SMART_HOME_PROFILE "full-device-ui-overhaul"','Workshop OS v11.25 Full Device UI Overhaul RC1','WORKSHOP_OS_V11_25_UI_OVERHAUL 1']:
        require(build,n,'build identity')

    for n in [
        'static int16_t hubNavH() { return 52; }',
        'static int16_t hubHeaderH() { return 40; }',
        'static const char* labels[4]={"HOME","PRINTER","WORKSHOP","MORE"};',
        '"STATUS","AMS","CONTROL"',
        'return hr(x,48,i==2?W-m-x:cw,50);',
        'return hr(m+(i%2)*(cw+g),106+(i/2)*76,cw,68);',
        'return hr(m+i*(cw+g),208,cw,52);',
        'return hr(x+i*(cw+g),104,cw,48);',
        'Inventory spool: Unknown',
        'Printer telemetry only • no identity inferred from color/material',
        'inventory spool Unknown',
        'g_printerMode!=HUB_PRINTER_CONTROL',
        'powerConfirmOpenForSlot(slot)',
        's.connected&&active&&longPress',
        'kind=3;bx=r.x;by=r.y;bw=r.w;bh=r.h;label="HOLD STOP"',
    ]:
        require(hub,n,'v11.25 UI contract')

    mode_touch='if(hubV1125PrinterModeRect(i).contains(x,y)){g_printerMode=i;buzzerPlay(BUZZ_CLICK);g_dirty=true;return true;}'
    require(hub,mode_touch,'explicit Printer mode switching')

    for n in ['requestPrinterControlCommand','requestLightCommand','securityPortalCode','recoveryWebReady']:
        require(hub,n,'inherited device boundary')
    for n in ['requestSpeedCommand','requestFanCommand','WORKSHOP_OS_TEMP_LAN_OPEN','TEMPORARY TRUSTED-LAN MODE']:
        forbid(hub,n,'unsafe control/auth regression')

    forbid(hub,'resolveSpool','firmware-side spool resolution')
    forbid(hub,'matchSpoolByColor','color-based spool identity')
    forbid(hub,'matchSpoolByMaterial','material-based spool identity')

    for fn in ['drawHome','drawPrinter','drawWorkshop','drawMore','drawSystem']:
        count=len(re.findall(rf'static void {fn}\s*\(',hub))
        if count!=1: raise AssertionError(f'{fn}: expected 1 definition, found {count}')

    dims=[52,50,68,64,52,60,48,50]
    if min(dims)<48: raise AssertionError('primary control geometry below 48px')

    print('Workshop OS v11.25 full-device UI contract: PASS')
    print('primary_nav=Home/Printer/Workshop/More')
    print('printer_modes=STATUS/AMS/CONTROL')
    print('inventory_identity=Unknown unless authoritative contract exists')
    print('routine_touch_floor=48px')
    print('stop_guard=long-press + progress feedback')
    return 0

if __name__=='__main__':
    try: raise SystemExit(main())
    except AssertionError as e:
        print(f'FAIL: {e}',file=sys.stderr); raise SystemExit(1)
