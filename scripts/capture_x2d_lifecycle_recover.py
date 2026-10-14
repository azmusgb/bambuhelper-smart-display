#!/usr/bin/env python3
"""Run the focused X2D lifecycle capture with state-aware transport recovery.

This wrapper is for physical development evidence only. The WS350 can occasionally
reset an HTTP connection while media work is active. Idempotent reads/navigation
receive bounded retries. Media mutations are never blindly repeated: authoritative
media status is probed first and the original response is only synthesized when the
requested state is already observable. Every recovery is printed so transport
instability remains visible instead of being hidden.
"""
from __future__ import annotations

import time

import accept_os12_media_runtime as runtime
import capture_x2d_full_ui as full
import capture_x2d_lifecycle as lifecycle
from accept_os12_portal_runtime import AcceptanceError

_ORIGINAL_API = runtime.api
_ORIGINAL_IDENTITY = lifecycle.update_identity
_ORIGINAL_SHOW = lifecycle.show
_ORIGINAL_FRAME_BYTES = lifecycle.frame_bytes

_EXPECTED_MUTATIONS: dict[str, tuple[set[str], int]] = {
    "/os12/media/video/start-x2d-bridge": ({"PlayingVideo"}, 202),
    "/os12/media/video/pause": ({"Paused"}, 200),
    "/os12/media/video/resume": ({"PlayingVideo"}, 200),
    "/os12/media/stop": ({"Idle"}, 200),
}

_transport_recoveries: list[str] = []
_read_recoveries: list[str] = []


def _is_transportish(exc: BaseException) -> bool:
    if isinstance(exc, (OSError, TimeoutError)):
        return True
    if isinstance(exc, AcceptanceError):
        text = str(exc).lower()
        return any(
            token in text
            for token in (
                "connection reset",
                "timed out",
                "timeout",
                "temporarily unavailable",
                "framebuffer capture request failed",
                "http error 503",
            )
        )
    return False


def _retry_read(label: str, fn, attempts: int = 5):
    last: BaseException | None = None
    for attempt in range(1, attempts + 1):
        try:
            value = fn()
            if attempt > 1:
                message = f"READ RECOVERY {label}: succeeded on attempt {attempt}"
                _read_recoveries.append(message)
                print(message)
            return value
        except Exception as exc:
            if not _is_transportish(exc):
                raise
            last = exc
            if attempt == attempts:
                break
            print(
                f"READ RETRY {label}: attempt {attempt}/{attempts} failed: "
                f"{type(exc).__name__}: {exc}"
            )
            time.sleep(min(0.25 * attempt, 0.8))
    if last is not None:
        raise last
    raise AcceptanceError(f"unreachable retry state for {label}")


def resilient_identity(client) -> dict:
    print("PHASE identity")
    return _retry_read("GET /os12/update/status", lambda: _ORIGINAL_IDENTITY(client))


def resilient_show(client, view_id: str) -> None:
    # /hub/show is navigation-only and idempotent for a fixed page target.
    return _retry_read(f"POST /hub/show page={view_id}", lambda: _ORIGINAL_SHOW(client, view_id), attempts=3)


def resilient_frame_bytes(client) -> bytes:
    return _retry_read("GET /hub/frame.ppm", lambda: _ORIGINAL_FRAME_BYTES(client), attempts=4)


def _raw_status(client) -> dict:
    payload = _ORIGINAL_API(client, "/os12/media/status")
    runtime.validate_status(payload)
    return payload


def _probe_expected_state(client, path: str, cause: BaseException) -> dict | None:
    expected, http_status = _EXPECTED_MUTATIONS[path]
    deadline = time.monotonic() + 4.0
    last_session: str | None = None
    while time.monotonic() < deadline:
        try:
            payload = _raw_status(client)
        except (OSError, TimeoutError, AcceptanceError):
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
    attempts = 4 if method == "GET" else 1
    last: BaseException | None = None
    for attempt in range(1, attempts + 1):
        try:
            return _ORIGINAL_API(client, path, method=method, form=form)
        except (OSError, TimeoutError, AcceptanceError) as exc:
            if not _is_transportish(exc):
                raise
            last = exc
            if method != "GET" and path in _EXPECTED_MUTATIONS:
                recovered = _probe_expected_state(client, path, exc)
                if recovered is not None:
                    return recovered
                raise
            if attempt < attempts:
                print(
                    f"READ RETRY {path}: attempt {attempt}/{attempts} failed: "
                    f"{type(exc).__name__}: {exc}"
                )
                time.sleep(min(0.20 * attempt, 0.7))
    if last is not None:
        raise last
    raise AcceptanceError(f"unreachable transport retry state for {method} {path}")


def resilient_status(client) -> dict:
    payload = resilient_api(client, "/os12/media/status")
    runtime.validate_status(payload)
    return payload


def main() -> int:
    # Patch every module that the focused runner reaches. Imported helper
    # functions resolve their module globals at call time, so this covers
    # wait_for_live_frame(), ensure_idle(), wait_for_session(), identity,
    # navigation and framebuffer evidence reads.
    runtime.api = resilient_api
    runtime.status = resilient_status
    full.api = resilient_api
    full.status = resilient_status
    lifecycle.api = resilient_api
    lifecycle.status = resilient_status
    lifecycle.update_identity = resilient_identity
    lifecycle.show = resilient_show
    lifecycle.frame_bytes = resilient_frame_bytes

    code = lifecycle.main()

    print(f"\nTransport recoveries observed: {len(_transport_recoveries)}")
    for item in _transport_recoveries:
        print(f"  - {item}")
    print(f"Read recoveries observed: {len(_read_recoveries)}")
    for item in _read_recoveries:
        print(f"  - {item}")
    if _transport_recoveries or _read_recoveries:
        print("Recoveries are diagnostic warnings and still require root-cause follow-up.")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
