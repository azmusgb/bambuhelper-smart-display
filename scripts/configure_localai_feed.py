#!/usr/bin/env python3
"""Point the WS350's calm screen at Local AI (Workshop OS 12.3.10, POST /os12/localai/config).

Sends Local AI's address, the name on its certificate, the display key and Local AI's CA to the display over its
signed-in portal, then waits for the first cards. The key is read from the Mac's login Keychain (account ws350,
service localai-display-key, made by Local AI's host/workshop-display/set-key.sh) and the CA from
~/.claude/localai-chat/localai-ca.crt (made by host/claude-chat/install.sh). Neither is printed.

  WORKSHOP_OS_COOKIE_JAR=<jar> python3 scripts/configure_localai_feed.py
  python3 scripts/configure_localai_feed.py --clear
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

from accept_os12_portal_runtime import Client, establish_portal_session

KEYCHAIN = ("ws350", "localai-display-key")
CA_PATH = Path.home() / ".claude" / "localai-chat" / "localai-ca.crt"


def keychain_secret(account: str, service: str) -> str:
    # posix_spawn, not subprocess: after urllib has run, a fork()ed child crashes on macOS (see portal_code_key).
    read_end, write_end = os.pipe()
    actions = [(os.POSIX_SPAWN_DUP2, write_end, 1), (os.POSIX_SPAWN_CLOSE, read_end),
               (os.POSIX_SPAWN_OPEN, 2, os.devnull, os.O_WRONLY, 0)]
    try:
        pid = os.posix_spawnp("security", ["security", "find-generic-password", "-a", account, "-s", service, "-w"],
                              os.environ, file_actions=actions)
    except OSError:
        os.close(read_end)
        os.close(write_end)
        return ""
    os.close(write_end)
    with os.fdopen(read_end, "rb") as out:
        value = out.read().decode("utf-8", "replace").strip()
    os.waitpid(pid, 0)
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--base-url", default=os.environ.get("WORKSHOP_OS_URL", "http://10.0.0.124"))
    parser.add_argument("--address", default="10.0.0.21", help="Local AI's IPv4 address on the home network")
    parser.add_argument("--name", default="localai.home.arpa", help="the name on Local AI's certificate")
    parser.add_argument("--clear", action="store_true", help="forget the settings on the display")
    args = parser.parse_args()

    client = Client(args.base_url)
    establish_portal_session(client)
    headers = {"Accept": "application/json"}
    if args.clear:
        r = client.request("/os12/localai/clear", method="POST", headers=headers)
        print(f"clear: HTTP {r.status}")
        return 0 if r.status == 200 else 1

    key = keychain_secret(*KEYCHAIN)
    if not key.startswith("wsd_"):
        sys.exit("FAIL: no display key in the Keychain; run Local AI's host/workshop-display/set-key.sh first")
    if not CA_PATH.is_file():
        sys.exit(f"FAIL: missing {CA_PATH}; run Local AI's host/claude-chat/install.sh first")
    form = {"address": args.address, "name": args.name, "key": key, "ca": CA_PATH.read_text(encoding="ascii")}
    r = client.request("/os12/localai/config", method="POST", form=form, headers=headers)
    del key, form
    if r.status != 202:
        sys.exit(f"FAIL: the display refused the settings (HTTP {r.status}): {r.body[:200]!r}")
    print("Saved on the display. Waiting for the first Local AI cards…")
    deadline = time.time() + 90
    while time.time() < deadline:
        time.sleep(5)
        s = json.loads(client.request("/os12/localai/status", headers=headers).body)
        if s.get("lastSuccessAgoS", -1) >= 0:
            print(f"PASS: {len(s.get('cards', []))} card(s): " + "; ".join(f"{c['title']}: {c['text']}" for c in s.get("cards", [])))
            return 0
        if s.get("failures"):
            print(f"not yet: {s.get('status')}")
    print("FAIL: no cards within 90 s; last status: " + str(s.get("status")))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
