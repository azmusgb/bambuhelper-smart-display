#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path


def require(path: Path, needles: tuple[str, ...]) -> str:
    if not path.is_file():
        raise SystemExit(f"FAIL: missing {path}")
    text = path.read_text(encoding="utf-8")
    for needle in needles:
        if needle not in text:
            raise SystemExit(f"FAIL: {path}: missing {needle!r}")
    return text


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    args = ap.parse_args()
    repo = Path(args.repo).resolve()

    es = require(
        repo / "src/buzzer_backend_es8311.cpp",
        (
            "ES_REG_SYS_14 = 0x14",
            "ES_REG_ADC_17 = 0x17",
            "esWrite(ES_REG_SYS_14, 0x1A)",
            "esWrite(ES_REG_ADC_17, 0xC8)",
            "analog mic route=0x%02X adc_gain=0x%02X",
            "OS12 mic raw: bytes=%u samples=%u nonzero=%u min=%d max=%d peak=%ld",
            "totalBytes += bytesRead",
            "nonZeroSamples",
            "minSample",
            "maxSample",
        ),
    )
    require(repo / "src/media_service.cpp", ("speakerTestEndsAtMs_ = nowMs + 750U",))
    backend = require(
        repo / "src/ws350_media_backend.cpp",
        (
            "caps.videoDecoderAvailable = caps.psramAvailable && cameraCanStreamDisplayedPrinter()",
            "OS12 media video: rejected PSRAM unavailable",
            "OS12 media video: rejected displayed-printer camera unavailable",
            "OS12 media video: rejected camera transport did not become active",
            "OS12 media video: displayed-printer camera active",
        ),
    )

    route = es.find("esWrite(ES_REG_SYS_14, 0x1A)")
    gain = es.find("esWrite(ES_REG_ADC_17, 0xC8)")
    adc = es.find("esWrite(ES_REG_ADC_1C, 0x6A)")
    if route < 0 or gain < 0 or adc < 0 or not (route < gain < adc):
        raise SystemExit("FAIL: analog mic route/gain must be configured before existing ADC setup")

    if "esWrite(ES_REG_SYS_14, 0x5A)" in es:
        raise SystemExit("FAIL: DMIC bit must remain clear for the WS350 analog microphone")

    if "caps.videoDecoderAvailable = caps.psramAvailable;" in backend:
        raise SystemExit("FAIL: WS350 must not advertise video from JPEG decoder presence alone")

    print(
        "PASS: OS12 WS350 analog microphone route/gain, raw RX diagnostics, audible speaker window, "
        "and displayed-printer camera capability truth are present"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
