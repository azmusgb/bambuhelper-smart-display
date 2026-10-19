#!/usr/bin/env python3
"""Workshop OS 12.3.6: WS350 touch responsiveness and audio fixes.

The owner's physical acceptance of 12.3.5 answered "no" to touch comfort on
ten views, to overall touch responsiveness, and to audio noise, the on-screen
microphone level and recording intelligibility. This layer fixes the causes
found in the firmware. It runs after apply_workshop_os12_tabs_overhaul.py
(the owning patch of the three tabs) and changes whole functions.

Touch (smart_hub.cpp, display_ui.cpp, main.cpp):
- Changed rows only: the hub frame is still composed into the PSRAM sprite,
  but hubCommitFrame hashes each row and pushes only the bands that differ
  from what is on the panel (include/workshop_frame_diff.hpp, host-tested).
  Up to 12.3.5 every 250 ms tick pushed all 307,200 bytes at 40 MHz SPI
  (61 ms or more with the main loop blocked and the FT6336 unread).
- Immediate redraw: a hub change (tap, toast, page switch) is drawn on the
  next loop instead of waiting for the 250 ms display tick.
- Pressed highlight on touch-down: the target a finger lands on is outlined
  at once (only that rectangle is pushed); the action still runs on release.
- More pages: the live microphone meter is driven from smartHubService.

Audio (buzzer_backend_es8311.cpp, buzzer_backend.h, web_server.cpp):
- No codec power cycling on boards without an amplifier enable pin
  (WS350: AUDIO_PA_CTRL=-1, the amplifier is always on). After the idle
  timeout the codec keeps streaming zeros with its DAC volume at 0 instead of
  being reset and powered down, which popped every time.
- Microphone capture moves into the audio task, in lockstep with the I2S
  writes, so the 48 ms RX DMA ring is read every 8 ms no matter how long the
  main loop is busy. The recording completes by size, not by wall clock.
- Playback picks the microphone slot, removes its DC offset, caps the gain at
  16x and fades 10 ms in and out (include/workshop_recording_dsp.hpp,
  host-tested), writing the same sample to both slots.
- The level meter reads a ring of the last 256 ms that the audio task fills,
  so a sample no longer blocks the main loop, and the screen can show a live
  bar.
- /os12/media/status adds recording and playback diagnostics.
"""
from __future__ import annotations

import argparse
import shutil
import sys as _sys
from pathlib import Path

_here = Path(__file__).resolve().parent
if str(_here) not in _sys.path:
    _sys.path.insert(0, str(_here))
from scripts.smart_home_patch_utils import PatchError, replace_cpp_function  # noqa: E402

BUILD_MARKER = "#define WORKSHOP_OS12_TOUCH_AUDIO_FIT 1"
TABS_MARKER = "#define WORKSHOP_OS12_TABS_OVERHAUL 1"

HEADERS = (
    (Path("firmware") / "platform" / "ui" / "frame_diff.hpp", Path("include") / "workshop_frame_diff.hpp"),
    (Path("firmware") / "platform" / "media" / "recording_dsp.hpp", Path("include") / "workshop_recording_dsp.hpp"),
)


def load(path: Path) -> str:
    if not path.is_file():
        raise PatchError(f"missing {path}")
    return path.read_text(encoding="utf-8")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise PatchError(f"{label}: expected exactly one anchor, found {count}")
    return text.replace(old, new, 1)


# ---------------------------------------------------------------------------
# smart_hub.cpp
# ---------------------------------------------------------------------------

HUB_INCLUDE_OLD = '#include "workshop_tabs_layout.hpp"\n'
HUB_INCLUDE_NEW = '#include "workshop_tabs_layout.hpp"\n#include "workshop_frame_diff.hpp"\n'

