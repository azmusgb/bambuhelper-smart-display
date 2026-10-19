#!/usr/bin/env python3
"""Consolidate the layered Workshop OS portal stylesheet without changing rendering.

web/app.css is the upstream base plus ~24 appended version layers. Later layers
override earlier ones instead of replacing them, so the served file carries
shadowed declarations, rules for retired markup, and repeated token blocks.

Only transformations that cannot change what a browser renders are applied,
and rule order is never changed:

1. Shadowed declarations. A declaration is dropped when a later rule with the
   identical selector list, in the identical @media/@supports context, sets the
   same property with equal or higher importance. Values that may be feature
   fallbacks for the later value (color-mix, oklch, dvh, ...) are kept.
2. Dead selectors. A selector that requires a class never mentioned by the
   portal markup or scripts can never match, so it is removed from its list
   (the rule goes when its list is empty). Classes built from string prefixes
   such as 'tone-'+name count as used, and :not(...) contents are ignored.
3. Unused custom properties: defined, never read via var() in CSS, and never
   mentioned by scripts or firmware.
4. Empty rules and empty at-rule blocks.

scripts/test_consolidate_portal_css.py covers the parser and each rule;
apply_workshop_os12_portal_css_consolidate.py runs this on a reconstructed tree.
"""
from __future__ import annotations

import argparse
import re
from dataclasses import dataclass, field
from pathlib import Path

# Later values that older engines may not understand; never treat an earlier
# declaration of the same property as dead when the later one uses these.
FALLBACK_SENSITIVE = re.compile(
    r"color-mix\(|oklch\(|oklab\(|\blab\(|\blch\(|\b\d*\.?\d+(?:dvh|svh|lvh|dvw|svw|lvw)\b|"
    r"\bcqi\b|\bcqw\b|\bcqh\b|light-dark\(|round\(|mod\(|rem\("
)
GROUPING_AT_RULES = ("@media", "@supports", "@layer", "@container")


@dataclass
class Decl:
    prop: str
    value: str
    important: bool

    def text(self) -> str:
        return f"{self.prop}:{self.value}{'!important' if self.important else ''}"


@dataclass
class Rule:
    selectors: list[str]
    decls: list[Decl]
    context: tuple[str, ...]

    def key(self) -> tuple:
        return (self.context, tuple(sorted(self.selectors)))


@dataclass
class Block:
    prelude: str
    children: list = field(default_factory=list)


@dataclass
class Raw:
    """An at-rule kept verbatim (@keyframes, @font-face, @import, ...)."""
    text: str


def _strip_comments(css: str) -> str:
    out, i, n = [], 0, len(css)
    while i < n:
        c = css[i]
        if c in "\"'":
            j = i + 1
            while j < n and css[j] != c:
                j += 2 if css[j] == "\\" else 1
            out.append(css[i:j + 1])
            i = j + 1
        elif css.startswith("/*", i):
            end = css.find("*/", i + 2)
            i = n if end < 0 else end + 2
        else:
            out.append(c)
            i += 1
    return "".join(out)


def _match_brace(css: str, open_idx: int) -> int:
    depth, i, n = 0, open_idx, len(css)
    while i < n:
        c = css[i]
        if c in "\"'":
            j = i + 1
            while j < n and css[j] != c:
                j += 2 if css[j] == "\\" else 1
            i = j
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    raise ValueError("unbalanced braces in stylesheet")


def _split_top(text: str, sep: str) -> list[str]:
    """Split on sep outside parentheses, brackets and strings."""
    parts, depth, quote, start = [], 0, "", 0
    for i, c in enumerate(text):
        if quote:
            if c == quote and text[i - 1] != "\\":
                quote = ""
        elif c in "\"'":
            quote = c
        elif c in "([":
            depth += 1
        elif c in ")]":
            depth -= 1
        elif c == sep and depth == 0:
            parts.append(text[start:i])
            start = i + 1
    parts.append(text[start:])
    return parts


def _parse_decls(body: str) -> list[Decl]:
    decls = []
    for chunk in _split_top(body, ";"):
        chunk = chunk.strip()
        if not chunk or ":" not in chunk:
            continue
        prop, value = chunk.split(":", 1)
        value = value.strip()
        important = False
        m = re.search(r"!\s*important\s*$", value, re.I)
        if m:
            important = True
            value = value[: m.start()].rstrip()
        decls.append(Decl(prop.strip().lower() if not prop.strip().startswith("--") else prop.strip(), value, important))
    return decls


def parse(css: str, context: tuple[str, ...] = ()) -> list:
    css = _strip_comments(css) if not context else css
    nodes, i, n = [], 0, len(css)
    while i < n:
        while i < n and css[i] in " \t\r\n;":
            i += 1
        if i >= n:
            break
        brace = css.find("{", i)
        semi = css.find(";", i)
        if css[i] == "@" and (brace < 0 or (0 <= semi < brace)):
            nodes.append(Raw(css[i:semi + 1].strip()))  # @import / @charset
            i = semi + 1
            continue
        if brace < 0:
            break
        end = _match_brace(css, brace)
        prelude = " ".join(css[i:brace].split())
        inner = css[brace + 1:end]
        if prelude.startswith("@"):
            if prelude.lower().startswith(GROUPING_AT_RULES):
                nodes.append(Block(prelude, parse(inner, context + (prelude,))))
            else:
                nodes.append(Raw(f"{prelude}{{{inner.strip()}}}"))
        else:
            selectors = [" ".join(s.split()) for s in _split_top(prelude, ",") if s.strip()]
            nodes.append(Rule(selectors, _parse_decls(inner), context))
        i = end + 1
    return nodes


