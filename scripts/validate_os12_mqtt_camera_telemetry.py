#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    args = ap.parse_args()
    root = Path(args.repo).resolve()
    state = (root / "include/bambu_state.h").read_text(encoding="utf-8")
    mqtt = (root / "src/bambu_mqtt.cpp").read_text(encoding="utf-8")
    for needle in (
        "bool ipcamSeen;",
        "bool liveviewPreview;",
        "bool rtspEnabled;",
        "char cameraResolution[12];",
        "bool brtcServiceEnabled;",
        "bool tutkServiceEnabled;",
    ):
        if needle not in state:
            raise SystemExit(f"FAIL: state missing {needle!r}")
    for needle in (
        'pf["ipcam"]["liveview_preview"] = true;',
        'pf["ipcam"]["rtsp_url"] = true;',
        'pf["ipcam"]["resolution"] = true;',
        'JsonObject ipcam = doc["print"]["ipcam"];',
        'strcmp(value, "disable") != 0',
    ):
        if needle not in mqtt:
            raise SystemExit(f"FAIL: MQTT parser missing {needle!r}")
    parse_block = mqtt[mqtt.find("JsonObject ipcam ="):mqtt.find("// Deferred activeTray sources")]
    if "publish(" in parse_block:
        raise SystemExit("FAIL: telemetry parser must remain read-only")
    if "rtspUrl" in state or "rtspUrl" in parse_block:
        raise SystemExit("FAIL: raw printer RTSP URL must not be retained; keep only capability state")
    print("PASS: printer MQTT camera capability telemetry is captured read-only")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
