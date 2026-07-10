#!/usr/bin/env bash
# Woodpecker agent + CI tooling watchdog for the GPU VM (proxVMwhisper43).
#
# Run periodically (systemd timer, see install-watchdog.sh). Recovers the
# three failure modes that have caused CI/deploy outages on this host:
#
#   1. Agent container stopped        -> docker start
#   2. Agent gRPC queue desync        -> docker restart
#      (agent reports "healthy" but stops claiming jobs; log signature:
#       "queue: task not found" / "extending pipeline deadline failed")
#   3. ci-deploy tooling image pruned -> rebuild from infra/ci-deploy
#      (docker_host_guard.sh prunes unused images under disk pressure and
#       deploy pipelines use `pull: false`)
set -euo pipefail

AGENT_CONTAINER="${AGENT_CONTAINER:-woodpecker-agent}"
CI_DEPLOY_IMAGE="${CI_DEPLOY_IMAGE:-ghcr.io/cooneycw/ci-deploy:3.12}"
REPO_DIR="${REPO_DIR:-/home/cooneycw/Projects/whisper-stt-bench}"
LOG_WINDOW="${LOG_WINDOW:-10m}"
RESTART_COOLDOWN_S="${RESTART_COOLDOWN_S:-900}"
STATE_FILE="${STATE_FILE:-/tmp/woodpecker-watchdog.last-restart}"

log() { echo "[watchdog $(date -u +%FT%TZ)] $*"; }

# --- 1. agent container must exist and be running -------------------------
if ! docker inspect "$AGENT_CONTAINER" >/dev/null 2>&1; then
    log "FATAL: agent container '$AGENT_CONTAINER' does not exist;" \
        "recreate it via woodpecker-agent/bootstrap-agent.sh"
    exit 1
fi

state="$(docker inspect -f '{{.State.Status}}' "$AGENT_CONTAINER")"
if [ "$state" != "running" ]; then
    log "agent state=$state; starting"
    docker start "$AGENT_CONTAINER"
fi

# --- 2. gRPC queue desync -> restart (with cooldown) -----------------------
# docker logs persist across restarts, so pre-restart error lines stay in
# the time window for a while; the cooldown prevents a restart loop.
last_restart=0
[ -f "$STATE_FILE" ] && last_restart="$(cat "$STATE_FILE" 2>/dev/null || echo 0)"
now="$(date +%s)"

if docker logs --since "$LOG_WINDOW" "$AGENT_CONTAINER" 2>&1 \
    | grep -qE "queue: task not found|extending pipeline deadline failed|connection refused|transport is closing"; then
    if [ $((now - last_restart)) -ge "$RESTART_COOLDOWN_S" ]; then
        log "queue desync signature in last $LOG_WINDOW; restarting agent"
        docker restart "$AGENT_CONTAINER"
        echo "$now" > "$STATE_FILE"
    else
        log "desync signature present but within restart cooldown; skipping"
    fi
fi

# --- 3. ci-deploy tooling image must be present ----------------------------
if ! docker image inspect "$CI_DEPLOY_IMAGE" >/dev/null 2>&1; then
    log "$CI_DEPLOY_IMAGE missing (pruned?); rebuilding from $REPO_DIR/infra/ci-deploy"
    if ! docker build -q -t "$CI_DEPLOY_IMAGE" "$REPO_DIR/infra/ci-deploy"; then
        log "build failed; trying registry pull"
        docker pull "$CI_DEPLOY_IMAGE" || {
            log "FATAL: cannot restore $CI_DEPLOY_IMAGE (build and pull failed)"
            exit 1
        }
    fi
    log "$CI_DEPLOY_IMAGE restored"
fi

log "ok: agent running, tooling image present"
