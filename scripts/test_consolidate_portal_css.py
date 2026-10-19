#!/usr/bin/env python3
"""Tests for the lossless portal stylesheet consolidation and its a11y stage."""
from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.consolidate_portal_css import consolidate, parse, serialize  # noqa: E402

spec = importlib.util.spec_from_file_location("css_overlay", ROOT / "apply_workshop_os12_portal_css_consolidate.py")
overlay = importlib.util.module_from_spec(spec)
spec.loader.exec_module(overlay)

theme_spec = importlib.util.spec_from_file_location("css_theme", ROOT / "apply_workshop_os12_portal_localai_theme.py")
theme = importlib.util.module_from_spec(theme_spec)
theme_spec.loader.exec_module(theme)

scale_spec = importlib.util.spec_from_file_location("css_scale", ROOT / "apply_workshop_os12_portal_design_scale.py")
scale = importlib.util.module_from_spec(scale_spec)
scale_spec.loader.exec_module(scale)


def run(css: str, corpus: str = "") -> str:
    out, _ = consolidate(css, corpus)
    return out.split("*/\n", 1)[1]


class ShadowingTests(unittest.TestCase):
    def test_later_identical_selector_shadows_same_property(self) -> None:
        self.assertEqual(run(".a{color:red;margin:0}.b{x:1}.a{color:blue}", "a b"),
                         ".a{margin:0}\n.b{x:1}\n.a{color:blue}\n")

    def test_selector_list_order_is_irrelevant_but_membership_is_not(self) -> None:
        self.assertEqual(run(".a,.b{color:red}.b,.a{color:blue}", "a b"), ".b,.a{color:blue}\n")
        self.assertEqual(run(".a,.b{color:red}.a{color:blue}", "a b"), ".a,.b{color:red}\n.a{color:blue}\n")

    def test_earlier_important_survives_later_normal(self) -> None:
        self.assertEqual(run(".a{color:red!important}.a{color:blue}", "a"),
                         ".a{color:red!important}\n.a{color:blue}\n")

    def test_media_context_must_match(self) -> None:
        css = ".a{color:red}@media(max-width:600px){.a{color:blue}}"
        self.assertEqual(run(css, "a"), ".a{color:red}\n@media(max-width:600px){\n  .a{color:blue}\n}\n")

    def test_fallback_for_newer_value_is_kept(self) -> None:
        css = ".a{background:#fff}.a{background:color-mix(in srgb,red 50%,blue)}"
        self.assertIn("background:#fff", run(css, "a"))

    def test_same_rule_fallbacks_are_untouched(self) -> None:
        self.assertEqual(run(".a{display:-webkit-box;display:flex}", "a"), ".a{display:-webkit-box;display:flex}\n")


class DeadSelectorTests(unittest.TestCase):
    def test_unreferenced_class_selector_is_removed(self) -> None:
        self.assertEqual(run(".live,.gone{color:red}.gone .x{margin:0}", "live x"), ".live{color:red}\n")

    def test_not_contents_are_not_required(self) -> None:
        self.assertEqual(run(".a:not(.gone){color:red}", "a"), ".a:not(.gone){color:red}\n")

    def test_dynamic_prefix_keeps_class(self) -> None:
        self.assertEqual(run(".tone-amber{color:red}", "el.className = 'tone-' + level;"), ".tone-amber{color:red}\n")


class TokenTests(unittest.TestCase):
    def test_unused_custom_property_removed_used_kept(self) -> None:
        css = ":root{--used:1px;--unused:2px;--js:3px}.a{margin:var(--used)}"
        self.assertEqual(run(css, "a style.setProperty('--js')"), ":root{--used:1px;--js:3px}\n.a{margin:var(--used)}\n")


class ParserTests(unittest.TestCase):
    def test_comments_strings_and_data_urls_survive(self) -> None:
        css = '/* x { */.a{content:"a;b}";background:url(data:image/svg+xml;utf8,<svg/>)}@keyframes k{0%{opacity:0}}'
        out = serialize(parse(css))
        self.assertIn('content:"a;b}"', out)
        self.assertIn("url(data:image/svg+xml;utf8,<svg/>)", out)
        self.assertIn("@keyframes k{0%{opacity:0}}", out)


class A11yStageTests(unittest.TestCase):
    def test_light_muted_text_and_min_font(self) -> None:
        css = (":root{--text-dim:#7b8a91}\n  .app{grid-template-columns:1fr!important}\n.badge{font-size:8px}\n.v98-ring span{font-size:7px}\n"
               ".kicker{font:700 9px ui-monospace}\n.body{font-size:14px}")
        fixed, raised = overlay.apply_a11y_fixes(css)
        self.assertIn("--text-dim:#5a686f", fixed)
        self.assertIn(".app{grid-template-columns:minmax(0,1fr)!important}", fixed)
        self.assertIn(".badge{font-size:10px}", fixed)
        self.assertIn(".v98-ring span{font-size:7px}", fixed)  # device-screen miniature keeps scale
        self.assertIn(".kicker{font:700 10px ui-monospace}", fixed)
        self.assertIn(".body{font-size:14px}", fixed)
        self.assertEqual(raised, 2)

    def test_missing_anchor_fails_loudly(self) -> None:
        with self.assertRaises(overlay.PatchError):
            overlay.apply_a11y_fixes(":root{--text-dim:#000000}")
        with self.assertRaises(overlay.PatchError):
            overlay.apply_a11y_fixes(":root{--text-dim:#7b8a91}")  # narrow shell rule missing


