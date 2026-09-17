#!/usr/bin/env python3
"""Make OS12 microphone capture hand off I2S without deleting the ES8311 task.

The first physical WS350 recording test showed that force-deleting the live TX
producer task while it could be inside i2s_write destabilized the device. Keep
the single existing audio task alive and use an explicit pause/ack handshake so
RX capture owns the full-duplex peripheral without destroying task state.
"""
from __future__ import annotations

import argparse
from pathlib import Path


class PatchError(RuntimeError):
    pass


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise PatchError(f"{label}: expected one anchor, found {count}")
    return text.replace(old, new, 1)


def apply(repo: Path) -> None:
    path = repo / "src/buzzer_backend_es8311.cpp"
    if not path.is_file():
        raise PatchError(f"missing reconstructed source: {path}")
    text = path.read_text(encoding="utf-8")

    text = replace_once(
        text,
        "volatile bool gOs12CaptureOwnsAudioTask = false;",
        "volatile bool gOs12CapturePauseRequested = false;\nvolatile bool gOs12CaptureTxPaused = false;",
        "capture handoff state",
    )

    loop_anchor = """  while (!gShutdownRequested) {\n    if (gOs12PlaybackActive && gOs12RecordingData && gOs12PlaybackPosition < gOs12RecordingBytes) {"""
    loop_replacement = """  while (!gShutdownRequested) {\n    if (gOs12CapturePauseRequested) {\n      // Cooperative handoff: finish any in-flight write, acknowledge that TX\n      // is quiescent, and keep this task alive while main-loop RX capture owns\n      // the already-installed full-duplex I2S driver.\n      gOs12CaptureTxPaused = true;\n      while (gOs12CapturePauseRequested && !gShutdownRequested) {\n        vTaskDelay(pdMS_TO_TICKS(1));\n      }\n      gOs12CaptureTxPaused = false;\n      continue;\n    }\n    if (gOs12PlaybackActive && gOs12RecordingData && gOs12PlaybackPosition < gOs12RecordingBytes) {"""
    text = replace_once(text, loop_anchor, loop_replacement, "audio-task capture pause")

    old_helpers = """void os12ResumeAudioTaskAfterCapture() {\n  if (!gOs12CaptureOwnsAudioTask) return;\n  gOs12CaptureOwnsAudioTask = false;\n  // Reuse the existing ES8311 authority. ensureAudioRunning() recreates the\n  // normal TX task if needed; it does not install a competing I2S driver.\n  (void)ensureAudioRunning();\n}\n\nvoid os12SuspendAudioTaskForCapture() {\n  // The legacy v11.24 microphone diagnostic proved the safe pattern: do not\n  // read RX concurrently with the normal ES8311 TX task. Keep the installed\n  // full-duplex driver, but temporarily stop its producer task while capture\n  // polls RX from the main loop.\n  buzzerBackendStop();\n  TaskHandle_t task = (TaskHandle_t)gAudioTask;\n  if (task) {\n    gAudioTask = nullptr;\n    vTaskDelete(task);\n  }\n  gOs12CaptureOwnsAudioTask = true;\n}\n"""
    new_helpers = """void os12ResumeAudioTaskAfterCapture() {\n  gOs12CapturePauseRequested = false;\n  // Do not block waiting for the acknowledgement to clear. The existing task\n  // resumes on its next scheduler slice; ownership has already returned to it.\n}\n\nbool os12PauseAudioTxForCapture() {\n  buzzerBackendStop();\n  gOs12CapturePauseRequested = true;\n  const uint32_t started = millis();\n  while (!gOs12CaptureTxPaused && (millis() - started) < 120U) {\n    vTaskDelay(pdMS_TO_TICKS(1));\n  }\n  if (!gOs12CaptureTxPaused) {\n    gOs12CapturePauseRequested = false;\n    return false;\n  }\n  return true;\n}\n"""
    text = replace_once(text, old_helpers, new_helpers, "capture task handoff helpers")

    text = replace_once(
        text,
        "  os12SuspendAudioTaskForCapture();\n\n  // Drain stale RX DMA without blocking so capture starts at the user action.",
        "  if (!os12PauseAudioTxForCapture()) {\n    os12FreeRecording();\n    return false;\n  }\n\n  // Drain stale RX DMA without blocking so capture starts at the user action.",
        "capture begin handoff",
    )
    text = replace_once(
        text,
        "  if (gOs12RecordingActive || gOs12CaptureOwnsAudioTask) os12FinishRecording();",
        "  if (gOs12RecordingActive || gOs12CapturePauseRequested) os12FinishRecording();",
        "record stop handoff",
    )
    text = replace_once(
        text,
        "  if (gOs12RecordingActive || gOs12CaptureOwnsAudioTask || !buzzerBackendMicHasRecording()) return false;",
        "  if (gOs12RecordingActive || gOs12CapturePauseRequested || !buzzerBackendMicHasRecording()) return false;",
        "playback handoff guard",
    )

    if "vTaskDelete(task)" in text:
        raise PatchError("force-delete capture handoff survived fix")
    for marker in (
        "gOs12CapturePauseRequested",
        "gOs12CaptureTxPaused",
        "os12PauseAudioTxForCapture",
        "vTaskDelay(pdMS_TO_TICKS(1))",
    ):
        if marker not in text:
            raise PatchError(f"capture handoff fix missing {marker}")

    path.write_text(text, encoding="utf-8")
    print("Workshop OS 12 microphone capture cooperative I2S handoff installed")


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
        raise SystemExit(str(exc)) from exc
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
