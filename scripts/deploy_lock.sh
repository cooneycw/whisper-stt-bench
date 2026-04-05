#!/usr/bin/env bash
# Cross-project deploy mutex using a named Docker container.
set -euo pipefail

DEPLOY_LOCK_NAME="${DEPLOY_LOCK_NAME:-deploy-gateway-lock}"
DEPLOY_LOCK_TTL="${DEPLOY_LOCK_TTL:-300}"
DEPLOY_LOCK_POLL="${DEPLOY_LOCK_POLL:-5}"
DEPLOY_LOCK_TIMEOUT="${DEPLOY_LOCK_TIMEOUT:-600}"

deploy_lock_acquire() {
  local elapsed=0
  echo "deploy-lock: acquiring lock '$DEPLOY_LOCK_NAME' (TTL=${DEPLOY_LOCK_TTL}s)..."

  while true; do
    if docker create \
      --name "$DEPLOY_LOCK_NAME" \
      --label "deploy-lock=true" \
      --label "deploy-lock-pipeline=${CI_PIPELINE_NUMBER:-local}" \
      --label "deploy-lock-repo=${CI_REPO:-local}" \
      alpine sleep "$DEPLOY_LOCK_TTL" >/dev/null 2>&1; then
      docker start "$DEPLOY_LOCK_NAME" >/dev/null 2>&1 || true
      echo "deploy-lock: acquired by pipeline ${CI_PIPELINE_NUMBER:-local} (repo: ${CI_REPO:-local})"
      return 0
    fi

    local state
    state=$(docker inspect --format='{{.State.Status}}' "$DEPLOY_LOCK_NAME" 2>/dev/null || echo "missing")
    if [ "$state" = "exited" ] || [ "$state" = "missing" ]; then
      docker rm -f "$DEPLOY_LOCK_NAME" >/dev/null 2>&1 || true
      echo "deploy-lock: removed stale lock (state=$state), retrying..."
      continue
    fi

    local holder_pipeline holder_repo
    holder_pipeline=$(docker inspect --format='{{index .Config.Labels "deploy-lock-pipeline"}}' "$DEPLOY_LOCK_NAME" 2>/dev/null || echo "unknown")
    holder_repo=$(docker inspect --format='{{index .Config.Labels "deploy-lock-repo"}}' "$DEPLOY_LOCK_NAME" 2>/dev/null || echo "unknown")
    echo "deploy-lock: held by pipeline $holder_pipeline ($holder_repo), waiting... (${elapsed}s/${DEPLOY_LOCK_TIMEOUT}s)"

    sleep "$DEPLOY_LOCK_POLL"
    elapsed=$((elapsed + DEPLOY_LOCK_POLL))
    if [ "$elapsed" -ge "$DEPLOY_LOCK_TIMEOUT" ]; then
      echo "deploy-lock: timeout after ${DEPLOY_LOCK_TIMEOUT}s; forcing lock release" >&2
      docker rm -f "$DEPLOY_LOCK_NAME" >/dev/null 2>&1 || true
    fi
  done
}

deploy_lock_release() {
  docker rm -f "$DEPLOY_LOCK_NAME" >/dev/null 2>&1 || true
  echo "deploy-lock: released"
}
