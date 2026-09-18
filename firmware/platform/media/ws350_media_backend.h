#pragma once

#include "media_service.h"

namespace workshop {
namespace media {

struct VideoDiagnostics {
  VideoDiagnostics()
      : polls(0), noFramePolls(0), frameObservations(0), framesRendered(0),
        lastFrameId(0), lastFrameBytes(0), lastFrameAtMs(0) {}
  uint32_t polls;
  uint32_t noFramePolls;
  uint32_t frameObservations;
  uint32_t framesRendered;
  uint32_t lastFrameId;
  uint32_t lastFrameBytes;
  uint32_t lastFrameAtMs;
};

class Ws350MediaBackend : public HardwareBackend {
 public:
  Ws350MediaBackend();

  Capabilities probe() override;
  bool setSpeakerVolume(uint8_t percent) override;
  bool setSpeakerMuted(bool muted) override;
  bool playDiagnosticTone() override;
  bool sampleMicrophoneLevel(uint8_t& percent) override;
  bool beginRecording(uint32_t maxDurationMs) override;
  bool stopRecording() override;
  bool playRecording() override;
  bool beginMjpeg(const char* source) override;
  bool pauseVideo(bool paused) override;
  bool stopMedia() override;
  void poll() override;
  bool isSessionActive() const override;
  bool hasRecording() const override;
  const VideoDiagnostics& videoDiagnostics() const { return videoDiagnostics_; }

 private:
  void renderLatestCameraFrame(uint32_t nowMs);

  uint8_t requestedVolume_;
  bool muted_;
  uint32_t requestedRecordMs_;
  bool recordingRequested_;
  bool recordingPlaybackRequested_;
  bool videoRequested_;
  bool videoPaused_;
  uint32_t videoLastFrameId_;
  uint32_t videoLastRenderAtMs_;
  VideoDiagnostics videoDiagnostics_;
};

}  // namespace media
}  // namespace workshop
