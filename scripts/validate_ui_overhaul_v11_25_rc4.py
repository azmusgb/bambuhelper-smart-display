#!/usr/bin/env python3
from pathlib import Path
import argparse,re,sys

def require(text,needle,label):
    if needle not in text: raise AssertionError(f'missing {label}: {needle}')
def forbid(text,needle,label):
    if needle in text: raise AssertionError(f'forbidden {label}: {needle}')

def main():
    ap=argparse.ArgumentParser();ap.add_argument('repo');a=ap.parse_args();root=Path(a.repo)
    hub=(root/'src/smart_hub.cpp').read_text(encoding='utf-8')
    build=(root/'include/smart_home_build.h').read_text(encoding='utf-8')
    security=(root/'src/security_manager.cpp').read_text(encoding='utf-8')
    css=(root/'web/app.css').read_text(encoding='utf-8')
    for n in ['SMART_HOME_VERSION "v11.25"','Workshop OS v11.25 Full Device UI Overhaul RC4 Product Polish','WORKSHOP_OS_V11_25_UI_OVERHAUL_RC4 1','WORKSHOP_OS_TEMP_NO_CODE_LAN 1']:
        require(build,n,'RC4 build/test identity')
    for n in ['W25_BG=0x08A3','W25_SURFACE=0x10E5','W25_SURFACE_2=0x1926','W25_ACCENT=0x5EB9','W25_INFO=0x5D5F','W25_WARN=0xF5AB','W25_DANGER=0xFB2E','W25_SUCCESS=0x5EB1','static const char* labels[4]={"HOME","PRINTER","WORKSHOP","MORE"};','static const char* labels[3]={"STATUS","AMS","CONTROL"};','HubRect hero=hr(8,48,304,128)','rail=hr(320,48,W-328,212)','"WORKSHOP STATUS"','"NO CODE"','"TEST BUILD ONLY"','"INVENTORY IDENTITY"','"Printer telemetry only - no inferred spool match"','"DIRECT CONTROLS"','"Stop requires hold"','g_printerMode!=HUB_PRINTER_CONTROL','s.connected&&active&&longPress']:
        require(hub,n,'RC4 native product contract')
    for fn in ['drawHome','drawPrinter','drawWorkshop','drawMore','drawSystem']:
        count=len(re.findall(rf'static void {fn}\s*\(',hub))
        if count!=1: raise AssertionError(f'{fn}: expected 1 definition, found {count}')
    for n in ['resolveSpool','matchSpoolByColor','matchSpoolByMaterial']:
        forbid(hub,n,'firmware-side inventory identity inference')
    require(security,'if (!isAPMode()) return true;','temporary station-LAN no-code mode')
    require(security,'if (mutating && !sameOrigin(server))','same-origin mutating-request guard')
    for n in ['Workshop OS v11.25 RC4 Product Polish','--accent:#22b8a9','--bg:#0f141a','.wk116-printer','.wk116-control','@media (pointer:coarse)','min-height:48px','@media(prefers-reduced-motion:reduce)','@media(forced-colors:active)']:
        require(css,n,'RC4 device CSS')
    if css.rfind('Workshop OS v11.25 RC4 Product Polish') < css.rfind('Workshop OS v11.25 RC3 — premium portal polish'):
        raise AssertionError('RC4 CSS does not override RC3 CSS')
    print('Workshop OS v11.25 RC4 Product Polish contract: PASS')
    print('native_palette=GRAPHITE_MINT_SEMANTIC')
    print('primary_nav=Home/Printer/Workshop/More')
    print('printer_modes=Status/AMS/Control')
    print('device_css=POLISHED_RESPONSIVE_TOUCH_A11Y')
    print('station_lan_device_code=TEMPORARILY_DISABLED_TEST_ONLY')
    print('inventory_identity_inference=FORBIDDEN')
    return 0
if __name__=='__main__':
    try: raise SystemExit(main())
    except AssertionError as e:
        print(f'FAIL: {e}',file=sys.stderr);raise SystemExit(1)