def _rules(nodes: list):
    for node in nodes:
        if isinstance(node, Rule):
            yield node
        elif isinstance(node, Block):
            yield from _rules(node.children)


def drop_shadowed(nodes: list) -> int:
    later: dict[tuple, dict[str, tuple[bool, str]]] = {}
    removed = 0
    for rule in reversed(list(_rules(nodes))):
        seen = later.setdefault(rule.key(), {})
        kept = []
        for decl in rule.decls:
            winner = seen.get(decl.prop)
            if winner and (winner[0] or not decl.important) and not FALLBACK_SENSITIVE.search(winner[1]):
                removed += 1
                continue
            kept.append(decl)
        rule.decls = kept
        for decl in rule.decls:
            prev = seen.get(decl.prop)
            if prev is None or (decl.important and not prev[0]):
                seen[decl.prop] = (decl.important, decl.value)
    return removed


CLASS_RE = re.compile(r"\.(-?[_a-zA-Z][\w-]*)")


def _required_classes(selector: str) -> set[str]:
    # Classes inside :not(...) or other functional pseudos are not required.
    flat, depth = [], 0
    for c in selector:
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
        elif depth == 0:
            flat.append(c)
    return set(CLASS_RE.findall("".join(flat)))


def referenced_classes(corpus: str) -> tuple[set[str], tuple[str, ...]]:
    words = set(re.findall(r"[A-Za-z_][\w-]*", corpus))
    prefixes = set(re.findall(r"""["'`]([A-Za-z][\w-]*-)["'`$]""", corpus))
    prefixes |= set(re.findall(r"""([A-Za-z][\w-]*-)\$\{""", corpus))
    return words, tuple(sorted(prefixes))


def drop_dead_selectors(nodes: list, words: set[str], prefixes: tuple[str, ...]) -> int:
    def alive(cls: str) -> bool:
        return cls in words or cls.startswith(prefixes)

    removed = 0
    for rule in _rules(nodes):
        kept = [s for s in rule.selectors if all(alive(c) for c in _required_classes(s))]
        removed += len(rule.selectors) - len(kept)
        rule.selectors = kept
    return removed


def drop_unused_properties(nodes: list, corpus: str) -> int:
    css_reads = set()
    for rule in _rules(nodes):
        for decl in rule.decls:
            css_reads |= set(re.findall(r"var\(\s*(--[\w-]+)", decl.value))
    removed = 0
    for rule in _rules(nodes):
        kept = []
        for decl in rule.decls:
            if decl.prop.startswith("--") and decl.prop not in css_reads and decl.prop not in corpus:
                removed += 1
                continue
            kept.append(decl)
        rule.decls = kept
    return removed


def prune_empty(nodes: list) -> list:
    out = []
    for node in nodes:
        if isinstance(node, Rule):
            if node.selectors and node.decls:
                out.append(node)
        elif isinstance(node, Block):
            node.children = prune_empty(node.children)
            if node.children:
                out.append(node)
        else:
            out.append(node)
    return out


def serialize(nodes: list, indent: str = "") -> str:
    lines = []
    for node in nodes:
        if isinstance(node, Rule):
            lines.append(f"{indent}{','.join(node.selectors)}{{{';'.join(d.text() for d in node.decls)}}}")
        elif isinstance(node, Block):
            lines.append(f"{indent}{node.prelude}{{")
            lines.append(serialize(node.children, indent + "  "))
            lines.append(f"{indent}}}")
        else:
            lines.append(f"{indent}{node.text}")
    return "\n".join(line for line in lines if line)


def consolidate(css: str, corpus: str) -> tuple[str, dict[str, int]]:
    nodes = parse(css)
    words, prefixes = referenced_classes(corpus)
    stats = {
        "deadSelectors": drop_dead_selectors(nodes, words, prefixes),
        "shadowedDeclarations": drop_shadowed(nodes),
    }
    stats["unusedProperties"] = drop_unused_properties(nodes, corpus)
    nodes = prune_empty(nodes)
    header = ("/* Workshop OS portal stylesheet, consolidated at build time by\n"
              "   scripts/consolidate_portal_css.py. Edit the layered sources, not this output. */\n")
    return header + serialize(nodes) + "\n", stats


def portal_corpus(repo: Path) -> str:
    parts = [repo / "web" / "app.js"]
    for folder in ("src", "include"):
        parts += sorted((repo / folder).glob("*.cpp")) + sorted((repo / folder).glob("*.h"))
    return "\n".join(p.read_text(encoding="utf-8", errors="ignore") for p in parts if p.is_file())


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--repo", required=True, help="reconstructed firmware tree")
    ap.add_argument("--out", help="write here instead of printing stats only")
    args = ap.parse_args()
    repo = Path(args.repo)
    css = (repo / "web" / "app.css").read_text(encoding="utf-8")
    result, stats = consolidate(css, portal_corpus(repo))
    print(f"{len(css)} -> {len(result)} bytes; {stats}")
    if args.out:
        Path(args.out).write_text(result, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
