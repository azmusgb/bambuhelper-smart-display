#!/usr/bin/env python3
"""Stamp an exact Workshop OS release identity into reconstructed firmware.

OS12 needs a release version independent from the frozen UI13 implementation
version. The device updater compares this release version to the manifest and
reports the source commit that produced the binary. Publishing workflows must
never reuse a release version for different bytes.
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path


class PatchError(RuntimeError):
    pass


VERSION_RE = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")
SHA_RE = re.compile(r"^[0-9a-f]{40}$")


def load(path: Path) -> str:
    if not path.is_file():
        raise PatchError(f"missing {path}")
    return path.read_text(encoding="utf-8")


def apply(repo: Path, version: str, source_sha: str) -> None:
    if not VERSION_RE.fullmatch(version):
        raise PatchError("release version must be numeric MAJOR.MINOR.PATCH")
    if not SHA_RE.fullmatch(source_sha):
        raise PatchError("source SHA must be exactly 40 lowercase hex characters")

    build_path = repo / "include" / "smart_home_build.h"
    build = load(build_path)
    if "WORKSHOP_OS12_DEVICE_UPDATE" not in build:
        raise PatchError("device-native update slice must be applied before release identity")

    # The device-update patcher installs a fallback macro. Replace it with one
    # exact identity for this build so post-reboot reporting and future update
    # comparison refer to the bytes that were actually built.
    fallback = '''#ifndef WORKSHOP_OS_RELEASE_VERSION
#define WORKSHOP_OS_RELEASE_VERSION SMART_HOME_VERSION
#endif
'''
    exact = f'''#ifdef WORKSHOP_OS_RELEASE_VERSION
#undef WORKSHOP_OS_RELEASE_VERSION
#endif
#define WORKSHOP_OS_RELEASE_VERSION "{version}"
#define WORKSHOP_OS_SOURCE_SHA "{source_sha}"
'''
    if fallback in build:
        build = build.replace(fallback, exact, 1)
    elif "#define WORKSHOP_OS_RELEASE_VERSION" not in build:
        build += "\n" + exact
    else:
        build = re.sub(
            r'#define WORKSHOP_OS_RELEASE_VERSION\s+"[^"]+"',
            f'#define WORKSHOP_OS_RELEASE_VERSION "{version}"',
            build,
            count=1,
        )
        if "#define WORKSHOP_OS_SOURCE_SHA" in build:
            build = re.sub(
                r'#define WORKSHOP_OS_SOURCE_SHA\s+"[0-9a-f]+"',
                f'#define WORKSHOP_OS_SOURCE_SHA "{source_sha}"',
                build,
                count=1,
            )
        else:
            build += f'\n#define WORKSHOP_OS_SOURCE_SHA "{source_sha}"\n'
    build_path.write_text(build, encoding="utf-8")

    service_path = repo / "src" / "workshop_update_service.cpp"
    service = load(service_path)
    count = service.count("SMART_HOME_VERSION")
    if count != 2:
        raise PatchError(f"expected two SMART_HOME_VERSION update-service references, found {count}")
    service = service.replace("SMART_HOME_VERSION", "WORKSHOP_OS_RELEASE_VERSION")
    service_path.write_text(service, encoding="utf-8")

    if service.count("WORKSHOP_OS_RELEASE_VERSION") != 2:
        raise PatchError("release version was not applied to both update comparison/reporting paths")

    print(f"Workshop OS release identity: {version} @ {source_sha}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    if not args.apply:
        raise SystemExit("refusing to modify source without --apply")
    try:
        apply(Path(args.repo).resolve(), args.version, args.source_sha)
    except PatchError as exc:
        raise SystemExit(f"FAIL: {exc}") from exc
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
