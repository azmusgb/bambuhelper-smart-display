#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="${ROOT:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
TOOL_ROOT="${WORKSHOP_TOOL_ROOT:-$ROOT/.workshop-tools}"
VENV="$TOOL_ROOT/platformio"

# Print only the resolved pio executable on stdout. Human-readable setup
# progress goes to stderr so callers can safely capture this command.
if command -v pio >/dev/null 2>&1; then
  command -v pio
  exit 0
fi

if [[ -x "$VENV/bin/pio" ]]; then
  printf '%s\n' "$VENV/bin/pio"
  exit 0
fi

command -v python3 >/dev/null 2>&1 || {
  echo "ERROR: python3 is required to provision the repo-local PlatformIO environment." >&2
  exit 2
}

# Homebrew Python on current macOS releases follows PEP 668 and correctly
# rejects `pip install --user`. Keep PlatformIO isolated in a repo-local venv
# instead of weakening the system Python with --break-system-packages.
echo "PlatformIO not found; provisioning isolated tool environment at:" >&2
echo "  $VENV" >&2
mkdir -p "$TOOL_ROOT"

if [[ ! -x "$VENV/bin/python" ]]; then
  python3 -m venv "$VENV"
fi

"$VENV/bin/python" -m pip install --disable-pip-version-check --upgrade pip platformio >&2
[[ -x "$VENV/bin/pio" ]] || {
  echo "ERROR: PlatformIO installation completed without a pio executable." >&2
  exit 3
}

printf '%s\n' "$VENV/bin/pio"
