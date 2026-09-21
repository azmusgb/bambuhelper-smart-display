# Workshop OS 12 Media Physical Acceptance

This procedure is the physical gate for the WS350 speaker, microphone, bounded recording/playback, and fixed-source displayed-printer camera video path.

It does **not** promote Workshop OS to stable and does not replace whole-device acceptance. CI build/test results are prerequisites, not physical evidence.

## Preconditions

- Exact candidate source SHA is known and CI is green.
- The WS350 is running that exact source SHA, verified by `/os12/update/status`.
- The WS350 and Mac are on the same LAN.
- A compatible displayed Bambu printer is connected through the normal printer authority.
- The displayed printer exposes a local camera stream for video acceptance.
- The actual printer is in a safe state for operator interaction.
- Recovery/rollback evidence exists for the installed image.

## Default unattended acceptance

Routine candidate validation should now start with the unattended runner rather than the interactive physical helpers:

```bash
python3 scripts/accept_os12_unattended.py \\
  --base-url http://10.0.0.124
```

By default, the runner resolves the exact expected source SHA from the `candidate` entry in `releases/device-update.json`, refuses to test a different running source, and requires no operator prompts. It automatically records:

- exact running source identity before and after the run;
- code-free local portal contract;
- required native-view catalog coverage;
- canonical `/hub/show` routing across the whole 480x320 UI set;
- framebuffer dimensions, content sanity, hashes, and route diversity;
- speaker lifecycle plus codec/I2S/pipeline/amplifier diagnostics;
- valid microphone ADC/sample measurements;
- bounded record -> idle -> playback -> idle lifecycle;
- video framebuffer motion, pause/freeze, resume, and stop behavior;
- clean final media state, end-of-run LAN reachability, and monotonic uptime.

A successful run reports `UNATTENDED WORKSHOP OS 12 ACCEPTANCE: PASS` and writes a timestamped JSON evidence bundle under `~/Downloads` unless `--output` is supplied.

This unattended pass deliberately does **not** relabel machine-observable evidence as final physical acceptance. The remaining human-only checks are reduced to a final release spot-check for physical LCD appearance, actual finger-driven touch behavior, audible speaker quality, microphone intelligibility, and physical recovery/rollback when that gate is due. Those checks are not required on every candidate iteration.

## Runtime exercise

From the repository root:

```bash
python3 scripts/accept_os12_media_runtime.py \
  --base-url http://10.0.0.124 \
  --exercise \
  --exercise-video
```

This validates the authenticated runtime contract and drives:

- bounded non-blocking speaker test;
- microphone activity sample;
- five-second maximum PSRAM recording;
- local recording playback;
- fixed-source displayed-printer camera video start;
- video pause;
- video resume;
- video stop;
- clean return to `Idle`.

The video path accepts no arbitrary URL. It reuses the existing printer-camera client and LovyanGFX JPEG renderer and is paced to a maximum of approximately 8 fps.

## Physical evidence

Run:

```bash
python3 scripts/accept_os12_media_physical.py \
  --base-url http://10.0.0.124 \
  --expect-source-sha <EXACT_CI_SOURCE_SHA>
```

The helper drives the media diagnostics and requires explicit operator observations for:

- audible, clean speaker output;
- microphone response to local sound;
- intelligible five-second recording playback;
- no obvious electrical noise, lockup, reboot, or UI freeze;
- visibly updating printer-camera video;
- visible freeze/resume behavior;
- responsive touch while video is active;
- continued printer telemetry;
- healthy non-destructive printer controls;
- LAN reachability after media stop;
- no watchdog reset or unexpected recovery entry.

The helper refuses an open-LAN image and requires the running device's exact source SHA to equal `--expect-source-sha` before any physical result can pass. It writes a timestamped JSON evidence bundle under `~/Downloads` by default. The portal code is never written to the bundle.

## Acceptance rule

`PHYSICAL MEDIA ACCEPTANCE: PASS` is valid only when:

1. runtime identity is captured;
2. required speaker, microphone, PSRAM, and video capabilities are present;
3. every required operator observation is explicitly confirmed;
4. the final media state is `Idle` with `error=None`;
5. the evidence bundle is retained with the candidate evidence.

Any failed or unknown observation leaves media physical acceptance **pending/failed**. Do not reinterpret a CI pass, successful API call, or configured transport as physical acceptance.

## Release boundary

A media physical pass advances only the media slice toward `physically validated`. Whole-device `accepted` and `stable` still require the broader Workshop OS acceptance gate, including navigation, printer controls, networking, OTA, reboot, recovery, and rollback verification.
