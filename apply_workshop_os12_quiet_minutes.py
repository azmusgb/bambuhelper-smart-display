#!/usr/bin/env python3
"""Quiet hours get an explicit Off and times in 15-minute steps (display-kit K9; rollout step 5).

The reconstructed source keeps quiet hours as two whole hours (BuzzerSettings::quietStartHour / quietEndHour, NVS
buz_qstart / buz_qend) and treats equal hours as off. The portal said "0-0 = off" and the touchscreen showed "Off" for a
start of 0 although 00:00 to 07:00 was a working window. The kit's Picker lists "Off" and then the times, so:

- BuzzerSettings keeps quietEnabled, quietStartMin and quietEndMin (NVS buz_qon, buz_qsm, buz_qem); the times are kept
  while it is off. A device with only the old hour keys migrates as it behaved: on exactly when the two hours differed.
  The hours are still written (the hour the time falls in; 0 and 0 when off) so a downgrade finds something sensible;
- buzzerIsQuietHour() tests the minute of the day (equal times still hold nothing);
- the portal: the Sound card's two fields are lists (Quiet from: Off and the 96 times, Quiet until: the 96 times) and
  post buzqon / buzqsm / buzqem; the Workshop experience card posts quietOn / quietStartMin / quietEndMin; both still read
  the old whole-hour fields (buzqs / buzqe, quietStart / quietEnd) from a page loaded before the update. The settings
  export carries quietEnabled / quietStartMin / quietEndMin and a restore reads an older export's hours.

Needs apply_workshop_os12_night_minutes.py first (the header it installs, include/workshop_night_time.hpp, holds the
rules). The Picker half is in firmware/platform/ui/more_pages.cppfrag.
"""
from __future__ import annotations

import argparse
import sys as _sys
from pathlib import Path as _Path
from pathlib import Path

_here = _Path(__file__).resolve().parent
if str(_here) not in _sys.path:
    _sys.path.insert(0, str(_here))

from scripts.smart_home_patch_utils import PatchError, replace_once

INCLUDE = '#include "workshop_night_time.hpp"\n'

SETTINGS_H_OLD = """  uint8_t quietStartHour;   // quiet hours start (0-23), 0 = disabled
  uint8_t quietEndHour;     // quiet hours end (0-23)
"""
SETTINGS_H_NEW = """  bool quietEnabled;        // quiet hours on; the times below are kept while it is off
  uint16_t quietStartMin;   // quiet hours start, minutes after midnight (0-1425, 15-minute steps)
  uint16_t quietEndMin;     // quiet hours end, minutes after midnight (0-1425, 15-minute steps)
"""
INIT_OLD = "BuzzerSettings buzzerSettings = { false, BUZZER_DEFAULT_PIN, 0, 0, false, false, 35 };"
INIT_NEW = "BuzzerSettings buzzerSettings = { false, BUZZER_DEFAULT_PIN, false, 0, 0, false, false, 35 };"

LOAD_OLD = """  buzzerSettings.quietStartHour = prefs.getUChar("buz_qstart", 0);
  buzzerSettings.quietEndHour = prefs.getUChar("buz_qend", 0);
"""
LOAD_NEW = """  {
    // Quiet hours: buz_qon / buz_qsm / buz_qem; a device saved before that only has the whole-hour keys and keeps what it did.
    const wnight::Quiet q = wnight::resolveQuiet(prefs.isKey("buz_qon"), prefs.getBool("buz_qon", false), prefs.getUShort("buz_qsm", 0),
                                                 prefs.getUShort("buz_qem", 0), prefs.getUChar("buz_qstart", 0), prefs.getUChar("buz_qend", 0));
    buzzerSettings.quietEnabled = q.enabled;
    buzzerSettings.quietStartMin = q.start;
    buzzerSettings.quietEndMin = q.end;
  }
"""
SAVE_OLD = """  prefs.putUChar("buz_qstart", buzzerSettings.quietStartHour);
  prefs.putUChar("buz_qend", buzzerSettings.quietEndHour);
"""
SAVE_NEW = """  prefs.putBool("buz_qon", buzzerSettings.quietEnabled);
  prefs.putUShort("buz_qsm", buzzerSettings.quietStartMin);
  prefs.putUShort("buz_qem", buzzerSettings.quietEndMin);
  // The hours, for a downgrade: the hour each time falls in, and 0 and 0 (off) when quiet hours are off.
  prefs.putUChar("buz_qstart", buzzerSettings.quietEnabled ? (uint8_t)(buzzerSettings.quietStartMin / 60U) : 0);
  prefs.putUChar("buz_qend", buzzerSettings.quietEnabled ? (uint8_t)(buzzerSettings.quietEndMin / 60U) : 0);
"""