class DesignScaleTests(unittest.TestCase):
    HEAD = "/* x, consolidated at build time by\n   y */\n"

    def scaled(self, body: str) -> str:
        out, _ = scale.apply_scale(self.HEAD + body)
        return out

    def test_font_sizes_become_tokens_rounding_half_pixels_up(self) -> None:
        out = self.scaled(".a{font-size:12.5px}\n.b{font:700 15px ui-monospace}\n.c{font-size:27px}")
        self.assertIn(".a{font-size:var(--fs-md)}", out)       # 12.5 -> 13
        self.assertIn(".b{font:700 var(--fs-lg) ui-monospace}", out)  # 15 -> 16
        self.assertIn(".c{font-size:var(--fs-2xl)}", out)      # 27 -> 28
        self.assertIn(":root{--fs-2xs:10px;", out)

    def test_miniature_keeps_scale_and_pills_stay_round(self) -> None:
        out = self.scaled(".v98-ring span{font-size:7px;border-radius:3px}\n.p{border-radius:999px}\n.r{border-radius:9px}")
        self.assertIn(".v98-ring span{font-size:7px;border-radius:3px}", out)
        self.assertIn(".p{border-radius:999px}", out)
        self.assertIn(".r{border-radius:8px}", out)

    def test_breakpoints_snap_only_in_media_queries(self) -> None:
        out = self.scaled("@media(max-width:980px){\n  .a{max-width:980px}\n}")
        self.assertIn("@media(max-width:1050px){", out)
        self.assertIn(".a{max-width:980px}", out)

    def test_indistinguishable_colours_merge_onto_most_used(self) -> None:
        out = self.scaled(".a{color:#10151a}\n.b{color:#10151a}\n.c{color:#0f141a}\n.d{color:#ff0000}")
        self.assertEqual(out.count("#10151a"), 3)
        self.assertNotIn("#0f141a", out)
        self.assertIn("#ff0000", out)

    def test_requires_consolidated_input(self) -> None:
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "web").mkdir()
            (Path(d) / "web/app.css").write_text(".a{color:red}")
            with self.assertRaises(scale.PatchError):
                scale.apply(Path(d))




class LocalAIThemeTests(unittest.TestCase):
    CSS = ("/* x, consolidated at build time by\n   y */\n"
           ":root{--sp-2:8px;--sans:-apple-system,sans-serif;--mono:ui-monospace}\n"
           ":root{--fs-2xs:10px;--fs-xs:11px;--fs-sm:12px;--fs-md:13px;--fs-base:14px;--fs-lg:16px;--fs-xl:24px;--fs-2xl:28px}\n"
           ":root{" + ";".join(f"{k}:#000" for k in theme.LIGHT) + "}\n"
           'html[data-theme="dark"]{' + ";".join(f"{k}:#000" for k in theme.DARK) + "}\n"
           ".v98-ring span{font-size:7px;color:#ff6b23}")

    def test_palettes_type_and_font_follow_localai(self) -> None:
        out = theme.theme_css(self.CSS, b"woff2-bytes")
        self.assertIn("--accent:#6cb6ff", out)          # LocalAI --ds-accent, dark
        self.assertIn("--bg:#0a111c", out)              # LocalAI --ds-bg
        self.assertIn("--accent:#1b62bd", out)          # derived light accent
        self.assertIn("--fs-base:15px", out)            # LocalAI --ds-fs-2
        self.assertIn('--sans:Figtree,system-ui', out)
        self.assertIn("@font-face{font-family:Figtree;", out)
        self.assertIn("SIL OFL 1.1", out)
        self.assertIn(".v98-ring span{font-size:7px;color:#ff6b23}", out)  # device miniature untouched

    def test_missing_token_fails_loudly(self) -> None:
        with self.assertRaises(theme.PatchError):
            theme.theme_css(self.CSS.replace("--bg-elev:#000;", ""), b"x")

    def test_dark_is_the_default_but_a_saved_choice_wins(self) -> None:
        html = "if(t!=='light'&&t!=='dark'){" + theme.THEME_DEFAULT_OLD + "}"
        self.assertEqual(theme.theme_pages(html), "if(t!=='light'&&t!=='dark'){t='dark';}")
        self.assertEqual(theme.theme_pages(theme.theme_pages(html)), theme.theme_pages(html))

    def test_light_palette_meets_wcag_aa(self) -> None:
        def lum(h):
            r, g, b = (int(h[i:i + 2], 16) / 255 for i in (1, 3, 5))
            f = lambda c: c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
            return .2126 * f(r) + .7152 * f(g) + .0722 * f(b)
        ratio = lambda a, b: (max(lum(a), lum(b)) + .05) / (min(lum(a), lum(b)) + .05)
        for palette in (theme.LIGHT, theme.DARK):
            for fg in ("--text", "--text-mid", "--text-dim", "--accent", "--danger", "--success", "--warn"):
                for bg in ("--bg", "--bg-elev", "--bg-sub"):
                    self.assertGreaterEqual(ratio(palette[fg], palette[bg]), 4.5, f"{fg} on {bg}")


if __name__ == "__main__":
    unittest.main()
