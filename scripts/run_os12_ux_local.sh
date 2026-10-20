#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="${ROOT:-$(git rev-parse --show-toplevel)}"
BUILD="${BUILD:-/tmp/ws350-os12-ux-build}"
OS12_RELEASE_VERSION="${OS12_RELEASE_VERSION:-12.6.0}"
OS12_SOURCE_SHA="${OS12_SOURCE_SHA:-$(git -C "$ROOT" rev-parse HEAD)}"

cd "$ROOT"

echo "=== Workshop OS 12 UX/control-plane reconstruction ==="
echo "ROOT=$ROOT"
echo "BUILD=$BUILD"
echo "OS12_RELEASE_VERSION=$OS12_RELEASE_VERSION"
echo "OS12_SOURCE_SHA=$OS12_SOURCE_SHA"

BUILD="$BUILD" \
OS12_RELEASE_VERSION="$OS12_RELEASE_VERSION" \
OS12_SOURCE_SHA="$OS12_SOURCE_SHA" \
bash "$ROOT/scripts/run_os12_platform_local.sh"

python3 "$ROOT/apply_workshop_os12_ux_architecture.py" --repo "$BUILD" --apply
python3 "$ROOT/apply_workshop_os12_ux_geometry.py" --repo "$BUILD" --apply
python3 "$ROOT/apply_workshop_os12_ux_physical_fit.py" --repo "$BUILD" --apply
python3 "$ROOT/apply_workshop_os12_ui_finish.py" --repo "$BUILD" --apply
python3 "$ROOT/apply_workshop_os12_product_surface.py" --repo "$BUILD" --apply
python3 "$ROOT/apply_workshop_os12_product_surface_complete.py" --repo "$BUILD" --apply
python3 "$ROOT/apply_workshop_os12_physical_acceptance_refinement.py" --repo "$BUILD" --apply
python3 "$ROOT/apply_workshop_os12_portal_control_plane.py" --repo "$BUILD" --apply
# The device-feed transport is installed by the platform stage. Its browser
# controls are applied only after the OS12 portal owns the integration surface.
python3 "$ROOT/apply_workshop_os12_inventory_service.py" --repo "$BUILD" --source-root "$ROOT" --portal-only --apply
python3 "$ROOT/scripts/validate_os12_inventory_service.py" --repo "$BUILD"
python3 "$ROOT/scripts/validate_os12_ux_architecture.py" --repo "$BUILD"
python3 "$ROOT/scripts/validate_os12_ux_geometry.py" --repo "$BUILD"
python3 "$ROOT/scripts/validate_os12_ux_physical_fit.py" --repo "$BUILD"
python3 "$ROOT/scripts/validate_os12_ui_finish.py" --repo "$BUILD"
python3 "$ROOT/scripts/validate_os12_product_surface.py" --repo "$BUILD"
python3 "$ROOT/scripts/validate_os12_product_surface_complete.py" --repo "$BUILD"
python3 "$ROOT/scripts/validate_os12_physical_acceptance_refinement.py" --repo "$BUILD"

# Validate the hardened control plane; the portal sign-in restore below is the
# final security layer.
python3 "$ROOT/scripts/validate_os12_portal_login.py" --repo "$BUILD"
python3 "$ROOT/scripts/validate_os12_portal_control_plane.py" \
  --repo "$BUILD" \
  --contract "$ROOT/contracts/filament-inventory-device-feed-v1.schema.json"

# Final native WS350 product pass. Earlier validators intentionally prove their
# layer contracts before this presentation-only composition replaces renderers.
python3 "$ROOT/apply_workshop_os12_visual_overhaul.py" --repo "$BUILD" --apply
python3 "$ROOT/scripts/validate_os12_visual_overhaul.py" --repo "$BUILD"

# Real-device 480x320 framebuffer review identified layout and action-mapping
# defects that must remain later than the broad visual composition layer.
python3 "$ROOT/apply_workshop_os12_post_capture_ui_hardening.py" --repo "$BUILD" --apply
python3 "$ROOT/scripts/validate_os12_post_capture_ui_hardening.py" --repo "$BUILD"

