#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
OUT="$ROOT/diagnostics/runs/$(date +%Y%m%d-%H%M%S)"
mkdir -p "$OUT"

PORT="${1:-}"

if [[ -z "$PORT" ]]; then
  PORT=$(ls /dev/cu.* 2>/dev/null | grep -E 'usbmodem|Maker' | head -1 || true)
fi

{
  echo "Waveshare ESP32 Diagnostics"
  echo "==========================="
  echo "Date: $(date)"
  echo "Repo: $ROOT"
  echo "Port: ${PORT:-not detected}"
  echo
  echo "Git:"
  git -C "$ROOT" rev-parse HEAD 2>/dev/null || true
  echo
  echo "ESP-IDF:"
  idf.py --version 2>/dev/null || true
} > "$OUT/environment.txt"

{
  echo "Serial capture"
  echo "=============="
  echo "Port: ${PORT:-not detected}"
  echo
} > "$OUT/serial.log"

if [[ -n "$PORT" ]]; then
  echo "Capturing 20 seconds of serial output..."
  timeout 20 screen "$PORT" 115200 >> "$OUT/serial.log" 2>&1 || true
else
  echo "No ESP32 serial port detected" >> "$OUT/serial.log"
fi

if [[ -d "$ROOT/firmware/build" ]]; then
  find "$ROOT/firmware/build" -maxdepth 2 -type f \( -name '*.elf' -o -name 'flasher_args.json' \) > "$OUT/build_artifacts.txt" || true
fi

printf '\nDiagnostics saved: %s\n' "$OUT"
