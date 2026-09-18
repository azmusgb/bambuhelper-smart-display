#!/usr/bin/env python3
"""Apply evidence-backed WS350 media signal-path hardening after OS12 media runtime reconstruction.

This patch does not create a second audio authority. It augments the existing
ES8311 backend with the Waveshare analog-microphone route/gain registers and
adds bounded diagnostics that make physical acceptance failures observable.
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path


class PatchError(RuntimeError):
    pass


def load(path: Path) -> str:
    if not path.is_file():
        raise PatchError(f"missing reconstructed source: {path}")
    return path.read_text(encoding="utf-8")


def once(text: str, old: str, new: str, label: str) -> str:
    if new in text:
        return text
    count = text.count(old)
    if count != 1:
        raise PatchError(f"{label}: expected one anchor, found {count}")
    return text.replace(old, new, 1)


def apply(repo: Path) -> None:
    header_path = repo / "src/buzzer_backend.h"
    es_path = repo / "src/buzzer_backend_es8311.cpp"
    media_path = repo / "src/media_service.cpp"

    header = load(header_path)
    es = load(es_path)
    media = load(media_path)

    diagnostics_decl = """bool buzzerBackendCodecReady();
bool buzzerBackendI2sReady();
bool buzzerBackendAudioRunning();
uint32_t buzzerBackendMicLastBytes();
uint32_t buzzerBackendMicLastSamples();
uint32_t buzzerBackendMicLastNonZeroSamples();
uint32_t buzzerBackendMicLastPeak();
uint32_t buzzerBackendAudioLastWriteBytes();
uint32_t buzzerBackendAudioLastPeak();
uint16_t buzzerBackendAudioCurrentFrequency();
"""
    if "buzzerBackendCodecReady" not in header:
        header = once(
            header,
            "int buzzerBackendMicLevel(uint16_t sampleMs);\n",
            "int buzzerBackendMicLevel(uint16_t sampleMs);\n" + diagnostics_decl,
            "ES8311 media diagnostic declarations",
        )

    if "gOs12MicLastPeak" not in es:
        es = once(
            es,
            "bool     gAmpEnabled  = false;\n",
            "bool     gAmpEnabled  = false;\n"
            "uint32_t gOs12MicLastBytes = 0;\n"
            "uint32_t gOs12MicLastSamples = 0;\n"
            "uint32_t gOs12MicLastNonZeroSamples = 0;\n"
            "uint32_t gOs12MicLastPeak = 0;\n"
            "uint32_t gOs12AudioLastWriteBytes = 0;\n"
            "uint32_t gOs12AudioLastPeak = 0;\n",
            "ES8311 media diagnostic state",
        )

    es = once(
        es,
        "constexpr uint8_t ES_REG_SYS_13 = 0x13;\n",
        "constexpr uint8_t ES_REG_SYS_13 = 0x13;\n"
        "constexpr uint8_t ES_REG_SYS_14 = 0x14;\n"
        "constexpr uint8_t ES_REG_ADC_17 = 0x17;\n",
        "ES8311 analog-mic register declarations",
    )

    mic_route = """  if (!esWrite(ES_REG_SYS_13, 0x10)) return false;

  // WS350 onboard microphone is analog. Waveshare's ES8311 reference config
  // enables the analog MIC path with maximum PGA gain and programs ADC gain.
  // DMIC bit 6 remains clear intentionally; do not silently select digital MIC.
  if (!esWrite(ES_REG_SYS_14, 0x1A)) return false;
  if (!esWrite(ES_REG_ADC_17, 0xC8)) return false;

  uint8_t os12MicRoute = 0;
  uint8_t os12AdcGain = 0;
  if (!esRead(ES_REG_SYS_14, os12MicRoute) || !esRead(ES_REG_ADC_17, os12AdcGain)) return false;
  Serial.printf("ES8311: analog mic route=0x%02X adc_gain=0x%02X\\n", os12MicRoute, os12AdcGain);
