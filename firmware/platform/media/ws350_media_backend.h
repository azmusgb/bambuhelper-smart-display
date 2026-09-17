#pragma once

#include "media_service.h"

namespace workshop {
namespace media {

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

 private:
  uint8_t requestedVolume_;
  bool muted_;
  uint32_t requestedRecordMs_;
  bool recordingRequested_;
  bool recordingPlaybackRequested_;
  bool videoRequested_;
  bool videoPaused_;
};

}  // namespace media
}  // namespace workshop
