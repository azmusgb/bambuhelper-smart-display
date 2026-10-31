#!/usr/bin/env python3
from pathlib import Path
import argparse

class PatchError(RuntimeError):
    pass

def replace_once(text, old, new, name):
    n = text.count(old)
    if n != 1:
        raise PatchError(f"{name}: expected exactly 1 match, found {n}")
    return text.replace(old, new, 1)

def apply(repo: Path):
    p = repo / 'src' / 'smart_hub.cpp'
    text = p.read_text(encoding='utf-8')

    old = '''static void drawWorkshop(bool full) {\n  (void)full;\n  tft.fillScreen(dispSettings.bgColor);\n  drawHeader("WORKSHOP", "Printer + AMS", 1);\n'''
    new = '''static void drawWorkshop(bool full) {\n  // Smart Home v7.2 display-stability pass. The v7.1 Workshop renderer\n  // cleared and repainted the full panel whenever the hub render loop asked\n  // for a frame. On the physical WS350 this showed up as a rolling/pulsing\n  // redraw in video and could be perceived as flicker. Cap dynamic redraws\n  // and preserve the static header/footer between updates.\n  static unsigned long lastDraw = 0;\n  const unsigned long now = millis();\n  if (!full && lastDraw != 0) {\n    if (now - lastDraw < 750) return;\n    if (!g_dirty && now - lastDraw < 5000) return;\n  }\n  const bool fullRedraw = full || lastDraw == 0;\n  lastDraw = now;\n\n  if (fullRedraw) {\n    tft.fillScreen(dispSettings.bgColor);\n    drawHeader("WORKSHOP", "Printer + AMS", 1);\n  } else {\n    // Clear only the dynamic body. Leave header and bottom navigation intact\n    // so the eye never sees the entire 320x480 panel blank between frames.\n    const int16_t bodyTop = 38;\n    const int16_t footerReserve = 30;\n    tft.fillRect(0, bodyTop, tft.width(),\n                 tft.height() - bodyTop - footerReserve,\n                 dispSettings.bgColor);\n  }\n'''
    text = replace_once(text, old, new, 'Workshop redraw throttling')

    text = replace_once(text,
        'drawHeader("HOME", "Smart Home v7.1", 0);',
        'drawHeader("HOME", "Smart Home v7.2", 0);',
        'Home release identity')
    text = replace_once(text,
        'drawHeader("SYSTEM", "Smart Home v7.1", 3);',
        'drawHeader("SYSTEM", "Smart Home v7.2", 3);',
        'System release identity')

    marker = '// BambuHelper smart home UX evolution v7.1'
    if marker in text and '// BambuHelper display stability evolution v7.2' not in text:
        text = text.replace(marker,
            marker + '\n// BambuHelper display stability evolution v7.2', 1)

    p.write_text(text, encoding='utf-8')

if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--repo', required=True)
    ap.add_argument('--apply', action='store_true')
    args = ap.parse_args()
    if not args.apply:
        raise SystemExit('Pass --apply')
    apply(Path(args.repo))
    print('Smart Home v7.2 display stability patch applied')
