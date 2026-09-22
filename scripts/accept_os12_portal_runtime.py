#!/usr/bin/env python3
"""Compatibility entry point for the Workshop OS 12 code-free portal acceptance.

The legacy module name remains the shared import surface for acceptance helpers.
User-entered portal-code/session helpers are intentionally not reintroduced.
"""
from accept_os12_code_free_portal_runtime import (
    AcceptanceError,
    Client,
    Response,
    assert_code_free_portal,
    check,
    main,
)

__all__ = [
    "AcceptanceError",
    "Client",
    "Response",
    "assert_code_free_portal",
    "check",
    "main",
]

if __name__ == "__main__":
    raise SystemExit(main())
