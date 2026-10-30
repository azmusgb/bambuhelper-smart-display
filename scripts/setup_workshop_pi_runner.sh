#!/usr/bin/env bash
set -euo pipefail

REPO_URL="${REPO_URL:-https://github.com/azmusgb/bambuhelper-smart-display}"
RUNNER_NAME="${RUNNER_NAME:-workshop-pi}"
RUNNER_LABELS="${RUNNER_LABELS:-workshop-pi,workshop-os}"
RUNNER_DIR="${RUNNER_DIR:-$HOME/actions-runner/bambuhelper-smart-display}"

if [[ "$(id -u)" -eq 0 ]]; then
  echo "ERROR: run this script as the normal Pi user, not root." >&2
  exit 2
fi

case "$(uname -m)" in
  aarch64|arm64) ;;
  *)
    echo "ERROR: this bootstrap currently supports Linux ARM64 only; found $(uname -m)." >&2
    exit 2
    ;;
esac

: "${GITHUB_RUNNER_TOKEN:?Set GITHUB_RUNNER_TOKEN to a fresh repository runner registration token.}"

for cmd in curl python3 tar sha256sum; do
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "ERROR: missing required command: $cmd" >&2
    exit 2
  fi
done

mkdir -p "$RUNNER_DIR"
cd "$RUNNER_DIR"

if [[ -f .runner ]]; then
  echo "ERROR: a GitHub Actions runner is already configured in $RUNNER_DIR." >&2
  echo "       Refusing to overwrite it automatically." >&2
  exit 2
fi

readarray -t release_info < <(
  python3 - <<'PY'
import json
import urllib.request

url = "https://api.github.com/repos/actions/runner/releases/latest"
req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json"})
with urllib.request.urlopen(req, timeout=30) as response:
    data = json.load(response)

version = data["tag_name"].lstrip("v")
name = f"actions-runner-linux-arm64-{version}.tar.gz"
asset = next((a for a in data.get("assets", []) if a.get("name") == name), None)
if not asset:
    raise SystemExit(f"latest runner release has no ARM64 asset named {name}")

digest = asset.get("digest") or ""
if digest.startswith("sha256:"):
    digest = digest.split(":", 1)[1]
else:
    digest = ""

print(version)
print(asset["browser_download_url"])
print(digest)
PY
)

VERSION="${release_info[0]}"
DOWNLOAD_URL="${release_info[1]}"
API_SHA256="${release_info[2]}"
PACKAGE="actions-runner-linux-arm64-${VERSION}.tar.gz"
EXPECTED_SHA256="${RUNNER_SHA256:-$API_SHA256}"

if [[ -z "$EXPECTED_SHA256" ]]; then
  echo "ERROR: GitHub did not publish an API digest for $PACKAGE." >&2
  echo "       Set RUNNER_SHA256 to the SHA-256 shown by GitHub for this runner package." >&2
  exit 2
fi

printf 'Downloading GitHub Actions runner %s for ARM64...\n' "$VERSION"
curl --fail --location --silent --show-error \
  --output "$PACKAGE" \
  "$DOWNLOAD_URL"

ACTUAL_SHA256="$(sha256sum "$PACKAGE" | awk '{print $1}')"
if [[ "$ACTUAL_SHA256" != "$EXPECTED_SHA256" ]]; then
  echo "ERROR: runner archive SHA-256 mismatch." >&2
  echo "Expected: $EXPECTED_SHA256" >&2
  echo "Actual:   $ACTUAL_SHA256" >&2
  rm -f "$PACKAGE"
  exit 2
fi

tar xzf "$PACKAGE"
rm -f "$PACKAGE"

# GitHub's dependency helper is intentionally run with sudo; the runner itself
# remains owned by and runs as the normal Pi user.
sudo ./bin/installdependencies.sh

./config.sh \
  --unattended \
  --url "$REPO_URL" \
  --token "$GITHUB_RUNNER_TOKEN" \
  --name "$RUNNER_NAME" \
  --labels "$RUNNER_LABELS" \
  --work _work \
  --replace

# The registration token is short-lived. Remove it from this process before
# service installation so child processes cannot inherit it unnecessarily.
unset GITHUB_RUNNER_TOKEN

sudo ./svc.sh install "$(id -un)"
sudo ./svc.sh start
sudo ./svc.sh status

cat <<EOF

Workshop Pi GitHub runner installed.
  Repository: $REPO_URL
  Runner:     $RUNNER_NAME
  Labels:     $RUNNER_LABELS
  Directory:  $RUNNER_DIR

Next:
  1. Confirm the runner is Online in GitHub > Settings > Actions > Runners.
  2. Manually run the "Workshop Pi Fast Preflight" workflow once.
  3. Keep the GitHub-hosted UX Architecture workflow as authoritative firmware candidate CI.
EOF
