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
#
# The bridge is copied to ~/Library/Application Support/x2d-camera-bridge with a VERSION file, and the
# agent runs that copy, so switching branches in a checkout never changes what is running.
set -euo pipefail

LABEL="com.bambuhelper.x2d-camera-bridge"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
LOG="$HOME/Library/Logs/x2d-camera-bridge.log"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
INSTALL_DIR="$HOME/Library/Application Support/x2d-camera-bridge"
DOMAIN="gui/$(id -u)"

case "${1:-}" in
  --uninstall)
    launchctl bootout "$DOMAIN/$LABEL" 2>/dev/null || true
    rm -f "$PLIST"
    rm -rf "$INSTALL_DIR"
    echo "Removed $LABEL"
    exit 0 ;;
  --status)
    launchctl print "$DOMAIN/$LABEL" 2>/dev/null | grep -E '^\s*(state|pid|last exit code) =' || echo "$LABEL is not loaded"
    cat "$INSTALL_DIR/VERSION" 2>/dev/null || echo "no installed copy in $INSTALL_DIR"
    curl -s -m3 http://127.0.0.1:8091/x2d/health.json && echo || echo "bridge not answering on :8091"
    exit 0 ;;
  --) shift ;;
  "") ;;
  *) echo "usage: $0 [--uninstall|--status] [-- bridge args...]" >&2; exit 2 ;;
esac

PYTHON="$(command -v python3)"
FFMPEG="$(command -v ffmpeg)" || { echo "ffmpeg not found on PATH" >&2; exit 1; }

mkdir -p "$INSTALL_DIR"
install -m 644 "$ROOT/tools/x2d_camera_bridge.py" "$INSTALL_DIR/x2d_camera_bridge.py.new"
mv -f "$INSTALL_DIR/x2d_camera_bridge.py.new" "$INSTALL_DIR/x2d_camera_bridge.py"
{
  echo "source: $ROOT"
  echo "commit: $(git -C "$ROOT" describe --always --dirty 2>/dev/null || echo unknown)"
  echo "sha256: $(shasum -a 256 "$INSTALL_DIR/x2d_camera_bridge.py" | cut -d' ' -f1)"
  echo "installed: $(date '+%Y-%m-%d %H:%M:%S %z')"
} >"$INSTALL_DIR/VERSION"

xml() { sed -e 's/&/\&amp;/g' -e 's/</\&lt;/g' -e 's/>/\&gt;/g' <<<"$1"; }
args="    <string>$(xml "$PYTHON")</string>
    <string>-u</string>
    <string>$(xml "$INSTALL_DIR/x2d_camera_bridge.py")</string>
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
  <key>WorkingDirectory</key><string>$(xml "$INSTALL_DIR")</string>
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
# bootout returns before the old agent is gone; bootstrapping too early fails with "Input/output error".
for _ in $(seq 1 20); do launchctl print "$DOMAIN/$LABEL" >/dev/null 2>&1 || break; sleep 0.5; done
launchctl bootstrap "$DOMAIN" "$PLIST"
echo "Installed $LABEL (logs: $LOG)"
