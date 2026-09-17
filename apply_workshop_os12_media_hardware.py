#!/usr/bin/env python3
"""Install the minimal proven audio hardware contract needed by OS12 Media.

This deliberately ports only the ES8311 volume plumbing from the historical
v11.24 Audio Console donor. It does not import the old console, LED, power, or
settings authority.
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
    settings_h = repo / "src/settings.h"
    settings_cpp = repo / "src/settings.cpp"
    backend_h = repo / "src/buzzer_backend.h"
    backend_cpp = repo / "src/buzzer_backend_es8311.cpp"

    sh = load(settings_h)
    if "uint8_t volume;" not in sh:
        sh = once(
            sh,
            "  bool bedCooldownAlert;          // play second alert when bed cools after print\n"
            "  uint8_t bedCooldownThresholdC;  // bed temperature threshold (20-80 C)\n};",
            "  bool bedCooldownAlert;          // play second alert when bed cools after print\n"
            "  uint8_t bedCooldownThresholdC;  // bed temperature threshold (20-80 C)\n"
            "  uint8_t volume;                 // ES8311 speaker output 0-100; ignored by GPIO buzzers\n};",
            "BuzzerSettings volume field",
        )
        settings_h.write_text(sh, encoding="utf-8")

    sc = load(settings_cpp)
    if 'prefs.getUChar("buz_vol"' not in sc:
        sc = once(
            sc,
            "  buzzerSettings.bedCooldownThresholdC = bct;\n",
            "  buzzerSettings.bedCooldownThresholdC = bct;\n"
            "  { uint8_t v=prefs.getUChar(\"buz_vol\",75); if(v>100)v=75; buzzerSettings.volume=v; }\n",
            "load speaker volume",
        )
    if 'prefs.putUChar("buz_vol"' not in sc:
        sc = once(
            sc,
            '  prefs.putUChar("buz_bed_c", buzzerSettings.bedCooldownThresholdC);\n  prefs.end();\n',
            '  prefs.putUChar("buz_bed_c", buzzerSettings.bedCooldownThresholdC);\n'
            '  prefs.putUChar("buz_vol", buzzerSettings.volume<=100?buzzerSettings.volume:75);\n'
            '  prefs.end();\n',
            "save speaker volume",
        )
    settings_cpp.write_text(sc, encoding="utf-8")

    bh = load(backend_h)
    if "buzzerBackendSetVolume" not in bh:
        bh = once(
            bh,
            "void buzzerBackendShutdown();\n",
            "void buzzerBackendShutdown();\n"
            "#if defined(BOARD_HAS_ES8311_AUDIO)\n"
            "void buzzerBackendSetVolume(uint8_t percent);\n"
            "#endif\n",
            "backend volume declaration",
        )
        backend_h.write_text(bh, encoding="utf-8")

    bc = load(backend_cpp)
    # Replace the fixed donor constant/codec initialization with persisted volume.
    bc = bc.replace(
        "constexpr uint8_t  kCodecVolume    = 75;            // percent\n",
        "",
        1,
    )
    fixed = (
        "  uint8_t vol = (kCodecVolume == 0) ? 0 : "
        "(uint8_t)(((kCodecVolume * 256) / 100) - 1);\n"
        "  if (!esWrite(ES_REG_DAC_32, vol)) return false;"
    )
    dynamic = (
        "  uint8_t pct = buzzerSettings.volume <= 100 ? buzzerSettings.volume : 75;\n"
        "  uint8_t vol = (pct == 0) ? 0 : (uint8_t)(((pct * 256U) / 100U) - 1U);\n"
        "  if (!esWrite(ES_REG_DAC_32, vol)) return false;"
    )
    if dynamic not in bc:
        if fixed not in bc:
            raise PatchError("dynamic ES8311 codec-volume anchor missing")
        bc = bc.replace(fixed, dynamic, 1)

    if "void buzzerBackendSetVolume(uint8_t percent)" not in bc:
        marker = "#endif // BOARD_HAS_ES8311_AUDIO"
        if bc.count(marker) != 1:
            raise PatchError("ES8311 backend endif missing/non-unique")
        implementation = r'''
void buzzerBackendSetVolume(uint8_t percent) {
  if (percent > 100U) percent = 100U;
  buzzerSettings.volume = percent;
  if (!gCodecReady) return;
  const uint8_t vol = (percent == 0U)
      ? 0U
      : (uint8_t)(((percent * 256U) / 100U) - 1U);
  esWrite(ES_REG_DAC_32, vol);
}

'''
        bc = bc.replace(marker, implementation + marker, 1)
    backend_cpp.write_text(bc, encoding="utf-8")

    # Grounding checks: the earlier audio stack must supply the actual speaker
    # and microphone primitives. Do not fabricate them here.
    final_h = load(backend_h)
    final_cpp = load(backend_cpp)
    for needle in ("buzzerBackendSetVolume", "buzzerBackendMicLevel"):
        if needle not in final_h:
            raise PatchError(f"audio backend contract missing {needle}")
    for needle in ("ES_REG_DAC_32", "buzzerBackendSetVolume"):
        if needle not in final_cpp:
            raise PatchError(f"ES8311 implementation missing {needle}")

    print("Workshop OS 12 media hardware contract installed")


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
        raise SystemExit(str(exc)) from exc
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
