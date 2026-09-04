# BambuHelper Smart Display — Waveshare Workshop OS

Local-first Workshop OS for the **Waveshare ESP32-S3-Touch-LCD-3.5 (`ws_lcd_350`)**, built on the BambuHelper v3.8.1 core.

## Release model

The repository separates the accepted **source line** from the intentionally conservative static firmware download channel:

| Surface | Current state | Purpose |
| --- | --- | --- |
| `main` | **Workshop OS v11.19.1 — physically accepted** | Authoritative accepted source line. |
| `release.json` / Netlify | **Smart Home v7.2** | Integrity-checked static download channel. |
| rollback download | **Smart Home v7.1** | Single immediate rollback retained for recovery safety. |
| active candidate | **Workshop OS v11.20 Portal Auth RC1 — PR #67** | Restores normal-LAN portal authentication; physical acceptance required before promotion. |

The source line, active candidate and static installer are intentionally independent. A newer candidate or accepted source does not silently replace the conservative download channel.

## Active candidate — Workshop OS v11.20 Portal Auth RC1

PR **#67** is the single current firmware candidate to `main`. It removes the accepted v11.19.1 development-auth bypass and restores the existing rotating portal-code + boot-scoped cookie session for normal LAN access while preserving the independently accessible Recovery AP path.

The candidate is intentionally **not accepted yet**. Promotion requires exact-head CI plus physical WS350 verification of login, wrong-code rejection, logout/reboot session invalidation, authenticated controls/OTA, Recovery AP access, touch behavior, printer settings and the accepted v11.19.1 physical-fit baseline.

No speculative printer-control surface is added by v11.20; Light, Pause/Resume, guarded Stop, mapped Printer Power and fail-closed MQTT behavior are inherited unchanged.

## Accepted source — Workshop OS v11.19.1

v11.19.1 is the physically accepted **Physical Fit RC2** source baseline. It preserves the complete Workshop OS feature stack and closes the final text-fit defects found by the authenticated 22-view WS350 framebuffer acceptance pass.

### Workshop experience

- calm adaptive Home and ambient/standby experience;
- materials-first AMS / filament presentation;
- Printer, Workshop, Tools, More and System surfaces;
- Workshop note and configurable timers;
- live-state freshness/stale handling;
- network, audio and LED essentials;
- printer HMS/attention presentation;
- authenticated 22-view framebuffer capture for physical UI review.

### Guarded controls

- chamber light;
- state-aware Pause / Resume;
- long-press guarded Stop;
- mapped smart-plug Printer Power;
- power automation / auto-off safeguards;
- fail-closed command behavior when MQTT connectivity disappears.

Speed/fan commands remain intentionally absent until there is an equally proven backend path and explicit safety contract.

### Hardware and recovery

- FT6336 touch recovery;
- ES8311 speaker and onboard microphone / MIC ECHO;
- settings persistence;
- printer-screen retention;
- Safari-safe recovery hashing;
- OTA candidate/rollback protections;
- `ws_lcd_350` native build and `jc3248w535` shared 320×480 regression compatibility.

The v11.19.1 physical-fit delta specifically replaces clipped Workshop/System strings with forms that fit the real 320×480 panel while preserving the v11.19 behavior contract.

## Validation model

Firmware is reconstructed deterministically from a pinned upstream BambuHelper baseline plus the incremental `apply_smart_home_*.py` evolution stack. The reusable firmware gate validates:

1. patch/tooling reconstruction;
2. inherited device contracts;
3. accepted v11.19 visual correctness;
4. accepted v11.19.1 rendered-fit contracts;
5. candidate-specific contracts when a candidate is active;
6. browser JavaScript;
7. native `ws_lcd_350` PlatformIO build;
8. shared `jc3248w535` regression build;
9. Full-image merge and OTA artifact packaging.

The accepted v11.19.1 source was promoted only after those gates and the real-device 22-view physical acceptance passed. v11.20 must pass its own physical authentication acceptance before promotion.

## Governance and safety

- `SECURITY.md` — security reporting and sensitive-data handling for a hardware-control project.
- `CONTRIBUTING.md` — contribution rules, validation tiers and repository boundaries.
- `docs/CONTROL_SAFETY.md` — fail-closed printer/power command contract.
- `docs/RELEASE_PROCESS.md` — accepted-source, candidate and static-download promotion lifecycle.
- `.github/pull_request_template.md` — safety/acceptance checklist for every PR.

## License and attribution

Original Workshop OS contributions in this repository are provided under the **MIT License** in `LICENSE`.

Workshop OS is a derived project built on **Keralots/BambuHelper**. The accepted v11.19.1 source is based on upstream commit `8cb1cbbb6d3c175af91989e8ebe1bbdcbe848ac4`; BambuHelper's README at that commit declares the project **MIT**. The upstream repository does not publish a project-level root `LICENSE` or project-level copyright notice at that baseline, so this repository does not invent one.

See `NOTICE.md` for exact upstream attribution and the boundary between Workshop OS contributions, upstream-derived material and third-party notices. Third-party components retain their original license and attribution requirements.

## Repository layout

- `apply_smart_home_*.py` — deterministic firmware evolution inputs; **not generated debris**.
- `.bambuhelper-validation/` — verified compressed patch payloads required by selected loaders.
- `.github/workflows/firmware-candidate.yml` — the single reusable firmware/hardware gate. Update this file in place for the next candidate rather than adding version-named workflows.
- `.github/workflows/validate.yml` — repository validation.
- `.github/workflows/release-gate.yml` — release/source metadata gate.
- `.github/workflows/release-main.yml` — static OTA portal integrity gate.
- `docs/` — current architecture/acceptance policy and current-version evidence.
- `docs/archive/` — superseded engineering/acceptance documentation.
- `releases/` — current release state and accepted download provenance.
- `releases/archive/` — historical RC manifests/reports retained for provenance, not active release discovery.
- `firmware/` — only the accepted v7.2 Full+OTA pair and immediate v7.1 rollback Full+OTA pair.
- `scripts/capture-ws350-views.zsh` — authenticated real-device framebuffer capture helper.
- `scripts/waveshare-usb.sh` — safe Mac USB/JTAG serial auto-detection helper.

## Upstream policy

Workshop OS remains deliberately pinned to BambuHelper commit `8cb1cbbb6d3c175af91989e8ebe1bbdcbe848ac4` for reproducibility. Upstream has advanced beyond that pin; see `docs/UPSTREAM_SYNC.md`.

Do **not** silently repin an accepted source line. Upstream synchronization is its own candidate with full reconstruction, dual-target CI, overlap review and physical acceptance.

## Firmware installation rule

For a normal device OTA/recovery-page update, use the **application image** (`WaveshareHome-firmware.bin` / named OTA image).

Only a **Full** image belongs at flash offset `0x0` during an intentional USB recovery/full flash.

## Development policy

1. Maintain one active firmware candidate PR to `main` at a time.
2. Keep one stable `.github/workflows/firmware-candidate.yml`; do not accumulate per-version workflow files.
3. Keep generated PlatformIO output, local ZIPs, temporary artifacts and ad-hoc validation reports out of source control.
4. Candidate binaries belong in GitHub Actions artifacts until intentionally promoted to the static download channel.
5. Preserve historical provenance under `docs/archive/` and `releases/archive/`, not in the active root/release namespace.
6. Retain only the accepted static firmware pair plus one immediate rollback pair as tracked binaries.
7. Do not promote a hardware-facing candidate on CI alone when physical acceptance is required.
8. Do not add speculative Bambu commands; controls require a proven backend path and explicit safety semantics.
