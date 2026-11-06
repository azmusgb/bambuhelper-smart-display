#!/usr/bin/env python3
"""A report the display can't parse is counted and shown on /debug, never stored."""
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
    web = (root / "src/web_server.cpp").read_text(encoding="utf-8")
    for needle in ("uint32_t parseErrors;", "char lastParseError[16];", "uint32_t lastParseErrorLen;",
                   "unsigned long lastParseErrorMs;"):
        if needle not in state:
            raise SystemExit(f"FAIL: state missing {needle!r}")
    start = mqtt.find("  if (err) {\n    MQTT_LOG(\"JSON parse error")
    if start < 0:
        raise SystemExit("FAIL: MQTT parse error branch not found")
    branch = mqtt[start:mqtt.find("    return;\n  }", start)]
    for needle in ("s.parseErrors++;", "strlcpy(s.lastParseError, err.c_str()", "s.lastParseErrorLen = length;",
                   "s.lastParseErrorMs = millis();"):
        if needle not in branch:
            raise SystemExit(f"FAIL: parse error branch missing {needle!r}")
    if "payload" in branch.replace("length", ""):
        raise SystemExit("FAIL: the parse error branch must not keep any of the payload")
    for needle in ('p["parse_errors"] = st.parseErrors;', 'p["last_parse_error"] = st.lastParseError;',
                   'p["last_parse_error_len"] = st.lastParseErrorLen;', 'p["last_parse_error_age_s"]'):
        if needle not in web:
            raise SystemExit(f"FAIL: /debug missing {needle!r}")
    print("PASS: MQTT parse errors are counted and shown on /debug without keeping the payload")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
