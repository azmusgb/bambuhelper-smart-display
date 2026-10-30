#!/usr/bin/env python3
"""Validate the Workshop OS 12.3.6 WS350 touch and audio layer on a finished tree.

Run after apply_workshop_os12_touch_audio_fit.py. Fails on a tree without it.
Checks, in the reconstructed source:

Touch
- the hub commits only changed row bands (frame-diff header installed and
  identical to firmware/platform/ui/frame_diff.hpp, clip-rect pushes, full
  push only when forced);
- updateDisplay redraws a changed hub page at once instead of waiting for the
  250 ms tick;
- a touch-down outlines its target before the click sound, and the release
  clears the outline;
- the tab bar touch zone keeps its guard band, and read-only/disabled rows are
  drawn flat (wsm::rowRaised).

Audio
- WS350 (no amplifier enable pin) never powers the codec down at idle;
- microphone capture and the level meter run in the audio task; the main loop
  no longer reads I2S for them;
- playback goes through the recording DSP (slot, DC, capped gain, fades);
- /os12/media/status carries the recording and playback diagnostics;
- media-lab opens Sound & Alerts on its media rows, and the Microphone row
  has a live meter.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class ValidationError(RuntimeError):
    pass


def read(path: Path) -> str:
    if not path.is_file():
        raise ValidationError(f"missing {path}")
    return path.read_text(encoding="utf-8")


def need(text: str, needle: str, what: str) -> None:
    if needle not in text:
        raise ValidationError(f"{what}: missing {needle!r}")


def forbid(text: str, needle: str, what: str) -> None:
    if needle in text:
        raise ValidationError(f"{what}: found {needle!r}")


def block(text: str, signature: str) -> str:
    start = text.find(signature)
    if start < 0:
        raise ValidationError(f"missing function {signature}")
    brace = text.find("{", start + len(signature))
    depth = 0
    for i in range(brace, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return text[start:i + 1]
    raise ValidationError(f"unterminated function {signature}")


def validate(repo: Path, source_root: Path) -> None:
    build = read(repo / "include/smart_home_build.h")
    need(build, "#define WORKSHOP_OS12_TOUCH_AUDIO_FIT 1", "build marker")
    for src, dst in (("firmware/platform/ui/frame_diff.hpp", "include/workshop_frame_diff.hpp"),
                     ("firmware/platform/media/recording_dsp.hpp", "include/workshop_recording_dsp.hpp")):
        if read(repo / dst) != read(source_root / src):
            raise ValidationError(f"installed {dst} differs from {src}")

    hub = read(repo / "src/smart_hub.cpp")
    display = read(repo / "src/display_ui.cpp")
    main = read(repo / "src/main.cpp")
    es = read(repo / "src/buzzer_backend_es8311.cpp")
    web = read(repo / "src/web_server.cpp")
    layout = read(repo / "include/workshop_more_layout.hpp")
    tabs = read(repo / "include/workshop_tabs_layout.hpp")

    # --- Touch: changed rows only ---------------------------------------------------
    commit = block(hub, "static void hubCommitFrame()")
    need(commit, "workshop::ui::frame::rowHash(", "row hashes")
    need(commit, "workshop::ui::frame::diffBands(", "changed-row bands")
    need(commit, "g_hubPanelCanvas->setClipRect(0, bands[i].y, w, bands[i].h);", "band push through a clip rectangle")
    if commit.count("pushSprite(0, 0)") != 2:
        raise ValidationError("hubCommitFrame must push once for a full frame and once per band")
    full = commit[commit.find("const bool full ="):commit.find(";", commit.find("const bool full ="))]
    for cond in ("!g_hubFramePrimed", "g_hubCommitForceFull"):
        need(full, cond, "full push only when forced")
    draw = block(hub, "void smartHubDraw(ScreenState screen, bool forceRedraw)")
    need(draw, "if (effectiveForce) g_hubCommitForceFull = true;", "forced redraw pushes the whole frame")
    need(draw, "g_dirty = false;", "drawn change is consumed")
    hold = block(hub, "void smartHubUpdateHoldProgress(uint16_t rawX, uint16_t rawY, uint32_t holdMs)")
    need(hold, "g_hubCommitForceFull = true;", "hold progress drawn to the panel forces a full push")

    # --- Touch: immediate redraw ----------------------------------------------------
    upd = block(display, "void updateDisplay()")
    need(upd, "smartHubRedrawPending()", "hub change redraws at once")
    need(upd, "hubChanged ? kHubChangeRedrawMs :", "hub change interval")
    need(display, "static const unsigned long kHubChangeRedrawMs = 20;", "redraw floor")

    # --- Touch: pressed highlight -------------------------------------------------
    wake = block(main, "static void handleWakeButton()")
    down = wake.find("smartHubTouchDown(hubTouchX, hubTouchY);")
    click = wake.find("buzzerPlayClick();", wake.find("hubTouchHasPoint = buttonGetTouchPosition(&hubTouchX, &hubTouchY);"))
    if down < 0 or click < 0 or down > click:
        raise ValidationError("the pressed highlight must be drawn on touch-down, before the click sound")
    need(block(hub, "void smartHubTouchDown(uint16_t rawX, uint16_t rawY)"), "hubPressRect(x, y, r)", "highlight target")
    touch = block(hub, "bool smartHubHandleTouch(uint16_t rawX, uint16_t rawY, bool longPress)")
    need(touch, "if (g_hubPressShown) { g_hubPressShown = false; g_dirty = true; }", "release clears the highlight")
    pressed = block(hub, "static void hubDrawPressed(const wsm::Rect& r)")
    need(pressed, "hubInvalidateRows(r.y, r.h);", "highlight rows re-pushed on the next commit")
    need(read(repo / "src/smart_hub.h"), "void smartHubTouchDown(uint16_t rawX, uint16_t rawY);", "touch-down API")

    # --- Touch: geometry and styling ----------------------------------------------
    for name, text in (("More", layout), ("tabs", tabs)):
        hit = block(text, "inline Hit hitTest(")
        need(hit, "tabTouchRect(s, i).contains(x, y)", f"{name} tab touch keeps the guard band")
        forbid(hit, "tabRect(s, i).contains(x, y)", f"{name} tab touch on the drawn tab")
    need(layout, "static const int16_t kTabGuard = 4;", "guard band")
    row = block(hub, "static void wsDrawRowBody(const wsm::Screen& s, wsm::RowKind kind, const char* labelText, const WsRowView& v,")
    need(row, "const bool raised = wsm::rowRaised(kind, v.enabled);", "flat read-only and disabled rows")
    need(layout, "inline bool rowRaised(RowKind kind, bool enabled) { return rowInteractive(kind) && enabled; }", "raised rule")
    tray = block(hub, "static void wtDrawTray(const wsm::Screen& s, const wsm::Rect& row, const WtTray& t)")
    if re.search(r"(?:fill|draw)RoundRect\s*\(\s*surface\.x", tray):
        raise ValidationError(
            "AMS read-only tray surface must stay flat; "
            "a rounded tray surface looks interactive"
        )

    # --- Audio: no codec power cycling without a PA pin -----------------------------
    tick = block(es, "void buzzerBackendTick()")
    need(tick, "#if AUDIO_PA_CTRL >= 0\n        shutdownAudio();\n#else", "codec power-down only with a PA pin")
    need(tick, "os12SetIdleQuiet(true);", "idle quiet instead of power-down")
    need(block(es, "void buzzerBackendApplyStep(uint16_t freq)"), "os12SetIdleQuiet(false);", "unmute on sound")

    # --- Audio: capture and meter in the audio task -------------------------------
    task = block(es, "void audioTask(void*)")
    need(task, "os12ReadMic(rx, sizeof(rx));", "RX read after every TX write")
    need(task, "workshop::media::dsp::renderChunk(", "playback through the recording DSP")
    forbid(task, "gOs12PlaybackGainQ8) >> 8", "12.3.5 raw stereo playback gain")
    need(es, 'audioTask, "buzzer_es8311", 4096, nullptr, 3,', "audio task above the loop task")
    for sig in ("bool buzzerBackendMicRecordPoll()", "int buzzerBackendMicLevel(uint16_t sampleMs)",
                "bool buzzerBackendMicRecordBegin(uint32_t maxDurationMs)"):
        forbid(block(es, sig), "i2s_read(", f"{sig} reads I2S from the main loop")
    need(block(es, "void os12StoreChunk(const uint8_t* data, size_t bytes)"),
         "gOs12RecordingBytes >= gOs12RecordingCapacity", "recording completes by size")
    play = block(es, "bool buzzerBackendMicPlaybackBegin()")
    need(play, "workshop::media::dsp::analyzeStereoClip(", "clip analysed before playback")
    forbid(play, "96U * 256U", "12.3.5 96x playback gain")
    dsp = read(repo / "include/workshop_recording_dsp.hpp")
    need(dsp, "static const uint32_t kPlaybackMaxGainQ8 = 16U * 256U;", "gain capped at 16x")

    # --- Audio: diagnostics --------------------------------------------------------
    status = block(web, "static void sendWorkshopMediaStatus(")
    for key in ("audioIdleQuiet", "recordingBytes", "recordingTargetBytes", "recordingWallMs",
                "recordingRxShortReads", "playbackSlot", "playbackDcOffset", "playbackGainQ8"):
        if status.count(f'doc["{key}"]') != 2:
            raise ValidationError(f"media status must report {key} on every board")

    # --- Microphone meter and media rows on screen -------------------------------------
    show = block(hub, "static bool wsMoreShowPage(const char* name)")
    need(show, "wsm::scrollToRow(wsScreen(), wsm::PageId::SoundAlerts, wsm::RowId::SpeakerTest)", "media-lab shows the media rows")
    view = block(hub, "static void wsRowView(wsm::RowId id, WsRowView& v)")
    mic = view[view.find("case R::MicTest:"):view.find("case R::Recorder:")]
    need(mic, "v.meter = (int8_t)g_wsMicLiveLevel;", "live microphone bar")
    service = block(hub, "void smartHubService()")
    need(service, "wsMoreService();", "meter driven every loop")
    need(block(hub, "static void wsMoreService()"), "buzzerBackendMicLiveLevel()", "meter reads the live level")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    ap.add_argument("--source-root", default=str(ROOT))
    args = ap.parse_args()
    try:
        validate(Path(args.repo).resolve(), Path(args.source_root).resolve())
    except ValidationError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    print("Workshop OS 12.3.6 touch and audio fit: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
