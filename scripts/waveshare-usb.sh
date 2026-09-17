#!/usr/bin/env bash
set -Eeuo pipefail

# Resolve the Waveshare ESP32-S3 USB JTAG/serial device without depending on
# macOS-assigned /dev/cu.usbmodem#### numbering.

ROOT="${ROOT:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VID_PID="${WAVESHARE_VID_PID:-303A:1001}"
USB_SERIAL="${WAVESHARE_USB_SERIAL:-}"
MONITOR_BAUD="${WAVESHARE_MONITOR_BAUD:-115200}"
PIO_BIN="${PIO_BIN:-}"

usage() {
  cat <<'EOF'
Usage:
  bash scripts/waveshare-usb.sh port
  bash scripts/waveshare-usb.sh list
  bash scripts/waveshare-usb.sh monitor
  bash scripts/waveshare-usb.sh diagnose

Environment overrides:
  WAVESHARE_USB_SERIAL=<serial>   Select one board when multiple matches exist
  WAVESHARE_VID_PID=303A:1001    Override USB VID:PID
  WAVESHARE_MONITOR_BAUD=115200  Override serial-monitor baud rate
  PIO_BIN=/path/to/pio           Explicit PlatformIO executable
EOF
}

resolve_platformio() {
  if [[ -n "$PIO_BIN" && -x "$PIO_BIN" ]]; then
    return 0
  fi
  if command -v pio >/dev/null 2>&1; then
    PIO_BIN="$(command -v pio)"
    return 0
  fi
  if [[ -x "$SCRIPT_DIR/ensure-platformio.sh" ]]; then
    PIO_BIN="$(ROOT="$ROOT" bash "$SCRIPT_DIR/ensure-platformio.sh")"
    [[ -x "$PIO_BIN" ]] && return 0
  fi
  echo "ERROR: PlatformIO could not be resolved." >&2
  echo "Run: bash scripts/ensure-platformio.sh" >&2
  return 1
}

platformio_list() {
  resolve_platformio
  "$PIO_BIN" device list
}

detect_ports() {
  local listing
  listing="$(platformio_list)" || return 1

  awk -v vid="$VID_PID" -v serial="$USB_SERIAL" '
    /^\/dev\/(cu|tty)\./ { port=$1; next }
    /^Hardware ID:/ {
      if (index($0, "USB VID:PID=" vid) > 0 &&
          (serial == "" || index($0, "SER=" serial) > 0)) {
        print port
      }
    }
  ' <<<"$listing"
}

usb_diagnostics() {
  echo "=== PlatformIO serial devices ==="
  platformio_list || true
  echo
  echo "=== macOS /dev/cu.* ==="
  compgen -G '/dev/cu.*' 2>/dev/null || ls -1 /dev/cu.* 2>/dev/null || echo "(none)"
  echo
  echo "=== macOS USB summary ==="
  if command -v system_profiler >/dev/null 2>&1; then
    system_profiler SPUSBDataType 2>/dev/null | grep -A12 -B2 -Ei 'Espressif|303a|USB JTAG|serial|Waveshare' || true
  else
    echo "system_profiler unavailable"
  fi
}

resolve_port() {
  local listing
  if ! listing="$(platformio_list)"; then
    echo "ERROR: unable to enumerate serial devices because PlatformIO failed." >&2
    return 1
  fi

  local -a ports=()
  while IFS= read -r port; do
    [[ -n "$port" ]] && ports+=("$port")
  done < <(
    awk -v vid="$VID_PID" -v serial="$USB_SERIAL" '
      /^\/dev\/(cu|tty)\./ { port=$1; next }
      /^Hardware ID:/ {
        if (index($0, "USB VID:PID=" vid) > 0 &&
            (serial == "" || index($0, "SER=" serial) > 0)) {
          print port
        }
      }
    ' <<<"$listing"
  )

  if (( ${#ports[@]} == 1 )); then
    printf '%s\n' "${ports[0]}"
    return 0
  fi

  if (( ${#ports[@]} == 0 )); then
    echo "ERROR: Waveshare USB device not found (VID:PID $VID_PID)." >&2
    if [[ -n "$USB_SERIAL" ]]; then
      echo "Requested serial: $USB_SERIAL" >&2
    fi
    echo >&2
    echo "$listing" >&2
    echo >&2
    echo "If the display is powered but no Espressif serial device appears, check that the USB cable carries data." >&2
    echo "Then reconnect the WS350 directly to the Mac and run:" >&2
    echo "  bash scripts/waveshare-usb.sh diagnose" >&2
    return 2
  fi

  echo "ERROR: Multiple matching Espressif USB devices were found:" >&2
  printf '  %s\n' "${ports[@]}" >&2
  echo "Set WAVESHARE_USB_SERIAL to select the intended board." >&2
  return 3
}

command="${1:-port}"
case "$command" in
  port)
    resolve_port
    ;;
  list)
    platformio_list
    ;;
  monitor)
    resolve_platformio
    port="$(resolve_port)"
    echo "Waveshare detected at: $port" >&2
    exec "$PIO_BIN" device monitor \
      --port "$port" \
      --baud "$MONITOR_BAUD" \
      --filter time
    ;;
  diagnose)
    usb_diagnostics
    ;;
  -h|--help|help)
    usage
    ;;
  *)
    echo "ERROR: Unknown command '$command'." >&2
    usage >&2
    exit 64
    ;;
esac
