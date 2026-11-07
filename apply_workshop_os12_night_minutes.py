#!/usr/bin/env python3
"""Keep the night-mode schedule in minutes, in 15-minute steps (display-kit K9; rollout step 5, PR 1).

The reconstructed source stores the night-mode window as whole hours (DisplayPowerSettings::nightStartHour and
nightEndHour, NVS dp_nstart and dp_nend, 24 portal options). The kit says a time is chosen from a Picker of times in
15-minute steps, so the window is kept as minutes after midnight:

- firmware/platform/ui/night_time.hpp (the migration, the night test, the 96 options, the label, the portal's inputs;
  host-tested by tests/workshop_os12_night_time_smoke.cpp) is installed as include/workshop_night_time.hpp;
- settings.h: nightStartHour / nightEndHour become uint16_t nightStartMin / nightEndMin;
- settings.cpp: the schedule is read from dp_nstartm / dp_nendm; a device that only has the old whole-hour keys keeps its
  schedule (hour h becomes h * 60); both forms are written (the minutes, and the hour they fall in), so a downgrade
  still finds its schedule;
- display_ui.cpp: the night test compares minutes of the day, so 22:15 to 07:00 starts at 22:15 and ends at 07:00;
- the portal: the Display page's two times list the 96 options (value: the minutes) and post nstartm / nendm; /apply
  still reads nstart / nend as hours (a portal page loaded before the update), and the settings export carries
  nightStartMin / nightEndMin while a restore still reads nightStartHour / nightEndHour from an older export.

The touchscreen half (the Picker's option list and its setters, the row labels) is in
firmware/platform/ui/more_pages.cppfrag, which this tree already includes. Runs after the X2D overlays, on the
finished tree: it edits only the lines below, and refuses a tree where one is missing.
"""
from __future__ import annotations

import argparse
import shutil
import sys as _sys
from pathlib import Path as _Path
from pathlib import Path

_here = _Path(__file__).resolve().parent
if str(_here) not in _sys.path:
    _sys.path.insert(0, str(_here))

from scripts.smart_home_patch_utils import PatchError, replace_once

HEADER_SOURCE = Path("firmware") / "platform" / "ui" / "night_time.hpp"
HEADER_TARGET = Path("include") / "workshop_night_time.hpp"
INCLUDE = '#include "workshop_night_time.hpp"\n'

SETTINGS_H_OLD = """  uint8_t nightStartHour;      // dim start hour (0-23)
  uint8_t nightEndHour;        // dim end hour (0-23)
"""
SETTINGS_H_NEW = """  uint16_t nightStartMin;      // dim start, minutes after midnight (0-1425, 15-minute steps)
  uint16_t nightEndMin;        // dim end, minutes after midnight (0-1425, 15-minute steps)
"""

LOAD_OLD = """  dpSettings.nightStartHour = prefs.getUChar("dp_nstart", 22);
  dpSettings.nightEndHour = prefs.getUChar("dp_nend", 7);
"""
LOAD_NEW = """  // Night schedule: minutes after midnight (dp_nstartm / dp_nendm). A device that was saved before the schedule had
  // minutes only has the whole-hour keys; its hour h becomes h * 60 and is written back as minutes on the next save.
  dpSettings.nightStartMin = wnight::resolveStored(prefs.isKey("dp_nstartm"), prefs.getUShort("dp_nstartm", 0),
                                                   prefs.getUChar("dp_nstart", 255), wnight::kDefaultStart);
  dpSettings.nightEndMin = wnight::resolveStored(prefs.isKey("dp_nendm"), prefs.getUShort("dp_nendm", 0),
                                                 prefs.getUChar("dp_nend", 255), wnight::kDefaultEnd);
"""
SAVE_OLD = """  prefs.putUChar("dp_nstart", dpSettings.nightStartHour);
  prefs.putUChar("dp_nend", dpSettings.nightEndHour);
"""
SAVE_NEW = """  prefs.putUShort("dp_nstartm", dpSettings.nightStartMin);
  prefs.putUShort("dp_nendm", dpSettings.nightEndMin);
  prefs.putUChar("dp_nstart", (uint8_t)(dpSettings.nightStartMin / 60U));  // the hour it falls in, for a downgrade
  prefs.putUChar("dp_nend", (uint8_t)(dpSettings.nightEndMin / 60U));
"""

