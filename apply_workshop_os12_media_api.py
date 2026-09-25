#!/usr/bin/env python3
"""Expose OS12 MediaService through a narrow authenticated diagnostics API.

The API never accepts arbitrary media URLs and does not create a second media
implementation. It reports MediaService truth and invokes only bounded local
speaker/microphone/recording/video diagnostics.
"""
from __future__ import annotations

import argparse
from pathlib import Path




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
  doc["deviceUptimeMs"] = (uint32_t)millis();
#if defined(BOARD_HAS_ES8311_AUDIO)
  doc["audioCodecReady"] = buzzerBackendCodecReady();
  doc["audioI2sReady"] = buzzerBackendI2sReady();
  doc["audioPipelineRunning"] = buzzerBackendAudioRunning();
  doc["microphoneLastBytes"] = buzzerBackendMicLastBytes();
  doc["microphoneLastSamples"] = buzzerBackendMicLastSamples();
  doc["microphoneLastNonZeroSamples"] = buzzerBackendMicLastNonZeroSamples();
  doc["microphoneLastPeak"] = buzzerBackendMicLastPeak();
  doc["audioAmpEnabled"] = buzzerBackendAmpEnabled();
  doc["audioCurrentFrequency"] = buzzerBackendAudioCurrentFrequency();
  doc["audioTargetGain"] = buzzerBackendAudioTargetGain();
  doc["audioCurrentGain"] = buzzerBackendAudioCurrentGain();
#else
  doc["audioCodecReady"] = false;
  doc["audioI2sReady"] = false;
  doc["audioPipelineRunning"] = false;
  doc["microphoneLastBytes"] = 0;
  doc["microphoneLastSamples"] = 0;
  doc["microphoneLastNonZeroSamples"] = 0;
  doc["microphoneLastPeak"] = 0;
  doc["audioAmpEnabled"] = false;
  doc["audioCurrentFrequency"] = 0;
  doc["audioTargetGain"] = 0;
  doc["audioCurrentGain"] = 0;
#endif
  const bool printerConfigured = isAnyPrinterConfigured();
  const PrinterSlot* printer = printerConfigured ? &displayedPrinter() : nullptr;
  doc["printerConfigured"] = printerConfigured;
  doc["printerCameraObserved"] = printer ? printer->state.ipcamSeen : false;
  doc["printerLiveviewPreview"] = printer ? printer->state.liveviewPreview : false;
  doc["printerRtspEnabled"] = printer ? printer->state.rtspEnabled : false;
  doc["printerCameraResolution"] = printer ? printer->state.cameraResolution : "";
  doc["printerBrtcEnabled"] = printer ? printer->state.brtcServiceEnabled : false;
  doc["printerTutkEnabled"] = printer ? printer->state.tutkServiceEnabled : false;
  const workshop::media::VideoDiagnostics& video = workshopVideoDiagnostics();
  doc["videoPolls"] = video.polls;
  doc["videoNoFramePolls"] = video.noFramePolls;
  doc["videoFrameObservations"] = video.frameObservations;
  doc["videoFramesRendered"] = video.framesRendered;
  doc["videoLastFrameId"] = video.lastFrameId;
  doc["videoLastFrameBytes"] = video.lastFrameBytes;
  doc["videoLastFrameAtMs"] = video.lastFrameAtMs;
  CameraTransportDiagnostics cameraDiag;
  cameraGetTransportDiagnostics(&cameraDiag);
  doc["cameraSocketConnected"] = cameraDiag.socketConnected;
  doc["cameraConnectAttempts"] = cameraDiag.connectAttempts;
  doc["cameraConnectSuccesses"] = cameraDiag.connectSuccesses;
  doc["cameraConnectFailures"] = cameraDiag.connectFailures;
  doc["cameraAuthWrites"] = cameraDiag.authWrites;
  doc["cameraBytesRead"] = cameraDiag.bytesRead;
  doc["cameraParserResets"] = cameraDiag.parserResets;
  doc["cameraFramesPublished"] = cameraDiag.framesPublished;
  doc["cameraLastReadAtMs"] = cameraDiag.lastReadAtMs;
  String json;
  serializeJson(doc, json);
  server.sendHeader("Cache-Control", "no-store");
  server.send(httpCode, "application/json", json);
}

