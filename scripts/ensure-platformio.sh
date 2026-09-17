#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="${ROOT:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
TOOL_ROOT="${WORKSHOP_TOOL_ROOT:-$ROOT/.workshop-tools}"
VENV="$TOOL_ROOT/platformio"

# PlatformIO's packaged esptool is sometimes invoked directly by the guarded
# WS350 bootstrap helper. On macOS, a Homebrew/global `pio` can be healthy for
# normal PlatformIO builds while its managed Python environment is missing the
# `intelhex` module required by tool-esptoolpy. Repair only that isolated
# PlatformIO environment; never install into or weaken the system Python.
ensure_platformio_esptool_runtime() {
  local penv_python="$HOME/.platformio/penv/bin/python"

  # Global/Homebrew PlatformIO normally owns this isolated penv. Provision the
  # dependency before the ESP32 package is populated so a first bootstrap run
  # cannot build successfully and then fail at the direct chip probe.
  [[ -x "$penv_python" ]] || return 0

  if "$penv_python" -c 'import intelhex' >/dev/null 2>&1; then
    return 0
  fi

  echo "PlatformIO esptool runtime is missing intelhex; repairing its isolated penv..." >&2
  "$penv_python" -m pip install \
    --disable-pip-version-check \
    'intelhex>=2.3,<3' >&2

  "$penv_python" -c 'import intelhex' >/dev/null 2>&1 || {
    echo "ERROR: PlatformIO penv still cannot import intelhex after repair." >&2
    return 1
  }
}

# Print only the resolved pio executable on stdout. Human-readable setup
# progress goes to stderr so callers can safely capture this command.
if command -v pio >/dev/null 2>&1; then
  ensure_platformio_esptool_runtime
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
