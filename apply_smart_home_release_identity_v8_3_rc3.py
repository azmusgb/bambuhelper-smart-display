#!/usr/bin/env python3
from pathlib import Path
import argparse


class PatchError(RuntimeError):
    pass


def replace_once(text: str, old: str, new: str, name: str) -> str:
    count = text.count(old)
    if count != 1:
        raise PatchError(f"{name}: expected exactly 1 match, found {count}")
    return text.replace(old, new, 1)


def apply(repo: Path) -> None:
    hub = repo / "src" / "smart_hub.cpp"
    text = hub.read_text(encoding="utf-8")
    text = replace_once(
        text,
        'snprintf(build, sizeof(build), "%s · %s", SMART_HOME_VERSION, SMART_HOME_UPSTREAM_SHA_SHORT);',
        'snprintf(build, sizeof(build), "%s RC3 · %s", SMART_HOME_VERSION, SMART_HOME_UPSTREAM_SHA_SHORT);',
        "System RC3 provenance",
    )
    hub.write_text(text, encoding="utf-8")

    build = repo / "include" / "smart_home_build.h"
    text = build.read_text(encoding="utf-8")
    text = replace_once(
        text,
        '#define SMART_HOME_BUILD_LABEL "Smart Home v8.3 Hardening RC"',
        '#define SMART_HOME_BUILD_LABEL "Smart Home v8.3 RC3"',
        "RC3 build label",
    )
    build.write_text(text, encoding="utf-8")

    if "v8.3 RC3" not in hub.read_text(encoding="utf-8"):
        raise PatchError("RC3 physical identity missing")
    if '#define SMART_HOME_BUILD_LABEL "Smart Home v8.3 RC3"' not in build.read_text(encoding="utf-8"):
        raise PatchError("RC3 build label missing")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    if not args.apply:
        raise SystemExit("Pass --apply")
    apply(Path(args.repo))
    print("Smart Home v8.3 RC3 release identity applied")
