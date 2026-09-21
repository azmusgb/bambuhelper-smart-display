#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="${ROOT:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
TOOL_ROOT="${WORKSHOP_TOOL_ROOT:-$ROOT/.workshop-tools}"
VENV="$TOOL_ROOT/platformio"

python_minor() {
  "$1" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")' 2>/dev/null
}

python_is_supported_for_platformio() {
  local py="$1"
  local version
  [[ -x "$py" ]] || return 1
  version="$(python_minor "$py" || true)"
  case "$version" in
    3.9|3.10|3.11|3.12) return 0 ;;
    *) return 1 ;;
  esac
}

select_platformio_python() {
  local candidate
  local override="${WORKSHOP_PLATFORMIO_PYTHON:-}"

  if [[ -n "$override" ]]; then
    if python_is_supported_for_platformio "$override"; then
      printf '%s\n' "$override"
      return 0
    fi
    echo "ERROR: WORKSHOP_PLATFORMIO_PYTHON is not a supported Python 3.9-3.12 interpreter: $override" >&2
    return 2
  fi

  for candidate in \
    "$(command -v python3.12 2>/dev/null || true)" \
    "$(command -v python3.11 2>/dev/null || true)" \
    "$(command -v python3.10 2>/dev/null || true)" \
    "$(command -v python3.9 2>/dev/null || true)" \
    "/usr/bin/python3" \
    "$(command -v python3 2>/dev/null || true)"; do
    [[ -n "$candidate" ]] || continue
    if python_is_supported_for_platformio "$candidate"; then
      printf '%s\n' "$candidate"
      return 0
    fi
  done

  return 1
}

ensure_platformio_esptool_runtime() {
  local penv_python="$1"
  [[ -x "$penv_python" ]] || return 0

  if "$penv_python" -c 'import intelhex' >/dev/null 2>&1; then
    return 0
  fi

  echo "PlatformIO esptool runtime is missing intelhex; repairing its isolated environment..." >&2
  "$penv_python" -m pip install \
    --disable-pip-version-check \
    'intelhex>=2.3,<3' >&2

  "$penv_python" -c 'import intelhex' >/dev/null 2>&1 || {
    echo "ERROR: PlatformIO environment still cannot import intelhex after repair." >&2
    return 1
  }
}

# The WS350 PlatformIO/SCons image-generation path is known-good in CI on
# Python 3.12. A real macOS bootstrap reproduced the SCons command-rendering
# failure below under Python 3.13 as well as the previously observed 3.14 case:
#   TypeError: unsupported operand type(s) for +: _Null and str
# Fail closed on 3.13+ rather than allowing source compilation to succeed and
# firmware.bin generation to fail later. Keep the toolchain repo-local so an
# arbitrary global PlatformIO/Python installation cannot redefine release bytes.
PYTHON_BIN="$(select_platformio_python || true)"
if [[ -z "$PYTHON_BIN" ]]; then
  echo "ERROR: Workshop OS requires Python 3.9-3.12 for its isolated PlatformIO toolchain." >&2
  echo "Python 3.13+ is intentionally rejected because the WS350 PlatformIO/SCons image-generation path is not reliable under it." >&2
  if [[ "$(uname -s 2>/dev/null || true)" == "Darwin" ]]; then
    echo "Install Python 3.12 with Homebrew: brew install python@3.12" >&2
    echo "Then rerun the bootstrap. The helper will prefer /opt/homebrew/bin/python3.12 when available." >&2
  else
    echo "Install Python 3.12 and rerun the bootstrap." >&2
  fi
  exit 2
fi

EXPECTED_PY_VERSION="$(python_minor "$PYTHON_BIN")"
VENV_REBUILD=0
if [[ -x "$VENV/bin/python" ]]; then
  VENV_PY_VERSION="$(python_minor "$VENV/bin/python" || true)"
  if [[ "$VENV_PY_VERSION" != "$EXPECTED_PY_VERSION" ]]; then
    VENV_REBUILD=1
  fi
fi

if [[ "$VENV_REBUILD" -eq 1 ]]; then
  echo "Rebuilding repo-local PlatformIO environment for Python $EXPECTED_PY_VERSION..." >&2
  rm -rf "$VENV"
fi

if [[ ! -x "$VENV/bin/python" ]]; then
  echo "Provisioning isolated PlatformIO with Python $EXPECTED_PY_VERSION at:" >&2
  echo "  $VENV" >&2
  mkdir -p "$TOOL_ROOT"
  "$PYTHON_BIN" -m venv "$VENV"
fi

if ! python_is_supported_for_platformio "$VENV/bin/python"; then
  echo "ERROR: repo-local PlatformIO environment is bound to an unsupported Python runtime." >&2
  echo "Remove $VENV and rerun after installing Python 3.12." >&2
  exit 3
fi

if [[ ! -x "$VENV/bin/pio" ]]; then
  "$VENV/bin/python" -m pip install \
    --disable-pip-version-check \
    --upgrade pip 'platformio==6.2.0' >&2
fi

[[ -x "$VENV/bin/pio" ]] || {
  echo "ERROR: PlatformIO installation completed without a pio executable." >&2
  exit 3
}

ensure_platformio_esptool_runtime "$VENV/bin/python"

echo "PlatformIO Python: $VENV/bin/python (Python $(python_minor "$VENV/bin/python"))" >&2
"$VENV/bin/pio" --version >&2
printf '%s\n' "$VENV/bin/pio"
