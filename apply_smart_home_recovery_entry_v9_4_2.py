#!/usr/bin/env python3
from pathlib import Path
import argparse


class PatchError(RuntimeError):
    pass


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise PatchError(f"{label}: expected exactly 1 match, found {count}")
    return text.replace(old, new, 1)


def apply(repo: Path) -> None:
    p = repo / "src" / "web_server.cpp"
    text = p.read_text(encoding="utf-8")

    text = replace_once(
        text,
        '''static void handleRoot() {
  if (isAPMode()) {
    serveApPage();
  } else {
    serveMainPage();
  }
}
''',
        '''static void handleRoot() {
  // Safe Mode is a rescue environment, not first-time Wi-Fi onboarding. Make
  // the recovery console the unavoidable landing page so the owner never has
  // to remember a hidden path while repairing a broken candidate firmware.
  if (isAPMode() && recoverySafeModeActive()) {
    server.sendHeader("Cache-Control", "no-cache, no-store, must-revalidate");
    server.sendHeader("Location", "/recovery");
    server.send(302, "text/plain", "");
    return;
  }
  if (isAPMode()) {
    serveApPage();
  } else {
    serveMainPage();
  }
}
''',
        "Safe Mode root recovery redirect",
    )

    old_location = 'server.sendHeader("Location", "http://192.168.4.1/");'
    count = text.count(old_location)
    if count != 2:
        raise PatchError(f"AP captive redirects: expected 2 matches, found {count}")
    text = text.replace(
        old_location,
        'server.sendHeader("Location", recoverySafeModeActive() ? "http://192.168.4.1/recovery" : "http://192.168.4.1/");',
    )

    text = replace_once(
        text,
        "var rows=[['Build',d.build],['Mode',d.safeMode?'SAFE MODE':'Normal / Development'],['IP',d.ip],['Touch',d.touch],['Running slot',d.runningSlot],['Known good',d.knownGood||'—'],['Fallback',d.fallback||'—'],['Candidate OTA',d.candidatePending?('pending · attempt '+d.candidateAttempts):'healthy'],['Rapid-reset count',d.rapidBootCount]];",
        "var rows=[['Build',d.build],['Mode',d.safeMode?'SAFE MODE':'Normal / Development'],['Auth','OFF · DEVELOPMENT'],['Web control plane',d.webReady?'READY':'STARTING'],['IP',d.ip],['Touch',d.touch],['Running slot',d.runningSlot],['Known good',d.knownGood||'—'],['Fallback',d.fallback||'—'],['Candidate OTA',d.candidatePending?('pending · attempt '+d.candidateAttempts):'healthy'],['Rapid-reset count',d.rapidBootCount]];",
        "recovery diagnostics rows",
    )

    # Anchor on visible text rather than C++ quote escaping. The recovery page
    # is embedded in a C++ string, so matching its escaped onclick syntax is
    # unnecessarily brittle across patch generations.
    text = replace_once(
        text,
        "Reset Portal Session</button>",
        "Reset Portal Session</button><a href='/settings/export'>Download Settings Backup</a>",
        "recovery settings backup link",
    )

    p.write_text(text, encoding="utf-8")

    p = repo / "include" / "smart_home_build.h"
    text = p.read_text(encoding="utf-8")
    text = replace_once(
        text,
        '#define SMART_HOME_BUILD_LABEL "Smart Home v9.4 Recovery Foundation RC2"\n',
        '#define SMART_HOME_BUILD_LABEL "Smart Home v9.4 Recovery Foundation RC3"\n',
        "RC3 build label",
    )
    p.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    if not args.apply:
        raise SystemExit("Pass --apply")
    apply(Path(args.repo))
    print("Smart Home v9.4 Recovery Foundation RC3 entry hardening applied")
