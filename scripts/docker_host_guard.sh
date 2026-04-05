#!/usr/bin/env bash
set -euo pipefail

MIN_FREE_GB="${DOCKER_GUARD_MIN_FREE_GB:-20}"
PRUNE_UNTIL="${DOCKER_GUARD_PRUNE_UNTIL:-168h}"
DOCKER_ROOT="${DOCKER_GUARD_ROOT:-$(docker info --format '{{.DockerRootDir}}' 2>/dev/null || echo /var/lib/docker)}"
REQUIRED_MB=$((MIN_FREE_GB * 1024))

available_mb() {
  df -Pm "$DOCKER_ROOT" | awk 'NR==2 {print $4}'
}

print_usage() {
  echo "docker-guard: docker root=$DOCKER_ROOT"
  df -h "$DOCKER_ROOT" || true
  docker system df || true
}

echo "docker-guard: checking free space (need >= ${MIN_FREE_GB}GB)"
print_usage

if [ "$(available_mb)" -ge "$REQUIRED_MB" ]; then
  echo "docker-guard: enough free space available"
  exit 0
fi

echo "docker-guard: low free space detected; pruning reclaimable Docker data"
docker container prune -f || true
docker builder prune -af --filter "until=$PRUNE_UNTIL" || true
docker image prune -af --filter "until=$PRUNE_UNTIL" || true
docker volume prune -f || true
docker network prune -f || true

if [ "$(available_mb)" -lt "$REQUIRED_MB" ]; then
  echo "docker-guard: still low after filtered prune; running aggressive prune"
  docker builder prune -af || true
  docker image prune -af || true
fi

print_usage

if [ "$(available_mb)" -lt "$REQUIRED_MB" ]; then
  echo "docker-guard: insufficient free space after cleanup" >&2
  exit 1
fi

echo "docker-guard: reclaimed enough space"