# Physical evidence showed the Workshop root had stale hidden v11.25 touch zones
# and did not consume the already-authoritative device-feed runtime snapshot.
python3 "$ROOT/apply_workshop_os12_workshop_surface_runtime.py" --repo "$BUILD" --apply
python3 "$ROOT/scripts/validate_os12_workshop_surface_runtime.py" --repo "$BUILD"

# Focused real-panel polish: hierarchy, status semantics, secondary-action weight,
# settings pictograms, Home inventory projection, and Software Update content.
python3 "$ROOT/apply_workshop_os12_physical_polish.py" --repo "$BUILD" --apply
python3 "$ROOT/scripts/validate_os12_physical_polish.py" --repo "$BUILD"

# Security candidate 12.0.1: the 12.0.0 code-free overlay is retired. Restore
# the documented boot-scoped portal-code session for normal LAN routes, with
# real same-origin provenance for every mutation (docs/portal-auth-v11-20.md).
python3 "$ROOT/apply_workshop_os12_portal_signin_restore.py" --repo "$BUILD" --source-root "$ROOT" --apply
python3 "$ROOT/scripts/validate_os12_portal_signin.py" --repo "$BUILD" --source-root "$ROOT"
python3 -m py_compile "$ROOT/scripts/accept_os12_portal_runtime.py"

# Touch hotfix 12.0.2: the hidden tab bar no longer steals the sub-pages' bottom
# buttons, the stepper "-" touch zone matches the drawn button, and Software
# Update's action button says what it does.
python3 "$ROOT/apply_workshop_os12_touch_hotfix.py" --repo "$BUILD" --apply
python3 "$ROOT/scripts/validate_os12_touch_hotfix.py" --repo "$BUILD"

# Candidate 12.1.0: one read-only, token-checked status route for Local AI.
python3 "$ROOT/apply_workshop_os12_status_lite.py" --repo "$BUILD" --source-root "$ROOT" --apply
python3 "$ROOT/scripts/validate_os12_status_lite.py" --repo "$BUILD" --source-root "$ROOT"
python3 "$ROOT/scripts/validate_os12_portal_signin.py" --repo "$BUILD" --source-root "$ROOT" \
  --extra-public-route "HTTP_GET:/api/status/lite"
python3 -m py_compile "$ROOT/scripts/accept_os12_status_lite_runtime.py"

# 12.1.1: the triple-reset entry to Recovery Safe Mode counts in NVS; RTC
# memory is re-initialised on every non-deep-sleep reset and never got past 1.
python3 "$ROOT/apply_workshop_os12_rapid_reset.py" --repo "$BUILD" --source-root "$ROOT" --apply
python3 "$ROOT/scripts/validate_os12_rapid_reset.py" --repo "$BUILD"

# 12.2.0: a second device-issued key, scoped to GET /api/portal-code only, so
# Local AI can show the Local Portal sign-in code. Before the More overhaul,
# which draws its touchscreen row and reads its prompt.
python3 "$ROOT/apply_workshop_os12_code_token.py" --repo "$BUILD" --source-root "$ROOT" --apply
python3 "$ROOT/scripts/validate_os12_code_token.py" --repo "$BUILD" --source-root "$ROOT"
python3 "$ROOT/scripts/validate_os12_portal_signin.py" --repo "$BUILD" --source-root "$ROOT" \
  --extra-public-route "HTTP_GET:/api/status/lite" \
  --extra-public-route "HTTP_GET:/api/portal-code"
python3 -m py_compile "$ROOT/scripts/accept_os12_code_token_runtime.py"

