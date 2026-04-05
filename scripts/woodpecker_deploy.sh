#!/usr/bin/env bash
set -euo pipefail

git config --global --add safe.directory "*"
export HOME=/tmp/ci-home
mkdir -p "$HOME"

DEPLOY_BRANCH="${CI_COMMIT_BRANCH:-main}"
LATEST_SHA="$(git ls-remote origin "refs/heads/$DEPLOY_BRANCH" | awk '{print $1}')"
DEPLOY_SHA="${CI_COMMIT_SHA:-$(git rev-parse HEAD)}"
if [ "$DEPLOY_SHA" != "$LATEST_SHA" ]; then
  echo "Skipping deploy for stale commit $DEPLOY_SHA; latest $DEPLOY_BRANCH is $LATEST_SHA"
  exit 0
fi

source scripts/deploy_lock.sh
deploy_lock_acquire
trap deploy_lock_release EXIT

export HOST_CANONICAL_WORKSPACE="${WHISPER_STT_BENCH_HOST_WORKSPACE:-/home/cooneycw/Projects/whisper-stt-bench}"
export DEPLOY_SHA DEPLOY_BRANCH
bash scripts/sync_canonical_checkout.sh "$HOST_CANONICAL_WORKSPACE"
cd "$HOST_CANONICAL_WORKSPACE"

COMPOSE_PROJECT_NAME=whisper-stt-bench \
make deploy

if [ "${WOODPECKER_SKIP_FANOUT:-false}" != "true" ]; then
  python3 scripts/woodpecker_fanout.py \
    --branch "$DEPLOY_BRANCH" \
    --source "${CI_REPO:-cooneycw/whisper-stt-bench}" \
    --targets "cooneycw/voice-bot-acs,cooneycw/personas-service"
fi
