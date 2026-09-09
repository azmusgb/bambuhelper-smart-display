# Device-native Workshop OS updates

`releases/device-update.json` is the machine-readable discovery contract for a WS350 that is already running a compatible Workshop OS partition layout.

## Required device behavior

1. Fetch `releases/device-update.json` from this repository's raw `main` URL over HTTPS.
2. Require `schemaVersion == 1` and `board == ws_lcd_350`.
3. Select the configured `stable` or `candidate` channel. Stable is the default.
4. Treat `status != published`, missing fields, malformed metadata, board mismatch, or an unknown schema as **no installable update**.
5. Compare the published version with the running firmware. Never downgrade automatically.
6. Download only the channel's `ota.path` for an ordinary on-device update.
7. Require the exact declared byte size and SHA-256 before beginning the OTA write/activation step.
8. On verification or installation failure, leave the currently bootable firmware authoritative and present an explicit error/retry state.
9. Reboot only after successful OTA completion. After reboot, report the actual running firmware version rather than assuming installation succeeded.

## Release channels

- **stable** — physically accepted/published binary channel. This is the normal device default.
- **candidate** — optional hardware-acceptance candidate. It remains `none-published` until an exact candidate OTA artifact, size, hash, source SHA, and release identity have been recorded.

A candidate being built or merged does not make it stable. Stable promotion requires the project's physical-acceptance process.

## Recovery boundary

The Full image is intentionally present for provenance and recovery, but `deviceInstallAllowed` is false. A Full image belongs at flash offset `0x0` only during the approved USB recovery/full-flash flow. Device-native OTA must not attempt cross-partition-layout migration.

Legacy Waveshare Home recovery remains available until the Workshop OS replacement/recovery path is physically proven.

## Publishing a new candidate

Publishing code must populate the candidate entry only after the OTA bytes exist at the declared repository path and their exact size/SHA-256 have been calculated. Never publish placeholder hashes or infer artifact identity from a version label.

After physical acceptance, promotion to stable must preserve the exact accepted artifact identity and evidence rather than rebuilding an allegedly equivalent binary.
