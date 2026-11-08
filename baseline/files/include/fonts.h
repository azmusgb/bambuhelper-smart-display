#ifndef FONTS_H
#define FONTS_H

#include <LovyanGFX.hpp>

// The display's text faces are the kit's Archivo VLW files (display-kit K3: Archivo everywhere, nothing under 14 px).
// Each id keeps its old name so existing logic reads the same; the size is the nearest kit face of 14 px or more.
enum FontID : uint8_t {
    FONT_NONE   = 0,
    FONT_SMALL  = 1,   // Archivo 14 px (Fs3), was Figtree 12 px
    FONT_BODY   = 2,   // Archivo 16 px (Fs4), was Figtree 16 px
    FONT_LARGE  = 4,   // Archivo 20 px (Fs5), was Figtree 22 px
    FONT_XLARGE = 5,   // Archivo 26 px (Fs6), was Figtree 26 px
    FONT_7SEG   = 7,   // Built-in 7-segment (kept for clock displays)
};

// Sets the active font. Caches the last selection - calling setFont() repeatedly
// with the same id is a no-op. If a VLW font fails to load (e.g. heap exhausted)
// the helper falls back to a built-in bitmap font that is also 16 px or taller instead of
// silently leaving the previous font (or Font0) selected.
// Note: parameter is named `gfx` (not `tft`) because display_ui.h defines
// a `#define tft (*tft_ptr)` macro for the JC3248W535 sprite redirection,
// which would otherwise mangle this declaration when both headers are
// included in the same translation unit.
void setFont(lgfx::LovyanGFX& gfx, FontID id);

// Load a VLW font into an arbitrary render target (e.g. an LGFX_Sprite),
// bypassing setFont()'s last-selection cache — that cache tracks the main
// panel only and would skip the load on a second target. Returns false when
// the id has no VLW blob (FONT_7SEG / FONT_NONE) or the load fails.
bool loadFontInto(lgfx::LovyanGFX& gfx, FontID id);

#endif // FONTS_H
