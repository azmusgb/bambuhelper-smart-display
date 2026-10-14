#!/usr/bin/env python3
"""Run the focused X2D lifecycle capture with state-aware transport recovery.

This wrapper is for physical development evidence only. The WS350 can occasionally
reset the HTTP connection immediately after a media mutation even when the media
state transition itself completed. For GETs, bounded retries are safe. For media
mutations, this wrapper never blindly repeats a POST: it probes authoritative media
status and only synthesizes the original response when the requested state is
already observable. Every such recovery is printed so transport instability remains
visible instead of being hidden.
"""
from __future__ import annotations

import time

import accept_os12_media_runtime as runtime
import capture_x2d_full_ui as full
import capture_x2d_lifecycle as lifecycle
from accept_os12_portal_runtime import AcceptanceError

_ORIGINAL_API = runtime.api

_EXPECTED_MUTATIONS: dict[str, tuple[set[str], int]] = {
    "/os12/media/video/start-x2d-bridge": ({"PlayingVideo"}, 202),
    "/os12/media/video/pause": ({"Paused"}, 200),
    "/os12/media/video/resume": ({"PlayingVideo"}, 200),
    "/os12/media/stop": ({"Idle"}, 200),
}

_transport_recoveries: list[str] = []


def _raw_status(client) -> dict:
    payload = _ORIGINAL_API(client, "/os12/media/status")
    runtime.validate_status(payload)
    return payload


def _probe_expected_state(client, path: str, cause: BaseException) -> dict | None:
    expected, http_status = _EXPECTED_MUTATIONS[path]
    deadline = time.monotonic() + 3.0
    last_session: str | None = None
    while time.monotonic() < deadline:
        try:
            payload = _raw_status(client)
        except (OSError, TimeoutError):
            time.sleep(0.12)
            continue
        last_session = str(payload.get("session"))
        if last_session in expected:
            payload["_http_status"] = http_status
            message = (
                f"TRANSPORT RECOVERY {path}: {type(cause).__name__}: {cause}; "
                f"authoritative session={last_session}"
            )
            _transport_recoveries.append(message)
            print(message)
            return payload
        time.sleep(0.12)
    print(
        f"TRANSPORT UNRECOVERED {path}: {type(cause).__name__}: {cause}; "
        f"lastSession={last_session}"
    )
    return None


def resilient_api(client, path: str, *, method: str = "GET", form=None) -> dict:
    attempts = 3 if method == "GET" else 1
    last: BaseException | None = None
    for attempt in range(1, attempts + 1):
        try:
            return _ORIGINAL_API(client, path, method=method, form=form)
        except (OSError, TimeoutError) as exc:
            last = exc
            if method != "GET" and path in _EXPECTED_MUTATIONS:
                recovered = _probe_expected_state(client, path, exc)
                if recovered is not None:
                    return recovered
                raise
            if attempt < attempts:
                time.sleep(0.20 * attempt)
    if last is not None:
        raise last
    raise AcceptanceError(f"unreachable transport retry state for {method} {path}")


def resilient_status(client) -> dict:
    payload = resilient_api(client, "/os12/media/status")
    runtime.validate_status(payload)
    return payload


def main() -> int:
    # Patch every module that the focused runner reaches. Imported helper
    # functions resolve their module globals at call time, so this also covers
    # wait_for_live_frame(), ensure_idle(), and wait_for_session().
    runtime.api = resilient_api
    runtime.status = resilient_status
    full.api = resilient_api
    full.status = resilient_status
    lifecycle.api = resilient_api
    lifecycle.status = resilient_status

    code = lifecycle.main()
    if _transport_recoveries:
        print(f"\nTransport recoveries observed: {len(_transport_recoveries)}")
        for item in _transport_recoveries:
            print(f"  - {item}")
        print("These are diagnostic warnings and still require root-cause follow-up.")
    else:
        print("\nTransport recoveries observed: 0")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
