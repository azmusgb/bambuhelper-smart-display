#!/usr/bin/env python3
"""Expose OS12 MediaService through a narrow authenticated diagnostics API.

The API never accepts arbitrary media URLs and does not create a second media
implementation. It reports MediaService truth and invokes only bounded local
speaker/microphone/recording diagnostics.
"""
from __future__ import annotations

import argparse
from pathlib import Path


class PatchError(RuntimeError):
    pass


HANDLERS = r'''
// ---------------------------------------------------------------------------
// Workshop OS 12 media diagnostics API
// ---------------------------------------------------------------------------
static void sendWorkshopMediaStatus(int httpCode = 200) {
  const workshop::media::Snapshot& snap = workshopMediaSnapshot();
  JsonDocument doc;
  doc["session"] = workshop::media::sessionStateName(snap.runtime.session);
  doc["error"] = workshop::media::mediaErrorName(snap.runtime.lastError);
  doc["speakerAvailable"] = snap.capabilities.speakerAvailable;
  doc["microphoneAvailable"] = snap.capabilities.microphoneAvailable;
  doc["videoDecoderAvailable"] = snap.capabilities.videoDecoderAvailable;
  doc["psramAvailable"] = snap.capabilities.psramAvailable;
  doc["psramFreeBytes"] = (uint32_t)snap.capabilities.psramFreeBytes;
  doc["volumePercent"] = snap.runtime.volumePercent;
  doc["muted"] = snap.runtime.muted;
  doc["microphoneLevelPercent"] = snap.runtime.microphoneLevelPercent;
  doc["recordingAvailable"] = snap.runtime.recordingAvailable;
  doc["audioUnderruns"] = snap.runtime.audioUnderruns;
  doc["droppedVideoFrames"] = snap.runtime.droppedVideoFrames;
  String json;
  serializeJson(doc, json);
  server.sendHeader("Cache-Control", "no-store");
  server.send(httpCode, "application/json", json);
}

static void handleWorkshopMediaStatus() {
  sendWorkshopMediaStatus();
}

static void handleWorkshopMediaSpeakerTest() {
  workshop::media::MediaService& media = workshopMediaService();
  const bool started = media.testSpeaker(millis());
  sendWorkshopMediaStatus(started ? 202 : 409);
}

static void handleWorkshopMediaMicrophoneSample() {
  workshop::media::MediaService& media = workshopMediaService();
  const bool sampled = media.sampleMicrophone(millis());
  sendWorkshopMediaStatus(sampled ? 200 : 409);
}

static void handleWorkshopMediaRecordStart() {
  workshop::media::MediaService& media = workshopMediaService();
  const bool started = media.startRecording(5000U, millis());
  sendWorkshopMediaStatus(started ? 202 : 409);
}

static void handleWorkshopMediaRecordStop() {
  workshop::media::MediaService& media = workshopMediaService();
  const bool stopped = media.stopRecording(millis());
  sendWorkshopMediaStatus(stopped ? 200 : 409);
}

static void handleWorkshopMediaRecordPlay() {
  workshop::media::MediaService& media = workshopMediaService();
  const bool started = media.playRecording(millis());
  sendWorkshopMediaStatus(started ? 202 : 409);
}

static void handleWorkshopMediaStop() {
  workshop::media::MediaService& media = workshopMediaService();
  const bool stopped = media.stop(millis());
  sendWorkshopMediaStatus(stopped ? 200 : 409);
}
'''

ROUTES = '''  SECURE_GET("/os12/media/status", handleWorkshopMediaStatus);\n  SECURE_POST("/os12/media/speaker-test", handleWorkshopMediaSpeakerTest);\n  SECURE_POST("/os12/media/microphone-sample", handleWorkshopMediaMicrophoneSample);\n  SECURE_POST("/os12/media/record/start", handleWorkshopMediaRecordStart);\n  SECURE_POST("/os12/media/record/stop", handleWorkshopMediaRecordStop);\n  SECURE_POST("/os12/media/record/play", handleWorkshopMediaRecordPlay);\n  SECURE_POST("/os12/media/stop", handleWorkshopMediaStop);\n'''


def load(path: Path) -> str:
    if not path.is_file():
        raise PatchError(f"missing {path}")
    return path.read_text(encoding="utf-8")


def apply(repo: Path) -> None:
    path = repo / "src/web_server.cpp"
    text = load(path)
    if not (repo / "include/workshop_media_runtime.h").is_file():
        raise PatchError("media runtime must be installed before media API")
    if "PortalLoginPageState" not in text:
        raise PatchError("portal authentication hardening must be present")

    if '#include "workshop_media_runtime.h"' not in text:
        anchor = '#include "workshop_update_service.h"\n'
        if text.count(anchor) != 1:
            raise PatchError("media API include anchor missing/non-unique")
        text = text.replace(anchor, anchor + '#include "workshop_media_runtime.h"\n', 1)

    if "sendWorkshopMediaStatus" not in text:
        marker = "void initWebServer() {\n"
        if text.count(marker) != 1:
            raise PatchError("web server init anchor missing/non-unique")
        text = text.replace(marker, HANDLERS + "\n" + marker, 1)

    if '/os12/media/status' not in text:
        route_anchor = '  SECURE_GET("/os12/update/status", handleWorkshopUpdateStatus);\n'
        if text.count(route_anchor) != 1:
            raise PatchError("authenticated OS12 route anchor missing/non-unique")
        text = text.replace(route_anchor, route_anchor + ROUTES, 1)

    for route in (
        '/os12/media/status',
        '/os12/media/speaker-test',
        '/os12/media/microphone-sample',
        '/os12/media/record/start',
        '/os12/media/record/stop',
        '/os12/media/record/play',
        '/os12/media/stop',
    ):
        if text.count(route) != 1:
            raise PatchError(f"media route missing/non-unique: {route}")

    init_start = text.find("void initWebServer() {")
    init_end = text.find("\nvoid handleWebServer()", init_start)
    if init_start < 0 or init_end < 0:
        raise PatchError("web route-registration block missing")
    registration = text[init_start:init_end]
    if 'server.on("/os12/media/' in registration:
        raise PatchError("media mutations must use authenticated SECURE routes")

    path.write_text(text, encoding="utf-8")
    print("Workshop OS 12 authenticated media diagnostics API installed")


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
