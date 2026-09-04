#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path


def need(body: str, marker: str, label: str) -> None:
    if marker not in body:
        raise SystemExit(f"V11.23 RC2 GUARD FEEDBACK FAILED: missing {label}: {marker}")


def forbid(body: str, marker: str, label: str) -> None:
    if marker in body:
        raise SystemExit(f"V11.23 RC2 GUARD FEEDBACK FAILED: forbidden {label}: {marker}")


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit(f"Usage: {sys.argv[0]} <reconstructed-repo>")
    repo=Path(sys.argv[1]).resolve()
    hub=(repo/'src/smart_hub.cpp').read_text(encoding='utf-8',errors='replace')
    main_cpp=(repo/'src/main.cpp').read_text(encoding='utf-8',errors='replace')
    header=(repo/'src/smart_hub.h').read_text(encoding='utf-8',errors='replace')

    for marker in [
        'Workshop OS v11.23 RC2 guarded-action feedback',
        'void smartHubUpdateHoldProgress(uint16_t rawX, uint16_t rawY, uint32_t holdMs)',
        'uint8_t segments=(uint8_t)((holdMs*5U+649U)/650U);',
        'kind=1;bx=240;by=252;bw=230;bh=56;label="HOLD APPLY";',
        'kind=2;bx=160;by=258;bw=310;bh=52;label="HOLD ROTATION";',
        'tft.fillRoundRect((int16_t)(px+i*(sw+gap)),py,sw,sh,2,c);',
        'smartHubUpdateHoldProgress(rawX,rawY,0);',
        'printerActive?"PRINTER ACTIVE - DISPLAY WILL RESTART"',
        '"Printer continues; display reconnects"',
        'printerActive?"HOLD APPLY - DISPLAY RESTART":"HOLD APPLY + RESTART"',
        'displayedPrinter().state.printing',
        'displayedPrinter().state.gcodeStateId==GCODE_PAUSE',
    ]:
        need(hub,marker,'guarded-action source contract')

    need(main_cpp,'if (hubTouchHasPoint) smartHubUpdateHoldProgress(hubTouchX, hubTouchY, d);','live hold dispatch')
    need(main_cpp,'hubTouchMaxHoldMs >= 650','existing long-press threshold')
    need(header,'void smartHubUpdateHoldProgress(uint16_t rawX, uint16_t rawY, uint32_t holdMs);','hold-feedback declaration')

    # The warning is informational only; this delta must not add printer-control calls.
    forbid(hub,'requestPrinterControlCommand','printer command in guarded network feedback')

    print('v11.23 RC2 guarded-action feedback: PASS')
    print('Hold progress: 5 live segments tied to 650 ms commit threshold')
    print('Network Apply: active-printer display restart/reconnect warning')
    print('Printer behavior: informational only; no printer command added')
    return 0


if __name__=='__main__':
    raise SystemExit(main())
