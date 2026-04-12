#!/usr/bin/env bash
set -euo pipefail

MIN_FREE_GB="${DOCKER_GUARD_MIN_FREE_GB:-12}"
PRUNE_UNTIL="${DOCKER_GUARD_PRUNE_UNTIL:-168h}"
DOCKER_ROOT="${DOCKER_GUARD_ROOT:-$(docker info --format '{{.DockerRootDir}}' 2>/dev/null || echo /var/lib/docker)}"
REQUIRED_MB=$((MIN_FREE_GB * 1024))

resolve_probe_path() {
  local candidate="${1:-/}"
  if [ -z "$candidate" ]; then
    echo "/"
    return 0
  fi

  while :; do
    if [ -e "$candidate" ]; then
      echo "$candidate"
      return 0
    fi
    if [ "$candidate" = "/" ] || [ "$candidate" = "." ]; then
      echo "/"
      return 0
    fi
    candidate="$(dirname "$candidate")"
  done
}

is_uint() {
  case "${1:-}" in
    "" | *[!0-9]*)
      return 1
      ;;
    *)
      return 0
      ;;
  esac
}

PROBE_PATH="$(resolve_probe_path "$DOCKER_ROOT")"

available_mb() {
  df -Pm "$PROBE_PATH" 2>/dev/null | awk 'NR==2 {print $4}'
}

space_check_status() {
  local available
  available="$(available_mb)"
  if ! is_uint "$available"; then
    echo "docker-guard: unable to determine free space for probe path $PROBE_PATH" >&2
    return 2
  fi
  if [ "$available" -ge "$REQUIRED_MB" ]; then
    return 0
  fi
  return 1
}

print_usage() {
  echo "docker-guard: docker root=$DOCKER_ROOT"
  if [ "$PROBE_PATH" != "$DOCKER_ROOT" ]; then
    echo "docker-guard: disk probe path=$PROBE_PATH (docker root not present)"
  fi
  df -h "$PROBE_PATH" || true
  docker system df || true
}

echo "docker-guard: checking free space (need >= ${MIN_FREE_GB}GB)"
print_usage

if space_check_status; then
  echo "docker-guard: enough free space available"
  exit 0
else
  status=$?
  if [ "$status" -eq 2 ]; then
    exit 1
  fi
fi

echo "docker-guard: low free space detected; pruning reclaimable Docker data"
docker container prune -f || true
docker builder prune -af --filter "until=$PRUNE_UNTIL" || true
docker image prune -af --filter "until=$PRUNE_UNTIL" || true
docker volume prune -f || true
docker network prune -f || true

if ! space_check_status; then
  status=$?
  if [ "$status" -eq 2 ]; then
    exit 1
  fi
  echo "docker-guard: still low after filtered prune; running aggressive prune"
  docker builder prune -af || true
  docker image prune -af || true
fi

print_usage

if ! space_check_status; then
  status=$?
  if [ "$status" -eq 2 ]; then
    exit 1
  fi
  echo "docker-guard: insufficient free space after cleanup" >&2
  exit 1
fi

echo "docker-guard: reclaimed enough space"
