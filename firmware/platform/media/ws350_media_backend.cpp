#include "ws350_media_backend.h"

#include <Arduino.h>
#include "buzzer_backend.h"

#if defined(ESP32)
#include <esp_heap_caps.h>
#endif

namespace workshop {
namespace media {

Ws350MediaBackend::Ws350MediaBackend()
    : requestedVolume_(70), muted_(false), requestedRecordMs_(0),
      recordingRequested_(false), recordingPlaybackRequested_(false),
      videoRequested_(false), videoPaused_(false) {}

Capabilities Ws350MediaBackend::probe() {
  Capabilities caps;
#if defined(BOARD_HAS_ES8311_AUDIO)
  caps.speakerAvailable = true;
#endif
#if defined(BOARD_HAS_MICROPHONE)
  caps.microphoneAvailable = true;
#endif
#if defined(BOARD_HAS_PSRAM)
  caps.psramAvailable = psramFound();
  if (caps.psramAvailable) {
#if defined(ESP32)
    caps.psramFreeBytes = heap_caps_get_free_size(MALLOC_CAP_SPIRAM);
#endif
  }
#endif
  // Video remains unavailable until a bounded MJPEG decoder is installed and
  // validated on the WS350. PSRAM alone is not evidence of decoder capability.
  caps.videoDecoderAvailable = false;
  return caps;
}

bool Ws350MediaBackend::setSpeakerVolume(uint8_t percent) {
#if defined(BOARD_HAS_ES8311_AUDIO)
  if (percent > 100U) percent = 100U;
  requestedVolume_ = percent;
  buzzerBackendSetVolume(muted_ ? 0U : requestedVolume_);
  return true;
#else
  (void)percent;
  return false;
#endif
}

bool Ws350MediaBackend::setSpeakerMuted(bool muted) {
#if defined(BOARD_HAS_ES8311_AUDIO)
  muted_ = muted;
  buzzerBackendSetVolume(muted_ ? 0U : requestedVolume_);
  return true;
#else
  (void)muted;
  return false;
#endif
}

bool Ws350MediaBackend::playDiagnosticTone() {
#if defined(BOARD_HAS_ES8311_AUDIO)
  // Non-blocking: existing ES8311 audio task owns DMA streaming. MediaService
  // stops this test on its bounded deadline.
  buzzerBackendApplyStep(1047U);
  return true;
#else
  return false;
#endif
}

bool Ws350MediaBackend::sampleMicrophoneLevel(uint8_t& percent) {
#if defined(BOARD_HAS_MICROPHONE)
  const int level = buzzerBackendMicLevel(250U);
  if (level < 0) return false;
  percent = static_cast<uint8_t>(level > 100 ? 100 : level);
  return true;
#else
  (void)percent;
  return false;
#endif
}

bool Ws350MediaBackend::beginRecording(uint32_t maxDurationMs) {
#if defined(BOARD_HAS_MICROPHONE)
  requestedRecordMs_ = maxDurationMs;
  recordingPlaybackRequested_ = false;
  recordingRequested_ = buzzerBackendMicRecordBegin(maxDurationMs);
  return recordingRequested_;
#else
  (void)maxDurationMs;
  requestedRecordMs_ = 0;
  recordingRequested_ = false;
  return false;
#endif
}

bool Ws350MediaBackend::stopRecording() {
#if defined(BOARD_HAS_MICROPHONE)
  const bool ok = buzzerBackendMicRecordStop();
  recordingRequested_ = false;
  requestedRecordMs_ = 0;
  return ok;
#else
  recordingRequested_ = false;
  requestedRecordMs_ = 0;
  return false;
#endif
}

bool Ws350MediaBackend::playRecording() {
#if defined(BOARD_HAS_MICROPHONE) && defined(BOARD_HAS_ES8311_AUDIO)
  if (!buzzerBackendMicHasRecording()) return false;
  recordingRequested_ = false;
  recordingPlaybackRequested_ = buzzerBackendMicPlaybackBegin();
  return recordingPlaybackRequested_;
#else
  return false;
#endif
}

bool Ws350MediaBackend::beginMjpeg(const char* source) {
  (void)source;
  videoRequested_ = false;
  videoPaused_ = false;
  return false;
}

bool Ws350MediaBackend::pauseVideo(bool paused) {
  (void)paused;
  return false;
}

bool Ws350MediaBackend::stopMedia() {
#if defined(BOARD_HAS_MICROPHONE)
  if (recordingRequested_) buzzerBackendMicRecordStop();
  buzzerBackendMicPlaybackStop();
#endif
#if defined(BOARD_HAS_ES8311_AUDIO)
  buzzerBackendStop();
#endif
  recordingRequested_ = false;
  recordingPlaybackRequested_ = false;
  requestedRecordMs_ = 0;
  videoRequested_ = false;
  videoPaused_ = false;
  return true;
}

void Ws350MediaBackend::poll() {
#if defined(BOARD_HAS_MICROPHONE)
  if (recordingRequested_) {
    recordingRequested_ = buzzerBackendMicRecordPoll();
    if (!recordingRequested_) requestedRecordMs_ = 0;
  }
  if (recordingPlaybackRequested_) {
    recordingPlaybackRequested_ = buzzerBackendMicPlaybackPoll();
  }
#endif
  // All low-level capture work is burst-bounded. Printer telemetry, touch,
  // network, OTA and recovery remain serviced by the main loop between polls.
}

bool Ws350MediaBackend::isSessionActive() const {
  return recordingRequested_ || recordingPlaybackRequested_ || videoRequested_;
}

bool Ws350MediaBackend::hasRecording() const {
#if defined(BOARD_HAS_MICROPHONE)
  return buzzerBackendMicHasRecording();
#else
  return false;
#endif
}

}  // namespace media
}  // namespace workshop
