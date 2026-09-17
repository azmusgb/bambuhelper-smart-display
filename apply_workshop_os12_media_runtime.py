#!/usr/bin/env python3
"""Install the Workshop OS 12 media runtime into reconstructed UI13 source."""
from __future__ import annotations

import argparse
import shutil
from pathlib import Path


class PatchError(RuntimeError):
    pass


MEDIA_HEADERS = (
    "media_service.h",
    "ws350_media_backend.h",
    "workshop_media_runtime.h",
)
MEDIA_SOURCES = (
    "media_service.cpp",
    "ws350_media_backend.cpp",
    "workshop_media_runtime.cpp",
)

INCLUDE_ANCHOR = '#include "workshop_platform_bridge.h"\n'
INCLUDE_LINE = '#include "workshop_media_runtime.h"\n'
BEGIN_ANCHOR = "    workshopPlatformBegin();\n"
POLL_ANCHOR = "  workshopPlatformPoll();\n"


def copy_exact(source: Path, destination: Path) -> None:
    if not source.is_file():
        raise PatchError(f"missing media source asset: {source}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if new in text:
        return text
    count = text.count(old)
    if count != 1:
        raise PatchError(f"{label}: expected one anchor, found {count}")
    return text.replace(old, new, 1)


def insert_once(text: str, anchor: str, addition: str, label: str) -> str:
    if addition.strip() in text:
        return text
    count = text.count(anchor)
    if count != 1:
        raise PatchError(f"{label}: expected one anchor, found {count}")
    return text.replace(anchor, anchor + addition, 1)


def insert_before_once(text: str, anchor: str, addition: str, label: str) -> str:
    if addition.strip() in text:
        return text
    count = text.count(anchor)
    if count != 1:
        raise PatchError(f"{label}: expected one anchor, found {count}")
    return text.replace(anchor, addition + anchor, 1)


def patch_audio_volume_contract(repo: Path) -> None:
    """Extend the existing ES8311 backend; never create a parallel audio path."""
    header_path = repo / "src" / "buzzer_backend.h"
    es8311_path = repo / "src" / "buzzer_backend_es8311.cpp"
    if not header_path.is_file() or not es8311_path.is_file():
        raise PatchError("reconstructed ES8311 audio backend is missing")

    header = header_path.read_text(encoding="utf-8")
    header = replace_once(
        header,
        "void buzzerBackendShutdown();\n",
        "void buzzerBackendSetVolume(uint8_t percent);\nvoid buzzerBackendShutdown();\n",
        "ES8311 volume API declaration",
    )
    header_path.write_text(header, encoding="utf-8")

    source = es8311_path.read_text(encoding="utf-8")
    source = replace_once(
        source,
        "constexpr uint8_t  kCodecVolume    = 75;            // percent\n",
        "constexpr uint8_t  kCodecVolume    = 75;            // percent\n"
        "volatile uint8_t gCodecVolumePercent = kCodecVolume;\n",
        "ES8311 mutable volume state",
    )
    source = replace_once(
        source,
        "  uint8_t vol = (kCodecVolume == 0) ? 0 : (uint8_t)(((kCodecVolume * 256) / 100) - 1);\n",
        "  const uint8_t requestedVolume = gCodecVolumePercent;\n"
        "  uint8_t vol = (requestedVolume == 0) ? 0 : (uint8_t)(((requestedVolume * 256) / 100) - 1);\n",
        "ES8311 startup volume",
    )

    volume_function = """void buzzerBackendSetVolume(uint8_t percent) {
  if (percent > 100U) percent = 100U;
  gCodecVolumePercent = percent;
  if (!gCodecReady) return;

  const uint8_t vol = (percent == 0U)
      ? 0U
      : (uint8_t)(((uint16_t)percent * 256U) / 100U - 1U);
  esWrite(ES_REG_DAC_32, vol);
}

"""
    source = insert_before_once(
        source,
        "void buzzerBackendShutdown() {\n",
        volume_function,
        "ES8311 runtime volume implementation",
    )
    es8311_path.write_text(source, encoding="utf-8")

    # Validate header and implementation independently. Do not infer the target
    # file from punctuation: source declarations and definitions can both end
    # in semicolons internally, which previously caused a false CI failure.
    if "void buzzerBackendSetVolume(uint8_t percent);" not in header:
        raise PatchError("ES8311 volume API declaration missing after patch")
    for needle in (
        "volatile uint8_t gCodecVolumePercent = kCodecVolume;",
        "const uint8_t requestedVolume = gCodecVolumePercent;",
        "void buzzerBackendSetVolume(uint8_t percent)",
        "gCodecVolumePercent = percent;",
        "esWrite(ES_REG_DAC_32, vol);",
    ):
        if needle not in source:
            raise PatchError(f"ES8311 volume implementation missing after patch: {needle}")


def apply(repo: Path, source_root: Path) -> None:
    main_cpp = repo / "src" / "main.cpp"
    build_h = repo / "include" / "smart_home_build.h"
    buzzer_h = repo / "src" / "buzzer_backend.h"
    if not main_cpp.is_file() or not build_h.is_file() or not buzzer_h.is_file():
        raise PatchError("OS12 media runtime requires reconstructed firmware source")

    build_text = build_h.read_text(encoding="utf-8")
    if "WORKSHOP_OS_RELEASE_VERSION" not in build_text:
        raise PatchError("OS12 media runtime must be applied after release identity")

    # Extend the existing proven ES8311 backend with one narrow runtime-volume
    # contract. This keeps audio authority in buzzer_backend_es8311.cpp instead
    # of creating a second codec implementation inside MediaService.
    patch_audio_volume_contract(repo)

    media_root = source_root / "firmware" / "platform" / "media"
    for name in MEDIA_HEADERS:
        copy_exact(media_root / name, repo / "include" / name)
    for name in MEDIA_SOURCES:
        copy_exact(media_root / name, repo / "src" / name)

    text = main_cpp.read_text(encoding="utf-8")
    text = insert_once(text, INCLUDE_ANCHOR, INCLUDE_LINE, "media runtime include")
    text = insert_once(text, BEGIN_ANCHOR, "    workshopMediaBegin();\n", "media begin")
    text = insert_once(text, POLL_ANCHOR, "  workshopMediaPoll();\n", "media poll")
    main_cpp.write_text(text, encoding="utf-8")

    if text.count("workshopMediaBegin();") != 1:
        raise PatchError("workshopMediaBegin must be injected exactly once")
    if text.count("workshopMediaPoll();") != 1:
        raise PatchError("workshopMediaPoll must be injected exactly once")

    print("Workshop OS 12 media runtime installed")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True)
    parser.add_argument("--source-root", default=str(Path(__file__).resolve().parent))
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    if not args.apply:
        raise SystemExit("refusing to modify source without --apply")
    try:
        apply(Path(args.repo).resolve(), Path(args.source_root).resolve())
    except PatchError as exc:
        raise SystemExit(str(exc)) from exc
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
