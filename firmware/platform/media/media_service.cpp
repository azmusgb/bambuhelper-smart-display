#include "media_service.h"

namespace workshop::media {

namespace {
uint8_t clampPercent(uint8_t value) { return value > 100 ? 100 : value; }
}

void MediaService::begin(HardwareBackend* backend, uint32_t nowMs) {
  backend_ = backend;
  snapshot_ = Snapshot{};
  snapshot_.runtime.volumePercent = 70;
  if (!backend_) {
    fail(MediaError::HardwareUnavailable);
    return;
  }
  snapshot_.capabilities = backend_->probe();
  transition(SessionState::Idle, nowMs);
}

void MediaService::poll(uint32_t) {
  if (backend_) backend_->poll();
}

bool MediaService::requireIdle() {
  if (snapshot_.runtime.session == SessionState::Idle) return true;
  snapshot_.runtime.lastError = MediaError::Busy;
  return false;
}

bool MediaService::requireCapability(bool available) {
  if (available && backend_) return true;
  snapshot_.runtime.lastError = MediaError::HardwareUnavailable;
  return false;
}

void MediaService::transition(SessionState next, uint32_t nowMs) {
  snapshot_.runtime.session = next;
  snapshot_.runtime.sessionStartedAtMs = nowMs;
}

void MediaService::clearError() { snapshot_.runtime.lastError = MediaError::None; }

bool MediaService::setVolume(uint8_t percent) {
  if (!requireCapability(snapshot_.capabilities.speakerAvailable)) return false;
  percent = clampPercent(percent);
  if (!backend_->setSpeakerVolume(percent)) {
    fail(MediaError::IoFailure);
    return false;
  }
  snapshot_.runtime.volumePercent = percent;
  clearError();
  return true;
}

bool MediaService::setMuted(bool muted) {
  if (!requireCapability(snapshot_.capabilities.speakerAvailable)) return false;
  if (!backend_->setSpeakerMuted(muted)) {
    fail(MediaError::IoFailure);
    return false;
  }
  snapshot_.runtime.muted = muted;
  clearError();
  return true;
}

bool MediaService::testSpeaker(uint32_t nowMs) {
  if (!requireIdle() || !requireCapability(snapshot_.capabilities.speakerAvailable)) return false;
  transition(SessionState::Starting, nowMs);
  if (!backend_->playDiagnosticTone()) {
    fail(MediaError::IoFailure);
    return false;
  }
  transition(SessionState::PlayingAudio, nowMs);
  clearError();
  return true;
}

bool MediaService::sampleMicrophone(uint32_t nowMs) {
  if (!requireIdle() || !requireCapability(snapshot_.capabilities.microphoneAvailable)) return false;
  uint8_t level = 0;
  transition(SessionState::Starting, nowMs);
  if (!backend_->sampleMicrophoneLevel(level)) {
    fail(MediaError::IoFailure);
    return false;
  }
  snapshot_.runtime.microphoneLevelPercent = clampPercent(level);
  transition(SessionState::Idle, nowMs);
  clearError();
  return true;
}

bool MediaService::startRecording(uint32_t maxDurationMs, uint32_t nowMs) {
  if (maxDurationMs == 0) {
    snapshot_.runtime.lastError = MediaError::InvalidArgument;
    return false;
  }
  if (!requireIdle() || !requireCapability(snapshot_.capabilities.microphoneAvailable)) return false;
  if (!snapshot_.capabilities.psramAvailable) {
    snapshot_.runtime.lastError = MediaError::OutOfMemory;
    return false;
  }
  transition(SessionState::Starting, nowMs);
  if (!backend_->beginRecording(maxDurationMs)) {
    fail(MediaError::IoFailure);
    return false;
  }
  transition(SessionState::Recording, nowMs);
  clearError();
  return true;
}

bool MediaService::stopRecording(uint32_t nowMs) {
  if (!backend_ || snapshot_.runtime.session != SessionState::Recording) {
    snapshot_.runtime.lastError = MediaError::InvalidArgument;
    return false;
  }
  transition(SessionState::Stopping, nowMs);
  if (!backend_->stopRecording()) {
    fail(MediaError::IoFailure);
    return false;
  }
  transition(SessionState::Idle, nowMs);
  clearError();
  return true;
}

bool MediaService::playRecording(uint32_t nowMs) {
  if (!requireIdle() || !requireCapability(snapshot_.capabilities.speakerAvailable)) return false;
  transition(SessionState::Starting, nowMs);
  if (!backend_->playRecording()) {
    fail(MediaError::IoFailure);
    return false;
  }
  transition(SessionState::PlayingRecording, nowMs);
  clearError();
  return true;
}

bool MediaService::playMjpeg(const char* source, uint32_t nowMs) {
  if (!source || !*source) {
    snapshot_.runtime.lastError = MediaError::InvalidArgument;
    return false;
  }
  if (!requireIdle() || !requireCapability(snapshot_.capabilities.videoDecoderAvailable)) return false;
  if (!snapshot_.capabilities.psramAvailable) {
    snapshot_.runtime.lastError = MediaError::OutOfMemory;
    return false;
  }
  transition(SessionState::Starting, nowMs);
  if (!backend_->beginMjpeg(source)) {
    fail(MediaError::DecoderFailure);
    return false;
  }
  transition(SessionState::PlayingVideo, nowMs);
  clearError();
  return true;
}

bool MediaService::pauseVideo(bool paused, uint32_t nowMs) {
  const auto current = snapshot_.runtime.session;
  if (!backend_ || (current != SessionState::PlayingVideo && current != SessionState::Paused)) {
    snapshot_.runtime.lastError = MediaError::InvalidArgument;
    return false;
  }
  if (!backend_->pauseVideo(paused)) {
    fail(MediaError::IoFailure);
    return false;
  }
  transition(paused ? SessionState::Paused : SessionState::PlayingVideo, nowMs);
  clearError();
  return true;
}

bool MediaService::stop(uint32_t nowMs) {
  if (!backend_) {
    fail(MediaError::HardwareUnavailable);
    return false;
  }
  if (snapshot_.runtime.session == SessionState::Idle) return true;
  transition(SessionState::Stopping, nowMs);
  if (!backend_->stopMedia()) {
    fail(MediaError::IoFailure);
    return false;
  }
  transition(SessionState::Idle, nowMs);
  clearError();
  return true;
}

void MediaService::noteAudioUnderrun() { ++snapshot_.runtime.audioUnderruns; }
void MediaService::noteDroppedVideoFrame() { ++snapshot_.runtime.droppedVideoFrames; }

void MediaService::fail(MediaError error) {
  snapshot_.runtime.lastError = error;
  snapshot_.runtime.session = SessionState::Fault;
}

const char* sessionStateName(SessionState state) {
  switch (state) {
    case SessionState::Idle: return "Idle";
    case SessionState::Starting: return "Starting";
    case SessionState::PlayingAudio: return "PlayingAudio";
    case SessionState::Recording: return "Recording";
    case SessionState::PlayingRecording: return "PlayingRecording";
    case SessionState::PlayingVideo: return "PlayingVideo";
    case SessionState::Paused: return "Paused";
    case SessionState::Stopping: return "Stopping";
    case SessionState::Fault: return "Fault";
  }
  return "Unknown";
}

const char* mediaErrorName(MediaError error) {
  switch (error) {
    case MediaError::None: return "None";
    case MediaError::Unsupported: return "Unsupported";
    case MediaError::HardwareUnavailable: return "HardwareUnavailable";
    case MediaError::Busy: return "Busy";
    case MediaError::InvalidArgument: return "InvalidArgument";
    case MediaError::OutOfMemory: return "OutOfMemory";
    case MediaError::IoFailure: return "IoFailure";
    case MediaError::DecoderFailure: return "DecoderFailure";
    case MediaError::Timeout: return "Timeout";
  }
  return "Unknown";
}

}  // namespace workshop::media
