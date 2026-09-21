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

## 2. Build-only identity check

From the exact source checkout:

```bash
bash scripts/bootstrap_ws350_os12_usb_macos.sh \
  --expect-source-sha <EXACT_HEAD_SHA> \
  --expect-firmware-sha256 <CI_FIRMWARE_SHA256>
```

Expected result:

- exact local source matches CI source;
- locally reconstructed `firmware.bin` matches the CI SHA-256;
- no USB device access occurs;
- no firmware changes occur.

## 3. Attached-device preflight

Only when the printer is not preparing, printing, or paused:

```bash
bash scripts/bootstrap_ws350_os12_usb_macos.sh \
  --confirm-printer-idle \
  --expect-source-sha <EXACT_HEAD_SHA> \
  --expect-firmware-sha256 <CI_FIRMWARE_SHA256>
```

This may reset the WS350 into bootloader for chip/readback operations. It captures critical recovery metadata and requires a byte-for-byte partition-table match. A mismatch is a stop condition and requires the approved full-image/recovery path at `0x0`.

## 4. Guarded install

After the preflight passes:

```bash
bash scripts/bootstrap_ws350_os12_usb_macos.sh \
  --full-backup \
  --flash \
  --confirm-printer-idle \
  --expect-source-sha <EXACT_HEAD_SHA> \
  --expect-firmware-sha256 <CI_FIRMWARE_SHA256>
```

Retain the recovery directory and hashes with the candidate evidence.

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

Walk every required root/child view and record clipping, hierarchy, touch-target, navigation, responsiveness, and reboot/watchdog observations. Sensitive views are not retained as framebuffer evidence.

## 8. Device-native update / recovery

Run a non-installing candidate-channel check:

```bash
python3 scripts/accept_os12_update_runtime.py \
  --base-url http://10.0.0.124 \
  --channel candidate
```

Formal GitHub OTA install acceptance requires a strictly newer published candidate with an explicitly expected version and source SHA. Do not reuse the bootstrap version for different bytes.

Exercise recovery/rollback separately and retain the result. CI, USB upload success, and runtime API success do not substitute for physical recovery evidence.

## Release-state boundary

Only evidence actually obtained may advance the state:

`implemented -> built -> tested -> runtime validated -> production validated -> physically validated -> accepted -> stable`

A green CI candidate is **not** physically validated. A flashed candidate is **not** accepted. Physical acceptance is not stable promotion.
