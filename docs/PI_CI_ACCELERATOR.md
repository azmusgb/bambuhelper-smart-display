# Workshop Pi CI Accelerator

This repository can use the Raspberry Pi as an always-on GitHub Actions preflight runner without making the Pi the release or firmware-candidate authority.

## Authority model

- **Pi runner:** fast preflight only; syntax, Premium UI contract, layout smoke tests, and X2D unit tests.
- **GitHub-hosted Workshop OS 12 UX Architecture:** remains the sole CI authority for the flashable WS350 physical-acceptance candidate, exact source SHA, artifact packaging, and candidate evidence.
- **Physical acceptance:** remains mandatory before promotion.

## Why this exists

UI-only changes under `firmware/platform/ui/**` previously caused both Workshop OS 12 UX Architecture and Workshop OS 12 Platform Bridge to perform full firmware reconstruction/builds.

Platform Bridge now classifies pull-request deltas before preparing PlatformIO. On a PR `synchronize` event, only the newly pushed `before -> head` delta is classified. If all newly pushed platform changes are presentation-only files under `firmware/platform/ui/**`, Platform Bridge keeps its lightweight source/safety/helper checks but skips the second firmware reconstruction/build. Non-UI platform, media, control, security, update, inventory, tooling, or Platform Bridge workflow changes still force the full regression build.

## Pi preflight safety model

The Pi preflight is a second job inside `.github/workflows/os12-platform-bridge.yml`. It runs only when both conditions are true:

1. the pull request comes from this same repository, not a fork; and
2. repository Actions variable `WORKSHOP_PI_RUNNER` equals `enabled`.

Until that variable is enabled, the Pi job is skipped immediately. An offline or not-yet-configured Pi therefore cannot leave pull requests waiting for a self-hosted runner.

Never remove the same-repository guard for a runner located on the home/workshop network.

## Install the Pi runner

1. In GitHub, open the repository and go to **Settings > Actions > Runners > New self-hosted runner**.
2. Choose **Linux** and **ARM64** and copy a fresh repository runner registration token.
3. On the Pi, as the normal non-root user, fetch a branch containing `scripts/setup_workshop_pi_runner.sh` and run:

```bash
export GITHUB_RUNNER_TOKEN='<short-lived token>'
bash scripts/setup_workshop_pi_runner.sh
unset GITHUB_RUNNER_TOKEN
```

The bootstrap:

- resolves the current ARM64 GitHub Actions runner release;
- verifies the downloaded archive SHA-256 before extraction;
- installs required runner dependencies;
- registers runner name `workshop-pi` by default;
- registers labels `workshop-pi,workshop-os`;
- installs the runner as a service owned by the normal Pi user; and
- removes the short-lived registration token from its process environment before service installation.

Do not commit, save, or paste the registration token into repository files or chat. Treat it as a secret while valid.

## Enable the preflight

After GitHub shows the runner **Online**:

1. Go to **Settings > Secrets and variables > Actions > Variables**.
2. Create repository variable:

```text
WORKSHOP_PI_RUNNER=enabled
```

3. Push or synchronize a same-repository pull request that triggers Workshop OS 12 Platform Bridge.
4. Confirm that Platform Bridge shows two jobs:
   - `Reconstruct and compile OS12 device platform`
   - `Pi fast preflight`

For an ordinary Premium UI-only synchronize delta, the desired behavior is:

- Pi fast preflight runs the Premium UI validator, tabs layout smoke, More layout smoke, and X2D unit tests;
- hosted Platform Bridge takes its lightweight UI-only path rather than repeating the firmware reconstruction;
- hosted UX Architecture performs the one authoritative exact-head firmware reconstruction/build and candidate packaging.

## Disable / fail-safe

Set `WORKSHOP_PI_RUNNER` to any value other than `enabled`, or delete the variable. The Pi job will skip while all GitHub-hosted authoritative CI continues normally.

If the Pi is intentionally offline, disable the variable first.

## Release boundary

The Pi result is additional fast evidence only. It does not establish runtime acceptance, physical acceptance, accepted state, or stable release state. GitHub-hosted UX Architecture remains the candidate authority, and physical 480x320 acceptance remains required before promotion.
