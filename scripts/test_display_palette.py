#!/usr/bin/env python3
"""Tests for the display palette generator (display-kit K1) and the raw-colour guard (K7)."""
from __future__ import annotations

import importlib.util
import json
import re
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


gen = load("generate_display_palette")
guard = load("validate_ui_raw_colours")


def rgb565(hex_colour: str) -> int:
    r, g, b = (int(hex_colour[i:i + 2], 16) for i in (1, 3, 5))
    return ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3)


class PaletteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tokens = gen.read_tokens()

    def test_tokens_are_the_kits_dark_values(self) -> None:
        kit = json.loads((ROOT / "assets" / "ui" / "tokens.json").read_text(encoding="utf-8"))["color"]
        self.assertEqual(self.tokens["ACCENT"], rgb565(kit["accent"]["dark"]))
        self.assertEqual(self.tokens["BG"], rgb565(kit["bg"]["dark"]))
        self.assertEqual(self.tokens["BAD"], rgb565(kit["bad"]["dark"]))

    def test_every_role_names_a_token(self) -> None:
        gen.validate(self.tokens)

    def test_an_unknown_token_fails(self) -> None:
        saved = gen.ROLES["UI"]["UI_BG"]
        gen.ROLES["UI"]["UI_BG"] = "NOT_A_TOKEN"
        try:
            with self.assertRaises(SystemExit):
                gen.validate(self.tokens)
        finally:
            gen.ROLES["UI"]["UI_BG"] = saved

    def test_every_old_constant_in_the_sources_has_a_role(self) -> None:
        """A UI_*, OS12V_*, C10_* or W25_* palette constant defined anywhere in the tracked sources is mapped."""
        files = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, check=True, capture_output=True).stdout.decode().split("\0")
        pattern = re.compile(r"uint16_t\s+((?:UI|OS12V|C10|W25)_[A-Z0-9_]+)\s*=\s*0x[0-9A-Fa-f]{4}")
        found: set[str] = set()
        for name in files:
            if not name or not re.search(r"\.(py|cppfrag|hpp|h|cpp)$", name) or name.startswith(("scripts/", "tests/")):
                continue
            path = ROOT / name
            if path.is_file():
                found |= set(pattern.findall(path.read_text(encoding="utf-8", errors="replace")))
        self.assertTrue(found, "no palette constants found: the scan is broken")
        self.assertEqual(sorted(found - set(gen.all_roles())), [], "constants with no mapping")

    def test_the_accent_is_not_orange_or_blue(self) -> None:
        for name in ("UI_ORANGE", "OS12V_ACCENT", "C10_ACCENT", "W25_ACCENT", "UI_CYAN", "UI_BLUE"):
            self.assertEqual(gen.all_roles()[name], "ACCENT", name)
        accent = self.tokens["ACCENT"]
        r, g, b = (accent >> 11) << 3, ((accent >> 5) & 63) << 2, (accent & 31) << 3
        self.assertTrue(g > r and b > r, "the kit accent is teal: green and blue above red")

    def test_lamps_stay_distinct(self) -> None:
        roles = gen.all_roles()
        lamps = [self.tokens[roles[n]] for n in ("OS12V_ACCENT", "OS12V_GREEN", "OS12V_AMBER", "OS12V_RED")]
        self.assertEqual(len(set(lamps)), 4)

    def test_tint_arithmetic_matches_the_kits_blend(self) -> None:
        self.assertEqual(gen.blend565(0xFFFF, 0x0000, 50), 0x8410)
        self.assertEqual(gen.blend565(0x1234, 0x1234, 37), 0x1234)
        self.assertEqual(gen.blend565(0xF800, 0x0000, 100), 0xF800)
        self.assertEqual(gen.blend565(0xF800, 0x001F, 0), 0x001F)

    def test_the_committed_header_is_what_the_generator_writes(self) -> None:
        version = gen.kit_version()
        self.assertEqual((ROOT / "firmware" / "platform" / "ui" / "display_palette.h").read_text(encoding="utf-8"),
                         gen.render(self.tokens, version))

    def test_the_header_defines_every_role_without_a_literal(self) -> None:
        text = gen.render(self.tokens, "0.0.0")
        for name in gen.all_roles():
            self.assertRegex(text, rf"constexpr uint16_t {name}\s+= (UI_COLOR_[A-Z0-9_]+|uiTint565\()")
        self.assertEqual(guard.offences(text), [])