COMMIT_SIGNATURE = "static void hubCommitFrame()"
COMMIT_NEW = r'''// 12.3.6: push only the rows that changed. Each committed frame's row hashes
// are kept; the next commit pushes the bands whose hash differs (through a
// clip rectangle on the panel), or the whole frame when forced (page change,
// forced redraw, or something drew straight to the panel).
static const int16_t kHubMaxRows = 480;
static uint32_t g_hubRowHash[kHubMaxRows];
static uint32_t g_hubNextHash[kHubMaxRows];
static bool g_hubRowHashValid = false;
static bool g_hubCommitForceFull = false;
static bool g_hubPressShown = false;
static workshop::ui::more::Rect g_hubPressRect = {0, 0, 0, 0};
static uint32_t g_hubCommitsFull = 0;
static uint32_t g_hubCommitsBands = 0;
static uint32_t g_hubCommitsSkipped = 0;

// The pressed-highlight outline (12.3.6), drawn on `dst` at g_hubPressRect.
static void hubPaintPressed(lgfx::LovyanGFX* dst) {
  const workshop::ui::more::Rect& r = g_hubPressRect;
  if (!dst || r.empty()) return;
  const int16_t radius = r.h >= 40 ? 10 : 8;
  dst->drawRoundRect(r.x + 1, r.y + 1, r.w - 2, r.h - 2, radius, OS12V_ACCENT);
  dst->drawRoundRect(r.x + 2, r.y + 2, r.w - 4, r.h - 4, radius - 1, OS12V_ACCENT);
}

// Rows that were drawn straight to the panel: the next commit re-pushes them.
static void hubInvalidateRows(int16_t y, int16_t h) {
  for (int16_t r = y < 0 ? 0 : y; r < y + h && r < kHubMaxRows; ++r) g_hubRowHash[r] ^= 0xA5A5A5A5u;
}

static void hubCommitFrame() {
  if (!g_hubFrame || !g_hubFrame->getBuffer()) return;
  const int16_t w = g_hubFrameW, h = g_hubFrameH;
  const uint16_t* buf = static_cast<const uint16_t*>(g_hubFrame->getBuffer());
  const bool full = !g_hubFramePrimed || !g_hubRowHashValid || g_hubCommitForceFull || h > kHubMaxRows ||
                    !g_hubPanelCanvas;
  if (h <= kHubMaxRows)
    for (int16_t y = 0; y < h; ++y) g_hubNextHash[y] = workshop::ui::frame::rowHash(buf + (size_t)y * (size_t)w, w);
  if (full) {
    g_hubFrame->pushSprite(0, 0);
    ++g_hubCommitsFull;
  } else {
    workshop::ui::frame::Band bands[6];
    const uint8_t n = workshop::ui::frame::diffBands(g_hubRowHash, g_hubNextHash, h, 8, bands, 6);
    for (uint8_t i = 0; i < n; ++i) {
      g_hubPanelCanvas->setClipRect(0, bands[i].y, w, bands[i].h);
      g_hubFrame->pushSprite(0, 0);
    }
    if (n) {
      g_hubPanelCanvas->clearClipRect();
      ++g_hubCommitsBands;
    } else {
      ++g_hubCommitsSkipped;
    }
  }
  if (h <= kHubMaxRows) {
    memcpy(g_hubRowHash, g_hubNextHash, sizeof(uint32_t) * (size_t)h);
    g_hubRowHashValid = true;
  }
  g_hubCommitForceFull = false;
  g_hubFrameDirty = false;
  g_hubFramePrimed = true;
}
'''

DRAW_COMMIT_OLD = """    if (g_hubFrameDirty || effectiveForce) {
      g_hubFrameDirty = true;
      hubCommitFrame();
    }
  }
}
"""
DRAW_COMMIT_NEW = """    if (g_hubFrameDirty || effectiveForce) {
      g_hubFrameDirty = true;
      if (effectiveForce) g_hubCommitForceFull = true;
      // A finger is still down on a control: keep its outline in the frame.
      if (g_hubPressShown) hubPaintPressed(g_hubFrame);
      hubCommitFrame();
    }
  }
  // The frame now shows the current state (12.3.6: g_dirty also asks
  // updateDisplay for an immediate redraw, so it must not stay set).
  g_dirty = false;
}
"""

HOLD_OLD = "  if(kind==3){wtDrawStopHold(wsm::makeRect(bx,by,bw,bh),segments);hubMarkFrameDirty();return;}"
HOLD_NEW = ("  // Drawn straight to the panel: the next commit pushes the whole frame.\n"
            "  g_hubCommitForceFull = true;\n" + HOLD_OLD)

TOUCH_OLD = """bool smartHubHandleTouch(uint16_t rawX, uint16_t rawY, bool longPress) {
  smartHubUpdateHoldProgress(rawX,rawY,0);
"""
TOUCH_NEW = """// 12.3.6 pressed highlight. On touch-down the target under the finger is
// outlined at once: drawn into the sprite and pushed for that rectangle only
// (or straight to the panel over a running video). The action still runs on
// release, and the release redraws the page, which removes the outline.
static void hubDrawPressed(const wsm::Rect& r) {
  if (r.empty()) return;
  const bool direct = getScreenState() == SCREEN_HUB_MORE && wsVideoDirect();
  lgfx::LovyanGFX* dst = nullptr;
  if (direct) dst = tft_ptr;
  else if (g_hubFrame && g_hubFrame->getBuffer() && g_hubFramePrimed && g_hubPanelCanvas) dst = g_hubFrame;
  if (!dst) return;
  g_hubPressRect = r;
  hubPaintPressed(dst);
  if (!direct) {
    g_hubPanelCanvas->setClipRect(r.x, r.y, r.w, r.h);
    g_hubFrame->pushSprite(0, 0);
    g_hubPanelCanvas->clearClipRect();
    // The sprite now differs from its stored hashes only by the outline;
    // make sure the next commit re-pushes those rows without it.
    hubInvalidateRows(r.y, r.h);
  }
  g_hubPressShown = true;
}

void smartHubTouchDown(uint16_t rawX, uint16_t rawY) {
  if (!g_cfg.enabled || !smartHubIsScreen(getScreenState())) return;
  if (workshopStatusTokenPromptVisible() || workshopCodeTokenPromptVisible()) return;
  int16_t x = 0, y = 0;
  mapHubTouch(rawX, rawY, x, y);
  wsm::Rect r = wsm::makeRect(0, 0, 0, 0);
  if (hubPressRect(x, y, r)) hubDrawPressed(r);
}

bool smartHubRedrawPending() { return g_dirty; }

bool smartHubHandleTouch(uint16_t rawX, uint16_t rawY, bool longPress) {
  smartHubUpdateHoldProgress(rawX,rawY,0);
  if (g_hubPressShown) { g_hubPressShown = false; g_dirty = true; }
"""

