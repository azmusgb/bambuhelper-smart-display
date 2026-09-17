#!/usr/bin/env python3
"""Add bounded microphone record/playback to the existing ES8311 authority.

Recording keeps the installed full-duplex I2S driver and the single existing
ES8311 task running. RX is read into an internal-RAM scratch buffer, then copied
into PSRAM. This preserves TX clocks for the codec and avoids passing PSRAM
directly to the legacy I2S read path observed to destabilize the WS350.
"""
from __future__ import annotations

import argparse
from pathlib import Path


class PatchError(RuntimeError):
    pass


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


CAPTURE_DECLS = """int buzzerBackendMicLevel(uint16_t sampleMs);
bool buzzerBackendMicRecordBegin(uint32_t maxDurationMs);
bool buzzerBackendMicRecordPoll();
bool buzzerBackendMicRecordStop();
bool buzzerBackendMicHasRecording();
bool buzzerBackendMicPlaybackBegin();
bool buzzerBackendMicPlaybackPoll();
void buzzerBackendMicPlaybackStop();
"""

CAPTURE_STATE = r'''
uint8_t* gOs12RecordingData = nullptr;
size_t gOs12RecordingCapacity = 0;
volatile size_t gOs12RecordingBytes = 0;
volatile bool gOs12RecordingActive = false;
uint32_t gOs12RecordingDeadlineMs = 0;
volatile bool gOs12PlaybackActive = false;
volatile size_t gOs12PlaybackPosition = 0;
'''

CAPTURE_API = r'''
#if defined(BOARD_HAS_MICROPHONE) && defined(AUDIO_I2S_DIN) && (AUDIO_I2S_DIN >= 0)
namespace {
constexpr uint32_t kOs12RecordMinMs = 250U;
constexpr uint32_t kOs12RecordMaxMs = 5000U;
constexpr size_t kOs12CaptureBurstBytes = 1024U;
constexpr uint8_t kOs12CaptureBurstsPerPoll = 2U;

bool os12DeadlineReached(uint32_t deadlineMs) {
  return (int32_t)(millis() - deadlineMs) >= 0;
}

void os12FreeRecording() {
  if (gOs12RecordingData) {
    free(gOs12RecordingData);
    gOs12RecordingData = nullptr;
  }
  gOs12RecordingCapacity = 0;
  gOs12RecordingBytes = 0;
  gOs12RecordingActive = false;
  gOs12PlaybackActive = false;
  gOs12PlaybackPosition = 0;
}

void os12FinishRecording() {
  gOs12RecordingActive = false;
}
}

bool buzzerBackendMicRecordBegin(uint32_t maxDurationMs) {
  if (gOs12PlaybackActive) return false;
  if (maxDurationMs < kOs12RecordMinMs) maxDurationMs = kOs12RecordMinMs;
  if (maxDurationMs > kOs12RecordMaxMs) maxDurationMs = kOs12RecordMaxMs;
  if (!ensureAudioRunning()) return false;

  os12FreeRecording();
  const uint64_t bytes64 = ((uint64_t)kSampleRate * 2ULL * sizeof(int16_t) * maxDurationMs) / 1000ULL;
  if (bytes64 == 0 || bytes64 > 512000ULL) return false;
  const size_t capacity = (size_t)bytes64;
  gOs12RecordingData = static_cast<uint8_t*>(
      heap_caps_malloc(capacity, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT));
  if (!gOs12RecordingData) return false;

  // Keep the normal ES8311 task alive and streaming silence. Besides avoiding
  // task-lifecycle races, this keeps the I2S master clocks running for the
  // ES8311 ADC while RX is sampled from the main loop.
  buzzerBackendStop();

  uint8_t scratch[256];
  for (uint8_t i = 0; i < 4U; ++i) {
    size_t drained = 0;
    if (i2s_read((i2s_port_t)AUDIO_I2S_PORT, scratch, sizeof(scratch), &drained, 0) != ESP_OK || drained == 0) break;
  }

  gOs12RecordingCapacity = capacity;
  gOs12RecordingBytes = 0;
  gOs12RecordingDeadlineMs = millis() + maxDurationMs;
  gOs12RecordingActive = true;
  return true;
}

bool buzzerBackendMicRecordPoll() {
  if (!gOs12RecordingActive) return false;
  if (!gOs12RecordingData || gOs12RecordingCapacity == 0 || os12DeadlineReached(gOs12RecordingDeadlineMs)) {
    os12FinishRecording();
    return false;
  }

  // Never give the legacy I2S receive path a PSRAM destination. Read each
  // bounded burst into internal task-stack RAM, then copy the completed bytes
  // into the large PSRAM recording buffer.
  uint8_t captureScratch[kOs12CaptureBurstBytes];
  for (uint8_t burst = 0; burst < kOs12CaptureBurstsPerPoll; ++burst) {
    const size_t used = gOs12RecordingBytes;
    if (used >= gOs12RecordingCapacity) {
      os12FinishRecording();
      break;
    }
    const size_t remaining = gOs12RecordingCapacity - used;
    const size_t request = remaining < kOs12CaptureBurstBytes ? remaining : kOs12CaptureBurstBytes;
    size_t bytesRead = 0;
    const esp_err_t rc = i2s_read((i2s_port_t)AUDIO_I2S_PORT,
                                  captureScratch,
                                  request,
                                  &bytesRead,
                                  0);
    if (rc != ESP_OK) {
      os12FinishRecording();
      break;
    }
    if (bytesRead == 0) break;
    memcpy(gOs12RecordingData + used, captureScratch, bytesRead);
    gOs12RecordingBytes = used + bytesRead;
  }

  if (gOs12RecordingActive &&
      (gOs12RecordingBytes >= gOs12RecordingCapacity || os12DeadlineReached(gOs12RecordingDeadlineMs))) {
    os12FinishRecording();
  }
  return gOs12RecordingActive;
}

bool buzzerBackendMicRecordStop() {
  if (gOs12RecordingActive) os12FinishRecording();
  return gOs12RecordingData != nullptr && gOs12RecordingBytes > 0;
}

bool buzzerBackendMicHasRecording() {
  return gOs12RecordingData != nullptr && gOs12RecordingBytes > 0;
}

bool buzzerBackendMicPlaybackBegin() {
  if (gOs12RecordingActive || !buzzerBackendMicHasRecording()) return false;
  if (!ensureAudioRunning()) return false;
  buzzerBackendStop();
  gOs12PlaybackPosition = 0;
  gOs12PlaybackActive = true;
  return true;
}

bool buzzerBackendMicPlaybackPoll() {
  return gOs12PlaybackActive;
}

void buzzerBackendMicPlaybackStop() {
  gOs12PlaybackActive = false;
  gOs12PlaybackPosition = 0;
}
#else
bool buzzerBackendMicRecordBegin(uint32_t) { return false; }
bool buzzerBackendMicRecordPoll() { return false; }
bool buzzerBackendMicRecordStop() { return false; }
bool buzzerBackendMicHasRecording() { return false; }
bool buzzerBackendMicPlaybackBegin() { return false; }
bool buzzerBackendMicPlaybackPoll() { return false; }
void buzzerBackendMicPlaybackStop() {}
#endif

'''