BUZZER_OLD = """bool buzzerIsQuietHour() {
  uint8_t qs = buzzerSettings.quietStartHour;
  uint8_t qe = buzzerSettings.quietEndHour;
  if (qs == qe) return false;

  struct tm now;
  if (!getLocalTime(&now, 0)) return false;
  uint8_t h = now.tm_hour;

  if (qs < qe) return h >= qs && h < qe;
  else          return h >= qs || h < qe;
}
"""
BUZZER_NEW = """bool buzzerIsQuietHour() {
  if (!buzzerSettings.quietEnabled) return false;

  struct tm now;
  if (!getLocalTime(&now, 0)) return false;

  // Minute of the day against the window (equal times hold nothing; the end minute is outside it).
  const wnight::Quiet q = {buzzerSettings.quietEnabled, buzzerSettings.quietStartMin, buzzerSettings.quietEndMin};
  return wnight::quietNow(q, (unsigned)now.tm_hour * 60U + (unsigned)now.tm_min);
}
"""

TEMPLATE_OLD = """  if (strcmp(name, "BUZ_QS") == 0)        { out = String(buzzerSettings.quietStartHour); return true; }
  if (strcmp(name, "BUZ_QE") == 0)        { out = String(buzzerSettings.quietEndHour); return true; }
"""
TEMPLATE_NEW = """  if (strcmp(name, "BUZ_QS_OPTS") == 0 || strcmp(name, "BUZ_QE_OPTS") == 0) {
    // Quiet from: Off and the 96 times. Quiet until: the 96 times. The value is the minutes ("off" for Off).
    const bool from = strcmp(name, "BUZ_QS_OPTS") == 0;
    out = "";
    if (from) out += buzzerSettings.quietEnabled ? "<option value=\\"off\\">Off</option>" : "<option value=\\"off\\" selected>Off</option>";
    for (int i = 0; i < wnight::kOptionCount; i++) {
      char label[16], opt[80];
      const uint16_t minutes = (uint16_t)wnight::minutesOf(i);
      wnight::format(label, sizeof(label), minutes, netSettings.use24h);
      const bool selected = from ? (buzzerSettings.quietEnabled && minutes == buzzerSettings.quietStartMin) : minutes == buzzerSettings.quietEndMin;
      snprintf(opt, sizeof(opt), "<option value=\\"%u\\"%s>%s</option>", (unsigned)minutes, selected ? " selected" : "", label);
      out += opt;
    }
    return true;
  }
"""

PAGES_OLD = """          <input type="number" id="buzqs" class="mono" min="0" max="23" value="%BUZ_QS%" style="max-width:70px" placeholder="22">
          <span class="text-dim small">to</span>
          <input type="number" id="buzqe" class="mono" min="0" max="23" value="%BUZ_QE%" style="max-width:70px" placeholder="7">
          <span class="text-dim small">(0-0 = off)</span>
"""
PAGES_NEW = """          <select id="buzqs" class="mono" style="max-width:120px" aria-label="Quiet hours from">%BUZ_QS_OPTS%</select>
          <span class="text-dim small">to</span>
          <select id="buzqe" class="mono" style="max-width:120px" aria-label="Quiet hours until">%BUZ_QE_OPTS%</select>
"""
PAGES_COMMENT_OLD = "//              buzpin, buzqs, buzqe, buzclick,"
PAGES_COMMENT_NEW = "//              buzpin, buzqon, buzqsm, buzqem, buzclick,"