STUB_OLD = "bool smartHubHandleTouch(uint16_t, uint16_t, bool) { return false; }\n"
STUB_NEW = STUB_OLD + "void smartHubTouchDown(uint16_t, uint16_t) {}\nbool smartHubRedrawPending() { return false; }\n"

SERVICE_OLD = """void smartHubService() {
  if (!g_initialized) smartHubInit();
"""
SERVICE_NEW = SERVICE_OLD + "  wsMoreService();  // 12.3.6 live microphone meter\n"

HEADER_OLD = "void smartHubUpdateHoldProgress(uint16_t rawX, uint16_t rawY, uint32_t holdMs);\n"
HEADER_NEW = HEADER_OLD + """// 12.3.6: touch-down feedback. Outlines the target under the finger at once;
// the tap itself is still dispatched on release by smartHubHandleTouch.
void smartHubTouchDown(uint16_t rawX, uint16_t rawY);
// 12.3.6: true when the hub has a change to draw (updateDisplay draws it on
// the next loop instead of waiting for the display tick).
bool smartHubRedrawPending();
"""

# ---------------------------------------------------------------------------
# display_ui.cpp and main.cpp
# ---------------------------------------------------------------------------

THROTTLE_OLD = """  unsigned long now = millis();
  unsigned long interval = gaugesAnimating ? GAUGE_ANIM_MS : DISPLAY_UPDATE_MS;
"""
THROTTLE_NEW = """  unsigned long now = millis();
  // 12.3.6: a hub page with a change to show (a tap, a toast, a page switch)
  // draws on the next loop, not up to DISPLAY_UPDATE_MS (250 ms) later. The
  // 20 ms floor keeps a flag that is set every loop from redrawing nonstop.
  static const unsigned long kHubChangeRedrawMs = 20;
  const bool hubChanged = smartHubIsScreen(currentScreen) &&
                          (currentScreen != prevScreen || smartHubRedrawPending());
  unsigned long interval = hubChanged ? kHubChangeRedrawMs : (gaugesAnimating ? GAUGE_ANIM_MS : DISPLAY_UPDATE_MS);
"""

MAIN_TOUCH_OLD = """      hubTouchHasPoint = buttonGetTouchPosition(&hubTouchX, &hubTouchY);
      buzzerPlayClick();
"""
MAIN_TOUCH_NEW = """      hubTouchHasPoint = buttonGetTouchPosition(&hubTouchX, &hubTouchY);
      // 12.3.6: show which control the finger is on before anything else.
      if (hubTouchHasPoint) smartHubTouchDown(hubTouchX, hubTouchY);
      buzzerPlayClick();
"""

# ---------------------------------------------------------------------------
# buzzer_backend_es8311.cpp
# ---------------------------------------------------------------------------

ES_INCLUDE_OLD = "#include <esp_heap_caps.h>\n"
ES_INCLUDE_NEW = "#include <esp_heap_caps.h>\n#include <string.h>\n#include \"workshop_recording_dsp.hpp\"\n"

ES_STATE_OLD = "uint16_t gOs12PlaybackSourcePeak = 0U;\n"
ES_STATE_NEW = ES_STATE_OLD + r'''
// ---- 12.3.6 --------------------------------------------------------------
// Idle quiet: on a board without an amplifier enable pin (WS350) the codec is
// never powered down at idle; its DAC volume goes to 0 while zeros stream.
volatile bool gIdleQuiet = false;
// Recording, filled by the audio task in lockstep with the I2S writes.
size_t gOs12RecordingTargetBytes = 0;
uint32_t gOs12RecordingStartedMs = 0;
volatile uint32_t gOs12RecordingWallMs = 0;
volatile uint32_t gOs12RecordRxShortReads = 0;
workshop::media::dsp::ClipAnalysis gOs12Clip = {0, 0, 0, 256U};
// Microphone meter: per-chunk statistics of the last 32 RX chunks (8 ms
// each, 256 ms), written by the audio task, read by buzzerBackendMicLevel
// and the live meter.
struct Os12MicChunk {
  uint16_t peak;
  int16_t minSample;
  int16_t maxSample;
  uint16_t nonZero;
  uint16_t samples;
};
constexpr uint8_t kOs12MicRing = 32;
Os12MicChunk gOs12MicRingBuf[kOs12MicRing];
volatile uint32_t gOs12MicRingHead = 0;   // chunks written since boot
volatile uint32_t gOs12MicSampleCount = 0;
'''

ES_QUIET_ANCHOR = "// ----- I2S -----\n"
ES_QUIET_NEW = r'''// 12.3.6: DAC digital volume to 0 while idle, back to the setting on the next
// sound. Only ever switched while the task streams zeros, so it is silent.
void os12SetIdleQuiet(bool quiet) {
  if (gIdleQuiet == quiet || !gCodecReady) { gIdleQuiet = quiet && gCodecReady; return; }
  uint8_t vol = 0;
  if (!quiet) {
    const uint8_t pct = buzzerSettings.volume <= 100 ? buzzerSettings.volume : 75;
    vol = (pct == 0) ? 0 : (uint8_t)(((pct * 256U) / 100U) - 1U);
  }
  if (esWrite(ES_REG_DAC_32, vol)) gIdleQuiet = quiet;
}

''' + ES_QUIET_ANCHOR