# 12.1.x More/System overhaul. Owning patch for the More area; keep it last.
# 12.2.1: no stray "|" beside toggles, Local Portal tile fits, and an unsaved
# date format defaults to MM/DD/YYYY (validated by validate_os12_more_overhaul.py).
python3 "$ROOT/apply_workshop_os12_more_overhaul.py" --repo "$BUILD" --source-root "$ROOT" --apply
python3 "$ROOT/scripts/validate_os12_more_overhaul.py" --repo "$BUILD"
# Touchscreen palette: the three role-named RGB565 palettes take LocalAI's colours.
python3 "$ROOT/apply_workshop_os12_device_localai_palette.py" --repo "$BUILD" --apply
# 12.3.x Home, Printer and Workshop tabs on the More design system. Owning
# patch for the three tabs; runs after the More overhaul, whose layout and rows
# it builds on.
python3 "$ROOT/apply_workshop_os12_tabs_overhaul.py" --repo "$BUILD" --source-root "$ROOT" --apply
python3 "$ROOT/scripts/validate_os12_tabs_overhaul.py" --repo "$BUILD"
# 12.3.10 Local AI cards on the calm idle screen (GET /api/display/feed over pinned TLS).
python3 "$ROOT/apply_workshop_os12_localai_feed.py" --repo "$BUILD" --source-root "$ROOT" --apply
python3 "$ROOT/scripts/validate_os12_localai_feed.py" --repo "$BUILD"
# 12.5: the animated boot splash on the LocalAI palette (printed hexagon, sparkle, boot bar, Wi-Fi line).
python3 "$ROOT/apply_workshop_os12_boot_splash.py" --repo "$BUILD" --source-root "$ROOT" --apply
# 12.3.6: WS350 touch and audio fixes from the 12.3.5 physical acceptance:
# changed-row pushes, immediate redraw, pressed highlight; no codec power
# cycling, microphone capture in the audio task, mono DC-free playback and a
# live microphone meter. Changes whole functions of the tab/More layers above.
python3 "$ROOT/apply_workshop_os12_touch_audio_fit.py" --repo "$BUILD" --source-root "$ROOT" --apply
python3 "$ROOT/scripts/validate_os12_touch_audio_fit.py" --repo "$BUILD" --source-root "$ROOT"
# 12.3.8: fixes from the 12.3.6 review: same-origin sign-in, Local AI prompts
# answer only an armed press on the button, a press acts only on the target it
# went down on (the outline follows the finger), no /audio/mic/echo, a
# DC-free microphone meter and a gated recording buffer.
python3 "$ROOT/apply_workshop_os12_review_hardening.py" --repo "$BUILD" --source-root "$ROOT" --apply
python3 "$ROOT/scripts/validate_os12_review_hardening.py" --repo "$BUILD" --source-root "$ROOT"
# 12.3.9: glanceability and legibility from the 12.3.8 UX critique: a 48 px
# print percentage with time left and one done-at time beside it on Home and
# Printer, 14 px row values and toasts, muted not-set-up reasons, and the
# camera picture from the header to the tab bar. The drawing is in the
# design-system sources installed above; this layer wires the camera area.
python3 "$ROOT/apply_workshop_os12_glance_legibility.py" --repo "$BUILD" --apply
python3 "$ROOT/scripts/validate_os12_glance_legibility.py" --repo "$BUILD"
# The finished tree still sends every physical printer command through the
# OS12 facade, and Stop from exactly one (hold-guarded) place.
python3 "$ROOT/scripts/validate_os12_control_boundary.py" --repo "$BUILD"
# The finished tree: both Local AI keys still have exactly their own route.
python3 "$ROOT/scripts/validate_os12_code_token.py" --repo "$BUILD" --source-root "$ROOT" --final
python3 "$ROOT/scripts/validate_os12_status_lite.py" --repo "$BUILD" --source-root "$ROOT"

