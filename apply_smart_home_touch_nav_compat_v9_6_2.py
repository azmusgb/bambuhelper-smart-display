#!/usr/bin/env python3
from pathlib import Path
import argparse


class PatchError(RuntimeError):
    pass


def apply(repo: Path) -> None:
    p = repo / "src" / "main.cpp"
    text = p.read_text(encoding="utf-8")

    old = '''  if (smartHubIsScreen(cur)) {
    int16_t touchX = 0, touchY = 0;
    if (buttonLastTouchPoint(&touchX, &touchY) &&
        smartHubHandleTouch(touchX, touchY)) {
      return;
    }
    smartHubAdvance();
    return;
  }'''

    new = '''  if (smartHubIsScreen(cur)) {
#if defined(BOARD_IS_WS350)
    // Coordinate-aware direct navigation is intentionally WS350-only. Shared
    // targets keep the established tap-cycle interaction and do not link the
    // WS350 Smart Hub coordinate handler.
    int16_t touchX = 0, touchY = 0;
    if (buttonLastTouchPoint(&touchX, &touchY) &&
        smartHubHandleTouch(touchX, touchY)) {
      return;
    }
#endif
    smartHubAdvance();
    return;
  }'''

    count = text.count(old)
    if count != 1:
        raise PatchError(f"main direct-nav compatibility anchor: expected 1 match, found {count}")
    text = text.replace(old, new, 1)
    p.write_text(text, encoding="utf-8")

    out = p.read_text(encoding="utf-8")
    for needle in [
        '#if defined(BOARD_IS_WS350)',
        'buttonLastTouchPoint(&touchX, &touchY)',
        'smartHubHandleTouch(touchX, touchY)',
        'smartHubAdvance();',
        'Coordinate-aware direct navigation is intentionally WS350-only',
    ]:
        if needle not in out:
            raise PatchError(f"compatibility contract missing: {needle}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Smart Home v9.6 RC2 cross-board touch-nav compatibility")
    ap.add_argument("--repo", required=True)
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    if not args.apply:
        raise SystemExit("Pass --apply")
    apply(Path(args.repo))
    print("Smart Home v9.6 RC2 WS350 touch-nav compatibility applied")
