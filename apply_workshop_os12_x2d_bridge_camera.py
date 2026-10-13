#!/usr/bin/env python3
"""Enable the fixed Mac X2D JPEG bridge on a reconstructed WS350 OS12 image.

This patch is intentionally experimental. It does not enable arbitrary media
URLs. The operator supplies one private-LAN HTTP endpoint at build time; the
firmware compiles that exact endpoint and exposes a dedicated authenticated
start route that always selects the fixed ``x2d-bridge`` media source.
"""
from __future__ import annotations

import argparse
import ipaddress
from pathlib import Path
import re
from urllib.parse import urlparse

from scripts.smart_home_patch_utils import PatchError


HANDLER = r'''
static void handleWorkshopMediaVideoStartX2dBridge() {
  workshop::media::MediaService& media = workshopMediaService();
  // Fixed build-time bridge source only. No request URL/path is accepted.
  const bool started = media.playMjpeg("x2d-bridge", millis());
  sendWorkshopMediaStatus(started ? 202 : 409);
}

'''

ROUTE = '  SECURE_POST("/os12/media/video/start-x2d-bridge", handleWorkshopMediaVideoStartX2dBridge);\n'


def validate_bridge_url(raw: str) -> str:
    parsed = urlparse(raw)
    if parsed.scheme != "http" or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise PatchError("bridge URL must be plain HTTP with no credentials/query/fragment")
    if parsed.path != "/x2d/frame.jpg":
        raise PatchError("bridge URL path must be exactly /x2d/frame.jpg")
    if parsed.port is None:
        raise PatchError("bridge URL must include an explicit port")
    try:
        address = ipaddress.ip_address(parsed.hostname or "")
    except ValueError as exc:
        raise PatchError("bridge host must be a literal private LAN IP address") from exc
    if not address.is_private:
        raise PatchError("bridge host must be a private LAN IP address")
    return f"http://{address}:{parsed.port}/x2d/frame.jpg"


def apply(repo: Path, bridge_url: str) -> None:
    backend = repo / "src/ws350_media_backend.cpp"
    web = repo / "src/web_server.cpp"
    if not backend.is_file() or not web.is_file():
        raise PatchError("X2D bridge patch requires reconstructed OS12 media runtime and web server")

    backend_text = backend.read_text(encoding="utf-8")
    if "kX2dBridgeSource" not in backend_text or "renderX2dBridgeFrame" not in backend_text:
        raise PatchError("canonical X2D bridge-capable WS350 media backend is not installed")

    empty_define = '#define WORKSHOP_X2D_BRIDGE_URL ""'
    configured_define_pattern = re.compile(r'^#define WORKSHOP_X2D_BRIDGE_URL "[^"]*"$', re.MULTILINE)
    replacement = f'#define WORKSHOP_X2D_BRIDGE_URL "{bridge_url}"'
    match = configured_define_pattern.search(backend_text)
    if not match:
        raise PatchError("WORKSHOP_X2D_BRIDGE_URL build-time anchor missing")
    backend_text = backend_text[:match.start()] + replacement + backend_text[match.end():]
    backend.write_text(backend_text, encoding="utf-8")

    web_text = web.read_text(encoding="utf-8")
    if "sendWorkshopMediaStatus" not in web_text or "/os12/media/video/start" not in web_text:
        raise PatchError("authenticated OS12 media API must be installed before X2D bridge route")

    if "handleWorkshopMediaVideoStartX2dBridge" not in web_text:
        anchor = "static void handleWorkshopMediaVideoPause() {\n"
        if web_text.count(anchor) != 1:
            raise PatchError("media video pause handler anchor missing/non-unique")
        web_text = web_text.replace(anchor, HANDLER + anchor, 1)

    if "/os12/media/video/start-x2d-bridge" not in web_text:
        route_anchor = '  SECURE_POST("/os12/media/video/start", handleWorkshopMediaVideoStart);\n'
        if web_text.count(route_anchor) != 1:
            raise PatchError("media video start route anchor missing/non-unique")
        web_text = web_text.replace(route_anchor, route_anchor + ROUTE, 1)

    if web_text.count("/os12/media/video/start-x2d-bridge") != 1:
        raise PatchError("X2D bridge route missing/non-unique after patch")
    if 'server.on("/os12/media/video/start-x2d-bridge"' in web_text:
        raise PatchError("X2D bridge route must remain authenticated")
    if 'media.playMjpeg("x2d-bridge", millis())' not in web_text:
        raise PatchError("X2D bridge handler is not fixed to x2d-bridge source")

    web.write_text(web_text, encoding="utf-8")
    print(f"Workshop OS 12 X2D bridge camera enabled at {bridge_url}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True)
    parser.add_argument("--bridge-url", required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    if not args.apply:
        raise SystemExit("refusing to modify source without --apply")
    try:
        bridge_url = validate_bridge_url(args.bridge_url)
        apply(Path(args.repo).resolve(), bridge_url)
    except PatchError as exc:
        raise SystemExit(str(exc)) from exc
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
