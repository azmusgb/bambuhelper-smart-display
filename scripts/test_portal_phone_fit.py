#!/usr/bin/env python3
"""Unit tests for apply_workshop_os12_portal_phone_fit.py and its validator."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import apply_workshop_os12_portal_phone_fit as fit  # noqa: E402
import validate_os12_portal_phone_fit as check  # noqa: E402
from scripts.smart_home_patch_utils import PatchError  # noqa: E402

CSS = ("/* x, consolidated at build time by y */\n.app{display:grid}\n.topbar .hamburger{width:36px}\n"
       ".icon-btn{width:40px}\n.section input[type=\"color\"]{width:36px}\n.v96-tab{padding:10px}\n"
       ".os12-security-control{display:grid}\n")


def make_tree(d: Path, css: str = CSS) -> Path:
    (d / "web").mkdir()
    (d / "src").mkdir()
    (d / "include").mkdir()
    (d / "web/app.css").write_text(css)
    (d / "web/app.js").write_text("var s='.v92-build-pill{color:#ff9b68!important}';")
    (d / "src/web_server.cpp").write_text(fit.PAGE_EDITS[0][1])
    (d / "include/web_pages.h").write_text("\n".join(old for rel, old, _n, _l in fit.PAGE_EDITS[1:]))
    return d


class PhoneFitTests(unittest.TestCase):
    def test_layer_is_appended_once(self) -> None:
        once = fit.apply_css(CSS)
        self.assertEqual(fit.apply_css(once), once)
        self.assertEqual(once.count(fit.MARKER), 1)
        self.assertTrue(once.startswith(CSS.rstrip("\n")))

    def test_requires_consolidated_stylesheet(self) -> None:
        with self.assertRaises(PatchError):
            fit.apply_css(".topbar .hamburger{width:36px}")

    def test_missing_selector_fails_loud(self) -> None:
        with self.assertRaises(PatchError):
            fit.apply_css(CSS.replace(".v96-tab{", ".v97-tab{"))

    def test_light_and_dark_scoping(self) -> None:
        layer = fit.apply_css(CSS)[len(CSS):]
        self.assertIn('html[data-theme="light"]{--accent:#0d7068;', layer)
        # No unscoped colour rule: dark keeps its palette apart from the white-on-fill fixes.
        for line in layer.splitlines():
            if "color:" in line and "data-theme" not in line:
                self.fail(f"unscoped colour rule: {line}")

    def test_tree_apply_is_idempotent_and_validates(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            tree = make_tree(Path(d))
            fit.apply(tree)
            fit.apply(tree)
            check.check_tree(tree)
            self.assertIn("min-height:44px", (tree / "src/web_server.cpp").read_text())

    def test_page_anchor_missing_fails_loud(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            tree = make_tree(Path(d))
            (tree / "include/web_pages.h").write_text("")
            with self.assertRaises(PatchError):
                fit.apply(tree)

    def test_validator_rejects_unpatched_tree(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(check.ValidationError):
                check.check_tree(make_tree(Path(d)))

    def test_light_colours_pass_aa(self) -> None:
        check.check_contrast()
        self.assertLess(check.contrast("#ffffff", "#22b8a9"), 4.5)  # the old light teal failed
        self.assertGreaterEqual(check.contrast("#f4f4f2", fit.LIGHT_TOKENS["--accent"]), 4.5)


if __name__ == "__main__":
    unittest.main()
