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


def patch_web_pages(repo: Path) -> None:
    p = repo / "include" / "web_pages.h"
    text = p.read_text(encoding="utf-8")

    text = replace_once(
        text,
        '<p class="small text-dim" style="margin:0 0 var(--sp-3);line-height:1.6">The device signs in and fetches the token itself. This page has no password and runs over plain HTTP, so what you type here crosses your network unencrypted - use it on a network you trust.</p>',
        '<div class="banner" style="margin-bottom:var(--sp-3)"><span class="dot" style="background:var(--success)"></span><div><strong>Passwordless sign-in.</strong><div class="small text-dim" style="margin-top:4px">Smart Home v8 uses Bambu email-code authentication only. Your Bambu account password is never accepted by this local HTTP portal.</div></div></div>',
        "passwordless banner",
    )

    text = replace_once(
        text,
        '<div class="seg" style="margin-bottom:var(--sp-3)">\n          <button type="button" id="cl-mode-pass-btn" aria-pressed="true" onclick="clSetLoginMode(\'password\')">Password</button>\n          <button type="button" id="cl-mode-code-btn" aria-pressed="false" onclick="clSetLoginMode(\'code\')">Email code</button>\n        </div>',
        '<div class="seg" style="margin-bottom:var(--sp-3)">\n          <button type="button" id="cl-mode-pass-btn" aria-pressed="false" disabled style="display:none">Password</button>\n          <button type="button" id="cl-mode-code-btn" aria-pressed="true" disabled>Email code</button>\n        </div>',
        "login mode selector",
    )

    text = re.sub(
        r'<div id="cl_passWrap">',
        '<div id="cl_passWrap" style="display:none">',
        text,
        count=1,
    )
    if 'id="cl_passWrap" style="display:none"' not in text:
        raise PatchError("password field could not be hidden")

    p.write_text(text, encoding="utf-8")


def patch_web_app(repo: Path) -> None:
    p = repo / "web" / "app.js"
    text = p.read_text(encoding="utf-8")

    text = replace_once(text, "var clLoginMode = 'password';", "var clLoginMode = 'code';", "default email-code mode")

    old = '''function clSetLoginMode(m){
  clLoginMode = m;
  document.getElementById('cl-mode-pass-btn').setAttribute('aria-pressed', m === 'password');
  document.getElementById('cl-mode-code-btn').setAttribute('aria-pressed', m === 'code');
  document.getElementById('cl_passWrap').style.display = (m === 'password') ? '' : 'none';
  document.getElementById('cl_signinBtn').textContent = (m === 'password') ? 'Sign in' : 'Email me a code';
}
'''
    new = '''function clSetLoginMode(m){
  // Smart Home v8.3 intentionally permits only the Bambu email-code flow.
  clLoginMode = 'code';
  var passBtn = document.getElementById('cl-mode-pass-btn');
  var codeBtn = document.getElementById('cl-mode-code-btn');
  var passWrap = document.getElementById('cl_passWrap');
  if (passBtn) passBtn.setAttribute('aria-pressed', 'false');
  if (codeBtn) codeBtn.setAttribute('aria-pressed', 'true');
  if (passWrap) passWrap.style.display = 'none';
  document.getElementById('cl_signinBtn').textContent = 'Email me a code';
}
'''
    text = replace_once(text, old, new, "force email-code mode")

    text = replace_once(
        text,
        "  clSetAuthMethod('signin');\n  fetch('/cloud/login/status')",
        "  clSetAuthMethod('signin');\n  clSetLoginMode('code');\n  fetch('/cloud/login/status')",
        "initialize code-only mode",
    )

    old_branch = '''  p.append('mode', clLoginMode);
  if (clLoginMode === 'password'){
    p.append('password', document.getElementById('cl_pass').value);
    p.append('save', document.getElementById('cl_savePass').checked ? '1' : '0');
  }
'''
    new_branch = '''  p.append('mode', 'code');
'''
    text = replace_once(text, old_branch, new_branch, "remove browser password serialization")

    if "p.append('password'" in text:
        raise PatchError("browser password serialization remains")

    p.write_text(text, encoding="utf-8")


def patch_web_server(repo: Path) -> None:
    p = repo / "src" / "web_server.cpp"
    text = p.read_text(encoding="utf-8")

    anchor = '''  if (server.arg("mode") == "code") {
    cloudLoginRequestEmailCode(email.c_str());
    sendCloudLoginState();
    return;
  }

  String password = server.arg("password");
'''
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

  // Kept unreachable for source compatibility with upstream login internals;
  // the request gate above prevents this legacy password path from executing.
  String password = server.arg("password");
'''
    text = replace_once(text, anchor, replacement, "server password gate")

    if 'server.arg("mode") != "code"' not in text:
        raise PatchError("server code-only gate missing")

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