AUDIO_TASK_SIGNATURE = "void audioTask(void*)"
AUDIO_TASK_NEW = r'''#if defined(BOARD_HAS_MICROPHONE) && defined(AUDIO_I2S_DIN) && (AUDIO_I2S_DIN >= 0)
// 12.3.6: one RX chunk into the meter ring (both slots, as before).
void os12MeterChunk(const int16_t* s, size_t count) {
  Os12MicChunk c;
  int32_t peak = 0;
  c.minSample = INT16_MAX;
  c.maxSample = INT16_MIN;
  uint32_t nz = 0;
  for (size_t i = 0; i < count; ++i) {
    const int16_t v = s[i];
    if (v) ++nz;
    if (v < c.minSample) c.minSample = v;
    if (v > c.maxSample) c.maxSample = v;
    int32_t a = v;
    if (a < 0) a = -a;
    if (a > peak) peak = a;
  }
  if (!count) { c.minSample = 0; c.maxSample = 0; }
  c.peak = (uint16_t)(peak > 65535 ? 65535 : peak);
  c.nonZero = (uint16_t)nz;
  c.samples = (uint16_t)count;
  gOs12MicRingBuf[gOs12MicRingHead % kOs12MicRing] = c;
  gOs12MicRingHead = gOs12MicRingHead + 1;
}

// 12.3.6: one RX chunk into the recording; completes the clip by size.
void os12StoreChunk(const uint8_t* data, size_t bytes) {
  const size_t used = gOs12RecordingBytes;
  if (!gOs12RecordingData || used >= gOs12RecordingCapacity) {
    gOs12RecordingActive = false;
    gOs12CaptureKeepAlive = false;
    return;
  }
  size_t n = gOs12RecordingCapacity - used;
  if (n > bytes) n = bytes;
  memcpy(gOs12RecordingData + used, data, n);
  gOs12RecordingBytes = used + n;
  if (gOs12RecordingBytes >= gOs12RecordingCapacity) {
    gOs12RecordingWallMs = millis() - gOs12RecordingStartedMs;
    gOs12RecordingActive = false;
    gOs12CaptureKeepAlive = false;
    gIdleStartMs = millis();
  }
}

// 12.3.6: read what the RX DMA has, right after each TX write. TX and RX run
// on the same clock, so one 8 ms chunk is normally ready; up to three more
// are drained without waiting if the task fell behind.
void os12ReadMic(int16_t* rx, size_t rxBytes) {
  for (uint8_t i = 0; i < 4; ++i) {
    size_t got = 0;
    const TickType_t wait = i == 0 ? pdMS_TO_TICKS(20) : 0;
    if (i2s_read((i2s_port_t)AUDIO_I2S_PORT, rx, rxBytes, &got, wait) != ESP_OK || got == 0) {
      if (i == 0 && gOs12RecordingActive) gOs12RecordRxShortReads = gOs12RecordRxShortReads + 1;
      return;
    }
    got -= got % (2 * sizeof(int16_t));
    os12MeterChunk(rx, got / sizeof(int16_t));
    if (gOs12RecordingActive) os12StoreChunk(reinterpret_cast<const uint8_t*>(rx), got);
    if (got < rxBytes) return;
  }
}
#endif

void audioTask(void*) {
  static int16_t chunk[kChunkSamples];
#if defined(BOARD_HAS_MICROPHONE) && defined(AUDIO_I2S_DIN) && (AUDIO_I2S_DIN >= 0)
  static int16_t rx[kChunkSamples];
#endif

  while (!gShutdownRequested) {
    if (gOs12PlaybackActive && gOs12RecordingData && gOs12PlaybackPosition < gOs12RecordingBytes) {
      gIdleStartMs = millis();
      // 12.3.6: the microphone slot, DC removed, bounded gain, 10 ms fades,
      // the same sample in both slots (workshop_recording_dsp.hpp).
      const size_t frameBytes = 2 * sizeof(int16_t);
      const size_t totalFrames = gOs12RecordingBytes / frameBytes;
      const size_t startFrame = gOs12PlaybackPosition / frameBytes;
      size_t frames = totalFrames > startFrame ? totalFrames - startFrame : 0;
      if (frames > kFramesPerChunk) frames = kFramesPerChunk;
      memset(chunk, 0, sizeof(chunk));
      workshop::media::dsp::renderChunk(reinterpret_cast<const int16_t*>(gOs12RecordingData), startFrame, frames,
                                        totalFrames, gOs12Clip, chunk);
      gOs12PlaybackPosition += frames ? frames * frameBytes : gOs12RecordingBytes;
      if (gOs12PlaybackPosition >= gOs12RecordingBytes) {
        gOs12PlaybackActive = false;
        gOs12CaptureKeepAlive = false;
        gIdleStartMs = millis();
      }
    } else {
      fillChunk(chunk);
    }
    size_t written = 0;
    i2s_write((i2s_port_t)AUDIO_I2S_PORT, chunk, sizeof(chunk),
              &written, pdMS_TO_TICKS(50));
#if defined(BOARD_HAS_MICROPHONE) && defined(AUDIO_I2S_DIN) && (AUDIO_I2S_DIN >= 0)
    os12ReadMic(rx, sizeof(rx));
#endif
  }

  // Clean self-exit
  gTaskStarted = false;
  gAudioTask = nullptr;
  vTaskDelete(nullptr);
}
'''

