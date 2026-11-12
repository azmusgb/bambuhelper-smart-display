#!/usr/bin/env python3
"""Point the WS350's calm screen at Local AI (Workshop OS 12.3.10, POST /os12/localai/config).

Sends Local AI's address, the name on its certificate, the display key and Local AI's CA to the display over its
signed-in portal, then waits for the first cards. The key is read from the Mac's login Keychain (account ws350,
service localai-display-key, made by Local AI's host/workshop-display/set-key.sh) and the CA from
~/.claude/localai-chat/localai-ca.crt (made by host/claude-chat/install.sh). Neither is printed.

31 Oct 2026: --backend pihub points it at Pi Hub instead (address 10.0.0.80, name home.home.arpa unless --address or
--name say otherwise). The key is then Pi Hub's display key (hubd_), read from Keychain service pihub-display-key if
one was stored there, and the CA must be Pi Hub's, given with --ca (there is no default for Pi Hub). Pairing from the
display or the portal is the normal route: it fetches the key and the CA itself.

  python3 scripts/configure_localai_feed.py --backend pihub --ca ~/Downloads/home-ca.crt

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

KEYCHAIN = {"localai": ("ws350", "localai-display-key"), "pihub": ("ws350", "pihub-display-key")}
KEY_PREFIX = {"localai": "wsd_", "pihub": "hubd_"}
# The address and certificate name each backend has on the home network (firmware: backendInfo()).
DEFAULTS = {"localai": ("10.0.0.81", "localai.home.arpa"), "pihub": ("10.0.0.80", "home.home.arpa")}
CA_PATH = Path.home() / ".claude" / "localai-chat" / "localai-ca.crt"
PIHUB_NEEDS_CA = "For Pi Hub, pass --ca with Pi Hub's CA (http://10.0.0.80/home-ca.crt), or pair from the display or the portal."


def default_ca(backend: str) -> Path | None:
    """Local AI's CA where its installer puts it; none for Pi Hub (its CA must be named, never guessed)."""
    return CA_PATH if backend == "localai" else None


def read_ca(path: Path) -> str:
    """The CA file's PEM text; exits when it is missing or holds no certificate."""
    try:
        text = path.read_text(encoding="ascii")
    except (OSError, UnicodeDecodeError) as exc:
        sys.exit(f"FAIL: cannot read the CA {path}: {exc}")
    if "-----BEGIN CERTIFICATE-----" not in text:
        sys.exit(f"FAIL: {path} is not a PEM certificate (no -----BEGIN CERTIFICATE-----)")
    return text


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
    parser = argparse.ArgumentParser(description=(__doc__ or "Configure the display's feed.").splitlines()[0])
    parser.add_argument("--base-url", default=os.environ.get("WORKSHOP_OS_URL", "http://10.0.0.124"))
    parser.add_argument("--backend", choices=("localai", "pihub"), default="localai",
                        help="the service the display takes its feed from (pihub: Pi Hub; its CA is Pi Hub's home-ca.crt)")
    parser.add_argument("--address", default=None, help="the service's IPv4 address (default: 10.0.0.81 Local AI, 10.0.0.80 Pi Hub)")
    parser.add_argument("--name", default=None, help="the name on its certificate (default: localai.home.arpa, home.home.arpa)")
    parser.add_argument("--ca", type=Path, default=None,
                        help=f"the service's CA certificate (PEM). Local AI default: {CA_PATH}; Pi Hub: required "
                             "(http://10.0.0.80/home-ca.crt)")
    parser.add_argument("--clear", action="store_true", help="forget the settings on the display")
    parser.epilog = ("Keys come from the login Keychain, account ws350: service localai-display-key (Local AI) or "
                     "pihub-display-key (where a Pi Hub key would be stored; pairing from the display or the portal "
                     "is the normal route for Pi Hub).")
    args = parser.parse_args()
    address, name = DEFAULTS[args.backend]
    args.address = args.address or address
    args.name = args.name or name
    ca_pem = key = ""
    if not args.clear:  # checked before the display is contacted (31 Oct 2026: the key too)
        ca_path = args.ca or default_ca(args.backend)
        if ca_path is None:
            sys.exit(f"FAIL: {PIHUB_NEEDS_CA}")
        if ca_path == CA_PATH and not ca_path.is_file():
            sys.exit(f"FAIL: missing {CA_PATH}; run Local AI's host/claude-chat/install.sh first")
        ca_pem = read_ca(ca_path)
        key = keychain_secret(*KEYCHAIN[args.backend])
        if not key.startswith(KEY_PREFIX[args.backend]):
            where = "Local AI's host/workshop-display/set-key.sh" if args.backend == "localai" else "Pi Hub's display key into the Keychain"
            sys.exit(f"FAIL: no {args.backend} display key in the Keychain (service {KEYCHAIN[args.backend][1]}); put {where} first")

    client = Client(args.base_url)
    establish_portal_session(client)
    headers = {"Accept": "application/json"}
    if args.clear:
        r = client.request("/os12/localai/clear", method="POST", headers=headers)
        print(f"clear: HTTP {r.status}")
        return 0 if r.status == 200 else 1

    form = {"address": args.address, "name": args.name, "key": key, "ca": ca_pem, "backend": args.backend}
    r = client.request("/os12/localai/config", method="POST", form=form, headers=headers)
    del key, form
    if r.status != 202:
        sys.exit(f"FAIL: the display refused the settings (HTTP {r.status}): {r.body[:200]!r}")
    print(f"Saved on the display. Waiting for the first {'Pi Hub' if args.backend == 'pihub' else 'Local AI'} cards…")
    deadline = time.time() + 90
    s: dict = {}
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
