#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="${ROOT:-$(git rev-parse --show-toplevel)}"
BUILD="${BUILD:-/tmp/ws350-os12-ux-build}"
OS12_RELEASE_VERSION="${OS12_RELEASE_VERSION:-12.0.0}"
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

# Validate the hardened control plane first, then apply the intentional final
# production policy: no user-facing device code on the trusted local LAN.
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

python3 "$ROOT/apply_workshop_os12_code_free_portal.py" --repo "$BUILD" --apply
python3 "$ROOT/scripts/validate_os12_code_free_portal.py" --repo "$BUILD"
python3 -m py_compile "$ROOT/scripts/accept_os12_code_free_portal_runtime.py"

if [[ "${1:-}" == "--build" ]]; then
  PIO_BIN="$(ROOT="$ROOT" bash "$ROOT/scripts/ensure-platformio.sh")"
  [[ -x "$PIO_BIN" ]] || { echo 'FAIL: pio unavailable after isolated setup' >&2; exit 1; }
  echo "PlatformIO: $PIO_BIN"
  "$PIO_BIN" --version

  echo "=== Build WS350 OS12 code-free local-portal candidate ==="
  (cd "$BUILD" && "$PIO_BIN" run -e ws_lcd_350)
  test -s "$BUILD/.pio/build/ws_lcd_350/firmware.bin" || { echo 'FAIL: WS350 image missing' >&2; exit 1; }

  echo "=== Cross-board compile regression ==="
  (cd "$BUILD" && "$PIO_BIN" run -e jc3248w535)
  test -s "$BUILD/.pio/build/jc3248w535/firmware.bin" || { echo 'FAIL: cross-board image missing' >&2; exit 1; }
fi

echo "=== OS12 portal control-plane reconstruction complete ==="
echo "Release identity: Workshop OS $OS12_RELEASE_VERSION @ $OS12_SOURCE_SHA"
echo "Root portal IA: Home / Printer / Workshop / More; final WS350 visual overhaul plus post-capture 480x320 hardening applied across shell, hierarchy, cards, rows, controls, media and system surfaces."
echo "Portal identity: Workshop OS / WS350; legacy Waveshare Home branding removed from primary surfaces."
echo "Portal security: device code disabled by product policy; local portal opens directly on the trusted LAN."
echo "Mutation security: same-origin enforcement remains mandatory; no user-entered device code or portal session is required."
echo "Inventory authority: Filament Inventory device-feed v1 contract; printer AMS telemetry never creates canonical inventory facts."
echo "Home/Workshop: Unknown/Undetermined until authoritative profile-scoped inventory/readiness evidence is available."
echo "Physical acceptance: REQUIRED before integration into the canonical bootstrap/update path."
echo "Stable promotion: forbidden by this script."
