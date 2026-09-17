#!/usr/bin/env python3
"""Exercise Workshop OS 12 GitHub-native update behavior on a real WS350.

Default behavior is non-installing: authenticate locally, select a channel,
request a manifest check, and validate returned update metadata/state.

Actual installation requires BOTH --install and --expect-version. The helper
never accepts an arbitrary firmware URL. If the device reboots successfully it
prompts for the newly rotated portal code and verifies the reported running
release version after reconnect.
"""
from __future__ import annotations

import argparse
import getpass
import json
import os
import re
import time
import urllib.error

from accept_os12_portal_runtime import (
    AcceptanceError,
    Client,
    assert_login_markup,
    check,
    login,
    normalized_code,
)

HEX40 = re.compile(r"^[0-9a-f]{40}$")
HEX64 = re.compile(r"^[0-9a-fA-F]{64}$")
TERMINAL_CHECK_PHASES = {"Idle", "Available", "Failed"}


def api(client: Client, path: str, *, method: str = "GET", form: dict[str, str] | None = None) -> dict:
    headers = {"X-BambuHelper-Client": "1", "Accept": "application/json"}
    response = client.request(path, method=method, form=form, headers=headers, timeout=15.0)
    check(response.status in (200, 202), f"{method} {path} returned HTTP {response.status}: {response.body[:200]}")
    try:
        payload = json.loads(response.body)
    except json.JSONDecodeError as exc:
        raise AcceptanceError(f"{method} {path} did not return JSON") from exc
    check(isinstance(payload, dict), f"{method} {path} returned non-object JSON")
    return payload


def read_code(prompt: str, *, env_name: str = "WORKSHOP_OS_PORTAL_CODE") -> str:
    raw = os.environ.get(env_name)
    if not raw:
        raw = getpass.getpass(prompt)
    code = normalized_code(raw)
    raw = ""
    return code


def authenticated_client(base_url: str, code: str, label: str) -> Client:
    client = Client(base_url)
    login(client, code, label)
    return client


def validate_status(payload: dict) -> None:
    required = (
        "channel", "phase", "progress", "busy", "updateAvailable",
        "artifactIdentityVerified", "runningVersion", "availableVersion",
        "availableLabel", "status", "sourceCommit", "artifactSize", "artifactSha256",
    )
    missing = [key for key in required if key not in payload]
    check(not missing, f"update status missing fields: {', '.join(missing)}")
    check(payload["channel"] in ("Stable", "Candidate"), "invalid update channel in status")
    check(isinstance(payload["busy"], bool), "busy must be boolean")
    check(isinstance(payload["updateAvailable"], bool), "updateAvailable must be boolean")
    check(isinstance(payload["progress"], int) and 0 <= payload["progress"] <= 100, "progress outside 0..100")
    check(isinstance(payload["runningVersion"], str) and payload["runningVersion"], "runningVersion missing")


def poll_check(client: Client, timeout: float) -> dict:
    deadline = time.monotonic() + timeout
    last_phase = None
    while time.monotonic() < deadline:
        payload = api(client, "/os12/update/status")
        validate_status(payload)
        phase = str(payload["phase"])
        if phase != last_phase:
            print(f"STATE {phase}: {payload.get('status', '')}")
            last_phase = phase
        if not payload["busy"] and phase in TERMINAL_CHECK_PHASES:
            return payload
        time.sleep(1.0)
    raise AcceptanceError("timed out waiting for GitHub update check")


def poll_install_until_reboot(client: Client, base_url: str, timeout: float) -> None:
    deadline = time.monotonic() + timeout
    last_phase = None
    saw_install_state = False
    while time.monotonic() < deadline:
        try:
            payload = api(client, "/os12/update/status")
            validate_status(payload)
            phase = str(payload["phase"])
            if phase != last_phase:
                print(f"STATE {phase} {payload['progress']}%: {payload.get('status', '')}")
                last_phase = phase
            if phase in ("Downloading", "Verifying", "Installing", "RebootRequired"):
                saw_install_state = True
            if phase == "Failed":
                raise AcceptanceError(f"device update failed: {payload.get('status', '')}")
            time.sleep(1.0)
        except AcceptanceError as exc:
            # A reachable HTTP error is a real failure. A transport drop after
            # staging is expected because the device is rebooting; probe with a
            # fresh unauthenticated client before deciding.
            if not saw_install_state:
                raise
            probe = Client(base_url)
            try:
                probe.request("/login", timeout=3.0)
            except AcceptanceError:
                print("STATE rebooting: device temporarily unreachable")
                return
            if "request failed" not in str(exc):
                raise
    raise AcceptanceError("timed out waiting for update installation/reboot")