NIGHT_OLD = """  uint8_t h = now.tm_hour;
  uint8_t s = dpSettings.nightStartHour;
  uint8_t e = dpSettings.nightEndHour;

  if (s == e) return false;  // same hour = disabled
  if (s < e) return (h >= s && h < e);     // e.g. 01:00-07:00
  return (h >= s || h < e);                // e.g. 22:00-07:00 (wraps midnight)
}
"""
NIGHT_NEW = """  // Minutes of the day against the schedule: 22:15-07:00 starts at 22:15 and ends at 07:00; equal times are off.
  return wnight::isNight((unsigned)now.tm_hour * 60U + (unsigned)now.tm_min, dpSettings.nightStartMin, dpSettings.nightEndMin);
}
"""

FORM_OLD = """  if (server.hasArg("nstart")) dpSettings.nightStartHour = server.arg("nstart").toInt();
  if (server.hasArg("nend"))   dpSettings.nightEndHour = server.arg("nend").toInt();
"""
FORM_NEW = """  {
    // nstartm / nendm: minutes after midnight in 15-minute steps. nstart / nend: whole hours, from a portal page that was
    // loaded before this firmware. A value that is not a valid time leaves the schedule as it was.
    const String nsm = server.arg("nstartm"), nsh = server.arg("nstart");
    const String nem = server.arg("nendm"), neh = server.arg("nend");
    wnight::importTimeText(server.hasArg("nstartm") ? nsm.c_str() : nullptr, server.hasArg("nstart") ? nsh.c_str() : nullptr,
                           dpSettings.nightStartMin);
    wnight::importTimeText(server.hasArg("nendm") ? nem.c_str() : nullptr, server.hasArg("nend") ? neh.c_str() : nullptr,
                           dpSettings.nightEndMin);
  }
"""
EXPORT_OLD = """  dp["nightStartHour"] = dpSettings.nightStartHour;
  dp["nightEndHour"] = dpSettings.nightEndHour;
"""
EXPORT_NEW = """  dp["nightStartMin"] = dpSettings.nightStartMin;
  dp["nightEndMin"] = dpSettings.nightEndMin;
"""
RESTORE_OLD = """    if (dp["nightStartHour"].is<uint8_t>())     dpSettings.nightStartHour = dp["nightStartHour"].as<uint8_t>();
    if (dp["nightEndHour"].is<uint8_t>())       dpSettings.nightEndHour = dp["nightEndHour"].as<uint8_t>();
"""
RESTORE_NEW = """    // Minutes; an export from before the schedule had minutes carries whole hours instead (read as h * 60).
    wnight::importTime(dp["nightStartMin"].is<int>(), dp["nightStartMin"].as<long>(), dp["nightStartHour"].is<int>(),
                       dp["nightStartHour"].as<long>(), dpSettings.nightStartMin);
    wnight::importTime(dp["nightEndMin"].is<int>(), dp["nightEndMin"].as<long>(), dp["nightEndHour"].is<int>(),
                       dp["nightEndHour"].as<long>(), dpSettings.nightEndMin);
"""

TEMPLATE_START_OLD = """    for (uint8_t h = 0; h < 24; h++) {
      char opt[64];
      snprintf(opt, sizeof(opt), "<option value=\\"%d\\"%s>%02d:00</option>",
               h, h == dpSettings.nightStartHour ? " selected" : "", h);
      out += opt;
    }
"""
TEMPLATE_START_NEW = """    for (int i = 0; i < wnight::kOptionCount; i++) {
      char label[16], opt[80];
      const uint16_t minutes = (uint16_t)wnight::minutesOf(i);
      wnight::format(label, sizeof(label), minutes, netSettings.use24h);
      snprintf(opt, sizeof(opt), "<option value=\\"%u\\"%s>%s</option>",
               (unsigned)minutes, minutes == dpSettings.nightStartMin ? " selected" : "", label);
      out += opt;
    }
"""
TEMPLATE_END_OLD = TEMPLATE_START_OLD.replace("nightStartHour", "nightEndHour")
TEMPLATE_END_NEW = TEMPLATE_START_NEW.replace("nightStartMin", "nightEndMin")