"""
    es = once(
        es,
        "  if (!esWrite(ES_REG_SYS_13, 0x10)) return false;\n",
        mic_route,
        "ES8311 analog-mic route/gain",
    )

    if "gOs12AudioLastWriteBytes = (uint32_t)written;" not in es:
        pattern = re.compile(
            r"(fillChunk\(chunk\);\s*)"
            r"(size_t\s+written\s*=\s*0;\s*)"
            r"(i2s_write\(\(i2s_port_t\)AUDIO_I2S_PORT,\s*chunk,\s*sizeof\(chunk\),\s*"
            r"&written,\s*pdMS_TO_TICKS\(50\)\);)"
        )
        match = pattern.search(es)
        if not match:
            raise PatchError("ES8311 speaker TX diagnostics: audio task write anchor missing")
        instrumented = (
            match.group(1)
            + "uint32_t peak = 0;\n"
            + "    for (size_t i = 0; i < kChunkSamples; ++i) {\n"
            + "      int32_t v = chunk[i];\n"
            + "      if (v < 0) v = -v;\n"
            + "      if ((uint32_t)v > peak) peak = (uint32_t)v;\n"
            + "    }\n"
            + "    "
            + match.group(2)
            + match.group(3)
            + "\n    gOs12AudioLastWriteBytes = (uint32_t)written;"
            + "\n    gOs12AudioLastPeak = peak;"
        )
        es = es[:match.start()] + instrumented + es[match.end():]

    mic_meter_old = """  int16_t samples[128];
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
"""
    mic_meter_new = """  int16_t samples[128];
  int32_t peak = 0;
  int16_t minSample = INT16_MAX;
  int16_t maxSample = INT16_MIN;
  size_t totalBytes = 0;
  uint32_t nonZeroSamples = 0;
  uint32_t totalSamples = 0;
  uint32_t deadline = millis() + sampleMs;
  do {
    size_t bytesRead = 0;
    if (i2s_read((i2s_port_t)AUDIO_I2S_PORT, samples, sizeof(samples),
                 &bytesRead, pdMS_TO_TICKS(25)) != ESP_OK) return -1;
    totalBytes += bytesRead;
    size_t count = bytesRead / sizeof(samples[0]);
    totalSamples += (uint32_t)count;
    for (size_t i = 0; i < count; ++i) {
      const int16_t sample = samples[i];
      if (sample != 0) ++nonZeroSamples;
      if (sample < minSample) minSample = sample;
      if (sample > maxSample) maxSample = sample;
      int32_t v = sample;
      if (v < 0) v = -v;
      if (v > peak) peak = v;
    }
    yield();
  } while ((int32_t)(deadline - millis()) > 0);

  if (totalSamples == 0) {
    minSample = 0;
    maxSample = 0;
  }
  gOs12MicLastBytes = (uint32_t)totalBytes;
  gOs12MicLastSamples = totalSamples;
  gOs12MicLastNonZeroSamples = nonZeroSamples;
  gOs12MicLastPeak = (uint32_t)peak;
  Serial.printf(
      "OS12 mic raw: bytes=%u samples=%u nonzero=%u min=%d max=%d peak=%ld\\n",
      (unsigned)totalBytes,
      (unsigned)totalSamples,
      (unsigned)nonZeroSamples,
      (int)minSample,
      (int)maxSample,
      (long)peak);

  if (gTargetGain == 0 && gCurrentGain == 0) gIdleStartMs = millis();
  // Map -60 dBFS..0 dBFS to 0..100 for a human-scale activity meter.
  // Raw peak remains authoritative diagnostic evidence.
  int level = 0;
  if (peak > 0) {
    const float dbfs = 20.0f * log10f((float)peak / 32767.0f);
    level = (int)lroundf(((dbfs + 60.0f) * 100.0f) / 60.0f);
  }
  return constrain(level, 0, 100);
"""
    es = once(es, mic_meter_old, mic_meter_new, "ES8311 raw microphone diagnostics")

    media = once(
        media,
        "  speakerTestEndsAtMs_ = nowMs + 180U;\n",
        "  speakerTestEndsAtMs_ = nowMs + 750U;\n",
        "physical speaker diagnostic duration",
    )

    diagnostics_impl = r'''
bool buzzerBackendCodecReady() { return gCodecReady; }
bool buzzerBackendI2sReady() { return gI2sReady; }
bool buzzerBackendAudioRunning() { return gAudioState == AUDIO_RUNNING; }
uint32_t buzzerBackendMicLastBytes() { return gOs12MicLastBytes; }
uint32_t buzzerBackendMicLastSamples() { return gOs12MicLastSamples; }
uint32_t buzzerBackendMicLastNonZeroSamples() { return gOs12MicLastNonZeroSamples; }
uint32_t buzzerBackendMicLastPeak() { return gOs12MicLastPeak; }
uint32_t buzzerBackendAudioLastWriteBytes() { return gOs12AudioLastWriteBytes; }
uint32_t buzzerBackendAudioLastPeak() { return gOs12AudioLastPeak; }
uint16_t buzzerBackendAudioCurrentFrequency() { return gCurrentFreq; }

'''
    if "bool buzzerBackendCodecReady()" not in es:
        marker = "#endif // BOARD_HAS_ES8311_AUDIO"
        if es.count(marker) != 1:
            raise PatchError("ES8311 backend endif missing/non-unique for diagnostics")
        es = es.replace(marker, diagnostics_impl + marker, 1)

    header_path.write_text(header, encoding="utf-8")
    es_path.write_text(es, encoding="utf-8")
    media_path.write_text(media, encoding="utf-8")

    for needle in (
        "buzzerBackendCodecReady",
        "buzzerBackendI2sReady",
        "buzzerBackendAudioRunning",
        "buzzerBackendMicLastBytes",
        "buzzerBackendMicLastSamples",
        "buzzerBackendMicLastNonZeroSamples",
        "buzzerBackendMicLastPeak",
        "buzzerBackendAudioLastWriteBytes",
        "buzzerBackendAudioLastPeak",
        "buzzerBackendAudioCurrentFrequency",
    ):
        if needle not in header or needle not in es:
            raise PatchError(f"media diagnostic contract missing {needle}")

    print("Workshop OS 12 media signal-path hardening installed")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    if not args.apply:
        raise SystemExit("refusing to modify source without --apply")
    try:
        apply(Path(args.repo).resolve())
    except PatchError as exc:
        raise SystemExit(f"FAIL: {exc}") from exc
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