def wait_for_login(base_url: str, timeout: float) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            response = Client(base_url).request("/login", timeout=3.0)
            if response.status == 200:
                print("PASS  WS350 reachable after reboot")
                return
        except AcceptanceError:
            pass
        time.sleep(2.0)
    raise AcceptanceError("WS350 did not return to the login surface after reboot")


def run(args: argparse.Namespace) -> int:
    base_url = args.base_url.rstrip("/")
    if args.install and not args.expect_version:
        raise AcceptanceError("--install requires --expect-version; refusing unconstrained installation")

    print(f"Target: {base_url}")
    assert_login_markup(Client(base_url))
    code = read_code("Current portal code shown on WS350 System screen: ")
    client = authenticated_client(base_url, code, "update acceptance session")
    code = ""

    channel_payload = api(
        client,
        "/os12/update/channel",
        method="POST",
        form={"channel": args.channel},
    )
    validate_status(channel_payload)
    check(channel_payload["channel"].lower() == args.channel, "device did not select requested update channel")
    print(f"PASS  selected {channel_payload['channel']} channel")

    api(client, "/os12/update/check", method="POST")
    status = poll_check(client, args.check_timeout)
    print(f"PASS  GitHub manifest check completed: {status['phase']}")
    print(f"Running: {status['runningVersion']}")

    if status["updateAvailable"]:
        check(status["phase"] == "Available", "updateAvailable true outside Available phase")
        check(HEX40.fullmatch(str(status["sourceCommit"])) is not None, "available sourceCommit is not 40 hex chars")
        check(HEX64.fullmatch(str(status["artifactSha256"])) is not None, "available SHA-256 is malformed")
        check(isinstance(status["artifactSize"], int) and status["artifactSize"] > 0, "available artifact size is invalid")
        print(
            "AVAILABLE "
            f"{status['availableVersion']} | {status['availableLabel']} | "
            f"{status['artifactSize']} bytes | sha256={status['artifactSha256']}"
        )
    else:
        check(status["phase"] == "Idle", f"no update advertised but phase is {status['phase']}")
        print("PASS  selected channel reports this release as current")

    if not args.install:
        print("RUNTIME UPDATE CHECK: PASS — no firmware installation requested")
        return 0

    check(status["updateAvailable"], "--install requested but selected channel has no newer published update")
    check(status["availableVersion"] == args.expect_version,
          f"refusing install: discovered {status['availableVersion']!r}, expected {args.expect_version!r}")
    if args.expect_source_sha:
        check(status["sourceCommit"] == args.expect_source_sha,
              "refusing install: discovered source SHA does not match --expect-source-sha")

    print("INSTALL AUTHORIZED BY EXPLICIT EXPECTATION")
    print(f"Expected version: {args.expect_version}")
    if args.expect_source_sha:
        print(f"Expected source: {args.expect_source_sha}")
    api(client, "/os12/update/install", method="POST")
    poll_install_until_reboot(client, base_url, args.install_timeout)
    wait_for_login(base_url, args.reboot_timeout)

    print("Portal code rotates on reboot; re-authentication is required for post-install verification.")
    new_code = read_code(
        "New portal code shown on WS350 System screen after reboot: ",
        env_name="WORKSHOP_OS_POST_REBOOT_PORTAL_CODE",
    )
    post = authenticated_client(base_url, new_code, "post-reboot verification session")
    new_code = ""
    final_status = api(post, "/os12/update/status")
    validate_status(final_status)
    check(final_status["runningVersion"] == args.expect_version,
          f"post-reboot running version is {final_status['runningVersion']!r}, expected {args.expect_version!r}")
    print(f"PASS  post-reboot running Workshop OS release is {args.expect_version}")
    print("RUNTIME GITHUB OTA ACCEPTANCE SUBSET: PASS")
    print("This is runtime evidence only; touchscreen/recovery/control physical acceptance remains separate.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default=os.environ.get("WORKSHOP_OS_URL", "http://10.0.0.124"))
    parser.add_argument("--channel", choices=("stable", "candidate"), default="candidate")
    parser.add_argument("--check-timeout", type=float, default=45.0)
    parser.add_argument("--install-timeout", type=float, default=180.0)
    parser.add_argument("--reboot-timeout", type=float, default=120.0)
    parser.add_argument("--install", action="store_true")
    parser.add_argument("--expect-version")
    parser.add_argument("--expect-source-sha")
    args = parser.parse_args()
    try:
        return run(args)
    except AcceptanceError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    import sys
    raise SystemExit(main())
