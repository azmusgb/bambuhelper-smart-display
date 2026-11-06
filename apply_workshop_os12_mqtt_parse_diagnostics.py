#!/usr/bin/env python3
"""Count printer reports the display could not parse, and show the last error on /debug.

12.9.1 (6 Nov 2026): the WS350 kept receiving X2D reports (messages rising, the
connection up) while its printer state stopped updating for 13 hours, so every
screen showed 0° and no state. The parser's only exit that skips the update is a
JSON parse error, and that error was logged to the USB serial port only. This
layer records it in BambuState so the signed-in /debug page can say how many
reports failed, the last error, and the size of that report. Read-only: it
changes no parsing and stores no payload.
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
    web_path = repo / "src" / "web_server.cpp"
    state = load(state_path)
    mqtt = load(mqtt_path)
    web = load(web_path)

    anchor = '  bool tutkServiceEnabled;    // print.ipcam.tutk_server == "enable"\n'
    state = once(
        state,
        anchor,
        anchor
        + """  uint32_t parseErrors;        // reports that failed to parse since the state was reset
  char lastParseError[16];     // ArduinoJson's code for the last one ("NoMemory", "TooDeep", ...)
  uint32_t lastParseErrorLen;  // its payload size in bytes
  unsigned long lastParseErrorMs;
""",
        "BambuState parse diagnostics",
    )

    mqtt = once(
        mqtt,
        """  if (err) {
    MQTT_LOG("JSON parse error: %s", err.c_str());
    return;
  }
""",
        """  if (err) {
    MQTT_LOG("JSON parse error: %s", err.c_str());
    s.parseErrors++;
    strlcpy(s.lastParseError, err.c_str(), sizeof(s.lastParseError));
    s.lastParseErrorLen = length;
    s.lastParseErrorMs = millis();
    return;
  }
""",
        "MQTT parse error diagnostics",
    )

    web_anchor = '    p["last_print_data_age_s"] = st.lastPrintDataMs > 0 ? (now - st.lastPrintDataMs) / 1000UL : 0;\n'
    web = once(
        web,
        web_anchor,
        web_anchor
        + """    p["parse_errors"] = st.parseErrors;
    if (st.parseErrors > 0) {
      p["last_parse_error"] = st.lastParseError;
      p["last_parse_error_len"] = st.lastParseErrorLen;
      p["last_parse_error_age_s"] = (now - st.lastParseErrorMs) / 1000UL;
    }
""",
        "/debug parse diagnostics",
    )

    state_path.write_text(state, encoding="utf-8")
    mqtt_path.write_text(mqtt, encoding="utf-8")
    web_path.write_text(web, encoding="utf-8")
    print("Workshop OS 12 MQTT parse diagnostics installed")


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