# Portal stylesheet: drop what the 24 appended CSS layers already override and
# fix muted-text contrast and sub-10px text. Must follow every overlay that
# appends to web/app.css; it only rewrites that file.
python3 "$ROOT/apply_workshop_os12_portal_css_consolidate.py" --repo "$BUILD" --apply
# Then one type/radius/breakpoint/colour scale: small, measured visual changes.
python3 "$ROOT/apply_workshop_os12_portal_design_scale.py" --repo "$BUILD" --apply
# 12.3.5: 44 px tap targets on phones and WCAG AA colours in both themes.
python3 "$ROOT/apply_workshop_os12_portal_phone_fit.py" --repo "$BUILD" --apply
python3 "$ROOT/scripts/validate_os12_portal_phone_fit.py" --repo "$BUILD"
# Then the LocalAI design system: palette, type, radii and Figtree (dark by default).
python3 "$ROOT/apply_workshop_os12_portal_localai_theme.py" --repo "$BUILD" --apply
# Version labels show the running release instead of v11.28 / 12.0.0.
python3 "$ROOT/apply_workshop_os12_portal_release_labels.py" --repo "$BUILD" --apply
# LocalAI-style icon rail on desktop, icons in the phone drawer.
python3 "$ROOT/apply_workshop_os12_portal_icon_rail.py" --repo "$BUILD" --apply
# The finished portal boots: _profileCaps is initialised before boot() reads
# it, and nothing that starts hidden is shown by an app.css display rule.
# Runs after the last layer that edits web/app.css.
python3 "$ROOT/scripts/validate_os12_portal_boot.py" --repo "$BUILD"

if [[ "${1:-}" == "--build" ]]; then
  PIO_BIN="$(ROOT="$ROOT" bash "$ROOT/scripts/ensure-platformio.sh")"
  [[ -x "$PIO_BIN" ]] || { echo 'FAIL: pio unavailable after isolated setup' >&2; exit 1; }
  echo "PlatformIO: $PIO_BIN"
  "$PIO_BIN" --version

  echo "=== Build WS350 OS12 signed-in local-portal candidate ==="
  # Install library deps first: a build that also installs them can fail silently.
  # The PlatformIO registry occasionally drops a download (HTTPClientError);
  # retry instead of failing the whole build on one network hiccup.
  for attempt in 1 2 3; do
    if (cd "$BUILD" && "$PIO_BIN" pkg install -e ws_lcd_350 -e jc3248w535 >/dev/null); then break; fi
    if [[ "$attempt" -eq 3 ]]; then echo "FAIL: pio pkg install failed 3 times" >&2; exit 1; fi
    echo "pio pkg install failed (attempt $attempt of 3); retrying in $((attempt * 15)) s" >&2
    sleep $((attempt * 15))
  done
  (cd "$BUILD" && "$PIO_BIN" run -e ws_lcd_350)
  test -s "$BUILD/.pio/build/ws_lcd_350/firmware.bin" || { echo 'FAIL: WS350 image missing' >&2; exit 1; }

  echo "=== Cross-board compile regression ==="
  (cd "$BUILD" && "$PIO_BIN" run -e jc3248w535)
  test -s "$BUILD/.pio/build/jc3248w535/firmware.bin" || { echo 'FAIL: cross-board image missing' >&2; exit 1; }
fi

echo "=== OS12 portal control-plane reconstruction complete ==="
echo "Release identity: Workshop OS $OS12_RELEASE_VERSION @ $OS12_SOURCE_SHA"
echo "Root portal IA: Home / Printer / Workshop / More; final WS350 visual overhaul, post-capture hardening, Workshop runtime repair, and focused physical product-polish pass applied across shell, hierarchy, cards, rows, controls, media and system surfaces."
echo "Portal identity: Workshop OS / WS350; legacy Waveshare Home branding removed from primary surfaces."
echo "Portal security: boot-scoped portal-code session required for normal LAN routes; the code is shown on System -> Local Portal."
echo "Mutation security: a valid session plus real Origin/Referer same-origin provenance (sign-in too); no client marker header is trusted."
echo "Status token: GET /api/status/lite only, bearer token approved on the touchscreen, digest-only storage, no control access."
echo "Sign-in code key: GET /api/portal-code only, separate wsc_ key approved on the touchscreen, digest-only storage, its own lock-out (only a wrong wsc_ key counts), never the sign-in one."
echo "Inventory authority: Filament Inventory device-feed v1 contract; printer AMS telemetry never creates canonical inventory facts."
echo "Home/Workshop: consume the same profile-scoped Filament Inventory projection; Unknown/Undetermined is preserved when authoritative evidence is absent."
echo "Physical acceptance: REQUIRED before integration into the canonical bootstrap/update path."
echo "Stable promotion: forbidden by this script."
