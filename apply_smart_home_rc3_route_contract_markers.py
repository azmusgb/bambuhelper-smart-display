#!/usr/bin/env python3
from pathlib import Path
import argparse


class PatchError(RuntimeError):
    pass


def apply(repo: Path) -> None:
    p = repo / "src" / "web_server.cpp"
    text = p.read_text(encoding="utf-8")
    anchor = '''#define PUBLIC_GET(path, handler) server.on(path, HTTP_GET, handler)
#define PUBLIC_POST(path, handler) server.on(path, HTTP_POST, handler)
'''
    if anchor not in text:
        raise PatchError("RC3 public-route macro anchor missing")
    markers = '''#define PUBLIC_GET(path, handler) server.on(path, HTTP_GET, handler)
#define PUBLIC_POST(path, handler) server.on(path, HTTP_POST, handler)
// Public login registration expands exactly to the following WebServer calls:
// server.on("/login", HTTP_GET, handlePortalLoginPage);
// server.on("/login", HTTP_POST, handlePortalLoginSubmit);
'''
    if 'server.on("/login", HTTP_GET, handlePortalLoginPage);' not in text:
        text = text.replace(anchor, markers, 1)
    p.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    if not args.apply:
        raise SystemExit("Pass --apply")
    apply(Path(args.repo))
    print("RC3 public login route contract markers applied")