APP_JS_OLD = """  p.append('nstart', document.getElementById('nstart').value);
  p.append('nend', document.getElementById('nend').value);
"""
APP_JS_NEW = """  p.append('nstartm', document.getElementById('nstart').value);
  p.append('nendm', document.getElementById('nend').value);
"""
PAGES_COMMENT_OLD = "//    Display:  bright, nighten, nstart, nend, nbright,"
PAGES_COMMENT_NEW = "//    Display:  bright, nighten, nstartm, nendm, nbright,"


def read(path: Path) -> str:
    if not path.is_file():
        raise PatchError(f"missing reconstructed source: {path}")
    return path.read_text(encoding="utf-8")


def add_include(text: str, after: str, label: str) -> str:
    return replace_once(text, after, after + INCLUDE, label)


def patch_all(repo: Path, source_root: Path) -> dict[Path, str]:
    """Every file's new text, staged in memory: nothing is written unless every anchor matched."""
    out: dict[Path, str] = {}

    settings_h = read(repo / "src/settings.h")
    out[repo / "src/settings.h"] = replace_once(settings_h, SETTINGS_H_OLD, SETTINGS_H_NEW, "settings.h night fields")

    settings_cpp = read(repo / "src/settings.cpp")
    settings_cpp = add_include(settings_cpp, '#include "settings.h"\n', "settings.cpp include")
    settings_cpp = replace_once(settings_cpp, LOAD_OLD, LOAD_NEW, "settings.cpp load")
    settings_cpp = replace_once(settings_cpp, SAVE_OLD, SAVE_NEW, "settings.cpp save")
    out[repo / "src/settings.cpp"] = settings_cpp

    display_ui = read(repo / "src/display_ui.cpp")
    display_ui = add_include(display_ui, '#include "smart_home_build.h"\n', "display_ui.cpp include")
    display_ui = replace_once(display_ui, NIGHT_OLD, NIGHT_NEW, "display_ui.cpp night test")
    display_ui = display_ui.replace("isNightHour", "isNightNow")
    out[repo / "src/display_ui.cpp"] = display_ui

    web_server = read(repo / "src/web_server.cpp")
    web_server = add_include(web_server, '#include "workshop_localai_feed.h"\n', "web_server.cpp include")
    web_server = replace_once(web_server, FORM_OLD, FORM_NEW, "web_server.cpp form")
    web_server = replace_once(web_server, EXPORT_OLD, EXPORT_NEW, "web_server.cpp export")
    web_server = replace_once(web_server, RESTORE_OLD, RESTORE_NEW, "web_server.cpp restore")
    out[repo / "src/web_server.cpp"] = web_server

    web_template = read(repo / "src/web_template.cpp")
    web_template = add_include(web_template, '#include "web_template.h"\n', "web_template.cpp include")
    web_template = replace_once(web_template, TEMPLATE_START_OLD, TEMPLATE_START_NEW, "web_template.cpp start options")
    web_template = replace_once(web_template, TEMPLATE_END_OLD, TEMPLATE_END_NEW, "web_template.cpp end options")
    out[repo / "src/web_template.cpp"] = web_template

    app_js = read(repo / "web/app.js")
    out[repo / "web/app.js"] = replace_once(app_js, APP_JS_OLD, APP_JS_NEW, "app.js display form")

    pages = read(repo / "include/web_pages.h")
    out[repo / "include/web_pages.h"] = replace_once(pages, PAGES_COMMENT_OLD, PAGES_COMMENT_NEW, "web_pages.h key list")

    hub = read(repo / "src/smart_hub.cpp")
    out[repo / "src/smart_hub.cpp"] = add_include(hub, '#include "workshop_lgfx_canvas.hpp"\n', "smart_hub.cpp include")

    header = source_root / HEADER_SOURCE
    if not header.is_file():
        raise PatchError(f"missing {header}")
    return out


def apply(repo: Path, source_root: Path) -> None:
    staged = patch_all(repo, source_root)
    for path, text in staged.items():
        path.write_text(text, encoding="utf-8")
    shutil.copyfile(source_root / HEADER_SOURCE, repo / HEADER_TARGET)
    print("Workshop OS 12 night-mode times installed: minutes in 15-minute steps, hour migration, portal and export")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True)
    parser.add_argument("--source-root", required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    if not args.apply:
        raise SystemExit("refusing to modify reconstructed source without --apply")
    try:
        apply(Path(args.repo).resolve(), Path(args.source_root).resolve())
    except PatchError as exc:
        raise SystemExit(f"FAIL: {exc}") from exc
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
