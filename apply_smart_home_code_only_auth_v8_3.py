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


def regex_once(text: str, pattern: str, repl: str, name: str, flags: int = 0) -> str:
    updated, count = re.subn(pattern, repl, text, count=1, flags=flags)
    if count != 1:
        raise PatchError(f"{name}: expected exactly 1 match, found {count}")
    return updated


def patch_web_pages(repo: Path) -> None:
    p = repo / "include" / "web_pages.h"
    text = p.read_text(encoding="utf-8")

    # Earlier Smart Home layers have changed this explanatory copy over time.
    # Anchor to the stable sign-in container + mode selector instead of prose.
    banner = (
        '<div class="banner" style="margin-bottom:var(--sp-3)">'
        '<span class="dot" style="background:var(--success)"></span><div>'
        '<strong>Passwordless sign-in.</strong>'
        '<div class="small text-dim" style="margin-top:4px">'
        'Smart Home v8 uses Bambu email-code authentication only. '
        'Your Bambu account password is never accepted by this local HTTP portal.'
        '</div></div></div>'
    )
    text = regex_once(
        text,
        r'(<div id="cl_signinWrap"[^>]*>\s*).*?(\s*<div class="seg"\s+style="margin-bottom:var\(--sp-3\)"[^>]*>)',
        lambda m: m.group(1) + banner + m.group(2),
        "passwordless banner",
        re.S,
    )

    selector = (
        '<div class="seg" style="margin-bottom:var(--sp-3)">\n'
        '          <button type="button" id="cl-mode-pass-btn" aria-pressed="false" disabled style="display:none">Password</button>\n'
        '          <button type="button" id="cl-mode-code-btn" aria-pressed="true" disabled>Email code</button>\n'
        '        </div>'
    )
    text = regex_once(
        text,
        r'<div class="seg"\s+style="margin-bottom:var\(--sp-3\)"[^>]*>\s*'
        r'<button[^>]*id="cl-mode-pass-btn"[^>]*>Password</button>\s*'
        r'<button[^>]*id="cl-mode-code-btn"[^>]*>Email code</button>\s*</div>',
        selector,
        "login mode selector",
        re.S,
    )

    text = regex_once(
        text,
        r'<div id="cl_passWrap"[^>]*>',
        '<div id="cl_passWrap" style="display:none">',
        "hide password field",
    )

    required = [
        "Passwordless sign-in.",
        'id="cl-mode-pass-btn" aria-pressed="false" disabled style="display:none"',
        'id="cl-mode-code-btn" aria-pressed="true" disabled',
        'id="cl_passWrap" style="display:none"',
    ]
    for needle in required:
        if needle not in text:
            raise PatchError(f"passwordless markup validation failed: missing {needle}")

    p.write_text(text, encoding="utf-8")


def patch_web_app(repo: Path) -> None:
    p = repo / "web" / "app.js"
    text = p.read_text(encoding="utf-8")

    text = regex_once(
        text,
        r"var\s+clLoginMode\s*=\s*['\"](?:password|code)['\"];",
        "var clLoginMode = 'code';",
        "default email-code mode",
    )

    new_mode_fn = '''function clSetLoginMode(m){
  // Smart Home v8.3 intentionally permits only the Bambu email-code flow.
  clLoginMode = 'code';
  var passBtn = document.getElementById('cl-mode-pass-btn');
  var codeBtn = document.getElementById('cl-mode-code-btn');
  var passWrap = document.getElementById('cl_passWrap');
  if (passBtn) passBtn.setAttribute('aria-pressed', 'false');
  if (codeBtn) codeBtn.setAttribute('aria-pressed', 'true');
  if (passWrap) passWrap.style.display = 'none';
  document.getElementById('cl_signinBtn').textContent = 'Email me a code';
}'''
    text = regex_once(
        text,
        r'function\s+clSetLoginMode\s*\(m\)\s*\{.*?\n\}',
        new_mode_fn,
        "force email-code mode",
        re.S,
    )

    # Initialize the sign-in pane explicitly in code-only mode. Be idempotent if
    # an earlier compatibility layer already inserted the call.
    if "clSetLoginMode('code');\n  fetch('/cloud/login/status')" not in text:
        text = replace_once(
            text,
            "  clSetAuthMethod('signin');\n  fetch('/cloud/login/status')",
            "  clSetAuthMethod('signin');\n  clSetLoginMode('code');\n  fetch('/cloud/login/status')",
            "initialize code-only mode",
        )

    # Remove the browser password serialization branch entirely. The device-side
    # route is also gated below, so both sides independently enforce the policy.
    text = regex_once(
        text,
        r"  p\.append\('mode',\s*clLoginMode\);\s*"
        r"if\s*\(clLoginMode\s*===\s*'password'\)\s*\{.*?\n  \}",
        "  p.append('mode', 'code');",
        "remove browser password serialization",
        re.S,
    )

    forbidden = [
        "p.append('password'",
        "p.append('save'",
        "clLoginMode = 'password'",
    ]
    for needle in forbidden:
        if needle in text:
            raise PatchError(f"passwordless browser validation failed: {needle} remains")

    p.write_text(text, encoding="utf-8")


def patch_web_server(repo: Path) -> None:
    p = repo / "src" / "web_server.cpp"
    text = p.read_text(encoding="utf-8")

    # Replace the existing code-mode fast path with a fail-closed mode gate.
    # The legacy password implementation can remain below for easier upstream
    # rebases, but is unreachable because every non-code request returns here.
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