# The audio task runs above the Arduino loop task (priority 1) so it is never
# starved by a long frame push; it blocks on DMA almost all the time.
TASK_PRIO_OLD = 'audioTask, "buzzer_es8311", 4096, nullptr, 1, (TaskHandle_t*)&gAudioTask, tskNO_AFFINITY);'
TASK_PRIO_NEW = 'audioTask, "buzzer_es8311", 4096, nullptr, 3, (TaskHandle_t*)&gAudioTask, tskNO_AFFINITY);'

TICK_OLD = "      if (!gOs12CaptureKeepAlive) shutdownAudio();\n"
TICK_NEW = """      if (!gOs12CaptureKeepAlive) {
#if AUDIO_PA_CTRL >= 0
        shutdownAudio();
#else
        // 12.3.6: no amplifier enable pin (WS350): the amplifier is always
        // powered, so resetting and powering the codec down and up again is
        // what popped after every sound. Keep it running, DAC muted.
        os12SetIdleQuiet(true);
#endif
      }
"""

SHUTDOWN_OLD = """  gAudioState = AUDIO_OFF;
  Serial.println("ES8311: audio shutdown");"""
SHUTDOWN_NEW = """  gIdleQuiet = false;
  gAudioState = AUDIO_OFF;
  Serial.println("ES8311: audio shutdown");"""

APPLY_STEP_OLD = """  if (freq > 0) {
    if (!ensureAudioRunning()) return;
    gIdleStartMs = 0;  // reset idle timer"""
APPLY_STEP_NEW = """  if (freq > 0) {
    if (!ensureAudioRunning()) return;
    os12SetIdleQuiet(false);  // 12.3.6: zeros are streaming, so this is silent
    gIdleStartMs = 0;  // reset idle timer"""

SET_VOLUME_OLD = """  buzzerSettings.volume = percent;
  if (!gCodecReady) return;"""
SET_VOLUME_NEW = """  buzzerSettings.volume = percent;
  if (!gCodecReady || gIdleQuiet) return;  // 12.3.6: applied when the DAC unmutes"""

MIC_LEVEL_SIGNATURE = "int buzzerBackendMicLevel(uint16_t sampleMs)"
MIC_LEVEL_NEW = r'''// 12.3.6: the audio task reads the microphone continuously into a 256 ms
// ring, so a level sample is the last `sampleMs` of it (no i2s_read here,
// no 250 ms block of the main loop). Only a cold start waits for the ring.
int buzzerBackendMicLevel(uint16_t sampleMs) {
  if (sampleMs < 80) sampleMs = 80;
  if (sampleMs > 256) sampleMs = 256;
  if (!ensureAudioRunning()) return -1;
  const uint32_t want = (sampleMs + 7U) / 8U;
  const uint32_t waitStart = millis();
  while (gOs12MicRingHead < want && millis() - waitStart < (uint32_t)sampleMs + 150U) delay(5);
  const uint32_t head = gOs12MicRingHead;
  const uint32_t n = head < want ? head : want;
  int32_t peak = 0;
  int16_t minSample = INT16_MAX;
  int16_t maxSample = INT16_MIN;
  uint32_t nonZeroSamples = 0;
  uint32_t totalSamples = 0;
  for (uint32_t i = 0; i < n; ++i) {
    const Os12MicChunk c = gOs12MicRingBuf[(head - 1 - i) % kOs12MicRing];
    if (c.peak > peak) peak = c.peak;
    if (c.minSample < minSample) minSample = c.minSample;
    if (c.maxSample > maxSample) maxSample = c.maxSample;
    nonZeroSamples += c.nonZero;
    totalSamples += c.samples;
  }
  if (totalSamples == 0) {
    minSample = 0;
    maxSample = 0;
  }
  gOs12MicLastBytes = totalSamples * (uint32_t)sizeof(int16_t);
  gOs12MicLastSamples = totalSamples;
  gOs12MicLastNonZeroSamples = nonZeroSamples;
  gOs12MicLastPeak = (uint32_t)peak;
  gOs12MicSampleCount = gOs12MicSampleCount + 1;
  Serial.printf(
      "OS12 mic raw: bytes=%u samples=%u nonzero=%u min=%d max=%d peak=%ld\n",
      (unsigned)gOs12MicLastBytes,
      (unsigned)totalSamples,
      (unsigned)nonZeroSamples,
      (int)minSample,
      (int)maxSample,
      (long)peak);
  if (gTargetGain == 0 && gCurrentGain == 0) gIdleStartMs = millis();
  // Map -60 dBFS..0 dBFS to 0..100 for a human-scale activity meter.
  // Raw peak remains authoritative diagnostic evidence.
  return (int)workshop::media::dsp::levelPercentFromPeak((uint32_t)peak);
}

// 12.3.6 live meter: the level of the last ~96 ms (12 chunks), or -1.
int buzzerBackendMicLiveLevel() {
  if (gAudioState != AUDIO_RUNNING) return -1;
  const uint32_t head = gOs12MicRingHead;
  if (!head) return -1;
  const uint32_t n = head < 12U ? head : 12U;
  uint32_t peak = 0;
  for (uint32_t i = 0; i < n; ++i) {
    const uint16_t p = gOs12MicRingBuf[(head - 1 - i) % kOs12MicRing].peak;
    if (p > peak) peak = p;
  }
  return (int)workshop::media::dsp::levelPercentFromPeak(peak);
}

// 12.3.6: make sure the microphone is being read (for the live meter).
bool buzzerBackendMicMeterBegin() {
  if (!ensureAudioRunning()) return false;
  if (gTargetGain == 0 && gCurrentGain == 0) gIdleStartMs = millis();
  return true;
}

uint32_t buzzerBackendMicSampleCount() { return gOs12MicSampleCount; }
'''

