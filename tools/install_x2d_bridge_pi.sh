#!/usr/bin/env bash
# Install (or remove) the X2D camera bridge on an always-on Raspberry Pi, run from the Mac.
#
# On the Pi the bridge reads the printer's own LAN stream (no Bambu Studio, no cloud, no Mac), which needs
# "LAN Only Liveview" turned on at the printer's touchscreen. It runs as the system user x2dbridge under systemd
# and waits, doing nothing, until the stream's URL is set.
#
#   bash tools/install_x2d_bridge_pi.sh                 # install / update (host "pi" from ~/.ssh/config)
#   bash tools/install_x2d_bridge_pi.sh --set-code      # asks for the printer's access code, then starts it
#   bash tools/install_x2d_bridge_pi.sh --status
#   bash tools/install_x2d_bridge_pi.sh --uninstall
#
# Environment: PI_HOST (default pi), PRINTER_IP (default 10.0.0.136).
# The access code is typed here, sent to the Pi on stdin and kept in /etc/x2d-bridge/rtsp-url (mode 600,
# owner x2dbridge). It is never put on a command line or in a log.
set -euo pipefail

HOST="${PI_HOST:-pi}"
PRINTER_IP="${PRINTER_IP:-10.0.0.136}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
UNIT=x2d-camera-bridge.service

case "${1:-}" in
  --status)
    ssh "$HOST" "systemctl is-active $UNIT; systemctl status $UNIT --no-pager -n 5 | tail -6; curl -s -m3 http://127.0.0.1:8091/x2d/health.json; echo"
    exit 0 ;;
  --uninstall)
    ssh "$HOST" "sudo systemctl disable --now $UNIT 2>/dev/null || true; sudo rm -f /etc/systemd/system/$UNIT; sudo systemctl daemon-reload; sudo rm -rf /opt/x2d-bridge /etc/x2d-bridge; sudo userdel x2dbridge 2>/dev/null || true"
    echo "Removed the bridge from $HOST"
    exit 0 ;;
  --set-code)
    read -r -s -p "Printer access code (8 characters, from the printer's touchscreen): " code; echo
    [[ "$code" =~ ^[A-Za-z0-9]{8}$ ]] || { echo "That is not an 8-character access code." >&2; exit 1; }
    printf 'bambu://bblp:%s@%s:6000\n' "$code" "$PRINTER_IP" |
      ssh "$HOST" "sudo install -m 600 -o x2dbridge -g x2dbridge /dev/stdin /etc/x2d-bridge/rtsp-url && sudo systemctl restart $UNIT"
    unset code
    echo "Saved on $HOST; the bridge is starting. Check: bash $0 --status"
    exit 0 ;;
  "") ;;
  *) echo "usage: $0 [--set-code|--status|--uninstall]" >&2; exit 2 ;;
esac

scp -q "$ROOT/tools/x2d_camera_bridge.py" "$HOST:/tmp/x2d_camera_bridge.py"
ssh "$HOST" "bash -s" <<REMOTE
set -euo pipefail
command -v ffmpeg >/dev/null || { sudo apt-get update -qq && sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq ffmpeg >/dev/null; }
id x2dbridge >/dev/null 2>&1 || sudo useradd --system --no-create-home --shell /usr/sbin/nologin x2dbridge
sudo install -d -m 755 /opt/x2d-bridge
sudo install -m 644 /tmp/x2d_camera_bridge.py /opt/x2d-bridge/x2d_camera_bridge.py
rm -f /tmp/x2d_camera_bridge.py
sudo install -d -m 700 -o x2dbridge -g x2dbridge /etc/x2d-bridge
sudo tee /etc/systemd/system/$UNIT >/dev/null <<'EOF'
[Unit]
Description=X2D camera bridge for the Workshop display (printer LAN stream -> latest JPEG on :8091)
After=network-online.target
Wants=network-online.target
# Idle until the stream URL (with the access code) is set: install_x2d_bridge_pi.sh --set-code
ConditionPathExists=/etc/x2d-bridge/rtsp-url

[Service]
User=x2dbridge
Group=x2dbridge
ExecStart=/usr/bin/python3 -u /opt/x2d-bridge/x2d_camera_bridge.py --rtsp-url-file /etc/x2d-bridge/rtsp-url --ffmpeg /usr/bin/ffmpeg
Restart=always
RestartSec=10
NoNewPrivileges=yes
ProtectSystem=strict
ProtectHome=yes
PrivateTmp=yes
PrivateDevices=yes
MemoryMax=256M
CPUQuota=80%

[Install]
WantedBy=multi-user.target
EOF
sudo systemctl daemon-reload
sudo systemctl enable $UNIT >/dev/null 2>&1
if [ -f /etc/x2d-bridge/rtsp-url ]; then sudo systemctl restart $UNIT; fi
echo "ffmpeg: \$(ffmpeg -version | head -1 | cut -d' ' -f1-3)"
REMOTE
echo "Installed on $HOST. Next: turn on LAN Only Liveview at the printer, then: bash $0 --set-code"
