# Workshop OS 12 physical acceptance sequence

This is the canonical path from an exact-head CI candidate to physical evidence on the WS350. It does not merge, accept, or promote the release automatically.

## 1. Exact-head prerequisites

Require all exact-head PR gates to be green, including:

- Validate
- Workshop OS Firmware Gate
- Workshop OS UI13 Appliance Settings Gate
- Validate accepted static installer
- Workshop OS 12 Platform Bridge
- Workshop OS 12 UX Architecture
- Release Gate / merge-gate

Record the exact source SHA, the OS12 UX physical-candidate artifact ID, firmware byte count, and firmware SHA-256. Platform Bridge regression evidence is not flashable candidate authority.

## 2. Prepare the exact CI candidate

Download the OS12 UX Architecture artifact for the exact PR head and extract it locally. The artifact must contain:

- `candidate.json`
- `SHA256SUMS.txt`
- `firmware.bin`
- `partitions.bin`

Do not rebuild firmware on the Mac. CI is the sole physical-candidate build authority.

## 3. Attached-device preflight + guarded exact-artifact install

Only when the printer is not preparing, printing, or paused:

```bash
bash scripts/flash_os12_ci_candidate_macos.sh \
  --candidate-dir /path/to/extracted-os12-ci-candidate \
  --expect-source-sha <EXACT_HEAD_SHA> \
  --expect-firmware-sha256 <CI_FIRMWARE_SHA256> \
  --confirm-printer-idle \
  --full-backup
```

The installer must:

- verify the exact checkout SHA;
- verify `candidate.json`, `SHA256SUMS.txt`, `firmware.bin`, and `partitions.bin`;
- use an isolated `esptool`/pyserial runtime only;
- read the attached WS350 partition table and require a byte-for-byte match with the CI `partitions.bin`;
- capture NVS, OTA data, partition-table bytes, and a full 16 MB recovery image before install;
- return the device to runtime;
- upload the exact CI `firmware.bin` through the device manual OTA path with the expected SHA-256;
- run the post-reboot portal probe.

A partition mismatch is a stop condition. Cross-line migration still requires the approved full-image/recovery path at `0x0`.

The macOS physical installer must not invoke PlatformIO or rebuild a substitute `firmware.bin`. Retain the recovery directory and hashes with the candidate evidence.

## 4. Installer evidence boundary

Successful exact-artifact install establishes only:

- source identity verified;
- CI firmware identity verified;
- CI partition-layout identity verified;
- full recovery capture completed;
- exact CI application image accepted by the device;
- portal probe completed.

It does not establish whole-device physical acceptance, media quality, printer-control acceptance, recovery acceptance, OTA acceptance, accepted state, or stable state.

## 5. Authenticated runtime acceptance

First prove the temporary/open-LAN test path is absent:

```bash
python3 scripts/accept_os12_portal_runtime.py \
  --base-url http://10.0.0.124 \
  --exercise-rate-limit
```

If the supported persisted policy is `open-readonly`, re-enable **Require access code** before acceptance. If the root is open while the policy is not `open-readonly`, stop: that is an unexpected authorization state.

## 6. Media runtime + physical acceptance

```bash
python3 scripts/accept_os12_media_runtime.py \
  --base-url http://10.0.0.124 \
  --exercise \
  --exercise-video

python3 scripts/accept_os12_media_physical.py \
  --base-url http://10.0.0.124 \
  --expect-source-sha <EXACT_HEAD_SHA>
```

Unknown or failed operator observations remain pending; they are not coerced to pass.

## 7. Whole-device 480×320 acceptance

```bash
python3 scripts/accept_os12_device_ui_physical.py \
  --base-url http://10.0.0.124 \
  --expect-source-sha <EXACT_HEAD_SHA>
```

Walk every required root/child view and record clipping, hierarchy, touch-target, navigation, responsiveness, and reboot/watchdog observations. On Workshop, explicitly prove that the visible **Refresh** and **Local Portal / Set Up Inventory** controls respond as labeled and that tapping the read-only evidence rows does not trigger hidden legacy actions. Sensitive views are not retained as framebuffer evidence.

### More pages (Workshop OS 12.1.4 and later)

The More tab holds 15 pages, at most two levels deep. The page table and every touch rectangle live in `firmware/platform/ui/more_layout.hpp`. The host test `tests/workshop_os12_more_layout_smoke.cpp` covers both orientations.

| `/hub/views` id | Page | Opens from |
|---|---|---|
| `more` | More (six tiles) | More tab |
| `settings-printer-power` | Printer & Power | More |
| `hardware-auto-off` | Auto power-off | Printer & Power |
| `settings-network` | Network | More |
| `system-date-time` | Time & locale | Network |
| `settings-display` | Display | More |
| `display-clock` | Clock & schedule | Display |
| `display-gauges` | Gauges | Display |
| `settings-sounds` | Sound & Alerts | More |
| `display-alerts` | Printer alerts | Sound & Alerts |
| `hardware-led` | Status light | Sound & Alerts |
| `media-video` | Video test | Sound & Alerts |
| `system-portal` | Local Portal (**sensitive**: the access code) | More |
| `system-update` | Updates & About | More |
| `system-diagnostics` | Device health | Updates & About |

With Home, Printer and Workshop, the catalog lists 18 views (catalog version 3). Removed ids are still accepted by `/hub/show` and open the page that replaced them: `system`, `tools`, `custom`, `media`, `media-lab`, the merged `display-*` ids, the other `hardware-*` ids, and the Network Expert ids. `scripts/capture-ws350-views.zsh` redacts the access-code row, (8, 89)–(472, 133), on catalog v3.

Every More page must show:
- the same header, with Back at top-left going to the parent page;
- the tab bar, drawn and live (the More tab always opens the More root);
- single-line rows at least 44 px tall;
- stepper values centred between "−" and "+";
- disabled controls that state the reason.

In the physical walk, tap the centre and the edges of Back, a tab, and each kind of control on each page.

## 8. Device-native update / recovery

Run a non-installing candidate-channel check:

```bash
python3 scripts/accept_os12_update_runtime.py \
  --base-url http://10.0.0.124 \
  --channel candidate
```

Formal GitHub OTA install acceptance requires a strictly newer published candidate with an explicitly expected version and source SHA. Do not reuse the bootstrap version for different bytes.

Exercise recovery separately and retain the result. The repository now provides an unattended same-state full-image recovery round-trip for the attached WS350:

```bash
bash scripts/accept_os12_recovery_roundtrip_macos.sh \
  --artifact-zip ~/Downloads/os12-ux-ws350-<source-sha>.zip \
  --confirm-printer-idle \
  --exercise \
  --base-url http://10.0.0.124
```

This helper validates the exact CI artifact against `releases/current.json`, verifies the running source, byte-compares the live partition table to the CI artifact, captures the current full 16 MB flash, writes **only that just-captured image** back at offset `0x0`, and requires the same exact source SHA after reboot. It uses no interactive `y/n/u` prompts and does not rebuild firmware.

A PASS proves the current-device full-image recovery/write/boot path while preserving the intended installed source. It does **not** prove rollback to a historical firmware generation. Historical-version rollback, if required for stable promotion, remains a separate explicitly identified exercise using an approved known-good artifact.

CI, USB upload success, and runtime API success do not substitute for the physical recovery round-trip actually running and passing on the WS350.

## Release-state boundary

Only evidence actually obtained may advance the state:

`implemented -> built -> tested -> runtime validated -> merged-unaccepted -> physically validated -> accepted -> stable`

A green CI candidate is **not** physically validated. A flashed candidate is **not** accepted. Physical acceptance is not stable promotion.
