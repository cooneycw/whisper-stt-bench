#!/usr/bin/env bash
# deploy_lock.sh — Cross-project deploy mutex using a named Docker container.
#
# All CI deploy steps on the same host share the Docker daemon via socket
# mount. This script uses a named container as a distributed lock:
#   - docker create --name deploy-gateway-lock → succeeds only if no lock held
#   - If another deploy holds the lock, waits with backoff
#   - Lock auto-expires after DEPLOY_LOCK_TTL seconds (default 300)
#   - Caller MUST source this script and call deploy_lock_release on exit
#
# Usage:
#   source scripts/deploy_lock.sh
#   deploy_lock_acquire            # blocks until lock acquired
#   trap deploy_lock_release EXIT  # release on exit
#   make deploy                    # do the actual deploy
#
set -euo pipefail

DEPLOY_LOCK_NAME="${DEPLOY_LOCK_NAME:-deploy-gateway-lock}"
DEPLOY_LOCK_TTL="${DEPLOY_LOCK_TTL:-300}"
DEPLOY_LOCK_POLL="${DEPLOY_LOCK_POLL:-5}"
DEPLOY_LOCK_TIMEOUT="${DEPLOY_LOCK_TIMEOUT:-600}"

deploy_lock_acquire() {
  local elapsed=0
  echo "deploy-lock: acquiring lock '$DEPLOY_LOCK_NAME' (TTL=${DEPLOY_LOCK_TTL}s)..."

  while true; do
    # Try to create a lock container. Fails if name already taken.
    if docker create \
        --name "$DEPLOY_LOCK_NAME" \
        --label "deploy-lock=true" \
        --label "deploy-lock-pipeline=${CI_PIPELINE_NUMBER:-local}" \
        --label "deploy-lock-repo=${CI_REPO:-local}" \
        alpine sleep "$DEPLOY_LOCK_TTL" >/dev/null 2>&1; then
      # Start the container so it auto-exits after TTL (safety net)
      docker start "$DEPLOY_LOCK_NAME" >/dev/null 2>&1 || true
      echo "deploy-lock: acquired by pipeline ${CI_PIPELINE_NUMBER:-local} (repo: ${CI_REPO:-local})"
      return 0
    fi

    # Lock is held — check if it's stale (container exited = TTL expired)
    local state
    state=$(docker inspect --format='{{.State.Status}}' "$DEPLOY_LOCK_NAME" 2>/dev/null || echo "missing")
    if [ "$state" = "exited" ] || [ "$state" = "missing" ]; then
      # Stale lock — clean up and retry
      docker rm -f "$DEPLOY_LOCK_NAME" >/dev/null 2>&1 || true
      echo "deploy-lock: removed stale lock (state=$state), retrying..."
      continue
    fi

    # Lock is active — wait
    local holder_pipeline holder_repo
    holder_pipeline=$(docker inspect --format='{{index .Config.Labels "deploy-lock-pipeline"}}' "$DEPLOY_LOCK_NAME" 2>/dev/null || echo "unknown")
    holder_repo=$(docker inspect --format='{{index .Config.Labels "deploy-lock-repo"}}' "$DEPLOY_LOCK_NAME" 2>/dev/null || echo "unknown")
    echo "deploy-lock: held by pipeline $holder_pipeline ($holder_repo), waiting... (${elapsed}s/${DEPLOY_LOCK_TIMEOUT}s)"

    sleep "$DEPLOY_LOCK_POLL"
    elapsed=$((elapsed + DEPLOY_LOCK_POLL))

    if [ "$elapsed" -ge "$DEPLOY_LOCK_TIMEOUT" ]; then
      echo "deploy-lock: timeout after ${DEPLOY_LOCK_TIMEOUT}s — forcing lock release" >&2
      docker rm -f "$DEPLOY_LOCK_NAME" >/dev/null 2>&1 || true
    fi
  done
}

deploy_lock_release() {
  docker rm -f "$DEPLOY_LOCK_NAME" >/dev/null 2>&1 || true
  echo "deploy-lock: released"
}
