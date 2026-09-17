# Device-native Workshop OS updates

`releases/device-update.json` is the machine-readable discovery contract for a WS350 that is already running a compatible Workshop OS partition layout.

Workshop OS 12 now has one device-native online-update authority: `UpdateService`. It reads this manifest from the repository's raw `main` URL, exposes normalized update state through `WorkshopState`, and owns check/download/verify/stage/reboot behavior. The historical URL-driven `/ota/auto` route is deliberately not registered by the OS12 reconstruction. Manual local OTA remains a maintenance/bootstrap fallback.

Implementation/build validation is not physical acceptance. Until the new updater is installed and exercised on the WS350, this capability remains below `runtime validated`.

## Required device behavior

1. Fetch `releases/device-update.json` from this repository's raw `main` URL over certificate-validated HTTPS. There is no `setInsecure` fallback.
2. Require `schemaVersion == 1`, `authority == azmusgb/bambuhelper-smart-display`, `board == ws_lcd_350`, and the canonical raw-`main` `artifactBaseUrl`.
3. Resolve repository-root artifact paths against `artifactBaseUrl`. Do not resolve `ota.path` relative to the `releases/` manifest directory and reject absolute, traversal, backslash, or alternate-host paths.
4. Select the configured `stable` or `candidate` channel. Stable is the default; Candidate is an explicit opt-in hardware-acceptance channel.
5. Treat `status != published`, missing fields, malformed metadata, board/authority mismatch, an unknown schema, or an OTA image larger than the inactive application partition as **no installable update**.
6. Compare the published release version with the running Workshop OS release version. Never downgrade automatically. A published version must never be reused for different bytes.
7. Before installation, fail closed when any configured printer has stale/unknown state or is preparing, printing, or paused. An update temporarily removes local device control and must not begin from uncertain/active printer state.
8. Download only the selected channel's `ota.path` for an ordinary on-device update. Full images are never eligible for this path.
9. Require the exact declared HTTP content length and exact downloaded byte count. Stream the image only to `esp_ota_get_next_update_partition(nullptr)` while computing SHA-256.
10. Require the computed SHA-256 to equal the manifest before calling `esp_ota_set_boot_partition`. On download, size, hash, flash, or finalization failure, leave the current boot partition authoritative and restore normal printer connectivity where possible.
11. Reboot only after the inactive application partition has been written, finalized, hash-verified, and selected as the next boot partition. After reboot, report the actual embedded Workshop OS release version rather than assuming installation succeeded.

## Release channels

- **stable** — the physically accepted/published binary channel and the normal device default.
- **candidate** — an optional published hardware-acceptance candidate. `published` means exact bytes, size, SHA-256, source SHA, path, and release identity exist; it does **not** mean accepted or stable.

The manifest's current entries are authoritative. Historical candidates may remain published while a newer OS12 candidate is still only a CI artifact. A build, merge, Actions artifact, or version label by itself does not make an image discoverable by the device.

## Update UX and API

On the WS350 the intended touch flow is:

`System -> Software Update -> Stable/Candidate -> Check Now -> Review & Install -> Install`

The screen renders normalized `UpdateState`: running/available version, selected channel, phase, progress, candidate label, freshness, and artifact-integrity state. Installation requires an explicit confirmation and communicates that the device will download the exact GitHub OTA image, verify size/SHA-256, write the inactive application partition, and reboot.

The authenticated local portal also exposes the same service rather than a second updater:

- `GET /os12/update/status`
- `POST /os12/update/check`
- `POST /os12/update/channel` with `channel=stable|candidate`
- `POST /os12/update/install`

These routes are local control surfaces over `UpdateService`; they do not accept an arbitrary firmware URL.

## Recovery boundary

The Full image is intentionally a recovery/migration artifact and is not a normal device update. A Full image belongs at flash offset `0x0` only during the approved USB recovery/full-flash flow. Device-native OTA must not attempt cross-partition-layout migration.

Legacy Waveshare Home recovery remains available until the Workshop OS replacement/recovery path is physically proven.

## Bootstrap requirement

A WS350 running firmware from before this OS12 UpdateService cannot acquire the new updater by using a feature it does not yet have. The first installation is therefore a **bootstrap OTA** using the existing authenticated local firmware-upload path (or the approved USB recovery path only when partition migration is actually required).

After that bootstrap installation and reboot, future ordinary candidates can be checked and installed directly from GitHub on the device, subject to the manifest and acceptance rules above.

## Preparing a candidate

The build pipeline creates an exact-head WS350 **CI artifact** with SHA-256 and build metadata, but intentionally does not publish it into `releases/device-update.json` automatically.

For a reviewed publication change, use `scripts/prepare_os12_device_candidate.py` against the exact `ws_lcd_350` PlatformIO `firmware.bin`. The helper:

- refuses Full/merged image names and requires ESP application-image magic;
- computes the exact byte size and SHA-256;
- copies the bytes to a deterministic `releases/os12-candidates/<version>/` path;
- records source SHA and artifact provenance;
- updates **only** the `candidate` manifest entry;
- rejects reuse of a published version for different bytes/source identity;
- never pushes, merges, edits `stable`, or claims physical acceptance.

Commit the candidate bytes, `BUILD-INFO.json`, `SHA256SUMS.txt`, and manifest change together so the manifest never points at absent or placeholder bytes.

After physical acceptance, promotion to stable must preserve the exact accepted artifact identity and evidence rather than rebuilding an allegedly equivalent binary.

## Superseded branch cleanup

Experimental or handoff branches are not release channels and do not become authoritative because they contain a higher version label. Before deleting a superseded branch, compare it with the active release/candidate line and preserve any required source, tests, documentation, or artifact provenance in an authoritative branch. Branch deletion is repository hygiene only; it does not establish runtime, production, physical-acceptance, or stable status.

Historical `workshop-os-v11-26-*` development branches remain historical even if a v11.26 candidate is present in the manifest. The manifest plus exact artifact bytes/provenance is authoritative for what a device may discover and install.
