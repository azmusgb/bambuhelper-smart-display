#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path


class ValidationError(RuntimeError):
    pass


def need(text: str, needle: str, label: str) -> None:
    if needle not in text:
        raise ValidationError(f"missing {label}: {needle}")


def forbid(text: str, needle: str, label: str) -> None:
    if needle in text:
        raise ValidationError(f"forbidden {label}: {needle}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    args = ap.parse_args()
    root = Path(args.repo).resolve()

    sec = (root / "src/security_manager.cpp").read_text(encoding="utf-8")
    web = (root / "src/web_server.cpp").read_text(encoding="utf-8")
    html = (root / "include/web_pages.h").read_text(encoding="utf-8")
    build = (root / "include/smart_home_build.h").read_text(encoding="utf-8")

    need(build, "#define WORKSHOP_OS_CODE_FREE_PORTAL 1", "code-free build identity")

    need(sec, "Workshop OS local portal: device code disabled", "code-free initialization")
    need(sec, "if (mutating && !sameOrigin(server))", "same-origin mutation gate")
    need(sec, "return false;", "mutation rejection")
    need(sec, "return true;", "code-free authorization")
    need(sec, "bool securityPortalCodeRequired() {\n  return false;", "portal code disabled")
    forbid(sec, "if (cookieMatches(server)) return true;", "session gate in final authorization")
    forbid(sec, "kTemporaryNoCodeLan", "temporary physical-test bypass")

    for marker in (
        'd["requirePortalCode"]=false;',
        'd["deviceCodeEnabled"]=false;',
        'd["authMode"]="local-code-free";',
        'd["mutationsRequireSession"]=false;',
        'd["sameOriginProtection"]=true;',
        'Workshop OS device code is disabled by product policy.',
    ):
        need(web, marker, "code-free runtime contract")

    need(web, 'server.sendHeader("Location", "/");', "login redirect")
    forbid(web, "<form id='login-form'", "device-code login form")
    forbid(web, "name='code'", "device-code input")
    forbid(web, "Enter the current portal code", "device-code prompt")

    need(html, "No device code required", "code-free portal UX")
    need(html, "trusted local network", "local access explanation")
    forbid(html, "Require access code", "portal-code toggle")
    forbid(html, 'id="portalCodeRequired"', "portal-code checkbox")

    print("PASS: OS12 final portal is code-free, prompt-free, and same-origin protected")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ValidationError as exc:
        raise SystemExit(f"FAIL: {exc}")
