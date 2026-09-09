# Device-native Workshop OS updates

`releases/device-update.json` is the machine-readable discovery contract for a WS350 that is already running a compatible Workshop OS partition layout.

## Required device behavior

1. Fetch `releases/device-update.json` from this repository's raw `main` URL over HTTPS.
2. Require `schemaVersion == 1`, `board == ws_lcd_350`, the expected repository authority, and a valid HTTPS `artifactBaseUrl`.
3. Select the configured `stable` or `candidate` channel. Stable is the default.
4. Treat `status != published`, missing fields, malformed metadata, board mismatch, unknown schema, or an invalid artifact base as **no installable update**.
5. Compare the published version with the running firmware. Never downgrade automatically.
6. For an ordinary on-device update, resolve the channel's repository-root `ota.path` against `artifactBaseUrl`; do not resolve it relative to the manifest's `/releases/` directory.
7. Download only that OTA/app image. Require the exact declared byte size and SHA-256 before beginning the OTA write/activation step.
8. On verification or installation failure, leave the currently bootable firmware authoritative and present an explicit error/retry state.
9. Reboot only after successful OTA completion. After reboot, report the actual running firmware version rather than assuming installation succeeded.

## Release channels

- **stable** — physically accepted/published binary channel. This is the normal device default.
- **candidate** — optional hardware-acceptance candidate. It remains `none-published` until an exact candidate OTA artifact, size, hash, source SHA, and release identity have been recorded.

A candidate being built or merged does not make it stable. Stable promotion requires the project's physical-acceptance process.

## Integrity gate

The accepted-static-installer workflow treats `releases/device-update.json` as release metadata. It validates the manifest schema/authority/base URL, cross-checks the stable channel against `release.json`, and recomputes the declared size and SHA-256 from the retained firmware bytes. A published candidate must likewise reference bytes present in the repository and match their exact size/hash.

This prevents a metadata-only change from publishing a stale or nonexistent artifact while still passing the release gate.

## Recovery boundary

The Full image is intentionally present for provenance and recovery, but `deviceInstallAllowed` is false. A Full image belongs at flash offset `0x0` only during the approved USB recovery/full-flash flow. Device-native OTA must not attempt cross-partition-layout migration.

Legacy Waveshare Home recovery remains available until the Workshop OS replacement/recovery path is physically proven.

## Publishing a new candidate

Publishing code must populate the candidate entry only after the OTA bytes exist at the declared repository path and their exact size/SHA-256 have been calculated. Never publish placeholder hashes or infer artifact identity from a version label.

After physical acceptance, promotion to stable must preserve the exact accepted artifact identity and evidence rather than rebuilding an allegedly equivalent binary.
