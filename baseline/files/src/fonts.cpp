#include "fonts.h"
#include "workshop_archivo_fonts.h"

// The text faces are the kit's Archivo VLW files, defined once in workshop_archivo_fonts.cpp (generated from
// assets/ui/display/fonts by apply_workshop_os12_display_kit_home.py) in UiFont order: 14, 16, 20, 26 px, readout 34.
// Display-kit K3: Archivo everywhere and no text under 14 px, so no id maps to a smaller face and the bitmap fallback is
// never smaller than 16 px. scripts/validate_text_font_floor.py checks this file.
enum ArchivoFace : uint8_t { kFace14 = 0, kFace16 = 1, kFace20 = 2, kFace26 = 3 };

static FontID currentFont = FONT_NONE;

static const uint8_t* faceFor(FontID id) {
    switch (id) {
        case FONT_SMALL:  return kWorkshopArchivoFonts.vlw[kFace14];
        case FONT_BODY:   return kWorkshopArchivoFonts.vlw[kFace16];
        case FONT_LARGE:  return kWorkshopArchivoFonts.vlw[kFace20];
        case FONT_XLARGE: return kWorkshopArchivoFonts.vlw[kFace26];
        default:          return nullptr;
    }
}

static void applyBitmapFallback(lgfx::LovyanGFX& gfx, FontID id) {
    gfx.unloadFont();
    switch (id) {
        case FONT_SMALL:  gfx.setTextFont(2); break;  // 16 px
        case FONT_BODY:   gfx.setTextFont(2); break;  // 16 px
        case FONT_LARGE:  gfx.setTextFont(4); break;  // 26 px
        case FONT_XLARGE: gfx.setTextFont(4); break;  // 26 px
        default:          gfx.setTextFont(2); break;
    }
}

void setFont(lgfx::LovyanGFX& gfx, FontID id) {
    if (id == currentFont) return;

    switch (id) {
        case FONT_SMALL:
        case FONT_BODY:
        case FONT_LARGE:
        case FONT_XLARGE:
            if (!gfx.loadFont(faceFor(id))) applyBitmapFallback(gfx, id);
            break;
        case FONT_7SEG:
            gfx.unloadFont();
            gfx.setTextFont(7);
            break;
        case FONT_NONE:
        default:
            gfx.unloadFont();
            break;
    }

    currentFont = id;
}

bool loadFontInto(lgfx::LovyanGFX& gfx, FontID id) {
    const uint8_t* face = faceFor(id);
    return face ? gfx.loadFont(face) : false;
}
