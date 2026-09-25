#!/usr/bin/env python3
"""Stamp an exact Workshop OS release identity into reconstructed firmware.

OS12 needs a release version independent from the frozen UI13 implementation
version. The device updater compares this release version to the manifest and
reports the exact source commit that produced the running binary. Publishing
workflows must never reuse a release version for different bytes.
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path
from scripts.smart_home_patch_utils import PatchError, fail, replace_once, replace_braced_block




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

    header_path = repo / "include" / "workshop_update_service.h"
    header = load(header_path)
    header = replace_once(
        header,
        '    char runningVersion[workshop::platform::kVersionLabelLength]{};\n',
        '    char runningVersion[workshop::platform::kVersionLabelLength]{};\n'
        '    char runningSourceCommit[41]{};\n',
        "running source identity field",
    )
    header_path.write_text(header, encoding="utf-8")

    service_path = repo / "src" / "workshop_update_service.cpp"
    service = load(service_path)

    # The early OS12 template carried an unused source-SHA fallback under a
    # different macro name. Construct that historical token rather than keeping
    # it as a live source marker, then normalize the reconstructed implementation.
    legacy_source_macro = "WORKSHOP_OS12_" + "SOURCE_SHA"
    service = service.replace(
        f'#ifndef {legacy_source_macro}\n#define {legacy_source_macro} "unknown"\n#endif',
        '#ifndef WORKSHOP_OS_SOURCE_SHA\n#define WORKSHOP_OS_SOURCE_SHA "unknown"\n#endif',
        1,
    )

    count = service.count("SMART_HOME_VERSION")
    if count != 2:
        raise PatchError(f"expected two SMART_HOME_VERSION update-service references, found {count}")
    service = service.replace("SMART_HOME_VERSION", "WORKSHOP_OS_RELEASE_VERSION")

    source_anchor = (
        '    copyText(g_runtime.runningVersion, sizeof(g_runtime.runningVersion), '
        'WORKSHOP_OS_RELEASE_VERSION);\n'
    )
    source_publish = (
        source_anchor
        + '    copyText(g_runtime.runningSourceCommit, sizeof(g_runtime.runningSourceCommit), '
        'WORKSHOP_OS_SOURCE_SHA);\n'
    )
    service = replace_once(
        service,
        source_anchor,
        source_publish,
        "running source identity publication",
    )
    service_path.write_text(service, encoding="utf-8")

    web_path = repo / "src" / "web_server.cpp"
    web = load(web_path)
    web = replace_once(
        web,
        '  doc["runningVersion"] = snap.runningVersion;\n',
        '  doc["runningVersion"] = snap.runningVersion;\n'
        '  doc["runningSourceCommit"] = snap.runningSourceCommit;\n',
        "running source identity API",
    )
    web_path.write_text(web, encoding="utf-8")

    if service.count("WORKSHOP_OS_RELEASE_VERSION") != 2:
        raise PatchError("release version was not applied to both update comparison/reporting paths")
    if service.count("WORKSHOP_OS_SOURCE_SHA") < 2:
        raise PatchError("running source SHA is not compiled into update runtime")
    if "runningSourceCommit" not in header or "runningSourceCommit" not in web:
        raise PatchError("running source SHA is not exposed through the runtime status contract")

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
