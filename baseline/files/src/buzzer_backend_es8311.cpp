#include "buzzer_backend.h"
#include "settings.h"

#if defined(BOARD_HAS_ES8311_AUDIO)

#include <Wire.h>
#include <driver/i2s.h>
#include <math.h>
#include <esp_heap_caps.h>

namespace {

// ES8311 register addresses
constexpr uint8_t ES_REG_RESET  = 0x00;
constexpr uint8_t ES_REG_CLK1   = 0x01;
constexpr uint8_t ES_REG_CLK2   = 0x02;
constexpr uint8_t ES_REG_CLK3   = 0x03;
constexpr uint8_t ES_REG_CLK4   = 0x04;
constexpr uint8_t ES_REG_CLK5   = 0x05;
constexpr uint8_t ES_REG_CLK6   = 0x06;
constexpr uint8_t ES_REG_CLK7   = 0x07;
constexpr uint8_t ES_REG_CLK8   = 0x08;
constexpr uint8_t ES_REG_SDP_IN = 0x09;
constexpr uint8_t ES_REG_SDP_OUT = 0x0A;
constexpr uint8_t ES_REG_SYS_0D = 0x0D;
constexpr uint8_t ES_REG_SYS_0E = 0x0E;
constexpr uint8_t ES_REG_SYS_12 = 0x12;
constexpr uint8_t ES_REG_SYS_13 = 0x13;
constexpr uint8_t ES_REG_ADC_1C = 0x1C;
constexpr uint8_t ES_REG_DAC_31 = 0x31;
constexpr uint8_t ES_REG_DAC_32 = 0x32;
constexpr uint8_t ES_REG_DAC_37 = 0x37;

// Audio parameters
constexpr uint32_t kSampleRate     = 16000;
constexpr size_t   kFramesPerChunk = 128;           // per DMA buffer
constexpr size_t   kChunkSamples   = kFramesPerChunk * 2;  // stereo
constexpr int16_t  kToneAmplitude  = 9000;
constexpr uint8_t  kCodecVolume    = 75;            // percent

// Envelope for click-free transitions between tones
constexpr uint16_t kEnvMax  = 256;
constexpr uint16_t kEnvStep = 4;   // ~4ms full ramp at 16 kHz / 128 frames

// Idle timeout - shutdown audio pipeline after this much silence
constexpr uint32_t kIdleTimeoutMs = 1500;

// Audio lifecycle state
enum AudioState : uint8_t { AUDIO_OFF = 0, AUDIO_RUNNING };
volatile AudioState gAudioState = AUDIO_OFF;
volatile bool gShutdownRequested = false;
uint32_t gIdleStartMs = 0;

// Tone state - shared between main loop and audio task
volatile uint16_t gCurrentFreq  = 0;
volatile uint32_t gPhaseStep    = 0;
volatile uint16_t gTargetGain   = 0;
volatile uint16_t gCurrentGain  = 0;

// Internal state
bool     gWireReady   = false;
bool     gI2sReady    = false;
bool     gCodecReady  = false;
volatile bool gTaskStarted = false;
bool     gAmpEnabled  = false;
uint32_t gPhase       = 0;
uint32_t gLastTonePhaseStep = 0;

int16_t  gWaveTable[256];
bool     gWaveReady = false;
volatile TaskHandle_t gAudioTask = nullptr;

// ----- helpers -----

void buildWaveTable() {
  if (gWaveReady) return;
  for (int i = 0; i < 256; i++)
    gWaveTable[i] = (int16_t)lroundf(sinf(2.0f * PI * i / 256.0f) * 32767.0f);
  gWaveReady = true;
}

void setAmpEnabled(bool on) {
  if (gAmpEnabled == on) return;
#if AUDIO_PA_CTRL >= 0
  digitalWrite(AUDIO_PA_CTRL, on ? HIGH : LOW);
#endif
  gAmpEnabled = on;
}

void ensureWire() {
  if (gWireReady) return;
  Wire.begin(AUDIO_I2C_SDA, AUDIO_I2C_SCL);
  Wire.setClock(400000);
  gWireReady = true;
}

bool esWrite(uint8_t reg, uint8_t val) {
  Wire.beginTransmission(AUDIO_I2C_ADDR);
  Wire.write(reg);
  Wire.write(val);
  return Wire.endTransmission(true) == 0;
}

bool esRead(uint8_t reg, uint8_t& val) {
  Wire.beginTransmission(AUDIO_I2C_ADDR);
  Wire.write(reg);
  if (Wire.endTransmission(false) != 0) {
    Wire.beginTransmission(AUDIO_I2C_ADDR);
    Wire.write(reg);
    if (Wire.endTransmission(true) != 0) return false;
  }
  if (Wire.requestFrom((uint8_t)AUDIO_I2C_ADDR, (uint8_t)1, (uint8_t)true) != 1) return false;
  val = Wire.read();
  return true;
}

// ----- I2S -----

bool initI2s() {
  if (gI2sReady) return true;

  i2s_config_t cfg = {};
#if defined(AUDIO_I2S_DIN) && (AUDIO_I2S_DIN >= 0)
  cfg.mode            = (i2s_mode_t)(I2S_MODE_MASTER | I2S_MODE_TX | I2S_MODE_RX);
#else
  cfg.mode            = (i2s_mode_t)(I2S_MODE_MASTER | I2S_MODE_TX);
#endif
  cfg.sample_rate     = kSampleRate;
  cfg.bits_per_sample = I2S_BITS_PER_SAMPLE_16BIT;
  cfg.channel_format  = I2S_CHANNEL_FMT_RIGHT_LEFT;
  cfg.communication_format = I2S_COMM_FORMAT_STAND_I2S;
  cfg.intr_alloc_flags = ESP_INTR_FLAG_LEVEL1;
  cfg.dma_buf_count   = 6;
  cfg.dma_buf_len     = kFramesPerChunk;
  cfg.use_apll        = false;
  cfg.tx_desc_auto_clear = true;
  cfg.fixed_mclk      = kSampleRate * 256;
  cfg.mclk_multiple   = I2S_MCLK_MULTIPLE_256;
  cfg.bits_per_chan    = I2S_BITS_PER_CHAN_16BIT;

  if (i2s_driver_install((i2s_port_t)AUDIO_I2S_PORT, &cfg, 0, nullptr) != ESP_OK) {
    Serial.println("ES8311: i2s_driver_install failed");
    return false;
  }

  i2s_pin_config_t pins = {};
  pins.mck_io_num    = AUDIO_I2S_MCLK;
  pins.bck_io_num    = AUDIO_I2S_BCLK;
  pins.ws_io_num     = AUDIO_I2S_LRC;
  pins.data_out_num  = AUDIO_I2S_DOUT;
#if defined(AUDIO_I2S_DIN) && (AUDIO_I2S_DIN >= 0)
  pins.data_in_num   = AUDIO_I2S_DIN;
#else
  pins.data_in_num   = I2S_PIN_NO_CHANGE;
#endif

  if (i2s_set_pin((i2s_port_t)AUDIO_I2S_PORT, &pins) != ESP_OK) {
    Serial.println("ES8311: i2s_set_pin failed");
    i2s_driver_uninstall((i2s_port_t)AUDIO_I2S_PORT);
    return false;
  }

  i2s_zero_dma_buffer((i2s_port_t)AUDIO_I2S_PORT);
  gI2sReady = true;
  return true;
}

// ----- ES8311 codec -----

bool initCodec() {
  if (gCodecReady) return true;
  ensureWire();

  Wire.beginTransmission(AUDIO_I2C_ADDR);
  if (Wire.endTransmission(true) != 0) {
    Serial.printf("ES8311: not found on I2C 0x%02X\n", AUDIO_I2C_ADDR);
    return false;
  }

  // Reset (20 ms settling required)
  if (!esWrite(ES_REG_RESET, 0x1F)) return false;
  delay(20);
  if (!esWrite(ES_REG_RESET, 0x00)) return false;
  if (!esWrite(ES_REG_RESET, 0x80)) return false;

  // Clock registers - tuned for ESP32 I2S master providing 4.096 MHz MCLK
  if (!esWrite(ES_REG_CLK1, 0x3F)) return false;
  if (!esWrite(ES_REG_CLK2, 0x00)) return false;
  if (!esWrite(ES_REG_CLK3, 0x10)) return false;
  if (!esWrite(ES_REG_CLK4, 0x10)) return false;
  if (!esWrite(ES_REG_CLK5, 0x00)) return false;

  uint8_t reg06 = 0;
  esRead(ES_REG_CLK6, reg06);
  reg06 = (reg06 & 0xE0) | 0x03;
  if (!esWrite(ES_REG_CLK6, reg06)) return false;

  if (!esWrite(ES_REG_CLK7, 0x00)) return false;
  if (!esWrite(ES_REG_CLK8, 0xFF)) return false;

  // I2S slave mode
  uint8_t reg00 = 0;
  if (!esRead(ES_REG_RESET, reg00)) return false;
  reg00 &= 0xBF;
  if (!esWrite(ES_REG_RESET, reg00)) return false;

  // 16-bit I2S format
  if (!esWrite(ES_REG_SDP_IN,  0x0C)) return false;
  if (!esWrite(ES_REG_SDP_OUT, 0x0C)) return false;

  // System power-up
  if (!esWrite(ES_REG_SYS_0D, 0x01)) return false;
  if (!esWrite(ES_REG_SYS_0E, 0x02)) return false;
  if (!esWrite(ES_REG_SYS_12, 0x00)) return false;
  if (!esWrite(ES_REG_SYS_13, 0x10)) return false;

  if (!esWrite(ES_REG_ADC_1C, 0x6A)) return false;
  if (!esWrite(ES_REG_DAC_37, 0x08)) return false;

  uint8_t vol = (kCodecVolume == 0) ? 0 : (uint8_t)(((kCodecVolume * 256) / 100) - 1);
  if (!esWrite(ES_REG_DAC_32, vol)) return false;

  uint8_t reg31 = 0;
  esRead(ES_REG_DAC_31, reg31);
  reg31 &= ~0x60;
  if (!esWrite(ES_REG_DAC_31, reg31)) return false;

  gCodecReady = true;
  Serial.println("ES8311: codec initialized");
  return true;
}

// ----- tone generation -----

uint32_t phaseStepFor(uint16_t freq) {
  if (freq == 0) return 0;
  return (uint32_t)(((uint64_t)freq << 32) / kSampleRate);
}

void fillChunk(int16_t* out) {
  uint32_t step = gPhaseStep;
  if (step != 0) gLastTonePhaseStep = step;
  else step = gLastTonePhaseStep;

  for (size_t i = 0; i < kFramesPerChunk; i++) {
    uint16_t target = gTargetGain;
    if (gCurrentGain < target) {
      uint16_t next = gCurrentGain + kEnvStep;
      gCurrentGain = (next > target) ? target : next;
    } else if (gCurrentGain > target) {
      gCurrentGain = (gCurrentGain > kEnvStep + target)
                     ? (uint16_t)(gCurrentGain - kEnvStep)
                     : target;
    }

    int16_t sample = 0;
    if (gCurrentGain > 0 && step != 0) {
      uint8_t idx = (uint8_t)(gPhase >> 24);
      int32_t raw = gWaveTable[idx];
      int64_t scaled = (int64_t)raw * kToneAmplitude * gCurrentGain;
      sample = (int16_t)(scaled / ((int64_t)32767 * kEnvMax));
      gPhase += step;
    }
    out[i * 2]     = sample;
    out[i * 2 + 1] = sample;
  }
}

// ----- audio task -----
// Streams tones when requested, silence between tones.
// Exits cooperatively when gShutdownRequested is set.

void audioTask(void*) {
  static int16_t chunk[kChunkSamples];

  while (!gShutdownRequested) {
    fillChunk(chunk);
    size_t written = 0;
    i2s_write((i2s_port_t)AUDIO_I2S_PORT, chunk, sizeof(chunk),
              &written, pdMS_TO_TICKS(50));
  }

  // Clean self-exit
  gTaskStarted = false;
  gAudioTask = nullptr;
  vTaskDelete(nullptr);
}

void ensureTaskStarted() {
  if (gTaskStarted) return;
  gShutdownRequested = false;
  BaseType_t ok = xTaskCreatePinnedToCore(
      audioTask, "buzzer_es8311", 4096, nullptr, 1, (TaskHandle_t*)&gAudioTask, tskNO_AFFINITY);
  if (ok == pdPASS) {
    gTaskStarted = true;
  } else {
    Serial.println("ES8311: failed to start audio task");
  }
}

// ----- lifecycle management -----

// PA amplifier settling time after power-on.
// Coupling capacitors need to charge before clean audio output. 30 ms proved
// too short on hardware: the first tone after an idle teardown had its attack
// audibly clipped while immediately repeated sounds played fine. The delay is
// invisible to melody timing (buzzer.cpp arms the step timer after this
// returns), it only postpones the first sound's onset.
constexpr uint32_t kPaSettleMs = 100;

bool ensureAudioRunning() {
  if (gAudioState == AUDIO_RUNNING) return true;

  if (!initI2s()) return false;
  if (!initCodec()) return false;
  setAmpEnabled(true);
  ensureTaskStarted();

  // Let PA settle while task streams silence through DMA.
  // Without this, the first ~30ms of audio is muffled/cut.
  delay(kPaSettleMs);

  gAudioState = AUDIO_RUNNING;
  gIdleStartMs = 0;
  Serial.println("ES8311: audio activated");
  return true;
}

void shutdownAudio() {
  if (gAudioState == AUDIO_OFF) return;

  // Signal task to stop cooperatively
  gShutdownRequested = true;

  // Wait for task to finish current i2s_write and self-exit
  if (gTaskStarted && gAudioTask != nullptr) {
    uint32_t waitStart = millis();
    while (gTaskStarted && (millis() - waitStart < 100)) {
      vTaskDelay(pdMS_TO_TICKS(5));
    }
    // Forceful delete as fallback
    if (gTaskStarted) {
      vTaskDelete(gAudioTask);
      gTaskStarted = false;
    }
    gAudioTask = nullptr;
  }

  // Disable PA before I2S teardown (envelope already at 0, no pop)
  setAmpEnabled(false);

  // Tear down I2S
  if (gI2sReady) {
    i2s_zero_dma_buffer((i2s_port_t)AUDIO_I2S_PORT);
    i2s_driver_uninstall((i2s_port_t)AUDIO_I2S_PORT);
    gI2sReady = false;
  }

  // Put codec in standby for real power savings
  // Do NOT call Wire.end() - shared with CST816D touch controller
  if (gCodecReady) {
    esWrite(ES_REG_SYS_0D, 0x00);  // power down DAC
    esWrite(ES_REG_SYS_0E, 0x00);  // power down analog
    gCodecReady = false;
  }

  // Reset tone state
  gCurrentFreq = 0;
  gPhaseStep = 0;
  gTargetGain = 0;
  gCurrentGain = 0;
  gIdleStartMs = 0;
  gShutdownRequested = false;

  gAudioState = AUDIO_OFF;
  Serial.println("ES8311: audio shutdown");
}

}  // namespace

