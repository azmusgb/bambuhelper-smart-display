#!/usr/bin/env bash
set -euo pipefail

echo "Connected serial devices:"
ls /dev/cu.* 2>/dev/null || true

echo

echo "Likely ESP32 devices:"
ls /dev/cu.* 2>/dev/null | grep -Ei 'usbmodem|maker|esp|wch|serial' || echo "No obvious ESP32 port found"

echo

echo "Usage:"
echo "  ./tools/diagnostics/collect_diagnostics.sh /dev/cu.Maker-XXXX"
