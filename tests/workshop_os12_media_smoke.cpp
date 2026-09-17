#include <cassert>
#include <cstring>
#include "../firmware/platform/media/media_service.h"

using namespace workshop::media;

class FakeBackend : public HardwareBackend {
 public:
  FakeBackend() : failNext(false), muted(false), volume(0), stopCount(0) {
    caps.speakerAvailable = true;
    caps.microphoneAvailable = true;
    caps.videoDecoderAvailable = true;
    caps.psramAvailable = true;
    caps.psramFreeBytes = 2U * 1024U * 1024U;
  }

  Capabilities caps;
  bool failNext;
  bool muted;
  uint8_t volume;
  unsigned stopCount;

  Capabilities probe() override { return caps; }
  bool ok() { if (failNext) { failNext = false; return false; } return true; }
  bool setSpeakerVolume(uint8_t p) override { volume = p; return ok(); }
  bool setSpeakerMuted(bool m) override { muted = m; return ok(); }
  bool playDiagnosticTone() override { return ok(); }
  bool sampleMicrophoneLevel(uint8_t& p) override { p = 42; return ok(); }
  bool beginRecording(uint32_t) override { return ok(); }
  bool stopRecording() override { return ok(); }
  bool playRecording() override { return ok(); }
  bool beginMjpeg(const char*) override { return ok(); }
  bool pauseVideo(bool) override { return ok(); }
  bool stopMedia() override { ++stopCount; return ok(); }
  void poll() override {}
};

int main() {
  FakeBackend hw;
  MediaService media;
  media.begin(&hw, 1);
  assert(media.snapshot().runtime.session == SessionState::Idle);
  assert(media.snapshot().capabilities.speakerAvailable);
  assert(media.snapshot().capabilities.microphoneAvailable);
  assert(media.snapshot().capabilities.videoDecoderAvailable);

  assert(media.setVolume(90));
  assert(hw.volume == 90);
  assert(media.setMuted(true));
  assert(hw.muted);

  assert(media.testSpeaker(100));
  assert(media.snapshot().runtime.session == SessionState::PlayingAudio);
  media.poll(279);
  assert(media.snapshot().runtime.session == SessionState::PlayingAudio);
  media.poll(280);
  assert(media.snapshot().runtime.session == SessionState::Idle);
  assert(hw.stopCount == 1);

  assert(media.sampleMicrophone(300));
  assert(media.snapshot().runtime.microphoneLevelPercent == 42);

  assert(media.startRecording(5000, 301));
  assert(media.snapshot().runtime.session == SessionState::Recording);
  assert(!media.playMjpeg("clip.mjpg", 302));
  assert(media.snapshot().runtime.lastError == MediaError::Busy);
  assert(media.stopRecording(303));
  assert(media.playRecording(304));
  assert(media.stop(305));

  assert(!media.playMjpeg(0, 306));
  assert(media.snapshot().runtime.lastError == MediaError::InvalidArgument);
  assert(media.playMjpeg("clip.mjpg", 307));
  assert(media.pauseVideo(true, 308));
  assert(media.snapshot().runtime.session == SessionState::Paused);
  media.noteDroppedVideoFrame();
  media.noteAudioUnderrun();
  assert(media.snapshot().runtime.droppedVideoFrames == 1);
  assert(media.snapshot().runtime.audioUnderruns == 1);
  assert(media.pauseVideo(false, 309));
  assert(media.stop(310));

  FakeBackend noPsram;
  noPsram.caps.psramAvailable = false;
  MediaService constrained;
  constrained.begin(&noPsram, 311);
  assert(!constrained.startRecording(1000, 312));
  assert(constrained.snapshot().runtime.lastError == MediaError::OutOfMemory);
  assert(!constrained.playMjpeg("clip.mjpg", 313));
  assert(constrained.snapshot().runtime.lastError == MediaError::OutOfMemory);

  FakeBackend broken;
  MediaService faulted;
  faulted.begin(&broken, 314);
  broken.failNext = true;
  assert(!faulted.testSpeaker(315));
  assert(faulted.snapshot().runtime.session == SessionState::Fault);
  assert(faulted.snapshot().runtime.lastError == MediaError::IoFailure);

  assert(std::strcmp(sessionStateName(SessionState::PlayingVideo), "PlayingVideo") == 0);
  assert(std::strcmp(mediaErrorName(MediaError::Busy), "Busy") == 0);
  return 0;
}