APP_ROT_OLD = """  p.append('buzqs', document.getElementById('buzqs').value);
  p.append('buzqe', document.getElementById('buzqe').value);
"""
APP_ROT_NEW = """  var quietFrom = document.getElementById('buzqs').value;
  p.append('buzqon', quietFrom === 'off' ? '0' : '1');
  if (quietFrom !== 'off') p.append('buzqsm', quietFrom);
  p.append('buzqem', document.getElementById('buzqe').value);
"""
APP_HOURS_OLD = """function hours(value){var out='';for(var i=0;i<24;i++){out+='<option value="'+i+'"'+(Number(value)===i?' selected':'')+'>'+String(i).padStart(2,'0')+':00</option>'}return out}"""
APP_HOURS_NEW = """function quietTimes(value,withOff){var out=withOff?'<option value="off"'+(value==='off'?' selected':'')+'>Off</option>':'';for(var i=0;i<96;i++){var m=i*15;out+='<option value="'+m+'"'+(Number(value)===m&&value!=='off'?' selected':'')+'>'+String(Math.floor(m/60)).padStart(2,'0')+':'+String(m%60).padStart(2,'0')+'</option>'}return out}"""
APP_LOAD_OLD = """el('v111QuietStart').innerHTML=hours(d.quietStart||0);el('v111QuietEnd').innerHTML=hours(d.quietEnd||0);"""
APP_LOAD_NEW = """el('v111QuietStart').innerHTML=quietTimes(d.quietEnabled?d.quietStartMin:'off',true);el('v111QuietEnd').innerHTML=quietTimes(d.quietEndMin,false);"""
APP_SAVE_OLD = """p.append('quietStart',el('v111QuietStart').value);p.append('quietEnd',el('v111QuietEnd').value);"""
APP_SAVE_NEW = """var qf=el('v111QuietStart').value;p.append('quietOn',qf==='off'?'0':'1');if(qf!=='off')p.append('quietStartMin',qf);p.append('quietEndMin',el('v111QuietEnd').value);"""
APP_NOTE_OLD = "Quiet start = quiet end disables quiet hours."
APP_NOTE_NEW = "Choose Off in Quiet from to turn quiet hours off."