// ----- public API -----

void buzzerBackendInit() {
#if AUDIO_PA_CTRL >= 0
  pinMode(AUDIO_PA_CTRL, OUTPUT);
  digitalWrite(AUDIO_PA_CTRL, LOW);
#endif
  gAmpEnabled = false;
  buildWaveTable();
  gCurrentFreq = 0;
  gPhaseStep = 0;
  gTargetGain = 0;
  gCurrentGain = 0;
  gLastTonePhaseStep = 0;
  gAudioState = AUDIO_OFF;
  // Do NOT start I2S/codec/task here - lazy init on first sound
}

void buzzerBackendApplyStep(uint16_t freq) {
  if (freq > 0) {
    if (!ensureAudioRunning()) return;
    gIdleStartMs = 0;  // reset idle timer
    if (gPhaseStep == 0) {
      gPhase = 0;  // new tone starting - reset phase for clean waveform
    }
  }
  gCurrentFreq = freq;
  gPhaseStep = phaseStepFor(freq);
  if (gPhaseStep != 0) gLastTonePhaseStep = gPhaseStep;
  gTargetGain = (freq > 0) ? kEnvMax : 0;
}

void buzzerBackendStop() {
  gCurrentFreq = 0;
  gPhaseStep = 0;
  gTargetGain = 0;
  // Envelope decays naturally in audio task.
  // Idle timer will be armed by buzzerBackendTick() once gCurrentGain reaches 0.
}

