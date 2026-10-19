#!/usr/bin/env bash
# Install (or remove) a per-user launchd agent that keeps the X2D camera bridge
# running: it starts at login and is restarted if it exits.
#
#   bash tools/install_x2d_bridge_agent.sh            # install / update and start
#   bash tools/install_x2d_bridge_agent.sh --uninstall
#   bash tools/install_x2d_bridge_agent.sh --status
#
# Extra arguments after -- are passed to the bridge, e.g. -- --fps 3.
# Logs: ~/Library/Logs/x2d-camera-bridge.log
set -euo pipefail

LABEL="com.bambuhelper.x2d-camera-bridge"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
LOG="$HOME/Library/Logs/x2d-camera-bridge.log"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DOMAIN="gui/$(id -u)"

case "${1:-}" in
  --uninstall)
    launchctl bootout "$DOMAIN/$LABEL" 2>/dev/null || true
    rm -f "$PLIST"
    echo "Removed $LABEL"
    exit 0 ;;
  --status)
    launchctl print "$DOMAIN/$LABEL" 2>/dev/null | grep -E '^\s*(state|pid|last exit code) =' || echo "$LABEL is not loaded"
    curl -s -m3 http://127.0.0.1:8091/x2d/health.json && echo || echo "bridge not answering on :8091"
    exit 0 ;;
  --) shift ;;
  "") ;;
  *) echo "usage: $0 [--uninstall|--status] [-- bridge args...]" >&2; exit 2 ;;
esac

PYTHON="$(command -v python3)"
FFMPEG="$(command -v ffmpeg)" || { echo "ffmpeg not found on PATH" >&2; exit 1; }

xml() { sed -e 's/&/\&amp;/g' -e 's/</\&lt;/g' -e 's/>/\&gt;/g' <<<"$1"; }
args="    <string>$(xml "$PYTHON")</string>
    <string>-u</string>
    <string>$(xml "$ROOT/tools/x2d_camera_bridge.py")</string>
    <string>--ffmpeg</string>
    <string>$(xml "$FFMPEG")</string>"
for a in "$@"; do args+=$'\n'"    <string>$(xml "$a")</string>"; done

mkdir -p "$(dirname "$PLIST")" "$(dirname "$LOG")"
cat >"$PLIST" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key>
  <array>
$args
  </array>
  <key>WorkingDirectory</key><string>$(xml "$ROOT")</string>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>ThrottleInterval</key><integer>10</integer>
  <key>ProcessType</key><string>Background</string>
  <key>StandardOutPath</key><string>$(xml "$LOG")</string>
  <key>StandardErrorPath</key><string>$(xml "$LOG")</string>
</dict>
</plist>
PLIST
plutil -lint "$PLIST" >/dev/null

launchctl bootout "$DOMAIN/$LABEL" 2>/dev/null || true
launchctl bootstrap "$DOMAIN" "$PLIST"
echo "Installed $LABEL (logs: $LOG)"
