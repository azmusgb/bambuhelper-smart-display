#include <cassert>
#include <cstring>
#include "../firmware/platform/media/media_service.h"

using namespace workshop::media;

class FakeBackend : public HardwareBackend {
 public:
  FakeBackend()
      : failNext(false), muted(false), active(false), recording(false),
        volume(0), stopCount(0) {
    caps.speakerAvailable = true;
    caps.microphoneAvailable = true;
    caps.videoDecoderAvailable = true;
    caps.psramAvailable = true;
    caps.psramFreeBytes = 2U * 1024U * 1024U;
  }

  Capabilities caps;
  bool failNext;
  bool muted;
  bool active;
  bool recording;
  uint8_t volume;
  unsigned stopCount;

  Capabilities probe() override { return caps; }
  bool ok() { if (failNext) { failNext = false; return false; } return true; }
  bool setSpeakerVolume(uint8_t p) override { volume = p; return ok(); }
  bool setSpeakerMuted(bool m) override { muted = m; return ok(); }
  bool playDiagnosticTone() override { return ok(); }
  bool sampleMicrophoneLevel(uint8_t& p) override { p = 42; return ok(); }
  bool beginRecording(uint32_t) override { recording = false; active = ok(); return active; }
  bool stopRecording() override { active = false; recording = ok(); return recording; }
  bool playRecording() override { active = recording && ok(); return active; }
  bool beginMjpeg(const char*) override { active = ok(); return active; }
  bool pauseVideo(bool) override { return ok(); }
  bool stopMedia() override { ++stopCount; active = false; return ok(); }
  void poll() override {}
  bool isSessionActive() const override { return active; }
  bool hasRecording() const override { return recording; }
};

int main() {
  FakeBackend hw;
  MediaService media;
  media.begin(&hw, 1);
  assert(media.snapshot().runtime.session == SessionState::Idle);
  assert(media.snapshot().capabilities.speakerAvailable);
  assert(media.snapshot().capabilities.microphoneAvailable);
  assert(media.snapshot().capabilities.videoDecoderAvailable);
  assert(!media.snapshot().runtime.recordingAvailable);

  assert(media.setVolume(90));
  assert(hw.volume == 90);
  assert(media.setMuted(true));
  assert(hw.muted);

  assert(media.testSpeaker(100));
  assert(media.snapshot().runtime.session == SessionState::PlayingAudio);
  media.poll(1299);
  assert(media.snapshot().runtime.session == SessionState::PlayingAudio);
  media.poll(1300);
  assert(media.snapshot().runtime.session == SessionState::Idle);
  assert(hw.stopCount == 1);

  assert(media.sampleMicrophone(300));
  assert(media.snapshot().runtime.microphoneLevelPercent == 42);

  assert(media.startRecording(5000, 301));
  assert(media.snapshot().runtime.session == SessionState::Recording);
  assert(!media.playMjpeg("clip.mjpg", 302));
  assert(media.snapshot().runtime.lastError == MediaError::Busy);
  assert(media.stopRecording(303));
  assert(media.snapshot().runtime.recordingAvailable);

  assert(media.startRecording(5000, 304));
  hw.recording = true;
  hw.active = false;  // bounded backend completed its requested recording.
  media.poll(305);
  assert(media.snapshot().runtime.session == SessionState::Idle);
  assert(media.snapshot().runtime.recordingAvailable);

  assert(media.playRecording(306));
  assert(media.snapshot().runtime.session == SessionState::PlayingRecording);
  hw.active = false;  // DMA playback reached the captured byte count.
  media.poll(307);
  assert(media.snapshot().runtime.session == SessionState::Idle);
  assert(media.snapshot().runtime.recordingAvailable);

  assert(!media.playMjpeg(0, 308));
  assert(media.snapshot().runtime.lastError == MediaError::InvalidArgument);
  assert(media.playMjpeg("clip.mjpg", 309));
  assert(media.pauseVideo(true, 310));
  assert(media.snapshot().runtime.session == SessionState::Paused);
  media.noteDroppedVideoFrame();
  media.noteAudioUnderrun();
  assert(media.snapshot().runtime.droppedVideoFrames == 1);
  assert(media.snapshot().runtime.audioUnderruns == 1);
  assert(media.pauseVideo(false, 311));
  assert(media.stop(312));

  FakeBackend noPsram;
  noPsram.caps.psramAvailable = false;
  MediaService constrained;
  constrained.begin(&noPsram, 313);
  assert(!constrained.startRecording(1000, 314));
  assert(constrained.snapshot().runtime.lastError == MediaError::OutOfMemory);
  assert(!constrained.playMjpeg("clip.mjpg", 315));
  assert(constrained.snapshot().runtime.lastError == MediaError::OutOfMemory);

  FakeBackend broken;
  MediaService faulted;
  faulted.begin(&broken, 316);
  broken.failNext = true;
  assert(!faulted.testSpeaker(317));
  assert(faulted.snapshot().runtime.session == SessionState::Fault);
  assert(faulted.snapshot().runtime.lastError == MediaError::IoFailure);

  assert(std::strcmp(sessionStateName(SessionState::PlayingVideo), "PlayingVideo") == 0);
  assert(std::strcmp(mediaErrorName(MediaError::Busy), "Busy") == 0);
  return 0;
}