CAPTURE_START = "bool buzzerBackendMicRecordBegin(uint32_t maxDurationMs) {"
CAPTURE_END = "#else\nbool buzzerBackendMicRecordBegin(uint32_t) { return false; }"
CAPTURE_NEW = r'''bool buzzerBackendMicRecordBegin(uint32_t maxDurationMs) {
  if (gOs12PlaybackActive) return false;
  if (maxDurationMs < kOs12RecordMinMs) maxDurationMs = kOs12RecordMinMs;
  if (maxDurationMs > kOs12RecordMaxMs) maxDurationMs = kOs12RecordMaxMs;
  if (!ensureAudioRunning()) return false;

  os12FreeRecording();
  const uint64_t bytes64 = ((uint64_t)kSampleRate * 2ULL * sizeof(int16_t) * maxDurationMs) / 1000ULL;
  if (bytes64 == 0 || bytes64 > 512000ULL) return false;
  const size_t capacity = (size_t)(bytes64 - bytes64 % (2U * sizeof(int16_t)));
  gOs12RecordingData = static_cast<uint8_t*>(
      heap_caps_malloc(capacity, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT));
  if (!gOs12RecordingData) return false;

  gOs12CaptureKeepAlive = true;
  gIdleStartMs = millis();
  buzzerBackendStop();

  // 12.3.6: the audio task fills the clip from its next RX chunk, in step
  // with the I2S clock (no draining or reading from the main loop here).
  gOs12RecordingCapacity = capacity;
  gOs12RecordingTargetBytes = capacity;
  gOs12RecordingBytes = 0;
  gOs12RecordingWallMs = 0;
  gOs12RecordRxShortReads = 0;
  gOs12RecordingStartedMs = millis();
  // Safety only: the clip completes by size; this ends a stalled capture.
  gOs12RecordingDeadlineMs = millis() + maxDurationMs + 1500U;
  gOs12RecordingActive = true;
  return true;
}

bool buzzerBackendMicRecordPoll() {
  if (!gOs12RecordingActive) {
    if (gOs12CaptureKeepAlive && !gOs12PlaybackActive) os12FinishRecording();
    return false;
  }
  if (!gOs12RecordingData || gOs12RecordingCapacity == 0 || os12DeadlineReached(gOs12RecordingDeadlineMs)) {
    if (!gOs12RecordingWallMs) gOs12RecordingWallMs = millis() - gOs12RecordingStartedMs;
    os12FinishRecording();
    return false;
  }
  gIdleStartMs = millis();
  return true;
}

bool buzzerBackendMicRecordStop() {
  if (gOs12RecordingActive || gOs12CaptureKeepAlive) {
    if (gOs12RecordingActive && !gOs12RecordingWallMs) gOs12RecordingWallMs = millis() - gOs12RecordingStartedMs;
    os12FinishRecording();
  }
  return gOs12RecordingData != nullptr && gOs12RecordingBytes > 0;
}

bool buzzerBackendMicHasRecording() {
  return gOs12RecordingData != nullptr && gOs12RecordingBytes > 0;
}

bool buzzerBackendMicPlaybackBegin() {
  if (gOs12RecordingActive || gOs12CaptureKeepAlive || !buzzerBackendMicHasRecording()) return false;
  if (!ensureAudioRunning()) return false;

  // 12.3.6: analyse the clip once (workshop_recording_dsp.hpp): the slot
  // with the most AC energy is the microphone, its mean is the DC offset,
  // and the gain comes from the DC-free peak, capped at 16x. The stored
  // recording is never modified.
  const size_t frames = gOs12RecordingBytes / (2U * sizeof(int16_t));
  gOs12Clip = workshop::media::dsp::analyzeStereoClip(reinterpret_cast<const int16_t*>(gOs12RecordingData), frames);
  gOs12PlaybackSourcePeak = gOs12Clip.peak;
  gOs12PlaybackGainQ8 = gOs12Clip.gainQ8;

  Serial.printf(
      "OS12 playback: frames=%u slot=%u dc=%d peak=%u gainQ8=%lu gain=%.2fx\n",
      (unsigned)frames,
      (unsigned)gOs12Clip.channel,
      (int)gOs12Clip.dc,
      (unsigned)gOs12Clip.peak,
      (unsigned long)gOs12Clip.gainQ8,
      (double)gOs12Clip.gainQ8 / 256.0);

  gOs12CaptureKeepAlive = true;
  gIdleStartMs = millis();
  buzzerBackendStop();
  os12SetIdleQuiet(false);
  gOs12PlaybackPosition = 0;
  gOs12PlaybackActive = true;
  return true;
}

bool buzzerBackendMicPlaybackPoll() {
  if (gOs12PlaybackActive) gIdleStartMs = millis();
  return gOs12PlaybackActive;
}

void buzzerBackendMicPlaybackStop() {
  gOs12PlaybackActive = false;
  gOs12PlaybackPosition = 0;
  gOs12CaptureKeepAlive = false;
  gIdleStartMs = millis();
}

// 12.3.6 recording and playback diagnostics (/os12/media/status).
uint32_t buzzerBackendRecordingBytes() { return (uint32_t)gOs12RecordingBytes; }
uint32_t buzzerBackendRecordingTargetBytes() { return (uint32_t)gOs12RecordingTargetBytes; }
uint32_t buzzerBackendRecordingWallMs() { return gOs12RecordingWallMs; }
uint32_t buzzerBackendRecordingRxShortReads() { return gOs12RecordRxShortReads; }
uint8_t buzzerBackendPlaybackSlot() { return gOs12Clip.channel; }
int16_t buzzerBackendPlaybackDcOffset() { return gOs12Clip.dc; }
uint32_t buzzerBackendPlaybackGainQ8() { return gOs12Clip.gainQ8; }
bool buzzerBackendAudioIdleQuiet() { return gIdleQuiet; }
'''
CAPTURE_STUBS_OLD = "void buzzerBackendMicPlaybackStop() {}\n#endif\n"
CAPTURE_STUBS_NEW = """void buzzerBackendMicPlaybackStop() {}
int buzzerBackendMicLiveLevel() { return -1; }
bool buzzerBackendMicMeterBegin() { return false; }
uint32_t buzzerBackendMicSampleCount() { return 0; }
uint32_t buzzerBackendRecordingBytes() { return 0; }
uint32_t buzzerBackendRecordingTargetBytes() { return 0; }
uint32_t buzzerBackendRecordingWallMs() { return 0; }
uint32_t buzzerBackendRecordingRxShortReads() { return 0; }
uint8_t buzzerBackendPlaybackSlot() { return 0; }
int16_t buzzerBackendPlaybackDcOffset() { return 0; }
uint32_t buzzerBackendPlaybackGainQ8() { return 256; }
bool buzzerBackendAudioIdleQuiet() { return gIdleQuiet; }
#endif
"""

