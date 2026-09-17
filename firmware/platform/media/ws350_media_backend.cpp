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
      recordingRequested_(false), videoRequested_(false), videoPaused_(false) {}

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
  // Video is deliberately unavailable until the bounded MJPEG renderer is
  // installed. Never advertise a decoder merely because PSRAM exists.
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
  // Non-blocking: existing ES8311 audio task owns DMA streaming.
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
  // The legacy mic-echo routine performs capture and playback as one blocking
  // operation. OS12 intentionally refuses to expose that as a recording
  // session. Native bounded capture is added by the media-capture backend.
  requestedRecordMs_ = maxDurationMs;
  recordingRequested_ = false;
  return false;
}

bool Ws350MediaBackend::stopRecording() {
  requestedRecordMs_ = 0;
  recordingRequested_ = false;
  return false;
}

bool Ws350MediaBackend::playRecording() {
  return false;
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
#if defined(BOARD_HAS_ES8311_AUDIO)
  buzzerBackendStop();
#endif
  recordingRequested_ = false;
  requestedRecordMs_ = 0;
  videoRequested_ = false;
  videoPaused_ = false;
  return true;
}

void Ws350MediaBackend::poll() {
  // Audio DMA remains owned by the existing backend. This adapter must never
  // block printer telemetry, touch handling, OTA, or recovery processing.
}

}  // namespace media
}  // namespace workshop
