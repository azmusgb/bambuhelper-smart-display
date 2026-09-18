#include "ws350_media_backend.h"

#include <Arduino.h>
#include <cstring>
#include "buzzer_backend.h"
#include "camera_client.h"
#include "display_ui.h"

#if defined(ESP32)
#include <esp_heap_caps.h>
#endif

namespace workshop {
namespace media {

namespace {
static const char kPrinterCameraSource[] = "printer-camera";
static const uint32_t kVideoFrameIntervalMs = 125U;  // 8 fps ceiling.
static const float kBambuCameraWidth = 1280.0f;
static const float kBambuCameraHeight = 720.0f;
}

Ws350MediaBackend::Ws350MediaBackend()
    : requestedVolume_(70), muted_(false), requestedRecordMs_(0),
      recordingRequested_(false), recordingPlaybackRequested_(false),
      videoRequested_(false), videoPaused_(false), videoLastFrameId_(0),
      videoLastRenderAtMs_(0), videoDiagnostics_() {}

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
#if defined(BOARD_IS_WS350) && defined(BOARD_HAS_PSRAM)
  // LovyanGFX provides the JPEG decoder, but a usable video feature also
  // requires the displayed printer to expose the existing bounded local JPEG
  // camera transport. Do not advertise video merely because the LCD can decode
  // JPEGs; unsupported printer camera transports must remain explicitly
  // unavailable rather than failing later as DecoderFailure.
  caps.videoDecoderAvailable = caps.psramAvailable && cameraCanStreamDisplayedPrinter();
#endif
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
#if defined(BOARD_IS_WS350) && defined(BOARD_HAS_PSRAM)
  if (!source || std::strcmp(source, kPrinterCameraSource) != 0) return false;
  if (!psramFound() || !cameraCanStreamDisplayedPrinter()) return false;

  // The existing camera client remains the sole network authority. It already
  // bounds input to two 200 KB PSRAM JPEG buffers and publishes only complete
  // SOI..EOI frames. MediaService owns only playback lifecycle and pacing.
  cameraBegin();
  if (!cameraActive()) return false;
  videoRequested_ = true;
  videoPaused_ = false;
  videoLastFrameId_ = 0;
  videoLastRenderAtMs_ = 0;
  videoDiagnostics_ = VideoDiagnostics();
  return true;
#else
  (void)source;
  return false;
#endif
}

bool Ws350MediaBackend::pauseVideo(bool paused) {
  if (!videoRequested_) return false;
  videoPaused_ = paused;
  return true;
}

void Ws350MediaBackend::renderLatestCameraFrame(uint32_t nowMs) {
#if defined(BOARD_IS_WS350) && defined(BOARD_HAS_PSRAM)
  if (!videoRequested_ || videoPaused_) return;
  if (videoLastRenderAtMs_ != 0 && nowMs - videoLastRenderAtMs_ < kVideoFrameIntervalMs) return;

  ++videoDiagnostics_.polls;
  const uint8_t* frame = 0;
  size_t frameLen = 0;
  uint32_t frameId = 0;
  if (!cameraGetLatestFrame(&frame, &frameLen, &frameId) || !frame || frameLen == 0) {
    ++videoDiagnostics_.noFramePolls;
    return;
  }
  videoDiagnostics_.lastFrameId = frameId;
  videoDiagnostics_.lastFrameBytes = static_cast<uint32_t>(frameLen);
  videoDiagnostics_.lastFrameAtMs = nowMs;
  if (frameId == videoLastFrameId_) return;
  ++videoDiagnostics_.frameObservations;

  // Reserve the bottom 50 px for the dedicated viewer controls. On the
  // 480x320 WS350 this yields an exact 480x270 16:9 camera viewport.
  const int16_t controlBarH = 50;
  const int16_t viewportH = tft.height() > controlBarH ? tft.height() - controlBarH : tft.height();
  const float sw = static_cast<float>(tft.width());
  const float sh = static_cast<float>(viewportH);
  float scale = sw / kBambuCameraWidth;
  const float heightScale = sh / kBambuCameraHeight;
  if (heightScale < scale) scale = heightScale;
  if (scale <= 0.0f) return;

  const int drawW = static_cast<int>(kBambuCameraWidth * scale);
  const int drawH = static_cast<int>(kBambuCameraHeight * scale);
  const int x = (tft.width() - drawW) / 2;
  const int y = (viewportH - drawH) / 2;
  tft.fillRect(0, 0, tft.width(), viewportH, TFT_BLACK);
  tft.drawJpg(frame, static_cast<uint32_t>(frameLen), x, y, 0, 0, 0, 0, scale, scale);
  markFrameDirty();
  videoLastFrameId_ = frameId;
  videoLastRenderAtMs_ = nowMs;
  ++videoDiagnostics_.framesRendered;
#else
  (void)nowMs;
#endif
}

bool Ws350MediaBackend::stopMedia() {
#if defined(BOARD_HAS_MICROPHONE)
  if (recordingRequested_) buzzerBackendMicRecordStop();
  buzzerBackendMicPlaybackStop();
#endif
#if defined(BOARD_HAS_ES8311_AUDIO)
  buzzerBackendStop();
#endif
  if (videoRequested_) cameraStop();
  recordingRequested_ = false;
  recordingPlaybackRequested_ = false;
  requestedRecordMs_ = 0;
  videoRequested_ = false;
  videoPaused_ = false;
  videoLastFrameId_ = 0;
  videoLastRenderAtMs_ = 0;
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
#if defined(BOARD_IS_WS350) && defined(BOARD_HAS_PSRAM)
  if (videoRequested_) {
    cameraService();
    if (!cameraActive()) {
      videoRequested_ = false;
      videoPaused_ = false;
    } else {
      renderLatestCameraFrame(millis());
    }
  }
#endif
  // All low-level capture/video work is bounded. Printer telemetry, touch,
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
