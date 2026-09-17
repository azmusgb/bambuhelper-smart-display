#!/usr/bin/env python3
"""Apply evidence-backed WS350 media signal-path hardening after OS12 media runtime reconstruction.

This patch does not create a second audio authority. It augments the existing
ES8311 backend with the Waveshare analog-microphone route/gain registers and
adds bounded diagnostics that make physical acceptance failures observable.
"""
from __future__ import annotations

import argparse
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
    es_path = repo / "src/buzzer_backend_es8311.cpp"
    media_path = repo / "src/media_service.cpp"
    backend_path = repo / "src/ws350_media_backend.cpp"

    es = load(es_path)
    media = load(media_path)
    backend = load(backend_path)

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
  Serial.printf(
      "OS12 mic raw: bytes=%u samples=%u nonzero=%u min=%d max=%d peak=%ld\\n",
      (unsigned)totalBytes,
      (unsigned)totalSamples,
      (unsigned)nonZeroSamples,
      (int)minSample,
      (int)maxSample,
      (long)peak);

  if (gTargetGain == 0 && gCurrentGain == 0) gIdleStartMs = millis();
  int level = (int)((peak * 100L) / 32767L);
  return constrain(level, 0, 100);
"""
    es = once(es, mic_meter_old, mic_meter_new, "ES8311 raw microphone diagnostics")

    media = once(
        media,
        "  speakerTestEndsAtMs_ = nowMs + 180U;\n",
        "  speakerTestEndsAtMs_ = nowMs + 750U;\n",
        "physical speaker diagnostic duration",
    )

    video_old = """  if (!source || std::strcmp(source, kPrinterCameraSource) != 0) return false;
  if (!psramFound() || !cameraCanStreamDisplayedPrinter()) return false;

  // The existing camera client remains the sole network authority. It already
  // bounds input to two 200 KB PSRAM JPEG buffers and publishes only complete
  // SOI..EOI frames. MediaService owns only playback lifecycle and pacing.
  cameraBegin();
  if (!cameraActive()) return false;
"""
    video_new = """  if (!source || std::strcmp(source, kPrinterCameraSource) != 0) {
    Serial.println("OS12 media video: rejected invalid fixed source");
    return false;
  }
  if (!psramFound()) {
    Serial.println("OS12 media video: rejected PSRAM unavailable");
    return false;
  }
  if (!cameraCanStreamDisplayedPrinter()) {
    Serial.println("OS12 media video: rejected displayed-printer camera unavailable");
    return false;
  }

  // The existing camera client remains the sole network authority. It already
  // bounds input to two 200 KB PSRAM JPEG buffers and publishes only complete
  // SOI..EOI frames. MediaService owns only playback lifecycle and pacing.
  cameraBegin();
  if (!cameraActive()) {
    Serial.println("OS12 media video: rejected camera transport did not become active");
    return false;
  }
  Serial.println("OS12 media video: displayed-printer camera active");
"""
    backend = once(backend, video_old, video_new, "video startup diagnostics")

    es_path.write_text(es, encoding="utf-8")
    media_path.write_text(media, encoding="utf-8")
    backend_path.write_text(backend, encoding="utf-8")

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
