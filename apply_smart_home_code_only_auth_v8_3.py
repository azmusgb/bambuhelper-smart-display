#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
from pathlib import Path


class PatchError(RuntimeError):
    pass


def replace_once(text: str, old: str, new: str, name: str) -> str:
    count = text.count(old)
    if count != 1:
        raise PatchError(f"{name}: expected exactly 1 match, found {count}")
    return text.replace(old, new, 1)


def regex_once(text: str, pattern: str, repl, name: str, flags: int = 0) -> str:
    updated, count = re.subn(pattern, repl, text, count=1, flags=flags)
    if count != 1:
        raise PatchError(f"{name}: expected exactly 1 match, found {count}")
    return updated


def patch_web_pages(repo: Path) -> None:
    p = repo / "include" / "web_pages.h"
    text = p.read_text(encoding="utf-8")

    # v8 already rewrites this stable password-retention notice. Reuse that
    # anchor instead of depending on the surrounding login layout, which older
    # Smart Home UX layers may restructure substantially.
    v8_notice = (
        "Smart Home v8 never stores your Bambu account password. The cloud token is retained; "
        "if Bambu later requires a fresh sign-in, enter the password again."
    )
    passwordless_notice = (
        "Smart Home v8 uses passwordless Bambu email-code sign-in. Your Bambu account password "
        "is never accepted, transmitted, or stored by this local portal."
    )
    text = replace_once(text, v8_notice, passwordless_notice, "passwordless notice")

    # Best-effort UI cleanup only. Security never depends on custom page markup.
    text, _ = re.subn(
        r'<button([^>]*?)id="cl-mode-pass-btn"([^>]*)>Password</button>',
        r'<button\1id="cl-mode-pass-btn"\2 disabled style="display:none">Password</button>',
        text,
        count=1,
    )
    text, _ = re.subn(
        r'<div id="cl_passWrap"([^>]*)>',
        r'<div id="cl_passWrap"\1 style="display:none">',
        text,
        count=1,
    )

    if passwordless_notice not in text:
        raise PatchError("passwordless notice missing after patch")
    p.write_text(text, encoding="utf-8")


def patch_web_app(repo: Path) -> None:
    p = repo / "web" / "app.js"
    text = p.read_text(encoding="utf-8")

    # Force the shared login state to code mode when that state variable exists.
    text, mode_state_count = re.subn(
        r"var\s+clLoginMode\s*=\s*['\"](?:password|code)['\"];",
        "var clLoginMode = 'code';",
        text,
        count=1,
    )

    # Replace the mode-switch UI logic when present. A custom Smart Home portal
    # may not expose this function; that is fine because request serialization
    # and the server endpoint below are the authoritative controls.
    mode_fn = '''function clSetLoginMode(m){
  // Smart Home v8.3: the local portal is email-code only.
  clLoginMode = 'code';
  var passBtn = document.getElementById('cl-mode-pass-btn');
  var codeBtn = document.getElementById('cl-mode-code-btn');
  var passWrap = document.getElementById('cl_passWrap');
  if (passBtn) { passBtn.setAttribute('aria-pressed', 'false'); passBtn.disabled = true; passBtn.style.display = 'none'; }
  if (codeBtn) codeBtn.setAttribute('aria-pressed', 'true');
  if (passWrap) passWrap.style.display = 'none';
  var signBtn = document.getElementById('cl_signinBtn');
  if (signBtn) signBtn.textContent = 'Email me a code';
}'''
    text, _ = re.subn(
        r'function\s+clSetLoginMode\s*\(m\)\s*\{.*?\n\}',
        mode_fn,
        text,
        count=1,
        flags=re.S,
    )

    # If the stock initializer remains, force it to initialize code mode.
    if "  clSetAuthMethod('signin');\n  fetch('/cloud/login/status')" in text:
        text = text.replace(
            "  clSetAuthMethod('signin');\n  fetch('/cloud/login/status')",
            "  clSetAuthMethod('signin');\n  clSetLoginMode('code');\n  fetch('/cloud/login/status')",
            1,
        )

    # Field-level request hardening is deliberately independent of function
    # formatting. Force any dynamic mode field to `code`, then strip password
    # and remember-password serialization wherever those calls occur.
    text = re.sub(
        r"p\.append\('mode',\s*clLoginMode\);",
        "p.append('mode', 'code');",
        text,
        count=1,
    )
    text = re.sub(
        r"^\s*p\.append\('password'[^\n]*\);\s*$",
        "",
        text,
        count=1,
        flags=re.M,
    )
    text = re.sub(
        r"^\s*p\.append\('save'[^\n]*\);\s*$",
        "",
        text,
        count=1,
        flags=re.M,
    )

    forbidden = [
        "p.append('password'",
        "p.append('save'",
        "clLoginMode = 'password'",
    ]
    for needle in forbidden:
        if needle in text:
            raise PatchError(f"passwordless browser validation failed: {needle} remains")

    # If this app.js still contains cloudSignIn(), it must now serialize code
    # mode. If the custom Smart Home layer has replaced that function entirely,
    # the device-side mode gate remains authoritative.
    if "function cloudSignIn" in text and "p.append('mode', 'code')" not in text:
        raise PatchError("cloudSignIn remains but does not force mode=code")
    if mode_state_count and "clLoginMode = 'code'" not in text:
        raise PatchError("cloud login mode state was not forced to code")

    p.write_text(text, encoding="utf-8")


def patch_web_server(repo: Path) -> None:
    p = repo / "src" / "web_server.cpp"
    text = p.read_text(encoding="utf-8")

    replacement = '''  // Smart Home v8.3: this local portal never accepts a Bambu account
  // password. Email-code sign-in gives us a short-lived verification secret
  // instead of transmitting a long-lived password over plain LAN HTTP.
  if (server.arg("mode") != "code") {
    sendCloudLoginError("Smart Home requires email-code sign-in; Bambu account passwords are not accepted by this portal.");
    return;
  }
  cloudLoginRequestEmailCode(email.c_str());
  sendCloudLoginState();
  return;
'''
    text = regex_once(
        text,
        r'  if\s*\(server\.arg\("mode"\)\s*==\s*"code"\)\s*\{\s*'
        r'cloudLoginRequestEmailCode\(email\.c_str\(\)\);\s*'
        r'sendCloudLoginState\(\);\s*return;\s*\}\s*',
        replacement,
        "server password gate",
        re.S,
    )

    required = [
        'server.arg("mode") != "code"',
        'Bambu account passwords are not accepted by this portal',
        'cloudLoginRequestEmailCode(email.c_str())',
    ]
    for needle in required:
        if needle not in text:
            raise PatchError(f"passwordless server validation failed: missing {needle}")

    p.write_text(text, encoding="utf-8")


def apply(repo: Path) -> None:
    patch_web_pages(repo)
    patch_web_app(repo)
    patch_web_server(repo)


def main() -> int:
    ap = argparse.ArgumentParser(description="Apply Smart Home v8.3 passwordless Bambu cloud sign-in")
    ap.add_argument("--repo", required=True)
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    if not args.apply:
        raise SystemExit("Pass --apply")
    apply(Path(args.repo))
    print("Smart Home v8.3 email-code-only cloud sign-in applied")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