void buzzerBackendTick() {
  if (gAudioState != AUDIO_RUNNING) return;

  // Check if audio pipeline is idle (silence + envelope fully decayed)
  if (gTargetGain == 0 && gCurrentGain == 0) {
    if (gIdleStartMs == 0) {
      gIdleStartMs = millis();
    } else if (millis() - gIdleStartMs >= kIdleTimeoutMs) {
      shutdownAudio();
    }
  } else {
    gIdleStartMs = 0;  // sound is playing or envelope ramping
  }
}

void buzzerBackendShutdown() {
  // Force immediate silence (skip envelope ramp)
  gCurrentGain = 0;
  gTargetGain = 0;
  gPhaseStep = 0;
  gCurrentFreq = 0;
  shutdownAudio();
}

#if defined(BOARD_HAS_MICROPHONE) && defined(AUDIO_I2S_DIN) && (AUDIO_I2S_DIN >= 0)
static void stopAudioTaskForDiagnostic() {
  gCurrentFreq = 0;
  gPhaseStep = 0;
  gTargetGain = 0;
  gCurrentGain = 0;
  gShutdownRequested = true;
  if (gTaskStarted && gAudioTask != nullptr) {
    uint32_t waitStart = millis();
    while (gTaskStarted && (millis() - waitStart < 120)) {
      vTaskDelay(pdMS_TO_TICKS(5));
    }
    if (gTaskStarted) {
      vTaskDelete(gAudioTask);
      gTaskStarted = false;
      gAudioTask = nullptr;
    }
  }
  gShutdownRequested = false;
}

