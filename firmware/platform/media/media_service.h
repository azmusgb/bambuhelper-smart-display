#pragma once

#include <stddef.h>
#include <stdint.h>

namespace workshop {
namespace media {

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
  Capabilities()
      : speakerAvailable(false), microphoneAvailable(false),
        videoDecoderAvailable(false), psramAvailable(false),
        psramFreeBytes(0) {}
  bool speakerAvailable;
  bool microphoneAvailable;
  bool videoDecoderAvailable;
  bool psramAvailable;
  size_t psramFreeBytes;
};

struct RuntimeState {
  RuntimeState()
      : session(SessionState::Idle), lastError(MediaError::None),
        volumePercent(70), muted(false), microphoneLevelPercent(0),
        audioUnderruns(0), droppedVideoFrames(0), sessionStartedAtMs(0) {}
  SessionState session;
  MediaError lastError;
  uint8_t volumePercent;
  bool muted;
  uint8_t microphoneLevelPercent;
  uint32_t audioUnderruns;
  uint32_t droppedVideoFrames;
  uint32_t sessionStartedAtMs;
};

struct Snapshot {
  Capabilities capabilities;
  RuntimeState runtime;
};

class HardwareBackend {
 public:
  virtual ~HardwareBackend() {}
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
  // True while an asynchronous recording/playback/video operation is still
  // owned by the backend. MediaService uses this only for sessions whose
  // lifetime is backend-driven; the speaker diagnostic has its own deadline.
  virtual bool isSessionActive() const = 0;
};

class MediaService {
 public:
  MediaService() : backend_(0), snapshot_(), speakerTestEndsAtMs_(0) {}

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

  HardwareBackend* backend_;
  Snapshot snapshot_;
  uint32_t speakerTestEndsAtMs_;
};

const char* sessionStateName(SessionState state);
const char* mediaErrorName(MediaError error);

}  // namespace media
}  // namespace workshop
