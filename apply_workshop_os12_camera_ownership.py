#!/usr/bin/env python3
"""Give OS12 Media explicit ownership of the shared Bambu camera transport.

The legacy dashboard camera lifecycle historically owned cameraBegin/cameraStop
based on SCREEN_CAMERA / visible GAUGE_CAMERA state. OS12 Media can also use the
same bounded camera transport. Without ownership, the legacy loop tears down an
OS12 media session immediately whenever no legacy camera tile/screen is active.

This patch keeps one camera transport authority and adds only an ownership bit:
- Dashboard lifecycle manages the camera only when Media does not own it.
- Media claims ownership before cameraBegin and releases it on stop/failure.
- Auto-rotation is frozen while Media owns the stream so displayedPrinter()
  cannot drift underneath the active camera session.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import sys as _sys
from pathlib import Path as _Path
_here = _Path(__file__).resolve().parent
if str(_here) not in _sys.path:
    _sys.path.insert(0, str(_here))
from scripts.smart_home_patch_utils import PatchError




def load(path: Path) -> str:
    if not path.is_file():
        raise PatchError(f"missing reconstructed source: {path}")
    return path.read_text(encoding="utf-8")


def once(text: str, old: str, new: str, label: str) -> str:
    if new in text:
        return text
    count = text.count(old)
    if count != 1:
        raise PatchError(f"{label}: expected one anchor, found {count}")
    return text.replace(old, new, 1)


def apply(repo: Path) -> None:
    camera_h = repo / "src/camera_client.h"
    camera_cpp = repo / "src/camera_client.cpp"
    backend_cpp = repo / "src/ws350_media_backend.cpp"
    main_cpp = repo / "src/main.cpp"

    h = load(camera_h)
    h = once(
        h,
        "bool cameraActive();\n",
        "bool cameraActive();\n"
        "void cameraSetMediaOwned(bool owned);\n"
        "bool cameraMediaOwned();\n",
        "camera ownership declarations",
    )
    camera_h.write_text(h, encoding="utf-8")

    c = load(camera_cpp)
    c = once(
        c,
        "static bool              g_active = false;\n",
        "static bool              g_active = false;\n"
        "static bool              g_mediaOwned = false;\n",
        "camera ownership state",
    )
    c = once(
        c,
        "bool cameraActive() { return g_active; }\n",
        "bool cameraActive() { return g_active; }\n"
        "void cameraSetMediaOwned(bool owned) { g_mediaOwned = owned; }\n"
        "bool cameraMediaOwned() { return g_mediaOwned; }\n",
        "camera ownership implementation",
    )
    c = once(
        c,
        "bool cameraActive() { return false; }\n"
        "void cameraService() {}\n",
        "bool cameraActive() { return false; }\n"
        "void cameraSetMediaOwned(bool) {}\n"
        "bool cameraMediaOwned() { return false; }\n"
        "void cameraService() {}\n",
        "non-camera ownership stubs",
    )
    camera_cpp.write_text(c, encoding="utf-8")

    b = load(backend_cpp)
    begin_old = """    if (!cameraCanStreamDisplayedPrinter()) return false;
    cameraBegin();
    if (!cameraActive()) return false;
    next = VideoSource::PrinterCamera;
"""
    begin_new = """    if (!cameraCanStreamDisplayedPrinter()) return false;
    cameraSetMediaOwned(true);
    cameraBegin();
    if (!cameraActive()) {
      cameraSetMediaOwned(false);
      return false;
    }
    next = VideoSource::PrinterCamera;
"""
    b = once(b, begin_old, begin_new, "Media camera ownership claim")

    b = once(
        b,
        "  if (videoRequested_ && videoSource_ == VideoSource::PrinterCamera) cameraStop();\n"
        "  recordingRequested_ = false;\n",
        "  if (videoRequested_ && videoSource_ == VideoSource::PrinterCamera) {\n"
        "    cameraStop();\n"
        "    cameraSetMediaOwned(false);\n"
        "  }\n"
        "  recordingRequested_ = false;\n",
        "Media camera ownership release",
    )

    b = once(
        b,
        "      if (!cameraActive()) {\n"
        "        videoRequested_ = false;\n"
        "        videoPaused_ = false;\n",
        "      if (!cameraActive()) {\n"
        "        cameraSetMediaOwned(false);\n"
        "        videoRequested_ = false;\n"
        "        videoPaused_ = false;\n",
        "Media ownership release on inactive camera",
    )
    backend_cpp.write_text(b, encoding="utf-8")

    m = load(main_cpp)
    legacy_old = """  {
    bool wantCamera = cameraCanStreamDisplayedPrinter() &&
        (getScreenState() == SCREEN_CAMERA ||
         (getScreenState() == SCREEN_PRINTING && cameraDisplayedHasCameraTile()));
    if (cameraActive() && (!wantCamera || !cameraStreamingDisplayed())) cameraStop();
    if (wantCamera && !cameraActive())                                  cameraBegin();
  }
"""
    legacy_new = """  {
    // OS12 Media and the legacy dashboard share one bounded camera transport.
    // When Media owns it, the dashboard must not infer teardown from screen/tile
    // state. MediaService owns start/stop until it releases the transport.
    if (!cameraMediaOwned()) {
      bool wantCamera = cameraCanStreamDisplayedPrinter() &&
          (getScreenState() == SCREEN_CAMERA ||
           (getScreenState() == SCREEN_PRINTING && cameraDisplayedHasCameraTile()));
      if (cameraActive() && (!wantCamera || !cameraStreamingDisplayed())) cameraStop();
      if (wantCamera && !cameraActive())                                  cameraBegin();
    }
  }
"""
    m = once(m, legacy_old, legacy_new, "legacy dashboard camera ownership boundary")

    rotation_old = """    if (getScreenState() != SCREEN_CAMERA &&
        getScreenState() != SCREEN_POWER_CONFIRM &&
        getScreenState() != SCREEN_HMS &&
        getScreenState() != SCREEN_DRY_PEEK) handleRotation();
"""
    rotation_new = """    if (!cameraMediaOwned() &&
        getScreenState() != SCREEN_CAMERA &&
        getScreenState() != SCREEN_POWER_CONFIRM &&
        getScreenState() != SCREEN_HMS &&
        getScreenState() != SCREEN_DRY_PEEK) handleRotation();
"""
    m = once(m, rotation_old, rotation_new, "freeze rotation during Media camera ownership")
    main_cpp.write_text(m, encoding="utf-8")

    for needle, path in (
        ("cameraSetMediaOwned(true);", backend_cpp),
        ("if (!cameraMediaOwned())", main_cpp),
        ("bool cameraMediaOwned()", camera_cpp),
    ):
        if needle not in load(path):
            raise PatchError(f"ownership contract missing after patch: {needle}")

    print("Workshop OS 12 shared camera ownership boundary installed")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    if not args.apply:
        raise SystemExit("refusing to modify source without --apply")
    try:
        apply(Path(args.repo).resolve())
    except PatchError as exc:
        raise SystemExit(f"FAIL: {exc}") from exc
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
