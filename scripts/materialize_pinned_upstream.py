#!/usr/bin/env python3
"""Materialize the exact historical BambuHelper source tree used by Workshop OS.

The historical commit object is no longer reachable through a normal git fetch,
but GitHub still serves its immutable root tree and blob objects. This helper
uses that Git object identity directly rather than silently repinning Workshop OS
to a newer upstream revision.
"""
from __future__ import annotations

import argparse
import base64
import concurrent.futures
import hashlib
import json
import os
from pathlib import Path
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

OWNER = "Keralots"
REPO = "BambuHelper"
PINNED_COMMIT = "8cb1cbbb6d3c175af919e8ebe1bbdcbe848ac4"
PINNED_TREE = "754c5506bdac08033f0cdc3439e4814acd2b4294"
API = "https://api.github.com"

# Build inputs plus the small installer/web-flasher documents that the earliest
# Workshop OS evolution patches intentionally update. Large photos, historical
# prebuilt firmware and unrelated desktop tools remain excluded.
PREFIXES = (
    "boards/",
    "include/",
    "lib/",
    "src/",
    "web/",
    "scripts/",
)
EXACT = {
    "platformio.ini",
    "merge_bins.py",
    "partitions_4mb.csv",
    "partitions_8mb.csv",
    "partitions_8mb_app0.csv",
    "partitions_16mb.csv",
    "tools/gen_web_assets.py",
    "docs/index.html",
    "docs/styles.css",
    "docs/cloud-token.html",
    "docs/flasher.js",
    "docs/CNAME",
    "docs/.nojekyll",
}


def selected(path: str) -> bool:
    return path in EXACT or any(path.startswith(prefix) for prefix in PREFIXES)


def request_json(url: str, token: str | None, attempts: int = 4) -> dict:
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "WorkshopOS-pinned-upstream-materializer/1",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    last: Exception | None = None
    for attempt in range(attempts):
        try:
            with urlopen(Request(url, headers=headers), timeout=45) as response:
                return json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError) as exc:
            last = exc
            if attempt + 1 == attempts:
                break
            time.sleep(1.0 * (attempt + 1))
    raise RuntimeError(f"GitHub API request failed for {url}: {last}")


def git_blob_sha(data: bytes) -> str:
    header = f"blob {len(data)}\0".encode("ascii")
    return hashlib.sha1(header + data).hexdigest()


def fetch_blob(entry: dict, token: str | None) -> tuple[str, bytes, str]:
    path = entry["path"]
    expected = entry["sha"]
    payload = request_json(entry["url"], token)
    if payload.get("sha") != expected:
        raise RuntimeError(
            f"{path}: blob identity changed: expected {expected}, got {payload.get('sha')}"
        )
    if payload.get("encoding") != "base64":
        raise RuntimeError(f"{path}: unsupported blob encoding {payload.get('encoding')!r}")
    data = base64.b64decode(payload["content"], validate=False)
    actual = git_blob_sha(data)
    if actual != expected:
        raise RuntimeError(f"{path}: blob SHA verification failed: {actual} != {expected}")
    return path, data, expected


def materialize(dest: Path, token: str | None, workers: int) -> None:
    tree_url = f"{API}/repos/{OWNER}/{REPO}/git/trees/{PINNED_TREE}?recursive=1"
    tree = request_json(tree_url, token)
    if tree.get("sha") != PINNED_TREE:
        raise RuntimeError(
            f"root tree mismatch: expected {PINNED_TREE}, got {tree.get('sha')}"
        )
    if tree.get("truncated"):
        raise RuntimeError("GitHub returned a truncated pinned tree; refusing partial reconstruction")

    entries = [
        item for item in tree.get("tree", [])
        if item.get("type") == "blob" and selected(item.get("path", ""))
    ]
    if not entries:
        raise RuntimeError("no build-relevant blobs selected from pinned tree")

    required = {
        "platformio.ini",
        "merge_bins.py",
        "boards/ws_lcd_350.ini",
        "src/main.cpp",
        "src/settings.cpp",
        "src/settings.h",
        "src/display_ui.cpp",
        "src/button.cpp",
        "src/button.h",
        "src/web_server.cpp",
        "web/app.js",
        "web/app.css",
        "tools/gen_web_assets.py",
        "docs/index.html",
        "docs/styles.css",
        "docs/flasher.js",
    }
    paths = {entry["path"] for entry in entries}
    missing = sorted(required - paths)
    if missing:
        raise RuntimeError(f"pinned tree is missing required build inputs: {missing}")

    if dest.exists():
        if any(dest.iterdir()):
            raise RuntimeError(f"destination is not empty: {dest}")
    else:
        dest.mkdir(parents=True)

    print(f"Pinned upstream commit identity: {PINNED_COMMIT}")
    print(f"Pinned immutable tree: {PINNED_TREE}")
    print(f"Materializing {len(entries)} reconstruction/build blobs with {workers} workers")

    records: list[tuple[str, str]] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        future_map = {pool.submit(fetch_blob, entry, token): entry for entry in entries}
        for index, future in enumerate(concurrent.futures.as_completed(future_map), 1):
            path, data, sha = future.result()
            target = dest / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            records.append((path, sha))
            if index % 50 == 0 or index == len(entries):
                print(f"  verified {index}/{len(entries)} blobs")

    manifest = "".join(f"{sha}  {path}\n" for path, sha in sorted(records)).encode("utf-8")
    subset_sha256 = hashlib.sha256(manifest).hexdigest()
    (dest / ".workshop-pinned-upstream.txt").write_text(
        "\n".join(
            [
                f"commit={PINNED_COMMIT}",
                f"tree={PINNED_TREE}",
                f"materialized_blobs={len(records)}",
                f"selected_manifest_sha256={subset_sha256}",
                "",
            ]
        ),
        encoding="utf-8",
    )
    print(f"Selected manifest SHA256: {subset_sha256}")
    print("Exact pinned upstream materialization: PASS")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dest", default="upstream")
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()
    if args.workers < 1 or args.workers > 16:
        raise SystemExit("--workers must be between 1 and 16")
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    try:
        materialize(Path(args.dest).resolve(), token, args.workers)
    except Exception as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
