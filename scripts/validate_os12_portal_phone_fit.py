#!/usr/bin/env python3
"""Validate the Local Portal phone fit on the finished OS12 tree.

Runs after apply_workshop_os12_portal_phone_fit.py.

1. Tap targets. app.css carries the phone-fit layer once, with the 44 px rules
   for the hamburger, theme toggle, colour inputs, Printer tabs, the
   "Release notes" link and the "Require access code" label. The Recovery
   buttons and the AP-setup fields, button and "Show password" label carry
   min-height:44px in their inline styles.
2. Contrast. Every light-theme colour the layer sets passes WCAG AA (4.5:1) as
   text on white, on the light page background and on the light sub-surface,
   and with the light page background as text on it.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import apply_workshop_os12_portal_phone_fit as fit  # noqa: E402

LIGHT_SURFACES = {"white": "#ffffff", "page": "#f4f4f2", "sub": "#edf1f1"}
TAP_RULES = (
    ".topbar .hamburger{width:44px;height:44px}",
    ".icon-btn{width:44px}",
    '.section input[type="color"]{width:44px}',
    ".v96-tab,.v104-printer-workspace .v96-tab{min-height:44px}",
    ".section a.small[href]{display:inline-flex;align-items:center;min-height:44px}",
    ".os12-security-control label[for]{display:inline-flex;align-items:center;min-height:44px",
)


class ValidationError(RuntimeError):
    pass


def luminance(hex_colour: str) -> float:
    h = hex_colour.lstrip("#")
    def channel(v: int) -> float:
        c = v / 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)


def contrast(a: str, b: str) -> float:
    la, lb = luminance(a), luminance(b)
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)


def check_contrast() -> None:
    colours = {k: v for k, v in fit.LIGHT_TOKENS.items() if k != "--accent-hover"}
    colours["v92-build-pill"] = fit.LIGHT_BUILD_PILL
    for name, colour in colours.items():
        for surface, bg in LIGHT_SURFACES.items():
            ratio = contrast(colour, bg)
            if ratio < 4.5:
                raise ValidationError(f"light {name} {colour} on {surface} {bg} is {ratio:.2f}:1, below 4.5:1")
    for name in ("--accent", "--ui5-accent", "--accent-hover"):
        ratio = contrast(LIGHT_SURFACES["page"], fit.LIGHT_TOKENS[name])
        if ratio < 4.5:
            raise ValidationError(f"light page colour on {name} is {ratio:.2f}:1, below 4.5:1")


def check_tree(repo: Path) -> None:
    css_path = repo / "web" / "app.css"
    if not css_path.is_file():
        raise ValidationError(f"missing {css_path}")
    css = css_path.read_text(encoding="utf-8")
    if css.count(fit.MARKER) != 1:
        raise ValidationError(f"phone-fit layer must appear exactly once in web/app.css (found {css.count(fit.MARKER)})")
    layer = css[css.index(fit.MARKER):]
    for rule in TAP_RULES:
        if rule not in layer:
            raise ValidationError(f"phone-fit layer is missing {rule!r}")
    tokens = re.search(r'html\[data-theme="light"\]\{([^}]*)\}', layer)
    if not tokens or any(f"{k}:{v}" not in tokens.group(1) for k, v in fit.LIGHT_TOKENS.items()):
        raise ValidationError("phone-fit layer is missing the light-theme AA colours")
    for rel, _old, new, label in fit.PAGE_EDITS:
        path = repo / rel
        if not path.is_file() or new not in path.read_text(encoding="utf-8"):
            raise ValidationError(f"{label}: 44px inline style missing from {rel}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True)
    args = parser.parse_args()
    try:
        check_contrast()
        check_tree(Path(args.repo).resolve())
    except ValidationError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    print("PASS: portal tap targets are 44px and the light-theme colours pass WCAG AA")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
