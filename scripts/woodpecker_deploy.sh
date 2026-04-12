#!/usr/bin/env bash
set -euo pipefail

git config --global --add safe.directory "*"
export HOME=/tmp/ci-home
mkdir -p "$HOME"

# --- GitHub auth bootstrap (mirrors personas-service pattern) ---
NETRC_SOURCE="${WOODPECKER_GITHUB_NETRC_SOURCE:-/root/.netrc}"
GH_HOSTS_SOURCE="${WOODPECKER_GITHUB_HOSTS_SOURCE:-/root/.config/gh/hosts.yml}"
if [ -f "$NETRC_SOURCE" ] && [ ! -f "$HOME/.netrc" ]; then
  cp "$NETRC_SOURCE" "$HOME/.netrc"
  chmod 600 "$HOME/.netrc"
fi

if [ ! -f "$HOME/.netrc" ] && [ -f "$GH_HOSTS_SOURCE" ]; then
  GH_USER="$(awk '/^[[:space:]]*user:/{print $2; exit}' "$GH_HOSTS_SOURCE")"
  GH_TOKEN="$(awk '/^[[:space:]]*oauth_token:/{print $2; exit}' "$GH_HOSTS_SOURCE")"
  if [ -n "$GH_TOKEN" ]; then
    {
      echo "machine github.com"
      echo "  login ${GH_USER:-x-access-token}"
      echo "  password $GH_TOKEN"
    } > "$HOME/.netrc"
    chmod 600 "$HOME/.netrc"
  fi
fi

if [ -n "${CI:-}" ] && [ ! -f "$HOME/.netrc" ]; then
  echo "FATAL: missing GitHub auth in CI; expected .netrc or gh hosts.yml for canonical checkout sync" >&2
  exit 1
fi
# --- end GitHub auth bootstrap ---

DEPLOY_BRANCH="${CI_COMMIT_BRANCH:-main}"
LATEST_SHA="$(git ls-remote origin "refs/heads/$DEPLOY_BRANCH" | awk '{print $1}')"
if [ -z "$LATEST_SHA" ]; then
  echo "Unable to resolve latest $DEPLOY_BRANCH SHA from origin" >&2
  exit 1
fi
DEPLOY_SHA="${CI_COMMIT_SHA:-$(git rev-parse HEAD)}"
if [ "$DEPLOY_SHA" != "$LATEST_SHA" ]; then
  echo "Skipping deploy for stale commit $DEPLOY_SHA; latest $DEPLOY_BRANCH is $LATEST_SHA"
  exit 0
fi

source scripts/deploy_lock.sh
deploy_lock_acquire
trap deploy_lock_release EXIT

export HOST_CANONICAL_WORKSPACE="${WHISPER_STT_BENCH_HOST_WORKSPACE:-/home/cooneycw/Projects/whisper-stt-bench}"
export WHISPER_BENCH_AWS_CREDENTIALS_DIR="${WHISPER_BENCH_AWS_CREDENTIALS_DIR:-/home/cooneycw/.aws}"
export AWS_SHARED_CREDENTIALS_FILE="${AWS_SHARED_CREDENTIALS_FILE:-$WHISPER_BENCH_AWS_CREDENTIALS_DIR/credentials}"
export AWS_CONFIG_FILE="${AWS_CONFIG_FILE:-$WHISPER_BENCH_AWS_CREDENTIALS_DIR/config}"
export AWS_SDK_LOAD_CONFIG="${AWS_SDK_LOAD_CONFIG:-1}"
export WOODPECKER_FANOUT_REPO_IDS="${WOODPECKER_FANOUT_REPO_IDS:-cooneycw/voice-bot-acs=6,cooneycw/whisper-stt-bench=7,cooneycw/personas-service=8}"
export DEPLOY_SHA DEPLOY_BRANCH
bash scripts/sync_canonical_checkout.sh "$HOST_CANONICAL_WORKSPACE"
cd "$HOST_CANONICAL_WORKSPACE"

COMPOSE_PROJECT_NAME=whisper-stt-bench \
make deploy

if [ "${WOODPECKER_SKIP_FANOUT:-false}" != "true" ]; then
  if ! python3 scripts/woodpecker_fanout.py \
    --branch "$DEPLOY_BRANCH" \
    --source "${CI_REPO:-cooneycw/whisper-stt-bench}" \
    --targets "cooneycw/voice-bot-acs,cooneycw/personas-service"; then
    if [ "${WOODPECKER_FANOUT_REQUIRED:-false}" = "true" ]; then
      echo "fanout: failed and WOODPECKER_FANOUT_REQUIRED=true" >&2
      exit 1
    fi
    echo "fanout: warning: failed; continuing because Whisper deploy is healthy" >&2
  fi
fi

# Restore host-user ownership on files touched by the root CI container
make fix-ownership
