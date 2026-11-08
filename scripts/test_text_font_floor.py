import importlib.util
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location("floor", Path(__file__).with_name("validate_text_font_floor.py"))
floor = importlib.util.module_from_spec(spec)
spec.loader.exec_module(floor)

GOOD = Path(floor.ROOT / floor.FONTS_CPP).read_text(encoding="utf-8")


def problems_for(text):
    out = []
    floor.check_fonts_cpp(text, out)
    return out


class TextFontFloor(unittest.TestCase):
    def test_current_fonts_cpp_passes(self):
        self.assertEqual(problems_for(GOOD), [])

    def test_small_maps_to_a_smaller_face_fails(self):
        self.assertTrue(problems_for(GOOD.replace("FONT_SMALL:  return kWorkshopArchivoFonts.vlw[kFace14]", "FONT_SMALL:  return kWorkshopArchivoFonts.vlw[kFace12]")))

    def test_figtree_table_fails(self):
        self.assertTrue(problems_for('#include "fonts/inter_10.h"\n' + GOOD))

    def test_foreign_loadfont_fails(self):
        self.assertTrue(problems_for(GOOD.replace("gfx.loadFont(face)", "gfx.loadFont(inter_10)")))

    def test_tiny_bitmap_fallback_fails(self):
        self.assertTrue(problems_for(GOOD.replace("gfx.setTextFont(2); break;  // 16 px\n        case FONT_BODY", "gfx.setTextFont(1); break;\n        case FONT_BODY")))

    def test_scope_flags_small_builtin_and_shrunk_text(self):
        for line in ("tft.setTextFont(1);", "g.setFont(&fonts::Font0);", "tft.setTextSize(0.8f);"):
            self.assertTrue(floor.SMALL_BUILTIN.search(line) or floor.TEXT_SIZE.search(line), line)
        for line in ("tft.setTextFont(6);", "tft.setTextSize(1);", "g.setTextSize(1.0f);"):
            self.assertFalse(floor.SMALL_BUILTIN.search(line) or floor.TEXT_SIZE.search(line), line)


if __name__ == "__main__":
    unittest.main()
