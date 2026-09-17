#pragma once

#include <stddef.h>
#include <stdint.h>

namespace workshop::media {

enum class SessionState : uint8_t {
  Idle = 0,
  Starting,
  PlayingAudio,
  Recording,
  PlayingRecording,
  PlayingVideo,
  Paused,
  Stopping,
  Fault,
};

enum class MediaError : uint8_t {
  None = 0,
  Unsupported,
  HardwareUnavailable,
  Busy,
  InvalidArgument,
  OutOfMemory,
  IoFailure,
  DecoderFailure,
  Timeout,
};

struct Capabilities {
  bool speakerAvailable = false;
  bool microphoneAvailable = false;
  bool videoDecoderAvailable = false;
  bool psramAvailable = false;
  size_t psramFreeBytes = 0;
};

struct RuntimeState {
  SessionState session = SessionState::Idle;
  MediaError lastError = MediaError::None;
  uint8_t volumePercent = 70;
  bool muted = false;
  uint8_t microphoneLevelPercent = 0;
  uint32_t audioUnderruns = 0;
  uint32_t droppedVideoFrames = 0;
  uint32_t sessionStartedAtMs = 0;
};

struct Snapshot {
  Capabilities capabilities{};
  RuntimeState runtime{};
};

class HardwareBackend {
 public:
  virtual ~HardwareBackend() = default;
  virtual Capabilities probe() = 0;
  virtual bool setSpeakerVolume(uint8_t percent) = 0;
  virtual bool setSpeakerMuted(bool muted) = 0;
  virtual bool playDiagnosticTone() = 0;
  virtual bool sampleMicrophoneLevel(uint8_t& percent) = 0;
  virtual bool beginRecording(uint32_t maxDurationMs) = 0;
  virtual bool stopRecording() = 0;
  virtual bool playRecording() = 0;
  virtual bool beginMjpeg(const char* source) = 0;
  virtual bool pauseVideo(bool paused) = 0;
  virtual bool stopMedia() = 0;
  virtual void poll() = 0;
};

class MediaService {
 public:
  void begin(HardwareBackend* backend, uint32_t nowMs = 0);
  void poll(uint32_t nowMs);

  const Snapshot& snapshot() const { return snapshot_; }

  bool setVolume(uint8_t percent);
  bool setMuted(bool muted);
  bool testSpeaker(uint32_t nowMs);
  bool sampleMicrophone(uint32_t nowMs);
  bool startRecording(uint32_t maxDurationMs, uint32_t nowMs);
  bool stopRecording(uint32_t nowMs);
  bool playRecording(uint32_t nowMs);
  bool playMjpeg(const char* source, uint32_t nowMs);
  bool pauseVideo(bool paused, uint32_t nowMs);
  bool stop(uint32_t nowMs);

  void noteAudioUnderrun();
  void noteDroppedVideoFrame();
  void fail(MediaError error);

 private:
  bool requireIdle();
  bool requireCapability(bool available);
  void transition(SessionState next, uint32_t nowMs);
  void clearError();

  HardwareBackend* backend_ = nullptr;
  Snapshot snapshot_{};
};

const char* sessionStateName(SessionState state);
const char* mediaErrorName(MediaError error);

}  // namespace workshop::media