def apply(repo: Path) -> None:
    header_path = repo / "src/buzzer_backend.h"
    source_path = repo / "src/buzzer_backend_es8311.cpp"
    header = load(header_path)
    source = load(source_path)

    if "buzzerBackendMicRecordBegin" not in header:
        header = once(header, "int buzzerBackendMicLevel(uint16_t sampleMs);\n", CAPTURE_DECLS,
                      "microphone capture API declarations")
        header_path.write_text(header, encoding="utf-8")

    if "#include <esp_heap_caps.h>" not in source:
        source = once(source, "#include <math.h>\n",
                      "#include <math.h>\n#include <esp_heap_caps.h>\n#include <string.h>\n",
                      "capture dependencies")

    if "gOs12RecordingData" not in source:
        source = once(source, "volatile TaskHandle_t gAudioTask = nullptr;\n",
                      "volatile TaskHandle_t gAudioTask = nullptr;\n" + CAPTURE_STATE + "\n",
                      "capture state")

    playback_loop = r'''    if (gOs12PlaybackActive && gOs12RecordingData && gOs12PlaybackPosition < gOs12RecordingBytes) {
      const size_t remaining = gOs12RecordingBytes - gOs12PlaybackPosition;
      const size_t copyBytes = remaining < sizeof(chunk) ? remaining : sizeof(chunk);
      memset(chunk, 0, sizeof(chunk));
      memcpy(chunk, gOs12RecordingData + gOs12PlaybackPosition, copyBytes);
      gOs12PlaybackPosition += copyBytes;
      if (gOs12PlaybackPosition >= gOs12RecordingBytes) gOs12PlaybackActive = false;
    } else {
      fillChunk(chunk);
    }
    size_t written = 0;'''
    if "gOs12PlaybackPosition < gOs12RecordingBytes" not in source:
        source = once(source, "    fillChunk(chunk);\n    size_t written = 0;", playback_loop,
                      "audio task recording playback")

    if "bool buzzerBackendMicRecordBegin(uint32_t maxDurationMs)" not in source:
        marker = "#endif // BOARD_HAS_ES8311_AUDIO"
        if source.count(marker) != 1:
            raise PatchError("ES8311 backend endif missing/non-unique")
        source = source.replace(marker, CAPTURE_API + marker, 1)

    source_path.write_text(source, encoding="utf-8")

    final_h = load(header_path)
    final_cpp = load(source_path)
    for needle in (
        "buzzerBackendMicRecordBegin", "buzzerBackendMicRecordPoll", "buzzerBackendMicRecordStop",
        "buzzerBackendMicHasRecording", "buzzerBackendMicPlaybackBegin",
        "buzzerBackendMicPlaybackPoll", "buzzerBackendMicPlaybackStop",
    ):
        if needle not in final_h or needle not in final_cpp:
            raise PatchError(f"bounded capture contract missing {needle}")
    for needle in (
        "MALLOC_CAP_SPIRAM", "kOs12RecordMaxMs = 5000U", "kOs12CaptureBurstsPerPoll = 2U",
        "captureScratch", "memcpy(gOs12RecordingData + used, captureScratch, bytesRead)",
        "gOs12PlaybackPosition < gOs12RecordingBytes",
    ):
        if needle not in final_cpp:
            raise PatchError(f"bounded capture implementation missing {needle}")
    for forbidden in (
        "gOs12CapturePauseRequested", "gOs12CaptureTxPaused", "os12PauseAudioTxForCapture",
        "vTaskDelete(task)",
    ):
        if forbidden in final_cpp:
            raise PatchError(f"capture retained unsafe task-handoff marker {forbidden}")

    print("Workshop OS 12 bounded microphone capture/playback installed")


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
