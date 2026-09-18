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
static const char kDemoVideoSource[] = "demo-video";
static const uint32_t kVideoFrameIntervalMs = 200U;  // 5 fps diagnostic ceiling; preserve touch/main-loop headroom.
static const float kBambuCameraWidth = 1280.0f;
static const float kBambuCameraHeight = 720.0f;
}

Ws350MediaBackend::Ws350MediaBackend()
    : requestedVolume_(70), muted_(false), requestedRecordMs_(0),
      recordingRequested_(false), recordingPlaybackRequested_(false),
      videoRequested_(false), videoPaused_(false), videoSource_(VideoSource::None),
      videoLastFrameId_(0), videoLastRenderAtMs_(0), videoDiagnostics_() {}

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
  // Video is a WS350 media capability, not a printer capability. Individual
  // sources (printer camera, network stream, local demo) perform their own
  // availability checks when selected.
  caps.videoDecoderAvailable = caps.psramAvailable;
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
  if (!source || !psramFound()) return false;

  VideoSource next = VideoSource::None;
  if (std::strcmp(source, kDemoVideoSource) == 0) {
    next = VideoSource::Demo;
  } else if (std::strcmp(source, kPrinterCameraSource) == 0) {
    if (!cameraCanStreamDisplayedPrinter()) return false;
    cameraBegin();
    if (!cameraActive()) return false;
    next = VideoSource::PrinterCamera;
  } else {
    return false;
  }

  videoRequested_ = true;
  videoPaused_ = false;
  videoSource_ = next;
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

void Ws350MediaBackend::renderDemoFrame(uint32_t nowMs) {
#if defined(BOARD_IS_WS350) && defined(BOARD_HAS_PSRAM)
  if (!videoRequested_ || videoPaused_ || videoSource_ != VideoSource::Demo) return;
  if (videoLastRenderAtMs_ != 0 && nowMs - videoLastRenderAtMs_ < kVideoFrameIntervalMs) return;

  const int16_t controlBarH = 50;
  const int16_t viewportH = tft.height() > controlBarH ? tft.height() - controlBarH : tft.height();
  const int16_t W = tft.width();
  const uint32_t frame = videoLastFrameId_ + 1U;
  const int16_t motionWidth = W > 76 ? W - 76 : 1;
  const int16_t motionHeight = viewportH > 130 ? viewportH - 130 : 1;
  const int16_t x = static_cast<int16_t>((frame * 11U) % motionWidth);
  const int16_t y = static_cast<int16_t>(54 + ((frame * 7U) % motionHeight));

  // The first frame establishes the static scene. Subsequent frames update
  // only the previous/current sprite and the two-pixel progress strip. This
  // avoids repainting ~130k pixels every frame on the 40 MHz SPI panel and
  // leaves materially more CPU/bus headroom for touch and printer telemetry.
  if (videoLastFrameId_ == 0U) {
    tft.fillRect(0, 0, W, viewportH, TFT_BLACK);
    tft.fillRoundRect(12, 12, W - 24, 34, 10, TFT_DARKGREY);
    tft.setTextColor(TFT_WHITE, TFT_DARKGREY);
    tft.setTextDatum(MC_DATUM);
    tft.drawString("Workshop OS Video Demo", W / 2, 29);
    tft.drawRect(10, viewportH - 18, W - 20, 6, TFT_DARKGREY);
  } else {
    const uint32_t previousFrame = frame - 1U;
    const int16_t previousX = static_cast<int16_t>((previousFrame * 11U) % motionWidth);
    const int16_t previousY = static_cast<int16_t>(54 + ((previousFrame * 7U) % motionHeight));
    tft.fillRect(previousX, previousY, 56, 56, TFT_BLACK);
  }

  tft.fillCircle(x + 28, y + 28, 28, TFT_CYAN);
  tft.fillRect(x + 18, y + 18, 20, 20, TFT_BLACK);
  tft.fillRect(12, viewportH - 16, W - 24, 2, TFT_BLACK);
  const int16_t progress = static_cast<int16_t>((frame * 5U) % (W > 24 ? W - 24 : 1));
  tft.fillRect(12, viewportH - 16, progress, 2, TFT_GREEN);

  markFrameDirty();
  videoLastFrameId_ = frame;
  videoLastRenderAtMs_ = nowMs;
  ++videoDiagnostics_.polls;
  ++videoDiagnostics_.frameObservations;
  ++videoDiagnostics_.framesRendered;
  yield();  // Cooperative handoff: demo rendering must not starve touch/network tasks.
  videoDiagnostics_.lastFrameId = frame;
  videoDiagnostics_.lastFrameBytes = 0;
  videoDiagnostics_.lastFrameAtMs = nowMs;
#else
  (void)nowMs;
#endif
}

void Ws350MediaBackend::renderLatestCameraFrame(uint32_t nowMs) {
#if defined(BOARD_IS_WS350) && defined(BOARD_HAS_PSRAM)
  if (!videoRequested_ || videoPaused_ || videoSource_ != VideoSource::PrinterCamera) return;
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
  if (videoRequested_ && videoSource_ == VideoSource::PrinterCamera) cameraStop();
  recordingRequested_ = false;
  recordingPlaybackRequested_ = false;
  requestedRecordMs_ = 0;
  videoRequested_ = false;
  videoPaused_ = false;
  videoSource_ = VideoSource::None;
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
    if (videoSource_ == VideoSource::PrinterCamera) {
      cameraService();
      if (!cameraActive()) {
        videoRequested_ = false;
        videoPaused_ = false;
        videoSource_ = VideoSource::None;
      } else {
        renderLatestCameraFrame(millis());
      }
    } else if (videoSource_ == VideoSource::Demo) {
      renderDemoFrame(millis());
    }
  }
#endif
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