ROT_OLD = """  if (server.hasArg("buzqs")) {
    int qs = server.arg("buzqs").toInt();
    if (qs >= 0 && qs <= 23) buzzerSettings.quietStartHour = qs;
  }
  if (server.hasArg("buzqe")) {
    int qe = server.arg("buzqe").toInt();
    if (qe >= 0 && qe <= 23) buzzerSettings.quietEndHour = qe;
  }
"""
ROT_NEW = """  {
    // buzqon (0 or 1), buzqsm / buzqem (minutes in 15-minute steps). buzqs / buzqe: whole hours, from a page loaded before
    // this firmware (on when they differ). A value that is not valid leaves that setting as it was.
    const String qon = server.arg("buzqon"), qsm = server.arg("buzqsm"), qem = server.arg("buzqem");
    const String qsh = server.arg("buzqs"), qeh = server.arg("buzqe");
    wnight::Quiet quiet = {buzzerSettings.quietEnabled, buzzerSettings.quietStartMin, buzzerSettings.quietEndMin};
    wnight::importQuietText(server.hasArg("buzqon") ? qon.c_str() : nullptr, server.hasArg("buzqsm") ? qsm.c_str() : nullptr,
                            server.hasArg("buzqem") ? qem.c_str() : nullptr, server.hasArg("buzqs") ? qsh.c_str() : nullptr,
                            server.hasArg("buzqe") ? qeh.c_str() : nullptr, quiet);
    buzzerSettings.quietEnabled = quiet.enabled;
    buzzerSettings.quietStartMin = quiet.start;
    buzzerSettings.quietEndMin = quiet.end;
  }
"""
EXPORT_OLD = """  buz["quietStart"] = buzzerSettings.quietStartHour;
  buz["quietEnd"] = buzzerSettings.quietEndHour;
"""
EXPORT_NEW = """  buz["quietEnabled"] = buzzerSettings.quietEnabled;
  buz["quietStartMin"] = buzzerSettings.quietStartMin;
  buz["quietEndMin"] = buzzerSettings.quietEndMin;
"""
RESTORE_OLD = """    if (buz["quietStart"].is<uint8_t>()) {
      uint8_t qs = buz["quietStart"].as<uint8_t>();
      if (qs <= 23) buzzerSettings.quietStartHour = qs;
    }
    if (buz["quietEnd"].is<uint8_t>()) {
      uint8_t qe = buz["quietEnd"].as<uint8_t>();
      if (qe <= 23) buzzerSettings.quietEndHour = qe;
    }
"""
RESTORE_NEW = """    {
      // quietEnabled and the two times in minutes; an export from before that has whole hours (on when they differ).
      wnight::Quiet quiet = {buzzerSettings.quietEnabled, buzzerSettings.quietStartMin, buzzerSettings.quietEndMin};
      wnight::importQuiet(buz["quietEnabled"].is<bool>(), buz["quietEnabled"].as<bool>() ? 1 : 0, buz["quietStartMin"].is<int>(),
                          buz["quietStartMin"].as<long>(), buz["quietEndMin"].is<int>(), buz["quietEndMin"].as<long>(),
                          buz["quietStart"].is<int>(), buz["quietStart"].as<long>(), buz["quietEnd"].is<int>(), buz["quietEnd"].as<long>(), quiet);
      buzzerSettings.quietEnabled = quiet.enabled;
      buzzerSettings.quietStartMin = quiet.start;
      buzzerSettings.quietEndMin = quiet.end;
    }
"""
HUB_GET_OLD = """  doc["quietStart"] = buzzerSettings.quietStartHour;
  doc["quietEnd"] = buzzerSettings.quietEndHour;
"""
HUB_GET_NEW = """  doc["quietEnabled"] = buzzerSettings.quietEnabled;
  doc["quietStartMin"] = buzzerSettings.quietStartMin;
  doc["quietEndMin"] = buzzerSettings.quietEndMin;
"""
HUB_SAVE_OLD = """  if(server.hasArg("quietStart")) buzzerSettings.quietStartHour = (uint8_t)constrain(server.arg("quietStart").toInt(),0,23);
  if(server.hasArg("quietEnd")) buzzerSettings.quietEndHour = (uint8_t)constrain(server.arg("quietEnd").toInt(),0,23);
"""
HUB_SAVE_NEW = """  {
    // quietOn (0 or 1), quietStartMin / quietEndMin; quietStart / quietEnd are whole hours from a page loaded before this firmware.
    const String qon = server.arg("quietOn"), qsm = server.arg("quietStartMin"), qem = server.arg("quietEndMin");
    const String qsh = server.arg("quietStart"), qeh = server.arg("quietEnd");
    wnight::Quiet quiet = {buzzerSettings.quietEnabled, buzzerSettings.quietStartMin, buzzerSettings.quietEndMin};
    wnight::importQuietText(server.hasArg("quietOn") ? qon.c_str() : nullptr, server.hasArg("quietStartMin") ? qsm.c_str() : nullptr,
                            server.hasArg("quietEndMin") ? qem.c_str() : nullptr, server.hasArg("quietStart") ? qsh.c_str() : nullptr,
                            server.hasArg("quietEnd") ? qeh.c_str() : nullptr, quiet);
    buzzerSettings.quietEnabled = quiet.enabled;
    buzzerSettings.quietStartMin = quiet.start;
    buzzerSettings.quietEndMin = quiet.end;
  }
"""


