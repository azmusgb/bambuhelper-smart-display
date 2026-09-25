#!/usr/bin/env python3
"""Capture selected printer MQTT camera telemetry as read-only Workshop OS state.

This layer does not create a second printer authority. It extends the existing
BambuState parser with fields observed in the printer's own push_status report
so the WS350 can present transport capability truth (for example, liveview on
while LAN RTSP remains disabled).
"""
from __future__ import annotations

import argparse
from pathlib import Path
import sys as _sys
from pathlib import Path as _Path
_here = _Path(__file__).resolve().parent
if str(_here) not in _sys.path:
    _sys.path.insert(0, str(_here))
from scripts.smart_home_patch_utils import PatchError




def load(path: Path) -> str:
    if not path.is_file():
        raise PatchError(f"missing reconstructed source: {path}")
    return path.read_text(encoding="utf-8")


def once(text: str, old: str, new: str, label: str) -> str:
    if new in text:
        return text
    n = text.count(old)
    if n != 1:
        raise PatchError(f"{label}: expected one anchor, found {n}")
    return text.replace(old, new, 1)


def apply(repo: Path) -> None:
    state_path = repo / "include" / "bambu_state.h"
    mqtt_path = repo / "src" / "bambu_mqtt.cpp"
    state = load(state_path)
    mqtt = load(mqtt_path)

    state = once(
        state,
        "  int8_t wifiSignal;          // RSSI in dBm\n",
        """  int8_t wifiSignal;          // RSSI in dBm
  bool ipcamSeen;             // printer reported print.ipcam
  bool liveviewPreview;       // print.ipcam.liveview_preview
  bool rtspEnabled;           // true only when printer reports a non-disabled RTSP URL
  char cameraResolution[12];  // printer-reported live-view resolution
  bool brtcServiceEnabled;    // print.ipcam.brtc_service == "enable"
  bool tutkServiceEnabled;    // print.ipcam.tutk_server == "enable"
""",
        "BambuState ipcam telemetry",
    )

    mqtt = once(
        mqtt,
        '  pf["wifi_signal"] = true;\n',
        '''  pf["wifi_signal"] = true;
  pf["ipcam"]["liveview_preview"] = true;
  pf["ipcam"]["rtsp_url"] = true;
  pf["ipcam"]["resolution"] = true;
  pf["ipcam"]["brtc_service"] = true;
  pf["ipcam"]["tutk_server"] = true;
''',
        "MQTT ipcam filter",
    )

    mqtt = once(
        mqtt,
        '  s.wifiSignal = 0;\n',
        '''  s.wifiSignal = 0;
  s.ipcamSeen = false;
  s.liveviewPreview = false;
  s.rtspEnabled = false;
  s.cameraResolution[0] = '\\0';
  s.brtcServiceEnabled = false;
  s.tutkServiceEnabled = false;
''',
        "clear MQTT ipcam state",
    )

    parse = '''  JsonObject ipcam = doc["print"]["ipcam"];
  if (!ipcam.isNull()) {
    s.ipcamSeen = true;
    if (ipcam["liveview_preview"].is<bool>())
      s.liveviewPreview = ipcam["liveview_preview"].as<bool>();
    if (ipcam["resolution"].is<const char*>())
      strlcpy(s.cameraResolution, ipcam["resolution"].as<const char*>(), sizeof(s.cameraResolution));
    if (ipcam["brtc_service"].is<const char*>())
      s.brtcServiceEnabled = strcmp(ipcam["brtc_service"].as<const char*>(), "enable") == 0;
    if (ipcam["tutk_server"].is<const char*>())
      s.tutkServiceEnabled = strcmp(ipcam["tutk_server"].as<const char*>(), "enable") == 0;
    if (ipcam["rtsp_url"].is<const char*>()) {
      const char* value = ipcam["rtsp_url"].as<const char*>();
      s.rtspEnabled = value && value[0] && strcmp(value, "disable") != 0;
    }
  }

'''
    anchor = '''  // Deferred activeTray sources (resolved after AMS unit loop)
'''
    mqtt = once(mqtt, anchor, parse + anchor, "MQTT ipcam parse")

    state_path.write_text(state, encoding="utf-8")
    mqtt_path.write_text(mqtt, encoding="utf-8")
    print("Workshop OS 12 read-only MQTT camera telemetry installed")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    if not args.apply:
        raise SystemExit("refusing to modify source without --apply")
    try:
        apply(Path(args.repo).resolve())
    except PatchError as exc:
        raise SystemExit(f"FAIL: {exc}") from exc
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
