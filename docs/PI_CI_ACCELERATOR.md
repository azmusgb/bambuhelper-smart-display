# Workshop Pi CI Accelerator

This repository can use a Raspberry Pi as an always-on GitHub Actions preflight runner without making the Pi the release or firmware-candidate authority.

## Authority model

- **Pi runner:** fast preflight only; syntax, Premium UI contract, layout smoke tests, X2D unit tests, and optionally a full local reconstruction when manually requested.
- **GitHub-hosted Workshop OS 12 UX Architecture:** remains the sole CI authority for the flashable WS350 physical-acceptance candidate, exact source SHA, artifact packaging, and candidate evidence.
- **Physical acceptance:** remains mandatory before promotion.

## Why this exists

UI-only changes under `firmware/platform/ui/**` previously caused both Workshop OS 12 UX Architecture and Workshop OS 12 Platform Bridge to perform full firmware reconstruction/builds. The Platform Bridge workflow now classifies pull-request changes and takes a lightweight fast path when the only platform changes are presentation-only UI files. Non-UI platform changes still run the complete Platform Bridge reconstruction/build.

## Install the Pi runner

1. In GitHub, open the repository and go to **Settings > Actions > Runners > New self-hosted runner**.
2. Choose **Linux** and **ARM64** and create/copy a fresh repository runner registration token.
3. On the Pi, as the normal non-root user, fetch the branch/repository and run:

```bash
export GITHUB_RUNNER_TOKEN='<short-lived token>'
bash scripts/setup_workshop_pi_runner.sh
unset GITHUB_RUNNER_TOKEN
```

The bootstrap verifies the downloaded ARM64 runner archive before configuring it, installs required dependencies, registers labels `workshop-pi,workshop-os`, and installs the runner as a system service.

Do not commit, save, or paste the runner registration token into repository files. Registration tokens are short-lived and should be treated as secrets while valid.

## First validation

After the runner shows **Online** in GitHub:

1. Open **Actions > Workshop Pi Fast Preflight**.
2. Select the desired branch/ref.
3. Run the workflow with `full_build=false` first.
4. Confirm the fast contracts pass.
5. Optionally run once with `full_build=true` to prove the pinned PlatformIO/ESP32-S3 toolchain on ARM64.

The Pi workflow is intentionally `workflow_dispatch`-only during initial qualification so an offline or unconfigured Pi can never leave pull requests stuck waiting for a self-hosted runner.

## Future automatic mode

After the Pi runner has been stable, the preflight workflow can be extended to `pull_request`/`synchronize` events with a same-repository guard. Do not enable automatic execution for untrusted fork pull requests on a home-network self-hosted runner.