BACKEND_HEADER_OLD = "uint16_t buzzerBackendAudioCurrentGain();\n"
BACKEND_HEADER_NEW = BACKEND_HEADER_OLD + """// 12.3.6 (ES8311): live microphone meter and recording diagnostics.
int buzzerBackendMicLiveLevel();
bool buzzerBackendMicMeterBegin();
uint32_t buzzerBackendMicSampleCount();
uint32_t buzzerBackendRecordingBytes();
uint32_t buzzerBackendRecordingTargetBytes();
uint32_t buzzerBackendRecordingWallMs();
uint32_t buzzerBackendRecordingRxShortReads();
uint8_t buzzerBackendPlaybackSlot();
int16_t buzzerBackendPlaybackDcOffset();
uint32_t buzzerBackendPlaybackGainQ8();
bool buzzerBackendAudioIdleQuiet();
"""

STATUS_ES_OLD = '  doc["audioCurrentGain"] = buzzerBackendAudioCurrentGain();\n#else\n'
STATUS_ES_NEW = '''  doc["audioCurrentGain"] = buzzerBackendAudioCurrentGain();
  doc["audioIdleQuiet"] = buzzerBackendAudioIdleQuiet();
  doc["recordingBytes"] = buzzerBackendRecordingBytes();
  doc["recordingTargetBytes"] = buzzerBackendRecordingTargetBytes();
  doc["recordingWallMs"] = buzzerBackendRecordingWallMs();
  doc["recordingRxShortReads"] = buzzerBackendRecordingRxShortReads();
  doc["playbackSlot"] = buzzerBackendPlaybackSlot();
  doc["playbackDcOffset"] = buzzerBackendPlaybackDcOffset();
  doc["playbackGainQ8"] = buzzerBackendPlaybackGainQ8();
#else
'''
STATUS_NONE_OLD = '  doc["audioCurrentGain"] = 0;\n#endif\n'
STATUS_NONE_NEW = '''  doc["audioCurrentGain"] = 0;
  doc["audioIdleQuiet"] = false;
  doc["recordingBytes"] = 0;
  doc["recordingTargetBytes"] = 0;
  doc["recordingWallMs"] = 0;
  doc["recordingRxShortReads"] = 0;
  doc["playbackSlot"] = 0;
  doc["playbackDcOffset"] = 0;
  doc["playbackGainQ8"] = 256;
#endif
'''


def install_headers(repo: Path, source_root: Path) -> None:
    for source, target in HEADERS:
        src = source_root / source
        if not src.is_file():
            raise PatchError(f"missing {src}")
        dst = repo / target
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)


