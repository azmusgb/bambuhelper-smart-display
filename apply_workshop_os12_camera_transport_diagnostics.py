#!/usr/bin/env python3
"""Instrument the existing Bambu LAN camera transport without changing authority.

Adds bounded counters/status to camera_client so physical acceptance can
separate TCP/TLS/auth/read/parser failures from viewer/render failures.
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
    n=text.count(old)
    if n != 1:
        raise PatchError(f"{label}: expected one anchor, found {n}")
    return text.replace(old,new,1)

def apply(repo: Path) -> None:
    hpath=repo/"src/camera_client.h"
    cpath=repo/"src/camera_client.cpp"
    h=load(hpath); c=load(cpath)

    h=once(h,
        "bool cameraActive();\n",
        """bool cameraActive();

struct CameraTransportDiagnostics {
  uint32_t connectAttempts;
  uint32_t connectSuccesses;
  uint32_t connectFailures;
  uint32_t authWrites;
  uint32_t bytesRead;
  uint32_t parserResets;
  uint32_t framesPublished;
  uint32_t lastReadAtMs;
  bool socketConnected;
};
void cameraGetTransportDiagnostics(CameraTransportDiagnostics* out);
""",
        "camera diagnostics declaration")

    c=once(c,
        "static unsigned long g_lastConnectMs = 0;\n",
        """static unsigned long g_lastConnectMs = 0;

static CameraTransportDiagnostics g_diag = {0,0,0,0,0,0,0,0,false};
""",
        "camera diagnostics state")

    c=once(c,
        "  g_tls->write(pkt, sizeof(pkt));\n",
        """  const size_t written = g_tls->write(pkt, sizeof(pkt));
  if (written == sizeof(pkt)) ++g_diag.authWrites;
""",
        "camera auth write diagnostics")

    c=once(c,
        "  g_frameId++;\n",
        """  g_frameId++;
  ++g_diag.framesPublished;
""",
        "published-frame diagnostics")

    c=once(c,
        "static void teardownSocket() {\n  if (g_tls) { g_tls->stop(); delete g_tls; g_tls = nullptr; }\n  g_inflightLen = 0;\n}\n",
        """static void teardownSocket() {
  if (g_tls) { g_tls->stop(); delete g_tls; g_tls = nullptr; }
  g_diag.socketConnected = false;
  g_inflightLen = 0;
}
""",
        "socket teardown diagnostics")

    c=once(c,
        "  g_connectBackoffMs = CAM_CONNECT_MIN_MS;\n  g_active = true;\n",
        """  g_connectBackoffMs = CAM_CONNECT_MIN_MS;
  g_diag = CameraTransportDiagnostics{0,0,0,0,0,0,0,0,false};
  g_active = true;
""",
        "diagnostics reset on begin")

    c=once(c,
        "    esp_task_wdt_reset();\n    if (!g_tls->connect(g_ip, CAM_PORT)) {\n",
        """    esp_task_wdt_reset();
    ++g_diag.connectAttempts;
    if (!g_tls->connect(g_ip, CAM_PORT)) {
      ++g_diag.connectFailures;
""",
        "connect attempt diagnostics")

    c=once(c,
        "    sendAuth();\n    g_inflightLen = 0;\n",
        """    ++g_diag.connectSuccesses;
    g_diag.socketConnected = true;
    sendAuth();
    g_inflightLen = 0;
""",
        "connect success diagnostics")

    c=once(c,
        "    int n = g_tls->read(chunk, want);\n    if (n <= 0) break;\n    budget -= n;\n",
        """    int n = g_tls->read(chunk, want);
    if (n <= 0) break;
    g_diag.bytesRead += (uint32_t)n;
    g_diag.lastReadAtMs = millis();
    budget -= n;
""",
        "socket read diagnostics")

    c=once(c,
        "    if (g_inflightLen + (uint32_t)n > CAM_BUF_SIZE) g_inflightLen = 0;  // desync reset\n",
        """    if (g_inflightLen + (uint32_t)n > CAM_BUF_SIZE) {
      g_inflightLen = 0;  // desync reset
      ++g_diag.parserResets;
    }
""",
        "parser reset diagnostics")

    c=once(c,
        "bool cameraActive() { return g_active; }\n",
        """bool cameraActive() { return g_active; }
void cameraGetTransportDiagnostics(CameraTransportDiagnostics* out) {
  if (!out) return;
  g_diag.socketConnected = g_tls && g_tls->connected();
  *out = g_diag;
}
""",
        "camera diagnostics getter")

    c=once(c,
        "bool cameraActive() { return false; }\nvoid cameraSetMediaOwned(bool) {}\n",
        """bool cameraActive() { return false; }
void cameraGetTransportDiagnostics(CameraTransportDiagnostics* out) {
  if (!out) return;
  *out = CameraTransportDiagnostics{0,0,0,0,0,0,0,0,false};
}
void cameraSetMediaOwned(bool) {}
""",
        "non-camera diagnostics stub")

    hpath.write_text(h,encoding="utf-8")
    cpath.write_text(c,encoding="utf-8")
    print("Workshop OS 12 camera transport diagnostics installed")

def main() -> int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--repo",required=True)
    ap.add_argument("--apply",action="store_true")
    args=ap.parse_args()
    if not args.apply:
        raise SystemExit("refusing to modify source without --apply")
    try:
        apply(Path(args.repo).resolve())
    except PatchError as exc:
        raise SystemExit(f"FAIL: {exc}") from exc
    return 0

if __name__=="__main__":
    raise SystemExit(main())
