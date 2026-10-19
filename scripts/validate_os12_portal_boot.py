#!/usr/bin/env python3
"""Validate that the finished Local Portal can boot and hide what it hides.

Runs on the finished OS12 tree, after every layer that edits web/app.js,
include/web_pages.h or web/app.css.

1. Boot order. boot() runs at the top level of app.js and calls
   toggleConnMode() -> refreshGaugeProfileUi(), which reads _profileCaps.
   If `var _profileCaps = {}` only runs after the boot IIFE, the read throws a
   TypeError, boot stops, and nothing after it in app.js runs: the Local AI
   panels stay at "Checking…" and Filament Inventory at "Loading…".
   _profileCaps must be declared once and initialised before boot.

2. Hidden attributes. A stylesheet `display:` on an element beats the
   browser's own `[hidden]{display:none}`. Every element that starts hidden
   must not carry a class that app.css gives a display value, unless app.css
   also hides that class (or every element) when [hidden] is set.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


class ValidationError(RuntimeError):
    pass


def read(path: Path) -> str:
    if not path.exists():
        raise ValidationError(f"missing {path}")
    return path.read_text(encoding="utf-8")


def check_boot_order(app_js: str) -> None:
    boot_at = app_js.find("(function boot(){")
    if boot_at < 0:
        raise ValidationError("boot IIFE `(function boot(){` not found in web/app.js")
    decls = [m.start() for m in re.finditer(r"\bvar _profileCaps\b", app_js)]
    if len(decls) != 1:
        raise ValidationError(f"_profileCaps must be declared exactly once, found {len(decls)}")
    init = re.search(r"\bvar _profileCaps\s*=\s*\{", app_js)
    if not init:
        raise ValidationError("_profileCaps must be initialised to an object where it is declared")
    if init.start() > boot_at:
        line = app_js.count("\n", 0, init.start()) + 1
        boot_line = app_js.count("\n", 0, boot_at) + 1
        raise ValidationError(
            f"_profileCaps is initialised at app.js:{line}, after the boot IIFE at app.js:{boot_line}; "
            "boot() -> toggleConnMode() -> refreshGaugeProfileUi() reads it while it is undefined"
        )


def css_rules(css: str):
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    for m in re.finditer(r"([^{}]+)\{([^{}]*)\}", css):
        selectors = [s.strip() for s in m.group(1).split(",")]
        yield selectors, m.group(2)


def display_value(body: str) -> str | None:
    found = re.findall(r"(?:^|;)\s*display\s*:\s*([^;!]+)", body)
    return found[-1].strip() if found else None


def check_hidden(html: str, css: str) -> None:
    shown_by: dict[str, str] = {}
    hidden_ok: set[str] = set()
    global_hidden = False
    for selectors, body in css_rules(css):
        value = display_value(body)
        if value is None:
            continue
        for sel in selectors:
            if value == "none":
                if sel == "[hidden]" and "!important" in body:
                    global_hidden = True
                m = re.fullmatch(r"\.([\w-]+)\[hidden\]", sel)
                if m:
                    hidden_ok.add(m.group(1))
                continue
            # The element the rule styles is the last compound selector.
            last = re.split(r"\s+|>|\+|~", sel)[-1]
            if ":" in last or "[" in last:
                continue
            for cls in re.findall(r"\.([\w-]+)", last):
                shown_by.setdefault(cls, f"{sel}{{display:{value}}}")
    if global_hidden:
        return
    problems = []
    for tag in re.finditer(r"<[a-zA-Z][^<>]*\shidden(?=[\s>])[^<>]*>", html):
        cls = re.search(r'\bclass="([^"]*)"', tag.group(0))
        if not cls:
            continue
        for name in cls.group(1).split():
            if name in shown_by and name not in hidden_ok:
                ident = re.search(r'\bid="([^"]*)"', tag.group(0))
                where = f"#{ident.group(1)}" if ident else tag.group(0)[:80]
                problems.append(f"{where} is hidden but .{name} sets {shown_by[name]}")
    if problems:
        raise ValidationError("hidden elements that the stylesheet shows anyway:\n  " + "\n  ".join(problems))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    args = ap.parse_args()
    repo = Path(args.repo)
    try:
        app_js = read(repo / "web" / "app.js")
        html = read(repo / "include" / "web_pages.h")
        css = read(repo / "web" / "app.css")
        check_boot_order(app_js)
        check_hidden(html, css)
    except ValidationError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    print("PASS: _profileCaps is initialised before boot reads it, and every element that starts "
          "hidden stays hidden under app.css")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