class GuardTests(unittest.TestCase):
    def test_a_raw_literal_is_an_offence(self) -> None:
        self.assertEqual(guard.offences("tft.fillRect(0,0,4,4,0xF81F);\n"), [1])
        self.assertEqual(guard.offences("x = 0x0000;\ny = 0xABcd;\n"), [1, 2])

    def test_a_new_palette_constant_is_an_offence(self) -> None:
        self.assertEqual(guard.offences("static const uint16_t MY_ORANGE = 0xFBC0;\n"), [1])
        self.assertEqual(guard.offences("static constexpr uint16_t MY_ORANGE = 0xFBC00;\n"), [1])
        self.assertEqual(guard.offences("static const uint16_t MY_GREEN = tft.color565(1, 2, 3);\n"), [1])
        self.assertEqual(guard.offences("#define CLR_X 0xFFFFFF\n"), [1])

    def test_kit_tokens_and_other_numbers_are_not(self) -> None:
        clean = ("static const uint16_t kBsBg = UI_COLOR_BG;\n"
                 "static constexpr uint16_t UI_GLOW = uiTint565(UI_COLOR_ACCENT, UI_COLOR_BG, 14);\n"
                 "tft.fillRect(0, 0, 4, 4, OS12V_ACCENT);\n"
                 "const uint8_t b = 0x7F; const uint32_t m = 0xFF00FF00u; const int z = 0x10000;\n")
        self.assertEqual(guard.offences(clean), [])

    def test_a_new_file_is_a_failure(self) -> None:
        out = guard.problems({"firmware/platform/ui/new.cppfrag": [3]}, {}, None)
        self.assertEqual(len(out), 1)
        self.assertIn("raw colour", out[0])

    def test_a_listed_file_may_not_grow(self) -> None:
        out = guard.problems({"firmware/platform/ui/a.cppfrag": [1, 2, 3]}, {"firmware/platform/ui/a.cppfrag": 2}, None)
        self.assertEqual(len(out), 1)
        self.assertIn("only shrink", out[0])

    def test_a_listed_file_that_shrank_must_lower_its_entry(self) -> None:
        out = guard.problems({"a.py": [1]}, {"a.py": 2}, None)
        self.assertEqual(len(out), 1)
        self.assertIn("lower", out[0])

    def test_a_listed_clean_file_must_be_removed(self) -> None:
        out = guard.problems({}, {"apply_workshop_os12_boot_splash.py": 3}, None)
        self.assertEqual(len(out), 1)
        self.assertIn("remove the entry", out[0])

    def test_the_list_may_not_grow_against_the_base(self) -> None:
        found = {"a.py": [1], "b.py": [1, 2]}
        allowed = {"a.py": 1, "b.py": 2}
        self.assertEqual(guard.problems(found, allowed, {"a.py": 1, "b.py": 2}), [])
        added = guard.problems(found, allowed, {"a.py": 1})
        self.assertEqual(len(added), 1)
        self.assertIn("added", added[0])
        raised = guard.problems(found, allowed, {"a.py": 1, "b.py": 1})
        self.assertEqual(len(raised), 1)
        self.assertIn("raised", raised[0])
        shrank = guard.problems({"a.py": [1]}, {"a.py": 1}, {"a.py": 4, "b.py": 2})
        self.assertEqual(shrank, [])

    def test_the_tree_passes_its_own_list(self) -> None:
        allowed = guard.read_list((ROOT / guard.ALLOWLIST).read_text(encoding="utf-8"))
        self.assertEqual(guard.problems(guard.scan(), allowed, None), [])

    def test_ported_files_are_not_on_the_list(self) -> None:
        allowed = guard.read_list((ROOT / guard.ALLOWLIST).read_text(encoding="utf-8"))
        for name in ("firmware/platform/ui/boot_splash.cppfrag", "firmware/platform/ui/more_pages.cppfrag",
                     "firmware/platform/ui/display_palette.h", "firmware/platform/ui/lgfx_canvas.hpp",
                     "apply_workshop_os12_display_kit_palette.py"):
            self.assertNotIn(name, allowed)


if __name__ == "__main__":
    unittest.main()