static void restartAudioTaskAfterDiagnostic() {
  gIdleStartMs = millis();
  ensureTaskStarted();
}

int buzzerBackendMicLevel(uint16_t sampleMs) {
  if (sampleMs < 80) sampleMs = 80;
  if (sampleMs > 1200) sampleMs = 1200;
  if (!ensureAudioRunning()) return -1;

  int16_t samples[128];
  int32_t peak = 0;
  uint32_t deadline = millis() + sampleMs;
  do {
    size_t bytesRead = 0;
    if (i2s_read((i2s_port_t)AUDIO_I2S_PORT, samples, sizeof(samples),
                 &bytesRead, pdMS_TO_TICKS(25)) != ESP_OK) return -1;
    size_t count = bytesRead / sizeof(samples[0]);
    for (size_t i = 0; i < count; ++i) {
      int32_t v = samples[i];
      if (v < 0) v = -v;
      if (v > peak) peak = v;
    }
    yield();
  } while ((int32_t)(deadline - millis()) > 0);

  if (gTargetGain == 0 && gCurrentGain == 0) gIdleStartMs = millis();
  int level = (int)((peak * 100L) / 32767L);
  return constrain(level, 0, 100);
}

int buzzerBackendMicEcho(uint16_t recordMs) {
  if (recordMs < 650) recordMs = 650;
  if (recordMs > 1400) recordMs = 1400;
  if (!ensureAudioRunning()) return -1;

  // Avoid capturing the tail of a UI click/tone and let the user start speaking.
  gCurrentFreq = 0;
  gPhaseStep = 0;
  gTargetGain = 0;
  gCurrentGain = 0;
  delay(90);
  stopAudioTaskForDiagnostic();

  const size_t framesWanted = (size_t)((kSampleRate * (uint32_t)recordMs) / 1000UL);
  const size_t samplesWanted = framesWanted * 2; // stereo I2S frames
  const size_t bytesWanted = samplesWanted * sizeof(int16_t);
  int16_t* capture = (int16_t*)heap_caps_malloc(bytesWanted, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
  if (!capture) capture = (int16_t*)heap_caps_malloc(bytesWanted, MALLOC_CAP_8BIT);
  if (!capture) {
    restartAudioTaskAfterDiagnostic();
    return -1;
  }

  // Drain stale RX DMA so playback represents audio spoken after the tap.
  int16_t drain[256];
  size_t drained = 0;
  for (uint8_t i = 0; i < 3; ++i)
    i2s_read((i2s_port_t)AUDIO_I2S_PORT, drain, sizeof(drain), &drained, pdMS_TO_TICKS(10));

  size_t captured = 0;
  int32_t peak = 0;
  const uint32_t deadline = millis() + recordMs + 500UL;
  while (captured < bytesWanted && (int32_t)(deadline - millis()) > 0) {
    size_t got = 0;
    size_t remaining = bytesWanted - captured;
    size_t ask = remaining > 1024 ? 1024 : remaining;
    esp_err_t err = i2s_read((i2s_port_t)AUDIO_I2S_PORT,
                             ((uint8_t*)capture) + captured,
                             ask, &got, pdMS_TO_TICKS(40));
    if (err != ESP_OK) break;
    if (got == 0) { yield(); continue; }
    const size_t first = captured / sizeof(int16_t);
    const size_t count = got / sizeof(int16_t);
    for (size_t i = 0; i < count; ++i) {
      int32_t v = capture[first + i];
      if (v < 0) v = -v;
      if (v > peak) peak = v;
    }
    captured += got;
    yield();
  }

  if (captured < sizeof(int16_t) * 8) {
    free(capture);
    restartAudioTaskAfterDiagnostic();
    return -1;
  }

  // Collapse the louder input channel to mono, apply modest gain, then copy it
  // to both TX channels so the onboard mono speaker reliably receives it.
  size_t samples = captured / sizeof(int16_t);
  samples -= samples % 2;
  for (size_t i = 0; i < samples; i += 2) {
    int32_t a = capture[i];
    int32_t b = capture[i + 1];
    int32_t va = a < 0 ? -a : a;
    int32_t vb = b < 0 ? -b : b;
    int32_t s = va >= vb ? a : b;
    s = (s * 3) / 2;
    if (s > 32767) s = 32767;
    if (s < -32768) s = -32768;
    capture[i] = (int16_t)s;
    capture[i + 1] = (int16_t)s;
  }

  i2s_zero_dma_buffer((i2s_port_t)AUDIO_I2S_PORT);
  delay(90);
  size_t played = 0;
  while (played < samples * sizeof(int16_t)) {
    size_t wrote = 0;
    size_t remaining = samples * sizeof(int16_t) - played;
    size_t ask = remaining > 1024 ? 1024 : remaining;
    if (i2s_write((i2s_port_t)AUDIO_I2S_PORT,
                  ((uint8_t*)capture) + played,
                  ask, &wrote, pdMS_TO_TICKS(60)) != ESP_OK) break;
    if (wrote == 0) break;
    played += wrote;
    yield();
  }
  free(capture);
  restartAudioTaskAfterDiagnostic();

  int level = (int)((peak * 100L) / 32767L);
  return constrain(level, 0, 100);
}
#elif defined(BOARD_HAS_MICROPHONE)
int buzzerBackendMicLevel(uint16_t) { return -1; }
int buzzerBackendMicEcho(uint16_t) { return -1; }
#endif

#endif // BOARD_HAS_ES8311_AUDIO