def read(path: Path) -> str:
    if not path.is_file():
        raise PatchError(f"missing reconstructed source: {path}")
    return path.read_text(encoding="utf-8")


def patch_all(repo: Path) -> dict[Path, str]:
    """Every file's new text, staged in memory: nothing is written unless every anchor matched."""
    if not (repo / "include/workshop_night_time.hpp").is_file():
        raise PatchError("include/workshop_night_time.hpp missing: apply_workshop_os12_night_minutes.py runs first")
    out: dict[Path, str] = {}

    settings_h = read(repo / "src/settings.h")
    out[repo / "src/settings.h"] = replace_once(settings_h, SETTINGS_H_OLD, SETTINGS_H_NEW, "settings.h quiet fields")

    settings_cpp = read(repo / "src/settings.cpp")
    settings_cpp = replace_once(settings_cpp, INIT_OLD, INIT_NEW, "settings.cpp buzzer initializer")
    settings_cpp = replace_once(settings_cpp, LOAD_OLD, LOAD_NEW, "settings.cpp quiet load")
    settings_cpp = replace_once(settings_cpp, SAVE_OLD, SAVE_NEW, "settings.cpp quiet save")
    out[repo / "src/settings.cpp"] = settings_cpp

    buzzer = read(repo / "src/buzzer.cpp")
    buzzer = replace_once(buzzer, '#include "settings.h"\n', '#include "settings.h"\n' + INCLUDE, "buzzer.cpp include")
    out[repo / "src/buzzer.cpp"] = replace_once(buzzer, BUZZER_OLD, BUZZER_NEW, "buzzer.cpp quiet test")

    template = read(repo / "src/web_template.cpp")
    out[repo / "src/web_template.cpp"] = replace_once(template, TEMPLATE_OLD, TEMPLATE_NEW, "web_template.cpp quiet options")

    pages = read(repo / "include/web_pages.h")
    pages = replace_once(pages, PAGES_OLD, PAGES_NEW, "web_pages.h quiet fields")
    out[repo / "include/web_pages.h"] = replace_once(pages, PAGES_COMMENT_OLD, PAGES_COMMENT_NEW, "web_pages.h key list")

    js = read(repo / "web/app.js")
    for old, new, label in (
        (APP_ROT_OLD, APP_ROT_NEW, "app.js sound form"),
        (APP_HOURS_OLD, APP_HOURS_NEW, "app.js quiet options"),
        (APP_LOAD_OLD, APP_LOAD_NEW, "app.js experience load"),
        (APP_SAVE_OLD, APP_SAVE_NEW, "app.js experience save"),
        (APP_NOTE_OLD, APP_NOTE_NEW, "app.js experience note"),
    ):
        js = replace_once(js, old, new, label)
    out[repo / "web/app.js"] = js

    web = read(repo / "src/web_server.cpp")
    for old, new, label in (
        (ROT_OLD, ROT_NEW, "web_server.cpp sound form"),
        (EXPORT_OLD, EXPORT_NEW, "web_server.cpp export"),
        (RESTORE_OLD, RESTORE_NEW, "web_server.cpp restore"),
        (HUB_GET_OLD, HUB_GET_NEW, "web_server.cpp experience get"),
        (HUB_SAVE_OLD, HUB_SAVE_NEW, "web_server.cpp experience save"),
    ):
        web = replace_once(web, old, new, label)
    out[repo / "src/web_server.cpp"] = web
    return out


def apply(repo: Path) -> None:
    for path, text in patch_all(repo).items():
        path.write_text(text, encoding="utf-8")
    print("Workshop OS 12 quiet hours installed: explicit Off, times in 15-minute steps, hour migration, portal and export")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    if not args.apply:
        raise SystemExit("refusing to modify reconstructed source without --apply")
    try:
        apply(Path(args.repo).resolve())
    except PatchError as exc:
        raise SystemExit(f"FAIL: {exc}") from exc
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
