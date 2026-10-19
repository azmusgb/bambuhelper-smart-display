#!/usr/bin/env python3
"""Tests for the WS350 touchscreen LocalAI palette step."""
from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("palette", ROOT / "apply_workshop_os12_device_localai_palette.py")
palette = importlib.util.module_from_spec(spec)
spec.loader.exec_module(palette)


def fixture() -> str:
    kinds = {"OS12V": "static constexpr uint16_t", "C10": "static constexpr uint16_t", "UI": "static const uint16_t"}
    return "".join(f"{kinds[name.split('_')[0]]} {name} = 0x1234; // old colour\n" for name in palette.ROLES) + "void draw() {}\n"


class PaletteTests(unittest.TestCase):
    def test_rgb565_conversion(self) -> None:
        self.assertEqual(palette.rgb565("#ffffff"), 0xFFFF)
        self.assertEqual(palette.rgb565("#000000"), 0x0000)
        self.assertEqual(palette.rgb565("#6cb6ff"), 0x6DBF)

    def test_every_role_is_repainted_and_commented(self) -> None:
        out, changed = palette.repaint(fixture())
        self.assertEqual(changed, len(palette.ROLES))
        self.assertNotIn("0x1234", out)
        self.assertNotIn("old colour", out)
        self.assertIn("OS12V_ACCENT = 0x6DBF; // LocalAI accent #6cb6ff", out)
        self.assertIn("UI_ORANGE = 0x6DBF; // LocalAI accent #6cb6ff", out)
        self.assertIn("C10_ORANGE = 0xFD84; // LocalAI attention #ffb224", out)
        self.assertEqual(out.count(palette.MARKER), 1)

    def test_missing_constant_fails_loudly(self) -> None:
        with self.assertRaises(palette.PatchError):
            palette.repaint(fixture().replace("C10_ACCENT", "C10_ACCENT_OLD"))

    def test_every_role_has_a_colour(self) -> None:
        self.assertTrue(set(palette.ROLES.values()) <= set(palette.DS))


if __name__ == "__main__":
    unittest.main()
