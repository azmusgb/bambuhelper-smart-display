#include <cassert>
#include <cstring>
#include "../firmware/platform/media/media_service.h"

using namespace workshop::media;

class FakeBackend : public HardwareBackend {
 public:
  FakeBackend() : failNext(false), muted(false), volume(0) {
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
  bool stopMedia() override { return ok(); }
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

  assert(media.sampleMicrophone(2));
  assert(media.snapshot().runtime.microphoneLevelPercent == 42);

  assert(media.startRecording(5000, 3));
  assert(media.snapshot().runtime.session == SessionState::Recording);
  assert(!media.playMjpeg("clip.mjpg", 4));
  assert(media.snapshot().runtime.lastError == MediaError::Busy);
  assert(media.stopRecording(5));
  assert(media.playRecording(6));
  assert(media.stop(7));

  assert(!media.playMjpeg(0, 8));
  assert(media.snapshot().runtime.lastError == MediaError::InvalidArgument);
  assert(media.playMjpeg("clip.mjpg", 9));
  assert(media.pauseVideo(true, 10));
  assert(media.snapshot().runtime.session == SessionState::Paused);
  media.noteDroppedVideoFrame();
  media.noteAudioUnderrun();
  assert(media.snapshot().runtime.droppedVideoFrames == 1);
  assert(media.snapshot().runtime.audioUnderruns == 1);
  assert(media.pauseVideo(false, 11));
  assert(media.stop(12));

  FakeBackend noPsram;
  noPsram.caps.psramAvailable = false;
  MediaService constrained;
  constrained.begin(&noPsram, 13);
  assert(!constrained.startRecording(1000, 14));
  assert(constrained.snapshot().runtime.lastError == MediaError::OutOfMemory);
  assert(!constrained.playMjpeg("clip.mjpg", 15));
  assert(constrained.snapshot().runtime.lastError == MediaError::OutOfMemory);

  FakeBackend broken;
  MediaService faulted;
  faulted.begin(&broken, 16);
  broken.failNext = true;
  assert(!faulted.testSpeaker(17));
  assert(faulted.snapshot().runtime.session == SessionState::Fault);
  assert(faulted.snapshot().runtime.lastError == MediaError::IoFailure);

  assert(std::strcmp(sessionStateName(SessionState::PlayingVideo), "PlayingVideo") == 0);
  assert(std::strcmp(mediaErrorName(MediaError::Busy), "Busy") == 0);
  return 0;
}