static void handleWorkshopMediaStatus() {
  sendWorkshopMediaStatus();
}

static void handleWorkshopMediaSpeakerVolume() {
  if (!server.hasArg("percent")) {
    sendWorkshopMediaStatus(400);
    return;
  }
  const int requested = server.arg("percent").toInt();
  if (requested < 0 || requested > 100) {
    sendWorkshopMediaStatus(400);
    return;
  }
  workshop::media::MediaService& media = workshopMediaService();
  const bool changed = media.setVolume((uint8_t)requested);
  sendWorkshopMediaStatus(changed ? 200 : 409);
}

static void handleWorkshopMediaSpeakerMute() {
  if (!server.hasArg("muted")) {
    sendWorkshopMediaStatus(400);
    return;
  }
  const String raw = server.arg("muted");
  bool muted = false;
  if (raw == "1" || raw == "true") muted = true;
  else if (raw == "0" || raw == "false") muted = false;
  else {
    sendWorkshopMediaStatus(400);
    return;
  }
  workshop::media::MediaService& media = workshopMediaService();
  const bool changed = media.setMuted(muted);
  sendWorkshopMediaStatus(changed ? 200 : 409);
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

static void handleWorkshopMediaVideoStart() {
  workshop::media::MediaService& media = workshopMediaService();
  // Fixed built-in source only. Video is a WS350 media capability; no arbitrary URL/path input is accepted.
  const bool started = media.playMjpeg("demo-video", millis());
  sendWorkshopMediaStatus(started ? 202 : 409);
}

static void handleWorkshopMediaVideoPause() {
  workshop::media::MediaService& media = workshopMediaService();
  const bool paused = media.pauseVideo(true, millis());
  sendWorkshopMediaStatus(paused ? 200 : 409);
}

static void handleWorkshopMediaVideoResume() {
  workshop::media::MediaService& media = workshopMediaService();
  const bool resumed = media.pauseVideo(false, millis());
  sendWorkshopMediaStatus(resumed ? 200 : 409);
}

static void handleWorkshopMediaStop() {
  workshop::media::MediaService& media = workshopMediaService();
  const bool stopped = media.stop(millis());
  sendWorkshopMediaStatus(stopped ? 200 : 409);
}
'''

ROUTES = '''  SECURE_GET("/os12/media/status", handleWorkshopMediaStatus);\n  SECURE_POST("/os12/media/volume", handleWorkshopMediaSpeakerVolume);\n  SECURE_POST("/os12/media/mute", handleWorkshopMediaSpeakerMute);\n  SECURE_POST("/os12/media/speaker-test", handleWorkshopMediaSpeakerTest);\n  SECURE_POST("/os12/media/microphone-sample", handleWorkshopMediaMicrophoneSample);\n  SECURE_POST("/os12/media/record/start", handleWorkshopMediaRecordStart);\n  SECURE_POST("/os12/media/record/stop", handleWorkshopMediaRecordStop);\n  SECURE_POST("/os12/media/record/play", handleWorkshopMediaRecordPlay);\n  SECURE_POST("/os12/media/video/start", handleWorkshopMediaVideoStart);\n  SECURE_POST("/os12/media/video/pause", handleWorkshopMediaVideoPause);\n  SECURE_POST("/os12/media/video/resume", handleWorkshopMediaVideoResume);\n  SECURE_POST("/os12/media/stop", handleWorkshopMediaStop);\n'''


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
        text = text.replace(anchor, anchor + '#include "workshop_media_runtime.h"\n#include "camera_client.h"\n#include "buzzer_backend.h"\n', 1)

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
        '/os12/media/volume',
        '/os12/media/mute',
        '/os12/media/speaker-test',
        '/os12/media/microphone-sample',
        '/os12/media/record/start',
        '/os12/media/record/stop',
        '/os12/media/record/play',
        '/os12/media/video/start',
        '/os12/media/video/pause',
        '/os12/media/video/resume',
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
