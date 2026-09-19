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

    require(repo / "src/settings.h", ("uint8_t volume;",))
    require(
        repo / "boards/ws_lcd_350.ini",
        (
            "-D BOARD_HAS_ES8311_AUDIO=1",
            "-D BOARD_HAS_MICROPHONE=1",
            "-D AUDIO_I2C_ADDR=0x18",
            "-D AUDIO_I2C_SDA=8",
            "-D AUDIO_I2C_SCL=7",
            "-D AUDIO_I2S_MCLK=12",
            "-D AUDIO_I2S_BCLK=13",
            "-D AUDIO_I2S_LRC=15",
            "-D AUDIO_I2S_DIN=14",
            "-D AUDIO_I2S_DOUT=16",
            "-D AUDIO_PA_CTRL=-1",
        ),
    )
    require(
        repo / "src/settings.cpp",
        ('getUChar("buz_vol"', 'putUChar("buz_vol"'),
    )
    require(
        repo / "src/buzzer_backend.h",
        ("buzzerBackendSetVolume", "buzzerBackendMicLevel"),
    )
    cpp = require(
        repo / "src/buzzer_backend_es8311.cpp",
        ("ES_REG_DAC_32", "buzzerBackendSetVolume", "buzzerSettings.volume"),
    )
    if "kCodecVolume" in cpp:
        raise SystemExit("FAIL: fixed ES8311 volume constant still active")

    print("PASS: OS12 media hardware reuses ES8311/microphone primitives with persisted volume")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
