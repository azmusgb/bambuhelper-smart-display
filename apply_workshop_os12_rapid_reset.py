#!/usr/bin/env python3
"""Make the triple-reset entry to Recovery Safe Mode work (12.1.1).

recovery_manager.cpp counted rapid resets in two RTC_DATA_ATTR variables.
Those are re-initialised on every reset except a deep-sleep wake, so after an
EN-button or USB reset the counter was always 1 and Safe Mode never started
(seen on the WS350: resets 4 s apart left safeMode false).

The count now lives in NVS (``bh_recovery/rapid``), which survives every kind
of reset. The counting rule is the host-tested pure policy in
``firmware/platform/recovery/rapid_reset_policy.hpp``: each boot adds one; a
boot that stays up for 15 s clears it; the third rapid boot in a row enters
Safe Mode and starts the count again.
"""
from __future__ import annotations

import argparse
import shutil
import sys as _sys
from pathlib import Path

_here = Path(__file__).resolve().parent
if str(_here) not in _sys.path:
    _sys.path.insert(0, str(_here))
from scripts.smart_home_patch_utils import PatchError  # noqa: E402

BUILD_MARKER = "#define WORKSHOP_OS12_RAPID_RESET_NVS 1"
POLICY_SOURCE = Path("firmware") / "platform" / "recovery" / "rapid_reset_policy.hpp"
POLICY_TARGET = Path("include") / "workshop_rapid_reset_policy.hpp"

OLD_INCLUDE = '#include <esp_partition.h>\n'
NEW_INCLUDE = '#include <esp_partition.h>\n#include "workshop_rapid_reset_policy.hpp"\n'

OLD_STATE = '''RTC_DATA_ATTR uint32_t sRapidMagic = 0;
RTC_DATA_ATTR uint8_t sRapidCount = 0;
'''
NEW_STATE = '''// Rapid-reset count for this boot. The persistent copy is NVS "rapid"; RTC
// memory is re-initialised on every non-deep-sleep reset and cannot hold it.
uint8_t sRapidCount = 0;
'''

OLD_PROBE = '''  if(sRapidMagic!=kRapidMagic){sRapidMagic=kRapidMagic;sRapidCount=0;}
  if(sRapidCount<250) ++sRapidCount;
  if(sRapidCount>=3){sSafeMode=true;sRapidCount=0;Serial.println("Recovery: triple reset -> Safe Mode");}
'''
NEW_PROBE = '''  {
    bool rapidSafe=false;
    prefs.begin(kNamespace,false);
    const uint8_t next=workshop::recovery::rapidResetOnBoot(prefs.getUChar("rapid",0),rapidSafe);
    prefs.putUChar("rapid",next);
    prefs.end();
    sRapidCount=rapidSafe?workshop::recovery::kRapidResetLimit:next;
    if(rapidSafe){sSafeMode=true;Serial.println("Recovery: triple reset -> Safe Mode");}
  }
'''

OLD_TICK = '''  if(!sRapidCleared && now>=kRapidClearMs){sRapidCount=0;sRapidCleared=true;}
'''
NEW_TICK = '''  if(workshop::recovery::rapidResetWindowClosed(now,sRapidCleared)){
    sRapidCount=0;sRapidCleared=true;
    prefs.begin(kNamespace,false);
    if(prefs.getUChar("rapid",0)!=0)prefs.putUChar("rapid",0);
    prefs.end();
  }
'''

OLD_CONSTANTS = '''constexpr uint32_t kRapidMagic = 0x52454334;
constexpr uint32_t kRapidClearMs = 15000;
'''
NEW_CONSTANTS = ''


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise PatchError(f"{label}: expected exactly one anchor, found {count}")
    return text.replace(old, new, 1)


def apply(repo: Path, source_root: Path) -> None:
    build_path = repo / "include" / "smart_home_build.h"
    if not build_path.is_file():
        raise PatchError(f"missing {build_path}")
    build = build_path.read_text(encoding="utf-8")
    if BUILD_MARKER in build:
        raise PatchError("rapid-reset fix is already applied")
    source = source_root / POLICY_SOURCE
    if not source.is_file():
        raise PatchError(f"missing {source}")
    path = repo / "src" / "recovery_manager.cpp"
    if not path.is_file():
        raise PatchError(f"missing {path}")
    text = path.read_text(encoding="utf-8")
    text = replace_once(text, OLD_INCLUDE, NEW_INCLUDE, "policy include")
    text = replace_once(text, OLD_CONSTANTS, NEW_CONSTANTS, "RTC magic constants")
    text = replace_once(text, OLD_STATE, NEW_STATE, "RTC rapid-reset state")
    text = replace_once(text, OLD_PROBE, NEW_PROBE, "boot probe")
    text = replace_once(text, OLD_TICK, NEW_TICK, "rapid window clear")
    target = repo / POLICY_TARGET
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)
    path.write_text(text, encoding="utf-8")
    build_path.write_text(build.rstrip() + "\n" + BUILD_MARKER + "\n", encoding="utf-8")
    print("Workshop OS triple-reset Safe Mode entry now counts in NVS")


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