def patch_hub(repo: Path) -> None:
    path = repo / "src" / "smart_hub.cpp"
    text = load(path)
    for needle in ("static bool hubPressRect(int16_t x, int16_t y, wsm::Rect& out)", "static void wsMoreService()"):
        if needle not in text:
            raise PatchError(f"smart_hub.cpp lacks {needle} (tabs_pages / more_pages fragments too old)")
    text = replace_once(text, HUB_INCLUDE_OLD, HUB_INCLUDE_NEW, "frame diff include")
    text = replace_cpp_function(text, COMMIT_SIGNATURE, COMMIT_NEW, "hubCommitFrame")
    text = replace_once(text, DRAW_COMMIT_OLD, DRAW_COMMIT_NEW, "smartHubDraw commit")
    text = replace_once(text, HOLD_OLD, HOLD_NEW, "hold progress full push")
    text = replace_once(text, TOUCH_OLD, TOUCH_NEW, "touch-down highlight")
    text = replace_once(text, STUB_OLD, STUB_NEW, "non-hub stubs")
    text = replace_once(text, SERVICE_OLD, SERVICE_NEW, "More service hook")
    path.write_text(text, encoding="utf-8")

    header = repo / "src" / "smart_hub.h"
    htext = replace_once(load(header), HEADER_OLD, HEADER_NEW, "smart_hub.h declarations")
    header.write_text(htext, encoding="utf-8")

    display = repo / "src" / "display_ui.cpp"
    dtext = replace_once(load(display), THROTTLE_OLD, THROTTLE_NEW, "hub change redraw")
    display.write_text(dtext, encoding="utf-8")

    main = repo / "src" / "main.cpp"
    mtext = replace_once(load(main), MAIN_TOUCH_OLD, MAIN_TOUCH_NEW, "touch-down call")
    main.write_text(mtext, encoding="utf-8")


def patch_audio(repo: Path) -> None:
    path = repo / "src" / "buzzer_backend_es8311.cpp"
    text = load(path)
    if "gOs12RecordingData" not in text or "gOs12MicLastPeak" not in text:
        raise PatchError("ES8311 backend lacks the OS12 capture and signal layers")
    text = replace_once(text, ES_INCLUDE_OLD, ES_INCLUDE_NEW, "ES8311 includes")
    text = replace_once(text, ES_STATE_OLD, ES_STATE_NEW, "ES8311 12.3.6 state")
    text = replace_once(text, ES_QUIET_ANCHOR, ES_QUIET_NEW, "idle quiet helper")
    text = replace_cpp_function(text, AUDIO_TASK_SIGNATURE, AUDIO_TASK_NEW, "audio task")
    text = replace_once(text, TASK_PRIO_OLD, TASK_PRIO_NEW, "audio task priority")
    text = replace_once(text, TICK_OLD, TICK_NEW, "idle without codec power cycling")
    text = replace_once(text, SHUTDOWN_OLD, SHUTDOWN_NEW, "shutdown clears idle quiet")
    text = replace_once(text, APPLY_STEP_OLD, APPLY_STEP_NEW, "unmute on sound")
    text = replace_once(text, SET_VOLUME_OLD, SET_VOLUME_NEW, "volume while quiet")
    text = replace_cpp_function(text, MIC_LEVEL_SIGNATURE, MIC_LEVEL_NEW, "microphone level")
    start = text.find(CAPTURE_START)
    end = text.find(CAPTURE_END, start)
    if start < 0 or end < 0 or text.count(CAPTURE_START) != 1:
        raise PatchError("capture API block not found")
    text = text[:start] + CAPTURE_NEW + text[end:]
    text = replace_once(text, CAPTURE_STUBS_OLD, CAPTURE_STUBS_NEW, "capture stubs")
    path.write_text(text, encoding="utf-8")

    header = repo / "src" / "buzzer_backend.h"
    header.write_text(replace_once(load(header), BACKEND_HEADER_OLD, BACKEND_HEADER_NEW, "backend declarations"),
                      encoding="utf-8")

    web = repo / "src" / "web_server.cpp"
    wtext = load(web)
    wtext = replace_once(wtext, STATUS_ES_OLD, STATUS_ES_NEW, "media status (ES8311)")
    wtext = replace_once(wtext, STATUS_NONE_OLD, STATUS_NONE_NEW, "media status (no ES8311)")
    web.write_text(wtext, encoding="utf-8")


def apply(repo: Path, source_root: Path) -> None:
    build_path = repo / "include" / "smart_home_build.h"
    build = load(build_path)
    if TABS_MARKER not in build:
        raise PatchError("the 12.3.6 touch/audio layer runs after apply_workshop_os12_tabs_overhaul.py")
    if BUILD_MARKER in build:
        raise PatchError("the 12.3.6 touch/audio layer is already applied")
    install_headers(repo, source_root)
    patch_hub(repo)
    patch_audio(repo)
    build_path.write_text(build.rstrip() + "\n" + BUILD_MARKER + "\n", encoding="utf-8")
    print("Workshop OS 12.3.6 touch and audio fit installed: changed-row pushes, immediate redraw, "
          "pressed highlight; no codec power cycling, task-side capture, mono DC-free playback, live meter")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    ap.add_argument("--source-root", default=str(_here))
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    if not args.apply:
        raise SystemExit("refusing to modify source without --apply")
    try:
        apply(Path(args.repo).resolve(), Path(args.source_root).resolve())
    except PatchError as exc:
        raise SystemExit(f"FAIL: {exc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
